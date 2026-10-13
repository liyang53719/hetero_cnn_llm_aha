"""Explicit two-slot K2048 profile over the original Dense/Matrix/iDMA owner.

No arithmetic or array is added. Producer requests retain the complete original
BF16 A/W/D Job and full A lease. Actual partials use the new physical layout;
only a sealed destructive sum may enter the original packed BF16 drain, whose
real DDR ACKs still gate public completion. Legacy owner/layout are unchanged.

The drain method specializes the reviewed source at commit1a59e575,
qwen35_gdn_prefill/projection_owner.py SHA71ed7e9bd228ac1cefc50c68c4afae5de7b2fc7111d18be28758f64f66c44b1b:
slot0 + explicit sum phase replace old slot2. All FP32/BF16 checks remain.
"""
from dataclasses import dataclass
from ..qwen35_gdn_prefill import projection_owner as base
from .partial_tiles import TileBankModel, Control, Read, A_WORDS
from .sum_tiles import SumInvocation

Job, down, drain = base.Job, base.down, base.drain
PrefixWorkspace = base.PrefixWorkspace


def validate_projection(job):
    if type(job) is not Job:
        raise ValueError("complete exact typed large-K Dense Job required")
    job.validate()
    if (any(type(v) is not int for v in
            (job.m,job.n,job.k,job.tag,job.a,job.b,job.dst,job.write_bytes)) or
            any(type(v) is not bool or not v for v in
                (job.activation_bf16,job.weight_bf16,job.output_bf16)) or
            job.materialize_dense_output or not 0 < job.k <= 2048 or
            job.write_bytes != job.m * job.n * 2):
        raise ValueError("large-K BF16 A/W/D full geometry with FP32 partials required")
    spans = base.projection_spans(job)
    if any(a < d and c < b for i,(a,b) in enumerate(spans) for c,d in spans[i+1:]):
        raise ValueError("large-K full A/W/D spans alias")


def validate_window(q):
    validate_projection(q.job)
    if (any(type(v) is not int for v in (q.identity,q.ng,q.cols)) or
            not 0 < q.identity < 1<<32 or not 0 <= q.ng < 1<<16 or
            q.ng % 32 or q.cols not in (32,64,96,128,160) or q.ng+q.cols > q.job.n):
        raise ValueError("large-K typed window identity/extent")


@dataclass(frozen=True,kw_only=True)
class LargeKWindowRequest(base.GdnKWindowRequest):
    def validate(self):
        validate_window(self)
        if (type(self.slot) is not int or self.slot not in (0,1) or
                type(self.reuse_a) is not bool or type(self.pair_reverse) is not bool or
                any(type(v) is not int for v in (self.k_begin,self.k_end,self.block_id)) or
                not 0 <= self.k_begin < self.k_end <= self.job.k or
                self.k_begin % 2 or self.k_end % 2 or not 0 < self.block_id < 1<<32):
            raise ValueError("large-K independent complete FP32 partial range")


@dataclass(frozen=True)
class LargeKDrainRequest(base.GdnDrainRequest):
    def validate(self):
        validate_window(self)


@dataclass(frozen=True,kw_only=True)
class LargeKReductionRequest(base.GdnReductionRequest):
    sum_identity: int

    def validate(self):
        validate_projection(self.job)
        if (type(self.k_ranges) is not tuple or len(self.k_ranges)!=2 or
                any(type(r) is not tuple or len(r)!=2 or
                    any(not base.uint(v,16) for v in r) for r in self.k_ranges) or
                type(self.pair_reverse) is not bool or not base.uint(self.sum_identity,32) or
                not self.sum_identity or self.sum_identity==self.identity):
            raise ValueError("explicit ordered ranges and distinct sum identity required")
        a,b=self.k_ranges
        if a[0]!=0 or a[1]!=b[0] or b[1]!=self.job.k:
            raise ValueError("large-K ranges cover full original K exactly")
        cols=min(160,self.job.n)
        LargeKDrainRequest(self.job,self.sum_identity,0,cols).validate()
        for slot,(begin,end) in enumerate(self.k_ranges):
            LargeKWindowRequest(self.job,self.identity,0,cols,slot,bool(slot),
                k_begin=begin,k_end=end,block_id=slot+1,pair_reverse=self.pair_reverse).validate()


