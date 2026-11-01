import copy,hashlib,json,pathlib,tempfile,unittest
import candidate_admission as m
class Test(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name).resolve();self.n=0
  self.identity=dict(run_id=1,artifact_name='candidate',source_commit='a'*40,launch_commit='b'*40,launch_manifest_path='ci_launch/candidate.json',launch_manifest_blob_sha='c'*40)
  self.contract={'schema':'MODEL_CANDIDATE_P0_OBSERVATION_CONTRACT_V1'};self.cp=self.write('contract.json',self.contract)
  self.op=self.write('overlay.json',dict(schema='MODEL_SOURCE_OVERLAY_V1',source_count=159,files=[{}]*159))
  raw=pathlib.Path(self.cp['path']).read_text();obs=dict(schema='MODEL_CANDIDATE_OBSERVATION_V1',status='OBSERVED_UNREVIEWED',source_closure=dict(source_commit='a'*40,source_count=159,source_overlay={k:self.op[k]for k in('bytes','sha256')}))
  source=dict(generation_input_pins={self.cp['path']:self.cp['sha256']},source_commit='a'*40,model_candidate_observation=obs,model_source_evidence=dict(schema='MODEL_CANDIDATE_P0_SOURCE_EVIDENCE_V1',contract=dict(self.cp,text=raw)))
  sp=self.write('source_manifest.json',source)
  self.f=dict(schema=m.SCHEMA,status='UNREVIEWED_MODEL_BUILD',cpp_build_policy='CPP_O1_STRICT_V1',cpp_build_overrides=m.POLICY,profiles=list(range(5)),layer='CHISEL_EMITTED_SV_NUMERICAL_BACKEND',matrix_macs=4096,vector_lanes=32,moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',artifact_identity=self.identity,common={'source_manifest':dict(sp,path='source_manifest.json')},tool_manifest={},model_candidate_observation_sha256=m.canonical_sha(obs),numerical_pass=False,final_rtl_executed=False,model_numerical_evaluation_authorized=False,external_review_required=True)
  self.fp=self.write('frozen_artifact.json',self.f)
  st={'schema':'MODEL_CANDIDATE_STRUCTURAL_REVIEW_V1','status':'VERIFIED_SOURCE_AND_ACTUAL_STRUCTURE_NOT_NUMERICAL','artifact_manifest_sha256':self.fp['sha256'],'observation_sha256':m.canonical_sha(obs),'source_overlay_sha256':self.op['sha256'],'source_contract_sha256':self.cp['sha256'],'matrix_macs':4096,'shared_vector_banks':1,'bank_alu_instances':32,'profiles':list(range(5)),'typed_port_count':122,'numerical_pass':False,'final_rtl_executed':False}
  self.st=st;self.r=dict(schema=m.REVIEW_SCHEMA,status='REVIEWED_FOR_MODEL_NUMERICAL_EVALUATION',scope=m.SCOPE,builder_identity=self.identity,artifact_manifest=self.fp,source_manifest_sha256=sp['sha256'],observation_sha256=m.canonical_sha(obs),source_overlay=self.op,source_contract=self.cp,structural_review=self.write('structural.json',st),data_reference_contract=None,numerical_pass=False,final_rtl_executed=False)
 def write(self,name,d):
  p=self.root/name;p.write_text(json.dumps(d,indent=2)+'\n');return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 def check(self,r=None):return m.verify_review(self.write('review.json',r or self.r),self.fp,self.identity)
 def test_offline_scope(self):
  v=self.check();self.assertEqual(v['scope'],m.SCOPE);self.assertFalse(v['numerical_pass'])
 def test_missing_review(self):
  with self.assertRaises(ValueError):m.verify_review(None,self.fp,self.identity)
 def test_no_builder_authorization(self):
  for key,value in [('model_numerical_evaluation_authorized',True),('numerical_pass',True),('status','PASS'),('schema','FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2'),('matrix_macs',4095)]:
   with self.subTest(key=key):
    f=copy.deepcopy(self.f);f[key]=value;self.fp=self.write('frozen_artifact.json',f);r=copy.deepcopy(self.r);r['artifact_manifest']=self.fp
    with self.assertRaises(ValueError):self.check(r)
 def test_observation_mismatch(self):
  r=copy.deepcopy(self.r);r['observation_sha256']='0'*64
  with self.assertRaises(ValueError):self.check(r)
 def test_structure_bool_count(self):
  st=copy.deepcopy(self.st);st['shared_vector_banks']=True;self.r['structural_review']=self.write('structural.json',st)
  with self.assertRaises(ValueError):self.check()
 def test_unrelated_overlay_rejected(self):
  altered=dict(schema='MODEL_SOURCE_OVERLAY_V1',source_count=159,files=[{'different':True}]*159);self.r['source_overlay']=self.write('other_overlay.json',altered)
  st=copy.deepcopy(self.st);st['source_overlay_sha256']=self.r['source_overlay']['sha256'];self.r['structural_review']=self.write('structural.json',st)
  with self.assertRaises(ValueError):self.check()
 def test_source_byte_drift(self):
  pathlib.Path(self.cp['path']).write_text('{}')
  with self.assertRaises(ValueError):self.check()
 def test_external_approval_required(self):
  rp=self.write('review.json',self.r)
  with self.assertRaises((KeyError,ValueError)):m.verify(rp,dict(execution_context='CLOUD_EXECUTOR_V1',model_candidate_review=rp))
 def test_actual_invocation_join(self):
  rp=self.write('review.json',self.r);b=dict(execution_context='CLOUD_EXECUTOR_V1',model_candidate_review=rp,artifact_manifest=self.fp,identity=dict(source_commit='d'*40,execution_id='synthetic-not-a-live-executor'))
  b['cloud_budget']=self.write('budget.json',dict(model_candidate_review=rp));a=dict(schema='OPERATOR_REVIEWED_CLOUD_INVOCATION_V1',approved=True,authority='USER_AUTHORIZED_OPERATOR_REVIEW',model_candidate_review_sha256=rp['sha256'],budget_sha256=b['cloud_budget']['sha256'],source_commit=b['identity']['source_commit'],execution_id=b['identity']['execution_id'],artifact_manifest_sha256=self.fp['sha256']);b['execution_approval']=self.write('approval.json',a)
  self.assertEqual(m.verify(rp,b)['artifact_manifest_sha256'],self.fp['sha256']);a['model_candidate_review_sha256']='0'*64;b['execution_approval']=self.write('approval.json',a)
  with self.assertRaises(ValueError):m.verify(rp,b)
 def test_unrecognized_review_field(self):
  r=copy.deepcopy(self.r);r['auto_approve']=True
  with self.assertRaises(ValueError):self.check(r)
if __name__=='__main__':unittest.main()
