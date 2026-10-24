"""Pure integer logical traffic regression, not a simulated M128 execution."""
import importlib.util
from fractions import Fraction
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('_direct_traffic', Path(__file__).with_name('traffic_plan.py'))
traffic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(traffic)


class TrafficTests(unittest.TestCase):
    def test_m2_control_trace_counts(self):
        p = traffic.counts(2)
        self.assertEqual((p['direct_q_reads'], p['direct_k_reads'], p['direct_v_reads'],
                          p['output_write_acks']), (192, 288, 288, 192))
        self.assertEqual(p['direct_to_cold_cached_kv_read_ratio'], Fraction(9))

    def test_m128_counts_are_not_representation_equivalence(self):
        p = traffic.counts(128)
        self.assertEqual(p['k_extent_bytes'] + p['v_extent_bytes'], 262144)
        self.assertEqual(p['direct_kv_reads'], 1585152)
        self.assertEqual(p['direct_kv_read_bytes'], 101449728)
        self.assertEqual((p['cold_raw_cache_misses'], p['raw_cache_hits']), (4096, 1581056))
        self.assertEqual(p['direct_to_cold_cached_kv_read_ratio'], Fraction(387))
        self.assertEqual(p['direct_raw_bank_acquires'], 0)
        self.assertEqual(p['direct_raw_bank_releases'], 0)
        self.assertEqual(p['extra_payload_capacity_bytes'], 0)

    def test_all_lengths_count_actual_causal_loops(self):
        for rows in range(1, 129):
            plan = traffic.counts(rows)
            per_k = sum(12 * 8 * (token + 1) for token in range(rows))
            self.assertEqual(plan['direct_k_reads'], per_k)
            self.assertEqual(plan['direct_v_reads'], per_k)
            self.assertEqual(plan['direct_kv_reads'],
                             plan['cold_raw_cache_misses'] + plan['raw_cache_hits'])
            self.assertEqual(plan['direct_to_cold_cached_kv_read_ratio'], 3 * (rows + 1))

    def test_noncanonical_shapes_reject(self):
        for rows in (True, False, 0, 129, 128.0, '128', None):
            with self.assertRaises(ValueError):
                traffic.counts(rows)


if __name__ == '__main__':
    unittest.main()
