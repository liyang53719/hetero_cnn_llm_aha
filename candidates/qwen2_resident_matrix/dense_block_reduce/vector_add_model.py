"""Bounded software protocol model of the explicitly enabled vector Add loan.

This is an owner arithmetic submechanism, not a bank/Dense connection or RTL
simulation. Lane returns and backpressure are independently supplied by tests;
model ticks are not hardware cycles. Add arithmetic reuses existing NumPy FP32
primitives, compared separately against the independent rational FP32 reference.
"""
from dataclasses import dataclass

from ..ffn_public import prefix_arithmetic as fp

LANES = 16
ZERO = (0,) * LANES


@dataclass(frozen=True)
class Request:
    gate: tuple[int, ...]
    up: tuple[int, ...]
    binary_add: bool = True


@dataclass(frozen=True)
class LaneReply:
    value: int
    flags: int = 0
    rejected: bool = False

    @property
    def error(self):
        # BlockScalarFloat Add: NV/DZ/OF/UF fatal, NX alone accepted.
        return self.rejected or bool(self.flags & 0b11110) or not fp.finite(self.value)


@dataclass(frozen=True)
class Result:
    words: tuple[int, ...]
    error: bool


def add_lane(a, b):
    """Existing scalar Add policy, including exact gradual subnormal results.

    Finite FP32 addition cannot generate inexact underflow: a tiny sum is an
    exact multiple of 2^-149. Injected UF responses still must be rejected.
    """
    if any(type(x) is not int or not 0 <= x < 1 << 32 for x in (a, b)):
        raise ValueError('Add operands must be FP32 words')
    if not fp.finite(a) or not fp.finite(b):
        return LaneReply(0, rejected=True)
    with fp.np.errstate(all='ignore'):
        result = fp.word(fp.np.add(fp.value(a), fp.value(b), dtype=fp.np.float32))
    flags = 0b00101 if not fp.finite(result) else 0
    if fp.finite(result) and fp.tiny_inexact('add', a, b, result):
        flags |= 0b00011
    return LaneReply(result, flags)


class VectorLoanModel:
    """Enabled-only loan control with the same single shared vector lifecycle.

    A legacy SiLU request can exercise the original six-phase dispatch, but its
    primitive arithmetic is externally supplied, not reimplemented here. Policy
    materialization is modeled only at the original SiLU phases 4 and 5.
    """
    def __init__(self, *, official_bf16=False, auto_respond=True, lane_latency=2):
        if type(lane_latency) is not int or lane_latency < 1:
            raise ValueError("positive injected lane latency required")
        self.official_bf16 = official_bf16
        self.auto_respond = auto_respond
        self.lane_latency = lane_latency
        self.reset()

    def reset(self):
        self.state = 'idle'
        self.input = None
        self.phase = 0
        self.value = ZERO
        self.probability = ZERO
        self.error = False
        self.poison = False
        self.active = False
        self.replies = {}
        self.pending = {}
        self.issued = []
        self.published = []

    def operands(self):
        r, p = self.input, self.phase
        if r.binary_add:
            return tuple(('add', a, b) for a, b in zip(r.gate, r.up))
        result = []
        for i in range(LANES):
            if p == 0:
                item = ('exp_negative', r.gate[i], 0)
            elif p == 1:
                item = ('add', 0x3f800000, self.value[i])
            elif p == 2:
                item = ('div', 0x3f800000, self.value[i])
            elif p == 3:
                item = ('mul', self.value[i], self.probability[i] if r.gate[i] >> 31 else 0x3f800000)
            elif p == 4:
                item = ('mul', self.value[i], r.gate[i])
            else:
                item = ('mul', self.value[i], r.up[i])
            result.append(item)
        return tuple(result)

    def ports(self, *, owner_idle=True, abort=False):
        # Registered poison may feed borrower abort. Current result.error must
        # instead be consumed on its actual handshake and poison the next edge.
        ready = owner_idle and not self.active and not self.poison and not abort and self.state == 'idle'
        visible = self.active and self.state == 'reply' and not self.poison and not abort
        result = Result(ZERO if self.error else self.value, self.error) if visible else None
        return {'request_ready': ready, 'result_valid': visible,
                'result': result, 'words': result.words if result else ZERO,
                'error': result.error if result else False,
                'busy': self.active or self.poison or abort, 'drained': not self.active,
                'reset_required': self.poison}

    def tick(self, *, request=None, owner_idle=True, core_ready=None,
             lane_returns=None, result_ready=False, abort=False,
             coordinated_reset=False):
        """Return edge-before outputs/fires, then update the single live loan.

        Automatic Add completion is a software backend behind the lane request
        handshake. Manual mode allows independently timed or faulty lane replies.
        A caller never supplies a reference tensor as an owner result.
        """
        if coordinated_reset:
            self.reset()
            return {**self.ports(), 'request_fire': False, 'result_fire': False, 'issued': None}
        state = self.state
        ports = self.ports(owner_idle=owner_idle, abort=abort)
        request_fire = ports['request_ready'] and request is not None
        result_fire = ports['result_valid'] and result_ready
        issued = None
        if request_fire:
            if len(request.gate) != LANES or len(request.up) != LANES:
                raise ValueError('exactly sixteen lanes required')
            self.input = Request(tuple(request.gate), tuple(request.up), bool(request.binary_add))
            self.active, self.state, self.phase, self.error = True, 'issue', 0, False
        if state == 'issue' and all(core_ready if core_ready is not None else [True] * LANES):
            issued = self.operands()
            self.issued.append(issued)
            self.state = 'wait'
            if self.auto_respond:
                if not self.input.binary_add:
                    raise ValueError('legacy SiLU needs externally supplied primitive replies')
                self.pending = {i: (self.lane_latency, add_lane(a, b))
                                for i, (_, a, b) in enumerate(issued)}
        if state == 'wait' and self.auto_respond:
            if lane_returns:
                raise ValueError('cannot mix automatic and injected lane returns')
            lane_returns = {}
            for i, (delay, reply) in list(self.pending.items()):
                if delay == 1:
                    lane_returns[i] = reply
                    del self.pending[i]
                else:
                    self.pending[i] = (delay - 1, reply)
        if lane_returns:
            if state != 'wait':
                raise ValueError('lane return without an accepted operation')
            if any(i in self.replies or not 0 <= i < LANES for i in lane_returns):
                raise ValueError('duplicate or invalid lane reply')
            self.replies.update(lane_returns)
        if state == 'wait' and len(self.replies) == LANES:
            replies = tuple(self.replies[i] for i in range(LANES))
            materialize = self.official_bf16 and self.phase in (4, 5)
            self.value = tuple(fp.bf(r.value) if materialize else r.value for r in replies)
            bad = any(r.error for r in replies) or any(not fp.finite(x) for x in self.value)
            if self.phase == 0:
                self.probability = tuple(r.value for r in replies)
            self.error |= bad
            self.replies = {}
            if bad or self.input.binary_add or self.phase == 5:
                self.state = 'reply'
            else:
                self.phase += 1
                self.state = 'issue'
        # Abort takes precedence over public result fire, but accepted arithmetic
        # still runs to completion and drains without requiring borrower ready.
        if self.active and state == 'reply' and (result_ready or self.poison or abort):
            if result_fire:
                self.published.append(ports['result'])
            self.poison |= self.error
            self.active, self.state = False, 'idle'
        self.poison |= abort
        return {**ports, 'request_fire': request_fire, 'issued': issued, 'result_fire': result_fire}
