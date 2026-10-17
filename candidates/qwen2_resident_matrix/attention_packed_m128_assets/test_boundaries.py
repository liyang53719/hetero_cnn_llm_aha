"""Cold negative boundary tests with no framework, ELF or producer execution."""
import copy, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from . import admission as A, origin as O, prerequisite as P
from . import test_admission as fixtures
from ..attention_packed_m128_entry import contract
from ..raw_kv_public_fresh import setup
R=O.R

class BoundaryTests(unittest.TestCase):
 def test_current_backend_mismatch(self):
  name='candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py'
  sources={name:R.file_hash(contract.ROOT/name)}
  with patch.object(contract,'snapshot',return_value=sources),patch.object(R,'read_metadata',return_value={'identity':{'torch':'expected'}}), \
       patch.object(setup,'backend_identity',return_value=(object(),{'torch':'changed'})),patch.object(setup,'backend_threads'):
   with self.assertRaisesRegex(ValueError,'backend/source/build'):A.verify_current_backend('/test/origin')
 def test_current_backend_requires_original_blas(self):
  name='candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py';sources={name:R.file_hash(contract.ROOT/name)}
  with patch.object(contract,'snapshot',return_value=sources),patch.object(R,'read_metadata',return_value={'identity':{'torch':'expected'}}), \
       patch.object(setup,'backend_identity',return_value=(object(),{'torch':'expected'})),patch.object(setup,'backend_threads'),patch.dict(os.environ,{'OMP_NUM_THREADS':'1'}):
   with self.assertRaisesRegex(ValueError,'BLAS'):A.verify_current_backend('/test/origin')
 def test_wrong_combined_library_rejected_before_verifier(self):
  value=fixtures.ManifestTests().fixture()
  with patch.object(contract,'snapshot',return_value=value['source_sha256']):
   with self.assertRaisesRegex(ValueError,'combined packed library'):A.verify_library('/test/lib',manifest=value)
 def test_verify_before_after_asset_drift(self):
  value=fixtures.ManifestTests().fixture();pins=O.provenance()
  value['origin_manifest']['sha256']=pins['metadata']['private/assets/ASSETS.json']['sha256']
  before={'artifacts':{'x':{'sha256':'a'*64}}};after={'artifacts':{'x':{'sha256':'b'*64}}}
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'manifest.json';raw=R.encoded(value);p.write_bytes(raw)
   with patch.object(contract,'snapshot',return_value=value['source_sha256']),patch.object(contract,'git_context'), \
        patch.object(O,'snapshot',side_effect=[(before,{}, {}, []),(after,{}, {}, [])]), \
        patch.object(P,'verify',return_value={}),patch.object(A,'verify_current_backend'), \
        patch.object(A,'verify_library',return_value={'library':'/test/library'}), \
        patch.object(A.views,'build_views',return_value={'provenance':{}}):
    with self.assertRaisesRegex(ValueError,'changed during admission'):A.verify(p,R.sha(raw),rows=128,enable_raw_kv=True)
 def test_no_launch_permission_in_frozen_provenance(self):
  self.assertTrue(all(v is False for v in O.provenance()['claims'].values()))

class PrerequisiteTests(unittest.TestCase):
 def fixture(self):
  pins=copy.deepcopy(O.provenance());p=pins['m16_prerequisite'];sources={'source.py':'a'*64}
  p['source_manifest_sha256']=R.sha(R.encoded(sources));p['compatible_source_sha256']=dict(sources)
  actual=dict(rows=16,status='PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES',actual_dataflow_pass=True,native_acceptance='PASS_OBSERVED_ONLY',
   old_pass_inherited=False,full_29_node_acceptance=False,source_sha256=sources,source_sha256_after=sources,
   snapshot_sha256=p['metadata']['snapshot/SNAPSHOT.json']['sha256'],
   binaries=dict(compile_sha256=pins['library']['receipt_sha256'],library_sha256=pins['library']['sha256']))
  summary=dict(status='PASS_ASSIGNED_OFFICIAL_OBSERVED_GATES_ONLY',child_exit_code=0,cleanup_complete=True,assigned_official_observed_gates_passed=True,
   contract_sha256=p['contract_sha256'],full_29_node_acceptance=False,source_manifest_sha256=p['source_manifest_sha256'],
   validation=dict(summary_sha256=p['metadata']['actual/summary.json']['sha256'],assigned_official_gates=27))
  caller=dict(status='OBSERVED_PASS_ASSIGNED_OFFICIAL_OBSERVED_GATES_ONLY',observation='tool_terminal_result',outer_exit_code=0,child_exit_code=0,
   cleanup_complete=True,actual_chain_completion_verified=True,contract_sha256=p['contract_sha256'],
   private_actual_summary_sha256=p['metadata']['actual/summary.json']['sha256'],summary_sha256=p['metadata']['summary.json']['sha256'],
   full_29_node_acceptance=False,assigned_official_gates=27,official_observed_stages=28,public_completions=21,owner_jobs=17,
   source_manifest_compact_sha256=p['source_manifest_sha256'])
  return pins,{'actual/summary.json':actual,'summary.json':summary,'SUPERVISOR.json':caller,'snapshot/SNAPSHOT.json':{'source_sha256':sources}},sources
 def call(self,pins,meta,sources):
  with tempfile.TemporaryDirectory() as temp,patch.object(O,'provenance',return_value=pins),patch.object(R,'read_metadata',side_effect=lambda r,n,p:copy.deepcopy(meta[n])):
   return P.verify(temp,sources)
 def test_prerequisite_not_inherited_verdict(self):
  result=self.call(*self.fixture());self.assertTrue(result['m16_completion_verified'])
  self.assertIs(result['m128_verdict_inherited'],False);self.assertIs(result['old_pass_inherited'],False)
 def test_source_compatibility(self):
  pins,meta,sources=self.fixture();sources={'source.py':'b'*64}
  with self.assertRaisesRegex(ValueError,'unchanged arithmetic'):self.call(pins,meta,sources)
 def test_exit_and_full29_and_m16_scope(self):
  for role,key,value in [('SUPERVISOR.json','outer_exit_code',False),('actual/summary.json','rows',128),
   ('summary.json','full_29_node_acceptance',True),('SUPERVISOR.json','assigned_official_gates',26),
   ('actual/summary.json','old_pass_inherited',True)]:
   pins,meta,sources=self.fixture();meta[role][key]=value
   with self.assertRaises(ValueError,msg=(role,key,value)):self.call(pins,meta,sources)

if __name__=='__main__':unittest.main()
