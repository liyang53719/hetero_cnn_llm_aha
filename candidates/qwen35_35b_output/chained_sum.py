"""Four-partial left fold using the same two-slot bank and Vector16 loan.

This source explicitly specializes the original destructive sum controller's
identity/phase selection. SRAM timing, Add request/result retirement, poison,
held responses and abort/reset drain keep the original lifecycle. Completion
is an internal sealed sum; the caller's final drain still owns public DDR ACKs.
"""
from dataclasses import dataclass

from ..qwen35_35b_prefill import sum_tiles as original
from .chained_tiles import ChainedTileBankModel, BeginOverwrite, Control, Read, Write

shared_loan_edge, owner_tile_edge = original.shared_loan_edge, original.owner_tile_edge
SumRequest = original.SumRequest


@dataclass(frozen=True)
class SumInvocation:
    identity: int
    lhs_identity: int
    rhs_identity: int
    ng: int
    rows: int
    cols: int
    lhs_phase: str = 'partial'
    lhs_slot: int = 0
    rhs_slot: int = 1
    output_slot: int = 0

    @property
    def beats(self):
        return self.rows // 16 * self.cols

    def begin(self):
        return BeginOverwrite(self.identity, self.ng, self.rows, self.cols,
                              self.lhs_identity, self.rhs_identity,
                              self.lhs_slot, self.rhs_slot, lhs_phase=self.lhs_phase)

    def validate(self):
        self.begin().validate()
        if type(self.output_slot) is not int or self.output_slot != 0:
            raise ValueError('chained left fold must overwrite physical lhs slot0')


class LegacyInplaceSumController(original.InplaceSumController):
    """Original upstream partial+partial arithmetic on the SAME new wrapper.

    Only constructor authority is extended. Inherited exact original
    SumInvocation, two-partial admission, default BeginOverwrite and lifecycle
    remain unchanged; sum-phase inputs stay forbidden.
    """
    def __init__(self, banks, *, bank_tick=None):
        if type(banks) is not ChainedTileBankModel:
            raise ValueError('explicit chained bank wrapper required for legacy adapter')
        original.TileSumController.__init__(self, banks, bank_tick=bank_tick)


