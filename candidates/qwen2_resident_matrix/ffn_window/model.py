"""Same-bank FFN Dense window port/control candidate, not an arithmetic oracle.

The frozen Down owner supplies actual DDR ingress, A RMW, B double buffering,
and accepted Matrix packets. The frozen tile model supplies actual synchronous
read/modify/write traffic in those very same A banks. This module adds only
window admission, a real-load A lease, and an ordered Matrix-result adapter.
There is one 16 KiB ``final_value`` and no second retained-A or result array.
Results are external inputs: opaque test values prove transport, not numerics.

``tick`` returns pre-edge ports and that edge's transfers. It is an event/port
specification, not a cycle-equivalence claim: the inherited tile model applies
accepted controls immediately, while generated RTL validates the stored tag
in its next controller phase. Invalid controls poison before SRAM access.
As in the pinned
owner, DMA/Matrix are controlled physical backends; their accepted obligations
must eventually respond. A local abort cannot manufacture that response or
claim a coordinated reset. No RTL/Scala simulation is represented here.
"""
from dataclasses import dataclass
import hashlib
import importlib.util
from pathlib import Path
import sys


def _pinned_module(name, path, digest):
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("frozen physical model drift: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parent.parent
tiles = _pinned_module("ffn_window_frozen_tiles", ROOT / "ffn_tiles/model.py",
                       "f7bb9b370a240baae98cf16490a7d86301c7ac8dffea96a5adb5e3bed34ce7ed")
# ffn_tiles verifies and imports this exact Down model itself.
down = tiles.down
Job = down.Job
ReadCommand, ReadBeat = down.ReadCommand, down.ReadBeat
Step, MatrixResult, MatrixDone = down.Step, down.MatrixResult, down.MatrixDone
PrefixWorkspace = down.PrefixWorkspace
Read, Write, Response = tiles.Read, tiles.Write, tiles.Response


@dataclass(frozen=True)
class Control(tiles.Control):
    matrix_producer_order: bool = False


@dataclass
class Tag(tiles.Tag):
    matrix_producer_order: bool = False


def producer_index(produced, rows, cols):
    """Context-major Matrix retirement -> unchanged row-group-major tile key."""
    if rows not in (16, 128) or cols not in (32, 64, 96, 128, 160):
        raise ValueError("Matrix tile geometry")
    groups = rows // 16
    if type(produced) is not int or not 0 <= produced < groups * cols:
        raise ValueError("Matrix producer count")
    context, within = divmod(produced, 32 * groups)
    group, column = divmod(within, 32)
    return group * cols + context * 32 + column


class TileBankModel(tiles.TileBankModel):
    """New adapter variant; the old default and sealed consumer order survive."""
    def _control(self, q):
        mode = getattr(q, "matrix_producer_order", False)
        if type(mode) is not bool or (q.op == 0 and mode and q.slot not in (0, 1)):
            self._fault("Matrix producer order only for Gate/Up")
            return
        # Producer mode is captured at begin only. Existing SiLU consumers
        # seal/release through the unchanged, default-false control API.
        super()._control(q)
        if q.op == 0 and not self.poison:
            self.tags[q.slot] = Tag(**vars(self.tags[q.slot]), matrix_producer_order=mode)

    def _beat_valid(self, q, writing):
        if not writing or not self._key_valid(q):
            return super()._beat_valid(q, writing)
        tag = self.tags[q.slot]
        if not getattr(tag, "matrix_producer_order", False):
            return super()._beat_valid(q, writing)
        return (type(q.index) is int and tag.live and not tag.sealed and
                tag.identity == q.identity and tag.ng == q.ng and
                tag.produced < tag.expected and
                q.index == producer_index(tag.produced, tag.rows, tag.cols))


@dataclass(frozen=True)
class FfnWindowRequest:
    job: Job
    identity: int
    ng: int
    cols: int
    slot: int
    reuse_a: bool = False

    def validate(self):
        j = self.job
        # Keep full original N and complete physical spans. The selected width
        # must never replace N in B DDR strides or input/output alias checks.
        j.validate()
        if any(type(x) is not bool for x in
               (j.activation_bf16, j.weight_bf16, j.output_bf16, self.reuse_a)):
            raise ValueError("typed dtype/reuse flags")
        if any(type(x) is not int for x in (j.m, j.k, j.n, j.tag, j.a, j.b, j.dst)):
            raise ValueError("typed original Job integers")
        if j.k > 1536 or j.output_bf16:
            raise ValueError("FFN window K<=1536 and FP32 output required")
        if type(self.identity) is not int or not 0 < self.identity < 2**32:
            raise ValueError("nonzero UInt32 window identity")
        if type(self.ng) is not int or not 0 <= self.ng < 2**16 or self.ng % 32:
            raise ValueError("aligned UInt16 ng")
        if type(self.cols) is not int or self.cols not in (32, 64, 96, 128, 160):
            raise ValueError("window width")
        if type(self.slot) is not int or self.slot not in (0, 1):
            raise ValueError("Gate/Up slot")
        if self.ng + self.cols > j.n:  # deliberately widened, no UInt16 wrap
            raise ValueError("window exceeds original N")


@dataclass(frozen=True)
class FfnWindowResult:
    tag: int
    identity: int
    ng: int
    slot: int
    rows: int
    cols: int
    status: str | None
    committed: bool
    produced_beats: int
    ddr_write_bytes: int = 0


@dataclass(frozen=True)
class ALease:
    base: int
    activation_bf16: bool
    rows: int
    k: int
    row_stride: int
    identity: int

    @classmethod
    def for_request(cls, q):
        j = q.job
        return cls(j.a, j.activation_bf16, j.m, j.k,
                   j.k * (2 if j.activation_bf16 else 4), q.identity)


class FfnWindowOwnerModel(down.DenseOwnerModel):
    """Default-off window extension of the frozen ordinary Down owner.

    Jobs retain the original explicit PrefixWorkspace admission API. A window
    does not access that workspace and never emits Host completion or DDR
    output traffic. External tile operations use ``tile_*`` tick inputs and are
    granted only while the owner is idle; all accesses share the same banks.
    """
    def __init__(self, workspace=None, *, enable_ffn_window=False, enable_ffn_tiles=False):
        if enable_ffn_window and not enable_ffn_tiles:
            raise ValueError("FFN windows require FFN tiles")
        self.enable_ffn_window = enable_ffn_window
        self.enable_ffn_tiles = enable_ffn_tiles
        super().__init__(workspace)
        self.tiles = TileBankModel(self.a_banks)

    def _reset(self):
        super()._reset()
        self.window_request = None
        self.lease = None
        self.window_result = None
        self.adapter_index = 0
        self.adapter_phase = "idle"
        self.traffic = dict(a_read_bytes=0, b_read_bytes=0, windows=0)
        self.loaded_a_bytes = 0
        self.a_fences = 0
        self.window_begun = False
        self.results_received = self.group_accepted_steps = 0

    @property
    def chunk_start(self):
        return 0 if self.window_request is not None else super().chunk_start

    @property
    def chunk_end(self):
        return self.job.k if self.window_request is not None else super().chunk_end

    @property
    def saving_prefix(self):
        return False if self.window_request is not None else super().saving_prefix

    def _fault(self, reason):
        self.lease = None
        super()._fault(reason)
        if self.window_request is not None:
            self.final_value = None
            self.adapter_phase = "idle"
            self.tiles._fault(reason)

    def _window(self):
        if self.window_request is None:
            return super()._window()
        # Called by the actual inherited A RMW ingress after its final commit.
        # No lease is minted on command acceptance or last DDR beat acceptance.
        self.state = "a_fence"

    def _begin_execute(self):
        self.n_base = self.window_request.ng
        self.contexts = self.window_request.cols // 32
        self.group_started = self.group_done = False
        self.group_accepted_steps = self.results_received = self.written = 0
        self.terminal_issued = set()
        self.issue_k = self.load_k = 0
        self.issue_context = self.load_depth = self.load_beat = 0
        self.ready[:] = [False, False]
        self.ready_k[:] = [None, None]
        self.pending = None
        self.fifo.clear()
        self.state = "execute"

    def _tile_control(self, op):
        q = self.window_request
        return Control(op, q.slot, q.identity, q.ng, q.job.m, q.cols, True)

    def _tile_write(self):
        q = self.window_request
        group, column = divmod(self.adapter_index, 32)
        words = tuple(self.final_value[column % 16][128*(column // 16) + 16*group + lane]
                      for lane in range(16))
        return Write(q.slot, q.identity, q.ng,
                     group*q.cols + 32*self.write_context + column, words)

    def _receive_result(self, result, terminal_at_edge):
        if self.window_request is None:
            return super()._receive_result(result, terminal_at_edge)
        # Same finite/order/terminal checks and the very same final_value as
        # ordinary Dense. Its DDR writer request is replaced by tile RMW.
        super()._receive_result(result, terminal_at_edge)
        if not self.error:
            self.write_state = "idle"
            self.adapter_index = 0
            self.adapter_phase = "drain_operands"

    def _write_command(self):
        return None if self.window_request is not None else super()._write_command()

    def _write_data(self):
        return None if self.window_request is not None else super()._write_data()

    def ports(self):
        p = super().ports()
        window_mode = self.window_request is not None
        ready = (self.state == "idle" and self.tiles.idle and not self.tiles.poison)
        p.update(window_ready=ready and self.enable_ffn_window,
                 window_result=self.window_result if self.state == "finish" and window_mode else None,
                 busy=self.state not in ("idle", "locked"), lease_valid=self.lease is not None)
        p["job_ready"] = ready
        p["reset_required"] = p["reset_required"] or self.tiles.poison
        if window_mode:
            p["response"] = None
            p["result_ready"] = (self.state in ("execute", "drain") and self.group_started and
                                 (bool(self.error) or self.final_value is None))
            p["write_ack_ready"] = False
        return p

    def _finish_window(self):
        q = self.window_request
        tag = self.tiles.tags[q.slot] if type(q.slot) is int and 0 <= q.slot < 3 else None
        produced = (tag.produced if self.window_begun and tag is not None and
                    tag.identity == q.identity and tag.ng == q.ng else 0)
        self.window_result = FfnWindowResult(q.job.tag, q.identity, q.ng, q.slot,
                                            q.job.m, q.cols, self.error,
                                            self.error is None, produced)
        self.state = "finish"

    def tick(self, *, window=None, job=None, read_command_ready=True, read_beat=None,
             group_ready=True, step_ready=True, result=None, matrix_done=None,
             window_result_ready=True, response_ready=True, abort=False,
             local_reset=False, coordinated_reset=False, tile_control=None,
             tile_write=None, tile_read=None, tile_response_ready=True,
             tile_accept_ready=True, dense_reads=None, dense_writes=None,
             invalidate_lease=False, loan_busy=False, loan_request=False, **ordinary):
        p = self.ports()
        tile_offered = self.enable_ffn_tiles and any(x is not None for x in
                                                    (tile_control, tile_write, tile_read))
        # Match source combinational admission: external tiles, then window,
        # then ordinary jobs. Existing accepted traffic always drains.
        if tile_offered or loan_busy or loan_request or abort or local_reset:
            p["window_ready"] = p["job_ready"] = False
        elif window is not None:
            p["job_ready"] = False
        if invalidate_lease:
            self.lease = None
        # The ordinary owner remains executable, rather than being represented
        # by a synthetic receipt. Its physical A writes invalidate the lease.
        if self.window_request is None and (self.state != "idle" or window is None or tile_offered) and not (abort or local_reset or coordinated_reset):
            if job is not None and p["job_ready"]:
                self.lease = None
            # Ordinary work and external tiles cannot own one bank edge.
            if self.state != "idle" or (job is not None and p["job_ready"]):
                if job is not None and p["job_ready"] and self.tiles.leased and (job.kind != "Dense" or job.k > 1536):
                    self.job = job
                    self.write_bytes = self.prefix_bytes = self.accepted_steps = self.rmw_commits = 0
                    self.group_started = self.group_done = False
                    self.group_accepted_steps = self.results_received = self.written = 0
                    self._fault("ordinary job intersects live tile allocation")
                    return self.tick(response_ready=response_ready, **ordinary)
                e = super().tick(job=job if p["job_ready"] else None, read_command_ready=read_command_ready,
                                 read_beat=read_beat, group_ready=group_ready, step_ready=step_ready,
                                 result=result, matrix_done=matrix_done, response_ready=response_ready,
                                 **ordinary)
                if any(word < 768 for word in e.get("a_writes", {}).values()):
                    self.lease = None
                return dict(e, window_result_fire=False, window_fire=False)
            e = self.tiles.tick(control=tile_control if self.enable_ffn_tiles else None,
                                write=tile_write if self.enable_ffn_tiles else None,
                                read=tile_read if self.enable_ffn_tiles else None,
                                response_ready=tile_response_ready,
                                owner_quiescent=not (dense_reads or dense_writes),
                                dense_reads=dense_reads, dense_writes=dense_writes)
            if self.tiles.poison or any(word < 768 for word in e["writes"].values()):
                self.lease = None
            self.clock += 1
            return dict(p, tile=e, window_result_fire=False, window_fire=False,
                        a_reads=e["reads"], a_writes=e["writes"], b_reads={}, b_writes={},
                        read_fire=False, read_command_fire=False, step_fire=False,
                        group_fire=False, result_fire=False, response_fire=False)

        self.clock += 1
        self.b_banks.begin_cycle()
        if coordinated_reset:
            self.tiles.tick(coordinated_reset=True)
            self._reset()
            return dict(p, coordinated_reset=True, window_fire=False, window_result_fire=False)
        # Local reset/abort invalidates immediately, but accepted DMA, Matrix,
        # synchronous operand responses and tile RMW/response obligations drain.
        if abort or local_reset:
            self._fault("abort" if abort else "local reset requires coordinated backend reset")
        if self.tiles.poison and not self.error:
            self._fault(self.tiles.reason or "tile bank poison")
        error_at_edge = self.error is not None
        old_pending = self.pending
        terminal_at_edge = set(getattr(self, "terminal_issued", ()))
        state_at_edge = self.state
        reserved = len(self.fifo) + int(old_pending is not None)
        self.max_reserved = max(self.max_reserved, reserved)
        assert reserved <= self.FIFO_DEPTH
        done_ok = (self.group_started and self.issue_k == self.chunk_end and
                   self.group_accepted_steps == self.job.k*self.contexts and
                   self.results_received == self.contexts and old_pending is None and not self.fifo
                   if self.window_request is not None and self.group_started else False)

        internal_control = internal_write = None
        if not self.error and self.window_request is not None:
            if self.state == "tile_begin":
                internal_control = self._tile_control(0)
            elif self.state == "seal":
                internal_control = self._tile_control(1)
            elif (self.state == "execute" and self.final_value is not None and
                  self.adapter_phase in ("drain_operands", "write") and
                  old_pending is None):
                internal_write = self._tile_write()
        internal_access = internal_control is not None or internal_write is not None
        external_access = self.state == "idle" and window is None and job is None
        te = self.tiles.tick(control=internal_control if tile_accept_ready else None,
                             write=internal_write if tile_accept_ready else None,
                             read=None, response_ready=tile_response_ready,
                             abort=abort or local_reset,
                             owner_quiescent=internal_access and tile_accept_ready)
        if external_access:
            # This branch is only relevant to an abort/reset recovery edge;
            # regular idle tile traffic uses the ordinary branch above.
            assert not (tile_control or tile_write or tile_read)
        p.update(tile=te, window_fire=False, window_result_fire=False,
                 read_fire=False, read_command_fire=False, group_fire=False,
                 step_fire=False, operand_read=False, operand_response=False,
                 result_fire=False, matrix_done_fire=False, response_fire=False,
                 write_command_fire=False, write_data_fire=False, write_ack_fire=False,
                 a_fence=False)

        if p["window_result"] is not None and window_result_ready:
            p["window_result_fire"] = True
            self.responses += 1
            self.state = "locked" if self.error else "idle"
            if not self.error:
                self.window_request = None
                self.window_result = None
        if window is not None and p["window_ready"] and not (abort or local_reset):
            p["window_fire"] = True
            self.window_request, self.job = window, window.job
            self.window_result = None
            self.window_begun = False
            self.error = None
            self.group_started = self.group_done = False
            self.restoring = self.prefix_valid = False
            self.seed_state = "idle"
            self.seed_outstanding = False
            self.final_value = None
            self.write_state = "idle"
            self.rmw_commits = self.accepted_steps = self.write_bytes = self.loaded_a_bytes = 0
            self.results_received = self.group_accepted_steps = self.written = 0
            self.adapter_phase = "idle"
            try:
                window.validate()
                if self.workspace is None:
                    raise ValueError("explicit Down prefix workspace required")
                self.workspace.validate(window.job)
                if self.tiles.tags[window.slot].live:
                    raise ValueError("target tile slot already live")
                if window.reuse_a and self.lease != ALease.for_request(window):
                    raise ValueError("A lease metadata mismatch or invalid lease")
            except ValueError as exc:
                self._fault(str(exc))
            else:
                if not window.reuse_a:
                    self.lease = None
                self.state = "tile_begin"
                self.traffic["windows"] += 1
                self.a_row = self.a_beat = self.clear_word = 0

        if te["ctl_fire"] and not self.error:
            if self.tiles.poison:
                self._fault(self.tiles.reason)
            elif state_at_edge == "tile_begin":
                self.window_begun = True
                if self.window_request.reuse_a:
                    self._begin_execute()
                else:
                    self.state = "clear"
            elif state_at_edge == "seal":
                self.state = "check_seal"
        if te["write_fire"] and not self.error:
            if self.tiles.poison:
                self._fault(self.tiles.reason)
            else:
                self.adapter_phase = "commit"
        if te["rmw_commit"] and not self.error:
            self.adapter_index += 1
            if self.adapter_index == self.job.m//16*32:
                self.written += 1
                self.final_value = None
                self.adapter_phase = "idle"
            else:
                self.adapter_phase = "write"

        if self.state == "clear":
            for bank in range(16):
                self.a_banks.write(bank, self.clear_word, 0)
            self.lease = None
            self.clear_word += 1
            if self.clear_word == self.job.k//16*8:
                self.state = "a_load"
        if state_at_edge == "a_fence" and not self.error:
            assert not (self.read_active or self.a_hold or self.a_rmw_pending)
            expected_bytes = self.job.m*self.job.k*(2 if self.job.activation_bf16 else 4)
            if self.rmw_commits != self.job.m*self.job.k or self.loaded_a_bytes != expected_bytes:
                self._fault("A fence without exact actual DDR/RMW production")
            else:
                if not invalidate_lease:
                    self.lease = ALease.for_request(self.window_request)
                self.a_fences += 1
                p["a_fence"] = True
                self._begin_execute()
        if p["read_command"] is not None and read_command_ready and not self.error:
            self.read_active = (p["read_command"], 0)
            p["read_command_fire"] = True
        self._a_cycle()
        if read_beat is not None and p["read_ready"]:
            p["read_fire"] = True
            command = self.read_active[0]
            self._receive_read(read_beat)
            self.traffic[command.kind + "_read_bytes"] += 64
            if command.kind == "a" and not self.error:
                self.loaded_a_bytes += 64
        if p["group"] is not None and group_ready and not self.error:
            self.group_started = True
            p["group_fire"] = True

        can_issue = (not self.error and self.state == "execute" and self.group_started and
                     not self.group_done and self.final_value is None and not internal_access and
                     self.tiles.idle and self.issue_k < self.job.k and reserved < self.FIFO_DEPTH and
                     self.ready[(self.issue_k//128)&1] and
                     self.ready_k[(self.issue_k//128)&1] == self.issue_k//128*128)
        if p["step"] is not None and step_ready and not self.error:
            p["step_fire"] = True
            self.fifo.popleft()
            self.accepted_steps += 1
            self.group_accepted_steps += 1
            if p["step"].last:
                self.terminal_issued.add(p["step"].context)
        elif self.error and self.fifo:
            self.fifo.popleft()
        self.pending = None
        if old_pending is not None and not error_at_edge:
            assert len(self.fifo) < self.FIFO_DEPTH
            self.fifo.append(self._operand_response(old_pending))
            p["operand_response"] = True
        if can_issue:
            self._issue_read()
            p["operand_read"] = True
        if result is not None and p["result_ready"]:
            p["result_fire"] = True
            self._receive_result(result, terminal_at_edge)
        if matrix_done is not None and p["matrix_done_ready"]:
            p["matrix_done_fire"] = True
            self.group_done = True
            if matrix_done.tag != self.job.tag:
                self._fault("matrix done tag")
            elif matrix_done.error:
                self._fault("matrix done error")
            elif not self.error and not done_ok:
                self._fault("matrix done before all accepted steps/results")
        if self.tiles.poison and not self.error:
            self._fault(self.tiles.reason or "tile bank poison")
        if any(word < 768 for word in self.a_banks.writes.values()):
            self.lease = None
        if self.error and self.state == "drain":
            if not (self.read_active or self.a_hold or self.a_rmw_pending or self.pending or self.fifo) and self.tiles.idle and (not self.group_started or self.group_done):
                if self.window_request is not None:
                    self._finish_window()
                else:
                    self.state = "finish"
        elif self.state == "execute" and self.group_done and self.written == self.contexts:
            assert self.final_value is None and self.tiles.idle
            assert not (self.read_active or self.a_hold or self.a_rmw_pending or self.pending or self.fifo)
            self.state = "seal"
        elif state_at_edge == "check_seal" and not self.error:
            q, t = self.window_request, self.tiles.tags[self.window_request.slot]
            if (not self.tiles.idle or not t.live or not t.sealed or
                (t.identity, t.ng, t.rows, t.cols, t.produced, t.consumed,
                 getattr(t, "matrix_producer_order", False)) !=
                (q.identity, q.ng, q.job.m, q.cols, q.job.m//16*q.cols, 0, True)):
                self._fault("sealed tile state mismatch")
            else:
                self._finish_window()
        p["a_reads"], p["a_writes"] = dict(self.a_banks.reads), dict(self.a_banks.writes)
        p["b_reads"], p["b_writes"] = dict(self.b_banks.reads), dict(self.b_banks.writes)
        p["reserved_after"] = len(self.fifo) + int(self.pending is not None)
        assert p["reserved_after"] <= self.FIFO_DEPTH
        return p
