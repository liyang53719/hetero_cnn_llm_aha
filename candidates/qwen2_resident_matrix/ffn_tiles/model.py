"""Ordered typed FP32 tiles in the actual transposed Dense A-bank layout.

Port/control model only. Arithmetic is supplied by the unchanged source-tied
SiLU reference; no output oracle is used to answer a memory read. Each bank
still has one synchronous read and one write. Python's pending read value
represents the SRAM response wire, not another architectural SRAM or a
4096-bit response register. Only the selected 16 FP32 values are held.
"""
from dataclasses import dataclass
import hashlib
import importlib.util
from pathlib import Path
import sys

P = Path(__file__).resolve().parent.parent / "transposed_down/model.py"
if hashlib.sha256(P.read_bytes()).hexdigest() != "3e6f73fa8fe6ce5e78b4578335e82d7e593d0cce0b35e8f401dc045e1df59412":
    raise ValueError("frozen physical bank model drift")
spec = importlib.util.spec_from_file_location("ffn_frozen_down", P)
down = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = down
spec.loader.exec_module(down)


@dataclass(frozen=True)
class Control:
    op: int
    slot: int
    identity: int
    ng: int
    rows: int
    cols: int


@dataclass(frozen=True)
class Read:
    slot: int
    identity: int
    ng: int
    index: int


@dataclass(frozen=True)
class Write(Read):
    words: tuple


@dataclass(frozen=True)
class Response(Read):
    words: tuple
    error: bool = False


@dataclass
class Tag:
    identity: int = 0
    ng: int = 0
    rows: int = 0
    cols: int = 0
    produced: int = 0
    consumed: int = 0
    live: bool = False
    sealed: bool = False

    @property
    def expected(self):
        return self.rows // 16 * self.cols


def location(slot, row_group, column):
    if not (0 <= slot < 3 and 0 <= row_group < 8 and 0 <= column < 160):
        raise ValueError("physical FP32 tile coordinate")
    return 768 + slot*160 + row_group*20 + column//8, column % 8


