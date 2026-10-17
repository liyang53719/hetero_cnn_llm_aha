"""Small isolated source tests; synthetic Python behavior, no C++/model/RTL run."""
import ast
import hashlib
import json
import re
import unittest
from dataclasses import replace
from pathlib import Path

from hold_contract_cold import Hold, Observation, normal_result

HERE = Path(__file__).resolve().parent


class SourceOnlyCold(unittest.TestCase):
    def test_01_project_source_hashes(self):
        records = json.loads((HERE / 'PROJECT_SOURCE_HASHES.json').read_text())
        self.assertEqual(set(records['copied_unchanged']),
                         {'axi_protocol.hpp', 'hold_contract_cold.py'})
        self.assertEqual(set(records['new_test_source']), {'test_source_only_cold.py'})
        for section in ('copied_unchanged', 'new_test_source'):
            for name, record in records[section].items():
                data = (HERE / name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
                self.assertEqual(len(data), record['bytes'])

    def test_02_python_sources_parse_without_execution(self):
        for name in ('hold_contract_cold.py', 'test_source_only_cold.py'):
            ast.parse((HERE / name).read_text(), filename=name)

    def test_03_unchanged_header_is_self_contained_source_text(self):
        text = (HERE / 'axi_protocol.hpp').read_text()
        self.assertFalse(re.search(r'#\s*include\s*"', text))
        for expected in ('class IndependentLedger', 'struct Sample', 'struct Ledger',
                         'unexpected/duplicate/early B', 'RLAST mismatch', 'WLAST mismatch',
                         'counts_.ar_id == counts_.rlast_id',
                         'counts_.aw_id == counts_.b_id'):
            self.assertIn(expected, text)
        self.assertNotRegex(text, r'\b(?:main|system|popen)\s*\(')

    def test_04_normal_result_value_contract(self):
        normal_result(0, 21, 20, 7)
        for fields in ((1, 21, 20, 7), (0, 20, 20, 7), (0, 22, 20, 7),
                       (0, 21, 65535, 7), (0, 21, 19, 7), (0, 21, 20, 8)):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                normal_result(*fields)

    def test_05_all_request_offers_rejected_at_first_sample(self):
        for field in ('ar', 'aw', 'w'):
            hold = Hold()
            with self.subTest(field=field), self.assertRaises(ValueError):
                hold.observe(1, replace(Observation(), **{field: True}))
            self.assertIsNone(hold.snapshot)

    def test_06_all_request_offers_rejected_while_held(self):
        for field in ('ar', 'aw', 'w'):
            hold, observation = Hold(), Observation()
            hold.observe(1, observation)
            with self.subTest(field=field), self.assertRaises(ValueError):
                hold.observe(1, replace(observation, **{field: True}))

    def test_07_both_debts_must_remain_zero(self):
        for field in ('axi_debt', 'physical_debt'):
            hold, observation = Hold(), Observation()
            hold.observe(1, observation)
            with self.subTest(field=field), self.assertRaises(ValueError):
                hold.observe(1, replace(observation, **{field: 1}))

    def test_08_all_cumulative_activity_is_frozen(self):
        changes = (
            ('issued', 2), ('axi_counts', (1, 0, 0, 0, 0)),
            ('hub_counts', (1, 0, 0, 0)), ('owner_activity', (2, 2)),
            ('matrix_loan_prefix_activity', (1, 1, 0, 0, 0, 0)),
            ('matrix_loan_prefix_activity', (0, 0, 1, 1, 0, 0)),
            ('matrix_loan_prefix_activity', (0, 0, 0, 0, 1, 1)),
        )
        for field, value in changes:
            hold, observation = Hold(), Observation()
            hold.observe(1, observation)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                hold.observe(1, replace(observation, **{field: value}))

    def test_09_word_stability(self):
        hold, observation = Hold(), Observation()
        hold.observe(1, observation)
        with self.assertRaises(ValueError):
            hold.observe(2, observation)

    def test_10_actual_ack_is_required(self):
        for valid, ready in ((False, False), (False, True), (True, False)):
            hold, observation = Hold(), Observation()
            hold.observe(1, observation)
            with self.subTest(valid=valid, ready=ready), self.assertRaises(ValueError):
                hold.ack(1, observation, valid, ready)
            self.assertFalse(hold.released)

    def test_11_ack_sample_is_checked(self):
        hold, observation = Hold(), Observation()
        hold.observe(1, observation)
        with self.assertRaises(ValueError):
            hold.ack(1, replace(observation, ar=True), True, True)
        self.assertFalse(hold.released)

    def test_12_unchanged_hold_compares_once(self):
        hold, observation = Hold(), Observation()
        for _ in range(4):
            hold.observe(1, observation)
        self.assertEqual(hold.compares, 1)
        hold.ack(1, observation, True, True)
        self.assertTrue(hold.released)
        self.assertEqual(hold.compares, 1)

    def test_13_released_hold_cannot_restart(self):
        hold, observation = Hold(), Observation()
        hold.ack(1, observation, True, True)
        with self.assertRaises(ValueError):
            hold.observe(1, observation)
        with self.assertRaises(ValueError):
            hold.ack(1, observation, True, True)

    def test_14_terminal_style_snapshot_survives_until_explicit_release(self):
        hold = Hold()
        observation = Observation(issued=17, owner_activity=(17, 17))
        hold.observe(21, observation)
        hold.observe(21, observation)
        with self.assertRaises(ValueError):
            hold.observe(21, replace(observation, owner_activity=(18, 18)))
        self.assertEqual(hold.snapshot, observation)
        self.assertFalse(hold.released)


if __name__ == '__main__':
    unittest.main(verbosity=2)
