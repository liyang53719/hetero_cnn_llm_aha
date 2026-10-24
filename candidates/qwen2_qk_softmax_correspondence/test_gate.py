"""Cold, stdlib-only source/mutation tests. Never import the selected sources."""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import unittest

# Bound only this fresh test process, not another task or an inherited runtime.
resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
if hasattr(os, 'sched_getaffinity'):
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})

spec = importlib.util.spec_from_file_location('source_gate_under_test',
                                           Path(__file__).with_name('gate.py'))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
ROOT = None


def changed(source, old, new, expected_count=1):
    if source.count(old) != expected_count:
        raise RuntimeError('mutation target count: ' + old)
    return source.replace(old, new)


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = gate.strict_json((gate.HERE / 'SOURCE_PINS.json').read_bytes())
        cls.raw = {p: gate.read_bound(ROOT, p, r) for p, r in cls.pins['sources'].items()}
        cls.schedule = gate.apply_target_patch(cls.raw[gate.SCHEDULE].decode(),
                                              cls.raw[gate.M16_PATCH].decode(), gate.SCHEDULE)
        cls.schedule = gate.apply_target_patch(cls.schedule, cls.raw[gate.M128_PATCH].decode(),
                                              gate.SCHEDULE)
        cls.client = cls.raw[gate.CLIENT].decode()
        cls.scala = cls.raw[gate.SNAPSHOT].decode()

    def test_pinned_positive_slice_stays_incomplete(self):
        report = gate.inspect(ROOT)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['coordinate_check']['ordered_coordinate_comparisons'], 2176)
        self.assertEqual(report['coordinate_check']['full_tile_unique_cells'], 256)
        self.assertEqual(report['coordinate_check']['tail_key_counts'], list(range(1, 17)))
        self.assertTrue(all(v == 'INCOMPLETE' for v in report['unproven'].values()))
        self.assertEqual(set(report['unproven']), set(gate.UNPROVEN))
        self.assertFalse(report['scope']['arithmetic_equivalence'])
        self.assertFalse(report['scope']['full_block_acceptance'])
        self.assertFalse(report['scope']['full29_acceptance'])
        self.assertFalse(report['scope']['scale_constant_numerically_validated'])
        self.assertFalse(report['scope']['native_model_imported'])
        self.assertFalse(report['scope']['scala_executed'])
        self.assertFalse(report['scope']['rtl_executed'])
        self.assertFalse(report['scope']['cycle_or_timing_claim'])

    def test_historical_scope_not_inherited(self):
        report = gate.inspect(ROOT)
        old = report['historical_cold_m128']
        self.assertEqual(old['status'], 'PASS_FRESH_SAME_HOST_M128_ASSIGNED27')
        self.assertEqual((old['assigned_gates'], old['observed_stages']), (27, 28))
        self.assertEqual(old['ci']['commit'], '8ba333c76722b47b681be88612b1c6987e34a5f4')
        self.assertFalse(old['result_reexecuted'])
        self.assertFalse(old['acceptance_inherited_by_this_gate'])
        self.assertFalse(old['carried'])
        self.assertFalse(report['scope']['mask_tensor_fabricated'])
        self.assertFalse(report['scope']['new_tolerance'])

    def test_current_main_is_not_selected_production_postimage(self):
        binding = gate.inspect(ROOT)['current_main_binding']
        self.assertEqual(binding['status'], 'MISMATCH')
        self.assertFalse(binding['matches_selected_postimage'])
        self.assertFalse(binding['has_production_packed_qk16_selector'])
        self.assertFalse(binding['has_official_materialize_function'])
        self.assertFalse(binding['att_score_body_matches_selected'])
        with self.assertRaises(gate.Rejected):
            gate.scala_projection(self.raw[gate.SCALA].decode())

    def test_patches_and_postimage_bound(self):
        self.assertEqual(gate.sha(self.schedule.encode()), self.pins['derived_schedule_sha256'])
        self.assertEqual(gate.sha(self.scala.encode()), self.pins['target_postimage_sha256'])
        self.assertNotEqual(gate.sha(self.scala.encode()), gate.sha(self.raw[gate.SCALA]))

    def test_cli_exit_two_is_not_acceptance(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = gate.main(['--source-root', str(ROOT)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'INCOMPLETE')

    def test_missing_input_rejected_cli(self):
        with tempfile.TemporaryDirectory(prefix='qk_gate_missing_') as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = gate.main(['--source-root', directory])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())['status'], 'REJECTED')

    def test_changed_pinned_bytes_rejected(self):
        with tempfile.TemporaryDirectory(prefix='qk_gate_hash_') as directory:
            p = Path(directory) / 'source'
            raw = self.raw[gate.SCALA]
            p.write_bytes(raw[:-1] + b' ')
            with self.assertRaisesRegex(gate.Rejected, 'SOURCE_HASH'):
                gate.read_bound(Path(directory), 'source', self.pins['sources'][gate.SCALA])

    def test_symlink_rejected_even_matching_bytes(self):
        with tempfile.TemporaryDirectory(prefix='qk_gate_symlink_') as directory:
            p = Path(directory) / 'source'
            p.symlink_to(ROOT / gate.SCALA)
            with self.assertRaisesRegex(gate.Rejected, 'SOURCE_SYMLINK'):
                gate.read_bound(Path(directory), 'source', self.pins['sources'][gate.SCALA])

    def test_paths_cannot_escape(self):
        for path in ('../source', '/tmp/source'):
            with self.subTest(path=path), self.assertRaisesRegex(gate.Rejected, 'SOURCE_PATH'):
                gate.read_bound(ROOT, path, {'bytes': 1, 'sha256': 'bad'})

    def test_patch_wrong_target_rejected(self):
        with self.assertRaisesRegex(gate.Rejected, 'PATCH_TARGET'):
            gate.apply_target_patch('one\n', '--- a/wrong\n+++ b/wrong\n@@ -1,1 +1,1 @@\n-one\n+two\n', 'source')

    def test_patch_offset_rejected(self):
        with self.assertRaisesRegex(gate.Rejected, 'PATCH_OFFSET'):
            gate.apply_target_patch('one\n', '--- a/source\n+++ b/source\n@@ -1,1 +2,1 @@\n-one\n+two\n', 'source')

    def test_patch_context_rejected(self):
        with self.assertRaisesRegex(gate.Rejected, 'PATCH_CONTEXT'):
            gate.apply_target_patch('one\n', '--- a/source\n+++ b/source\n@@ -1,1 +1,1 @@\n-wrong\n+two\n', 'source')

    def test_patch_counts_rejected(self):
        with self.assertRaisesRegex(gate.Rejected, 'PATCH_COUNTS'):
            gate.apply_target_patch('one\n', '--- a/source\n+++ b/source\n@@ -1,2 +1,1 @@\n-one\n+two\n', 'source')

    def test_json_duplicates_nonfinite_rejected(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(gate.Rejected):
                gate.strict_json(raw)

    def test_integer_evaluator_does_not_eval_code(self):
        for expr in ('__import__("os").system("false")', '-1', 'r-k', 'r**k', 'unknown', 'True'):
            with self.subTest(expr=expr), self.assertRaises(gate.Rejected):
                gate.integer(gate.expression(expr), {'r': 1, 'k': 2})

    def test_client_selected_order_not_reversed(self):
        altered = changed(self.client, 'return tuple(self.value[row][column]',
                          'return tuple(self.value[column][row]')
        with self.assertRaisesRegex(gate.Rejected, 'PYTHON_SELECTED_WORDS_ORDER'):
            gate.python_projection(self.schedule, altered)

    def test_client_selected_forwarding_not_reversed(self):
        altered = changed(self.client, 'PackedResult(self.tag, result, self.request.selected)',
                          'PackedResult(self.tag, result, tuple(reversed(self.request.selected)))')
        with self.assertRaisesRegex(gate.Rejected, 'PYTHON_RESULT_SELECTED_FORWARDING'):
            gate.python_projection(self.schedule, altered)

    def test_client_request_fields_not_reordered(self):
        altered = changed(self.client, '    steps: int\n    slice_mask: int = 1',
                          '    slice_mask: int = 1\n    steps: int')
        with self.assertRaisesRegex(gate.Rejected, 'PYTHON_RECORD_FIELDS:PackedRequest'):
            gate.python_projection(self.schedule, altered)

    def test_client_result_fields_not_reordered(self):
        altered = changed(self.client, '    service_result: object\n    selected: tuple',
                          '    selected: tuple\n    service_result: object')
        with self.assertRaisesRegex(gate.Rejected, 'PYTHON_RECORD_FIELDS:PackedResult'):
            gate.python_projection(self.schedule, altered)

    def test_client_value_forwarding_not_redirected(self):
        altered = changed(self.client, 'return self.service_result.value', 'return self.other.value')
        with self.assertRaisesRegex(gate.Rejected, 'PYTHON_RESULT_VALUE_FORWARDING'):
            gate.python_projection(self.schedule, altered)

    def test_coordinate_transpose_rejected(self):
        altered = changed(self.schedule, '(r,16*k+r)', '(r,16*r+k)')
        py = gate.python_projection(altered, self.client)
        with self.assertRaisesRegex(gate.Rejected, 'QK_SELECTED_CELL_MAPPING'):
            gate.check_coordinates(py, gate.scala_projection(self.scala))

    def test_both_scala_shifts_wrong_rejected(self):
        altered = changed(self.scala, '(packedSelected.get<<4)', '(packedSelected.get<<3)', 2)
        shift = gate.scala_projection(altered)
        with self.assertRaisesRegex(gate.Rejected, 'QK_SELECTED_CELL_MAPPING'):
            gate.check_coordinates(gate.python_projection(self.schedule, self.client), shift)

    def test_initial_and_held_selections_must_agree(self):
        altered = self.scala.replace('(packedSelected.get<<4)', '(packedSelected.get<<3)', 1)
        with self.assertRaisesRegex(gate.Rejected, 'SCALA_SELECTION_AGREEMENT'):
            gate.scala_projection(altered)

    def test_no_production_imports(self):
        for module in sys.modules:
            self.assertFalse(module.startswith(('torch', 'numpy', 'candidates.', 'heteronpu')))

    def test_fixture_unchanged(self):
        for p, raw in self.raw.items():
            self.assertEqual((ROOT / p).read_bytes(), raw)


PYTHON_MUTATIONS = {
    'qk_assigned_elsewhere': ('result=yield PackedRequest(0x23', 'other=yield PackedRequest(0x23'),
    'result_consumer_wrong': ('lanes=result.selected_words()', 'lanes=other.selected_words()'),
    'score_read_assigned_elsewhere': ("scores=(yield self.scratch('read',generation,token,kv,4096+8*h+first//16))", "other=(yield self.scratch('read',generation,token,kv,4096+8*h+first//16))"),
    'softmax_uses_other_scores': ('for score in scores[:count]:', 'for score in other[:count]:'),
    'dot_round_removed': ("o._op('bf',total)", 'total'),
    'score_round_removed': ("o._op('bf',o._op('mul',o._op('bf',total),0x3db504f3))",
                            "o._op('mul',o._op('bf',total),0x3db504f3)"),
    'fold_early_round': ("total=o._op('add',total,x)", "total=o._op('bf',o._op('add',total,x))"),
    'fold_reverse': ('for x in lanes[local*16:(local+1)*16]:', 'for x in reversed(lanes[local*16:(local+1)*16]):'),
    'fold_short': ('lanes[local*16:(local+1)*16]', 'lanes[local*16:(local+1)*16-1]'),
    'max_uses_raw_dot': ('if o._less(maxima[h],score):maxima[h]=score', 'if o._less(maxima[h],total):maxima[h]=total'),
    'score_storage_mismatch': ('4096+8*h+first//16,tuple(scores)', '4097+8*h+first//16,tuple(scores)'),
    'softmax_subtract_sign': ('score,maxima[h]^0x80000000', 'score,maxima[h]'),
    'selector_order': ('for k in range(count) for r in range(16)', 'for r in range(16) for k in range(count)'),
    'nonfinal_selection': ('for r in range(16)) if final else ()', 'for r in range(16)) if final else ((0,0),)'),
}
SCALA_MUTATIONS = {
    'initial_loop_short': ('for(i<-0 until 16){fmOut(i):=c.io.result.bits.value', 'for(i<-0 until 15){fmOut(i):=c.io.result.bits.value'),
    'selector_width_short': ('val packedSelected=if(enableProductionPackedQk16)Some(RegInit(0.U(4.W)))', 'val packedSelected=if(enableProductionPackedQk16)Some(RegInit(0.U(3.W)))'),
    'key_tail_off_by_one': ('val packedKeys=Mux(token-key>=15.U,16.U(5.W)', 'val packedKeys=Mux(token-key>=15.U,15.U(5.W)'),
    'exp_opcode_changed': ('ScalarOp.ExpNegative,scalarValue,0.U,"attExpResult"', 'ScalarOp.Add,scalarValue,0.U,"attExpResult"'),
    'dot_round_removed': ('val dotValue=materialize(scalarValue)', 'val dotValue=scalarValue'),
    'score_round_removed': ('val score=materialize(scalarValue)', 'val score=scalarValue'),
    'fold_early_round': ('ScalarOp.Add,sum,acc(lane)', 'ScalarOp.Add,materialize(sum),acc(lane)'),
    'fold_short': ('when(lane===15.U){\n    val dotValue', 'when(lane===14.U){\n    val dotValue'),
    'fold_uninitialized': ('acc:=fmOut;lane:=0.U;sum:=0.U;', 'acc:=fmOut;lane:=0.U;sum:=1.U;'),
    'scale_wrong_operand': ('ScalarOp.Mul,dotValue,F32.lit', 'ScalarOp.Mul,scalarValue,F32.lit'),
    'max_uses_unrounded': ('F32.less(maxScore,score)', 'F32.less(maxScore,scalarValue)'),
    'stored_unrounded': ('scores.write(key+packedSelected.getOrElse(0.U),score)', 'scores.write(key+packedSelected.getOrElse(0.U),scalarValue)'),
    'score_read_wrong_key': ('scores.read(key,state===st("attExpRead"))', 'scores.read(key+1.U,state===st("attExpRead"))'),
    'softmax_subtract_sign': ('ScalarOp.Add,scoreOut,F32.neg(maxScore)', 'ScalarOp.Add,scoreOut,maxScore'),
    'finite_guard_removed': ('enableProductionPackedQk16.B && !TensorMath.finite(dotValue)', 'false.B'),
    'held_short': ('val selected=VecInit((0 until 16)', 'val selected=VecInit((0 until 15)'),
}


def python_mutation(old, new):
    def test(self):
        altered = changed(self.schedule, old, new)
        with self.assertRaises(gate.Rejected):
            gate.python_projection(altered, self.client)
    return test


def scala_mutation(old, new):
    def test(self):
        altered = changed(self.scala, old, new)
        with self.assertRaises(gate.Rejected):
            gate.scala_projection(altered)
    return test


for name, pair in PYTHON_MUTATIONS.items():
    setattr(GateTests, 'test_python_mutation_' + name, python_mutation(*pair))
for name, pair in SCALA_MUTATIONS.items():
    setattr(GateTests, 'test_scala_mutation_' + name, scala_mutation(*pair))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args, rest = parser.parse_known_args()
    ROOT = args.source_root.absolute()
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
