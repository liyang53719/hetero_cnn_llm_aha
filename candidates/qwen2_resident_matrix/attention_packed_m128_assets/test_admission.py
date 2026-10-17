"""Cold synthetic tests. No original private files, model imports or numerical jobs."""
import copy, json, math, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from . import admission as A, origin as O, views as V
R=O.R

class ManifestTests(unittest.TestCase):
 def fixture(self):
  sources={'source.py':'a'*64}
  return dict(schema=1,profile=A.PROFILE,status=A.STATUS,rows=128,past_tokens=0,
   enable_raw_kv=True,enable_packed=True,source_sha256=sources,source_manifest_sha256=R.sha(R.encoded(sources)),
   origin='/test/origin',origin_manifest=dict(path='/test/origin/private/assets/ASSETS.json',sha256='b'*64),
   m16_prerequisite='/test/m16',library=dict(receipt=dict(path='/test/build/compile.json',sha256='c'*64),
   origin_root='/test/build/source',sha256='d'*64))
 def test_pure_schema(self):
  with patch.object(R,'safe_path',side_effect=AssertionError('file access')):
   self.assertEqual(A.validate_manifest(self.fixture()),self.fixture())
 def test_exact_inventory(self):
  for key in self.fixture():
   value=self.fixture();del value[key]
   with self.assertRaises(ValueError):A.validate_manifest(value)
  value=self.fixture();value['extra']=False
  with self.assertRaises(ValueError):A.validate_manifest(value)
 def test_no_m16_relabel(self):
  for key,values in {'schema':(True,1.0,2),'rows':(True,16,128.0),'past_tokens':(False,0.0,1),
   'enable_raw_kv':(1,False,None),'enable_packed':(1,False,None),'profile':('qwen2-public-pv16-packed-m16-linked-v1',),
   'status':('READY_FOR_ACTUAL_M128',)}.items():
   for item in values:
    value=self.fixture();value[key]=item
    with self.assertRaises(ValueError,msg=(key,item)):A.validate_manifest(value)
 def test_path_escape_or_repoint(self):
  for name in ('relative','/test/../escape','/test//origin','/test/./origin','/test\\origin','/test\0origin'):
   value=self.fixture();value['origin']=name
   with self.assertRaises(ValueError):A.validate_manifest(value)
  value=self.fixture();value['origin_manifest']['path']='/test/m16/ASSETS.json'
  with self.assertRaises(ValueError):A.validate_manifest(value)
 def test_source_mutation(self):
  value=self.fixture();value['source_sha256']['source.py']='e'*64
  with self.assertRaises(ValueError):A.validate_manifest(value)
 def test_manifest_bytes(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'manifest.json';raw=R.encoded(self.fixture());p.write_bytes(raw)
   self.assertEqual(A.read_manifest(p,R.sha(raw)),self.fixture())
   p.write_bytes(raw+b' ')
   with self.assertRaises(ValueError):A.read_manifest(p,R.sha(raw))
 def test_duplicate_and_nonfinite_json(self):
  for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e999}'):
   with self.assertRaises(ValueError):R.strict_json(raw)
 def test_modes(self):
  identity=dict(profile=A.PROFILE,manifest='/test/manifest.json',manifest_sha256='a'*64,enable_raw_kv=True)
  value=dict(rows=128,fresh_profile=True,fresh_assets=identity)
  self.assertEqual(A.snapshot_mode(value,True,enable_raw_kv=True),identity)
  for row in (16,True,128.0):
   with self.assertRaises(ValueError):A.fresh_mode(True,'/test/a','a'*64,rows=row)
  for mode in (False,1,None):
   with self.assertRaises(ValueError):A.snapshot_mode(value,mode,enable_raw_kv=True)
 def test_closed_without_contract(self):
  with self.assertRaises((ValueError,FileNotFoundError)):
   A.verify('/nonexistent','a'*64,rows=16,enable_raw_kv=True)

