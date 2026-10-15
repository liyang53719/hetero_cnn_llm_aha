"""Integer-only transposed exact-tree candidate; no payload, RTL or CI run.

Canonical tree/context/ACK protocol is imported unchanged from the reviewed
M16 candidate. Only geometry, physical addresses and supply transactions differ.
"""
from dataclasses import asdict, dataclass, replace
from candidates.qwen2_exact_tree_scheduler import model as exact
from .gather import Gather, segment_address

M, N, K = 128, 32, 1536
X_BYTES, X_WIRE_BYTES, W_BYTES = M*K*2, M*K*4, K*N*2
A_BYTES, B_BYTES = 16*1376*32, 16*160*32
PANELS = (1536+256)//32


def x_address(m, k):
    exact.require(type(m) is int and type(k) is int and 0 <= m < M and 0 <= k < K, 'X bounds')
    return (k & 15) ^ (m // 16), (k // 16)*8 + m//16, m % 16


def w_address(half, t, n):
    """Candidate partial slot: separate t from logical X k=64*t+p.

    Existing half/depth/group formula, Ncontext=0, two distinct 40KiB halves.
    Only 24x64B of each half is used. Accumulator context is NOT B Ncontext.
    """
    exact.require(half in (0, 1) and 0 <= t < 24 and 0 <= n < N, 'W slot bounds')
    linear = half*1280 + t*10 + n//16
    return linear % 16, linear//16, n % 16


def output_coordinate(m, n):
    exact.require(0 <= m < M and 0 <= n < N, 'output bounds')
    return n % 16, (n//16)*128 + m


def operand_wires(x128, w32):
    exact.require(len(x128) == 128 and len(w32) == 32, 'transposed wire geometry')
    # Only 160 BF16 values are meaningful in the existing 272-value envelope.
    return tuple(w32[:16]), tuple(x128) + tuple(w32[16:]) + (0,)*112


def physical_operands(a16, b256, slice_index, row, column):
    exact.require(0 <= slice_index < 8 and 0 <= row < 16 and 0 <= column < 32, 'physical bounds')
    weight = a16[row] if slice_index < 4 else b256[128+row]
    activation = b256[(slice_index % 4)*32+column]
    return weight, activation


def weight_ddr_offset(p, t, nbase=0, width=1536):
    exact.require(0 <= p < 64 and 0 <= t < 24 and width in (256, 1536), 'weight shape')
    exact.require(nbase % 32 == 0 and 0 <= nbase <= width-32, 'weight panel')
    return ((64*t+p)*width+nbase)*2


def panel_identity(index):
    exact.require(type(index) is int and 0 <= index < 56, 'Q/K panel index')
    return ('Q', 1536, index*32) if index < 48 else ('K', 256, (index-48)*32)


@dataclass(frozen=True)
class SupplyTag(exact.Tag):
    tensor: str = ''
    width: int = 0
    nbase: int = 0
    address: int = -1  # Relative to the named tensor, NOT an assumed real DDR base.
    b_half: int = -1
    b_t: int = -1
    x_k: int = -1
    block: int = -1
    row: int = -1


def transactions(op, costs, ingress='legacy_rmw'):
    if op.kind == 'load_a' and ingress == 'gather2_candidate':
        for block in range(768):
            for row in range(16):
                yield 'external_read_x', costs.external_read_response, block*16+row, block % 2, 64
            yield 'new_x_16bank_bulk_commit_ack', costs.local_commit_ack, block, block % 2, 512
    elif op.kind == 'load_a':
        # Public21 Norm writes FP32 containers; Dense activation_bf16=False.
        # Existing combinational conversion yields one 32B BF16 RMW per 64B beat.
        for word in range(768):
            yield 'x_zero_all_banks_ack', costs.local_commit_ack, word, -1, 512
        for packet in range(X_WIRE_BYTES//64):
            yield 'external_read_x', costs.external_read_response, packet, -1, 64
            # Issue reads all 16 banks; next edge commits merged words.
            # Delayed ACK holds metadata, not a hidden 4096-bit SRAM response.
            yield 'x_rmw_commit_ack', costs.local_commit_ack, packet, -1, 32
    elif op.kind == 'fill_b':
        for t in range(24):
            yield 'external_read_w', costs.external_read_response, t, -1, 64
            yield 'w_two_bank_commit_ack', costs.local_commit_ack, t, -1, 64
    elif op.kind == 'fma':
        # 8 A banks supply X128, two B banks supply W32. W fans across M.
        yield 'operand_read_X128_W32', costs.local_read, -1, -1, 320
        yield 'fma_nonemit_return', costs.fma, -1, -1, 0
    else:
        yield from exact.transactions(op, costs)


class TransposedScheduler(exact.Scheduler):
    """Same one-outstanding conservative core, bounded below existing credits.

    A cold load is mandatory at each real legacy job. Warm restart can only be
    modeled with a retained lease from THIS same fully completed event engine;
    no caller-provided a_ready boolean is used by run().
    """
    def __init__(self, costs=exact.Costs(), *, ingress='legacy_rmw', shared_qk_lease=False, **kwargs):
        exact.require(ingress in ('legacy_rmw', 'gather2_candidate'), 'ingress selection')
        super().__init__(costs, **kwargs)
        exact.require(type(shared_qk_lease) is bool, 'explicit shared Q/K lease selection')
        self.shared_qk_lease = shared_qk_lease
        self.ingress = ingress
        self.gather = Gather() if ingress == 'gather2_candidate' else None
        self.replace_transactions = False
        self.b_half = self.b_loading_half = 1
        self.panel = panel_identity(self.tile)

    def start(self, op):
        exact.require(not self.poisoned and not self.done, 'epoch is locked or terminal')
        exact.require(self.active is None and self.pending is None and self.inflight is None,
                      'active transaction/context hazard')
        if op.kind == 'fill_b':
            exact.require(0 <= op.p < 64, 'B partial range')
            self.b_loading_half = self.b_half ^ 1
        if op.kind == 'load_a' and self.gather is not None:
            exact.require(not any(x is not None for x in self.contexts) and not any(self.slot_committed),
                          'activation refill while values remain live')
            exact.require(self.gather.dma is None and self.gather.write is None, 'old gather drain')
            self.gather = Gather()
        self.replace_transactions = True
        try:
            super().start(op)
        except Exception:
            self.replace_transactions = False
            raise

    def _next(self):
        if self.replace_transactions:
            self.micro = iter(transactions(self.active, self.costs, self.ingress))
            self.replace_transactions = False
        super()._next()
        if self.pending is not None:
            req, op = self.pending, self.active
            data = asdict(req.tag)
            tensor, width, nbase = self.panel
            extra = dict(tensor=tensor, width=width, nbase=nbase)
            if op.kind == 'fill_b':
                extra.update(address=weight_ddr_offset(op.p, req.tag.packet, nbase, width),
                             b_half=self.b_loading_half, b_t=req.tag.packet, x_k=64*req.tag.packet+op.p)
            elif op.kind == 'fma':
                extra.update(b_half=self.b_half, b_t=op.t, x_k=64*op.t+op.p)
            elif op.kind == 'load_a':
                extra.update(tensor='X', width=1536, nbase=0)
                if req.tag.kind == 'external_read_x' and self.ingress == 'gather2_candidate':
                    block, row = divmod(req.tag.packet, 16)
                    extra.update(block=block, row=row, address=segment_address(block, row))
                elif req.tag.kind == 'new_x_16bank_bulk_commit_ack':
                    extra.update(block=req.tag.packet)
                elif req.tag.kind in ('external_read_x', 'x_rmw_commit_ack'):
                    m, q = divmod(req.tag.packet, 96)
                    extra.update(block=q*8+m//16, row=m % 16, address=(m*1536+q*16)*4)
            self.pending = replace(req, tag=SupplyTag(**data, **extra))

    def tick(self, *, request_ready=True, **kwargs):
        if request_ready and self.inflight is None and self.pending is not None and self.gather is not None:
            tag = self.pending.tag
            if tag.kind == 'external_read_x':
                self.gather.issue_segment(tag, tag.block, tag.row, tag.address)
            elif tag.kind == 'new_x_16bank_bulk_commit_ack':
                self.gather.issue_commit(tag, tag.block)
        super().tick(request_ready=request_ready, **kwargs)

    def accept_response(self, tag):
        if self.gather is not None and self.inflight is not None and tag == self.inflight[0].tag:
            exact.require(self.cycle >= self.inflight[1], 'response before service latency')
            if tag.kind == 'external_read_x':
                self.gather.accept_segment(tag)
            elif tag.kind == 'new_x_16bank_bulk_commit_ack':
                self.gather.accept_commit(tag)
        super().accept_response(tag)

    def abort(self):
        super().abort()
        if self.gather is not None:
            self.gather.abort()

    def _commit_command(self):
        if self.active.kind == 'fill_b':
            self.b_half = self.b_loading_half
        if self.active.kind == 'load_a' and self.gather is not None:
            exact.require(self.gather.ready, 'gather A publish before all bulk ACKs')
        super()._commit_command()

    def next_panel(self, tile):
        # Within-job A reuse exists; cross-Q/K reuse requires a NEW lease.
        exact.require(tile == self.tile + 1 and tile < 56, 'panel must be exact monotonic successor')
        exact.require(self.done and self.credit and self.active is None and not self.poisoned,
                      'retained A panel requires previous output ACK/drain')
        exact.require(self.a_ready and all(c or s is None for c, s in zip(self.slot_consumed, self.slots)),
                      'A lease/slot release incomplete')
        self.contexts = [None]*5
        self.context_progress = [None]*5
        self.slots, self.slot_committed, self.slot_consumed = [None]*2, [False]*2, [False]*2
        new_panel = panel_identity(tile)
        if new_panel[0] != self.panel[0] and not self.shared_qk_lease:
            self.a_ready = False
            if self.gather is not None:
                self.gather = Gather()
        self.tile, self.done, self.b_partial = tile, False, None
        self.panel = new_panel


def run(panels=1, costs=exact.Costs(), ready=None, max_cycles=5_000_000,
        ingress='legacy_rmw', shared_qk_lease=False):
    exact.require(type(panels) is int and 1 <= panels <= PANELS, 'panel bound')
    e = TransposedScheduler(costs, ingress=ingress, shared_qk_lease=shared_qk_lease)
    for tile in range(panels):
        if tile:
            e.next_panel(tile)
        for op in exact.program():
            if tile and op.kind == 'load_a' and (tile != 48 or shared_qk_lease):
                continue
            e.start(op)
            while e.active is not None:
                exact.require(e.cycle < max_cycles, 'bounded run incomplete, not success')
                e.tick(**(ready(e) if ready else {}))
    exact.require(e.done and e.credit == 1, 'final raw ACK required')
    return e


def ledger():
    # Physical floors permit overlap. Cold X is excluded from warm floor ONLY
    # by explicitly naming that scope; real owner clears/reloads each job.
    arithmetic = PANELS*(1536+64)
    cold_x = 768 + 2*(X_BYTES//32)
    current_two_jobs = arithmetic + 2*cold_x
    proposed_shared_job = arithmetic + cold_x
    useful = PANELS*1536
    dma_floor = PANELS*1536*2  # Current single-beat request and return cannot coincide.
    context_area = 1536*5 + 63*2*5 + 5 + 3*(512+256)
    context_floor = (context_area + 4)//5
    old_warm_floor = max(arithmetic, dma_floor, PANELS*context_floor)
    return dict(status='INTEGER_BEHAVIOR_AND_CONDITIONAL_PORT_BOUNDS_ONLY',
        geometry=dict(logical_m=128, logical_n=32, physical_macs=4096, contexts=5),
        unique_bytes=dict(x_sram=X_BYTES, x_wire=X_WIRE_BYTES, w_per_panel=W_BYTES, qk_weights=PANELS*W_BYTES,
                          fp32_output_per_panel=16384),
        physical=dict(a_bytes=A_BYTES, b_bytes=B_BYTES, accum_bytes=81920,
            retained_leaf_result_bytes=81920, result_fifo_bytes=32768, final_value_bytes=16384,
            x_resident_bytes=X_BYTES, tree_a_slots_bytes=32768,
            new_compact_route_a_reserved_bytes=X_BYTES+32768,
            legacy_tilebank_slot_address_reservation_bytes=163840,
            legacy_tilebank_total_a_reservation_bytes=X_BYTES+163840,
            b_half_reserved_bytes=40960, b_half_active_payload_bytes=1536,
            b_double_partial_active_payload_bytes=3072, mailbox_capacity_bytes=1024,
            modeled_mailbox_peak_bytes=64, dma_transfers_outstanding=1,
            operand_credit_capacity=4, modeled_operand_credit_peak=1,
            new_packet_hold_bytes=64, result_fifo_borrowed=False),
        bounds=dict(warm_arithmetic_cycles=arithmetic, warm_arithmetic_ceiling=useful/arithmetic,
            warm_w_fill_cycles=PANELS*W_BYTES//64,
            warm_existing_singlebeat_dma_min_cycles=dma_floor,
            warm_existing_singlebeat_dma_mac_ceiling=useful/dma_floor,
            whole_context_lock_area_per_panel=context_area,
            whole_context_lock_min_cycles_per_panel=context_floor,
            whole_context_lock_mac_ceiling=1536/context_floor,
            legacy_warm_combined_floor=old_warm_floor,
            legacy_two_job_cold_combined_floor=old_warm_floor+2*cold_x,
            legacy_two_job_cold_combined_mac_ceiling=useful/(old_warm_floor+2*cold_x),
            new_shared_lease_cold_combined_floor=old_warm_floor+cold_x,
            new_shared_lease_cold_combined_mac_ceiling=useful/(old_warm_floor+cold_x),
            cold_x_clear_cycles=768, cold_x_rmw_cycles=24576,
            cold_x_owner_state_floor=37632,
            legacy_owner_and_dma_cold_floor=old_warm_floor+2*37632,
            legacy_owner_and_dma_cold_mac_ceiling=useful/(old_warm_floor+2*37632),
            legacy_two_job_cold_cycles_floor=current_two_jobs,
            legacy_two_job_cold_mac_ceiling=useful/current_two_jobs,
            new_shared_x_lease_cold_cycles_floor=proposed_shared_job,
            new_shared_x_lease_cold_mac_ceiling=useful/proposed_shared_job,
            fullblock_shared_rms_residency_cycles=None,
            fullblock_shared_rms_residency_status='BLOCKED_UNPROVEN_RMS_TO_A_RESIDENT_INTERFACE'),
        gather2_candidate=dict(status='NEW_UNIMPLEMENTED_ROUTE_INTEGER_CONTROL_ONLY',
            buffer_count=2, buffer_bytes_each=512, extra_buffer_bytes=1024,
            x_wire_bytes=X_WIRE_BYTES, segments=12288, bulk_write_commits=768,
            existing_singlebeat_dma_min_cycles=24576, clear_and_rmw_removed=True,
            note='Still cannot exceed DMA50% or whole-context72.316% bounds'),
        target80_status='NO_GO_UNDER_EXISTING_DMA_INGRESS_AND_WHOLE_CONTEXT_LOCK_CONTRACTS',
        necessary_unimplemented_target80_changes=['masked A ingress or proven upstream-resident route',
            'bounded tagged gather or fully charged prepacking with same 512-bit bandwidth',
            'new packetwise context release or isolated frontier mode; whole-vector locks must change'],
        required_new_interfaces=['exact FP32 Add/restore', 'independent X-k and B-half/t selection',
            'partial B identity separate from accumulator context', 'raw context packet route',
            'A tree-slot commit/ownership route', 'cross-panel A lease (within one candidate job)'],
        hardware_cycles=None, hardware_utilization=None, rtl_executed=False,
        default_legacy_path_changed=False)


def report():
    e = run()
    out = ledger()
    out['serialized_cold_one_panel'] = dict(cycles=e.cycle, stats=dict(e.stats),
        service_cycles=dict(e.service_cycles), peak_contexts=e.peak_live_contexts,
        model_mac_ratio=1536/e.cycle)
    out['scope'] = 'Cold one panel through raw ACK; serial DFS; no independent-leaf/prefetch overlap.'
    return out


if __name__ == '__main__':
    import json
    print(json.dumps(report(), indent=2, sort_keys=True))
