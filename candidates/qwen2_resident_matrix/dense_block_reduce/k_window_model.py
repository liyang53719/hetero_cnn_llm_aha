"""Default-off internal K windows over the existing FFN physical owner.

The complete Job and A lease are never shortened. Actual A DDR/RMW ingress
loads all rows with the original stride, and selected logical K values address
those same banks. Each block clears Matrix accumulators and emits FP32 into
existing tile 0/1. This is a port/control model, not an FPU or RTL simulation.
Matrix results remain external physical inputs; no partial or golden storage
initializes execution. There is no new payload array, DDR scratch or translator.

The window tick below is the frozen FfnWindowOwnerModel state machine with
only three execution-limit/count expressions and the explicitly scoped
K-window fence diagnostic changed. Keeping this small
candidate copy avoids changing/hash-invalidating the published source. Ordinary
and legacy-window calls delegate through the published drain/window owner.
The drain remains default-off; enabling it reuses this owner and its storage.
Its Activation-only admission is unchanged and is NOT a Dense drain contract.
Physical Matrix results lack tags: the controlled one-group-at-a-time backend
assumption is unchanged. Active metadata and the existing job-tagged done bind
results; this is not a freshness proof for unsolicited backend responses.
"""
from dataclasses import dataclass
from pathlib import Path

# Reuse the published module and its pinned Down/Tile implementations.
import importlib
import hashlib
import sys
ROOT = Path(__file__).resolve().parent.parent
_source = ROOT / "ffn_window/model.py"
if hashlib.sha256(_source.read_bytes()).hexdigest() != "1c9f69beed57b96f6003c199fd02a9d362c16b6fff71ba93a18fb1f10f5eaae4":
    raise ValueError("frozen FFN window model drift")
# The public driver already owns a hash-checked dynamic drain module. Reuse
# that exact authority, including lease/wire classes, instead of loading the
# same source a second time under a different Python class identity.
_repository = str(ROOT.parents[1])
if _repository not in sys.path:
    sys.path.insert(0, _repository)
_drain_source = ROOT / "ffn_drain/model.py"
if hashlib.sha256(_drain_source.read_bytes()).hexdigest() != "c17be9ad7648b0c5ad1802034b47e686abb62ac08ce79d7489491052e300bdfe":
    raise ValueError("frozen FFN drain owner drift")
from ..ffn_public.execute_numeric import numeric as public_numeric
drain = public_numeric.model
if hashlib.sha256(Path(drain.__file__).read_bytes()).hexdigest() != "c17be9ad7648b0c5ad1802034b47e686abb62ac08ce79d7489491052e300bdfe":
    raise ValueError("public original drain authority drift")
window = drain.window
down = window.down
PrefixWorkspace = window.PrefixWorkspace
ReadCommand, ReadBeat = window.ReadCommand, window.ReadBeat
MatrixResult, MatrixDone = window.MatrixResult, window.MatrixDone
Control, Read, Write = window.Control, window.Read, window.Write
ALease = window.ALease


@dataclass(frozen=True)
class Job(window.Job):
    # Mirrors the official-policy job bit. A partial must never materialize BF16.
    materialize_dense_output: bool = False

    def validate(self):
        super().validate()
        if type(self.materialize_dense_output) is not bool:
            raise ValueError("typed Dense materialization policy")


@dataclass(frozen=True, kw_only=True)
class KWindowRequest(window.FfnWindowRequest):
    k_begin: int
    k_end: int
    block_id: int
    pair_reverse: bool = False

    def validate(self):
        super().validate()
        if getattr(self.job, "materialize_dense_output", False):
            raise ValueError("K-window partial must remain FP32")
        if any(type(v) is not int for v in (self.k_begin, self.k_end, self.block_id)):
            raise ValueError("typed K-window bounds/block identity")
        if not 0 <= self.k_begin < self.k_end <= self.job.k:
            raise ValueError("K-window outside full Job")
        # Row DDR packets stay aligned because N/ng/cols are unchanged. Pair
        # boundaries alone require even K; no 1024 or 128-window policy here.
        if self.k_begin % 2 or self.k_end % 2:
            raise ValueError("K-window must contain complete BF16 pairs")
        if not 0 < self.block_id < 2**32 or type(self.pair_reverse) is not bool:
            raise ValueError("nonzero UInt32 block identity/typed pair order")


@dataclass(frozen=True, kw_only=True)
class KWindowStep(down.Step):
    logical_k: int
    job_tag: int
    identity: int
    block_id: int


@dataclass(frozen=True, kw_only=True)
class KWindowResult(window.FfnWindowResult):
    useful_macs: int
    executed_macs: int
    k_begin: int
    k_end: int
    block_id: int
    pair_reverse: bool