class LargeKReductionCoordinator(base.GdnReductionCoordinator):
    def ports(self,*args,**kwargs):
        p=super().ports(*args,**kwargs)
        if p['window_request'] is not None:
            p['window_request']=LargeKWindowRequest(**vars(p['window_request']))
        if p['drain_request'] is not None:
            q=p['drain_request']
            p['drain_request']=LargeKDrainRequest(q.job,self.call.sum_identity,q.ng,q.cols)
        if p['sum_request'] is not None:
            q=p['sum_request']
            p['sum_request']=SumInvocation(self.call.sum_identity,self.call.identity,q.ng,q.rows,q.cols)
        return p

    def _drain_exact(self,r,services):
        try:
            fields=((r.tag,32),(r.identity,32),(r.ng,16),(r.rows,8),(r.cols,8),(r.consumed_beats,11))
            return (all(base.uint(v,bits) for v,bits in fields) and
                (r.tag,r.identity,r.ng,r.rows,r.cols)==
                (self.call.job.tag,self.call.sum_identity,self.ng,self.call.job.m,self.cols) and
                r.committed is True and r.consumed_beats==self.call.job.m//16*self.cols and
                r.ddr_write_bytes==self.call.job.m*self.cols*2 and
                not services.tiles_leased and services.tiles_drained)
        except (AttributeError,TypeError):
            return False


