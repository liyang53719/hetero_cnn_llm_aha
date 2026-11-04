"""Real pinned metadata plus fake transport/payload I/O, no download/framework/DUT."""
import copy,json,pathlib,tempfile,types,unittest
from unittest import mock
import selected_acquisition as a
import selected_reference_job as r
import selected_retained_materials as retained
P=pathlib.Path;REPO=a.D.parents[2]
POLICY=a.module('test_selected_policy',a.D.parent/'profile_policy.py')
def binding(selected):
 paths=[]
 for rel in(a.RECOVERY,a.RESUME,a.REFERENCE,'candidates/independent_reference_p0_cache_arm_20261028T2313','config/upstream/weight_headers'):
  paths += [p for p in(REPO/rel).rglob('*')if p.is_file()and '__pycache__'not in p.parts]
 paths += list(a.D.glob('*.py'))+[a.D.parent/'profile_policy.py',a.D.parent/'executor_identity.py']
 return dict(repo=str(REPO),profiles=list(range(5)),tokens=128,execution_policy=POLICY.selected_policy(selected),pins={str(p):a.sha(p)for p in paths})
class PlanTests(unittest.TestCase):
 def test_each_real_complete_original_layer(self):
  for i,count in enumerate(a.COUNTS):
   with self.subTest(profile=i):
    b=binding([i]);plan=a.selected_plan(b);profile=a.profiles(b)[i]
    self.assertEqual(plan['profiles'],[i]);self.assertEqual(len(plan['specs']),count);self.assertEqual(plan['profile_tensor_counts'],{str(i):count})
    self.assertEqual({x['model']for x in plan['specs']},{profile['model']})
    prefix=('model.layers.'if i==0 else'model.language_model.layers.')+str(profile['layer'])+'.'
    self.assertTrue(all(x['name'].startswith(prefix)for x in plan['specs']))
    self.assertEqual(plan['body_cap'],plan['tensor_bytes']+sum(x['header']['bytes']for x in plan['headers']))
    self.assertEqual({x['url']for x in plan['headers']},{x['url']for x in plan['specs']})
    self.assertEqual((plan['max_response_bytes'],plan['workers']),(8388608,2))
 def test_nonp0_58_weights_no_qwen2_all_experts(self):
  plan=a.selected_plan(binding([1,2,3,4]));self.assertEqual(len(plan['specs']),58)
  self.assertNotIn('qwen2_1p5b',{x['model']for x in plan['specs']});self.assertFalse(any('Qwen2-'in x['url']for x in plan['headers']))
  for x in plan['specs']:
   if x['model']=='qwen3_5_35b_a3b'and'.experts.'in x['name']:self.assertEqual(x['shape'][0],256)
 def test_allfive_still_original70(self):self.assertEqual(len(a.selected_plan(binding(list(range(5))))['specs']),70)
 def test_missing_or_drifted_pin(self):
  for value in(None,'0'*64):
   b=binding([1]);path=str(REPO/a.RECOVERY/'reconstruct_plan.py')
   if value is None:del b['pins'][path]
   else:b['pins'][path]=value
   with self.assertRaises(ValueError):a.selected_plan(b)
 def test_legacy_not_implicitly_selected(self):
  b=binding([1]);b['execution_policy']=POLICY.policy()
  with self.assertRaises(ValueError):a.selected_plan(b)
 def test_partial_hardware_and_short_tokens(self):
  for key,value in(('profiles',[1]),('profiles',[False,1,2,3,4]),('tokens',64),('tokens',True)):
   b=binding([2]);b[key]=value
   with self.assertRaises(ValueError):a.selected_plan(b)
 def test_only_selected_original_transport_calls(self):
  b=binding([2]);plan=a.selected_plan(b);called=[];fetched=[];real_module=a.module;totals=dict(requested=0,received=0,requests=0)
  def add(size):
   totals['requested']+=size;totals['received']+=size;totals['requests']+=1
  def fetch(url,start,end,size,identity):
   fetched.append(url);row=next(x for x in plan['headers']if x['url']==url);raw=(REPO/a.RECOVERY/row['header']['json_text']).read_bytes();data=len(raw).to_bytes(8,'little')+raw;add(len(data));return data
  def acquire(spec):called.append(spec);add(spec['bytes']);return dict(actual_bytes=spec['bytes'])
  def write(path,doc):
   with path.open('x')as f:json.dump(doc,f)
  fake=types.SimpleNamespace(MAX=8388608,fetch=fetch,acquire=acquire,write_json=write,digest=lambda raw:a.hashlib.sha256(raw).hexdigest(),totals=totals,stop=mock.Mock())
  def module(name,path):return fake if name=='selected_original_acquire'else real_module(name,path)
  with tempfile.TemporaryDirectory()as td:
   b['output']=str(P(td)/'output')
   with mock.patch.object(a,'module',side_effect=module),mock.patch.object(a.shutil,'disk_usage',return_value=types.SimpleNamespace(free=20<<30)):
    summary=a.run(b)
   self.assertEqual(summary['tensors'],11);self.assertEqual({x['name']for x in called},{x['name']for x in plan['specs']});self.assertEqual(set(fetched),{x['url']for x in plan['headers']});self.assertIsNone(fake.PREVIOUS)
 def test_existing_output_rejected(self):
  with tempfile.TemporaryDirectory()as td:
   b=binding([4]);b['output']=td
   with self.assertRaises(ValueError):a.run(b)
 def test_cheap_union_validator_does_not_read_payload(self):
  b=binding([1]);plan=a.selected_plan(b);rows=[dict(model=x['model'],name=x['name'],pin=dict(path='/fixture/'+x['model']+'/'+x['name']+'.bin',bytes=x['bytes'],sha256=x['expected_sha256']))for x in plan['specs']]
  with mock.patch.object(a,'pin',side_effect=AssertionError('no payload hashes')):
   self.assertEqual(len(a.validate_inventory(b,rows)),14)
   for invalid in(rows[:-1],[rows[0]]*14,rows+[rows[0]]):
    with self.assertRaises(ValueError):a.validate_inventory(b,invalid)
