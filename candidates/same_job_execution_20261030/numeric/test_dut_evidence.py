import json,pathlib,tempfile,unittest
import dut_evidence as d
class T(unittest.TestCase):
 def fixture(self,p):
  report=dict(status='INCOMPLETE',layer='CHISEL_EMITTED_SV_NUMERICAL_BACKEND',final_rtl_executed=False,artifact_manifest_sha256='a'*64,runtime_bundle_sha256='b'*64,profiles=[dict(profile=0,status='INCOMPLETE',error_class='TimeoutError')])
  start=dict(schema='ACTUAL_DUT_POPEN_V1',pid=2,consumer_pid=1,consumer_start_tick=123,inherited_group=1,inherited_session=1,binary_sha256='c'*64,runtime_sha256='d'*64)
  (p/'OUTER.json').write_text(json.dumps(dict(worker_started=True,native_exit=2,errors=[],owner_identity=dict(pid=1,start=123,group=1),cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',owner_identity=dict(pid=1,start=123,group=1),session=1),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True))))
  (p/'RESULT.json').write_text(json.dumps(report));(p/'profile0.started.json').write_text(json.dumps(start));return report,start
 def verify(self,p):return d.verify(p,0,'a'*64,'b'*64,'c'*64,'d'*64,d.pin(p/'OUTER.json'))
 def test_timeout_started(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);self.fixture(p);self.assertEqual(self.verify(p)['state'],'STARTED_TIMEOUT_INCOMPLETE')
 def test_rc2_no_report(self):
  with tempfile.TemporaryDirectory()as t:
   with self.assertRaises(ValueError):self.verify(pathlib.Path(t))
 def test_preexec_no_start(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);self.fixture(p);(p/'profile0.started.json').unlink()
   with self.assertRaises(ValueError):self.verify(p)
 def test_wrong_identity_or_profile(self):
  for field,value in (('artifact_manifest_sha256','e'*64),('profiles',[{'profile':1}]),('status','PASS')):
   with tempfile.TemporaryDirectory()as t:
    p=pathlib.Path(t);r,s=self.fixture(p);r[field]=value;(p/'RESULT.json').write_text(json.dumps(r))
    with self.assertRaises(ValueError):self.verify(p)
 def test_complete_diagnostic(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);r,s=self.fixture(p);r['profiles'][0]=dict(profile=0,status='BITWISE_MATCH_DIAGNOSTIC',exit_code=0);(p/'RESULT.json').write_text(json.dumps(r));self.assertEqual(self.verify(p)['state'],'COMPLETE_TERMINAL_DIAGNOSTIC_NOT_PASS')
 def test_wrong_group(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);r,s=self.fixture(p);s['inherited_group']=9;(p/'profile0.started.json').write_text(json.dumps(s))
   with self.assertRaises(ValueError):self.verify(p)
 def test_missing_wrong_outer(self):
  for field,value in (('worker_started',False),('native_exit',1),('cleanup_proof',None),('owner_identity',dict(pid=8,start=123,group=1))):
   with tempfile.TemporaryDirectory()as t:
    p=pathlib.Path(t);self.fixture(p);r=json.loads((p/'OUTER.json').read_text());r[field]=value;(p/'OUTER.json').write_text(json.dumps(r))
    with self.assertRaises(ValueError):self.verify(p)
 def test_pid_group_session_start_drift(self):
  for field in ('consumer_pid','inherited_group','inherited_session','consumer_start_tick'):
   with tempfile.TemporaryDirectory()as t:
    p=pathlib.Path(t);r,s=self.fixture(p);s[field]+=9;(p/'profile0.started.json').write_text(json.dumps(s))
    with self.assertRaises(ValueError):self.verify(p)
if __name__=='__main__':unittest.main()
