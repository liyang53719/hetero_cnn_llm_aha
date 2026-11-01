"""Synthetic byte/receipt fixtures. No model, runtime or DUT execution."""
import copy,json,pathlib,tempfile,unittest,sys,os
from unittest import mock
import retained_materials as m
P=pathlib.Path
BASE=P(os.environ.get('RETAINED_TEST_BASE',str(P(__file__).resolve().parent)))
class Fixture:
 def __init__(self,base):
  self.base=base;self.repo=base/'oldrepo';self.current=base/'newrepo';self.job=base/'oldjob';self.job.mkdir();self.payload=self.job/'runs/weights/output';self.payload.mkdir(parents=True)
  self.ident=dict(schema='CLOUD_EXECUTOR_IDENTITY_V1',source_commit='a'*40,execution_id='11111111-2222-4333-8444-555555555555',boot_id='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',controller_pid=999999,start_tick=1,host_identity_sha256='b'*64,started_monotonic=1)
  self.ip=self.write(P(str(self.job)+'-EXECUTOR_IDENTITY.json'),self.ident);self.pins={};self.newpins={str(m.D.parent/'executor_identity.py'):m.sha(m.D.parent/'executor_identity.py')};rows=[]
  names=set(m.EXACT)|{'candidates/five_profile_acquisition_resume_20261028/acquire_resumable.py','candidates/independent_reference_p0_cache_arm_20261028T2313/run_reference.py','candidates/independent_block_reference_prepare_v3_20261028T2312/run_reference.py'}|{'config/upstream/weight_headers/'+n+'/config.json'for n in m.MODELS}
  for n in sorted(names):
   for r in(self.repo,self.current):p=r/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'SYNTHETIC SOURCE')
   p=self.repo/n;self.pins[str(p)]=m.sha(p);self.newpins[str(self.current/n)]=m.sha(p);rows.append(dict(path=n,bytes=p.stat().st_size,sha256=m.sha(p)))
  catalog=self.write(base/'catalog.json',dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=rows))
  entries={}
  for key in set(m.KEYS):
   entries[key]={}
   for role in('wrapper','installation','sidecar'):entries[key][role]=self.write(base/key/(role+'.json'),{'synthetic':role})
  runtime=self.write(base/'runtime.json',dict(source_commit=self.ident['source_commit'],entries=entries));self.entries=entries
  self.old=dict(identity=self.ident,executor_identity=self.ident,executor_identity_pin=self.ip,execution_context='CLOUD_EXECUTOR_V1',profiles=list(range(5)),tokens=128,matrix_macs=4096,artifact_manifest={'sha256':'c'*64},job_root=str(self.job),repo=str(self.repo),pins=self.pins,source_pins=catalog,python='/synthetic/python',runtime_package=str(self.repo/'candidates/same_job_execution_20261030/runtime'),execution_policy={'mode':'synthetic-full'},runtime_reuse_manifest=runtime)
  self.op=self.write(P(str(self.job)+'-CLOUD_BINDING.json'),self.old);self.b=dict(repo=str(self.current),pins=self.newpins,identity=dict(self.ident,execution_id='22222222-2222-4333-8444-555555555555'),artifact_manifest=self.old['artifact_manifest'])
  weights=[]
  for i in range(70):
   p=self.payload/'qwen2_1p5b'/('w'+str(i)+'.bin');p.parent.mkdir(exist_ok=True);p.write_bytes(b'x');fp=self.pin(p)
   rp=self.write(p.with_name('w'+str(i)+'.receipt.json'),dict(status='ACQUIRED_ORIGINAL_TENSOR_BYTES_ONLY_NOT_REFERENCE_OR_DUT',actual_bytes=1,actual_sha256=fp['sha256'],bytes=1,model='qwen2_1p5b',name='w'+str(i),file=str(p.relative_to(self.payload))))
   weights.append(dict(file=fp,receipt=rp))
  ws=self.write(self.payload/'SUMMARY.json',dict(status='ACQUIRED_70_ORIGINAL_TENSORS_ONLY',tensors=70,tensor_bytes=70,reference_executed=False,dut_executed=False))
  wo=self.write(self.job/'runs/weights/RESULT.json',self.outer([self.old['python'],'-B',str(self.repo/'candidates/five_profile_acquisition_resume_20261028/acquire_resumable.py'),'--output',str(self.payload),'--execute']))
  refs={};index={}
  for i in range(5):
   home=self.job/f'materials/references/profile{i}';dest=home/'actual/reference';dest.mkdir(parents=True);rt=entries[m.KEYS[i]]
   rel='candidates/'+('independent_reference_p0_cache_arm_20261028T2313'if i==0 else'independent_block_reference_prepare_v3_20261028T2312')+'/run_reference.py';src=self.repo/rel;config=self.repo/'config/upstream/weight_headers'/m.MODELS[i]/'config.json'
   args=[str(src),'--profile',str(i),'--payload',str(self.payload),'--config',str(config),'--runtime-receipt',rt['installation']['path'],'--runtime-receipt-sha256',rt['installation']['sha256'],'--runtime-source-pins',rt['sidecar']['path'],'--runtime-source-pins-sha256',rt['sidecar']['sha256'],'--output',str(dest),'--execute-reviewed']
   phase=self.write(home/'PHASE.json',dict(argv=args,source_sha256=m.sha(src)));t=dest/'tensor.bin';t.write_bytes(b'x')
   result=self.write(dest/'RESULT.json',dict(status='CAPTURED_FRESH_OFFICIAL_FULL_BLOCK_REFERENCE_ONLY',profile=dict(profile=i,model=m.MODELS[i],layer=3 if i in(2,4)else 0,config_sha256=m.sha(config)),complete_block_tokens=128,exact_baseline_observer_output_equal=True,hardware_executed=False,router_policy='UNMODIFIED_OFFICIAL_TORCH_TOPK',runtime_receipt_sha256=rt['installation']['sha256'],runtime_source_pins_sha256=rt['sidecar']['sha256'],tensor_records={'one':dict(file='tensor.bin',bytes=1,sha256=m.sha(t))}))
   outer=self.write(home/'actual/RESULT.json',self.outer([rt['wrapper']['path'],str(P(self.old['runtime_package'])/'reference_phase.py'),'--binding',str(home/'PHASE.json'),'--sha256',phase['sha256']]))
   refs[str(i)]=dict(result=result,phase=phase,outer=outer);index[str(i)]=result
  rm=self.write(self.job/'materials/references/REFERENCES.json',dict(identity=self.ident,execution_policy=self.old['execution_policy'],scope='REGISTERED_FIVE_ELIGIBLE_SOFTWARE_REFERENCES_NOT_DUT',references=index))
  self.doc=dict(schema='RETAINED_M128_MATERIALS_V1',scope=m.SCOPE,old_controller_binding=self.op,old_executor_identity=self.ip,weights_summary=ws,weights_outer=wo,references_manifest=rm,weights=weights,references=refs,numerical_pass=False);self.path=base/'manifest.json';self.save()
 def pin(self,p):return dict(path=str(p),bytes=p.stat().st_size,sha256=m.sha(p))
 def write(self,p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d));return self.pin(p)
 def outer(self,args):return dict(native_exit=0,errors=[],argv=args,cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})
 def save(self):self.mp=self.write(self.path,self.doc)
 def mutate(self,row,key,val):p=P(row['path']);d=json.loads(p.read_text());d[key]=val;row.update(self.write(p,d));self.save()
 def verify(self):
  with mock.patch.object(m,'TOTAL_BYTES',70):return m.verify(self.mp,self.b)

class CandidateTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.dm=mock.patch.object(m,'D',BASE);self.dm.start();self.addCleanup(self.dm.stop)
  self.f=Fixture(P(self.temp.name));f=self.f
  self.helper=f.current/'candidates/same_job_execution_20261030/numeric/candidate_admission.py'
  self.helper.parent.mkdir(parents=True,exist_ok=True)
  self.helper.write_text("import json,hashlib,pathlib\ndef verify(pin,b):\n p=pathlib.Path(pin['path']);data=p.read_bytes()\n if len(data)!=pin['bytes'] or hashlib.sha256(data).hexdigest()!=pin['sha256']:raise ValueError('independent review pin')\n return json.loads(data)\n")
  f.b['pins'][str(self.helper)]=m.sha(self.helper);f.b['execution_context']='CLOUD_EXECUTOR_V1'
  catalog=m.read(f.old['source_pins'])
  for i in range(51-len(catalog['files'])):
   n=m.PREFIXES[0]+'synthetic_source_'+str(i)+'.py'
   for root in(f.repo,f.current):p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'synthetic')
   pin=f.pin(f.repo/n);catalog['files'].append(dict(pin,path=n));f.old['pins'][str(f.repo/n)]=pin['sha256'];f.b['pins'][str(f.current/n)]=pin['sha256']
  f.old['source_pins']=f.write(P(f.old['source_pins']['path']),catalog)
  def artifact(root,schema):
   root.mkdir();driver=root/'driver.cpp';driver.write_bytes(b'SYNTHETIC UNCHANGED DRIVER')
   return f.write(root/'frozen_artifact.json',dict(schema=schema,profiles=list(range(5)),matrix_macs=4096,moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',common={'driver':dict(f.pin(driver),path='driver.cpp')}))
  f.old['artifact_manifest']=artifact(f.base/'oldartifact','FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2')
  f.b['artifact_manifest']=artifact(f.base/'newartifact',m.CANDIDATE_SCHEMA)
  f.doc['old_controller_binding']=f.write(P(f.op['path']),f.old);f.save()
  self.contract=dict(schema='MODEL_CANDIDATE_DATA_REFERENCE_ONLY_V1',scope=m.CANDIDATE_SCOPE,old_artifact_manifest_sha256=f.old['artifact_manifest']['sha256'],new_artifact_manifest_sha256=f.b['artifact_manifest']['sha256'],retained_materials_sha256=f.mp['sha256'],old_source_pins_sha256=f.old['source_pins']['sha256'],reference_sources=catalog['files'],weights_sha256=m.domain_sha(f.doc['weights']),references_sha256=m.domain_sha(f.doc['references']),profiles=list(range(5)),tokens=128,routing='UNMODIFIED_OFFICIAL_TORCH_TOPK')
  self.review=dict(scope=m.REVIEW_SCOPE,data_reference_contract=self.contract);self.save_review()
 def save_review(self):self.f.b['model_candidate_review']=self.f.write(self.f.base/'review.json',self.review)
 def reject(self):
  with self.assertRaises((ValueError,KeyError,FileNotFoundError)):self.f.verify()
 def test_full_synthetic_data_chain(self):
  with mock.patch('subprocess.Popen',side_effect=AssertionError('no child')):out=self.f.verify()
  self.assertEqual(out['scope'],m.CANDIDATE_SCOPE);self.assertEqual(len(out['weights']),70);self.assertEqual(len(out['references']),5)
 def test_no_review(self):del self.f.b['model_candidate_review'];self.reject()
 def test_unpinned_validator(self):self.f.b['pins'][str(self.helper)]='0'*64;self.reject()
 def test_unpinned_review(self):self.f.b['model_candidate_review']['sha256']='0'*64;self.reject()
 def test_no_production_scope(self):self.review['scope']='PASS';self.save_review();self.reject()
 def test_unknown_hash(self):self.contract['new_artifact_manifest_sha256']=None;self.save_review();self.reject()
 def test_omitted_source(self):self.contract['reference_sources'].pop();self.save_review();self.reject()
 def test_source_drift(self):next(self.f.current.rglob('run_reference.py')).write_bytes(b'changed');self.reject()
 def test_driver_drift(self):(self.f.base/'newartifact/driver.cpp').write_bytes(b'changed');self.reject()
 def test_weight_drift(self):P(self.f.doc['weights'][0]['file']['path']).write_bytes(b'y');self.reject()
 def test_reference_drift(self):(self.f.job/'materials/references/profile4/actual/reference/tensor.bin').write_bytes(b'y');self.reject()
 def test_changed_reference_metadata(self):self.contract['references_sha256']='0'*64;self.save_review();self.reject()
 def test_changed_routing(self):self.contract['routing']='SMALL_ID';self.save_review();self.reject()
 def test_incomplete_receipt(self):
  self.f.mutate(self.f.doc['references']['1']['outer'],'errors',['failure']);self.contract['retained_materials_sha256']=self.f.mp['sha256'];self.contract['references_sha256']=m.domain_sha(self.f.doc['references']);self.save_review();self.reject()
 def test_extra_contract_key(self):self.contract['hardware_pass']=True;self.save_review();self.reject()
if __name__=='__main__':unittest.main()
