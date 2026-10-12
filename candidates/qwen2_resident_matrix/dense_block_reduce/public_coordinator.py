"""One public Dense transaction over two K partials and bounded N windows.

Only control metadata lives here. The existing owner produces tile 0/1, the
shared vector loan reduces them into tile 2, and the existing drain retires
real DDR ACKs. The caller clocks those components exactly once per edge and
supplies their actual retirement fences. No tensor, arithmetic, SRAM, public
opcode, private address, or shape-derived performance total is introduced.

Ticks are protocol events, never hardware cycles. A held terminal is stable;
reset_required fences an unaccepted success after a fault. The receiving Host
must honor that sideband on the same acceptance edge. An already accepted
terminal is never retracted. Coordinated reset also flushes external backends;
tag equality alone cannot establish freshness across that reset boundary.
"""
from dataclasses import dataclass, replace

from .dense_drain import DenseDrainRequest, Job
from .k_window_model import KWindowRequest
from .sum_tiles import SumInvocation

U64 = (1 << 64) - 1
RESET_DOMAIN = frozenset({"host", "coordinator", "window", "drain", "tiles", "vector", "dma", "matrix"})


def uint(value, bits):
    return type(value) is int and 0 <= value < 1 << bits


@dataclass(frozen=True)
class DenseReductionRequest:
    job: Job
    identity: int
    k_ranges: tuple[tuple[int, int], tuple[int, int]]
    pair_reverse: bool = False

    def validate(self):
        if not isinstance(self.job, Job):
            raise ValueError("complete typed original Dense Job required")
        if type(self.k_ranges) is not tuple or len(self.k_ranges) != 2:
            raise ValueError("three physical tiles require exactly two explicit K ranges")
        if any(type(r) is not tuple or len(r) != 2 or
               any(not uint(v, 16) for v in r) for r in self.k_ranges):
            raise ValueError("typed immutable K range pairs required")
        if type(self.pair_reverse) is not bool:
            raise ValueError("typed pair order required")
        a, b = self.k_ranges
        if a[0] != 0 or a[1] != b[0] or b[1] != self.job.k:
            raise ValueError("two contiguous K ranges must cover the original full K exactly")
        # Reuse real producer/drain validation, including original full spans.
        cols = min(160, self.job.n)
        DenseDrainRequest(self.job, self.identity, 0, cols).validate()
        for index, (begin, end) in enumerate(self.k_ranges):
            KWindowRequest(self.job, self.identity, 0, cols, index, bool(index),
                k_begin=begin, k_end=end, block_id=index + 1,
                pair_reverse=self.pair_reverse).validate()

    def snapshot(self):
        self.validate()
        return replace(self, job=replace(self.job),
                       k_ranges=tuple(tuple(r) for r in self.k_ranges))


@dataclass(frozen=True)
class Services:
    window_busy: bool = False
    drain_busy: bool = False
    tiles_drained: bool = True
    tiles_leased: bool = False
    vector_drained: bool = True
    sum_busy: bool = False
    lease_valid: bool = False
    matrix_drained: bool = True
    dma_drained: bool = True
    window_reset: bool = False
    drain_reset: bool = False
    sum_reset: bool = False
    vector_reset: bool = False
    tiles_reset: bool = False
    # Independent external or registered indication, never this coordinator's
    # outgoing backend_abort looped through an aggregate current reset wire.
    backend_reset: bool = False

    @property
    def error(self):
        return (self.window_reset or self.drain_reset or self.sum_reset or
                self.vector_reset or self.tiles_reset or self.backend_reset)

    @property
    def owner_retired(self):
        return not self.window_busy and not self.drain_busy and self.matrix_drained and self.dma_drained

    @property
    def retired(self):
        return self.owner_retired and self.tiles_drained and self.vector_drained and not self.sum_busy


@dataclass(frozen=True)
class DenseReductionResult:
    tag: int
    status: str | None
    write_bytes: int
    cycles: None
    useful_macs: int
    executed_macs: int
    model_ticks: int