class ReferenceTests(unittest.TestCase):
 def test_original_sources_unchanged(self):
  self.assertEqual(a.sha(a.D/'reference_job.py'),r.ORIGINAL_JOB_SHA);self.assertEqual(a.sha(a.D/'reference_phase.py'),r.ORIGINAL_PHASE_SHA)
  for i in range(5):r.producer(binding([i]),i)
 def test_complete_tensor_state_schemas(self):
  b=binding([0,1,2,3,4]);counts=[24,19,26,23,30]
  for i,p in enumerate(a.profiles(b)):
   cfg=json.loads((REPO/'config/upstream/weight_headers'/p['model']/'config.json').read_text());schema,calls=r.tensor_schema(p,cfg)
   self.assertEqual(len(schema),counts[i]);self.assertTrue(all(type(v)is int and v==1 for v in calls.values()))
   self.assertEqual({x.removeprefix('baseline_cache.')for x in schema if x.startswith('baseline_cache.')},{x.removeprefix('final_cache.')for x in schema if x.startswith('final_cache.')})
   if i in(3,4):self.assertEqual(schema['stage.mlp.gate.0.pre_topk_probs']['shape'],[128,256]);self.assertEqual(schema['stage.mlp.gate.0.2']['shape'],[128,8])
 def test_strict_outer_cleanup_eof_exit(self):
  good=dict(status='PASS_PROCESS_ONLY',native_exit=0,errors=[],argv=['python','source.py'],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True});r.strict(good,good['argv'])
  for k,v in(('native_exit',False),('status','PASS'),('errors',['bad']),('argv',['other']),('cleanup_proof',None),('log_capture',None)):
   bad=dict(good);bad[k]=v
   with self.assertRaises(ValueError):r.strict(bad,good['argv'])
 def test_no_nonselected_original_reference_sources(self):
  names=retained.original_sources(binding([2]),[2]);self.assertFalse(any('independent_reference_p0_cache_arm_'in x for x in names));self.assertFalse(any('weight_headers/qwen2_'in x for x in names))

class ResultContractTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=P(self.temp.name);self.b=binding([3]);self.profile=a.profiles(self.b)[3]
  config=json.loads((REPO/'config/upstream/weight_headers'/self.profile['model']/'config.json').read_text());schema,calls=r.tensor_schema(self.profile,config)
  records={}
  for name,value in schema.items():
   path=self.root/value['file'];path.parent.mkdir(exist_ok=True);path.touch();digest=a.domain_sha(name.removeprefix('baseline_cache.').removeprefix('final_cache.'))
   if name in('baseline_output','output_storage'):digest='1'*64
   records[name]=dict(value,sha256=digest)
  self.receipt=self.root/'receipt.json';self.receipt.write_text('{}');self.sidecar=self.root/'sidecar.json';self.sidecar.write_text(json.dumps(dict(framework_revision=self.profile['framework_revision'],module_sha256={'transformers.models.'+self.profile['module']+'.modeling_'+self.profile['module']:self.profile['source_sha256']})))
  self.rt=dict(receipt=a.pin(self.receipt),sidecar=dict(a.pin(self.sidecar),sha256=r.SIDECAR_SHAS['qwen35_35b']))
  self.doc=dict(status='CAPTURED_FRESH_OFFICIAL_FULL_BLOCK_REFERENCE_ONLY',profile=self.profile,complete_block_tokens=128,forward_calls=2,exact_baseline_observer_output_equal=True,hardware_executed=False,numerical_comparison_with_hardware=False,no_reference_outputs_or_router_ids_allowed_in_hardware_stimulus=True,input_identity='NEW_EXTERNAL_BOUNDARY_NOT_HISTORICAL_PREFIX',router_policy='UNMODIFIED_OFFICIAL_TORCH_TOPK',runtime_receipt_sha256=self.rt['receipt']['sha256'],runtime_source_pins_sha256=self.rt['sidecar']['sha256'],tensor_records=records,observed_module_calls=calls,raw_router_score_observation='ORIGINAL_FORWARD_LOCAL_RETURN_READONLY_PROFILE')
 def verify(self):
  path=self.root/'RESULT.json';path.write_text(json.dumps(self.doc));pin=a.pin(path);real=r.checked_pin
  def fake(row,cap=2<<20):
   path=P(row['path'])
   return path if path.suffix=='.bin'or path==self.sidecar else real(row,cap)
  with mock.patch.object(r,'checked_pin',side_effect=fake):return r.verify_result(self.b,3,pin,self.rt)
 def test_complete_real_schema_with_fake_tensor_io(self):self.verify()
 def test_missing_state_rejected(self):del self.doc['tensor_records']['final_cache.recurrent_states.0'];self.assertRaises(ValueError,self.verify)
 def test_profile_source_substitution_rejected(self):self.doc['profile']=dict(self.profile,source_sha256='0'*64);self.assertRaises(ValueError,self.verify)
 def test_wrong_cache_geometry_rejected(self):self.doc['tensor_records']['final_cache.recurrent_states.0']['shape']=[1,1];self.assertRaises(ValueError,self.verify)
 def test_changed_final_state_rejected(self):self.doc['tensor_records']['final_cache.recurrent_states.0']['sha256']='0'*64;self.assertRaises(ValueError,self.verify)
 def test_extra_tensor_file_rejected(self):(self.root/'reference_only/extra.bin').touch();self.assertRaises(ValueError,self.verify)
 def test_partial_expert_router_rejected(self):self.doc['tensor_records']['stage.mlp.gate.0.pre_topk_probs']['shape']=[128,8];self.assertRaises(ValueError,self.verify)
 def test_wrong_runtime_sidecar_rejected(self):self.rt['sidecar']['sha256']='0'*64;self.doc['runtime_source_pins_sha256']='0'*64;self.assertRaises(ValueError,self.verify)
 def test_transferred_numeric_pass_rejected(self):self.doc['numerical_comparison_with_hardware']=True;self.assertRaises(ValueError,self.verify)
 def test_bool_token_identity_rejected(self):self.doc['complete_block_tokens']=True;self.assertRaises(ValueError,self.verify)

class SelectedRetainedWiringTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=P(self.temp.name);self.job=self.root/'oldjob';self.job.mkdir();self.b=binding([2]);self.plan=a.selected_plan(self.b)
  self.ident=dict(schema='CLOUD_EXECUTOR_IDENTITY_V1',source_commit='a'*40,execution_id='11111111-2222-4333-8444-555555555555',boot_id='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',controller_pid=999999,start_tick=1,host_identity_sha256='b'*64,started_monotonic=1)
  ident=self.write(P(str(self.job)+'-EXECUTOR_IDENTITY.json'),self.ident)
  artifact=self.write(self.root/'frozen_artifact.json',dict(schema='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2'))
  names=retained.original_sources(self.b,[2])|{'candidates/same_job_execution_20261030/runtime/selected_acquisition.py','candidates/same_job_execution_20261030/runtime/selected_reference_job.py'}
  catalog=self.write(self.root/'catalog.json',dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=[dict(a.pin(REPO/name),path=name)for name in sorted(names)]))
  entries={'qwen35_08b':{k:self.write(self.root/(k+'.json'),{})for k in('wrapper','installation','sidecar')}}
  runtime=self.write(self.root/'runtime.json',dict(schema='PINNED_EXISTING_SELECTED_RUNTIME_BYTES_V1',scope='EXISTING_BYTES_ONLY_REVALIDATE_EVERY_EXECUTOR',execution_policy=self.b['execution_policy'],reference_qualified=False,numerical_qualified=False,source_commit=self.ident['source_commit'],entries=entries));self.rt=entries['qwen35_08b']
  self.old=dict(self.b,identity=self.ident,executor_identity=self.ident,executor_identity_pin=ident,execution_context='CLOUD_EXECUTOR_V1',matrix_macs=4096,artifact_manifest=artifact,source_pins=catalog,job_root=str(self.job),python='/fixture/python',runtime_package=str(a.D),runtime_reuse_manifest=runtime,runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',archive_mode='READ_EXISTING_PINNED_ARCHIVES')
  op=self.write(P(str(self.job)+'-CLOUD_BINDING.json'),self.old);self.b.update(identity=dict(self.ident,execution_id='22222222-2222-4333-8444-555555555555'),artifact_manifest=artifact)
  payload=self.job/'runs/weights/output';payload.mkdir(parents=True);self.payload=payload
  producer_binding=self.write(self.job/'bindings/SELECTED_WEIGHTS.json',dict(self.old,output=str(payload)))
  producer_plan=self.write(payload/'ACQUISITION_PLAN.json',self.plan)
  summary=dict(status=a.STATUS,execution_policy=self.plan['execution_policy'],profiles=[2],profile_tensor_counts={'2':11},tensors=11,tensor_bytes=self.plan['tensor_bytes'],selected_plan_sha256=a.domain_sha(self.plan),reference_executed=False,dut_executed=False,totals=dict(requested=self.plan['body_cap'],received=self.plan['body_cap'],requests=100))
  ws=self.write(payload/'SUMMARY.json',summary)
  wo=self.write(self.job/'runs/weights/RESULT.json',self.outer([self.old['python'],'-B',str(a.D/'selected_acquisition.py'),'--binding',producer_binding['path'],'--sha256',producer_binding['sha256'],'--execute']))
  weights=[]
  for spec in self.plan['specs']:
   path=payload/spec['model']/(spec['name']+'.bin');path.parent.mkdir(exist_ok=True);path.touch();file=dict(path=str(path),bytes=spec['bytes'],sha256=spec['expected_sha256'])
   receipt=self.write(path.with_name(spec['name']+'.receipt.json'),dict(spec,file=str(path.relative_to(payload)),actual_bytes=spec['bytes'],actual_sha256=file['sha256'],status='ACQUIRED_ORIGINAL_TENSOR_BYTES_ONLY_NOT_REFERENCE_OR_DUT'))
   weights.append(dict(file=file,receipt=receipt))
  home=self.job/'materials/references/profile2';dest=home/'actual/reference';result=self.write(dest/'RESULT.json',{})
  src=r.producer(self.b,2);config=REPO/'config/upstream/weight_headers/qwen3_5_0p8b/config.json';rt=self.rt
  args=[str(src),'--profile','2','--payload',str(payload),'--config',str(config),'--runtime-receipt',rt['installation']['path'],'--runtime-receipt-sha256',rt['installation']['sha256'],'--runtime-source-pins',rt['sidecar']['path'],'--runtime-source-pins-sha256',rt['sidecar']['sha256'],'--output',str(dest),'--execute-reviewed']
  phase=self.write(home/'PHASE.json',dict(argv=args,source_sha256=a.sha(src)));outer=self.write(home/'actual/RESULT.json',self.outer([rt['wrapper']['path'],str(a.D/'reference_phase.py'),'--binding',str(home/'PHASE.json'),'--sha256',phase['sha256']]))
  refs=self.write(self.job/'materials/references/REFERENCES.json',dict(identity=self.ident,execution_policy=self.old['execution_policy'],scope='REGISTERED_FIVE_ELIGIBLE_SOFTWARE_REFERENCES_NOT_DUT',references={'2':result}))
  self.doc=dict(schema=retained.SCHEMA,scope='REVALIDATED_DATA_AND_SOFTWARE_REFERENCES_NOT_RUNTIME_OR_DUT',old_controller_binding=op,old_executor_identity=ident,weights_summary=ws,weights_outer=wo,references_manifest=refs,weights=weights,references={'2':dict(result=result,phase=phase,outer=outer)},numerical_pass=False,execution_policy=self.old['execution_policy'],weights_producer=dict(kind='SELECTED_ORIGINAL_V1',binding=producer_binding,plan=producer_plan))
 def write(self,path,doc):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(doc));return a.pin(path)
 def outer(self,argv):return dict(status='PASS_PROCESS_ONLY',native_exit=0,errors=[],argv=argv,cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})
 def verify(self):
  pin=self.write(self.root/'selected.json',self.doc)
  def weights(b,rows,payload,summary=None,allow_unselected=False):
   self.assertFalse(allow_unselected);self.assertEqual(P(payload),self.payload);return a.validate_inventory(b,rows)
  with mock.patch.object(retained.a,'verify_weights',side_effect=weights),mock.patch.object(retained.r,'verify_result',return_value={}):return retained.verify(pin,self.b)
 def test_exact_generated_binding_selected_revalidation(self):
  result=self.verify();self.assertEqual(len(result['weights']),11);self.assertEqual(set(result['references']),{'2'});self.assertFalse(result['runtime_pass']);self.assertFalse(result['numerical_pass'])
 def test_caller_filtered_weight_list_rejected(self):self.doc['weights'].pop();self.assertRaises(ValueError,self.verify)
 def test_selected_binding_wrong_path_rejected(self):
  pin=self.doc['weights_producer']['binding'];self.doc['weights_producer']['binding']=self.write(self.job/'bindings/WEIGHTS.json',json.loads(P(pin['path']).read_text()));self.assertRaises(ValueError,self.verify)
 def test_wrong_producer_selection_rejected(self):
  pin=self.doc['weights_producer']['binding'];doc=json.loads(P(pin['path']).read_text());doc['execution_policy']=POLICY.selected_policy([1]);self.doc['weights_producer']['binding']=self.write(P(pin['path']),doc);self.assertRaises(ValueError,self.verify)
 def test_retained_selection_mismatch_rejected(self):self.doc['execution_policy']=POLICY.selected_policy([1]);self.assertRaises(ValueError,self.verify)
 def test_retained_missing_outer_eof_rejected(self):
  pin=self.doc['references']['2']['outer'];doc=json.loads(P(pin['path']).read_text());doc['log_capture']['pipe_eof_observed']=False;self.doc['references']['2']['outer']=self.write(P(pin['path']),doc);self.assertRaises(ValueError,self.verify)
 def test_fresh_owner_metadata_does_not_require_binding_fields_in_manifest(self):
  owner=dict(schema='SHARED_SELECTED_RUNTIME_OWNER_FRESH_JOB_V1',profile_mapping=list(r.KEYS),identity=self.ident,owner_root=str(self.job/'materials'),reference_qualified=False,numerical_qualified=False,execution_policy=self.old['execution_policy'],entries={'qwen35_08b':self.rt})
  pin=self.write(self.job/'materials/runs/bind/owner/SHARED_RUNTIMES_FRESH_JOB_V3.json',owner);old=dict(self.old);old['runtime_reuse_manifest']=None;old['runtime_mode']='FRESH_ORIGINAL_RUNTIME_INSTALL';old['archive_mode']='DOWNLOAD_ORIGINAL_ARCHIVES';m=retained.load('test_selected_legacy',a.D/'retained_materials.py')
  self.assertEqual(retained.runtime_entry(m,old,self.job,'qwen35_08b',dict(self.doc,runtime_owner=pin),POLICY),self.rt)

class WeightValidationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.payload=P(self.temp.name);self.path=self.payload/'qwen3_5_0p8b/model.language_model.layers.0.original.bin';self.path.parent.mkdir();self.path.write_bytes(b'original')
  self.spec=dict(model='qwen3_5_0p8b',name='model.language_model.layers.0.original',revision='pinned',dtype='BF16',shape=[4],bytes=8,start=20,end=27,url='https://huggingface.co/pinned',shard_bytes=100,verification='EXACT_NAME_SHA256',expected_sha256=a.sha(self.path))
  self.receipt=self.path.with_name(self.spec['name']+'.receipt.json');self.doc=dict(self.spec,file=str(self.path.relative_to(self.payload)),actual_bytes=8,actual_sha256=a.sha(self.path),status='ACQUIRED_ORIGINAL_TENSOR_BYTES_ONLY_NOT_REFERENCE_OR_DUT')
  self.rows=[dict(model=self.spec['model'],name=self.spec['name'],pin=a.pin(self.path))]
 def verify(self):
  self.receipt.write_text(json.dumps(self.doc))
  with mock.patch.object(a,'selected_plan',return_value=dict(specs=[self.spec],tensor_bytes=8)):return a.verify_weights({},self.rows,self.payload)
 def test_original_receipt_and_bytes(self):self.assertEqual(self.verify(),self.rows)
 def test_receipt_wrong_range(self):self.doc['start']=21;self.assertRaises(ValueError,self.verify)
 def test_receipt_wrong_dtype(self):self.doc['dtype']='F32';self.assertRaises(ValueError,self.verify)
 def test_receipt_wrong_hash_policy(self):self.doc['verification']='NO_HASH';self.assertRaises(ValueError,self.verify)
 def test_rehashed_payload_not_original(self):self.path.write_bytes(b'modified');self.rows[0]['pin']=a.pin(self.path);self.doc['actual_sha256']=a.sha(self.path);self.assertRaises(ValueError,self.verify)
 def test_unselected_extra_payload(self):(self.path.parent/'other.bin').write_bytes(b'x');self.assertRaises(ValueError,self.verify)
 def test_extra_receipt(self):(self.path.parent/'other.receipt.json').write_text('{}');self.assertRaises(ValueError,self.verify)
 def test_duplicate_inventory(self):self.rows.append(self.rows[0]);self.assertRaises(ValueError,self.verify)