class NativeTests(unittest.TestCase):
 def fixture(self,rows=128):
  shape=O.shapes(rows); exports=O.export_shapes(rows)
  policy={'operator':{'max_abs':0.03125,'mean_abs':0.005},'block':{'max_abs':0.05,'mean_abs':0.01},
   'sha256':'5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5'}
  result=dict(status='PASS_BF16_STAGE_BUDGET',tokens=rows,carried=False,m16_gate_sha256='a'*64 if rows==128 else None,
   torch_threads=4,payload_manifest_sha256='b'*64,official_framework_forward=True,policy=policy,modes={})
  for name in ('rtl_execution','hardware_recipe_acceptance','logits','full_model_quality','manifest_whole_checkpoint_hash_verified'):result[name]=False
  declared=dict(producer='qwen2-native-qkv-qk-pair-generated-v1',outputs={})
  for mode in R.MODES:
   semantics={n:True for n in ('mask_exact','native_fp32_probability_sum_within_2e_5','independent_fp32_probability_sum_within_2e_5',
    'native_cache_append_k_exact','native_cache_append_v_exact','independent_cache_append_k_exact','independent_cache_append_v_exact',
    'native_future_probability_zero','independent_future_probability_zero')}
   phase=dict(phase=0,past_tokens=0,token_ids=list(range(rows)),position_ids=list(range(rows)),semantics=semantics,
    all_semantics_exact=True,stages={},failed_stages=[],status='PASS_BF16_STAGE_BUDGET' if mode=='bf16' else 'DIAGNOSTIC_FP32')
   result['modes'][mode]=dict(phases=[phase]);declared['outputs'][mode]={m:{} for m in R.METHODS}
   for name,geometry in shape.items():
    item=dict(shape=geometry,elements=math.prod(geometry),finite=True)
    if name=='mask':item.update(contract='exact_causal_mask',bit_exact=True,passed=True)
    elif mode=='fp32' or name=='softmax_fp32':item.update(passed=None,contract=None,status='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE')
    else:item.update(limits=policy['block' if name=='y' else 'operator'],max_abs=0.0,mean_abs=0.0,passed=True,
     contract='spec/numerical_contract.md:'+('block' if name=='y' else 'operator'))
    for method,prefix in zip(R.METHODS,('native','independent')):
     relative='%s/phase_0/%s_%s.f32le'%(mode,prefix,name)
     item[prefix+'_file']=relative;item[prefix+'_export_shape']=exports[name];item[prefix+'_file_sha256']='c'*64
     declared['outputs'][mode][method][name]=dict(path=('native/' if rows==128 else 'native_m16/')+relative,
      bytes=math.prod(geometry)*4,sha256='c'*64)
    phase['stages'][name]=item
  return result,declared
 def validate(self,result,declared):O.validate_native(result,declared,'b'*64,rows=128,prerequisite_sha256='a'*64)
 def test_authentic_m128_geometry(self):self.validate(*self.fixture())
 def test_native_m16_separate_prerequisite(self):
  result,declared=self.fixture(16)
  O.validate_native(result,declared,'b'*64,rows=16,prerequisite_sha256=None)
  with self.assertRaises(ValueError):self.validate(result,declared)
 def test_no_relabel_or_threshold_relaxation(self):
  for key,value in [('tokens',16),('tokens',128.0),('m16_gate_sha256',None),('carried',True),('rtl_execution',True)]:
   result,declared=self.fixture();result[key]=value
   with self.assertRaises(ValueError):self.validate(result,declared)
  result,declared=self.fixture();result['policy']['operator']['max_abs']=0.04
  with self.assertRaises(ValueError):self.validate(result,declared)
 def test_bad_native_semantics(self):
  result,declared=self.fixture();result['modes']['bf16']['phases'][0]['semantics']['mask_exact']=1
  with self.assertRaises(ValueError):self.validate(result,declared)
 def test_bad_token_major_export(self):
  result,declared=self.fixture();result['modes']['bf16']['phases'][0]['stages']['q']['native_export_shape']=[1,12,128,128]
  with self.assertRaises(ValueError):self.validate(result,declared)
 def test_failed_or_diagnostic_gate_not_promoted(self):
  for name in ('y','softmax_fp32'):
   result,declared=self.fixture();result['modes']['bf16']['phases'][0]['stages'][name]['passed']=False
   with self.assertRaises(ValueError):self.validate(result,declared)

class LateReferenceTests(unittest.TestCase):
 def test_only_origin_and_late_hash(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);p=root/'ref.f32le';p.write_bytes(b'abcd')
   item=dict(root='origin',path=p.name,bytes=4,sha256=R.sha(b'abcd'))
   ref=dict(fresh_profile=V.PROFILE,roots={'origin':str(root)},fresh_lookup={'ref':item})
   self.assertEqual(V.read_reference_bytes(ref,'ref'),b'abcd')
   p.write_bytes(b'abce')
   with self.assertRaises(ValueError):V.read_reference_bytes(ref,'ref')
   ref['roots']['fresh']=str(root)
   with self.assertRaises(ValueError):V.read_reference_bytes(ref,'ref')
 def test_path_and_inode_aliases(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);a=root/'a';a.write_bytes(b'1234');b=root/'b';b.hardlink_to(a)
   with self.assertRaises(ValueError):R.no_aliases([a,b])
   c=root/'c';c.symlink_to(a)
   with self.assertRaises(ValueError):V.path({'origin':str(root)},dict(root='origin',path='c',bytes=4,sha256=R.sha(b'1234')))
 def test_m16_native_decode_rejected_before_import(self):
  with self.assertRaises(ValueError):V.read_native_reference({},b'',rows=16,method=R.METHODS[0],name='q',shape=(1,12,16,128))
 def test_token_major_decoder_and_bad_bytes(self):
  # Replace the decoder, so this cold test never allocates or decodes arrays.
  import sys,types
  mod=types.ModuleType('candidates.qwen2_resident_matrix.official_bf16.reference_layout')
  calls=[];mod.decode_qk=lambda raw,shape,layout:calls.append((shape,layout)) or 'decoded'
  raw=b'q'*(4*12*128*128);item=dict(root='origin',path='q',bytes=len(raw),sha256=R.sha(raw))
  ref=dict(fresh_profile=V.PROFILE,fresh_lookup={'references/'+R.METHODS[0]+'/q.f32le':item})
  with patch.dict(sys.modules,{mod.__name__:mod}):
   self.assertEqual(V.read_native_reference(ref,raw,rows=128,method=R.METHODS[0],name='q',shape=[1,12,128,128]),'decoded')
   self.assertEqual(calls,[([1,12,128,128],'token_major')])
   with self.assertRaises(ValueError):V.read_native_reference(ref,raw,rows=128,method=R.METHODS[0],name='q',shape=[True,12,128,128])
   with self.assertRaises(ValueError):V.read_native_reference(ref,b'x',rows=128,method=R.METHODS[0],name='q',shape=[1,12,128,128])

if __name__=='__main__':unittest.main()
