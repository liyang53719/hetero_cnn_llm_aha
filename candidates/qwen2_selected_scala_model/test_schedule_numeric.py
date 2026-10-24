"""Cold bounded arithmetic checks of the actual production QK16 generator.

This file executes unchanged reviewed AST definitions only. It does not import
NumPy, a native arithmetic library, MatrixService, a public model, or weights.
M2 is an exact arithmetic/schedule smoke against OfficialAttentionOwner, not an
M128 qualification, physical implementation, cycle model, or RTL acceptance.
Synthetic result/scalar faults below test guard ordering, not new arithmetic.
Full-profile status remains TEMP_NOT_NUMERICALLY_QUALIFIED.

Run with a process CPU limit <=20 seconds, address-space limit <=256 MiB, and
one CPU. Pass the required --source-root RAW_CHECKOUT argument. unittest
and need() remain active under python -O.
"""
import argparse
import ast
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import random
import struct
import sys
from types import SimpleNamespace
import unittest


HERE = Path(__file__).resolve().parent
# Consume only this harness's explicit source argument; unittest keeps -v,
# test selectors, and other options. There is no author-workspace default.
_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
_parser.add_argument('--source-root', required=True, metavar='RAW_CHECKOUT')
_options, _unittest_args = _parser.parse_known_args()
sys.argv = [sys.argv[0]] + _unittest_args
SOURCE_ROOT = Path(_options.source_root).expanduser().resolve(strict=True)
SOURCES = SOURCE_ROOT / 'candidates/qwen2_resident_matrix'
COLD_SOURCE = SOURCES / 'attention_matrix_batch/test_model.py'
INPUT_PINS = json.loads((HERE / 'INPUT_PINS.json').read_text())


def need(condition, message):
    if not condition:
        raise AssertionError(message)


# Pin all consumed raw definitions before the first AST execution. These pins
# travel with the candidate, not with a particular author's fixture directory.
CONSUMED_RAW = (
    'attention_matrix_batch/test_model.py',
    'ffn_public/test_prefix_owners.py',
    'ffn_attention/scalar_recipe.py',
    'official_bf16/owners.py',
    'ffn_attention/attention_owner.py',
    'ffn_public/prefix_owners.py',
    'ffn_attention/matrix_service.py',
    'attention_packed_owner/client.py',
    'attention_packed_owner/schedule.py',
)
need(SOURCE_ROOT.is_dir(), '--source-root must be a raw source directory')
for _relative in CONSUMED_RAW:
    _path = 'candidates/qwen2_resident_matrix/' + _relative
    need(_path in INPUT_PINS['sources'], 'missing consumed raw input pin: ' + _path)
    _pin = INPUT_PINS['sources'][_path]
    _data = (SOURCE_ROOT / _path).read_bytes()
    need(len(_data) == _pin['bytes'] and
         hashlib.sha256(_data).hexdigest() == _pin['sha256'],
         'consumed raw input does not match fixed pin: ' + _path)


def definitions(path, names, namespace):
    """Load exact named class/function ASTs, never their module import bodies."""
    tree = ast.parse(path.read_text(), filename=str(path))
    nodes = [node for node in tree.body
             if isinstance(node, (ast.ClassDef, ast.FunctionDef))
             and node.name in names]
    need({node.name for node in nodes} == set(names), 'missing reviewed definition')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


# Reuse the original cold harness, including its source_definitions loader and
# independent integer quotient/remainder IEEE RNE primitives. No replacement
# softmax, dot-fold, FMA rounding rule, or PV arithmetic is introduced here.
NS = {'__name__': __name__, 'ast': ast, 'Counter': Counter,
      'dataclass': dataclass, 'Fraction': Fraction, 'lru_cache': lru_cache,
      'struct': struct, 'random': random, 'SimpleNamespace': SimpleNamespace}
definitions(COLD_SOURCE, ('source_definitions',), NS)
source_definitions = NS['source_definitions']
source_definitions(SOURCES / 'ffn_public/test_prefix_owners.py',
                   ('exact', 'rn', 'ref_add', 'ref_mul', 'ref_div', 'ref_bf'), NS)
