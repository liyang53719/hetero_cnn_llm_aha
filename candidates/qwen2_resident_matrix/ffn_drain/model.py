"""Actual sealed act-bank reads through the existing finalValue and DDR port.

This extends the frozen window/Down owners; their physical A/B Banks, window
producer, ordinary execution and one final_value hold remain the same objects.
Only accepted tile responses populate the hold. No expected output or private
memory bucket can answer an SRAM read or DDR write. FP32 words are opaque here.

This is an event/port model, not a hardware-cycle or numerical claim. As in the
source, one controlled DMA write remains outstanding until its real terminal
ACK, even after abort. Eventual external response is a backend precondition;
finite directed cases do not prove deadlock freedom or generation freshness.
Coordinated reset explicitly includes owner, tile adapter, DMA and Matrix
backends. Identity/tag equality cannot distinguish a stale ACK that collides
with a newly accepted post-reset descriptor; the controlled backend must not
deliver one. Unsolicited late ACKs are poisoned, not silently forgotten.
Inherited WriteAck.nbytes is an optional harness diagnostic; the source wire
has tag/error only and derives byte credit from the accepted descriptor. The
tile_accept_ready/tile_response_ready knobs inject service stalls for protocol
testing; the source's internal adapter drives response.ready from pending.
"""
from dataclasses import dataclass, fields
import hashlib
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "ffn_window/model.py"
if hashlib.sha256(P.read_bytes()).hexdigest() != "1c9f69beed57b96f6003c199fd02a9d362c16b6fff71ba93a18fb1f10f5eaae4":
    raise ValueError("frozen window/physical bank model drift: " + str(P))
spec = importlib.util.spec_from_file_location("ffn_drain_frozen_window", P)
window = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = window
spec.loader.exec_module(window)
down, tiles = window.down, window.tiles
Job, PrefixWorkspace, ALease = window.Job, window.PrefixWorkspace, window.ALease
FfnWindowRequest, FfnWindowResult = window.FfnWindowRequest, window.FfnWindowResult
Control, Read, Write, Response = window.Control, window.Read, window.Write, window.Response
ReadCommand, ReadBeat, Step = window.ReadCommand, window.ReadBeat, window.Step
MatrixResult, MatrixDone = window.MatrixResult, window.MatrixDone
WriteCommand, WriteAck = down.WriteCommand, down.WriteAck


@dataclass(frozen=True)
class WriteBeat(down.WriteBeat):
    mask: int = (1 << 64) - 1


@dataclass(frozen=True)
class ActivationJob(Job):
    """Complete QwenOwnerJob value, using the repository's Python field style.

The public Activation command has k=n=8960, not Dense's input width 1536.
Ancillary fields are retained at their declared ABI widths; they do not select
memory or change the act-drain operation. write_bytes describes the FULL job.
"""
    k: int = 8960
    n: int = 8960
    activation_bf16: bool = False
    weight_bf16: bool = False
    kind: str = "Activation"
    c: int = 0
    history_out: int = 0
    expected_generation: int = 0
    current_generation: int = 0
    cold: bool = False
    cache_capacity: int = 0
    cache_length: int = 0
    expected_cache_length: int = 0
    query_start: int = 0
    qk_role: int = 0
    qk_position_base: int = 0
    qk_trig_tokens: int = 0
    gdn_a_log: int = 0
    gdn_dt_bias: int = 0
    gdn_state_out: int = 0
    gdn_recurrent_mode: bool = False
    gdn_elementwise_op: int = 0

    def validate(self):
        bools = {"activation_bf16", "weight_bf16", "output_bf16", "cold", "gdn_recurrent_mode"}
        widths = {"m": 16, "n": 16, "k": 16, "tag": 32,
                  "a": 64, "b": 64, "c": 64, "dst": 64, "write_bytes": 64,
                  "history_out": 64, "gdn_a_log": 64, "gdn_dt_bias": 64,
                  "gdn_state_out": 64, "qk_role": 2, "gdn_elementwise_op": 2}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in bools:
                if type(value) is not bool:
                    raise ValueError("typed Activation boolean " + f.name)
            elif f.name != "kind":
                if type(value) is not int or not 0 <= value < 1 << widths.get(f.name, 32):
                    raise ValueError("typed Activation UInt " + f.name)
        if self.kind != "Activation" or self.m not in (16, 128) or self.k != 8960 or self.n != 8960:
            raise ValueError("Activation M16/M128 and full K=N=8960 required")
        if self.activation_bf16 or self.weight_bf16 or self.output_bf16:
            raise ValueError("Activation requires FP32 A/B/D")
        size = self.m * self.n * 4
        if self.write_bytes != size:
            raise ValueError("Activation full declared output byte count")
        spans = [(base, base + size) for base in (self.a, self.b, self.dst)]
        if any(base % 64 or end > 1 << 56 for base, end in spans):
            raise ValueError("Activation full aligned 56-bit DDR spans")
        for index, (base, end) in enumerate(spans):
            if any(base < other_end and other_base < end for other_base, other_end in spans[index + 1:]):
                raise ValueError("Activation full spans alias")


