import copy,importlib.util,json,pathlib,sys,tempfile,unittest
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));sys.path.insert(0,str(R/'numeric'))
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
f=module('acceptance_fixtures',R/'acceptance_tests/test_required_acceptance.py');s=module('summary_independent',R/'summarize_same_job.py');d=f.d;a=f.a;H=f.H
I={'run_id':123,'source_commit':'1'*40,'launch_commit':'2'*40}
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v));return p
def fixture(root,profiles=range(5)):
 nr=root/'materials/numeric';records=[]
 for i in profiles:
  out=nr/f'profile{i}/material/dut_result';r=f.row(i);r.update(qualification=a.evaluate(r),status='INCOMPLETE',numerical_pass=False)
  report=dict(status='INCOMPLETE',numerical_pass=False,layer=a.LAYER,final_rtl_executed=False,artifact_manifest_sha256=H,runtime_bundle_sha256=H,profiles=[r],matrix_macs=4096,vector_lanes=32,artifact_identity=I,common={k:dict(sha256=H)for k in ('binary','sv','source_manifest','driver')})
  write(out/'RESULT.json',report)
  write(out/f'profile{i}.started.json',dict(schema='ACTUAL_DUT_POPEN_V1',binary_sha256=H,runtime_sha256=H,pid=12,consumer_pid=11,consumer_start_tick=42,inherited_group=11,inherited_session=11))
  leader=dict(pid=11,start=42,group=11)
  op=write(nr/f'runs/p{i}_dut/RESULT.json',dict(worker_started=True,native_exit=2,errors=[],owner_identity=leader,cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',owner_identity=leader,session=11),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True)))
  record=d.verify(out,i,H,H,H,H,d.pin(op));records.append(record);write(nr/f'PROFILE_{i}_DIAGNOSTIC.json',record)
 q=a.aggregate(records);np=write(nr/'RESULT.json',dict(actual_dut_reports=records,qualification=q,status=q['status'],numerical_pass=q['numerical_pass']))
 write(root/'FLOW_RESULT.json',dict(identity=I,execution_mode='BOUNDED_CALIBRATION',transport_exit_code=2,numeric_result=d.pin(np),hardware_definitions=1,profiles=list(range(5)),uploaded_payloads=False,qualification=q,status=q['status']))
 return nr
class Tests(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.p=pathlib.Path(self.t.name);self.n=fixture(self.p)
 def tearDown(self):self.t.cleanup()
 def projection(self):return s.numeric_qualification_projection(self.p,I)
 def alter(self,p,fn):r=json.loads(p.read_text());fn(r);write(p,r)
 def test_full_synthetic_join(self):
  r=self.projection();self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertTrue(r['numerical_pass']);self.assertFalse(r['final_rtl_executed']);self.assertNotIn(str(self.p),json.dumps(r))
 def test_missing_outer(self):
  (self.n/'runs/p0_dut/RESULT.json').unlink();self.assertFalse(self.projection()['numerical_pass'])
 def test_missing_eof(self):
  self.alter(self.n/'runs/p0_dut/RESULT.json',lambda r:r['log_capture'].update(pipe_eof_observed=False));self.assertFalse(self.projection()['numerical_pass'])
 def test_altered_comparison_after_receipt(self):
  self.alter(self.n/'profile0/material/dut_result/RESULT.json',lambda r:r['profiles'][0]['comparisons']['y'].update(byte_mismatches=1));self.assertFalse(self.projection()['numerical_pass'])
 def test_flow_identity_mismatch(self):
  self.alter(self.p/'FLOW_RESULT.json',lambda r:r['identity'].update(run_id=999));self.assertFalse(self.projection()['numerical_pass'])
 def test_copy_pass_only(self):
  for p in self.n.glob('PROFILE_*'):p.unlink()
  self.assertFalse(self.projection()['numerical_pass'])
 def test_missing_p0_eligible4(self):
  with tempfile.TemporaryDirectory()as td:
   p=pathlib.Path(td);fixture(p,range(1,5));r=s.numeric_qualification_projection(p,I);self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertFalse(r['numerical_pass']);self.assertEqual(r['qualification']['missing_profiles'],[0])
 def test_record_wrong_profile(self):
  self.alter(self.n/'PROFILE_0_DIAGNOSTIC.json',lambda r:r.update(profile=1));self.assertFalse(self.projection()['numerical_pass'])
 def test_forged_consumed_receipt_after_repin(self):
  op=self.n/'runs/p0_dut/RESULT.json';self.alter(op,lambda r:r['cleanup_proof'].update(session=99));rp=self.n/'PROFILE_0_DIAGNOSTIC.json';self.alter(rp,lambda r:r.update(outer=d.pin(op)));self.assertFalse(self.projection()['numerical_pass'])
if __name__=='__main__':unittest.main()