NS['exact'] = lru_cache(maxsize=32768)(NS['exact'])
definitions(COLD_SOURCE,
            ('finite', 'ref_fma', 'ArithmeticFault', 'PrefixFault', 'ExactScalar',
             'LegacyRequest', 'SelectedMatrix', 'OriginalSchedule', 'fixture'), NS)
source_definitions(SOURCES / 'ffn_attention/scalar_recipe.py',
                   ('EXP_COEFFICIENTS', 'LOG2_RECIPROCAL', 'exp_negative'),
                   NS)
# exp_negative references value/word exactly as in the existing cold harness.
NS['value'] = NS['exact']
NS['word'] = lambda value: NS['rn'](Fraction(value))
NS['LANES'] = 16
source_definitions(SOURCES / 'official_bf16/owners.py', ('_attention',), NS,
                   class_name='OfficialAttentionOwner')
source_definitions(SOURCES / 'ffn_attention/attention_owner.py',
                   ('_matrix_step', '_less'), NS, class_name='AttentionOwner')
source_definitions(SOURCES / 'ffn_public/prefix_owners.py', ('_read', '_write'), NS,
                   class_name='PrefixOwner')
OriginalSchedule = NS['OriginalSchedule']
for _method in ('_read', '_write', '_attention', '_matrix_step'):
    setattr(OriginalSchedule, _method, NS[_method])
OriginalSchedule._less = staticmethod(NS['_less'])

definitions(SOURCES / 'ffn_attention/matrix_service.py',
            ('MatrixProtocolError', 'require'), NS)
definitions(SOURCES / 'attention_packed_owner/client.py',
            ('_uint', 'PackedTag', 'PackedRequest', 'PackedResult',
             'PackedConsumerAck'), NS)
definitions(SOURCES / 'attention_packed_owner/schedule.py', ('PackedSchedule',), NS)
# The parent candidate file has no surrounding module body executed here.
definitions(HERE / 'schedule.py', ('ProductionQk16Schedule',), NS)

ExactScalar = NS['ExactScalar']
ArithmeticFault, PrefixFault = NS['ArithmeticFault'], NS['PrefixFault']
LegacyRequest, PackedRequest = NS['LegacyRequest'], NS['PackedRequest']
PackedTag, PackedResult = NS['PackedTag'], NS['PackedResult']
PackedConsumerAck = NS['PackedConsumerAck']
ProductionQk16Schedule = NS['ProductionQk16Schedule']
fixture, finite = NS['fixture'], NS['finite']
ref_fma, ref_bf = NS['ref_fma'], NS['ref_bf']


class ObservedScalar(ExactScalar):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    def op(self, client, operation, a, b=0, *, policy='legacy_scalar'):
        result = super().op(client, operation, a, b, policy=policy)
        # Deliberate scalar-output injection exercises BF-score guard ordering.
        # Its arithmetic value is never used for numerical acceptance.
        if (self.owner.inject_score_nonfinite and self.owner.held is not None
                and self.owner.position == (1, 0) and operation == 'bf'
                and len(self.trace) >= 2
                and self.trace[-2][0] == 'mul'
                and self.trace[-2][2] == 0x3db504f3):
            result = 0x7f800000
            self.trace[-1] = (operation, a, b, result, policy)
        self.owner.events.append(('scalar', self.owner.position, self.trace[-1]))
        return result


class LiveSelectedMatrix:
    """Only the returned QK group's selected live FIFO cells exist.

    Reads fail on any unselected row/column or after consumer retirement, so
    passing cannot rely on scanning a full tile or copying an unselected panel.
    """
    def __init__(self, owner, values, tag):
        self.owner, self.values, self.tag = owner, values, tag

    def __getitem__(self, row):
        outer = self
        class Row:
            def __getitem__(self, column):
                need(outer.owner.held == outer.tag, 'read after packed retirement')
                need((row, column) in outer.values, 'read unselected packed cell')
                committed = outer.owner.committed_scores()
                outer.owner.events.append(('cell', outer.owner.position,
                                           row, column, committed))
                return outer.values[row, column]
        return Row()


