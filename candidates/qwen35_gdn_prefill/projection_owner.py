"""GDN BF16 final drain on the existing K-window owner and physical banks.

The complete original Job keeps its BF16 destination extent throughout both
independent FP32 partials. Only the terminal tile drain rounds to BF16. Ordinary
Dense and seeded Down delegate to the frozen inherited owner in place.
This is a software protocol candidate, not RTL or hardware-cycle evidence.
"""
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path

from ..qwen2_resident_matrix.dense_block_reduce import k_window_model as kw
from ..qwen2_resident_matrix.dense_block_reduce.dense_drain import DenseReductionOwner, DenseDrainRequest
from ..qwen2_resident_matrix.dense_block_reduce.public_coordinator import (
    DenseReductionCoordinator, DenseReductionRequest, uint)

down, drain = kw.down, kw.drain
Job, PrefixWorkspace = kw.Job, kw.PrefixWorkspace
Control, Read = kw.Control, kw.Read

# The drain specialization below is an explicit reviewed copy of this frozen
# method. Do not patch/reload its authority or replace any allocated banks.
FROZEN_DRAIN_SHA256 = 'c17be9ad7648b0c5ad1802034b47e686abb62ac08ce79d7489491052e300bdfe'
if hashlib.sha256(Path(drain.__file__).read_bytes()).hexdigest() != FROZEN_DRAIN_SHA256:
    raise ValueError('GDN frozen drain lifecycle drift')


def projection_spans(job):
    return ((job.a, job.a + job.m * job.k * 2),
            (job.b, job.b + job.k * job.n * 2),
            (job.dst, job.dst + job.m * job.n * 2))


def validate_projection(job):
    if type(job) is not Job:
        raise ValueError('complete exact typed GDN Dense Job required')
    job.validate()
    if (any(type(v) is not int for v in
            (job.m, job.n, job.k, job.tag, job.a, job.b, job.dst, job.write_bytes)) or
            any(type(v) is not bool or not v for v in
                (job.activation_bf16, job.weight_bf16, job.output_bf16)) or
            job.materialize_dense_output or not 0 < job.k <= 1536 or
            job.write_bytes != job.m * job.n * 2):
        raise ValueError('GDN BF16 A/W/D full geometry with FP32 partials required')
    spans = projection_spans(job)
    if any(a < d and c < b for i, (a, b) in enumerate(spans) for c, d in spans[i + 1:]):
        raise ValueError('GDN complete A/W/D spans alias')


def validate_window(q):
    validate_projection(q.job)
    if (any(type(v) is not int for v in (q.identity, q.ng, q.cols)) or
            not 0 < q.identity < 1 << 32 or not 0 <= q.ng < 1 << 16 or
            q.ng % 32 or q.cols not in (32, 64, 96, 128, 160) or
            q.ng + q.cols > q.job.n):
        raise ValueError('typed GDN window identity/extent')


@dataclass(frozen=True, kw_only=True)
class GdnKWindowRequest(kw.KWindowRequest):
    def validate(self):
        # The inherited FFN validator requires a public FP32 D. This request
        # explicitly separates full-job BF16 D from the resident FP32 partial.
        validate_window(self)
        if (type(self.slot) is not int or self.slot not in (0, 1) or
                type(self.reuse_a) is not bool or type(self.pair_reverse) is not bool or
                any(type(v) is not int for v in (self.k_begin, self.k_end, self.block_id)) or
                not 0 <= self.k_begin < self.k_end <= self.job.k or
                self.k_begin % 2 or self.k_end % 2 or not 0 < self.block_id < 1 << 32):
            raise ValueError('typed GDN independent FP32 K window')


@dataclass(frozen=True)
class GdnDrainRequest(DenseDrainRequest):
    def validate(self):
        validate_window(self)


@dataclass(frozen=True)
class GdnReductionRequest(DenseReductionRequest):
    def validate(self):
        validate_projection(self.job)
        if (type(self.k_ranges) is not tuple or len(self.k_ranges) != 2 or
                any(type(r) is not tuple or len(r) != 2 or
                    any(not uint(v, 16) for v in r) for r in self.k_ranges) or
                type(self.pair_reverse) is not bool):
            raise ValueError('two explicit immutable GDN K ranges required')
        a, b = self.k_ranges
        if a[0] != 0 or a[1] != b[0] or b[1] != self.job.k:
            raise ValueError('GDN K ranges must cover full original K exactly')
        cols = min(160, self.job.n)
        GdnDrainRequest(self.job, self.identity, 0, cols).validate()
        for slot, (begin, end) in enumerate(self.k_ranges):
            GdnKWindowRequest(self.job, self.identity, 0, cols, slot, bool(slot),
                k_begin=begin, k_end=end, block_id=slot + 1,
                pair_reverse=self.pair_reverse).validate()


