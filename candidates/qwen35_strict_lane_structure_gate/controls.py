"""Synthetic negative controls: no JVM, compilation, elaboration or simulation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('lane_structure_gate', HERE / 'gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
gate.bounded_runtime()
PINS, SCOPE, PARSER = gate.load()


def fixture():
    rows = ['FIRRTL version 3.3.0', 'circuit StrictFp32MatrixLane :']
    for module, ports in SCOPE['module_ports'].items():
        rows.append('  module ' + module + ' :')
        rows.extend('    ' + p for p in ports)
        rows.extend('    inst ' + inst + ' of ' + target for inst, target in SCOPE['module_edges'][module])
        if module == gate.TOP:
            rows.extend('    regreset ' + k + ' : ' + v + ', clock, reset, UInt<1>(0h0)' for k, v in SCOPE['top_register_types'].items())
        if module == 'HeteroBF16FmaMul':
            rows.append('    node product = mul(io.mulAddA, io.mulAddB)')
    return '\n'.join(rows) + '\n'


BASE = fixture()
CASES = {
    'disconnected_extmodule': BASE + '  extmodule Hidden :\n',
    'disconnected_intmodule': BASE + '  intmodule Hidden :\n',
    'blackbox_marker': BASE + '    intrinsic BlackBox\n',
    'duplicate_module': BASE + '  module StrictFp32MatrixLane :\n',
    'duplicate_circuit': BASE + 'circuit StrictFp32MatrixLane :\n',
    'wrong_circuit': BASE.replace('circuit StrictFp32MatrixLane :', 'circuit Wrong :'),
    'missing_circuit': BASE.replace('circuit StrictFp32MatrixLane :\n', ''),
    'unexpected_disconnected_module': BASE + '  module Hidden :\n',
    'undefined_instance': BASE.replace('inst mul of HeteroBF16FmaMul', 'inst mul of Missing'),
    'cycle': BASE.replace('inst mul of HeteroBF16FmaMul', 'inst mul of StrictFp32MatrixLane'),
    'bad_instance_syntax': BASE.replace('inst mul of HeteroBF16FmaMul', 'inst mul : HeteroBF16FmaMul'),
    'duplicate_instance_name': BASE.replace('inst mul of HeteroBF16FmaMul', 'inst pre of HeteroBF16FmaMul'),
    'duplicate_chain': BASE.replace('inst mul of HeteroBF16FmaMul', 'inst mul of HeteroBF16FmaMul\n    inst other of HeteroBF16FmaMul'),
    'missing_edge': BASE.replace('    inst mul of HeteroBF16FmaMul\n', ''),
    'wrong_operand_width': BASE.replace('flip mulAddA : UInt<24>', 'flip mulAddA : UInt<23>', 1),
    'wrong_operand': BASE.replace('mul(io.mulAddA, io.mulAddB)', 'mul(io.mulAddA, io.mulAddA)'),
    'constant_operand': BASE.replace('mul(io.mulAddA, io.mulAddB)', 'mul(io.mulAddA, UInt<24>(1))'),
    'missing_multiplier': BASE.replace('mul(io.mulAddA, io.mulAddB)', 'add(io.mulAddA, io.mulAddB)'),
    'second_nested_multiplier': BASE.replace('mul(io.mulAddA, io.mulAddB)', 'mul(io.mulAddA, mul(io.mulAddA, io.mulAddB))'),
    'hidden_memory': BASE + '    mem hidden :\n',
    'empty_ir': '',
}


class Controls(unittest.TestCase):
    def test_positive_fixture(self):
        r = gate.structure(BASE.encode(), SCOPE, PARSER)
        self.assertEqual((r['module_count'], r['instance_count'], r['variable_mul_count']), (9, 8, 1))
        self.assertEqual(r['variable_mul_operand_bits'], [24, 24])
        self.assertEqual(r['annotation_scope'], 'absent; no external annotation claim')

    def test_empty_annotations(self):
        self.assertEqual(gate.structure(BASE.encode(), SCOPE, PARSER, b'[]')['annotation_scope'], 'explicit empty JSON array')

    def test_annotation_negative_controls(self):
        for raw in [b'[{"class":"firrtl.transforms.BlackBoxInlineAnno"}]', b'[{}]', b'{}', b'null', b'false', b'broken']:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    gate.structure(BASE.encode(), SCOPE, PARSER, raw)

    def test_frozen_ir_pin_required(self):
        # Even structurally acceptable fixtures cannot qualify as the frozen IR.
        with tempfile.TemporaryDirectory(prefix='strict_lane_structure_controls_') as temp:
            path = Path(temp) / 'fixture.fir'
            path.write_text(BASE)
            with self.assertRaisesRegex(ValueError, 'pin mismatch'):
                gate.read(path, PINS['ir'])

    def test_annotation_size_bound(self):
        with self.assertRaises(ValueError):
            gate.structure(BASE.encode(), SCOPE, PARSER, b' ' * (gate.MAX_BYTES + 1))

    def test_ir_size_bound(self):
        with self.assertRaises(ValueError):
            gate.structure(b' ' * (gate.MAX_BYTES + 1), SCOPE, PARSER)


for name, content in CASES.items():
    def test(self, content=content):
        with self.assertRaises(ValueError):
            gate.structure(content.encode(), SCOPE, PARSER)
    setattr(Controls, 'test_reject_' + name, test)

result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
if not result.wasSuccessful():
    raise SystemExit(1)
print(json.dumps({'status': 'PASS_SYNTHETIC_STRUCTURAL_CONTROLS_ONLY', 'test_methods': result.testsRun,
                  'negative_ir_cases': sorted(CASES), 'annotation_negative_cases': 6,
                  'hardware_executed': False, 'new_IR_generated': False}, indent=2, sort_keys=True))