class ObservedOriginal(OriginalSchedule):
    def __init__(self, tokens, q, k, v):
        super().__init__(tokens, q, k, v)
        self.events = []
        self.position = None
        self.held = None
        self.inject_score_nonfinite = False
        self.scalar = ObservedScalar(self)

    def _response(self, request):
        if isinstance(request, LegacyRequest):
            self.events.append(('legacy', self.position, request))
        elif isinstance(request, tuple):
            address, data = request
            if data is None:
                if self.job.a <= address < self.job.a + 4 * self.job.m * 1536:
                    offset = (address - self.job.a) // 4
                    self.position = (offset // 1536, (offset % 1536) // 128)
                self.events.append(('read', self.position, address))
            else:
                self.events.append(('write', self.position, address))
        return super()._response(request)


class ProductionDriver(ObservedOriginal):
    """Drive the candidate generator through real packet shapes, cold arithmetic.

    This is not PackedClient/MatrixService handshake simulation. Their separate
    protocol tests remain necessary. It models only selected QK cells with the
    existing exact FMA oracle and uses the unchanged legacy adapter for PV.
    """
    def __init__(self, tokens, q, k, v, *, injected_cells=None,
                 inject_score_nonfinite=False):
        super().__init__(tokens, q, k, v)
        self.schedule = ProductionQk16Schedule()
        self.schedule.bind(self)
        self.packed_requests, self.acks = [], []
        self.group_serial = 0
        self.group_first = self.group_steps = 0
        self.group_position = None
        self.group_cells = None
        self.injected_cells = injected_cells or {}
        self.inject_score_nonfinite = inject_score_nonfinite
        self.program = None
        self.fault_scores = None

    def committed_scores(self):
        need(self.program is not None and self.program.gi_frame is not None,
             'live schedule frame missing')
        return tuple(self.program.gi_frame.f_locals.get('scores', ()))

    def _response(self, request):
        if isinstance(request, PackedConsumerAck):
            need(request.tag == self.held, 'foreign/early packed ACK')
            committed = self.committed_scores()
            need(len(committed) == self.group_first + self.active_keys,
                 'ACK before final current-group score committed')
            self.events.append(('ack', self.position, request.tag, committed))
            self.acks.append(request)
            self.held = None
            self.group_first += self.active_keys
            return SimpleNamespace(error=False, value=None, tag=request.tag)
        if isinstance(request, PackedRequest):
            need(self.held is None, 'QK issue before prior result retirement')
            need(self.schedule.active_qk_keys == min(16, self.position[0] + 1 -
                 (self.group_first if self.group_position == self.position else 0)),
                 'active key metadata differs from packet extent')
            need(request.opcode == 0x23 and request.slice_mask == 255,
                 'packed path must be QK16 mask255 only')
            need(len(request.a) == 16 and len(request.b) == 256,
                 'packed operand packet width')
            need(all(type(x) is int and 0 <= x < 1 << 16
                     for x in request.a + request.b), 'packed input not BF16')
            if request.clear:
                if self.group_position != self.position:
                    self.group_position, self.group_first = self.position, 0
                self.active_keys = min(16, self.position[0] + 1 - self.group_first)
                need(self.active_keys > 0, 'empty causal QK group')
                self.group_serial += 1
                self.group_steps = 0
                self.group_cells = {(lane, 16 * key + lane): 0
                                    for key in range(self.active_keys)
                                    for lane in range(16)}
            need(self.group_cells is not None, 'QK packet without clear')
            need((request.clear, request.last, request.steps) ==
                 (self.group_steps == 0, self.group_steps == 7, 8),
                 'QK16 is exactly eight depth steps')
            need(not any(request.b[self.active_keys * 16:]), 'tail padding is not zero')
            for key in range(self.active_keys):
                for lane in range(16):
                    cell = (lane, 16 * key + lane)
                    self.group_cells[cell] = ref_fma(
                        request.a[lane] << 16, request.b[16 * key + lane] << 16,
                        self.group_cells[cell])
            self.group_steps += 1
            self.packed_requests.append(request)
            self.events.append(('packed', self.position, request))
            if not request.last:
                need(request.selected == (), 'nonfinal packet exposed result selection')
                return SimpleNamespace(error=False, value=None)
            selected = tuple((lane, 16 * key + lane)
                             for key in range(self.active_keys) for lane in range(16))
            need(request.selected == selected, 'QK16 selected mapping changed')
            tag = PackedTag(7, self.group_serial, self.group_serial, 0)
            self.held = tag
            if self.position == (1, 0):
                self.group_cells.update(self.injected_cells)
            value = LiveSelectedMatrix(self, self.group_cells, tag)
            return PackedResult(tag, SimpleNamespace(value=value, error=False), selected)
        need(self.held is None, 'memory/PV access before packed score retirement')
        if isinstance(request, LegacyRequest):
            need(self.schedule.active_qk_keys == 0, 'QK key extent leaked into PV')
            need(request.opcode == 0x24, 'production QK escaped into legacy path')
        # ScratchAction or other cross-head scratch/panel operation is rejected.
        need(isinstance(request, (tuple, LegacyRequest)), 'unexpected scratch/panel operation')
        return super()._response(request)

    def run(self):
        self.program = self.schedule.run(self, self.job)
        response = None
        while True:
            try:
                request = self.program.send(response)
            except StopIteration:
                break
            except (PrefixFault, ArithmeticFault) as fault:
                # Preserve actual generator locals at its rejecting statement;
                # reading an earlier event alone would miss append-then-fail.
                trace = fault.__traceback__
                while trace is not None:
                    if trace.tb_frame.f_code is self.schedule.run.__func__.__code__:
                        self.fault_scores = tuple(trace.tb_frame.f_locals.get('scores', ()))
                    trace = trace.tb_next
                raise
            response = self._response(request)
        need(self.held is None, 'normal exit with unretired packed result')
        need(all(word is not None for word in self.output), 'missing output words')
        return tuple(self.output)


def per_head_events(driver):
    grouped = {}
    for event in driver.events:
        grouped.setdefault(event[1], []).append(event)
    return grouped


def downstream_scalars(events):
    """Exact softmax/PV scalar stream after the last QK score materialization."""
    scalar = [event[2] for event in events if event[0] == 'scalar']
    scales = [i for i, entry in enumerate(scalar)
              if entry[0] == 'mul' and entry[2] == 0x3db504f3]
    need(scales, 'QK scale not observed')
    last = scales[-1]
    need(scalar[last + 1][:2] == ('bf', scalar[last][3]),
         'completed QK score materialization missing')
    return tuple(scalar[last + 2:])


class ProductionQk16NumericTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.words = fixture(2, seed=271828)
        cls.original = ObservedOriginal(2, *cls.words)
        cls.expected = cls.original.run()
        cls.production = ProductionDriver(2, *cls.words)
        cls.actual = cls.production.run()

    def test_m2_actual_generator_output_scores_and_fold_match(self):
        self.assertEqual(self.actual, self.expected)
        self.assertEqual(self.production.scores(), self.original.scores())
        self.assertEqual(len(self.actual), 2 * 1536)
        self.assertTrue(any(word != ref_bf(word) for word in self.words[0]))
        self.assertTrue(any(word != ref_bf(word) for word in self.original.scores()[0]))
        # QK useful-MAC credit belongs to the actual accepted-request router,
        # outside this direct-generator arithmetic harness. PV credit is real.
        self.assertEqual(self.production.useful_macs, 288 * 16)
        self.assertEqual(self.original.useful_macs, 36 * 256)
        self.assertEqual(self.production.counts['exp_negative_requests'], 36)
        self.assertEqual((self.production.peak_row_words,
                          self.production.peak_score_words,
                          self.production.peak_probability_words,
                          self.production.row_words), (128, 2, 2, 0))
        # BF input staging is deliberately repacked; arithmetic operations after
        # ingress retain the exact non-BF scalar order/operands/results/policy.
        self.assertEqual(tuple(x for x in self.production.scalar.trace if x[0] != 'bf'),
                         tuple(x for x in self.original.scalar.trace if x[0] != 'bf'))

    def test_each_head_finishes_original_softmax_and_legacy_pv_before_next_head(self):
        actual, original = per_head_events(self.production), per_head_events(self.original)
        expected_heads = [(token, head) for token in range(2) for head in range(12)]
        self.assertEqual(list(actual), expected_heads)
        self.assertEqual(list(original), expected_heads)
        for position in expected_heads:
            with self.subTest(position=position):
                a, o = actual[position], original[position]
                self.assertEqual(downstream_scalars(a), downstream_scalars(o))
                self.assertEqual([e[2] for e in a if e[0] == 'legacy'],
                                 [e[2] for e in o if e[0] == 'legacy' and e[2].opcode == 0x24])
                self.assertEqual([e[2] for e in a if e[0] == 'write'],
                                 [e[2] for e in o if e[0] == 'write'])
                pv = [e[2] for e in a if e[0] == 'legacy']
                self.assertEqual(len(pv), 8 * (position[0] + 1))
                self.assertTrue(all(x.opcode == 0x24 and not any(x.a[1:])
                                    and not any(x.b[16:]) for x in pv))
                self.assertEqual([e[0] for e in a].count('ack'), 1)
                self.assertEqual([e[0] for e in a].count('write'), 8)
                self.assertLess(max(i for i, e in enumerate(a) if e[0] == 'ack'),
                                min(i for i, e in enumerate(a) if e[0] == 'legacy'))

    def test_physical_q_k_v_reads_have_no_cross_head_reuse_or_panel(self):
        expected_reads = []
        job = self.production.job
        for token in range(2):
            for head in range(12):
                kv = head // 6
                expected_reads.extend(job.a + (token * 1536 + head * 128 + d) * 4
                                      for d in range(0, 128, 16))
                expected_reads.extend(job.b + (key * 256 + kv * 128 + d) * 4
                                      for d in range(0, 128, 16)
                                      for key in range(token + 1))
                expected_reads.extend(job.c + (key * 256 + kv * 128 + col) * 4
                                      for col in range(0, 128, 16)
                                      for key in range(token + 1))
        self.assertEqual(self.production.reads, expected_reads)
        self.assertEqual(Counter(self.production.reads), Counter(self.original.reads))
        self.assertEqual(len(self.production.reads), 768)
        self.assertEqual(len(self.production.writes), 192)
        self.assertEqual(len(self.production.packed_requests), 192)
        self.assertEqual(len(self.production.requests), 288)
        self.assertEqual(len(self.production.acks), 24)
        self.assertEqual(self.production.schedule.owner, self.production)
        self.assertIs(self.production.scalar.client, self.production)

    def test_live_key_cells_and_commit_order_precede_final_ack(self):
        grouped = per_head_events(self.production)
        for position, events in grouped.items():
            cells = [event for event in events if event[0] == 'cell']
            self.assertTrue(cells)
            # Current key may be read once for validation and once for folding;
            # no later key may be read until all earlier scores are committed.
            for cell in cells:
                local_key = cell[3] // 16
                self.assertEqual(cell[2], cell[3] % 16)
                self.assertEqual(len(cell[4]), local_key)
            ack = [event for event in events if event[0] == 'ack']
            self.assertEqual(len(ack), 1)
            self.assertEqual(len(ack[0][3]), position[0] + 1)


class ProductionQk16FaultOrderingTests(unittest.TestCase):
    def driver(self, **kwargs):
        return ProductionDriver(2, *fixture(2, seed=271828), **kwargs)

    def target_events(self, driver):
        return [event for event in driver.events if event[1] == (1, 0)]

    def test_nonfinite_current_key_stops_before_fold_or_score(self):
        for nonfinite in (0x7f800000, 0xff800000, 0x7fc00001, 0x7fa00001):
            with self.subTest(nonfinite=hex(nonfinite)):
                driver = self.driver(injected_cells={(7, 7): nonfinite})
                with self.assertRaises((PrefixFault, ArithmeticFault)):
                    driver.run()
                events = self.target_events(driver)
                self.assertFalse(any(e[0] == 'ack' for e in events))
                self.assertFalse(any(e[0] == 'write' for e in events))
                scalar = [e[2] for e in events if e[0] == 'scalar']
                self.assertTrue(all(e[0] == 'bf' for e in scalar))
                cells = [e for e in events if e[0] == 'cell']
                self.assertTrue(cells)
                self.assertTrue(all(e[3] < 16 and not e[4] for e in cells))
                self.assertIsNotNone(driver.held)
                self.assertEqual(driver.fault_scores, ())

    def test_later_key_nonfinite_does_not_pre_scan_or_erase_first_score(self):
        driver = self.driver(injected_cells={(1, 17): 0x7f800000})
        with self.assertRaises((PrefixFault, ArithmeticFault)):
            driver.run()
        events = self.target_events(driver)
        cells = [e for e in events if e[0] == 'cell']
        later = [e for e in cells if e[3] >= 16]
        self.assertTrue(later)
        self.assertTrue(all(len(e[4]) == 1 and finite(e[4][0]) for e in later))
        scalar = [e[2] for e in events if e[0] == 'scalar']
        self.assertEqual(sum(e[0] == 'add' for e in scalar), 16)
        self.assertEqual(sum(e[0] == 'mul' for e in scalar), 1)
        self.assertFalse(any(e[0] in ('ack', 'write', 'legacy') for e in events))
        self.assertIsNotNone(driver.held)
        self.assertEqual(len(driver.fault_scores), 1)
        self.assertTrue(finite(driver.fault_scores[0]))

    def test_finite_fold_then_bf_dot_overflow_is_not_committed_or_scaled(self):
        cells = {(lane, lane): (0x7f7f8000 if lane == 0 else 0)
                 for lane in range(16)}
        driver = self.driver(injected_cells=cells)
        with self.assertRaises((PrefixFault, ArithmeticFault)):
            driver.run()
        events = self.target_events(driver)
        scalar = [e[2] for e in events if e[0] == 'scalar']
        self.assertEqual(scalar[-1], ('bf', 0x7f7f8000, 0, 0x7f800000, 'legacy_scalar'))
        self.assertEqual(sum(e[0] == 'add' for e in scalar), 16)
        self.assertFalse(any(e[0] == 'mul' for e in scalar))
        self.assertFalse(any(e[0] in ('ack', 'write', 'legacy') for e in events))
        self.assertTrue(all(not e[4] for e in events if e[0] == 'cell'))
        self.assertEqual(driver.fault_scores, ())

    def test_injected_nonfinite_bf_score_cannot_commit_or_retire(self):
        driver = self.driver(inject_score_nonfinite=True)
        with self.assertRaises((PrefixFault, ArithmeticFault)):
            driver.run()
        events = self.target_events(driver)
        scalar = [e[2] for e in events if e[0] == 'scalar']
        self.assertEqual(scalar[-1][0], 'bf')
        self.assertEqual(scalar[-1][3], 0x7f800000)
        self.assertEqual(sum(e[0] == 'add' for e in scalar), 16)
        self.assertEqual(sum(e[0] == 'mul' for e in scalar), 1)
        self.assertFalse(any(e[0] in ('ack', 'write', 'legacy') for e in events))
        self.assertTrue(all(not e[4] for e in events if e[0] == 'cell'))
        self.assertEqual(driver.fault_scores, ())


class ColdSourceIsolationTests(unittest.TestCase):
    def test_raw_sources_match_candidate_input_pins(self):
        for path, pin in INPUT_PINS['sources'].items():
            data = (SOURCE_ROOT / path).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), pin['sha256'], path)
            self.assertEqual(len(data), pin['bytes'], path)

    def test_harness_imports_are_stdlib_and_guards_survive_optimization(self):
        forbidden = {'numpy', 'torch', 'ctypes', 'subprocess'}
        for path in (Path(__file__), HERE / 'schedule.py'):
            tree = ast.parse(path.read_text())
            imports = {alias.name.split('.')[0] for node in ast.walk(tree)
                       if isinstance(node, ast.Import) for alias in node.names}
            imports.update(node.module.split('.')[0] for node in ast.walk(tree)
                           if isinstance(node, ast.ImportFrom) and node.module)
            self.assertFalse(imports & forbidden)
        with self.assertRaisesRegex(AssertionError, 'active under -O'):
            need(False, 'active under -O')


if __name__ == '__main__':
    unittest.main()
