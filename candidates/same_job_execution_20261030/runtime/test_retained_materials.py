"""Synthetic metadata/byte fixtures only. No real old-owner lease or arithmetic.
The 3.53GB execution constant is patched to70 solely for tiny positive fixtures.
"""
import copy,json,pathlib,tempfile,unittest
from unittest import mock
import retained_materials as m
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'numeric'))
import numeric_tail as tail
P=pathlib.Path
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
class Tests(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.f=Fixture(P(self.t.name))
 def reject(self):
  with self.assertRaises((ValueError,KeyError)):self.f.verify()
 def test_complete_synthetic_old_dead_owner_revalidated(self):
  with mock.patch('subprocess.Popen',side_effect=AssertionError('no processes')):r=self.f.verify()
  self.assertEqual(len(r['weights']),70);self.assertEqual(set(r['references']),set(map(str,range(5))));self.assertEqual(r['scope'],m.SCOPE)
 def test_official_header_cache_not_a_weight(self):
  p=self.f.payload/'headers/hash.bin';p.parent.mkdir();p.write_bytes(b'original-header-only');self.assertEqual(len(self.f.verify()['weights']),70)
 def test_independent_manifest_pin(self):self.f.mp['sha256']='0'*64;self.reject()
 def test_old_identity_not_reused(self):self.f.b['identity']=self.f.ident;self.reject()
 def test_wrong_artifact(self):self.f.b['artifact_manifest']={'sha256':'0'*64};self.reject()
 def test_changed_source(self):next(self.f.current.rglob('run_reference.py')).write_bytes(b'changed');self.reject()
 def test_weight_payload_drift(self):P(self.f.doc['weights'][0]['file']['path']).write_bytes(b'y');self.reject()
 def test_weight_missing(self):self.f.doc['weights'].pop();self.f.save();self.reject()
 def test_weight_duplicate(self):self.f.doc['weights'][0]=copy.deepcopy(self.f.doc['weights'][1]);self.f.save();self.reject()
 def test_weight_extra_file(self):(self.f.payload/'qwen2_1p5b/extra.bin').write_bytes(b'x');self.reject()
 def test_weight_receipt_wrong_actual(self):self.f.mutate(self.f.doc['weights'][0]['receipt'],'actual_sha256','0'*64);self.reject()
 def test_weight_outer_native_bool(self):self.f.mutate(self.f.doc['weights_outer'],'native_exit',False);self.reject()
 def test_weight_outer_incomplete(self):self.f.mutate(self.f.doc['weights_outer'],'log_capture',{'pipe_eof_observed':False,'gzip_finalized':True});self.reject()
 def test_weight_argv_wrong(self):self.f.mutate(self.f.doc['weights_outer'],'argv',['other']);self.reject()
 def test_ref_outer_error(self):self.f.mutate(self.f.doc['references']['2']['outer'],'errors',['error']);self.reject()
 def test_ref_phase_wrong(self):self.f.mutate(self.f.doc['references']['1']['phase'],'argv',['other']);self.reject()
 def test_ref_tensor_drift(self):(self.f.job/'materials/references/profile4/actual/reference/tensor.bin').write_bytes(b'y');self.reject()
 def test_ref_profile_missing(self):del self.f.doc['references']['4'];self.f.save();self.reject()
 def test_ref_no_symlink(self):
  p=self.f.job/'materials/references/profile4/actual/reference/tensor.bin';p.unlink();p.symlink_to(self.f.job/'materials/references/profile3/actual/reference/tensor.bin');self.reject()
 def test_runtime_wrapper_drift(self):P(self.f.entries['qwen2']['wrapper']['path']).write_bytes(b'changed');self.reject()
 def test_scope_not_dut(self):self.f.doc['numerical_pass']=True;self.f.save();self.reject()
 def tail_binding(self):
  v=self.f.verify();return dict(execution_context='CLOUD_EXECUTOR_V1',retained_materials=self.f.mp,owner_root=str(self.f.base/'new_owner'),references=v['references']),v
 def test_tail_reference_exact_approved_set(self):
  b,v=self.tail_binding()
  for i in range(5):self.assertEqual(str(tail.reference_path(b,i,v)),v['references'][str(i)]['path'])
 def test_tail_legacy_owner_gate_unchanged(self):
  b,v=self.tail_binding()
  with self.assertRaisesRegex(ValueError,'owning job'):tail.reference_path(b,0,None)
 def test_tail_arbitrary_old_reference_rejected(self):
  b,v=self.tail_binding();v=copy.deepcopy(v);v['references']['0']=v['references']['1']
  with self.assertRaisesRegex(ValueError,'exact independently'):tail.reference_path(b,0,v)
 def test_tail_noncloud_retained_rejected(self):
  with self.assertRaisesRegex(ValueError,'explicit cloud'):tail.retained_context({'retained_materials':self.f.mp})
 def test_tail_missing_controller_rejected(self):
  with self.assertRaises(KeyError):tail.retained_context({'execution_context':'CLOUD_EXECUTOR_V1','retained_materials':self.f.mp})
if __name__=='__main__':unittest.main()
