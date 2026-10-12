"""Default-off block reduction through the existing physical FP32 tile ports.

This controller does no arithmetic. Its request/result port borrows the same
sixteen-lane owner; the parent supplies that owner's ready/valid edges.
Only the lhs sixteen-word hold is new. No SRAM, result tensor, or oracle is
allocated here. Completion denotes a sealed resident tile, never a DDR ACK or
a public Host completion. Model ticks are protocol events, not RTL cycles.
"""
from dataclasses import dataclass
from .k_window_model import window
TileBankModel, Control, Read, Write = window.TileBankModel, window.Control, window.Read, window.Write


@dataclass(frozen=True)
class SumInvocation:
    identity: int
    ng: int
    rows: int
    cols: int
    lhs_slot: int = 0
    rhs_slot: int = 1
    output_slot: int = 2

    @property
    def beats(self):
        return self.rows // 16 * self.cols

    def validate(self):
        if (any(type(x) is not int for x in vars(self).values()) or
                not 0 < self.identity < 2**32 or not 0 <= self.ng < 2**16 or
                self.ng % 32 or self.rows not in (16, 128) or
                self.cols not in (32, 64, 96, 128, 160) or
                sorted((self.lhs_slot, self.rhs_slot, self.output_slot)) != [0, 1, 2]):
            raise ValueError("typed full-tile sum identity/geometry/distinct slots")


@dataclass(frozen=True)
class SumRequest:
    """Same internal loan wires: no invented response transaction tag."""
    gate: tuple
    up: tuple
    binary_add: bool = True


@dataclass(frozen=True)
class SumResponse:
    words: tuple
    error: bool = False


def shared_loan_edge(controller, loan, **inputs):
    """Settle the real abort wires before sampling both ready/valid endpoints.

    The caller owns exclusive bank/Vector grants throughout this transaction.
    Arithmetic stays entirely in the passed existing loan service.
    """
    from .vector_add_model import Request
    response = controller.banks.response
    cancel = (inputs.get('abort', False) or controller.poison or
              controller.banks.poison or loan.ports()['reset_required'] or
              bool(response is not None and response.error))
    port = loan.ports(abort=cancel)
    edge = controller.tick(loan_ready=port['request_ready'], loan_result=port['result'],
        loan_drained=port['drained'], loan_poison=port['reset_required'], **inputs)
    req = edge['request']
    vector = loan.tick(request=None if req is None else Request(req.gate, req.up, req.binary_add),
        result_ready=edge['result_ready'], abort=edge.get('loan_abort', False),
        coordinated_reset=inputs.get('coordinated_reset', False))
    if (edge['request_fire'], edge['result_fire']) != (vector['request_fire'], vector['result_fire']):
        raise RuntimeError('sum and shared loan sampled inconsistent handshake wires')
    return edge


def owner_tile_edge(owner, **ports):
    """One tile-port grant on the existing owner; never clock banks twice.

    No normal job/window/drain request is allowed during this exclusive loan.
    A revoked/inhibited test grant blocks new requests but still retires a
    previously accepted synchronous bank operation.
    """
    grant=ports['owner_quiescent']
    if owner.window_request is not None or owner.drain_request is not None:
        raise ValueError('sum bank loan overlaps a live Dense/drain request')
    edge=owner.tick(tile_control=ports['control'] if grant else None,
        tile_read=ports['read'] if grant else None,tile_write=ports['write'] if grant else None,
        tile_response_ready=ports['response_ready'],abort=ports['abort'],loan_busy=True)
    tile=edge['tile']
    if not grant:
        tile=dict(tile,ctl_ready=False,read_ready=False,write_ready=False)
    return tile


