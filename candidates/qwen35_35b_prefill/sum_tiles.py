"""Explicit destructive two-partial sum through the SAME Vector16 loan.

Derived from dense_block_reduce/sum_tiles.py at main1a59e575. No arithmetic,
private tensor, third slot or new Vector resource exists here. Each old lhs/rhs
response must be accepted before the shared Add request; phase-bound sum RMW
then overwrites only that consumed lhs element. Completion is an internally
sealed sum, never public DDR completion. The parent's drain still owns ACKs.
"""
from dataclasses import dataclass
from .partial_tiles import TileBankModel, BeginOverwrite, Control, Read, Write
from ..qwen2_resident_matrix.dense_block_reduce.sum_tiles import (
    TileSumController, SumRequest, shared_loan_edge as _shared_loan_edge, owner_tile_edge)


def shared_loan_edge(controller, loan, **inputs):
    """Settle a premature coordinated reset as abort at BOTH endpoints.

    The original loan requires an already-drained reset. A held reply must
    first retire under abort, with consistent ready/valid on the controller
    and real loan, before either endpoint can clear its poison.
    """
    reject = bool(inputs.get('coordinated_reset') and
                  (not controller.banks.idle or controller.inflight or
                   not loan.ports()['drained']))
    if reject:
        inputs = dict(inputs, coordinated_reset=False, abort=True)
    edge = _shared_loan_edge(controller, loan, **inputs)
    if reject:
        edge.update(reset=False, reset_rejected=True)
    return edge


@dataclass(frozen=True)
class SumInvocation:
    identity: int
    partial_identity: int
    ng: int
    rows: int
    cols: int
    lhs_slot: int = 0
    rhs_slot: int = 1
    output_slot: int = 0

    @property
    def beats(self):
        return self.rows // 16 * self.cols

    def validate(self):
        BeginOverwrite(self.identity, self.ng, self.rows, self.cols,
                       self.partial_identity, self.partial_identity,
                       self.lhs_slot, self.rhs_slot).validate()
        if type(self.output_slot) is not int or (self.lhs_slot, self.rhs_slot, self.output_slot) != (0,1,0):
            raise ValueError("explicit overwrite lhs0/rhs1 -> sealed sum0 required")


class InplaceSumController(TileSumController):
    def __init__(self, banks, *, bank_tick=None):
        if type(banks) is not TileBankModel:
            raise ValueError("explicit K2048 destructive bank authority required")
        super().__init__(banks, bank_tick=bank_tick)

    def _admitted(self, call, loan_drained):
        try:
            if type(call) is not SumInvocation:
                return False
            call.validate()
        except (ValueError, AttributeError):
            return False
        self.call = call
        return (self.banks.idle and loan_drained and self.banks.overwrite is None and
                all(t.live and t.sealed and t.phase == "partial" and not t.poisoned and
                    (t.identity,t.ng,t.rows,t.cols,t.expected) ==
                    (call.partial_identity,call.ng,call.rows,call.cols,call.beats) and
                    t.produced == t.expected and t.consumed == 0
                    for t in self.banks.tags))

    def _retired(self, loan_drained):
        c, t = self.call, self.banks.tags[0]
        return (self.banks.idle and loan_drained and not self.inflight and
                self.banks.overwrite is None and not self.banks.tags[1].live and
                not self.banks.tags[1].sealed and self.banks.sum_ready and
                t.phase == "sum" and self._matches(t) and
                t.produced == t.expected and t.consumed == 0)

    def _response_exact(self, r, state):
        c = self.call
        if c is None or state not in ("lhsWait", "rhsWait"):
            return False
        lhs = state == "lhsWait"
        return (r.slot,r.identity,r.ng,r.index,getattr(r,"phase",None)) == (
            c.lhs_slot if lhs else c.rhs_slot, c.partial_identity,c.ng,self.index,
            "lhs" if lhs else "rhs")

    def tick(self, *, start=None, loan_ready=False, loan_result=None,
             loan_drained=True, loan_poison=False, bank_ready=True, abort=False,
             coordinated_reset=False):
        if coordinated_reset:
            # Caller must reset the loan/Matrix/iDMA in the same domain too.
            # An accepted RMW/response or Vector result must first retire;
            # reset cannot erase this controller's half-sum obligations.
            if not self.banks.idle or not loan_drained or self.inflight:
                edge = self.tick(loan_ready=False, loan_result=loan_result,
                    loan_drained=loan_drained, loan_poison=loan_poison,
                    bank_ready=False, abort=True)
                return dict(edge, reset=False, reset_rejected=True)
            self.banks.tick(coordinated_reset=True)
            self.state, self.call, self.index = "idle", None, 0
            self.lhs, self.poison, self.reason, self.inflight = None, False, None, False
            return dict(start_fire=False, complete=False, reset=True,
                        request=None, request_fire=False, result_ready=False, result_fire=False)
        state = self.state
        response = self.banks.response
        response_bad = response is not None and not self._response_exact(response, state)
        unexpected = loan_result is not None and not self.inflight
        loan_abort = (abort or self.poison or self.banks.poison or loan_poison or
                      bool(response is not None and response.error))
        # A current arithmetic error must retire on the actual error-result
        # handshake. Feeding it combinationally into abort could suppress the
        # result valid that discovered it. Registered poison stops later work.
        bad = (loan_abort or unexpected or response_bad or
               bool(loan_result is not None and self._bad_result(loan_result)))
        drained_at_edge = self.banks.idle and loan_drained and not self.inflight
        start_fire = (start is not None and state == "idle" and not bad and
                      self.banks.idle and bank_ready and loan_drained)
        complete = state == "retire" and self._retired(loan_drained) and not bad
        control = read = write = request = None
        bank_response_ready = bad or state == "lhsWait" or (state == "rhsWait" and loan_ready)
        if not bad and state == "begin":
            c = self.call
            control = BeginOverwrite(c.identity, c.ng, c.rows, c.cols,
                c.partial_identity, c.partial_identity, c.lhs_slot, c.rhs_slot)
        elif not bad and state == "seal":
            c = self.call
            control = Control(1, c.lhs_slot, c.identity, c.ng, c.rows, c.cols, phase="sum")
        if not bad and state in ("lhsRead", "rhsRead"):
            slot = self.call.lhs_slot if state == "lhsRead" else self.call.rhs_slot
            read = Read(slot, self.call.partial_identity, self.call.ng, self.index,
                        phase="lhs" if state == "lhsRead" else "rhs")
        if not bad and state == "rhsWait" and response is not None:
            request = SumRequest(self.lhs, response.words)
        if not bad and state == "result" and loan_result is not None:
            write = Write(self.call.output_slot, self.call.identity, self.call.ng,
                          self.index, loan_result.words, phase="sum")
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
            self.state = dict(begin="lhsRead", seal="retire")[state]
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
