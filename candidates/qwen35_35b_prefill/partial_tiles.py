"""Explicit K2048 dual-partial lease on the existing physical A SRAM.

This is a port/control specification, not arithmetic or RTL evidence. The
caller supplies the actual Vector Add result, after both operand response
handshakes. A sealed sum is INTERNAL completion; only the parent's real DDR
write acknowledgement can complete a public command.

All tensor storage is ``down.Banks``: 16 banks x 1376 x 256 bits. BF16 M128
K2048 A occupies [0,1024), two FP32 M128 N160 partials [1024,1184) and
[1184,1344), and [1344,1376) is spare, in EVERY bank. No logical third slot,
shadow partial/result array, or extra Matrix context is allocated. A pending
4096-bit captured value models the nonstallable synchronous SRAM response,
consumed on the next edge. The selected 16 FP32 words hold either a read
response or the accepted write payload, mutually exclusively. The existing
Sum controller owns its already-present separate lhs operand hold.

The fixed original authority is reused through k_window_model, which pins
the old window/drain/tile/Down sources. Legacy phase-less wires mean partial
only. Old 0.8B modules and their three-slot layout remain untouched.
"""
from dataclasses import dataclass, field

from ..qwen2_resident_matrix.dense_block_reduce.k_window_model import window, down


BANKS = 16
DEPTH = 1376
A_WORDS = 1024
SLOT_WORDS = 160
SLOTS = 2
CONTEXTS = 5


@dataclass(frozen=True)
class Control(window.Control):
    phase: str = field(default="partial", kw_only=True)


@dataclass(frozen=True)
class Read(window.Read):
    phase: str = field(default="partial", kw_only=True)


@dataclass(frozen=True)
class Write(window.Write):
    phase: str = field(default="partial", kw_only=True)


@dataclass(frozen=True)
class Response(window.Response):
    phase: str = field(default="partial", kw_only=True)


@dataclass(frozen=True)
class BeginOverwrite:
    """Revoke both partial leases and reserve lhs for a distinct sum identity."""
    identity: int
    ng: int
    rows: int
    cols: int
    lhs_identity: int
    rhs_identity: int
    lhs_slot: int = 0
    rhs_slot: int = 1

    @property
    def beats(self):
        return self.rows // 16 * self.cols

    def validate(self):
        if (any(type(value) is not int for value in vars(self).values()) or
                not all(0 < value < 2**32 for value in
                        (self.identity, self.lhs_identity, self.rhs_identity)) or
                self.identity in (self.lhs_identity, self.rhs_identity) or
                not 0 <= self.ng < 2**16 or self.ng % 32 or
                self.rows not in (16, 128) or
                self.cols not in (32, 64, 96, 128, 160) or
                sorted((self.lhs_slot, self.rhs_slot)) != [0, 1]):
            raise ValueError("typed overwrite identity/geometry/distinct physical slots")


@dataclass
class Tag(window.Tag):
    phase: str = "partial"
    poisoned: bool = False


@dataclass
class Overwrite:
    """Only control metadata; no old/new tensor values are retained."""
    call: BeginOverwrite
    index: int = 0
    stage: str = "lhs"
    lhs_consumed: int = 0
    rhs_consumed: int = 0
    writes_committed: int = 0


def location(slot, row_group, column):
    if (any(type(value) is not int for value in (slot, row_group, column)) or
            not 0 <= slot < SLOTS or not 0 <= row_group < 8 or
            not 0 <= column < 160):
        raise ValueError("physical dual FP32 tile coordinate")
    return A_WORDS + slot * SLOT_WORDS + row_group * 20 + column // 8, column % 8


producer_index = window.producer_index


def resource_ledger():
    """Coexistent physical allocation, independent of command indices."""
    return dict(banks=BANKS, words_per_bank=DEPTH, bits_per_word=256,
                total_bytes=BANKS * DEPTH * 32, matrix_contexts=CONTEXTS,
                a_words=(0, 1024), lhs_words=(1024, 1184),
                rhs_words=(1184, 1344), spare_words=(1344, 1376),
                a_bytes=524288, partial_bytes_each=81920, spare_bytes=16384,
                read_ports_per_bank=1, write_ports_per_bank=1,
                selected_value_hold_bits=512,
                pending_synchronous_response_bits=4096,
                additional_tensor_storage_bytes=0)


