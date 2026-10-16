"""Publication-only regression. Original numerical/control tests are unchanged."""
import json
from pathlib import Path
import tempfile
import unittest

from candidates.qwen2_resident_matrix.sfu_silu_cycle_candidate import run_evidence as e


class SummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full = e.collect()
        cls.summary = e.summarize(cls.full)

    def test_summary_is_exact_projection_of_all96_transactions(self):
        summary = self.summary
        self.assertEqual(len(summary['transactions']), 96)
        self.assertEqual(len(summary['configurations']), 6)
        for source, item in zip(self.full['results'], summary['transactions']):
            self.assertEqual(summary['configurations'][item['configuration']], source['configuration'])
            self.assertEqual(summary['requests'][item['request']],
                             dict(case=source['case'], sha256=source['request_sha256']))
            counters = dict(zip(summary['counter_names'], summary['counter_sets'][item['counters']]))
            self.assertEqual(counters, {name: source['counts'].get(name, 0) for name in summary['counter_names']})
            numeric = summary['numerical_groups'][item['numerical']]
            expected_phases = [e.digest({k: v for k, v in p.items() if k != 'edge'})
                               for p in source['phase_trace']]
            self.assertEqual(numeric['phase_sha256'], expected_phases)
            self.assertEqual(numeric['response_sha256'], e.digest(source['response']))
            self.assertEqual(item['full_node_trace_sha256'], source['all_node_trace_sha256'])
            self.assertEqual(item['phase_capture_edges'], [p['edge'] for p in source['phase_trace']])
            for key in ('input_accept_edge', 'first_response_visible_edge', 'response_ack_edge',
                        'next_request_eligible_edge'):
                self.assertEqual(item[key], source[key])
        self.assertEqual(summary['regenerated_full_report_canonical_sha256'], e.digest(self.full))
        self.assertEqual(summary['original_full_report_sha256'], e.ORIGINAL_FULL_REPORT_SHA256)
        self.assertEqual(e.digest(self.full['results']), e.ORIGINAL_RESULTS_SHA256)

    def test_no_arithmetic_payload_arrays_or_encoded_payloads(self):
        forbidden = {'raw', 'value', 'values', 'gate', 'up', 'phase_trace', 'response',
                     'results', 'bits', 'data', 'base64', 'payload', 'blob'}

        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(self.summary)
        self.assertLess(len(json.dumps(self.summary, separators=(',', ':'))), 65536)
        # Only scheduling integers occur in the two integer-list fields.
        for counts in self.summary['counter_sets']:
            self.assertTrue(all(type(n) is int and 0 <= n < 10000 for n in counts))
        for result in self.summary['transactions']:
            self.assertTrue(all(type(n) is int and 0 <= n < 128 for n in result['phase_capture_edges']))

    def test_committed_summary_matches_current_full_collection(self):
        committed = json.loads((e.HERE / 'EVIDENCE.json').read_text())
        self.assertEqual(committed, json.loads(json.dumps(self.summary)))

    def test_full_report_cannot_be_written_in_repository_or_overwritten(self):
        with self.assertRaises(ValueError):
            e.write_evidence(full_output=e.HERE / 'unsafe_full.json')
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / 'retained.json'
            existing.write_text('immutable')
            with self.assertRaises(ValueError):
                e.write_evidence(full_output=existing)
            self.assertEqual(existing.read_text(), 'immutable')


if __name__ == '__main__':
    unittest.main()
