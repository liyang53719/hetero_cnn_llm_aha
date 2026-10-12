"""Official-BF16 arithmetic on the existing memory-fed Qwen2 owners.

Only numerical generators differ from the original owners. Their admission,
physical memory requests, ACK/publication fences, poison/reset handling and
shared Scalar/Matrix services are inherited. Wire words remain FP32 containers;
BF16 materialization is a scalar RNE operation, never a packed-dtype flag.

RMS follows the frozen Torch210 CPU V8/ILP4/three-block reduction reviewed in
scripts/qwen2_rms_rope_policy_diagnostic.py. Other boundaries follow the reviewed
v2 isolated C++ recipe: bias follows the unrounded dense result, RoPE rounds
table/products/sums, QK rounds only its completed dot and scaled score, and PV
rounds only its completed output. These software owners do not establish RTL,
physical resource allocation, hardware timing or official acceptance.
"""
from ..ffn_public.prefix_arithmetic import finite, word
from ..ffn_public.prefix_owners import LANES, PrefixFault, PrefixOwner
from ..ffn_attention.attention_owner import AttentionOwner
from ..ffn_attention.scalar_recipe import exp_negative


class OfficialPrefixOwner(PrefixOwner):
    """Existing PrefixOwner with official-BF16 numerical materializations."""

    def _norm(self, j):
        for token in range(j.m):
            row = []
            for col in range(0, self.hidden, LANES):
                row.extend((yield from self._read(j.a + (token * self.hidden + col) * 4)))
                self.row_words = len(row)
                self.peak_row_words = max(self.peak_row_words, len(row))
            # Revisit the existing retained row; do not allocate another row
            # of squares. Each square and reduction edge is one shared scalar
            # RNE node. Independent lanes can be serialized lane-first while
            # retaining exactly the frozen vector recipe's addition graph.
            total = 0
            for lane in range(8):
                lane_sum = 0
                for residue in range(4):
                    residue_sum = 0
                    for block in range(3):
                        partial = 0
                        for term in range(16):
                            x = row[block * 512 + term * 32 + residue * 8 + lane]
                            square = self._op('mul', x, x)
                            partial = self._op('add', partial, square, policy='legacy_scalar')
                        residue_sum = self._op('add', residue_sum, partial, policy='legacy_scalar')
                    lane_sum = self._op('add', lane_sum, residue_sum, policy='legacy_scalar')
                total = self._op('add', total, lane_sum, policy='legacy_scalar')
            mean = self._op('div', total, word(1536.0), policy='legacy_scalar')
            epsilon = self._op('add', mean, word(1e-6), policy='legacy_scalar')
            root = self._op('sqrt', epsilon, policy='legacy_scalar')
            scale = self._op('div', word(1.0), root, policy='legacy_scalar')
            for col in range(0, self.hidden, LANES):
                gamma = yield from self._read(j.b + col * 4)
                scaled = tuple(self._op('bf', self._op('mul', row[col + i], scale))
                               for i in range(LANES))
                output = tuple(self._op('bf', self._op('mul', scaled[i], gamma[i]))
                               for i in range(LANES))
                yield from self._write(j.dst + (token * self.hidden + col) * 4, output)
            self.row_words = 0

    def _bias(self, j):
        for token in range(j.m):
            for col in range(0, j.n, LANES):
                index = (token * j.n + col) * 4
                a = yield from self._read(j.a + index)
                b = yield from self._read(j.b + col * 4)
                # Q/K/V raw dense sums remain FP32 until after bias addition.
                output = tuple(self._op('bf', self._op('add', x, y)) for x, y in zip(a, b))
                yield from self._write(j.dst + index, output)

    def _rope(self, j):
        half = self.head_dim // 2
        for token in range(j.m):
            for head in range(j.n // self.head_dim):
                for col in range(0, half, LANES):
                    index = (token * j.n + head * self.head_dim + col) * 4
                    trig_index = (token * half + col) * 4
                    x = yield from self._read(j.a + index)
                    y = yield from self._read(j.a + index + half * 4)
                    cosine = yield from self._read(j.b + trig_index)
                    sine = yield from self._read(j.c + trig_index)
                    cosine = tuple(self._op('bf', v) for v in cosine)
                    sine = tuple(self._op('bf', v) for v in sine)
                    xc = tuple(self._op('bf', self._op('mul', a, b)) for a, b in zip(x, cosine))
                    ys = tuple(self._op('bf', self._op('mul', a, b)) for a, b in zip(y, sine))
                    low = tuple(self._op('bf', self._op('add', a, b ^ 0x80000000))
                                for a, b in zip(xc, ys))
                    xs = tuple(self._op('bf', self._op('mul', a, b)) for a, b in zip(x, sine))
                    yc = tuple(self._op('bf', self._op('mul', a, b)) for a, b in zip(y, cosine))
                    yield from self._write(j.dst + index, low)
                    high = tuple(self._op('bf', self._op('add', a, b)) for a, b in zip(xs, yc))
                    yield from self._write(j.dst + index + half * 4, high)

    def _add(self, j):
        elements = j.m * j.n
        for base in range(0, elements, 1024):
            count = min(1024, elements - base)
            left, right = [], []
            for offset in range(0, count, LANES):
                left.extend((yield from self._read(j.a + (base + offset) * 4)))
            for offset in range(0, count, LANES):
                right.extend((yield from self._read(j.b + (base + offset) * 4)))
            output = [self._op('bf', self._op('add', a, b, policy='legacy_scalar'))
                      for a, b in zip(left, right)]
            self.peak_add_words = max(self.peak_add_words, len(left) + len(right) + len(output))
            # BF16 rounding can overflow an otherwise finite FP32 sum. Check
            # the complete original tile before issuing any store from it.
            if any(not finite(value) for value in output):
                raise PrefixFault('Numerical', 'nonfinite BF16 Elementwise Add tile')
            for offset in range(0, count, LANES):
                yield from self._write(j.dst + (base + offset) * 4, output[offset:offset + LANES])


class OfficialAttentionOwner(AttentionOwner):
    """Existing causal AttentionOwner with completed-output BF16 boundaries."""

    def _attention(self, j):
        for token in range(j.m):
            for head in range(12):
                kv_head = head // 6
                q = []
                for depth in range(0, 128, 16):
                    q.extend((yield from self._read(j.a + (token * 1536 + head * 128 + depth) * 4)))
                self.row_words = len(q)
                self.peak_row_words = max(self.peak_row_words, len(q))
                scores, maximum = [], 0xff800000
                for key in range(token + 1):
                    for depth in range(0, 128, 16):
                        k = yield from self._read(j.b + (key * 256 + kv_head * 128 + depth) * 4)
                        lanes = yield from self._matrix_step(0x23, q[depth:depth + 16], k,
                            clear=depth == 0, last=depth == 112, steps=8)
                    total = 0
                    for lane in lanes:
                        total = self._op('add', total, lane)
                    # The Matrix's eight FP32 accumulations and 16-stripe fold
                    # are unchanged; BF16 applies only to the completed dot.
                    dot = self._op('bf', total)
                    score = self._op('bf', self._op('mul', dot, 0x3db504f3))
                    scores.append(score)
                    if self._less(maximum, score):
                        maximum = score
                self.peak_score_words = max(self.peak_score_words, len(scores))
                probabilities, total = [], 0
                for score in scores:
                    difference = self._op('add', score, maximum ^ 0x80000000)
                    probability = exp_negative(self.scalar, self, difference)
                    self.counts['exp_negative_requests'] += 1
                    probabilities.append(probability)
                    total = self._op('add', total, probability)
                self.peak_probability_words = max(self.peak_probability_words, len(probabilities))
                inverse = self._op('div', 0x3f800000, total)
                for col in range(0, 128, 16):
                    for key, probability in enumerate(probabilities):
                        probability = self._op('mul', probability, inverse)
                        v = yield from self._read(j.c + (key * 256 + kv_head * 128 + col) * 4)
                        lanes = yield from self._matrix_step(0x24, (probability,) + (0,) * 15, v,
                            clear=key == 0, last=key == token, steps=token + 1)
                    output = tuple(self._op('bf', lane) for lane in lanes)
                    yield from self._write(j.dst + (token * 1536 + head * 128 + col) * 4, output)
                self.row_words = 0
