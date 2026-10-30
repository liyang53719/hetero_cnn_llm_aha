import unittest,copy,hashlib,json,pathlib,tempfile
import audit as a
class Test(unittest.TestCase):
 def test_module_same(self):
  row=dict(module='HostBlockTopV4',raw_sha256='a'*64,normalized_sha256='b'*64)
  r=a.module_diff([row],[row]);self.assertEqual(r['normalized_unchanged_count'],1);self.assertFalse(r['acceptance_authorized'])
 def test_unknown_change_not_accepted(self):
  x=dict(module='Matrix',raw_sha256='a'*64,normalized_sha256='b'*64);r=a.module_diff([x],[dict(x,normalized_sha256='c'*64)])
  self.assertEqual(r['changed_outside_eight_observer_names'],['Matrix']);self.assertFalse(r['acceptance_authorized'])
 def test_raw_only(self):
  x=dict(module='Matrix',raw_sha256='a'*64,normalized_sha256='b'*64);r=a.module_diff([x],[dict(x,raw_sha256='c'*64)])
  self.assertEqual(r['raw_only_changed'],['Matrix']);self.assertEqual(r['normalized_changed'],[])
 def test_missing_receipt_never_stop(self):
  with tempfile.TemporaryDirectory()as d:
   p=pathlib.Path(d);r=dict(schema='FRONTEND_QUALIFICATION_UNAVAILABLE_V1',status='OBSERVATION_UNAVAILABLE',artifact_identity=a.IDENTITY,archive_link_executed=False,numerical_pass=False,sv_accepted=False);b=(json.dumps(r)+'\n').encode();(p/'frontend-qualification.json').write_bytes(b)
   s=dict(schema='OBSERVER_FRONTEND_SAFE_SUMMARY_V1',status='OBSERVATION_UNAVAILABLE',artifact_identity=a.IDENTITY,qualification_file=dict(name='frontend-qualification.json',bytes=len(b),sha256=a.sha(b)),archive_link_executed=False,numerical_pass=False,sv_accepted=False,full_block_profiles_completed=0,final_rtl_replay=False);(p/'frontend-summary.json').write_text(json.dumps(s))
   self.assertEqual(a.audit(p)['status'],'OBSERVATION_UNAVAILABLE_OR_INCOMPLETE_NOT_TASK_STOP')
   r['numerical_pass']=True;b=json.dumps(r).encode();(p/'frontend-qualification.json').write_bytes(b);s['qualification_file'].update(bytes=len(b),sha256=a.sha(b));(p/'frontend-summary.json').write_text(json.dumps(s))
   with self.assertRaises(ValueError):a.audit(p)
 def test_full_projection_synthetic_never_accepts_sv(self):
  import sys
  from unittest.mock import patch
  sys.path.insert(0,str(a.Q));sys.path.insert(0,str(a.ROOT/'candidates/ci_frontend_pipeline_r2_20261029'))
  import export_metadata as e
  import test_observer_frontend_qualification as fixture
  raw,_=fixture.fixture();raw['artifact_identity']=a.IDENTITY;raw['source_commit']=a.IDENTITY['source_commit']
  with tempfile.TemporaryDirectory()as d:
   p=pathlib.Path(d);b=(json.dumps(raw)+'\n').encode();(p/'frontend-qualification.json').write_bytes(b)
   stage=dict(strict_complete=True,native_exit=0,error_count=0,cleanup_complete=True,pipe_eof_observed=True,gzip_finalized=True)
   s=dict(schema='OBSERVER_FRONTEND_SAFE_SUMMARY_V1',status='FRONTEND_QUALIFICATION_OBSERVED_UNREVIEWED',artifact_identity=a.IDENTITY,qualification_file=dict(name='frontend-qualification.json',bytes=len(b),sha256=a.sha(b)),archive_link_executed=False,numerical_pass=False,sv_accepted=False,full_block_profiles_completed=0,final_rtl_replay=False,stages=[dict(stage,name=n)for n in (*e.PREP,*e.INNER)],cpu_capability_observation=raw['cpu_capability_observation']);(p/'frontend-summary.json').write_text(json.dumps(s))
   with patch.object(e,'checker',return_value=fixture.m),patch.object(fixture.m,'GLOBAL_MK_SHA',hashlib.sha256(b'SYNTHETIC_GLOBAL_MAKE_TEST_ONLY\n').hexdigest()):
    r=a.audit(p);self.assertFalse(r['acceptance_authorized']);self.assertEqual(r['ports']['total'],122);self.assertEqual(r['module_difference']['added'],['fake_fixture'])
if __name__=='__main__':unittest.main()
