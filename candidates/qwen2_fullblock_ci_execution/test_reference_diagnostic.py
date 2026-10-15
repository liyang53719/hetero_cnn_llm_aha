"""Cold diagnostic tests: synthetic child logs only, never prepare or math."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import reference_diagnostic as d

class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        for target,key,value in ((d,'ROOT',self.root),(d.B,'ROOT',self.root)):
            p=patch.object(target,key,value);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'GITHUB_RUN_ATTEMPT':'1'});p.start();self.addCleanup(p.stop)
        old=(d.B.AUTH,d.B.AUTH_CERT,d.B.AUTH_PINS)
        self.addCleanup(lambda:setattr(d.B,'AUTH',old[0]));self.addCleanup(lambda:setattr(d.B,'AUTH_CERT',old[1]));self.addCleanup(lambda:setattr(d.B,'AUTH_PINS',old[2]))
    def test_default_cold(self):
        with patch.object(d.B,'capture',side_effect=AssertionError()):self.assertEqual(d.run()['status'],'NOT_EXECUTED')
    def test_success_exact_call_and_local_output(self):
        def capture():print('private arbitrary output');return 99
        with patch.object(d.B,'capture',side_effect=capture):r=d.run('capture')
        self.assertEqual(r,dict(schema=1,status='SUCCESS',phase='COMPLETE',module='NONE',line=0,guard_failure=None,guard_stage='UNKNOWN',guard_comparison=None,all_comparisons=None))
        self.assertIn('private arbitrary output',(self.root/'work/ci_reference_diagnostic/capture.log').read_text())
    def test_no_repeat_output(self):
        with patch.object(d.B,'capture'):
            d.run('capture')
            with self.assertRaises(FileExistsError):d.run('capture')
    def test_rerun_refused(self):
        with patch.dict(os.environ,{'GITHUB_RUN_ATTEMPT':'2'}):
            with self.assertRaises(ValueError):d.run('capture')
    def test_safe_known_child_trace(self):
        p=self.root/d.B.LOGS/'fresh_bindings.log';p.parent.mkdir(parents=True)
        p.write_text('secret-output\n  File "'+str(self.root/d.FILES['RECIPE'])+'", line 196, in metadata_check\nSECRET tensor data\n  File "/private/secret.py", line 25, in f\n')
        with p.open('a') as stream:stream.write('  File \"'+str(self.root/d.FILES['ORIGINAL_RECIPE'])+'\", line 50, in need\n')
        self.assertEqual(d.log_location('fresh_bindings'),('RECIPE',196))
    def test_unknown_or_oversized_log(self):
        self.assertEqual(d.log_location('fresh_bindings'),('OTHER',0))
        p=self.root/d.B.LOGS/'fresh_bindings.log';p.parent.mkdir(parents=True)
        with p.open('wb') as f:f.truncate(16*(1<<20)+1)
        self.assertEqual(d.log_location('fresh_bindings'),('OTHER',0))
    def test_child_failure_keeps_phase(self):
        def capture():d.B.call('recipe.py',['--prepare-bindings'],'fresh_bindings')
        with patch.object(d.B,'capture',side_effect=capture),patch.object(d.B,'call',side_effect=ValueError('secret')),patch.object(d,'log_location',return_value=('RECIPE',196)):
            r=d.run('capture')
        self.assertEqual((r['status'],r['phase'],r['module'],r['line']),('FAILED','BINDINGS','RECIPE',196))
        self.assertNotIn('secret',str(r))
    def test_aggregate_phase(self):
        def capture():
            d.B.call('guard.py',[],'reference_guard');raise ValueError('secret')
        with patch.object(d.B,'capture',side_effect=capture),patch.object(d.B,'call',return_value=0):r=d.run('capture')
        self.assertEqual(r['phase'],'AGGREGATE')
    def test_reject_extra_fields_and_bool_line(self):
        for key,value in [('path','secret'),('line',True),('module','private'),('phase','private')]:
            r=d.run();r[key]=value
            with self.assertRaises(ValueError):d.checked(r)
    def test_guard_failure_projection_prefers_worker(self):
        import json
        sup=d.F.project(ValueError('private'), 'SUPERVISOR', self.root)
        worker=d.F.project(TypeError('private'), 'WORKER', self.root)
        p=self.root/d.B.LOGS/'reference_guard.log';p.parent.mkdir(parents=True)
        p.write_text(json.dumps(sup)+'\n')
        p=self.root/d.B.WORK/'ci01/bootstrap';p.mkdir(parents=True)
        (p/'stderr.log').write_text('private non-json\n'+json.dumps(worker)+'\n'+json.dumps({'status':'WORKER_FAILED_UNSEALED','error':'private'})+'\n')
        (p/'STAGES.jsonl').write_text(json.dumps({'stage':'numeric-import-and-runtime-identity','secret':'private'})+'\n')
        record,stage,comparison,all_records=d.guard_observation()
        self.assertEqual(record,worker);self.assertEqual(stage,'numeric-import-and-runtime-identity')
        self.assertNotIn('private',str((record,stage)))
    def test_guard_unknown_records_are_not_forwarded(self):
        import json
        p=self.root/d.B.WORK/'ci01/bootstrap';p.mkdir(parents=True)
        (p/'stderr.log').write_text(json.dumps({'status':'CI_REFERENCE_FAILURE','error':'secret'})+'\n')
        (p/'STAGES.jsonl').write_text(json.dumps({'stage':'private path'})+'\n')
        self.assertEqual(d.guard_observation(),(None,'UNKNOWN',None,None))
    def test_guard_nested_extra_field_refused(self):
        r=d.run();r['guard_failure']=d.F.project(ValueError(),'WORKER',self.root)
        r['guard_failure']['path']='secret'
        with self.assertRaises(ValueError):d.checked(r)
    def test_unknown_cli_text_never_leaves_output(self):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):code=d.main(['--private-secret'])
        self.assertEqual(code,1);self.assertNotIn('private-secret',stream.getvalue())
        self.assertEqual(d.checked(__import__('json').loads(stream.getvalue()))['status'],'FAILED')
    def test_unrecognized_action_does_not_execute(self):
        with patch.object(d.B,'capture') as c:
            with self.assertRaises(ValueError):d.run('actual')
            c.assert_not_called()
    def test_comparison_only_fixed_record_forwarded(self):
        import json
        comparison=dict(schema=1,status='CI_REFERENCE_COMPARISON',node='NODE_06',categories=['HASH','STRIDE'],mismatch_count=4)
        p=self.root/d.B.WORK/'ci01/bootstrap';p.mkdir(parents=True)
        (p/'stderr.log').write_text(json.dumps(comparison)+'\n'+json.dumps({**comparison,'actual_hash':'private'})+'\n')
        _,_,observed,_=d.guard_observation()
        self.assertEqual(observed,comparison)
        result=d.run();result['guard_comparison']=observed;d.checked(result)
        result['guard_comparison']['actual_shape']=[1,2]
        with self.assertRaises(ValueError):d.checked(result)

    def test_all_existing_comparisons_strictly_forwarded(self):
        import json
        value=dict(schema=1,status='CI_REFERENCE_ALL_COMPARISONS',scope='EXISTING_OUTPUTS_ONLY',
                   compared_count=29,numeric_acceptance_claimed=False,
                   records=[dict(node=node,categories=[],mismatch_count=0) for node in d.ACD.NODES])
        p=self.root/d.B.WORK/'ci01/bootstrap';p.mkdir(parents=True)
        (p/'stderr.log').write_text(json.dumps(value)+'\n'+json.dumps({**value,'tensor':'private'})+'\n')
        *_,observed=d.guard_observation();self.assertEqual(observed,value)
        result=d.run();result['all_comparisons']=observed;d.checked(result)
        result['all_comparisons']['records'][0]['actual_hash']='private'
        with self.assertRaises(ValueError):d.checked(result)

if __name__=='__main__':unittest.main()
