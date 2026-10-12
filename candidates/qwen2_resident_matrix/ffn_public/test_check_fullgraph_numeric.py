"""Whole-terminal and source admission tests; no checkpoint/RTL execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from candidates.qwen2_resident_matrix.ffn_public import check_fullgraph_numeric as c


class FullgraphCaptureTests(unittest.TestCase):
    def receipt(self):
        snapshot = dict(source_sha256={'source': 'a'*64}, binaries={'binary': 'b'*64}, input_spec={'input': 'c'*64})
        match = dict(independent_bit_mismatches=0, saved_bit_mismatches=0,
                     actual_sha256='d'*64, independent_sha256='d'*64, saved_sha256='d'*64)
        prior = dict(status='PASS_PUBLIC21_FULLGRAPH_SOFTWARE_NOT_NATIVE_ACCEPTED', rows=16,
            **snapshot, source_sha256_after=snapshot['source_sha256'], execution={'host': dict(
                launch_result=dict(status=None, completed=21, jobs=17),
                completions=[dict(pc=i, status=None) for i in range(21)], reset_required=False,
                accepted=dict(result_fire=1, completion_fire=21, request_fire=17, owner_result_fire=17))},
            comparison=dict(whole_outputs={n: dict(match, values=16*w) for n, w in c.STAGE_WIDTHS.items()},
                prefix_outputs={'outputs': {n: dict(match, values=16*(512 if n == 'kv' else
                    1536 if n in ('n0', 'qraw', 'qr', 'q') else 256)) for n in c.base.OUTPUTS}}))
        return prior, snapshot

    def check(self, prior, snapshot):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'summary.json'; path.write_bytes(c.encoded(prior))
            return c.prerequisite(path, c.file_sha(path), snapshot)

    def test_exact_same_source_m16_terminal_and_comparisons_required(self):
        prior, snapshot = self.receipt()
        self.assertEqual(len(self.check(prior, snapshot)['sha256']), 64)
        for change in ('failed', 'rows', 'source', 'binary', 'input', 'after'):
            p = copy.deepcopy(prior)
            if change == 'failed': p['status'] = 'FAILED'
            elif change == 'rows': p['rows'] = 128
            elif change == 'after': p['source_sha256_after'] = {}
            else: p[{'source':'source_sha256', 'binary':'binaries', 'input':'input_spec'}[change]] = {}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check(p, snapshot)

    def test_no_opaque_completion_replay_or_poisoned_terminal(self):
        prior, snapshot = self.receipt()
        for key, value in (('result_fire', 0), ('result_fire', 2), ('completion_fire', 20),
                           ('owner_result_fire', 16), ('request_fire', 18)):
            p = copy.deepcopy(prior); p['execution']['host']['accepted'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.check(p, snapshot)
        for mutation in ('pc', 'status', 'poison', 'jobs'):
            p = copy.deepcopy(prior); h = p['execution']['host']
            if mutation == 'pc': h['completions'][19]['pc'] = 18
            elif mutation == 'status': h['completions'][20]['status'] = 'Memory'
            elif mutation == 'poison': h['reset_required'] = True
            else: h['launch_result']['jobs'] = 16
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.check(p, snapshot)

    def test_all_intermediate_and_raw_projection_comparisons_required(self):
        prior, snapshot = self.receipt()
        for node in ('whole_outputs', 'prefix_outputs'):
            for mutation in ('missing', 'mismatch', 'hash'):
                p = copy.deepcopy(prior)
                outputs = p['comparison'][node]
                if node == 'prefix_outputs': outputs = outputs['outputs']
                key = next(iter(outputs))
                if mutation == 'missing': del outputs[key]
                elif mutation == 'mismatch': outputs[key]['independent_bit_mismatches'] = 1
                else: outputs[key]['independent_sha256'] = 'f'*64
                with self.subTest(node=node, mutation=mutation), self.assertRaises(ValueError):
                    self.check(p, snapshot)

    def test_summary_hash_and_explicit_m16_receipt_cannot_be_omitted(self):
        _, snapshot = self.receipt()
        for path, digest in ((None, None), ('not-a-file', None)):
            with self.assertRaisesRegex(ValueError, 'exact completed M16'):
                c.prerequisite(path, digest, snapshot)


if __name__ == '__main__':
    unittest.main()
