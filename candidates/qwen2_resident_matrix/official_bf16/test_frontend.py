"""Frontend auditor negative controls. No hardware transactions or numerical claims."""
from pathlib import Path
import tempfile
import unittest

from candidates.qwen2_resident_matrix.official_bf16 import check_frontend as front


class FrontendAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = front.module('official_front_test_helper', front.ROOT / 'scripts/check_matrix_interface_candidate.py')
        cls.register = front.module('official_front_test_register', front.TASK.parent / 'transposed_host/check_frontend.py')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='official_frontend_test_')
        self.out = Path(self.tmp.name)
        for profile in front.PROFILES:
            leaf, mode = profile.split('_')
            name = {'host': 'HostBlockCommands', 'silu': 'SiluVectorUnit', 'elementwise': 'ElementwiseMemoryEngine'}[leaf]
            body = '    input clock : Clock\n    reg state : UInt<3>, clock\n'
            if leaf == 'host' and mode == 'official':
                body += '    reg officialOutputs : UInt<64>[21], clock\n    reg officialHidden : UInt<64>, clock\n    reg officialRows : UInt<16>, clock\n'
            if leaf == 'elementwise':
                body += ''.join(f'    smem bank_{i} : UInt<8>[16] [2]\n      read mport r{i} = bank_{i}[UInt<1>(0)], clock\n      write mport w{i} = bank_{i}[UInt<1>(0)], clock\n' for i in range(16))
            if mode == 'official':
                body += '    node policy = UInt<1>(1)\n'
            (self.out / (profile + '.fir')).write_text(f'FIRRTL version 3.3.0\ncircuit {name} :\n  module {name} :\n' + body)

    def tearDown(self):
        self.tmp.cleanup()

    def audit(self):
        return front.audit(self.out, self.helper, self.register)

    def change(self, profile, old, new):
        path = self.out / (profile + '.fir')
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1))

    def test_exact_default_legacy_and_declared_metadata_delta(self):
        report = self.audit()
        self.assertEqual(report['enabled_register_delta'], {'host': 1424, 'silu': 0, 'elementwise': 0})
        self.assertFalse(report['hardware_arithmetic_executed'])
        self.assertFalse(report['numerical_acceptance'])

    def test_reject_default_legacy_difference(self):
        self.change('silu_legacy', 'UInt<3>', 'UInt<4>')
        with self.assertRaisesRegex(ValueError, 'default differs'):
            self.audit()

    def test_reject_disconnected_enabled_policy(self):
        self.change('silu_official', '    node policy = UInt<1>(1)\n', '')
        with self.assertRaisesRegex(ValueError, 'no CHIRRTL effect'):
            self.audit()

    def test_reject_hidden_payload_register(self):
        self.change('silu_official', 'UInt<3>', 'UInt<515>')
        with self.assertRaisesRegex(ValueError, 'register delta'):
            self.audit()

    def test_reject_sram_geometry_change(self):
        self.change('elementwise_official', 'UInt<8>[16] [2]', 'UInt<8>[16] [3]')
        with self.assertRaisesRegex(ValueError, 'SRAM declaration/port drift'):
            self.audit()

    def test_reject_second_memory_port(self):
        self.change('elementwise_official', 'read mport r0 =', 'read mport extra = bank_0[UInt<1>(0)], clock\n      read mport r0 =')
        with self.assertRaisesRegex(ValueError, 'SRAM declaration/port drift'):
            self.audit()

    def test_hierarchical_register_count_includes_each_instance(self):
        fir = ('circuit Top :\n  module Top :\n    reg a : UInt<2>, clock\n'
               '    inst left of Leaf\n    inst right of Leaf\n'
               '  module Leaf :\n    reg b : { x : UInt<4>, y : UInt<8>[2]}[3], clock\n')
        self.assertEqual(front.resource_inventory(fir, self.register)['hierarchical_register_bits'], 122)

    def test_reject_blackbox(self):
        self.change('silu_official', '    node policy', '  extmodule Opaque :\n    node policy')
        with self.assertRaisesRegex(ValueError, 'opaque blackbox'):
            self.audit()

    def test_diagnostic_normalization_preserves_hardware_and_assertion_text(self):
        text = '    node result = add(a, b) @[A.scala 3:4]\n    printf(clock, UInt<1>(1), "failure at A.scala:20 operand") @[A.scala 20:4]\n'
        normalized = front.normalized(text, self.helper)
        self.assertIn('add(a, b)', normalized)
        self.assertIn('failure at <source> operand', normalized)
        self.assertNotIn('@[', normalized)


if __name__ == '__main__':
    unittest.main()
