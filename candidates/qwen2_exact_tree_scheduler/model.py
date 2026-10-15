"""Software-only exact-tree and bounded event candidate. No production wiring.

The wide FP32 Add/context read/restore ports below DO NOT EXIST in current RTL.
One command and one transaction are outstanding: an intentionally conservative
executable schedule, not a throughput claim about a future optimized controller.
"""
from collections import Counter
from dataclasses import asdict, dataclass
import json

WORDS = 4096
PACKETS = WORDS // 16
CONTEXTS = 5
TILE_BYTES = WORDS * 4


class ProtocolError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ProtocolError(message)


def fold(xs):
    xs = list(xs)
    while len(xs) > 1:
        n = len(xs) // 2
        xs = [(xs[i], xs[i + n]) for i in range(n)]
    return xs[0]


TREE = fold(fold(8 * r + lane for r in range(8)) for lane in range(8))
SUBTREES = dict(zip(('S04', 'S26', 'S15', 'S37'),
                   (TREE[0][0], TREE[0][1], TREE[1][0], TREE[1][1])))


def leaves(node):
    return [node] if isinstance(node, int) else leaves(node[0]) + leaves(node[1])


@dataclass(frozen=True)
class Op:
    kind: str
    dst: int = -1
    rhs: int = -1
    node: str = ''
    left: str = ''
    right: str = ''
    p: int = -1
    t: int = -1
    slot: int = -1


def program():
    """Four exact 16-leaf DFS trees require five vector contexts, never six."""
    ops, free, names = [Op('load_a')], list(range(CONTEXTS)), {}

    def walk(node, name=None):
        label = name or (f'p{node}' if isinstance(node, int) else f'n{len(names)}')
        names[node] = label
        if isinstance(node, int):
            require(bool(free), 'five-context allocator exhausted')
            dst = free.pop(0)
            ops.append(Op('fill_b', p=node))
            for t in range(24):
                out = label if t == 23 else f'{label}:{t}'
                ops.append(Op('fma', dst, node=out,
                              left='' if t == 0 else f'{label}:{t - 1}', p=node, t=t))
            return dst, label
        lhs, ln = walk(node[0])
        rhs, rn = walk(node[1])
        ops.append(Op('add', lhs, rhs, label, ln, rn))
        free.append(rhs); free.sort()
        return lhs, label

    def spill(ctx, label, slot):
        ops.append(Op('spill', ctx, node=label, left=label, slot=slot))
        free.append(ctx); free.sort()

    def restore(label, slot):
        ctx = free.pop(0)
        ops.append(Op('restore', ctx, node=label, slot=slot))
        return ctx

    c, label = walk(SUBTREES['S04'], 'S04'); spill(c, label, 0)
    c, label = walk(SUBTREES['S26'], 'S26')
    l = restore('S04', 0)
    ops.append(Op('add', l, c, 'T0', 'S04', 'S26')); free.append(c); free.sort()
    spill(l, 'T0', 0)
    c, label = walk(SUBTREES['S15'], 'S15'); spill(c, label, 1)
    c, label = walk(SUBTREES['S37'], 'S37')
    l = restore('S15', 1)
    ops.append(Op('add', l, c, 'T1', 'S15', 'S37')); free.append(c); free.sort()
    r = l; l = restore('T0', 0)
    ops.append(Op('add', l, r, 'ROOT', 'T0', 'T1')); free.append(r); free.sort()
    ops.append(Op('zero', l, node='RAW', left='ROOT'))
    ops.append(Op('output', l, node='RAW', left='RAW'))
    return ops


ORDERED_ADDS = {op.node: (op.left, op.right) for op in program() if op.kind == 'add'}
SLOT_VALUES = {('S04', 0), ('T0', 0), ('S15', 1)}


