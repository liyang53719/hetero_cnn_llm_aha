"""Cold exact-word tests for the separate behavioral Attention batching candidate.

The original owner's generator and Matrix input adapter are executed from their
unchanged ASTs, with physical-address reads and exact Fraction arithmetic. Only
those source definitions are loaded: no tensor package, native library, Matrix
service, public inference payload, RTL simulator, or compiler is imported/run.
These tests establish the selected useful arithmetic and packing schedule, not
handshake equivalence, physical implementation, or hardware performance.
"""
import ast
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
import random
import struct
from types import SimpleNamespace
import unittest

from . import model as candidate

ROOT = Path(__file__).resolve().parents[3]
PREFIX_TEST = ROOT / 'candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py'
PREFIX_OWNER = ROOT / 'candidates/qwen2_resident_matrix/ffn_public/prefix_owners.py'
ORIGINAL = ROOT / 'candidates/qwen2_resident_matrix/official_bf16/owners.py'
ATTENTION = ROOT / 'candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py'
SCALAR = ROOT / 'candidates/qwen2_resident_matrix/ffn_attention/scalar_recipe.py'


def source_definitions(path, names, namespace, *, class_name=None):
    """Execute only named reviewed definitions, with no source module imports."""
    tree = ast.parse(path.read_text(), filename=str(path))
    body = tree.body
    if class_name is not None:
        classes = [node for node in body if isinstance(node, ast.ClassDef)
                   and node.name == class_name]
        if len(classes) != 1:
            raise AssertionError('original source class missing: ' + class_name)
        body = classes[0].body
    found = []
    for node in body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            # Binding is supplied by the harness; the function body is intact.
            node.decorator_list = []
            found.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in names
                for target in node.targets):
            found.append(node)
    if len(found) != len(names):
        raise AssertionError('named original source definitions missing')
    exec(compile(ast.Module(body=found, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


# Reuse the existing independent integer quotient/remainder RNE helpers without
# importing the surrounding NumPy/native test harness.
_rational = source_definitions(PREFIX_TEST,
    ('exact', 'rn', 'ref_add', 'ref_mul', 'ref_div', 'ref_bf'),
    {'Fraction': Fraction, 'lru_cache': lru_cache})
exact, rn, ref_add, ref_mul, ref_div, ref_bf = (
    _rational[name] for name in ('exact', 'rn', 'ref_add', 'ref_mul', 'ref_div', 'ref_bf'))
exact = lru_cache(maxsize=32768)(exact)
_rational['exact'] = exact


def finite(word):
    return word & 0x7f800000 != 0x7f800000


def ref_fma(a, b, accumulator):
    product = exact(a) * exact(b)
    previous = exact(accumulator)
    negative_zero = (not product and not previous and
                     bool((a ^ b) >> 31) and bool(accumulator >> 31))
    return rn(product + previous, negative_zero)


class ArithmeticFault(ValueError):
    pass


class PrefixFault(ValueError):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail
        super().__init__(detail)


class ExactScalar:
    """Cold scalar adapter; every source node gets one exact binary32 rounding."""
    def __init__(self, client=None):
        self.client = client
        self.calls = Counter()
        self.trace = []

    def op(self, client, operation, a, b=0, *, policy='legacy_scalar'):
        if self.client is not client:
            raise AssertionError('scalar ownership mismatch')
        if policy not in ('legacy_scalar', 'vector'):
            raise AssertionError('unexpected scalar policy')
        self.calls[operation] += 1
        if operation == 'bf':
            result = ref_bf(a)
        else:
            if not finite(a) or not finite(b):
                raise ArithmeticFault('nonfinite scalar input')
            if operation == 'add':
                mathematical, result = exact(a) + exact(b), ref_add(a, b)
            elif operation == 'mul':
                mathematical, result = exact(a) * exact(b), ref_mul(a, b)
            elif operation == 'div':
                mathematical, result = exact(a) / exact(b), ref_div(a, b)
            else:
                raise AssertionError('unexpected scalar operation ' + operation)
            if policy == 'legacy_scalar':
                if not finite(result):
                    raise ArithmeticFault('nonfinite scalar result')
                if not result & 0x7f800000 and exact(result) != mathematical:
                    raise ArithmeticFault('inexact scalar underflow')
        self.trace.append((operation, a, b, result, policy))
        return result

    def __call__(self, operation, a, b=0):
        return self.op(self.client, operation, a, b)


_scalar_source = source_definitions(SCALAR,
    ('EXP_COEFFICIENTS', 'LOG2_RECIPROCAL', 'exp_negative'),
    {'ArithmeticFault': ArithmeticFault, 'finite': finite, 'value': exact,
     'word': lambda value: rn(Fraction(value))})
exp_negative = _scalar_source['exp_negative']


@dataclass(frozen=True)
class LegacyRequest:
    opcode: int
    a: tuple
    b: tuple
    clear: bool
    last: bool
    steps: int


class SelectedMatrix:
    """Original adapter's selected cells only; unselected cells cannot be read."""
    def __init__(self, opcode, lanes):
        self.opcode, self.lanes = opcode, tuple(lanes)

    def __getitem__(self, row):
        outer = self
        class Row:
            def __getitem__(self, col):
                if not 0 <= col < 16 or row != (col if outer.opcode == 0x23 else 0):
                    raise AssertionError('original adapter read an unmodeled cell')
                return outer.lanes[col]
        return Row()


class OriginalSchedule:
    """Drive the actual source generator; memory is a small synthetic fixture."""
    def __init__(self, tokens, q, k, v):
        self.job = SimpleNamespace(m=tokens, a=0x100000, b=0x200000,
                                   c=0x300000, dst=0x400000)
        self.sources = ((self.job.a, tuple(q)), (self.job.b, tuple(k)),
                        (self.job.c, tuple(v)))
        self.scalar = ExactScalar(self)
        self.counts = Counter()
        self.row_words = self.peak_row_words = self.peak_score_words = 0
        self.peak_probability_words = self.useful_macs = 0
        self.requests, self.reads, self.writes = [], [], []
        self.output = [None] * (tokens * 1536)
        self.accumulator = None

    def _op(self, operation, a, b=0, *, policy='legacy_scalar'):
        return self.scalar.op(self, operation, a, b, policy=policy)

    def _response(self, request):
        if isinstance(request, LegacyRequest):
            self.requests.append(request)
            if len(request.a) != 16 or len(request.b) != 256 or any(request.b[16:]):
                raise AssertionError('original Matrix packet layout changed')
            if request.opcode not in (0x23, 0x24):
                raise AssertionError('unexpected original Matrix opcode')
            if any(type(word) is not int or not 0 <= word < 1 << 16
                   for word in request.a + request.b):
                raise AssertionError('original Matrix input is not BF16')
            if request.clear:
                self.accumulator = [0] * 16
            if self.accumulator is None:
                raise AssertionError('original Matrix packet before clear')
            for lane in range(16):
                a = request.a[lane if request.opcode == 0x23 else 0] << 16
                b = request.b[lane] << 16
                self.accumulator[lane] = ref_fma(a, b, self.accumulator[lane])
            return SimpleNamespace(error=False,
                value=SelectedMatrix(request.opcode, self.accumulator))
        address, words = request
        if words is not None:
            if not isinstance(words, bytes) or len(words) != 64:
                raise AssertionError('original write is not an exact 64-byte packet')
            words = struct.unpack('<16I', words)
            offset = (address - self.job.dst) // 4
            if address % 64 or not 0 <= offset <= len(self.output) - 16:
                raise AssertionError('original write outside synthetic output')
            if any(x is not None for x in self.output[offset:offset + 16]):
                raise AssertionError('original output written more than once')
            self.output[offset:offset + 16] = words
            self.writes.append((address, words))
            return None
        self.reads.append(address)
        for base, data in self.sources:
            if base <= address < base + 4 * len(data):
                offset = (address - base) // 4
                if address % 64 or offset + 16 > len(data):
                    raise AssertionError('unaligned or short original memory read')
                return data[offset:offset + 16]
        raise AssertionError('unmapped original memory read')

    def run(self):
        program = self._attention(self.job)
        response = None
        while True:
            try:
                request = program.send(response)
            except StopIteration:
                break
            response = self._response(request)
        if any(word is None for word in self.output):
            raise AssertionError('original generator left output unwritten')
        return tuple(self.output)

    def scores(self):
        scores, dots = [], []
        for index, entry in enumerate(self.scalar.trace):
            if entry[0] == 'mul' and entry[2] == 0x3db504f3:
                before, after = self.scalar.trace[index - 1], self.scalar.trace[index + 1]
                if before[0] != 'bf' or before[3] != entry[1] or after[:2] != ('bf', entry[3]):
                    raise AssertionError('original QK BF16/mul/BF16 boundary changed')
                dots.append(before[1])
                scores.append(after[3])
        return tuple(dots), tuple(scores)


_original_namespace = {'LegacyRequest': LegacyRequest, 'finite': finite,
                       'PrefixFault': PrefixFault, 'exp_negative': exp_negative,
                       'LANES': 16, 'struct': struct}
source_definitions(ORIGINAL, ('_attention',), _original_namespace,
                   class_name='OfficialAttentionOwner')
source_definitions(ATTENTION, ('_matrix_step', '_less'), _original_namespace,
                   class_name='AttentionOwner')
source_definitions(PREFIX_OWNER, ('_read', '_write'), _original_namespace,
                   class_name='PrefixOwner')
OriginalSchedule._read = _original_namespace['_read']
OriginalSchedule._write = _original_namespace['_write']
OriginalSchedule._attention = _original_namespace['_attention']
OriginalSchedule._matrix_step = _original_namespace['_matrix_step']
OriginalSchedule._less = staticmethod(_original_namespace['_less'])


def fixture(tokens, seed=271828):
    """Finite bit-encoded inputs, including BF16 ties and non-BF16 inputs."""
    rng = random.Random(seed)
    def words(count, low, high):
        return tuple((rng.randrange(2) << 31) | (rng.randrange(low, high) << 23)
                     | rng.randrange(1 << 23) for _ in range(count))
    return words(tokens * 1536, 120, 127), words(tokens * 256, 120, 127), words(tokens * 256, 121, 129)


def softmax(scores, scalar):
    maximum = max(scores, key=exact)
    weights, total = [], 0
    for score in scores:
        difference = scalar('add', score, maximum ^ 0x80000000)
        weight = exp_negative(scalar, scalar.client, difference)
        weights.append(weight)
        total = scalar('add', total, weight)
    return tuple(weights), scalar('div', 0x3f800000, total)


def expected_qk(q, keys):
    dots, scores = [], []
    for key in keys:
        stripes = [0] * 16
        for depth in range(128):
            lane = depth % 16
            stripes[lane] = ref_fma(ref_bf(q[depth]), ref_bf(key[depth]), stripes[lane])
        total = 0
        for stripe in stripes:
            total = ref_add(total, stripe)
        dots.append(total)
        scores.append(ref_bf(ref_mul(ref_bf(total), 0x3db504f3)))
    return tuple(dots), tuple(scores)


def expected_pv(weights, inverses, values):
    output = []
    for row, inverse in zip(weights, inverses):
        normalized = [ref_bf(ref_mul(probability, inverse)) for probability in row]
        columns = []
        for column in range(128):
            accumulator = 0
            for probability, value in zip(normalized, values):
                accumulator = ref_fma(probability, ref_bf(value[column]), accumulator)
            columns.append(ref_bf(accumulator))
        output.append(tuple(columns))
    return tuple(output)


def batched_attention(tokens, q, k, v):
    """Compose the candidate's documented same-token/same-KV-head batches."""
    scalar = ExactScalar(object())
    output = [None] * (tokens * 1536)
    score_rows = []
    counts = Counter()
    for token in range(tokens):
        token_scores = []
        for kv_head in range(2):
            keys = tuple(k[key * 256 + kv_head * 128:key * 256 + kv_head * 128 + 128]
                         for key in range(token + 1))
            values = tuple(v[key * 256 + kv_head * 128:key * 256 + kv_head * 128 + 128]
                           for key in range(token + 1))
            probabilities, inverses = [], []
            for local_head in range(6):
                head = kv_head * 6 + local_head
                start = token * 1536 + head * 128
                query = q[start:start + 128]
                scores = []
                for first in range(0, len(keys), 16):
                    result = candidate.qk(query, keys[first:first + 16], op=scalar, fma=ref_fma)
                    scores.extend(result.scores)
                    counts.update(dict(result.counts))
                token_scores.append(tuple(scores))
                weights, inverse = softmax(scores, scalar)
                probabilities.append(weights)
                inverses.append(inverse)
            result = candidate.pv(probabilities, inverses, values, op=scalar, fma=ref_fma)
            counts.update(dict(result.counts))
            for local_head, row in enumerate(result.output):
                start = token * 1536 + (kv_head * 6 + local_head) * 128
                output[start:start + 128] = row
        score_rows.extend(token_scores)
    if any(word is None for word in output):
        raise AssertionError('candidate composition left output unwritten')
    return tuple(output), tuple(score for row in score_rows for score in row), counts


class OriginalGeneratorEquivalenceTests(unittest.TestCase):
    def test_cold_m1_m2_match_actual_original_generator_and_adapter(self):
        for tokens in (1, 2):
            with self.subTest(tokens=tokens):
                q, k, v = fixture(tokens)
                original = OriginalSchedule(tokens, q, k, v)
                expected = original.run()
                actual, scores, counts = batched_attention(tokens, q, k, v)
                self.assertEqual(actual, expected)
                dots, original_scores = original.scores()
                self.assertEqual(scores, original_scores)
                self.assertTrue(any(word != ref_bf(word) for word in dots))
                self.assertTrue(any(word != ref_bf(word) for word in q + k + v))
                pairs = 12 * tokens * (tokens + 1) // 2
                self.assertEqual(len(original.requests), pairs * 16)
                self.assertEqual(original.useful_macs, pairs * 256)
                self.assertEqual(original.counts['exp_negative_requests'], pairs)
                self.assertEqual(len(original.writes), tokens * 96)
                self.assertEqual(original.peak_row_words, 128)
                self.assertEqual(original.peak_score_words, tokens)
                self.assertEqual(original.peak_probability_words, tokens)
                self.assertEqual(original.row_words, 0)
                self.assertEqual(counts['matrix_steps'], candidate.schedule_counts(tokens)['packed_steps'])
                for token in range(tokens):
                    for head in range(12):
                        keys = [k[key * 256 + head // 6 * 128:key * 256 + head // 6 * 128 + 128]
                                for key in range(token + 1)]
                        _, independent_scores = expected_qk(
                            q[token * 1536 + head * 128:token * 1536 + head * 128 + 128], keys)
                        start = 12 * token * (token + 1) // 2 + head * (token + 1)
                        self.assertEqual(scores[start:start + token + 1], independent_scores)
                if tokens == 1:
                    self.assertEqual(expected, tuple(ref_bf(v[head // 6 * 128 + col])
                        for head in range(12) for col in range(128)))

    def test_original_matrix_packets_preserve_eight_depths_and_causal_pv_end(self):
        original = OriginalSchedule(2, *fixture(2, seed=314159))
        original.run()
        offset = 0
        for token in range(2):
            for _head in range(12):
                for _key in range(token + 1):
                    group = original.requests[offset:offset + 8]
                    offset += 8
                    self.assertEqual([(x.opcode, x.clear, x.last, x.steps) for x in group],
                        [(0x23, step == 0, step == 7, 8) for step in range(8)])
                for _column_group in range(8):
                    group = original.requests[offset:offset + token + 1]
                    offset += token + 1
                    self.assertEqual([(x.opcode, x.clear, x.last, x.steps) for x in group],
                        [(0x24, key == 0, key == token, token + 1) for key in range(token + 1)])
                    self.assertTrue(all(not any(x.a[1:]) for x in group))
        self.assertEqual(offset, len(original.requests))


class BatchedNumericalBoundaryTests(unittest.TestCase):
    def test_qk_fifteen_sixteen_seventeen_causal_keys_keep_original_fold(self):
        q, k, _ = fixture(17, seed=1617)
        query = q[16 * 1536 + 3 * 128:16 * 1536 + 4 * 128]
        all_keys = tuple(k[key * 256:key * 256 + 128] for key in range(17))
        for count in (15, 16, 17):
            with self.subTest(causal_keys=count):
                scalar = ExactScalar(object())
                scores, counts = [], Counter()
                expected_dots, expected_scores = expected_qk(query, all_keys[:count])
                for first in range(0, count, 16):
                    result = candidate.qk(query, all_keys[first:min(first + 16, count)],
                                          op=scalar, fma=ref_fma)
                    scores.extend(result.scores)
                    counts.update(dict(result.counts))
                    self.assertEqual(result.trace,
                        tuple((step, step == 0, step == 7, step == 7, 0xff) for step in range(8)))
                self.assertEqual(tuple(scores), expected_scores)
                dots = [scalar.trace[index - 1][1] for index, entry in enumerate(scalar.trace)
                        if entry[0] == 'mul' and entry[2] == 0x3db504f3]
                self.assertEqual(tuple(dots), expected_dots)
                self.assertEqual(counts['matrix_steps'], 8 * ((count + 15) // 16))
                self.assertEqual(counts['selected_cell_fmas'], count * 128)
                self.assertEqual(counts['scalar_add'], count * 16)
                self.assertEqual(counts['scalar_mul'], count)
                self.assertEqual(counts['issued_cell_fmas'], 8 * ((count + 15) // 16) * 4096)

    def test_qk_must_not_round_eight_stripes_or_fold_with_a_tree(self):
        # A deterministic cancellation-sensitive fixture discriminates both
        # forbidden changes, even when their final BF16 scores might coincide.
        rng = random.Random(83123)
        query = tuple((rng.randrange(2) << 31) | (rng.randrange(109, 138) << 23)
                      | (rng.randrange(128) << 16) for _ in range(128))
        keys = tuple(tuple((rng.randrange(2) << 31) | (rng.randrange(109, 138) << 23)
                           | (rng.randrange(128) << 16) for _ in range(128)) for _ in range(16))
        scalar = ExactScalar(object())
        result = candidate.qk(query, keys, op=scalar, fma=ref_fma)
        dots, scores = expected_qk(query, keys)
        self.assertEqual(result.scores, scores)
        actual_dots = tuple(scalar.trace[index - 1][1] for index, entry in enumerate(scalar.trace)
                            if entry[0] == 'mul' and entry[2] == 0x3db504f3)
        self.assertEqual(actual_dots, dots)
        rounded_dots, tree_dots = [], []
        for key in keys:
            stripes, rounded = [0] * 16, [0] * 16
            for depth in range(128):
                lane = depth % 16
                stripes[lane] = ref_fma(query[depth], key[depth], stripes[lane])
                rounded[lane] = ref_bf(ref_fma(query[depth], key[depth], rounded[lane]))
            total = 0
            for stripe in rounded:
                total = ref_add(total, stripe)
            rounded_dots.append(total)
            while len(stripes) > 1:
                stripes = [ref_add(stripes[i], stripes[i + 1]) for i in range(0, len(stripes), 2)]
            tree_dots.append(stripes[0])
        self.assertNotEqual(tuple(rounded_dots), dots)
        self.assertNotEqual(tuple(tree_dots), dots)

    def test_pv_six_gqa_rows_share_causal_end_at_fifteen_sixteen_seventeen(self):
        q, k, v = fixture(17, seed=20261016)
        for count in (1, 2, 15, 16, 17):
            for kv_head in (0, 1):
                with self.subTest(causal_keys=count, kv_head=kv_head):
                    scalar = ExactScalar(object())
                    keys = tuple(k[key * 256 + kv_head * 128:key * 256 + kv_head * 128 + 128]
                                 for key in range(count))
                    values = tuple(v[key * 256 + kv_head * 128:key * 256 + kv_head * 128 + 128]
                                   for key in range(count))
                    weights, inverses = [], []
                    for head in range(kv_head * 6, kv_head * 6 + 6):
                        start = (count - 1) * 1536 + head * 128
                        _, scores = expected_qk(q[start:start + 128], keys)
                        row, inverse = softmax(scores, scalar)
                        weights.append(row)
                        inverses.append(inverse)
                    scalar.trace.clear()
                    result = candidate.pv(weights, inverses, values, op=scalar, fma=ref_fma)
                    self.assertEqual(result.output, expected_pv(weights, inverses, values))
                    self.assertEqual(result.trace, tuple(
                        (key, key == 0, key == count - 1, key == count - 1, 0x0f)
                        for key in range(count)))
                    counts = dict(result.counts)
                    self.assertEqual(counts['matrix_steps'], count)
                    self.assertEqual(counts['selected_cell_fmas'], count * 6 * 128)
                    self.assertEqual(counts['issued_cell_fmas'], count * 16 * 128)
                    self.assertEqual(counts['scalar_mul'], count * 6)
                    # Every six-head row is normalized in ascending key order,
                    # then all 768 outputs are rounded only after the last key.
                    normalizations = [(entry[1], entry[2]) for entry in scalar.trace if entry[0] == 'mul']
                    self.assertEqual(normalizations,
                        [(weights[head][key], inverses[head]) for key in range(count) for head in range(6)])
                    self.assertEqual([entry[0] for entry in scalar.trace[-768:]], ['bf'] * 768)

    def test_signed_zero_and_cancellation_are_exact_fma_operations(self):
        self.assertEqual(ref_fma(0x80000000, 0x3f800000, 0x80000000), 0x80000000)
        self.assertEqual(ref_fma(0x80000000, 0x3f800000, 0), 0)
        self.assertEqual(ref_fma(0x3f800000, 0xbf800000, 0x3f800000), 0)
        probabilities = ((0x3f000000, 0x3f000000),) * 6
        inverses = (0x3f800000,) * 6
        values = (tuple(0x80000000 if col % 2 else 0x3f800000 for col in range(128)),
                  tuple(0x80000000 if col % 2 else 0xbf800000 for col in range(128)))
        result = candidate.pv(probabilities, inverses, values,
                              op=ExactScalar(object()), fma=ref_fma)
        self.assertEqual(result.output, expected_pv(probabilities, inverses, values))
        self.assertEqual(result.output, ((0,) * 128,) * 6)


class MappingAndCountTests(unittest.TestCase):
    def test_full_128_schedule_count_is_enumeration_only(self):
        # Enumerate packing metadata only, not M128 arithmetic/inference.
        qk_steps = pv_steps = folds = pairs = qk_groups = pv_groups = 0
        for token in range(128):
            causal_keys = token + 1
            for _head in range(12):
                covered = []
                for first in range(0, causal_keys, 16):
                    columns = {}
                    for local, key in enumerate(range(first, min(first + 16, causal_keys))):
                        for lane in range(16):
                            address = lane * 256 + 16 * local + lane
                            self.assertNotIn(address, columns)
                            self.assertTrue(0 <= address < 4096)
                            columns[address] = (key, lane)
                        covered.append(key)
                    qk_groups += 1
                    qk_steps += 8
                self.assertEqual(covered, list(range(causal_keys)))
                pairs += causal_keys
                folds += causal_keys * 16
            for kv_head in range(2):
                heads = tuple(range(kv_head * 6, kv_head * 6 + 6))
                self.assertEqual(len(heads), 6)
                self.assertTrue(all(head // 6 == kv_head for head in heads))
                pv_groups += 1
                pv_steps += causal_keys
        counts = candidate.schedule_counts(128)
        self.assertEqual((qk_steps, pv_steps, qk_steps + pv_steps), (55296, 16512, 71808))
        self.assertEqual(folds, 1585152)
        for name, value in (('packed_qk_steps', qk_steps), ('packed_pv_steps', pv_steps),
                            ('qk_fold_adds', folds), ('causal_head_key_pairs', pairs),
                            ('qk_groups', qk_groups), ('pv_groups', pv_groups)):
            self.assertEqual(counts[name], value)
        self.assertEqual(counts['legacy_qk_steps'], pairs * 8)
        self.assertEqual(counts['legacy_pv_steps'], pairs * 8)
        self.assertEqual(counts['contexts_used'], 1)
        self.assertEqual(counts['metadata_slots_used'], 1)
        self.assertEqual(counts['result_tiles_used'], 1)
        self.assertEqual(counts['extra_mac_units'], 0)
        self.assertEqual(counts['extra_payload_banks'], 0)

    def test_optimistic_serial_bound_keeps_ordered_fold_cost_explicit(self):
        bound = candidate.serial_lower_bound(128, dense_issue_cycles=1462272)
        self.assertEqual(bound['serial_minimum_cycles'], 6289536)
        self.assertEqual(bound['ordered_fold_cycles'], 4755456)
        self.assertEqual(bound['matrix_issue_cycles'], 1534080)
        self.assertIsNone(bound['actual_hardware_cycles'])
        self.assertIsNone(bound['measured_utilization'])
        for key in ('includes_exp_div', 'includes_feed_stalls', 'includes_ddr',
                    'accepts_80_percent', 'accepts_90_percent'):
            self.assertFalse(bound[key])
        slow = candidate.serial_lower_bound(128, dense_issue_cycles=1462272,
                                           fold_latency=3, fold_ii=1)
        self.assertEqual(slow['ordered_fold_cycles'], 1585152 * 3)

    def test_model_and_cold_oracle_have_no_tensor_or_native_imports(self):
        for path in (Path(candidate.__file__), Path(__file__)):
            tree = ast.parse(path.read_text())
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module.split('.')[0])
            self.assertFalse(set(imports) & {'numpy', 'torch', 'ctypes', 'subprocess'})


class DomainAndFaultTests(unittest.TestCase):
    def test_qk_rejects_bad_shapes_words_and_nonfinite_inputs_before_work(self):
        good = (0x3f000000,) * 128
        invalid_queries = (good[:-1], good + (0,), (True,) + good[1:],
                           (-1,) + good[1:], (1 << 32,) + good[1:])
        for query in invalid_queries:
            with self.subTest(query=query[:2]), self.assertRaises(ValueError):
                candidate.qk(query, (good,), op=ExactScalar(object()), fma=ref_fma)
        for keys in ((), (good,) * 17, (good[:-1],)):
            with self.subTest(key_count=len(keys)), self.assertRaises(ValueError):
                candidate.qk(good, keys, op=ExactScalar(object()), fma=ref_fma)
        for nonfinite in (0x7f800000, 0xff800000, 0x7fc00001, 0x7fa00001):
            bad = (nonfinite,) + good[1:]
            for query, keys in ((bad, (good,)), (good, (bad,))):
                scalar = ExactScalar(object())
                with self.subTest(nonfinite=hex(nonfinite)), self.assertRaises(ValueError):
                    candidate.qk(query, keys, op=scalar, fma=ref_fma)
                self.assertEqual(scalar.calls, {})

    def test_pv_requires_six_rows_with_identical_causal_length(self):
        values = ((0x3f000000,) * 128,) * 2
        weights = ((0x3f800000,) * 2,) * 6
        inverses = (0x3f000000,) * 6
        invalid = (weights[:5], weights * 2,
                   weights[:5] + ((0x3f800000,),),
                   weights[:5] + ((0x3f800000,) * 3,))
        for rows in invalid:
            with self.subTest(row_lengths=tuple(map(len, rows))), self.assertRaises(ValueError):
                candidate.pv(rows, inverses, values, op=ExactScalar(object()), fma=ref_fma)
        for nonfinite in (0x7f800000, 0xff800000, 0x7fc00001, 0x7fa00001):
            cases = (
                (((nonfinite, 0x3f800000),) + weights[1:], inverses, values),
                (weights, (nonfinite,) + inverses[1:], values),
                (weights, inverses, ((nonfinite,) + values[0][1:], values[1])),
            )
            for rows, inverse, data in cases:
                scalar = ExactScalar(object())
                with self.subTest(nonfinite=hex(nonfinite)), self.assertRaises(ValueError):
                    candidate.pv(rows, inverse, data, op=scalar, fma=ref_fma)
                self.assertEqual(scalar.calls, {})

    def test_actual_finite_bf16_product_overflow_is_rejected_at_selected_cell(self):
        maximum = (0x7f7f0000,) * 128
        self.assertEqual(ref_fma(maximum[0], maximum[0], 0), 0x7f800000)
        scalar = ExactScalar(object())
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            candidate.qk(maximum, (maximum,), op=scalar, fma=ref_fma)
        self.assertEqual(scalar.calls['add'], 0)
        # Deliberately large finite PV inputs also overflow at a real FMA,
        # before the final BF16 materialization or any output is returned.
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            candidate.pv(((0x7f7f0000,),) * 6, (0x3f800000,) * 6, (maximum,),
                         op=ExactScalar(object()), fma=ref_fma)

    def test_equal_probability_final_bf16_overflow_matches_original_store_guard(self):
        # This is a real finite-input numerical edge, not an injected callback:
        # 13 BF16-normalized equal probabilities sum above 1 after rounding.
        # FP32 PV stays finite, but its final BF16 materialization overflows.
        weights = ((0x3f800000,) * 13,) * 6
        inverse = ref_div(0x3f800000, rn(Fraction(13)))
        values = ((0x7f7f0000,) * 128,) * 13
        p = ref_bf(inverse)
        accumulator = 0
        for _ in range(13):
            accumulator = ref_fma(p, values[0][0], accumulator)
        self.assertEqual(p, 0x3d9e0000)
        self.assertEqual(accumulator, 0x7f7fbf40)
        self.assertEqual(ref_bf(accumulator), 0x7f800000)
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            candidate.pv(weights, (inverse,) * 6, values,
                         op=ExactScalar(object()), fma=ref_fma)
        original = OriginalSchedule(1, *fixture(1))
        with self.assertRaisesRegex(PrefixFault, 'nonfinite prefix store'):
            next(original._write(original.job.dst, (ref_bf(accumulator),) * 16))

    def test_observed_callback_counts_and_operand_order_match_useful_mapping(self):
        q, k, v = fixture(16, seed=196)
        query = q[:128]
        keys = tuple(k[key * 256:key * 256 + 128] for key in range(16))
        seen = []
        def observed(a, b, previous):
            seen.append((a, b, previous))
            return ref_fma(a, b, previous)
        result = candidate.qk(query, keys, op=ExactScalar(object()), fma=observed)
        self.assertEqual(len(seen), 16 * 128)
        self.assertEqual(dict(result.counts)['selected_cell_fmas'], len(seen))
        expected_operands = [(ref_bf(query[step * 16 + lane]), ref_bf(key[step * 16 + lane]))
                             for step in range(8) for key in keys for lane in range(16)]
        self.assertEqual([(a, b) for a, b, _previous in seen], expected_operands)
        self.assertTrue(all(previous == 0 for _a, _b, previous in seen[:256]))
        for step in range(1, 8):
            for cell in range(256):
                before = seen[(step - 1) * 256 + cell]
                self.assertEqual(seen[step * 256 + cell][2], ref_fma(*before))
        seen.clear()
        weights = tuple(tuple(rn(Fraction(head + key + 1, 8)) for key in range(2))
                        for head in range(6))
        inverses = tuple(rn(Fraction(1, head + 1)) for head in range(6))
        values = (v[:128], v[256:384])
        result = candidate.pv(weights, inverses, values, op=ExactScalar(object()), fma=observed)
        self.assertEqual(len(seen), 2 * 6 * 128)
        self.assertEqual(dict(result.counts)['selected_cell_fmas'], len(seen))
        expected_operands = [(ref_bf(ref_mul(weights[head][key], inverses[head])), ref_bf(values[key][col]))
                             for key in range(2) for head in range(6) for col in range(128)]
        self.assertEqual([(a, b) for a, b, _previous in seen], expected_operands)
        self.assertTrue(all(previous == 0 for _a, _b, previous in seen[:768]))
        for cell in range(768):
            self.assertEqual(seen[768 + cell][2], ref_fma(*seen[cell]))

    def test_schedule_guards_reject_noninteger_or_out_of_range_profiles(self):
        for tokens in (0, 129, True, 1.0):
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                candidate.schedule_counts(tokens)
        for kwargs in ({'dense_issue_cycles': -1}, {'dense_issue_cycles': True},
                       {'dense_issue_cycles': 1, 'fold_latency': 0},
                       {'dense_issue_cycles': 1, 'fold_ii': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                candidate.serial_lower_bound(128, **kwargs)


if __name__ == '__main__':
    unittest.main()
