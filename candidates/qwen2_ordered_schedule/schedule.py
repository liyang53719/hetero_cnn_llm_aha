"""Opt-in model schedule for the selected production QK16 Scala postimage.

One Attention job carries its complete prefill length. Token/head/key loops are
operator loops inside that job, not repeated M1 block invocations. Numerical
admission and whole-transport/Scala equivalence remain unqualified.
"""
from ..attention_packed_owner.schedule import PackedSchedule
from ..attention_packed_owner.client import PackedRequest, PackedConsumerAck
from ..ffn_attention.scalar_recipe import exp_negative
from ..ffn_public.prefix_arithmetic import ArithmeticFault, finite
from ..ffn_public.prefix_owners import PrefixFault
from .ordered_work import OrderedFoldWork, OrderedRetired


class ProductionQk16Schedule(PackedSchedule):
    """Packed QK only; keep the official per-head softmax and legacy PV tail."""
    def __init__(self, *, ordered_fold=False):
        if type(ordered_fold) is not bool:
            raise ValueError('ordered_fold must be an explicit Boolean')
        self.ordered_fold = ordered_fold
        super().__init__()
        self.active_qk_keys = 0

    @staticmethod
    def validate_length(length):
        if type(length) is not int or not 1 <= length <= 128:
            raise PrefixFault('Bounds', 'selected production QK16 Attention requires 1<=M<=128')

    def run(self, o, j):
        self.validate_length(j.m)
        for token in range(j.m):
            for head in range(12):
                kv_head = head // 6
                q = []
                for depth in range(0, 128, 16):
                    q.extend((yield from o._read(j.a + (token * 1536 + head * 128 + depth) * 4)))
                o.row_words = len(q)
                o.peak_row_words = max(o.peak_row_words, len(q))
                scores, maximum = [], 0xff800000
                for first in range(0, token + 1, 16):
                    count = min(16, token + 1 - first)
                    self.active_qk_keys = count
                    for depth in range(0, 128, 16):
                        b = [0] * 256
                        for local in range(count):
                            key = first + local
                            k = yield from o._read(j.b + (key * 256 + kv_head * 128 + depth) * 4)
                            b[16 * local:16 * local + 16] = [o._op('bf', x) >> 16 for x in k]
                        final = depth == 112
                        result = yield PackedRequest(0x23,
                            tuple(o._op('bf', x) >> 16 for x in q[depth:depth + 16]),
                            tuple(b), depth == 0, final, 8, 255,
                            tuple((r, 16 * local + r) for local in range(count)
                                  for r in range(16)) if final else ())
                    if self.ordered_fold:
                        # Consumer-owned progression; no ScalarService requests.
                        work = OrderedFoldWork(result, count, maximum)
                        for local in range(count):
                            retired = yield work
                            if not work.consume(retired, local):
                                raise PrefixFault('Protocol', 'foreign, early or unordered fold retirement')
                            if retired.error:
                                raise ArithmeticFault('ordered QK strict arithmetic fault at key %d' % local)
                            score = retired.score
                            scores.append(score)
                            maximum = retired.maximum
                    else:
                        # Read/check one live selected key at a time, like attPackedSelect.
                        # Do not call selected_words(): it checks/copies the entire tile.
                        for local in range(count):
                            lanes = tuple(result.value[r][16 * local + r] for r in range(16))
                            if any(not finite(x) for x in lanes):
                                raise ArithmeticFault('selected production QK16 nonfinite lane')
                            total = 0
                            for lane in lanes:
                                total = o._op('add', total, lane)
                            dot = o._op('bf', total)
                            if not finite(dot):
                                raise ArithmeticFault('selected production QK16 nonfinite materialized dot')
                            score = o._op('bf', o._op('mul', dot, 0x3db504f3))
                            if not finite(score):
                                raise ArithmeticFault('selected production QK16 nonfinite materialized score')
                            scores.append(score)
                            if o._less(maximum, score):
                                maximum = score
                    # Resume only after the same client's result/done/response drain.
                    yield PackedConsumerAck(result.tag)
                self.active_qk_keys = 0
                o.peak_score_words = max(o.peak_score_words, len(scores))
                probabilities, total = [], 0
                for score in scores:
                    difference = o._op('add', score, maximum ^ 0x80000000)
                    probability = exp_negative(o.scalar, o, difference)
                    o.counts['exp_negative_requests'] += 1
                    probabilities.append(probability)
                    total = o._op('add', total, probability)
                o.peak_probability_words = max(o.peak_probability_words, len(probabilities))
                inverse = o._op('div', 0x3f800000, total)
                for col in range(0, 128, 16):
                    for key, probability in enumerate(probabilities):
                        probability = o._op('mul', probability, inverse)
                        v = yield from o._read(j.c + (key * 256 + kv_head * 128 + col) * 4)
                        lanes = yield from o._matrix_step(0x24, (probability,) + (0,) * 15, v,
                            clear=key == 0, last=key == token, steps=token + 1)
                    output = tuple(o._op('bf', lane) for lane in lanes)
                    yield from o._write(j.dst + (token * 1536 + head * 128 + col) * 4, output)
                o.row_words = 0