class GdnReductionCoordinator(DenseReductionCoordinator):
    def ports(self, *args, **kwargs):
        p = super().ports(*args, **kwargs)
        if p['window_request'] is not None:
            p['window_request'] = GdnKWindowRequest(**vars(p['window_request']))
        if p['drain_request'] is not None:
            p['drain_request'] = GdnDrainRequest(**vars(p['drain_request']))
        return p

    def _drain_exact(self, r, services):
        # Same terminal identity/lease/fence checks; actual packed bytes are 2B.
        try:
            fields = ((r.tag, 32), (r.identity, 32), (r.ng, 16), (r.rows, 8),
                      (r.cols, 8), (r.consumed_beats, 11))
            return (all(uint(v, bits) for v, bits in fields) and
                (r.tag, r.identity, r.ng, r.rows, r.cols) ==
                (self.call.job.tag, self.call.identity, self.ng, self.call.job.m, self.cols) and
                r.committed is True and r.consumed_beats == self.call.job.m // 16 * self.cols and
                r.ddr_write_bytes == self.call.job.m * self.cols * 2 and
                not services.tiles_leased and services.tiles_drained)
        except (AttributeError, TypeError):
            return False


class GdnProjectionOwner(DenseReductionOwner):
    def __init__(self, workspace=None):
        super().__init__(workspace, enable_dense_drain=True, enable_k_window=True,
            enable_ffn_drain=True, enable_ffn_window=True, enable_ffn_tiles=True)

    def _reset(self):
        super()._reset()
        self._ordinary_live = False

    def _receive_result(self, result, terminal_at_edge):
        if not isinstance(self.window_request, GdnKWindowRequest):
            return super()._receive_result(result, terminal_at_edge)
        # Same frozen Down checks and result hold, except BF16 range is checked
        # only after the actual FP32 Add. A large partial may cancel in the sum.
        if self.error:
            return
        if result.error or not result.last or result.context != self.results_received or result.context >= self.contexts:
            self._fault('matrix result order/context/last/error')
            return
        if result.context not in terminal_at_edge:
            self._fault('matrix result before final accepted step')
            return
        if len(result.value) != 16 or any(len(row) != 256 for row in result.value):
            self._fault('matrix result shape')
            return
        if any(not down.finite32(result.value[row][col]) for m in range(self.job.m)
               for n in range(32) for row, col in (down.output_coordinate(m, n),)):
            self._fault('nonfinite result')
            return
        self.final_value = result.value
        self.write_prefix_index = 0
        self.write_context = result.context
        self.write_row = self.write_row_beat = 0
        self.results_received += 1
        self.write_state = 'idle'
        self.adapter_index = 0
        self.adapter_phase = 'drain_operands'

    def _write_command(self):
        if not isinstance(self.drain_request, GdnDrainRequest):
            return super()._write_command()
        if self.error or self.drain_phase != 'write' or self.write_state != 'request':
            return None
        q = self.drain_request
        address = q.job.dst + (self.write_row * q.job.n + q.ng + 32 * self.write_row_beat) * 2
        beats = min(q.cols // 32 - self.write_row_beat, 16 - ((address >> 6) & 15))
        return drain.WriteCommand(address, beats, (q.job.tag << 32) | self.write_sequence)

    def _write_data(self):
        if not isinstance(self.drain_request, GdnDrainRequest):
            return super()._write_data()
        if self.write_state != 'data':
            return None
        first = 32 * (self.write_row_beat + self.write_index)
        words = tuple(down.bf16_rne(v) for v in self.final_value[self.write_row % 16][first:first + 32])
        return drain.WriteBeat(words, self.write_index + 1 == self.accepted_write.beats)

    def _admit_drain(self, q):
        if not isinstance(q, GdnDrainRequest):
            return super()._admit_drain(q)
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
            if not (self.tiles.idle and self._slot_exact() and self.tiles.tags[2].consumed == 0):
                raise ValueError('sealed GDN sum slot identity/shape/count mismatch')
        except ValueError as exc:
            self._fault(str(exc))
        else:
            self.final_value = [[0] * 256 for _ in range(16)]
            self.state, self.drain_phase = 'ffn_drain', 'read'

    def tick(self, **kwargs):
        if self._ordinary_live:
            # The frozen FFN window wrapper excludes ordinary delegation on a
            # local-reset edge. Its window-only drain omits outstanding DDR
            # and seed ACKs. An accepted ordinary/seeded job therefore keeps
            # the ORIGINAL Down lifecycle through its actual terminal.
            ordinary = {name: value for name, value in kwargs.items() if name in (
                'job', 'read_command_ready', 'read_beat', 'group_ready', 'step_ready',
                'result', 'matrix_done', 'write_command_ready', 'write_data_ready',
                'write_ack', 'response_ready', 'local_reset', 'coordinated_reset',
                'seed_begin_ready', 'seed_beat_ready', 'seed_ack')}
            ordinary['local_reset'] = bool(kwargs.get('local_reset') or kwargs.get('abort'))
            if kwargs.get('invalidate_lease') or ordinary['local_reset']:
                self.lease = None
            idle_unexpected = (self.state in ('finish', 'locked') and
                not kwargs.get('coordinated_reset') and any(kwargs.get(name) is not None
                    for name in ('write_ack', 'read_beat', 'result')))
            if idle_unexpected:
                # Preserve the frozen drain wrapper's sideband fence. A held
                # completion remains byte-stable even on the acceptance edge.
                self.drain_poison = True
                self.lease = None
                self.tiles._fault('unexpected idle DDR/Matrix response')
            if kwargs.get('coordinated_reset'):
                self.tiles.tick(coordinated_reset=True)
            elif (self.tiles.poison or self.drain_poison) and not self.error and self.state not in ('finish', 'locked'):
                self._fault(self.tiles.reason or 'ordinary shared tile poison')
            event = down.DenseOwnerModel.tick(self, **ordinary)
            if any(word < 768 for word in event.get('a_writes', {}).values()):
                self.lease = None
            if event.get('response_fire'):
                self._ordinary_live = False
                if self.tiles.poison or self.drain_poison:
                    self.state = 'locked'
            return dict(event, window_fire=False, window_result_fire=False,
                        drain_fire=False, drain_result_fire=False)
        if (isinstance(kwargs.get('drain'), GdnDrainRequest) or
                isinstance(self.drain_request, GdnDrainRequest)):
            return self._bf16_drain_tick(**kwargs)
        ordinary_admit = (kwargs.get('job') is not None and self.ports()['job_ready'] and
            self.window_request is None and self.drain_request is None and
            not any(kwargs.get(name) for name in ('window', 'drain', 'tile_control',
                'tile_write', 'tile_read', 'loan_busy', 'loan_request', 'abort',
                'local_reset', 'coordinated_reset')))
        event = super().tick(**kwargs)
        if ordinary_admit:
            self._ordinary_live = True
        return event

    # Frozen FfnDrainOwnerModel.tick specialization: 32 BF16/beat, 2B
    # final extent, and final BF16-domain check. All ACK/abort/release logic
    # and the sole inherited final_value hold retain their original lifecycle.
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
            e = super().tick(window=window, job=job,
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
                if not self._slot_exact() or self.tiles.tags[2].consumed != self.drain_consumed:
                    self._fault("act read slot metadata/consumption changed")
                else:
                    read = Read(2, q.identity, q.ng, self.write_row // 16 * q.cols + self.drain_column)
            elif phase == "release":
                expected = q.job.m // 16 * q.cols
                if (not self._slot_exact() or self.tiles.tags[2].consumed != expected or
                    self.drain_consumed != expected or self.write_bytes != q.job.m * q.cols * 2):
                    self._fault("act release slot metadata/read/ACK count changed")
                elif self.tiles.idle and self.drain_expected is None and self.write_state == "idle":
                    ctl = Control(2, 2, q.identity, q.ng, q.job.m, q.cols)
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
            matching = expected is not None and (r.slot, r.identity, r.ng, r.index) == (
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