class DenseReductionCoordinator:
    """Explicit ready/valid control; callers provide actual backend terminals.

    `window_result` must include useful_macs/executed_macs from accepted Matrix
    steps. Only a drain result may credit DDR bytes. Services remain busy while
    offering a terminal. Poisoned tile leases may remain quarantined after a
    failure, but every accepted DMA/Matrix/vector/bank obligation must retire.
    """
    STATES = ("idle", "partialFlush", "partialIssue", "partialWait", "sumIssue", "sumWait",
              "drainFlush", "drainIssue", "drainWait", "invalidate", "retire", "draining", "reply", "locked")

    def __init__(self):
        self.state = "idle"
        self.call = self.result = None
        self.ng = self.block = self.model_ticks = 0
        self.write_bytes = self.useful = self.executed = 0
        self.poison = False
        self.status = None
        self.window_pending = self.drain_pending = self.sum_pending = False

    @property
    def cols(self):
        return min(160, self.call.job.n - self.ng) if self.call else 0

    def ports(self, services=Services(), *, abort=False):
        s = self.state
        # The owner resetRequired wire can reflect its incoming abort. Never
        # feed that current service indication back into outgoing abort: only
        # independent external abort or registered local poison may cancel it.
        cancel = self.poison or abort
        bad = cancel or services.error
        bank_granted = services.owner_retired and s in ("sumIssue", "sumWait", "draining")
        window = None
        if not bad and s == "partialIssue":
            begin, end = self.call.k_ranges[self.block]
            window = KWindowRequest(self.call.job, self.call.identity, self.ng, self.cols,
                self.block, bool(self.block or self.ng), k_begin=begin, k_end=end,
                block_id=self.block + 1, pair_reverse=self.call.pair_reverse)
        return dict(state=s, busy=s not in ("idle", "locked"), reset_required=bool(bad),
            request_ready=s == "idle" and not bad and services.retired and not services.tiles_leased,
            result=self.result if s == "reply" else None,
            handoff=self.call.job if not bad and s in ("partialFlush", "drainFlush") else None,
            window_request=window,
            sum_request=SumInvocation(self.call.identity, self.ng, self.call.job.m, self.cols)
                if not bad and s == "sumIssue" and bank_granted else None,
            drain_request=DenseDrainRequest(self.call.job, self.call.identity, self.ng, self.cols)
                if not bad and s == "drainIssue" else None,
            window_result_ready=s in ("partialWait", "draining"),
            drain_result_ready=s in ("drainWait", "draining"),
            sum_bank_granted=bank_granted,
            invalidate_lease=bool(bad or s in ("invalidate", "retire")),
            backend_abort=bool(cancel))

    def _fail(self, status=None):
        self.poison = True
        self.status = self.status or status or "Protocol"
        self.state = "draining"

    def _reply(self, status):
        tag = getattr(getattr(self.call, "job", None), "tag", 0)
        self.result = DenseReductionResult(tag, status, self.write_bytes, None,
                                          self.useful, self.executed, self.model_ticks)
        self.state = "reply"

    def _credit(self, result, *, drain=False):
        try:
            useful, executed = result.useful_macs, result.executed_macs
            written = result.ddr_write_bytes
            if not all(uint(v, 64) for v in (useful, executed, written)):
                raise ValueError("typed actual terminal counters required")
            if not drain and written != 0:
                raise ValueError("K partial cannot credit DDR bytes")
            # Match the physical UInt64 counter registers, without shape totals.
            self.useful = (self.useful + useful) & U64
            self.executed = (self.executed + executed) & U64
            if drain:
                self.write_bytes = (self.write_bytes + written) & U64
            return True
        except (AttributeError, TypeError, ValueError):
            self._fail("Protocol")
            return False

    def _window_exact(self, r, services):
        try:
            fields = ((r.tag, 32), (r.identity, 32), (r.ng, 16), (r.rows, 8),
                      (r.cols, 8), (r.slot, 2), (r.k_begin, 16), (r.k_end, 16),
                      (r.block_id, 32), (r.produced_beats, 11))
            if not all(uint(value, bits) for value, bits in fields) or type(r.pair_reverse) is not bool:
                return False
            return ((r.tag, r.identity, r.ng, r.rows, r.cols, r.slot,
                     r.k_begin, r.k_end, r.block_id, r.pair_reverse) ==
                    (self.call.job.tag, self.call.identity, self.ng, self.call.job.m,
                     self.cols, self.block, *self.call.k_ranges[self.block],
                     self.block + 1, self.call.pair_reverse) and r.committed is True and
                    r.produced_beats == self.call.job.m // 16 * self.cols and
                    r.ddr_write_bytes == 0 and services.lease_valid)
        except (AttributeError, TypeError):
            return False

    def _drain_exact(self, r, services):
        try:
            fields = ((r.tag, 32), (r.identity, 32), (r.ng, 16), (r.rows, 8),
                      (r.cols, 8), (r.consumed_beats, 11))
            if not all(uint(value, bits) for value, bits in fields):
                return False
            return ((r.tag, r.identity, r.ng, r.rows, r.cols) ==
                    (self.call.job.tag, self.call.identity, self.ng, self.call.job.m, self.cols)
                    and r.committed is True and r.consumed_beats == self.call.job.m // 16 * self.cols
                    and r.ddr_write_bytes == self.call.job.m * self.cols * 4
                    and not services.tiles_leased and services.tiles_drained)
        except (AttributeError, TypeError):
            return False

    def tick(self, *, request=None, services=Services(), abort=False, local_reset=False,
             coordinated_reset=None, window_ready=True, drain_ready=True, sum_ready=True,
             window_result=None, drain_result=None, sum_complete=False, result_ready=False):
        abort = abort or local_reset
        p = self.ports(services, abort=abort)
        p.update(request_fire=False, result_fire=False, window_fire=False, drain_fire=False,
                 sum_fire=False, window_result_fire=False, drain_result_fire=False)
        if coordinated_reset is not None:
            if frozenset(coordinated_reset) != RESET_DOMAIN:
                raise ValueError("coordinated reset must flush Host, coordinator, owner, tiles, vector, DMA and Matrix")
            self.__init__()
            return p
        s = self.state
        bad = abort or self.poison or services.error
        live = s not in ("idle", "reply", "locked")
        if live:
            self.model_ticks += 1
        wf = p["window_result_ready"] and window_result is not None
        df = p["drain_result_ready"] and drain_result is not None
        if request is not None and p["request_ready"]:
            p["request_fire"] = True
            self.call = request
            self.ng = self.block = self.model_ticks = 0
            self.write_bytes = self.useful = self.executed = 0
            self.status = None
            try:
                self.call = request.snapshot()
            except (AttributeError, TypeError, ValueError):
                self._fail("Malformed")
            else:
                self.state = "partialFlush"
        if s in ("partialFlush", "drainFlush") and not bad:
            self.state = "partialIssue" if s == "partialFlush" else "drainIssue"
        if p["window_request"] is not None and window_ready:
            p["window_fire"] = True
            self.window_pending = True
            self.state = "partialWait"
        if wf:
            p["window_result_fire"] = True
            pending = self.window_pending
            self.window_pending = False
            valid_credit = self._credit(window_result) if pending else False
            if (not pending or not services.window_busy or df or
                    not valid_credit or getattr(window_result, "status", "Protocol") or
                    not self._window_exact(window_result, services) or bad):
                self._fail(getattr(window_result, "status", None))
            elif s == "partialWait":
                if self.block == 0:
                    self.block, self.state = 1, "partialFlush"
                else:
                    self.state = "sumIssue"
        if p["sum_request"] is not None and sum_ready:
            p["sum_fire"] = True
            self.sum_pending = True
            self.state = "sumWait"
        if sum_complete:
            if s != "sumWait" or not self.sum_pending or bad:
                self._fail()
            elif not services.tiles_drained or not services.vector_drained or not services.owner_retired:
                self._fail()
            else:
                self.sum_pending = False
                self.state = "drainFlush"
        if p["drain_request"] is not None and drain_ready:
            p["drain_fire"] = True
            self.drain_pending = True
            self.state = "drainWait"
        if df:
            p["drain_result_fire"] = True
            pending = self.drain_pending
            self.drain_pending = False
            valid_credit = self._credit(drain_result, drain=True) if pending else False
            if (not pending or not services.drain_busy or wf or not valid_credit or
                    getattr(drain_result, "status", "Protocol") or
                    not self._drain_exact(drain_result, services) or bad):
                self._fail(getattr(drain_result, "status", None))
            elif s == "drainWait":
                if self.ng + self.cols == self.call.job.n:
                    if self.write_bytes == self.call.job.write_bytes:
                        self.state = "invalidate"
                    else:
                        self._fail()
                else:
                    self.ng += self.cols
                    self.block, self.state = 0, "partialFlush"
        if s == "invalidate" and not bad:
            self.state = "retire"
        if s == "retire" and not bad and services.retired and not services.tiles_leased and not services.lease_valid:
            if not (self.window_pending or self.drain_pending or self.sum_pending):
                self._reply(None)
        # An unsolicited terminal cannot become a new job's completion.
        if ((window_result is not None and not wf) or (drain_result is not None and not df)):
            # Fence the current Host acceptance, including a held success.
            p["reset_required"] = p["invalidate_lease"] = True
            if live:
                self._fail()
            else:
                self.poison = True
        if bad and live:
            self._fail()
        if abort or services.error:
            self.poison = True
        if self.poison and self.sum_pending and not services.sum_busy and services.vector_drained and services.tiles_drained:
            self.sum_pending = False
        if (s == "draining" and services.retired and
                not (self.window_pending or self.drain_pending or self.sum_pending)):
            self._reply(self.status or "Protocol")
        if p["result"] is not None and result_ready:
            p["result_fire"] = True
            self.state = "locked" if self.poison or bad else "idle"
        return p
