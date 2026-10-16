"""Cold M128 entry/progress controls; never execute native arithmetic."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import m128_numeric as runner
from . import profile_numeric


class M128Preparation(unittest.TestCase):
    def test_explicit_single_profile_preserves_calibration_defaults(self):
        with patch.object(profile_numeric,'_run_profiles',return_value=(2,{})) as run:
            callback=lambda *a,**kw:None
            runner.run_m128(callback)
            self.assertEqual(run.call_args.args,((128,),))
            self.assertEqual(run.call_args.kwargs['seconds'],2400.)
            self.assertIs(run.call_args.kwargs['snapshot'],runner.source_snapshot)
            profile_numeric.run_calibration()
            self.assertEqual(run.call_args.args,((4,8),))
            self.assertEqual(run.call_args.kwargs['seconds'],120.)
            self.assertNotIn('progress',run.call_args.kwargs)

    def test_missing_library_cannot_pass(self):
        with patch.dict(os.environ,{},clear=True):
            code,result=runner.run_m128(lambda *a,**kw:None)
        self.assertEqual((code,result['status']),(2,'NOT_RUN'))
        self.assertFalse(result['m128_executed'])

    def test_atomic_fixed_schema_progress_and_cadence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'progress.json';p=runner.Progress(path)
            with self.assertRaises(ValueError):p('preflight',None,1,0,0,force=True)
            for clock in (p.start-1,p.start+2401,float('nan')):
                with patch.object(runner.time,'monotonic',return_value=clock),self.assertRaises(ValueError):
                    p('preflight',None,0,0,0,force=True)
            p('preflight',None,0,0,0,force=True)
            first=path.read_bytes()
            p('reference',None,0,0,0)
            self.assertEqual(path.read_bytes(),first)
            p('direct',False,1,2,3,force=True)
            v=json.loads(path.read_bytes());self.assertEqual(v['sequence'],2)
            self.assertEqual(v['status'],'PROGRESS');self.assertLess(len(path.read_bytes()),1024)
            self.assertEqual(list(Path(tmp).iterdir()),[path])
            for args in (('direct',False,0,2,3),('reference',None,0,0,0),('loan',False,0,0,0),('loan',True,0,55480321,0),('loan',True,True,0,0)):
                with self.assertRaises(ValueError):p(*args,force=True)
            p('loan',True,1,2,3,force=True)
            with self.assertRaises(ValueError):p('complete',True,1,2,3,force=True)
            p('complete',True,1,55480320,1585152,force=True)
            self.assertEqual(json.loads(path.read_bytes())['phase'],'complete')
            with self.assertRaises(ValueError):runner.Progress(path)

    def test_workflow_scope_and_budget_are_exact(self):
        from .run_numeric_ci import repository_path
        raw=repository_path(runner.WORKFLOW).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '6054bf0c352b228b60621ed1f17bbac69c89279c8d35897cc3b3a35f8b5b031d')
        text=raw.decode()
        self.assertIn("paths: ['.github/workflows/raw-kv-attention-m128.yml']",text)
        self.assertEqual(text.count('github.run_attempt == 1'),1)
        self.assertIn('timeout-minutes: 45',text)
        self.assertEqual(text.count('run_m128_ci --out'),1)
        artifacts=text.split('          path: |\n')[1].splitlines()
        self.assertEqual([line.strip() for line in artifacts],[
            'work/raw-kv-attention-m128/'+name for name in ('summary.json','source_hashes.json','progress.json')])

    def test_exact_source_freeze_and_final_line_check(self):
        hashes=runner.source_snapshot()
        self.assertEqual(len(hashes),71)
        self.assertIn(runner.WORKFLOW,hashes)
        for name in runner.INPUTS:
            self.assertIn('candidates/qwen2_resident_matrix/raw_kv_attention/'+name,hashes)
        source=Path(profile_numeric.__file__).read_text()
        self.assertIn("bus.reads.maximum==j.c+128*1024-64",source)
        self.assertIn("owner.ack_bytes==j.write_bytes",source)


if __name__=='__main__':unittest.main()