class TileSumController:
    def __init__(self, banks, *, bank_tick=None):
        # The public owner and this borrower share the exact pinned authority.
        # Never allocate replacement SRAM or accept a separately loaded class.
        if not isinstance(banks, TileBankModel):
            raise ValueError("the existing shared physical TileBankModel is required")
        self.banks = banks
        # Optional owner facade clocks the SAME physical tile port, once per
        # edge, while retaining its real owner clock/arbitration bookkeeping.
        self.bank_tick = banks.tick if bank_tick is None else bank_tick
        if not callable(self.bank_tick):
            raise ValueError("actual owner tile-port callback required")
        self.state, self.call, self.index = "idle", None, 0
        self.lhs, self.poison, self.reason = None, False, None
        self.inflight = False
        self.counts = dict(invocations=0, add_requests=0, add_results=0,
                           completed=0, accepted_operand_beats=0, output_beats=0)

    @property
    def busy(self):
        return self.state not in ("idle", "locked")

    def _matches(self, tag):
        c = self.call
        return (tag.identity, tag.ng, tag.rows, tag.cols, tag.expected) == (
            c.identity, c.ng, c.rows, c.cols, c.beats)

    def _admitted(self, call, loan_drained):
        try:
            call.validate()
        except (ValueError, AttributeError):
            return False
        self.call = call
        return (self.banks.idle and loan_drained and
                not self.banks.tags[call.output_slot].live and
                all(t.live and t.sealed and self._matches(t) and
                    t.produced == t.expected and t.consumed == 0
                    for t in (self.banks.tags[call.lhs_slot], self.banks.tags[call.rhs_slot])))

    def _retired(self, loan_drained):
        c = self.call
        t = self.banks.tags[c.output_slot]
        return (self.banks.idle and loan_drained and not self.inflight and
                not self.banks.tags[c.lhs_slot].live and
                not self.banks.tags[c.rhs_slot].live and
                t.live and t.sealed and self._matches(t) and
                t.produced == t.expected and t.consumed == 0)

    @staticmethod
    def _bad_result(result):
        return (result.error or len(result.words) != 16 or
                any(type(x) is not int or not 0 <= x < 2**32 or
                    x & 0x7f800000 == 0x7f800000 for x in result.words))

    def tick(self, *, start=None, loan_ready=False, loan_result=None,
             loan_drained=True, loan_poison=False, bank_ready=True, abort=False,
             coordinated_reset=False):
        if coordinated_reset:
            # Caller must reset the loan/Matrix/iDMA in the same domain too.
            self.banks.tick(coordinated_reset=True)
            self.state, self.call, self.index = "idle", None, 0
            self.lhs, self.poison, self.reason, self.inflight = None, False, None, False
            return dict(start_fire=False, complete=False, reset=True,
                        request=None, request_fire=False, result_ready=False, result_fire=False)
        state = self.state
        response = self.banks.response
        unexpected = loan_result is not None and not self.inflight
        loan_abort = (abort or self.poison or self.banks.poison or loan_poison or
                      bool(response is not None and response.error))
        # A current arithmetic error must retire on the actual error-result
        # handshake. Feeding it combinationally into abort could suppress the
        # result valid that discovered it. Registered poison stops later work.
        bad = (loan_abort or unexpected or
               bool(loan_result is not None and self._bad_result(loan_result)))
        drained_at_edge = self.banks.idle and loan_drained and not self.inflight
        start_fire = (start is not None and state == "idle" and not bad and
                      self.banks.idle and bank_ready and loan_drained)
        complete = state == "retire" and self._retired(loan_drained) and not bad
        control = read = write = request = None
        bank_response_ready = bad or state == "lhsWait" or (state == "rhsWait" and loan_ready)
        if not bad and state in ("begin", "seal", "releaseLhs", "releaseRhs"):
            slot = (self.call.lhs_slot if state == "releaseLhs" else
                    self.call.rhs_slot if state == "releaseRhs" else self.call.output_slot)
            control = Control(0 if state == "begin" else 1 if state == "seal" else 2,
                              slot, self.call.identity, self.call.ng,
                              self.call.rows, self.call.cols)
        if not bad and state in ("lhsRead", "rhsRead"):
            slot = self.call.lhs_slot if state == "lhsRead" else self.call.rhs_slot
            read = Read(slot, self.call.identity, self.call.ng, self.index)
        if not bad and state == "rhsWait" and response is not None:
            request = SumRequest(self.lhs, response.words)
        if not bad and state == "result" and loan_result is not None:
            write = Write(self.call.output_slot, self.call.identity, self.call.ng,
                          self.index, loan_result.words)
        edge = self.bank_tick(control=control, read=read, write=write,
                               response_ready=bank_response_ready, abort=bad,
                               owner_quiescent=bank_ready)
        request_fire = request is not None and loan_ready and edge["response_fire"]
        result_ready = bad or (state == "result" and edge["write_ready"])
        result_fire = loan_result is not None and result_ready
        if start_fire:
            self.counts["invocations"] += 1
            self.index, self.call = 0, start
            if self._admitted(start, loan_drained):
                self.state = "begin"
            else:
                bad = True
                self.reason = self.reason or "sum admission/lease mismatch"
        if edge["ctl_fire"]:
            self.state = dict(begin="lhsRead", seal="releaseLhs",
                              releaseLhs="releaseRhs", releaseRhs="retire")[state]
        if edge["read_fire"]:
            self.state = "lhsWait" if state == "lhsRead" else "rhsWait"
        if edge["response_fire"] and not bad:
            self.counts["accepted_operand_beats"] += 1
            if state == "lhsWait":
                self.lhs, self.state = edge["response"].words, "rhsRead"
        if request_fire:
            self.inflight = True
            self.counts["add_requests"] += 1
            self.state = "result"
        if result_fire:
            self.inflight = False
            self.counts["add_results"] += 1
        if (state == "drain" or bad) and loan_drained:
            # Abort may suppress the external result while the loan retires
            # it internally. Trust its explicit drained fence, never a timer.
            self.inflight = False
        if edge["write_fire"] and not bad and not self.banks.poison:
            self.index += 1
            self.counts["output_beats"] += 1
            self.state = "seal" if self.index == self.call.beats else "lhsRead"
        if state == "retire":
            if complete:
                self.counts["completed"] += 1
                self.state = "idle"
            else:
                bad = True
                self.reason = self.reason or "sum completion before retirement"
        if bad or self.banks.poison:
            self.poison = True
            self.reason = self.reason or ("unexpected loan result" if unexpected else "sum abort/error")
            self.state = "locked" if state in ("idle", "locked") else "drain"
        if (state == "drain" or bad or self.banks.poison) and drained_at_edge:
            self.state = "locked"
        return dict(bank=edge, start_fire=start_fire, complete=complete,
                    request=request, request_fire=request_fire, result_ready=result_ready,
                    result_fire=result_fire, loan_abort=loan_abort,
                    state=self.state, reset_required=self.poison or self.banks.poison)

