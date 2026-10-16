"""One16-lane, one-context functional SiLU cycle candidate; not RTL timing.

Default preserves the source wrapper schedule. `microsequence` removes only
primitive request/collect bubbles. Both modes retain every allValid barrier.
"""
from collections import Counter
from dataclasses import dataclass

from ..sfu_microsequence_audit.counter import Counter as DividerCounter, silu_division_class
from .arithmetic import (COEFFICIENTS, LOG2_RECIPROCAL, Primitive, check_sources,
                         exact, finite, primitive, ref_bf, rn, word)


@dataclass(frozen=True)
class Configuration:
    schedule: str = 'legacy_wrapper'
    divider_options: int = 0
    numerical_profile: str = 'LegacyV0'

    def __post_init__(self):
        if type(self.schedule) is not str or self.schedule not in ('legacy_wrapper', 'microsequence'):
            raise ValueError('named source baseline or candidate schedule required')
        if type(self.divider_options) is not int or self.divider_options not in (0, 16):
            raise ValueError('explicit divider configuration0 or16 required')
        if type(self.numerical_profile) is not str or self.numerical_profile not in (
                'LegacyV0', 'Qwen2OfficialBf16V2'):
            raise ValueError('only source-pinned existing numerical profiles')
        if self.schedule == 'legacy_wrapper' and self.divider_options != 0:
            raise ValueError('legacy baseline retains actual options0 allocation')


@dataclass(frozen=True)
class Request:
    tag: int
    gate: tuple
    up: tuple

    def __post_init__(self):
        if type(self.tag) is not int or not 0 <= self.tag < 1 << 64:
            raise ValueError('canonical tag')
        for data in (self.gate, self.up):
            if type(data) is not tuple or len(data) != 16:
                raise ValueError('exactly16 lanes required')
            for bits in data:
                word(bits)


@dataclass(frozen=True)
class Response:
    tag: int
    value: tuple
    error: bool
    aborted: bool
    failed_phase: int | None


