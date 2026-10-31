"""Synthetic receipt tests only; mocked admission never qualifies a real budget."""
import json,pathlib,tempfile,unittest,types
from unittest.mock import patch
import test_safe_summary_join as base
from test_safe_summary_join import s, ID, d

class FullTests(unittest.TestCase):
 def fixture(self,p,profiles=range(5)):
  base.Tests().setup_fixture(p,profiles)
  f=p/'FLOW_RESULT.json';flow=json.loads(f.read_text());flow.update(execution_mode='FULL_BLOCK_ACCEPTANCE',transport_exit_code=0)
  n=p/'materials/numeric';nf=n/'RESULT.json';nr=json.loads(nf.read_text())
  for i in profiles:
   out=n/f'profile{i}/material/dut_result';rp=out/'RESULT.json';r=json.loads(rp.read_text())
   original=dict(wall_seconds=20000,max_active_cycles=1000000000,cpu_seconds=18000,address_space_bytes=12<<30,file_bytes=64<<20)
   r['execution_admission']=dict(scope='FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE',execution_mode='FULL_BLOCK_ACCEPTANCE',reviewed_budget_sha256='a'*64,original_limits=original,effective_limits=dict(original,wall_seconds=100+i,max_active_cycles=10000+i),outer_cleanup_proof_required=True)
   rp.write_text(json.dumps(r));outer=n/f'runs/p{i}_dut/RESULT.json';record=d.verify(out,i,base.H,base.H,base.H,base.H,d.pin(outer));(n/f'PROFILE_{i}_DIAGNOSTIC.json').write_text(json.dumps(record));nr['actual_dut_reports'][list(profiles).index(i)]=record
  nr.update(execution_mode='FULL_BLOCK_ACCEPTANCE',full_budget_sha256='a'*64);nf.write_text(json.dumps(nr));flow['numeric_result']=d.pin(nf)
  f.write_text(json.dumps(flow));return flow
 def admitted(self,*args):
  def transport(mode,q):return 0 if q['numerical_pass'] else 1 if q['status']=='FAIL_EXACT_REFERENCE' else 2
  def limits(original,admission,i):return dict(original,wall_seconds=100+i,max_active_cycles=10000+i)
  return types.SimpleNamespace(transport_exit=transport,consumer_limits=limits),dict(mode='FULL_BLOCK_ACCEPTANCE',reviewed_budget_sha256='a'*64),'b'*64
 def run_projection(self,p,flow):
  flow['execution_binding']={'sha256':'c'*64};(p/'FLOW_RESULT.json').write_text(json.dumps(flow))
  with patch.object(s,'full_execution_admission',self.admitted):return s.numeric_qualification_projection(p,ID)
 def test_full_five_requires_reaggregation(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);flow=self.fixture(p);r=self.run_projection(p,flow)
   self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertTrue(r['numerical_pass']);self.assertEqual(r['transport_exit_code'],0);self.assertNotIn(t,json.dumps(r))
 def test_partial_cannot_exit_zero(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);flow=self.fixture(p,range(1,5));self.assertFalse(self.run_projection(p,flow)['numerical_pass'])
   flow['transport_exit_code']=2;r=self.run_projection(p,flow);self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertFalse(r['numerical_pass'])
 def test_wrong_or_bool_transport_rejected(self):
  for code in (1,2,False):
   with tempfile.TemporaryDirectory()as t:
    p=pathlib.Path(t);flow=self.fixture(p);flow['transport_exit_code']=code;self.assertEqual(self.run_projection(p,flow)['status'],'INVALID_OR_UNBOUND')
 def test_exact_failure_reaggregates_exit_one(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);flow=self.fixture(p);n=p/'materials/numeric';out=n/'profile0/material/dut_result'
   f=out/'RESULT.json';report=json.loads(f.read_text());row=report['profiles'][0];row['comparisons']['y']['byte_mismatches']=1
   row['qualification']=base.a.evaluate(row);row['status']=report['status']=row['qualification']['status'];f.write_text(json.dumps(report))
   outer=n/'runs/p0_dut/RESULT.json';o=json.loads(outer.read_text());o['native_exit']=1;outer.write_text(json.dumps(o))
   record=d.verify(out,0,base.H,base.H,base.H,base.H,d.pin(outer));(n/'PROFILE_0_DIAGNOSTIC.json').write_text(json.dumps(record))
   nf=n/'RESULT.json';nr=json.loads(nf.read_text());nr['actual_dut_reports'][0]=record;q=base.a.aggregate(nr['actual_dut_reports']);nr.update(qualification=q,status=q['status'],numerical_pass=False);nf.write_text(json.dumps(nr))
   flow.update(qualification=q,status=q['status'],numeric_result=d.pin(nf),transport_exit_code=1)
   r=self.run_projection(p,flow);self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertEqual(r['transport_exit_code'],1);self.assertFalse(r['numerical_pass'])
 def test_rebound_calibration_or_mixed_limits_refused(self):
  changes=[('execution_mode','BOUNDED_CALIBRATION'),('reviewed_budget_sha256','d'*64),('scope','CALIBRATION_SAME_FULL_M128_STIMULUS'),('outer_cleanup_proof_required',False),('effective_limits',{'wall_seconds':300})]
  for key,value in changes:
   with tempfile.TemporaryDirectory()as t:
    p=pathlib.Path(t);flow=self.fixture(p);n=p/'materials/numeric';out=n/'profile2/material/dut_result';rp=out/'RESULT.json';r=json.loads(rp.read_text());r['execution_admission'][key]=value;rp.write_text(json.dumps(r))
    record=d.verify(out,2,base.H,base.H,base.H,base.H,d.pin(n/'runs/p2_dut/RESULT.json'));(n/'PROFILE_2_DIAGNOSTIC.json').write_text(json.dumps(record));nf=n/'RESULT.json';nr=json.loads(nf.read_text());nr['actual_dut_reports'][2]=record;nf.write_text(json.dumps(nr));flow['numeric_result']=d.pin(nf)
    self.assertEqual(self.run_projection(p,flow)['status'],'INVALID_OR_UNBOUND')
 def test_numeric_mode_budget_drift_refused(self):
  for key,value in [('execution_mode','BOUNDED_CALIBRATION'),('full_budget_sha256','f'*64)]:
   with tempfile.TemporaryDirectory()as t:
    p=pathlib.Path(t);flow=self.fixture(p);nf=p/'materials/numeric/RESULT.json';n=json.loads(nf.read_text());n[key]=value;nf.write_text(json.dumps(n));flow['numeric_result']=d.pin(nf)
    self.assertEqual(self.run_projection(p,flow)['status'],'INVALID_OR_UNBOUND')
 def test_missing_admission_rejected(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);self.fixture(p);self.assertEqual(s.numeric_qualification_projection(p,ID)['status'],'INVALID_OR_UNBOUND')
 def binding(self,p,flow):
  identity={k:ID[k]for k in ('run_id','source_commit','launch_commit')};mode=s.D/'execution_mode.py'
  binding=dict(job_root=str(p),identity=identity,artifact_identity=ID,execution_mode='FULL_BLOCK_ACCEPTANCE',execution_policy=s.profile_policy.policy(),pins={str(mode):s.sha(mode)})
  bp=p.parent/(p.name+'-BINDING.json');bp.write_text(json.dumps(binding));flow['execution_binding']=d.pin(bp)
  return bp,binding,identity
 def test_real_pending_module_refuses(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'job';p.mkdir();flow=self.fixture(p);bp,binding,identity=self.binding(p,flow)
   with self.assertRaisesRegex(ValueError,'PENDING_ACTUAL'):s.full_execution_admission(p,flow,identity,d)
 def test_wrong_source_binding_and_scope_rejected(self):
  for field in ('pins','identity','job_root'):
   with tempfile.TemporaryDirectory()as t:
    p=pathlib.Path(t)/'job';p.mkdir();flow=self.fixture(p);bp,binding,identity=self.binding(p,flow)
    binding[field]={} if field!='job_root' else '/wrong';bp.write_text(json.dumps(binding));flow['execution_binding']=d.pin(bp)
    with self.assertRaises(ValueError):s.full_execution_admission(p,flow,identity,d)
 def test_mutated_profile_receipt_still_refuses(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);flow=self.fixture(p);r=p/'materials/numeric/runs/p2_dut/RESULT.json';v=json.loads(r.read_text());v['log_capture']['pipe_eof_observed']=False;r.write_text(json.dumps(v))
   self.assertEqual(self.run_projection(p,flow)['status'],'INVALID_OR_UNBOUND')
if __name__=='__main__':unittest.main()