class KWindowOwnerModel(drain.FfnDrainOwnerModel):
    def __init__(self, workspace=None, *, enable_k_window=False, **kwargs):
        if type(enable_k_window) is not bool:
            raise ValueError("typed K-window enable")
        if enable_k_window and not kwargs.get("enable_ffn_window", False):
            raise ValueError("K windows require the actual FFN window owner")
        self.enable_k_window = enable_k_window
        super().__init__(workspace, **kwargs)

    def _reset(self):
        super()._reset()
        # Source-model diagnostic event counters, not hardware cycle counters.
        # Preserve the old FFN-window counter's scope; never reset it between
        # modes merely to satisfy a downstream invariant.
        self.k_a_fences = 0

    @property
    def total_window_a_load_fences(self):
        return self.a_fences + self.k_a_fences

    @property
    def execution_end(self):
        return self.window_request.k_end

    @property
    def execution_length(self):
        return self.window_request.k_end - self.window_request.k_begin

    def _begin_execute(self):
        super()._begin_execute()
        if isinstance(self.window_request, KWindowRequest):
            self.issue_k = self.load_k = self.window_request.k_begin

    def _read_command(self):
        if not isinstance(self.window_request, KWindowRequest) or self.state != "execute":
            return super()._read_command()
        if self.error or self.read_active or self.a_hold or self.a_rmw_pending or self.load_k >= self.execution_end:
            return None
        half = (self.load_k // 128) & 1
        if self.ready[half]:
            return None
        j = self.job
        per = 32 if j.weight_bf16 else 16
        address = j.b + ((self.load_k + self.load_depth) * j.n + self.n_base + self.load_beat * per) * (2 if j.weight_bf16 else 4)
        return ReadCommand("b", address, 1, (j.tag << 32) | self.read_sequence)

    def _receive_read(self, beat):
        if not isinstance(self.window_request, KWindowRequest) or self.read_active[0].kind != "b":
            return super()._receive_read(beat)
        cmd, index = self.read_active
        if beat.tag != cmd.tag or beat.error or beat.last != (index + 1 == cmd.beats):
            self._fault("DMA tag/error/LAST")
        if not self.error:
            try:
                words = self._convert(beat.words, self.job.weight_bf16)
            except ValueError as exc:
                self._fault(str(exc))
            else:
                per = len(words)
                half = (self.load_k // 128) & 1
                for offset in range(per // 16):
                    group = self.load_beat * per // 16 + offset
                    bank, word = down.b_address(half, self.load_k + self.load_depth, group // 2, group % 2)
                    self.b_banks.write(bank, word, down.pack16(words[offset*16:offset*16+16]))
                self.load_beat += 1
        terminal = index + 1 == cmd.beats
        self.read_active = None if terminal else (cmd, index + 1)
        self.read_sequence += int(terminal)
        if beat.last and not self.error:
            per = 32 if self.job.weight_bf16 else 16
            if self.load_beat == self.contexts * 32 // per:
                self.load_beat = 0
                self.load_depth += 1
                # Even an interior begin/end remains within a physical B half.
                segment = min(128 - self.load_k % 128, self.execution_end - self.load_k)
                if self.load_depth == segment:
                    half = (self.load_k // 128) & 1
                    self.ready[half] = True
                    self.ready_k[half] = self.load_k // 128 * 128
                    self.load_k += self.load_depth
                    self.load_depth = 0

    def _issue_read(self):
        if not isinstance(self.window_request, KWindowRequest):
            return super()._issue_read()
        q = self.window_request
        ordinal, ctx = self.issue_k - q.k_begin, self.issue_context
        logical_k = q.k_begin + (ordinal ^ int(q.pair_reverse))
        half = (logical_k // 128) & 1
        awords = tuple(self.a_banks.read(*down.a_address(logical_k, 16*group)[:2]) for group in range(8))
        bwords = tuple(self.b_banks.read(*down.b_address(half, logical_k, ctx, nh)) for nh in range(2))
        self.pending = (ordinal, logical_k, ctx, awords, bwords)
        self.issue_context += 1
        if self.issue_context == self.contexts:
            self.issue_context = 0
            self.issue_k += 1
            # Release by accepted local issue progress, NEVER physical xor K.
            # Thus physical 127 then 126 both read before half reuse.
            if self.issue_k % 128 == 0 or self.issue_k == q.k_end:
                self.ready[half] = False

    def _operand_response(self, pending):
        if not isinstance(self.window_request, KWindowRequest):
            return super()._operand_response(pending)
        ordinal, logical_k, ctx, awords, bwords = pending
        q = self.window_request
        activations = tuple(x for word in awords for x in down.unpack16(word))
        weights = tuple(x for word in bwords for x in down.unpack16(word))
        last = ordinal + 1 == self.execution_length
        return KWindowStep(ordinal, ctx, ordinal == 0, last,
                           last and ctx + 1 == self.contexts, last,
                           weights[:16], activations + weights[16:] + (0,)*112,
                           logical_k=logical_k, job_tag=q.job.tag,
                           identity=q.identity, block_id=q.block_id)

    def _finish_window(self):
        super()._finish_window()
        q = self.window_request
        if isinstance(q, KWindowRequest):
            self.window_result = KWindowResult(**vars(self.window_result), k_begin=q.k_begin,
                                               k_end=q.k_end, block_id=q.block_id, pair_reverse=q.pair_reverse,
                                               useful_macs=(self.accepted_steps*q.job.m*32 if self.accepted_steps else 0),
                                               executed_macs=self.accepted_steps*4096)

    def tick(self, *, window=None, **kwargs):
        active = isinstance(self.window_request, KWindowRequest)
        if isinstance(window, KWindowRequest) and not self.enable_k_window:
            result = super().tick(window=None, **kwargs)
            result["window_ready"] = False
        elif active or isinstance(window, KWindowRequest):
            result = self._k_window_tick(window=window, **kwargs)
        else:
            result = super().tick(window=window, **kwargs)
        # Legacy window event traces remain exact when the optional drain is
        # disabled. Enabling drain exposes its existing additional port events.
        if not self.enable_ffn_drain:
            for key in ("drain_ready", "drain_result", "drain_phase", "drain_fire", "drain_result_fire"):
                result.pop(key, None)
        return result

    def _k_window_tick(self, *, window=None, job=None, read_command_ready=True, read_beat=None,
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
        done_ok = (self.group_started and self.issue_k == self.execution_end and
                   self.group_accepted_steps == self.execution_length*self.contexts and
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
                self.k_a_fences += 1
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
                     self.tiles.idle and self.issue_k < self.execution_end and reserved < self.FIFO_DEPTH and
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