class TileBankModel(window.TileBankModel):
    """Default-explicit, destructive dual-slot variant; never alias slot 2."""
    def __init__(self, banks=None):
        # Reuse the same class authority, including its physical port ledger.
        super().__init__(banks)
        if (not isinstance(self.banks, down.Banks) or
                len(self.banks.words) != BANKS or
                any(len(bank) != DEPTH for bank in self.banks.words)):
            raise ValueError("the existing 16x1376x256 down.Banks allocation is required")
        self.tags = [Tag() for _ in range(SLOTS)]
        self.overwrite = None
        self.counters.update(overwrites=0, sum_seals=0, operand_responses=0)

    @property
    def leased(self):
        return (self.overwrite is not None or
                any(tag.live or tag.poisoned for tag in self.tags))

    @property
    def sum_ready(self):
        return (not self.poison and self.idle and self.overwrite is None and
                any(tag.live and tag.sealed and tag.phase == "sum"
                    for tag in self.tags))

    def _fault(self, reason):
        super()._fault(reason)
        for tag in self.tags:
            if tag.live or self.overwrite is not None:
                tag.poisoned = True
                tag.live = tag.sealed = False

    def job_admission(self, kind, k, *, silu_busy=False, loan_request=False):
        if (self.poison or not self.idle or self.overwrite is not None or
                silu_busy or loan_request):
            return False, None
        if self.leased and kind != "Dense":
            return True, "Unsupported"
        if self.leased and (type(k) is not int or k > 2048):
            return True, "Bounds"
        return True, None

    @staticmethod
    def _phase(q):
        # The exact legacy authority has no phase and means ONLY partial.
        return getattr(q, "phase", "partial")

    @staticmethod
    def _key_valid(q):
        return (type(q.slot) is int and 0 <= q.slot < SLOTS and
                type(q.identity) is int and 0 < q.identity < 2**32 and
                type(q.ng) is int and 0 <= q.ng < 2**16 and q.ng % 32 == 0)

    def _beat_valid(self, q, writing):
        wire = window.Write if writing else window.Read
        if not isinstance(q, wire) or not self._key_valid(q) or type(q.index) is not int:
            return False
        phase = self._phase(q)
        if type(phase) is not str:
            return False
        if self.overwrite is not None:
            o, c = self.overwrite, self.overwrite.call
            if q.ng != c.ng or q.index != o.index or not 0 <= q.index < c.beats:
                return False
            if writing:
                return (phase == "sum" and o.stage == "sum" and
                        (q.slot, q.identity) == (c.lhs_slot, c.identity) and
                        o.lhs_consumed == o.rhs_consumed == o.index + 1)
            return ((phase == o.stage == "lhs" and
                     (q.slot, q.identity) == (c.lhs_slot, c.lhs_identity)) or
                    (phase == o.stage == "rhs" and
                     (q.slot, q.identity) == (c.rhs_slot, c.rhs_identity)))
        tag = self.tags[q.slot]
        if not (tag.live and not tag.poisoned and phase == tag.phase and
                tag.identity == q.identity and tag.ng == q.ng and
                0 <= q.index < tag.expected):
            return False
        if writing:
            expected = (producer_index(tag.produced, tag.rows, tag.cols)
                        if tag.matrix_producer_order and tag.produced < tag.expected
                        else tag.produced)
            return phase == "partial" and not tag.sealed and q.index == expected
        return tag.sealed and q.index == tag.consumed

    def _begin_overwrite(self, q):
        try:
            q.validate()
        except (ValueError, TypeError):
            self._fault("overwrite identity/geometry")
            return
        if self.overwrite is not None:
            self._fault("overwrite already in progress")
            return
        for slot, identity in ((q.lhs_slot, q.lhs_identity), (q.rhs_slot, q.rhs_identity)):
            tag = self.tags[slot]
            if not (tag.live and tag.sealed and tag.phase == "partial" and
                    not tag.poisoned and tag.identity == identity and
                    (tag.ng, tag.rows, tag.cols) == (q.ng, q.rows, q.cols) and
                    tag.produced == tag.expected and tag.consumed == 0):
                self._fault("overwrite requires two complete unconsumed sealed partials")
                return
        self.overwrite = Overwrite(q)
        # Revoke BOTH ordinary read capabilities immediately. Old lhs data
        # remains accessible only through the per-index destructive phase.
        self.tags[q.lhs_slot] = Tag(q.identity, q.ng, q.rows, q.cols, phase="sum")
        rhs = self.tags[q.rhs_slot]
        rhs.live = rhs.sealed = False
        rhs.phase = "rhs"
        self.counters["overwrites"] += 1

    def _control(self, q):
        if isinstance(q, BeginOverwrite):
            self._begin_overwrite(q)
            return
        if (not isinstance(q, window.Control) or not self._key_valid(q) or
                type(q.op) is not int or q.op not in (0, 1, 2) or
                type(q.rows) is not int or q.rows not in (16, 128) or
                type(q.cols) is not int or q.cols not in (32, 64, 96, 128, 160) or
                type(q.matrix_producer_order) is not bool or
                self._phase(q) not in ("partial", "sum")):
            self._fault("control geometry/identity/phase")
            return
        phase, tag = self._phase(q), self.tags[q.slot]
        same = ((tag.identity, tag.ng, tag.rows, tag.cols, tag.phase) ==
                (q.identity, q.ng, q.rows, q.cols, phase))
        if self.overwrite is not None:
            o, c = self.overwrite, self.overwrite.call
            if (q.op == 1 and same and phase == "sum" and q.slot == c.lhs_slot and
                    o.stage == "seal" and o.index == o.writes_committed == c.beats and
                    o.lhs_consumed == o.rhs_consumed == c.beats and
                    tag.produced == tag.expected and not q.matrix_producer_order):
                tag.live = tag.sealed = True
                self.tags[c.rhs_slot] = Tag()
                self.overwrite = None
                self.counters["sum_seals"] += 1
            else:
                self._fault("sum seal before destructive operand and RMW drain")
            return
        if q.op == 0:
            if tag.live or tag.poisoned or phase != "partial":
                self._fault("begin requires free partial slot")
            else:
                self.tags[q.slot] = Tag(q.identity, q.ng, q.rows, q.cols, live=True,
                                       matrix_producer_order=q.matrix_producer_order)
        elif (q.op == 1 and same and tag.live and phase == "partial" and
              not tag.sealed and tag.produced == tag.expected):
            tag.sealed = True
        elif (q.op == 2 and same and tag.live and tag.sealed and
              tag.consumed == tag.expected):
            # Preserve the retired identity/count receipt. The real Dense
            # drain checks these fields on the next edge before publishing;
            # revoking access must not erase the completion evidence.
            tag.live = False
            tag.sealed = False
        else:
            self._fault("seal/release before exact producer/consumer drain")

    @staticmethod
    def _dense_valid(reads, writes, limit):
        try:
            if any(len(q) != 2 for q in reads) or any(len(q) != 3 for q in writes):
                return False
            addresses = list(reads) + [(bank, word) for bank, word, _ in writes]
            if any(type(bank) is not int or type(word) is not int or
                   not 0 <= bank < BANKS or not 0 <= word < limit
                   for bank, word in addresses):
                return False
            if any(type(value) is not int or not 0 <= value < 2**256
                   for _, _, value in writes):
                return False
            return (len({q[0] for q in reads}) == len(reads) and
                    len({q[0] for q in writes}) == len(writes) and
                    not set(reads).intersection((bank, word) for bank, word, _ in writes))
        except (TypeError, ValueError):
            return False

    def tick(self, *, control=None, write=None, read=None, response_ready=True,
             abort=False, owner_quiescent=True, coordinated_reset=False,
             dense_reads=None, dense_writes=None):
        """One bank clock; accepted SRAM/RMW obligations retire next edge.

        Arbitration is control, write, read; no new request shares an edge
        with a pending response or selected response hold. Dense can access
        low A while ordinary partial/sum leases exist, but receives no grant
        during destructive reduction. Coordinated reset must follow physical
        drain, cannot cancel an accepted RMW, and never erases SRAM.
        """
        self.cycle += 1
        self.banks.begin_cycle()
        if coordinated_reset and self.idle:
            self.tags = [Tag() for _ in range(SLOTS)]
            self.overwrite = None
            self.poison, self.reason = False, None
            return dict(ctl_ready=False, write_ready=False, read_ready=False,
                        ctl_fire=False, write_fire=False, read_fire=False,
                        response_fire=False, response=None, dense_grant=False,
                        reads={}, writes={}, rmw_commit=False, poison=False,
                        sum_ready=False, reset=True)
        if coordinated_reset:
            self._fault("coordinated reset requires accepted bank obligations to drain")
        idle_at_edge, response_at_edge = self.idle, self.response
        grant = idle_at_edge and owner_quiescent and not self.poison and not abort
        ctl_ready = grant
        write_ready = grant and control is None
        read_ready = grant and control is None and write is None
        dense_grant = (idle_at_edge and not owner_quiescent and not self.poison and
                       not abort and self.overwrite is None)
        dense_reads, dense_writes = dense_reads or (), dense_writes or ()
        if dense_grant and not self._dense_valid(dense_reads, dense_writes,
                                                 A_WORDS if self.leased else DEPTH):
            self._fault("Dense access violates shared range/1R1W/read-write conflict")
            dense_grant = False
        edge = dict(ctl_ready=ctl_ready, write_ready=write_ready, read_ready=read_ready,
                    ctl_fire=ctl_ready and control is not None,
                    write_fire=write_ready and write is not None,
                    read_fire=read_ready and read is not None,
                    response=response_at_edge,
                    response_fire=response_at_edge is not None and response_ready,
                    dense_grant=dense_grant, reads={}, writes={}, rmw_commit=False,
                    reset=False)
        if response_at_edge is not None and not response_ready:
            self.counters["response_stall_cycles"] += 1
        if abort:
            self.counters["aborted"] += 1
            self._fault("abort")
        if self.pending is not None:
            kind, q, word, lane, captured = self.pending
            self.pending = None
            if kind == "write":
                mask = 0xffffffff << (32 * lane)
                for bank in range(BANKS):
                    merged = (captured[bank] & ~mask) | (q.words[bank] << (32 * lane))
                    self.banks.write(bank, word, merged)
                self.tags[q.slot].produced += 1
                if self.overwrite is not None:
                    o = self.overwrite
                    o.writes_committed += 1
                    o.index += 1
                    o.stage = "seal" if o.index == o.call.beats else "lhs"
                self.counters["rmw_commits"] += 1
                self.counters["logical_write_bytes"] += 64
                self.counters["physical_write_bytes"] += BANKS * 32
                edge["rmw_commit"] = True
            else:
                words = tuple((value >> (32 * lane)) & 0xffffffff for value in captured)
                bad = not all(down.finite32(value) for value in words)
                if bad:
                    self._fault("nonfinite tile read")
                self.response = Response(q.slot, q.identity, q.ng, q.index, words,
                                         bad or self.poison, phase=self._phase(q))
        if edge["response_fire"]:
            q = response_at_edge
            if self.overwrite is not None:
                o = self.overwrite
                if q.phase == "lhs":
                    o.lhs_consumed += 1
                    o.stage = "rhs"
                elif q.phase == "rhs":
                    o.rhs_consumed += 1
                    self.tags[q.slot].consumed += 1
                    o.stage = "sum"
                self.counters["operand_responses"] += 1
            else:
                self.tags[q.slot].consumed += 1
            self.counters["read_responses"] += 1
            self.counters["logical_read_bytes"] += 64
            self.response = None
        if edge["ctl_fire"]:
            self._control(control)
        if edge["write_fire"] or edge["read_fire"]:
            writing = edge["write_fire"]
            q = write if writing else read
            valid = self._beat_valid(q, writing)
            if writing:
                valid = (valid and type(q.words) is tuple and len(q.words) == BANKS and
                         all(down.finite32(value) for value in q.words))
            if not valid:
                self._fault("invalid or out-of-order tile phase/tag/index")
            else:
                tag = self.tags[q.slot]
                row_group, column = divmod(q.index, tag.cols)
                word, lane = location(q.slot, row_group, column)
                captured = tuple(self.banks.read(bank, word) for bank in range(BANKS))
                self.pending = ("write" if writing else "read", q, word, lane, captured)
                if writing and self.overwrite is not None:
                    self.overwrite.stage = "rmw"
                self.counters["write_requests" if writing else "read_requests"] += 1
                self.counters["physical_read_bytes"] += BANKS * 32
        if dense_grant:
            self.counters["dense_grants"] += 1
            for bank, word in dense_reads:
                self.banks.read(bank, word)
            for bank, word, value in dense_writes:
                self.banks.write(bank, word, value)
        edge["reads"], edge["writes"] = dict(self.banks.reads), dict(self.banks.writes)
        edge["poison"], edge["sum_ready"] = self.poison, self.sum_ready
        return edge