class LargeKProjectionOwner(base.GdnProjectionOwner):
    def __init__(self,workspace=None):
        super().__init__(workspace)
        # Control wrapper selected only at construction; the allocated SRAM
        # object is never replaced, and this owner remains fixed to this layout.
        self.tiles=TileBankModel(self.a_banks)

    def _finish_window(self):
        # Malformed slot2 must retire as an error, not index an absent third
        # tag. Preserve the original K-window result fields and MAC counters.
        q = self.window_request
        tag = self.tiles.tags[q.slot] if type(q.slot) is int and 0 <= q.slot < 2 else None
        produced = (tag.produced if self.window_begun and tag is not None and
                    tag.identity == q.identity and tag.ng == q.ng else 0)
        self.window_result = base.kw.KWindowResult(q.job.tag, q.identity, q.ng,
            q.slot, q.job.m, q.cols, self.error, self.error is None, produced,
            k_begin=q.k_begin, k_end=q.k_end, block_id=q.block_id,
            pair_reverse=q.pair_reverse,
            useful_macs=(self.accepted_steps*q.job.m*32 if self.accepted_steps else 0),
            executed_macs=self.accepted_steps*4096)
        self.state = 'finish'

    def tick(self,**kwargs):
        if kwargs.get('window') is not None and type(kwargs['window']) is not LargeKWindowRequest:
            raise ValueError("selected large-K owner requires matching internal window type")
        if kwargs.get('drain') is not None and type(kwargs['drain']) is not LargeKDrainRequest:
            raise ValueError("selected large-K owner requires matching internal sum drain type")
        reset_rejected = bool(kwargs.get('coordinated_reset') and not self.tiles.idle)
        if reset_rejected:
            # Keep the accepted bank obligation and owner's transaction state
            # alive. A later coordinated reset is legal only after drain.
            kwargs = dict(kwargs, coordinated_reset=False, abort=True)
        e=super().tick(**kwargs)
        if any(word < A_WORDS for word in e.get('a_writes',{}).values()):
            self.lease=None
        if reset_rejected:
            e.update(coordinated_reset=False, reset_rejected=True)
        return e

    def _slot_exact(self,*,released=False):
        q,t=self.drain_request,self.tiles.tags[0]
        expected=q.job.m//16*q.cols
        same=(t.identity,t.ng,t.rows,t.cols)==(q.identity,q.ng,q.job.m,q.cols)
        if released:
            return same and t.phase=='sum' and not t.live and not t.sealed and t.consumed==expected
        return (same and t.phase=='sum' and not t.poisoned and t.live and t.sealed and
                t.expected==expected and t.produced==expected and not t.matrix_producer_order)

    def _admit_drain(self, q):
        if not isinstance(q, LargeKDrainRequest):
            raise ValueError("explicit large-K sum drain required")
        self.drain_request, self.job = q, q.job
        self.drain_result = None
        self.drain_started = self.clock
        self.drain_consumed = self.drain_column = self.write_row = self.write_row_beat = 0
        self.write_bytes = 0
        self.drain_expected = self.accepted_write = None
        self.error = None
        self.write_state = 'idle'
        self.group_started = self.group_done = False
        self.final_value = None
        try:
            q.validate()
            if self.workspace is None:
                raise ValueError('explicit bounded prefix workspace required')
            self.workspace.validate(q.job)
            if not (self.tiles.idle and self._slot_exact() and self.tiles.tags[0].consumed == 0):
                raise ValueError('sealed GDN sum slot identity/shape/count mismatch')
        except ValueError as exc:
            self._fault(str(exc))
        else:
            self.final_value = [[0] * 256 for _ in range(16)]
            self.state, self.drain_phase = 'ffn_drain', 'read'

    def _bf16_drain_tick(self, *, drain=None, drain_result_ready=True, window=None, job=None,
             write_command_ready=True, write_data_ready=True, write_ack=None,
             abort=False, local_reset=False, coordinated_reset=False,
             tile_control=None, tile_write=None, tile_read=None,
             tile_response_ready=True, tile_accept_ready=True,
             invalidate_lease=False, loan_busy=False, loan_request=False, **kwargs):
        p = self.ports()
        external_tile = self.enable_ffn_tiles and any(x is not None for x in (tile_control, tile_write, tile_read))
        idle_unexpected = (self.enable_ffn_drain and self.drain_request is None and
            self.window_request is None and self.state in ("idle", "locked", "finish") and
            any(x is not None for x in (write_ack, kwargs.get("read_beat"), kwargs.get("result"))) and
            not coordinated_reset)
        blocked = (external_tile or window is not None or loan_busy or loan_request or
                   abort or local_reset or coordinated_reset or idle_unexpected)
        if blocked:
            p["drain_ready"] = False
        admit = drain is not None and p["drain_ready"]
        # A held future drain cannot interrupt an ordinary/window transaction.
        # New work: external tile > window > drain > ordinary, after loan guards.
        if self.drain_request is None and not admit:
            if idle_unexpected:
                # Sticky poison must not rewrite an already offered ordinary
                # completion payload. It only bars another launch and locks.
                self.drain_poison = True
                self.lease = None
                self.tiles._fault("unexpected idle DDR/Matrix response")
                if self.state == "idle":
                    self.state = "locked"
            e = base.DenseReductionOwner.tick(self, window=window, job=job,
                write_command_ready=write_command_ready, write_data_ready=write_data_ready,
                write_ack=write_ack, abort=abort, local_reset=local_reset,
                coordinated_reset=coordinated_reset, tile_control=tile_control,
                tile_write=tile_write, tile_read=tile_read,
                tile_response_ready=tile_response_ready, tile_accept_ready=tile_accept_ready,
                invalidate_lease=invalidate_lease, loan_busy=loan_busy, loan_request=loan_request, **kwargs)
            if self.drain_poison and (e.get("response_fire") or e.get("window_result_fire")):
                self.state = "locked"
            return dict(e, drain_ready=p["drain_ready"], drain_fire=False, drain_result_fire=False)

        self.clock += 1
        self.b_banks.begin_cycle()
        p.update(drain_fire=False, drain_result_fire=False, window_fire=False,
                 window_result_fire=False, read_fire=False, read_command_fire=False,
                 group_fire=False, step_fire=False, result_fire=False,
                 matrix_done_fire=False, response_fire=False, write_command_fire=False,
                 write_data_fire=False, write_ack_fire=False, release_fire=False,
                 release_verified=False, a_reads={}, a_writes={}, b_reads={}, b_writes={})
        if coordinated_reset:
            self.tiles.tick(coordinated_reset=True)
            self._reset()
            return dict(p, coordinated_reset=True)
        if invalidate_lease:
            self.lease = None
        phase = self.drain_phase
        if abort or local_reset:
            self._fault("abort" if abort else "local reset requires coordinated backend reset")
        if self.tiles.poison and not self.error:
            self._fault(self.tiles.reason or "tile bank poison")
        if write_ack is not None and self.write_state not in ("data", "ack"):
            self._fault("unexpected late write ACK")
        if self.drain_request is not None and (kwargs.get("result") is not None or kwargs.get("read_beat") is not None):
            self._fault("unexpected Matrix result or DMA read response during act drain")
        if self.tiles.response is not None and self.drain_expected is None:
            self._fault("unexpected act tile response without accepted read")
        if admit:
            p["drain_fire"] = True
            p["window_ready"] = p["job_ready"] = False
            self._admit_drain(drain)

        ctl = read = None
        if not self.error and not admit:
            q = self.drain_request
            if phase == "read":
                if not self._slot_exact() or self.tiles.tags[0].consumed != self.drain_consumed:
                    self._fault("act read slot metadata/consumption changed")
                else:
                    read = Read(0, q.identity, q.ng, self.write_row // 16 * q.cols + self.drain_column, phase="sum")
            elif phase == "release":
                expected = q.job.m // 16 * q.cols
                if (not self._slot_exact() or self.tiles.tags[0].consumed != expected or
                    self.drain_consumed != expected or self.write_bytes != q.job.m * q.cols * 2):
                    self._fault("act release slot metadata/read/ACK count changed")
                elif self.tiles.idle and self.drain_expected is None and self.write_state == "idle":
                    ctl = Control(2, 0, q.identity, q.ng, q.job.m, q.cols, phase="sum")
        te = self.tiles.tick(control=ctl if tile_accept_ready else None,
            read=read if tile_accept_ready else None, abort=abort or local_reset,
            response_ready=self.drain_expected is not None and tile_response_ready,
            owner_quiescent=bool(ctl or read) and tile_accept_ready)
        p["tile"] = te
        if te["read_fire"]:
            self.drain_expected = read
            self.drain_phase = "response"
        if te["response_fire"]:
            r, expected = te["response"], self.drain_expected
            self.drain_expected = None
            matching = expected is not None and getattr(r, "phase", None) == "sum" and (r.slot, r.identity, r.ng, r.index) == (
                expected.slot, expected.identity, expected.ng, expected.index)
            if matching:
                self.drain_consumed += 1
            if not matching or r.error:
                self._fault("act tile response identity/error")
            elif not self.error:
                if any(not down.finite32(word) or (word & 0x7fffffff) >= 0x7f7f8000 for word in r.words):
                    self._fault("sum outside finite BF16 output domain")
                else:
                    for lane, word in enumerate(r.words):
                        self.final_value[lane][self.drain_column] = word
                    self.drain_column += 1
                    if self.drain_column == self.drain_request.cols:
                        self.drain_phase, self.write_state = "write", "request"
                    else:
                        self.drain_phase = "read"
        if te["ctl_fire"]:
            p["release_fire"] = True
            self.drain_phase = "verify"
        if self.tiles.poison and not self.error:
            self._fault(self.tiles.reason or "tile bank poison")

        if p["write_command"] is not None and write_command_ready and not self.error:
            self.accepted_write = p["write_command"]
            self.write_index, self.write_state = 0, "data"
            p["write_command_fire"] = True
        if p["write_data"] is not None and write_data_ready:
            self.write_index += 1
            p["write_data_fire"] = True
            if self.write_index == self.accepted_write.beats:
                self.write_state = "ack"
        if write_ack is not None and p["write_ack_ready"]:
            p["write_ack_fire"] = True
            accepted = self.accepted_write
            nbytes = accepted.beats * 64
            self.write_state = "idle"
            if write_ack.error or write_ack.tag != accepted.tag or write_ack.nbytes not in (None, nbytes):
                self._fault("write ACK tag/error/bytes")
            else:
                self.write_bytes += nbytes
                self.write_sequence += 1
                if not self.error:
                    self.write_row_beat += accepted.beats
                    if self.write_row_beat == self.drain_request.cols // 32:
                        self.write_row_beat = 0
                        self.write_row += 1
                    if self.write_row == self.job.m:
                        if (self.write_bytes != self.job.m * self.drain_request.cols * 2 or
                            self.drain_consumed != self.job.m // 16 * self.drain_request.cols):
                            self._fault("exact act read and real ACK byte count")
                        else:
                            self.drain_phase = "release"
                    elif self.write_row % 16 == 0 and self.write_row_beat == 0:
                        self.drain_column, self.drain_phase = 0, "read"
                    else:
                        self.write_state = "request"
            self.accepted_write = None
        if phase == "verify" and not self.error:
            q = self.drain_request
            if (not self._slot_exact(released=True) or not self.tiles.idle or
                self.drain_expected is not None or self.write_state != "idle" or
                self.drain_consumed != q.job.m // 16 * q.cols or self.write_bytes != q.job.m * q.cols * 2):
                self._fault("act release not observed drained")
            else:
                p["release_verified"] = True
                self.final_value = None
                self._finish_drain()
        if self.error and self.drain_phase != "held" and self.tiles.idle and self.drain_expected is None and self.write_state == "idle":
            self.final_value = None
            self._finish_drain()
        if p["drain_result"] is not None and drain_result_ready:
            p["drain_result_fire"] = True
            self.responses += 1
            self.state = "locked" if self.error else "idle"
            if not self.error:
                self.drain_request = self.drain_result = None
                self.drain_phase = "idle"
        p["a_reads"], p["a_writes"] = dict(self.a_banks.reads), dict(self.a_banks.writes)
        return p