@dataclass(frozen=True)
class FfnDrainRequest:
    job: ActivationJob
    identity: int
    ng: int
    cols: int

    def validate(self):
        if not isinstance(self.job, ActivationJob):
            raise ValueError("complete ActivationJob required")
        self.job.validate()
        if type(self.identity) is not int or not 0 < self.identity < 1 << 32:
            raise ValueError("nonzero UInt32 drain identity")
        if type(self.ng) is not int or not 0 <= self.ng < 1 << 16 or self.ng % 32:
            raise ValueError("aligned UInt16 drain ng")
        if type(self.cols) is not int or self.cols not in (32, 64, 96, 128, 160):
            raise ValueError("drain width")
        if self.ng + self.cols > self.job.n:
            raise ValueError("drain exceeds original N")


@dataclass(frozen=True)
class FfnDrainResult:
    tag: int
    identity: int
    ng: int
    rows: int
    cols: int
    status: str | None
    committed: bool
    consumed_beats: int
    ddr_write_bytes: int
    model_ticks: int
    useful_macs: int = 0
    executed_macs: int = 0


class FfnDrainOwnerModel(window.FfnWindowOwnerModel):
    def __init__(self, workspace=None, *, enable_ffn_drain=False,
                 enable_ffn_window=False, enable_ffn_tiles=False):
        if enable_ffn_drain and not enable_ffn_tiles:
            raise ValueError("act drain requires tile profile")
        self.enable_ffn_drain = enable_ffn_drain
        super().__init__(workspace, enable_ffn_window=enable_ffn_window,
                         enable_ffn_tiles=enable_ffn_tiles)

    def _reset(self):
        super()._reset()
        self.drain_request = self.drain_result = None
        self.drain_poison = False
        self.drain_phase = "idle"
        self.drain_expected = None
        self.drain_consumed = self.drain_started = 0
        self.drain_column = self.write_row = self.write_row_beat = 0
        self.accepted_write = None

    @property
    def saving_prefix(self):
        return False if self.drain_request is not None else super().saving_prefix

    def _fault(self, reason):
        super()._fault(reason)
        if self.drain_request is not None:
            self.tiles._fault(reason)
            if self.drain_phase != "held":
                self.drain_phase = "error"

    def _write_command(self):
        if self.drain_request is None:
            return super()._write_command()
        if self.error or self.drain_phase != "write" or self.write_state != "request":
            return None
        q = self.drain_request
        address = q.job.dst + (self.write_row * q.job.n + q.ng + 16 * self.write_row_beat) * 4
        count = min(q.cols // 16 - self.write_row_beat, 16 - ((address >> 6) & 15))
        return WriteCommand(address, count, (q.job.tag << 32) | self.write_sequence)

    def _write_data(self):
        if self.drain_request is None:
            return super()._write_data()
        if self.write_state != "data":
            return None
        first = 16 * (self.write_row_beat + self.write_index)
        return WriteBeat(tuple(self.final_value[self.write_row % 16][first:first + 16]),
                         self.write_index + 1 == self.accepted_write.beats)

    def ports(self):
        p = super().ports()
        p.update(drain_ready=self.enable_ffn_drain and self.state == "idle" and self.tiles.idle and not self.tiles.poison,
                 drain_result=self.drain_result if self.drain_phase == "held" and self.state == "finish" else None,
                 drain_phase=self.drain_phase)
        if self.drain_poison:
            p.update(job_ready=False, window_ready=False, drain_ready=False, reset_required=True)
        if self.drain_request is not None:
            p.update(job_ready=False, window_ready=False, drain_ready=False,
                     response=None, window_result=None, read_command=None, read_ready=False,
                     group=None, step=None, result_ready=False, matrix_done_ready=False,
                     seed_begin=None, seed_beat=None, seed_ack_ready=False,
                     write_ack_ready=self.write_state == "ack")
        return p

    def _finish_drain(self):
        q = self.drain_request
        self.drain_result = FfnDrainResult(q.job.tag, q.identity, q.ng, q.job.m, q.cols,
            self.error, self.error is None, self.drain_consumed, self.write_bytes,
            self.clock - self.drain_started)
        self.drain_phase, self.state = "held", "finish"

    def _slot_exact(self, *, released=False):
        q, t = self.drain_request, self.tiles.tags[2]
        expected = q.job.m // 16 * q.cols
        same = ((t.identity, t.ng, t.rows, t.cols) == (q.identity, q.ng, q.job.m, q.cols))
        if released:
            return same and not t.live and not t.sealed and t.consumed == expected
        return (same and t.live and t.sealed and t.expected == expected and
                t.produced == expected and not getattr(t, "matrix_producer_order", False))

    def _admit_drain(self, q):
        self.drain_request, self.job = q, q.job
        self.drain_result = None
        self.drain_started = self.clock
        self.drain_consumed = self.drain_column = self.write_row = self.write_row_beat = 0
        self.write_bytes = 0
        self.drain_expected = self.accepted_write = None
        self.error = None
        self.write_state = "idle"
        self.group_started = self.group_done = False
        self.final_value = None
        try:
            q.validate()
            if self.workspace is None:
                raise ValueError("explicit prefix workspace required")
            # Activation spans are all M*N, not Dense B's K*N allocation.
            w = self.workspace
            if (type(w.base) is not int or type(w.extent) is not int or
                w.base < 0 or w.base % 64 or w.extent <= 0 or w.base + w.extent > 1 << 56 or
                not 0 < w.generation < 1 << 32 or not 0 < w.split_k <= 2560 or w.split_k % 128):
                raise ValueError("prefix workspace geometry")
            size = q.job.m * q.job.n * 4
            if any(w.base < base + size and base < w.base + w.extent for base in (q.job.a, q.job.b, q.job.dst)):
                raise ValueError("prefix workspace aliases Activation span")
            if not (self.tiles.idle and self._slot_exact() and self.tiles.tags[2].consumed == 0):
                raise ValueError("sealed act slot identity/shape/production/consumption mismatch")
        except ValueError as exc:
            self._fault(str(exc))
        else:
            # Reuse the inherited 16 KiB hold. Only its first cols words per
            # row are written/read by each 16-row group. It is never an oracle.
            self.final_value = [[0] * 256 for _ in range(16)]
            self.state, self.drain_phase = "ffn_drain", "read"

    def tick(self, *, drain=None, drain_result_ready=True, window=None, job=None,
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
                    self.drain_consumed != expected or self.write_bytes != q.job.m * q.cols * 4):
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
                    if self.write_row_beat == self.drain_request.cols // 16:
                        self.write_row_beat = 0
                        self.write_row += 1
                    if self.write_row == self.job.m:
                        if (self.write_bytes != self.job.m * self.drain_request.cols * 4 or
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
                self.drain_consumed != q.job.m // 16 * q.cols or self.write_bytes != q.job.m * q.cols * 4):
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