class ChainedSumController(original.TileSumController):
    def __init__(self, banks, *, bank_tick=None):
        if type(banks) is not ChainedTileBankModel:
            raise ValueError('explicit chained two-slot bank authority required')
        super().__init__(banks, bank_tick=bank_tick)

    def _admitted(self, call, loan_drained):
        try:
            if type(call) is not SumInvocation:
                return False
            call.validate()
        except (ValueError, AttributeError, TypeError):
            return False
        self.call = call
        return loan_drained and self.banks.accepts_overwrite(call.begin())

    def _retired(self, loan_drained):
        c, t, lineage = self.call, self.banks.tags[0], self.banks.lineage
        return (self.banks.idle and loan_drained and not self.inflight
                and self.banks.overwrite is None and not self.banks.tags[1].live
                and not self.banks.tags[1].sealed and self.banks.sum_ready
                and t.phase == 'sum' and self._matches(t)
                and t.produced == t.expected and t.consumed == 0
                and lineage is not None and lineage.identity == c.identity
                and (lineage.ng, lineage.rows, lineage.cols) == (c.ng, c.rows, c.cols))

    def _response_exact(self, response, state):
        c = self.call
        if c is None or state not in ('lhsWait', 'rhsWait'):
            return False
        lhs = state == 'lhsWait'
        return (response.slot, response.identity, response.ng, response.index,
                getattr(response, 'phase', None)) == (
            c.lhs_slot if lhs else c.rhs_slot,
            c.lhs_identity if lhs else c.rhs_identity, c.ng, self.index,
            'lhs' if lhs else 'rhs')

    def tick(self, *, start=None, loan_ready=False, loan_result=None,
             loan_drained=True, loan_poison=False, bank_ready=True, abort=False,
             coordinated_reset=False):
        if coordinated_reset:
            if not self.banks.idle or not loan_drained or self.inflight:
                edge = self.tick(loan_ready=False, loan_result=loan_result,
                    loan_drained=loan_drained, loan_poison=loan_poison,
                    bank_ready=False, abort=True)
                return dict(edge, reset=False, reset_rejected=True)
            self.banks.tick(coordinated_reset=True)
            self.state, self.call, self.index = 'idle', None, 0
            self.lhs, self.poison, self.reason, self.inflight = None, False, None, False
            return dict(start_fire=False, complete=False, reset=True,
                        request=None, request_fire=False, result_ready=False, result_fire=False)
        state = self.state
        response = self.banks.response
        response_bad = response is not None and not self._response_exact(response, state)
        unexpected = loan_result is not None and not self.inflight
        loan_abort = (abort or self.poison or self.banks.poison or loan_poison or
                      bool(response is not None and response.error))
        # A newly observed Add error must retire on its actual result edge;
        # do not suppress that result by combinationally aborting its loan.
        bad = (loan_abort or unexpected or response_bad or
               bool(loan_result is not None and self._bad_result(loan_result)))
        drained_at_edge = self.banks.idle and loan_drained and not self.inflight
        start_fire = (start is not None and state == 'idle' and not bad and
                      self.banks.idle and bank_ready and loan_drained)
        complete = state == 'retire' and self._retired(loan_drained) and not bad
        control = read = write = request = None
        bank_response_ready = bad or state == 'lhsWait' or (state == 'rhsWait' and loan_ready)
        if not bad and state == 'begin':
            control = self.call.begin()
        elif not bad and state == 'seal':
            c = self.call
            control = Control(1, c.lhs_slot, c.identity, c.ng, c.rows, c.cols, phase='sum')
        if not bad and state in ('lhsRead', 'rhsRead'):
            lhs = state == 'lhsRead'
            c = self.call
            read = Read(c.lhs_slot if lhs else c.rhs_slot,
                        c.lhs_identity if lhs else c.rhs_identity, c.ng, self.index,
                        phase='lhs' if lhs else 'rhs')
        if not bad and state == 'rhsWait' and response is not None:
            request = SumRequest(self.lhs, response.words)
        if not bad and state == 'result' and loan_result is not None:
            write = Write(self.call.output_slot, self.call.identity, self.call.ng,
                          self.index, loan_result.words, phase='sum')
        edge = self.bank_tick(control=control, read=read, write=write,
                              response_ready=bank_response_ready, abort=bad,
                              owner_quiescent=bank_ready)
        request_fire = request is not None and loan_ready and edge['response_fire']
        result_ready = bad or (state == 'result' and edge['write_ready'])
        result_fire = loan_result is not None and result_ready
        if start_fire:
            self.counts['invocations'] += 1
            self.index, self.call = 0, start
            if self._admitted(start, loan_drained):
                self.state = 'begin'
            else:
                bad = True
                self.reason = self.reason or 'chained sum admission/lease mismatch'
        if edge['ctl_fire']:
            self.state = dict(begin='lhsRead', seal='retire')[state]
        if edge['read_fire']:
            self.state = 'lhsWait' if state == 'lhsRead' else 'rhsWait'
        if edge['response_fire'] and not bad:
            self.counts['accepted_operand_beats'] += 1
            if state == 'lhsWait':
                self.lhs, self.state = edge['response'].words, 'rhsRead'
        if request_fire:
            self.inflight = True
            self.counts['add_requests'] += 1
            self.state = 'result'
        if result_fire:
            self.inflight = False
            self.counts['add_results'] += 1
        if (state == 'drain' or bad) and loan_drained:
            self.inflight = False
        if edge['write_fire'] and not bad and not self.banks.poison:
            self.index += 1
            self.counts['output_beats'] += 1
            self.state = 'seal' if self.index == self.call.beats else 'lhsRead'
        if state == 'retire':
            if complete:
                self.counts['completed'] += 1
                self.state = 'idle'
            else:
                bad = True
                self.reason = self.reason or 'chained sum completion before retirement'
        if bad or self.banks.poison:
            self.poison = True
            self.reason = self.reason or ('unexpected loan result' if unexpected else 'chained sum abort/error')
            self.state = 'locked' if state in ('idle', 'locked') else 'drain'
        if (state == 'drain' or bad or self.banks.poison) and drained_at_edge:
            self.state = 'locked'
        return dict(bank=edge, start_fire=start_fire, complete=complete,
                    request=request, request_fire=request_fire, result_ready=result_ready,
                    result_fire=result_fire, loan_abort=loan_abort,
                    state=self.state, reset_required=self.poison or self.banks.poison)