@dataclass(frozen=True)
class Costs:
    mode: str = 'wide_candidate'
    fma: int = 5
    wide_add: int = 5
    local_read: int = 1
    local_commit_ack: int = 1
    context_commit_ack: int = 1
    external_read_response: int = 2
    external_write_ack: int = 2
    vector16_add_response: int = 2

    def __post_init__(self):
        require(self.mode in ('wide_candidate', 'vector16_baseline'), 'unknown mode')
        require(all(type(v) is int and v > 0 for k, v in asdict(self).items() if k != 'mode'),
                'positive integer latencies required')
        require(self.fma >= 5 and self.wide_add >= 5, 'five stages cannot be shortened')


@dataclass(frozen=True)
class Tag:
    epoch: int
    tile: int
    sequence: int
    kind: str
    node: str
    context: int
    packet: int
    half: int
    rhs: int
    slot: int
    partial: int
    k: int


@dataclass(frozen=True)
class Request:
    tag: Tag
    latency: int
    bytes: int = 0


def a_address(slot, packet, half):
    require(slot in (0, 1) and 0 <= packet < PACKETS and half in (0, 1), 'A slot bounds')
    word = 2 * packet + half
    return word % 16, 768 + 32 * slot + word // 16


def transactions(op, costs):
    """A generator, not a hidden unbounded payload queue. Each yield needs ACK.

    Every transaction occupies an issue cycle, then latency complete cycles.
    Response backpressure keeps its sole credit and payload. No next request
    issues on that response edge (conservative, no zero-time fall-through).
    """
    def req(kind, latency, packet=-1, half=-1, size=0):
        return kind, latency, packet, half, size
    if op.kind == 'load_a':
        # Cold M16 x K1536 BF16 tile; no free prefetch or conversion assumed.
        for packet in range(16 * 1536 * 2 // 64):
            yield req('external_read_a', costs.external_read_response, packet, size=64)
            for half in (0, 1):
                yield req('activation_write', costs.local_commit_ack, packet, half, 32)
    elif op.kind == 'fill_b':
        for packet in range(24 * 256 * 2 // 64):
            yield req('external_read_b', costs.external_read_response, packet, size=64)
            yield req('b_write_two_banks', costs.local_commit_ack, packet, size=64)
    elif op.kind == 'fma':
        yield req('operand_read_A16_B256', costs.local_read, size=544)
        yield req('fma_nonemit_return', costs.fma)
    elif op.kind in ('add', 'zero'):
        if costs.mode == 'wide_candidate':
            yield req('new_wide_fp32_add_return', costs.wide_add)
        else:
            for packet in range(PACKETS):
                yield req('new_context_read', costs.local_read, packet, size=64)
                if op.kind == 'add':
                    yield req('new_context_read_rhs', costs.local_read, packet, size=64)
                yield req('borrowed_vector16_add', costs.vector16_add_response, packet)
                yield req('new_context_write_ack', costs.context_commit_ack, packet, size=64)
    elif op.kind == 'spill':
        for packet in range(PACKETS):
            yield req('new_context_read', costs.local_read, packet, size=64)
            for half in (0, 1):
                yield req('a_write_ack', costs.local_commit_ack, packet, half, 32)
    elif op.kind == 'restore':
        for packet in range(PACKETS):
            yield req('a_read_two_banks', costs.local_read, packet, size=64)
            yield req('new_context_write_ack', costs.context_commit_ack, packet, size=64)
    elif op.kind == 'output':
        for packet in range(PACKETS):
            yield req('new_context_read', costs.local_read, packet, size=64)
            yield req('external_output_write_ack', costs.external_write_ack, packet, size=64)
    else:
        raise ProtocolError('unknown operation')


class Scheduler:
    """Finite, serialized issue/return engine with explicit ownership and drain.

    Context labels stand in for vector payloads. The independent numeric model
    below checks arithmetic. This engine checks transactions, not RTL timing.
    """
    def __init__(self, costs=Costs(), *, epoch=1, tile=0):
        self.costs, self.epoch, self.tile = costs, epoch, tile
        self.contexts = [None] * CONTEXTS
        self.context_progress = [None] * CONTEXTS
        self.a_ready, self.b_partial = False, None
        self.slots = [None, None]
        self.slot_committed = [False, False]
        self.slot_consumed = [False, False]
        self.active = self.pending = self.inflight = None
        self.micro = None
        self.sequence = self.cycle = 0
        self.poisoned = self.done = False
        self.stats, self.latency_cycles = Counter(), Counter()
        self.service_cycles = Counter()
        self.stall_cycles = Counter()
        self.peak_live_contexts = 0
        self.history = []  # Control trace only, capped to program size by caller.
        self.record_history = False

    @property
    def credit(self):
        return int(self.inflight is None)

    def start(self, op):
        require(not self.poisoned and not self.done, 'epoch is locked or terminal')
        require(self.active is None and self.pending is None and self.inflight is None,
                'active transaction/context hazard')
        require(op.kind in ('load_a', 'fill_b', 'fma', 'add', 'zero', 'spill', 'restore', 'output'),
                'unknown command')
        if op.kind == 'add':
            require(ORDERED_ADDS.get(op.node) == (op.left, op.right), 'noncanonical ordered tree edge')
        if op.kind == 'spill':
            require(op.node == op.left and (op.node, op.slot) in SLOT_VALUES, 'noncanonical spill identity')
        if op.kind == 'restore':
            require((op.node, op.slot) in SLOT_VALUES, 'noncanonical restore identity')
        if op.kind == 'zero':
            require((op.left, op.node) == ('ROOT', 'RAW'), 'noncanonical explicit zero tail')
        if op.kind == 'output':
            require(op.left == op.node == 'RAW', 'noncanonical raw output')
        if op.kind == 'load_a':
            require(not any(x is not None for x in self.contexts) and not any(self.slot_committed),
                    'activation refill while values remain live')
            self.a_ready = False
        if op.kind == 'fill_b':
            require(0 <= op.p < 64, 'B partial range')
            self.b_partial = None
        if op.kind not in ('load_a', 'fill_b'):
            require(0 <= op.dst < CONTEXTS, 'context out of range')
            if op.kind == 'restore':
                require(op.slot in (0, 1), 'slot out of range')
                require(self.contexts[op.dst] is None, 'early context reuse')
                require(not self.slot_consumed[op.slot], 'duplicate A restore consumption')
                require(self.slot_committed[op.slot] and self.slots[op.slot] == op.node,
                        'A read before matching commit fence')
            elif op.kind == 'fma' and op.t == 0:
                require(self.contexts[op.dst] is None, 'early context reuse')
                require(0 <= op.p < 64, 'partial range')
            else:
                require(self.contexts[op.dst] == op.left, 'destination RAW/tag hazard')
            if op.kind == 'fma':
                require(0 <= op.t < 24 and 0 <= op.p < 64, 'FMA index range')
                expected = '' if op.t == 0 else f'p{op.p}:{op.t - 1}'
                require(op.left == expected, 'partial FMA ordering')
                output = f'p{op.p}' if op.t == 23 else f'p{op.p}:{op.t}'
                require(op.node == output, 'partial output label mismatch')
                require(self.context_progress[op.dst] == (None if op.t == 0 else (op.p, op.t)),
                        'partial progress/skipped FMA')
                require(self.a_ready and self.b_partial == op.p, 'A/B supply not ready or B partial mismatch')
            if op.kind == 'add':
                require(0 <= op.rhs < CONTEXTS and op.rhs != op.dst, 'add source alias/range')
                require(self.contexts[op.rhs] == op.right, 'rhs RAW/tag hazard')
            if op.kind == 'spill':
                require(op.slot in (0, 1), 'slot out of range')
                require(not self.slot_committed[op.slot] or self.slot_consumed[op.slot],
                        'overwrite of unread A slot')
                self.slot_committed[op.slot] = False
        self.active, self.micro = op, iter(transactions(op, self.costs))
        self._next()

    def _next(self):
        item = next(self.micro, None)
        if item is None:
            self._commit_command()
            return
        kind, latency, packet, half, size = item
        op = self.active
        tag = Tag(self.epoch, self.tile, self.sequence, kind, op.node or f'p{op.p}', op.dst, packet, half,
                  op.rhs, op.slot, op.p, 64 * op.t + op.p if op.kind == 'fma' else -1)
        self.sequence += 1
        self.pending = Request(tag, latency, size)

    def _commit_command(self):
        op = self.active
        if op.kind == 'load_a':
            self.a_ready = True
        if op.kind == 'fill_b':
            self.b_partial = op.p
        if op.kind in ('fma', 'add', 'zero', 'restore'):
            self.contexts[op.dst] = op.node
            self.context_progress[op.dst] = (op.p, op.t + 1) if op.kind == 'fma' else None
        if op.kind == 'add':
            self.contexts[op.rhs] = None
            self.context_progress[op.rhs] = None
        if op.kind == 'restore':
            self.slot_consumed[op.slot] = True
        if op.kind == 'spill':
            self.slot_consumed[op.slot] = False
            self.slots[op.slot], self.slot_committed[op.slot] = op.node, True
            self.contexts[op.dst] = None
            self.context_progress[op.dst] = None
        if op.kind == 'output':
            self.done = True
        self.stats['commands:' + op.kind] += 1
        self.peak_live_contexts = max(self.peak_live_contexts, sum(x is not None for x in self.contexts))
        if self.record_history:
            self.history.append((self.cycle, op, tuple(self.contexts), tuple(self.slot_committed)))
        self.active = self.micro = None

    def abort(self):
        self.poisoned, self.done = True, False
        self.contexts = [None] * CONTEXTS
        self.context_progress = [None] * CONTEXTS
        self.a_ready, self.b_partial = False, None
        self.slots, self.slot_committed = [None, None], [False, False]
        self.slot_consumed = [False, False]
        self.pending = self.active = self.micro = None
        # In-flight credit is NOT fabricated back. Accepted writes may still
        # land; the owned A lease remains poisoned until the drain completes.

    def reset_epoch(self):
        require(self.poisoned and self.inflight is None, 'reset requires exact outstanding drain')
        self.epoch += 1
        self.poisoned = False

    def accept_response(self, tag):
        require(self.inflight is not None, 'unsolicited/stale response')
        req, due = self.inflight
        if tag != req.tag:
            self.abort()
            raise ProtocolError('response tag/epoch/tile/context/packet mismatch')
        require(self.cycle >= due, 'response before modeled service latency')
        self.stats['acked:' + tag.kind] += 1
        self.stats['acked_bytes:' + tag.kind] += req.bytes
        self.inflight = None
        if not self.poisoned:
            self._next()

    def tick(self, *, request_ready=True, response_ready=True, drop_ack=False):
        """Readiness stalls are externally supplied, with no timeout-as-success."""
        self.cycle += 1
        if self.inflight is not None:
            req, due = self.inflight
            if self.cycle < due:
                self.latency_cycles[req.tag.kind] += 1
            elif response_ready and not drop_ack:
                self.accept_response(req.tag)
            else:
                self.stall_cycles['response:' + req.tag.kind] += 1
            return
        if self.pending is not None:
            if not request_ready:
                self.stall_cycles['request:' + self.pending.tag.kind] += 1
                return
            req, self.pending = self.pending, None
            self.inflight = req, self.cycle + req.latency
            self.service_cycles[req.tag.kind] += req.latency + 1
            self.stats['issued:' + req.tag.kind] += 1
            self.stats['issued_bytes:' + req.tag.kind] += req.bytes


def run(costs=Costs(), ready=None, max_cycles=1_000_000):
    engine = Scheduler(costs)
    for op in program():
        engine.start(op)
        while engine.active is not None:
            require(engine.cycle < max_cycles, 'simulation bound reached; no terminal success')
            kwargs = ready(engine) if ready else {}
            engine.tick(**kwargs)
    require(engine.done and engine.inflight is None and engine.credit == 1,
            'terminal requires final output ACK and drain')
    return engine


def report(costs=Costs()):
    e = run(costs)
    useful = WORDS * 1536
    # Conditional physical-port roofline only. A has distinct 1R/1W ports:
    # reading and writing may overlap; NEVER sum them into a universal floor.
    fma_issue_floor = 1536
    add_issue_floor = 64 if costs.mode == 'wide_candidate' else 64 * PACKETS * (costs.vector16_add_response + 1)
    arithmetic_floor = fma_issue_floor + add_issue_floor if costs.mode == 'wide_candidate' else max(fma_issue_floor, add_issue_floor)
    a_write_floor = 3 * TILE_BYTES // 32
    a_read_floor = 3 * TILE_BYTES // 64
    minimum = max(arithmetic_floor, a_write_floor, a_read_floor)
    cold_b_fill_floor = 1536 * 256 * 2 // 64  # Unique B bytes; existing 64B/cycle fill port.
    cold_minimum = max(minimum, cold_b_fill_floor)
    return dict(status='SOFTWARE_BEHAVIOR_ONLY_CONDITIONAL_INTERFACES', costs=asdict(costs),
        scheduling_policy='serialized DFS; no independent-leaf interleaving or same-edge return/issue',
        modeled_tile_cycles=e.cycle, modeled_tile_mac_ratio=useful / (WORDS * e.cycle),
        modeled_qk_m128_tiles=56, modeled_qk_m128_cycles_serial=56 * e.cycle,
        hardware_cycles=None, hardware_utilization=None, rtl_executed=False,
        peak_live_contexts=e.peak_live_contexts, stats=dict(e.stats), stalls=dict(e.stall_cycles),
        modeled_service_cycles=dict(e.service_cycles),
        conditional_port_floors=dict(arithmetic=arithmetic_floor, a_write=a_write_floor, a_read=a_read_floor),
        conditional_architectural_min_tile_cycles=minimum,
        conditional_architectural_mac_ratio_ceiling=1536 / minimum,
        architectural_bound_excludes='fills, recurrence, return, output, ACK, shared-port conflicts and stalls',
        conditional_cold_b_fill_min_cycles=cold_b_fill_floor,
        conditional_cold_tile_min_cycles=cold_minimum,
        conditional_cold_tile_mac_ratio_ceiling=1536 / cold_minimum,
        cold_bound_basis='786432 unique B bytes / existing 64B-per-cycle B fill; overlap allowed; other costs omitted',
        resources=dict(macs=4096, contexts=5, accumulator_bytes=81920,
            existing_leaf_result_bytes=81920, existing_result_fifo_bytes=32768,
            existing_final_value_bytes=16384, reused_a_slots=2, reused_a_slot_bytes=32768,
            conservative_a_activation_reserve_bytes=393216, a_capacity_bytes=704512,
            a_reserved_bytes=425984, b_capacity_bytes=81920, b_partial_payload_bytes=12288,
            additional_packet_hold_bytes=64, outstanding_requests=1,
            additional_mac_lanes=0, assumed_additional_arithmetic_lanes=0,
            arithmetic_reuse='CONDITIONAL_SAME_FMA_INTERNAL_PATH_NOT_IMPLEMENTED',
            new_wide_fp32_injection_and_two_context_source_mux='UNIMPLEMENTED_UNPRICED',
            new_context_packet_read_write_ports='UNIMPLEMENTED_UNPRICED',
            old_result_fifo_borrowed=False, legacy_path_changed=False))


if __name__ == '__main__':
    print(json.dumps([report(), report(Costs(mode='vector16_baseline'))], indent=2, sort_keys=True))