class TileBankModel:
    def __init__(self, banks=None):
        self.banks = down.Banks(1376) if banks is None else banks
        if self.banks.depth != 1376:
            raise ValueError("existing 16x1376x256 A allocation required")
        self.tags = [Tag() for _ in range(3)]
        self.poison = False
        self.reason = None
        self.pending = None
        self.response = None
        self.cycle = 0
        self.counters = dict(read_requests=0, write_requests=0, read_responses=0,
                             rmw_commits=0, logical_read_bytes=0, logical_write_bytes=0,
                             physical_read_bytes=0, physical_write_bytes=0,
                             aborted=0, dense_grants=0, response_stall_cycles=0)

    @property
    def idle(self):
        return self.pending is None and self.response is None

    @property
    def leased(self):
        return any(t.live for t in self.tags)

    def _fault(self, reason):
        self.poison = True
        self.reason = self.reason or reason

    def job_admission(self, kind, k, *, silu_busy=False, loan_request=False):
        """Selected owner/kernel admission slice, not a new public command."""
        if self.poison or not self.idle or silu_busy or loan_request:
            return False, None
        if self.leased and kind != "Dense":
            return True, "Unsupported"
        if self.leased and k > 1536:
            return True, "Bounds"
        return True, None

    @staticmethod
    def _key_valid(q):
        return (type(q.slot) is int and 0 <= q.slot < 3 and
                type(q.identity) is int and 0 < q.identity < 1 << 32 and
                type(q.ng) is int and 0 <= q.ng < 1 << 16 and q.ng % 32 == 0)

    def _beat_valid(self, q, writing):
        if not self._key_valid(q) or type(q.index) is not int:
            return False
        t = self.tags[q.slot]
        return (t.live and t.identity == q.identity and t.ng == q.ng and
                0 <= q.index < t.expected and
                (not t.sealed and q.index == t.produced if writing else
                 t.sealed and q.index == t.consumed))

    def _control(self, q):
        if (not self._key_valid(q) or q.op not in (0, 1, 2) or
                q.rows not in (16, 128) or q.cols not in (32, 64, 96, 128, 160)):
            self._fault("control geometry/identity")
            return
        t = self.tags[q.slot]
        if q.op == 0:
            if t.live:
                self._fault("begin while tile live")
            else:
                self.tags[q.slot] = Tag(q.identity, q.ng, q.rows, q.cols, live=True)
        else:
            same = (t.live and (t.identity, t.ng, t.rows, t.cols) ==
                    (q.identity, q.ng, q.rows, q.cols))
            if q.op == 1 and same and not t.sealed and t.produced == t.expected:
                t.sealed = True
            elif q.op == 2 and same and t.sealed and t.consumed == t.expected:
                t.live = False
                t.sealed = False
            else:
                self._fault("seal/release before exact producer/consumer drain")

    def tick(self, *, control=None, write=None, read=None, response_ready=True,
             abort=False, owner_quiescent=True, coordinated_reset=False,
             dense_reads=None, dense_writes=None):
        """Pre-edge ready/valid plus transfers and physical accesses at this edge.

        Arbitration priority is control, write, read. Dense may use the low
        768 A words while slots remain live, after accepted tile traffic has
        drained. Backends must respect that grant; invalid high-region access
        poisons without touching SRAM. Large-K admission belongs to the owner.
        Reset clears control state only; shared SRAM cells are not erased.
        """
        self.cycle += 1
        self.banks.begin_cycle()
        if coordinated_reset:
            self.tags = [Tag() for _ in range(3)]
            self.pending = self.response = None
            self.poison = False
            self.reason = None
            return dict(ctl_fire=False, write_fire=False, read_fire=False,
                        response_fire=False, response=None, reads={}, writes={}, reset=True)
        idle_at_edge = self.idle
        response_at_edge = self.response
        grant = idle_at_edge and owner_quiescent and not self.poison and not abort
        ctl_ready = grant
        write_ready = grant and control is None
        read_ready = grant and control is None and write is None
        dense_grant = idle_at_edge and not self.poison and not owner_quiescent and not abort
        dense_addresses = [(bank, word) for bank, word in dense_reads or ()]
        dense_addresses += [(bank, word) for bank, word, _ in dense_writes or ()]
        dense_bad = any(not (0 <= bank < 16 and 0 <= word < (768 if self.leased else 1376))
                        for bank, word in dense_addresses)
        if dense_grant and dense_bad:
            self._fault("Dense access intersects leased FP32 slots or exceeds A SRAM")
            dense_grant = False
        e = dict(ctl_ready=ctl_ready, write_ready=write_ready, read_ready=read_ready,
                 ctl_fire=ctl_ready and control is not None,
                 write_fire=write_ready and write is not None,
                 read_fire=read_ready and read is not None,
                 response=response_at_edge,
                 response_fire=response_at_edge is not None and response_ready,
                 dense_grant=dense_grant, reads={}, writes={}, rmw_commit=False)
        if response_at_edge is not None and not response_ready:
            self.counters["response_stall_cycles"] += 1
        if abort:
            self.counters["aborted"] += 1
            self._fault("abort")
        # An accepted read or RMW owns the next bank edge despite abort.
        if self.pending is not None:
            kind, q, word, lane, captured = self.pending
            self.pending = None
            if kind == "write":
                mask = 0xffffffff << (32*lane)
                for bank in range(16):
                    merged = (captured[bank] & ~mask) | (q.words[bank] << (32*lane))
                    self.banks.write(bank, word, merged)
                self.tags[q.slot].produced += 1
                self.counters["rmw_commits"] += 1
                self.counters["logical_write_bytes"] += 64
                self.counters["physical_write_bytes"] += 16*32
                e["rmw_commit"] = True
            else:
                words = tuple((x >> (32*lane)) & 0xffffffff for x in captured)
                bad = not all(down.finite32(x) for x in words)
                if bad:
                    self._fault("nonfinite tile read")
                self.response = Response(q.slot, q.identity, q.ng, q.index, words, bad or self.poison)
        if e["response_fire"]:
            self.tags[response_at_edge.slot].consumed += 1
            self.counters["read_responses"] += 1
            self.counters["logical_read_bytes"] += 64
            self.response = None
        if e["ctl_fire"]:
            self._control(control)
        if e["write_fire"] or e["read_fire"]:
            writing = e["write_fire"]
            q = write if writing else read
            valid = self._beat_valid(q, writing)
            if writing:
                valid = valid and len(q.words) == 16 and all(down.finite32(x) for x in q.words)
            if not valid:
                self._fault("invalid or out-of-order tile beat")
            else:
                t = self.tags[q.slot]
                row_group, column = divmod(q.index, t.cols)
                word, lane = location(q.slot, row_group, column)
                captured = tuple(self.banks.read(bank, word) for bank in range(16))
                self.pending = ("write" if writing else "read", q, word, lane, captured)
                self.counters["write_requests" if writing else "read_requests"] += 1
                self.counters["physical_read_bytes"] += 16*32
        if dense_grant:
            self.counters["dense_grants"] += 1
            for bank, word in dense_reads or ():
                self.banks.read(bank, word)
            for bank, word, value in dense_writes or ():
                self.banks.write(bank, word, value)
        e["reads"], e["writes"] = dict(self.banks.reads), dict(self.banks.writes)
        e["poison"] = self.poison
        return e
