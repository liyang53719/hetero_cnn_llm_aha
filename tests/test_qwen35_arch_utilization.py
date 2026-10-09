from fractions import Fraction
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.qwen35_arch_utilization import SOURCE_BASE, SOURCE_PINS, report, verify_sources


class Qwen35ArchitecturalBoundsTests(unittest.TestCase):
    def test_pinned_sources_and_exact_m1_bound(self):
        r = report(repo=ROOT)
        self.assertTrue(r['source_pins_verified'])
        self.assertEqual(r['physical_matrix_macs_per_cycle'], 4096)
        self.assertEqual(r['useful_matrix_macs'], 21528576)
        self.assertEqual(r['dense_issue_cycles_lower_bound'], 84992)
        self.assertEqual(r['scalar_recurrence']['basic_requests'], 1839104)
        self.assertEqual(r['scalar_recurrence']['multiply_requests'], 1050624)
        self.assertEqual(r['scalar_recurrence']['add_requests'], 788480)
        self.assertEqual(r['lower_bound_cycles'], 5602304)
        exact = r['upper_bound_utilization_exact']
        self.assertEqual(Fraction(exact['numerator'], exact['denominator']), Fraction(21528576, 4096 * 5602304))
        self.assertLess(r['upper_bound_utilization'], 0.001)

    def test_full_resource_denominator_and_padding_separate(self):
        r = report()
        by_name = {x['name']: x for x in r['dense']}
        self.assertEqual(by_name['qkv']['geometry_utilization_upper_bound'], 1 / 16)
        self.assertEqual(by_name['ab']['geometry_utilization_upper_bound'], 1 / 128)
        self.assertEqual(r['issued_physical_lane_macs'], 16 * r['useful_matrix_macs'])
        self.assertAlmostEqual(r['dense_geometry_utilization_upper_bound'], 0.061841114457831324)
        self.assertIsNone(r['source_hashes'])
        self.assertFalse(r['source_pins_verified'])

    def test_bounds_never_presented_as_predictions_or_measurements(self):
        r = report()
        for name in ('predicted_cycles', 'predicted_utilization', 'rtl_measured_cycles', 'rtl_measured_utilization'):
            self.assertIsNone(r[name])
        self.assertIsNone(r['scalar_recurrence']['mac_equivalence'])
        self.assertEqual(r['scalar_recurrence']['additional_exp_requests_excluded'], 16)
        self.assertIn('not a calibrated cycle prediction', r['warning'])

    def test_m128_and_non_m1_rejected(self):
        for tokens in (0, 2, 16, 128, -1, True, 1.0):
            with self.subTest(tokens=tokens), self.assertRaisesRegex(ValueError, 'M1'):
                report(tokens=tokens)

    def test_changed_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / SOURCE_BASE / next(iter(SOURCE_PINS))
            p.parent.mkdir(parents=True)
            p.write_text('// unreviewed scheduling change')
            with self.assertRaisesRegex(ValueError, 're-audit'):
                verify_sources(Path(tmp))


if __name__ == '__main__':
    unittest.main()