class RuntimeProvenanceConfusionTests(SelectedRetainedWiringTests):
 def runtime_doc(self,**changes):
  pin=self.old['runtime_reuse_manifest'];doc=json.loads(P(pin['path']).read_text());doc.update(changes);self.old['runtime_reuse_manifest']=self.write(P(pin['path']),doc);self.doc['old_controller_binding']=self.write(P(str(self.job)+'-CLOUD_BINDING.json'),self.old)
 def test_import_wrong_schema(self):self.runtime_doc(schema='SHARED_SELECTED_RUNTIME_OWNER_FRESH_JOB_V1');self.assertRaises(ValueError,self.verify)
 def test_import_legacy_schema_cannot_claim_selected(self):self.runtime_doc(schema='PINNED_EXISTING_THREE_RUNTIME_BYTES_V1');self.assertRaises(ValueError,self.verify)
 def test_import_pass_transfer(self):self.runtime_doc(reference_qualified=True);self.assertRaises(ValueError,self.verify)
 def test_import_wrong_selection(self):self.runtime_doc(execution_policy=POLICY.selected_policy([1]));self.assertRaises(ValueError,self.verify)
 def test_import_wrong_mode(self):
  old=dict(self.old,runtime_mode='FRESH_ORIGINAL_RUNTIME_INSTALL',archive_mode='DOWNLOAD_ORIGINAL_ARCHIVES');m=retained.load('test_selected_mode_legacy',a.D/'retained_materials.py')
  with self.assertRaises(ValueError):retained.runtime_entry(m,old,self.job,'qwen35_08b',self.doc,POLICY)
 def test_null_import_manifest_rejected(self):
  old=dict(self.old,runtime_reuse_manifest=None);m=retained.load('test_selected_null_legacy',a.D/'retained_materials.py')
  with self.assertRaises(ValueError):retained.runtime_entry(m,old,self.job,'qwen35_08b',self.doc,POLICY)
 def test_fresh_wrong_schema_rejected(self):
  old=dict(self.old,runtime_mode='FRESH_ORIGINAL_RUNTIME_INSTALL',archive_mode='DOWNLOAD_ORIGINAL_ARCHIVES',runtime_reuse_manifest=None);m=retained.load('test_selected_fresh_legacy',a.D/'retained_materials.py')
  owner=dict(schema='SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3',profile_mapping=list(r.KEYS),identity=self.ident,owner_root=str(self.job/'materials'),reference_qualified=False,numerical_qualified=False,execution_policy=old['execution_policy'],entries={'qwen35_08b':self.rt})
  pin=self.write(self.job/'materials/runs/bind/owner/SHARED_RUNTIMES_FRESH_JOB_V3.json',owner)
  with self.assertRaises(ValueError):retained.runtime_entry(m,old,self.job,'qwen35_08b',dict(self.doc,runtime_owner=pin),POLICY)

if __name__=='__main__':unittest.main()