class SiluCycleModel:
    """One allocation, at most one accepted vector debt until response ACK.

    tick returns pre-edge pins/events. Arithmetic nodes use old registers and
    capture on that edge. Results produced at edgeN are visible on edgeN+1.
    A divider pulse is captured regardless of response backpressure. No input
    can use a register released by a response ACK on the same edge.
    """
    def __init__(self, configuration=Configuration(), *, arithmetic=primitive):
        if type(configuration) is not Configuration or not callable(arithmetic):
            raise ValueError('configuration and arithmetic callback required')
        check_sources()
        self.configuration, self.arithmetic = configuration, arithmetic
        self.edge = self.accepted = self.retired = 0
        self.request = self.response = None
        self.state = 'idle'
        self.phase = 0
        self.error = self.aborted = False
        self.failed_phase = None
        self.counts = Counter()
        self.trace = []  # observer only, never read by the scheduler/datapath
        self.phase_trace = []
        self.lanes = []
        self.value, self.probability = [0] * 16, [0] * 16
        self.dividers = [DividerCounter(two_bits=configuration.divider_options == 16) for _ in range(16)]
        self.divider_debt = 0
        self._alu_used = set()

    def _node(self, lane, stage, operation, a, b, *, internal=False):
        if not finite(a) or not finite(b):
            result, bad = Primitive(0, 0), True
            self.counts['lane_input_rejection'] += 1
        else:
            if operation != 'div':
                if lane in self._alu_used:
                    raise RuntimeError('more than one existing ALU output per lane/edge')
                self._alu_used.add(lane)
            result = self.arithmetic(operation, a, b)
            if type(result) is not Primitive:
                raise ValueError('callback must return validated Primitive')
            bad = not internal and (bool(result.flags & 30) or not finite(result.bits))
        self.trace.append(dict(edge=self.edge, lane=lane, phase=self.phase, stage=stage,
                               operation=operation, a=a, b=b, bits=result.bits,
                               flags=result.flags, flags_ignored=internal, bad=bad))
        if finite(a) and finite(b):
            self.counts['lane_' + operation] += 1
        self.counts['lane_' + stage] += 1
        return result.bits, bad

    def _start_phase(self):
        self.lanes = []
        for i in range(16):
            self.lanes.append(dict(stage='scale' if self.phase == 0 else 'operation',
                                   done=False, bad=False, out=self.value[i]))
        self.state = 'execute'
        if self.configuration.schedule == 'legacy_wrapper':
            # Original BlockScalarFloat rejects at its request edge, before
            # entering normal/expScale. Faster failed lanes still hold allValid.
            for i, lane in enumerate(self.lanes):
                a, b = self._operands(i)
                if not finite(a) or not finite(b):
                    lane.update(out=0, bad=True, done=True)
                    self.counts['lane_input_rejection'] += 1
            if all(lane['done'] for lane in self.lanes):
                self.state = 'collect'

    def _operands(self, i):
        if self.phase == 0:
            return self.request.gate[i], 0
        if self.phase in (1, 2):
            return 0x3f800000, self.value[i]
        b = (self.probability[i] if self.request.gate[i] >> 31 else 0x3f800000) if self.phase == 3 else (
            self.request.gate[i] if self.phase == 4 else self.request.up[i])
        return self.value[i], b

    def _complete_phase(self):
        raw = tuple(lane['out'] for lane in self.lanes)
        values = raw
        materialize = self.configuration.numerical_profile == 'Qwen2OfficialBf16V2' and self.phase in (4, 5)
        if materialize:
            values = tuple(ref_bf(x) for x in raw)
            self.counts['bf16_lane_materializations'] += 16
        bad = any(lane['bad'] for lane in self.lanes) or (materialize and any(not finite(x) for x in values))
        self.value = list(values)
        if self.phase == 0:
            self.probability = list(raw)
        self.phase_trace.append(dict(edge=self.edge, phase=self.phase, raw=raw,
                                     value=values, error=bad))
        self.counts['phase_barriers'] += 1
        if bad:
            self.error, self.failed_phase = True, self.phase
        if bad or self.phase == 5:
            self._reply()
        else:
            self.phase += 1
            if self.configuration.schedule == 'legacy_wrapper':
                self.state = 'issue'
            else:
                self._start_phase()

    def _reply(self):
        if self.divider_debt:
            raise RuntimeError('response before draining accepted divider requests')
        self.response = Response(self.request.tag, tuple(self.value), self.error,
                                 self.aborted, self.failed_phase)
        self.state = 'reply'

    def _execute(self):
        for i, lane in enumerate(self.lanes):
            if lane['done']:
                self.counts['lane_barrier_hold'] += 1
                continue
            if self.phase == 0:
                self._exp(i, lane)
            elif self.phase == 2:
                self._divide(i, lane)
            else:
                a, b = self._operands(i)
                op = 'add' if self.phase == 1 else 'mul'
                lane['out'], lane['bad'] = self._node(i, 'phase' + str(self.phase), op, a, b)
                lane['done'] = True
        if all(lane['done'] for lane in self.lanes):
            if self.configuration.schedule == 'legacy_wrapper':
                self.state = 'collect'
            else:
                self._complete_phase()

    def _exp(self, i, lane):
        stage = lane['stage']
        gate = self.request.gate[i]
        if stage == 'scale':
            if not finite(gate):
                lane.update(out=0, bad=True, done=True)
                self.counts['lane_input_rejection'] += 1
                return
            lane['z'], _ = self._node(i, 'exp_scale', 'mul', gate & 0x7fffffff,
                                      LOG2_RECIPROCAL, internal=True)
            if gate & 0x7fffffff >= 0x42a00000:
                lane.update(out=0, done=True)
                self.counts['lane_cutoff'] += 1
            else:
                lane['stage'] = 'floor'
        elif stage == 'floor':
            lane.update(k=int(exact(lane['z'])), horner=COEFFICIENTS[7], index=6,
                        stage='fraction')
            self.counts['lane_exp_floor'] += 1
        elif stage == 'fraction':
            lane['fraction'], _ = self._node(i, 'exp_fraction', 'add', lane['z'],
                                             rn(lane['k']) ^ 0x80000000, internal=True)
            lane['stage'] = 'multiply'
        elif stage == 'multiply':
            lane['product'], _ = self._node(i, 'exp_horner_mul', 'mul', lane['horner'],
                                            lane['fraction'], internal=True)
            lane['stage'] = 'add'
        elif stage == 'add':
            lane['horner'], _ = self._node(i, 'exp_horner_add', 'add', lane['product'],
                                           COEFFICIENTS[lane['index']], internal=True)
            if lane['index'] == 0:
                lane['stage'] = 'finish'
            else:
                lane['index'] -= 1
                lane['stage'] = 'multiply'
        elif stage == 'finish':
            lane['out'], _ = self._node(i, 'exp_finish', 'mul', lane['horner'],
                                        (127 - lane['k']) << 23, internal=True)
            lane['done'] = True
        else:
            raise RuntimeError('invalid exp state')

    def _divide(self, i, lane):
        if lane['stage'] == 'operation':
            cls = silu_division_class(self.value[i])
            event = self.dividers[i].tick(valid=True, normal=cls['normal'],
                                           quotient_leading_one=cls['leading'])
            if not event['accepted']:
                raise RuntimeError('single-context divider not ready')
            lane.update(stage='divide_wait', issue_edge=self.edge)
            self.divider_debt += 1
            self.counts['divider_accepts'] += 1
        else:
            event = self.dividers[i].tick()
            if event['result']:
                lane['out'], lane['bad'] = self._node(i, 'divider_return', 'div',
                                                     0x3f800000, self.value[i])
                lane['done'] = True
                self.divider_debt -= 1
                self.counts['divider_returns'] += 1
                self.counts['divider_spacing_' + str(self.edge - lane['issue_edge'])] += 1

    def tick(self, *, request=None, response_ready=False, abort=False):
        if request is not None and type(request) is not Request:
            raise ValueError('validated Request required')
        if type(response_ready) is not bool or type(abort) is not bool:
            raise ValueError('canonical controls required')
        self._alu_used.clear()
        before_divider = self.counts['divider_accepts'], self.counts['divider_returns']
        before_floor = self.counts['lane_exp_floor']
        ready = self.state == 'idle' and not abort
        response = self.response
        accepted = ready and request is not None
        retired = response is not None and response_ready
        if abort and self.request is not None:
            # Cancellation is a sticky sideband, not a mutation of an already
            # offered Decoupled payload. Even abort+ACK suppresses publication.
            self.error = self.aborted = True
        state = self.state
        self.counts['edge_' + state] += 1
        if retired:
            self.retired += 1
            self.response = self.request = None
            self.state = 'idle'
        elif response is not None:
            self.counts['response_stall_edges'] += 1
        elif accepted:
            self.request = request
            self.accepted += 1
            self.phase = 0
            self.error = self.aborted = False
            self.failed_phase = None
            self.value, self.probability = [0] * 16, [0] * 16
            if self.configuration.schedule == 'legacy_wrapper':
                self.state = 'issue'
            else:
                self._start_phase()
        elif self.request is not None:
            if abort:
                self.error = self.aborted = True
                self.state = 'drain'
            if self.state == 'drain':
                # Existing divider has no ready on its return pulse. Drain all
                # accepted requests before exposing the terminal abort response.
                if self.divider_debt:
                    for i, lane in enumerate(self.lanes):
                        if not lane['done'] and lane.get('stage') == 'divide_wait':
                            self._divide(i, lane)
                if not self.divider_debt:
                    self._reply()
            elif self.state == 'issue':
                self._start_phase()
            elif self.state == 'collect':
                self._complete_phase()
            elif self.state == 'execute':
                self._execute()
        self.edge += 1
        debt = self.accepted - self.retired
        if debt not in (0, 1) or debt != int(self.request is not None):
            raise RuntimeError('accepted vector debt invariant')
        if self.divider_debt != self.counts['divider_accepts'] - self.counts['divider_returns']:
            raise RuntimeError('accepted divider debt invariant')
        self.counts['alu_service_edges'] += bool(self._alu_used)
        self.counts['conversion_service_edges'] += self.counts['lane_exp_floor'] != before_floor
        self.counts['divider_issue_edges'] += self.counts['divider_accepts'] != before_divider[0]
        self.counts['divider_return_edges'] += self.counts['divider_returns'] != before_divider[1]
        return dict(edge=self.edge - 1, state=state, request_ready=ready,
                    accepted=accepted, response=response, retired=retired,
                    publish=retired and not response.error and not self.aborted,
                    cancelled=self.aborted and (self.request is not None or response is not None), debt=debt,
                    divider_debt=self.divider_debt)
