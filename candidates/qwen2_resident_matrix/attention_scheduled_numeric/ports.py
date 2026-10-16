"""Proposed numerical ports: compute accepted work only, preserve held words.

All storage is host test storage. Timing parameters are hypothetical; no RTL.
"""
from dataclasses import dataclass
from ..attention_scalar_schedule.model import Schedule, Offer


def word(x):
    if type(x) is not int or not 0 <= x < 2**32:
        raise ValueError('FP32 word')
    return x


def finite(x):
    return word(x) & 0x7f800000 != 0x7f800000


@dataclass(frozen=True)
class ScalarResult:
    packet: int
    words: tuple
    error: bool


class ScalarPort:
    def __init__(self, plans, operation, exponential):
        self.schedule = Schedule(plans)
        self.operation, self.exponential = operation, exponential
        self.inputs = None
        self.held = None
        self.calls = 0
        self.trace = []

    def tick(self, *, acquire=None, release=None, offer=None, operands=None,
             ack=None, feed_ready=False, abort=False, soft_reset=False):
        if offer is not None and type(offer) is not Offer:
            raise ValueError('offer identity')
        if operands is not None:
            if type(operands) is not tuple or offer is None or len(operands) != len(offer.lanes):
                raise ValueError('operand packet')
            for pair in operands:
                if type(pair) is not tuple or len(pair) != 2 or not all(finite(x) for x in pair):
                    raise ValueError('finite operands')
        if offer is not None and operands is None:
            raise ValueError('offered payload missing')
        # Metadata may become available one edge before the captured payload.
        # An early ACK must not retire that metadata before computation/capture.
        old = self.held
        effective_ack = ack if old is not None else None
        if ack is not None and (type(ack) is not int or ack < 0):
            raise ValueError('ACK identity')
        out = self.schedule.tick(acquire=acquire, release=release, offer=offer,
            ack=effective_ack, feed_ready=feed_ready, abort=abort, soft_reset=soft_reset)
        if out['offer_fire']:
            self.inputs = operands
        if out['response'] is not None and old is None:
            result = out['response']
            values, bad = [], False
            for index, (a, b) in enumerate(self.inputs):
                self.calls += 1
                try:
                    value = (self.exponential(a) if result.opcode == 'exp'
                             else self.operation(result.opcode, a, b))
                    if not finite(value):
                        raise ValueError('nonfinite result')
                except (ValueError, ArithmeticError):
                    value, bad = 0, True
                values.append(value)
                self.trace.append((result.pool, result.opcode, result.lanes[index], result.indices[index], a, b, value))
            self.held = ScalarResult(result.packet, (0,) * len(values) if bad else tuple(values), bad)
            if bad:
                self.schedule.poison = True
        if out['ack_fire']:
            self.held = None
            self.inputs = None
        out['response'] = old
        out['publish'] = out['publish'] and old is not None and not old.error
        out['reset_required'] = self.schedule.poison
        return out


@dataclass(frozen=True)
class MatrixResult:
    group: int
    words: tuple  # existing16x256 logical output; unselected cells are not modeled
    error: bool


class MatrixPort:
    """One context, one accepted step and one joined held result at a time.

    Only selected dependency cells are numerical. Four contexts, seven metadata
    slots and a second result slot stay unused. Abort cancels unaccepted steps,
    drains accepted work, then produces a poisoned terminal response for ACK.
    That abort control is a proposal, not an existing endpoint equivalence claim.
    """
    def __init__(self, steps, mask, selected, fma, round_bf, *, latency, group):
        if type(steps) is not int or not 1 <= steps <= 128 or type(mask) is not int or mask not in (15,255):
            raise ValueError('group')
        if type(latency) is not int or not 1 <= latency <= 1000 or type(group) is not int or group < 1:
            raise ValueError('hypothetical latency/group identity')
        if type(selected) is not tuple or not selected or any(type(cell) is not tuple or len(cell) != 2 or any(type(x) is not int for x in cell) for cell in selected) or len(set(selected)) != len(selected):
            raise ValueError('selected cells')
        for row, col in selected:
            if type(row) is not int or type(col) is not int or not 0 <= row < 16 or not 0 <= col < (128 if mask == 15 else 256):
                raise ValueError('selected coordinate')
        self.steps, self.mask, self.selected = steps, mask, selected
        self.fma, self.round_bf, self.latency, self.group = fma, round_bf, latency, group
        self.cells = [0] * 4096
        self.pending = self.held = None
        self.cycle = self.accepted = self.returned = self.calls = self.conversions = 0
        self.poison = self.retired = False

    def tick(self, *, payload=None, feed_ready=False, ack=None, abort=False):
        if type(feed_ready) is not bool or type(abort) is not bool:
            raise ValueError('canonical control')
        if ack is not None and (type(ack) is not int or ack < 0):
            raise ValueError('ACK identity')
        if payload is not None:
            if type(payload) is not tuple or len(payload) != 2 or type(payload[0]) is not tuple or type(payload[1]) is not tuple or len(payload[0]) != 16 or len(payload[1]) != 256:
                raise ValueError('Matrix payload')
            if not all(finite(x) for x in payload[0] + payload[1]):
                raise ValueError('finite ingress')
        old_pending, old_held = self.pending, self.held
        fault = self.poison or abort
        ack_fire = old_held is not None and ack == old_held.group
        accepted = False
        if not self.retired and old_pending is None and old_held is None and not fault and self.accepted < self.steps and payload is not None and feed_ready:
            self.pending = (payload, self.cycle + self.latency)
            self.accepted += 1
            accepted = True
        if old_pending is not None and self.cycle >= old_pending[1]:
            original_left, original_right = old_pending[0]
            bad = False
            converted = []
            for value in original_left + original_right:
                self.conversions += 1
                try:
                    value = self.round_bf(value)
                    if not finite(value) or value & 65535:
                        raise ValueError('BF16 ingress conversion')
                except (ValueError, ArithmeticError):
                    value, bad = 0, True
                converted.append(value)
            left, right = converted[:16], converted[16:]
            updates = []
            for row, col in self.selected:
                self.calls += 1
                try:
                    value = self.fma(left[row], right[col], self.cells[row * 256 + col])
                    if not finite(value):
                        raise ValueError('nonfinite FMA result')
                except (ValueError, ArithmeticError):
                    value, bad = 0, True
                updates.append((row * 256 + col, value))
            for index, value in updates:
                self.cells[index] = value
            fault = fault or bad
            self.pending = None
            self.returned += 1
        if not self.retired and self.held is None and self.pending is None and (fault or self.returned == self.steps):
            self.held = MatrixResult(self.group, (0,) * 4096 if fault else tuple(self.cells), fault)
        if ack_fire:
            self.held = None
            self.retired = True
        self.poison = fault
        self.cycle += 1
        return dict(accepted=accepted, response=old_held, ack_fire=ack_fire,
                    publish=ack_fire and not fault and not old_held.error,
                    reset_required=fault, pending_debt=int(self.pending is not None),
                    terminal_debt=int(self.held is not None))
