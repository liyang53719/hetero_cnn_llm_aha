"""Runner evidence retention/observer dispatch; no large arithmetic job."""
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest import mock

from . import run_norm_rope as runner

class RunnerEvidenceTests(unittest.TestCase):
    def test_actual_observer_dispatch_duplicate_and_partial_snapshot(self):
        records={r:runner.ObservationRecorder(16,h,k) for r,h,k in
            (('q_norm',8,'norm'),('k_norm',2,'norm'),('q_rope',8,'rope'),('k_rope',2,'rope'))}
        owner=N(job=N(role=0));cb=runner.observation_sink(records,owner,'norm')
        cb('sum',0,0,(0x80000000,))
        with self.assertRaises(ValueError):cb('sum',0,0,(0,))
        owner.job=N(role=1);cb('sum',0,0,(0x3f800000,))
        observed={r:x.events for r,x in records.items()}
        with tempfile.TemporaryDirectory() as tmp:
            result=runner.freeze_observations(Path(tmp),'cold16',observed,prefix='failure_observations')
            self.assertEqual(set(result),{'q_norm.sum','k_norm.sum'})
            self.assertEqual((Path(tmp)/result['q_norm.sum']['file']).read_bytes(),struct.pack('<I',0x80000000))
            self.assertEqual(result['q_norm.sum']['rows'],[[0,0]])
            self.assertEqual(result['q_norm.sum']['widths'],[1])
            with self.assertRaises(FileExistsError):runner.freeze_observations(Path(tmp),'cold16',observed,prefix='failure_observations')

    def test_early_input_failure_retains_original_and_source_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'run'
            with mock.patch.object(runner.fixture,'load_fixture',side_effect=ValueError('fixed input rejected')):
                with self.assertRaisesRegex(ValueError,'fixed input rejected'):
                    runner.run('/unused-capture','/unused-payload',output,budget_seconds=1)
            report=json.loads((output/'summary.json').read_text())
            self.assertEqual(report['status'],'FAILED')
            self.assertEqual(report['error'],dict(type='ValueError',message='fixed input rejected'))
            self.assertEqual(report['windows'],[]);self.assertEqual(report['actual_outputs'],{})
            self.assertIsNone(report['active_at_failure']);self.assertEqual(report['evidence_preservation_errors'],[])
            for path,digest in report['source_sha256'].items():
                self.assertEqual(runner.sha((output/'source_snapshot'/path).read_bytes()),digest)
            with self.assertRaisesRegex(ValueError,'fresh directory'):
                runner.run('/unused-capture','/unused-payload',output,budget_seconds=1)

if __name__=='__main__':unittest.main()
