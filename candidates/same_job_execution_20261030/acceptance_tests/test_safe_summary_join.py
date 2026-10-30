"""Only synthetic fixture receipt wiring. No real DUT/reference execution."""
import copy,importlib.util,json,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'numeric'))
import required_acceptance as a
import dut_evidence as d
from test_required_acceptance import row,H
spec=importlib.util.spec_from_file_location('safe_summary_candidate',ROOT/'summarize_same_job.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
ID=dict(run_id=123,source_commit='a'*40,launch_commit='b'*40,launch_manifest_path='ci_launch/fixture.json',launch_manifest_blob_sha='c'*40,artifact_name='fixture')

class Tests(unittest.TestCase):
 def setup_fixture(self,p,profiles=range(5)):
  numeric=p/'materials/numeric';numeric.mkdir(parents=True);records=[]
  for i in profiles:
   out=numeric/f'profile{i}/material/dut_result';out.mkdir(parents=True)
   r=row(i);r.update(status='INCOMPLETE',numerical_pass=False);r['qualification']=a.evaluate(r)
   report=dict(status='INCOMPLETE',numerical_pass=False,layer=a.LAYER,final_rtl_executed=False,artifact_manifest_sha256=H,runtime_bundle_sha256=H,profiles=[r],matrix_macs=4096,vector_lanes=32,common={k:dict(sha256=H)for k in ('binary','sv','source_manifest','driver')},artifact_identity=ID)
   (out/'RESULT.json').write_text(json.dumps(report))
   start=dict(schema='ACTUAL_DUT_POPEN_V1',binary_sha256=H,runtime_sha256=H,pid=12+i*2,consumer_pid=11+i*2,consumer_start_tick=42+i,inherited_group=11+i*2,inherited_session=11+i*2)
   (out/f'profile{i}.started.json').write_text(json.dumps(start))
   leader=dict(pid=11+i*2,start=42+i,group=11+i*2)
   outer=dict(worker_started=True,native_exit=2,errors=[],owner_identity=leader,cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',owner_identity=leader,session=leader['group']),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True))
   op=numeric/f'runs/p{i}_dut/RESULT.json';op.parent.mkdir(parents=True);op.write_text(json.dumps(outer))
   record=d.verify(out,i,H,H,H,H,d.pin(op));records.append(record)
   (numeric/f'PROFILE_{i}_DIAGNOSTIC.json').write_text(json.dumps(record))
  q=a.aggregate(records);n=numeric/'RESULT.json';n.write_text(json.dumps(dict(actual_dut_reports=records,qualification=q,status=q['status'],numerical_pass=q['numerical_pass'])))
  flow=dict(identity={k:ID[k]for k in ('run_id','source_commit','launch_commit')},execution_mode='BOUNDED_CALIBRATION',transport_exit_code=2,numeric_result=d.pin(n),hardware_definitions=1,profiles=list(range(5)),uploaded_payloads=False,qualification=q,status=q['status'])
  (p/'FLOW_RESULT.json').write_text(json.dumps(flow));return numeric
 def test_full_fixture_reaggregates_without_paths(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);self.setup_fixture(p);r=s.numeric_qualification_projection(p,ID)
   self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertTrue(r['numerical_pass']);self.assertEqual(len(r['profiles']),5)
   self.assertNotIn(t,json.dumps(r));self.assertFalse(r['final_rtl_executed'])
 def test_four_is_not_five(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);self.setup_fixture(p,range(1,5));r=s.numeric_qualification_projection(p,ID)
   self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertFalse(r['numerical_pass']);self.assertEqual(r['qualification']['missing_profiles'],[0])
 def test_flow_missing_not_completion(self):
  with tempfile.TemporaryDirectory()as t:
   self.assertFalse(s.numeric_qualification_projection(pathlib.Path(t),ID)['numerical_pass'])
 def test_mutated_outer_blocks_projection(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);n=self.setup_fixture(p);f=n/'runs/p1_dut/RESULT.json';r=json.loads(f.read_text());r['log_capture']['pipe_eof_observed']=False;f.write_text(json.dumps(r))
   self.assertFalse(s.numeric_qualification_projection(p,ID)['numerical_pass'])
 def test_copied_pass_or_wrong_identity_blocked(self):
  for field,value in [('numeric_result',dict(path='/tmp/copied',bytes=1,sha256=H)),('identity',dict(run_id=124)),('qualification',dict(status='PASS'))]:
   with tempfile.TemporaryDirectory()as t:
    p=pathlib.Path(t);self.setup_fixture(p);f=p/'FLOW_RESULT.json';r=json.loads(f.read_text());r[field]=value;f.write_text(json.dumps(r))
    self.assertFalse(s.numeric_qualification_projection(p,ID)['numerical_pass'])
 def test_record_path_escape_blocked(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);n=self.setup_fixture(p);f=n/'PROFILE_0_DIAGNOSTIC.json';r=json.loads(f.read_text());r['report']['path']='/tmp/foreign';f.write_text(json.dumps(r))
   self.assertFalse(s.numeric_qualification_projection(p,ID)['numerical_pass'])
 def test_summary_bound(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);self.setup_fixture(p);r=s.numeric_qualification_projection(p,ID)
   self.assertLess(len(s.encode(r).encode()),65536)
if __name__=='__main__':unittest.main()
