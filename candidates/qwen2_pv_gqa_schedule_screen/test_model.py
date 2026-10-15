"""Cheap static checks, deliberately not numerical/RTL acceptance."""
from fractions import Fraction
import unittest

import model as m


class StaticScreenTests(unittest.TestCase):
    def test_m128_exact_geometry(self):
        r = m.report()
        self.assertEqual(r['candidate']['cohorts'], 48)
        self.assertEqual(r['candidate']['matrix_issue_steps'], 3216)
        self.assertEqual(r['candidate']['causal_useful_fmas'], 12681216)
        self.assertEqual(r['candidate']['row_final_captures'], 1536)
        self.assertEqual(r['candidate']['emitted_wide_values_if_row_final_only'], 288)
        self.assertEqual(r['candidate']['useful_over_issued_4096_geometry'], m.ratio(Fraction(129, 134)))
        self.assertEqual(r['original'], dict(qk_steps=792576, pv32_steps=396288, attention_steps=1188864))

    def test_geometry_independent_closed_form(self):
        # 768 query/head rows per KV head, flattened query-major, cohorts32.
        ends = [((32 * group + 5) // 6) for group in range(1, 25)]
        self.assertEqual(2 * sum(ends), 3216)
        self.assertEqual(12 * 128 * 129 // 2 * 128, 12681216)

    def test_all_coordinates_unique_and_same_KV(self):
        covered = []
        for tile in m.cohorts():
            self.assertEqual(len(tile.rows), 32)
            self.assertTrue(all(head // 6 == tile.kv_head for _, head in tile.rows))
            covered.extend(tile.rows)
        self.assertEqual(len(covered), len(set(covered)))
        self.assertEqual(set(covered), {(q, h) for q in range(128) for h in range(12)})

    def test_transposed_mapping_covers_exact_existing_array(self):
        cells = {m.physical_cell(r, d) for r in range(32) for d in range(128)}
        self.assertEqual(cells, {(r, c) for r in range(16) for c in range(256)})

    def test_probability_and_capture_storage_disjoint(self):
        p = {(b, w, byte + offset)
             for c in range(5) for k in range(128) for r in range(32)
             for b, w, byte in [m.probability_cell(c, k, r)] for offset in range(2)}
        cap = {(b, w, byte + offset)
               for r in range(32) for d in range(128)
               for b, w, byte in [m.capture_cell(r, d)] for offset in range(4)}
        self.assertEqual(len(p), 40960)
        self.assertEqual(len(cap), 16384)
        self.assertFalse(p & cap)
        self.assertTrue(all(b < 16 and w < 160 and byte < 32 for b, w, byte in p | cap))

    def test_port_capacity_and_same_address_rejection(self):
        for context in range(5):
            for key in (0, 127):
                reads = [('read', *x) for x in m.gather_reads(context, key)]
                writes = [('write', 'B', bank, 128) for bank in range(16)]
                m.check_port_batch(reads + writes)
        for invalid in (
            [('read', 'A', 0, 0), ('read', 'A', 0, 1)],
            [('write', 'B', 0, 1), ('write', 'B', 0, 2)],
            [('read', 'B', 0, 0), ('write', 'B', 0, 0)],
            [('read', 'B', 0, 160)],
        ):
            with self.assertRaises(ValueError):
                m.check_port_batch(invalid)

    def test_fullblock_bound_counts_each_shared_issue_once(self):
        b = m.report()['fullblock_bound']
        self.assertEqual(b['useful_fmas'], 6014828544)
        self.assertEqual(b['ideal_dense_issues'], 1462272)
        self.assertEqual(b['all_nonmatrix_work_and_pv_free_cycles_lower_bound'], 2254848)
        expected = Fraction(6014828544, 4096 * 2254848)
        self.assertEqual(b['fixed4096_utilization_upper_bound_pv_free'], m.ratio(expected))
        self.assertLess(expected, Fraction(4, 5))
        self.assertEqual(b['candidate_pv_and_all_nonmatrix_free_cycles_lower_bound'], 2258064)

    def test_short_cold_shapes_and_invalid_requests(self):
        for tokens in (1, 2, 5, 16, 31, 32, 127):
            r = m.report(tokens)
            self.assertEqual(r['candidate']['row_final_captures'], tokens * 12)
            self.assertEqual(r['candidate']['causal_useful_fmas'], 12 * tokens * (tokens + 1) // 2 * 128)
        for bad in (0, 129, True, 1.0):
            with self.assertRaises(ValueError):
                tuple(m.cohorts(bad))
        for args in ((5, 0, 0), (0, 128, 0), (0, 0, 32)):
            with self.assertRaises(ValueError):
                m.probability_cell(*args)

    def test_never_upgrades_unimplemented_candidate(self):
        r = m.report()
        self.assertEqual(r['status'], 'STATIC_ONLY_CANDIDATE_BLOCKED')
        self.assertIsNone(r['hardware_cycles'])
        self.assertIsNone(r['hardware_utilization'])
        self.assertIsNone(r['predicted_full_block_cycles'])
        self.assertFalse(r['actual_model_run'])
        self.assertFalse(r['actual_numeric_run'])
        self.assertFalse(r['actual_rtl_run'])
        self.assertFalse(r['capacity']['physical_ports_connected'])
        self.assertTrue(any('signed-zero' in x for x in r['blockers']))
        self.assertTrue(any('emit==last' in x for x in r['blockers']))
        self.assertTrue(all(len(x) == 64 for x in r['source_sha256'].values()))


if __name__ == '__main__':
    unittest.main()
