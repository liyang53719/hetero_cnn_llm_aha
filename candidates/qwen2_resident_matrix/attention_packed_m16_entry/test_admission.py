"""Pure linked schema tests. Numerical admission intentionally remains closed."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import admission as a
class AdmissionTests(unittest.TestCase):
 def fixture(self):
  sources={'source.py':'a'*64}
  return dict(schema=1,profile=a.PROFILE,status=a.STATUS,rows=16,past_tokens=0,enable_raw_kv=True,
   enable_packed=True,source_sha256=sources,source_manifest_sha256=a.R.sha(a.R.encoded(sources)),
   origin='/test/origin',references=dict(path='/test/fresh/M16_REFERENCES.json',sha256='b'*64),
   preparation_launch=dict(path='/test/fresh/LAUNCH_RECEIPT.json',sha256='e'*64),
   preparation_summary=dict(path='/test/fresh/summary.json',sha256='f'*64),
   supervisor=dict(path='/test/fresh/SUPERVISOR.json',sha256='1'*64),
   library=dict(receipt=dict(path='/test/library/compile.json',sha256='c'*64),origin_root='/test/build',sha256='d'*64))
 def test_shape_only_no_artifact_access(self):
  with patch.object(a.R,'safe_path',side_effect=AssertionError('artifact read')):
   self.assertEqual(a.validate_manifest(self.fixture()),self.fixture())
 def test_exact_inventory(self):
  for key in self.fixture():
   x=self.fixture();del x[key]
   with self.assertRaises(ValueError):a.validate_manifest(x)
  x=self.fixture();x['extra']=0
  with self.assertRaises(ValueError):a.validate_manifest(x)
 def test_canonical_modes(self):
  for key,values in {'schema':(True,1.0,2),'rows':(True,16.0,128),'past_tokens':(False,0.0,1),
    'enable_raw_kv':(1,False,None),'enable_packed':(1,False,None),'profile':('old',),'status':('READY_FOR_ACTUAL_M128',)}.items():
   for value in values:
    x=self.fixture();x[key]=value
    with self.assertRaises(ValueError):a.validate_manifest(x)
 def test_path_and_hash_schema(self):
  for path in ('relative','/test/../escape'):
   x=self.fixture();x['references']['path']=path
   with self.assertRaises(ValueError):a.validate_manifest(x)
  x=self.fixture();x['library']['receipt']['sha256']='z'*64
  with self.assertRaises(ValueError):a.validate_manifest(x)
 def test_source_digest(self):
  x=self.fixture();x['source_sha256']['source.py']='b'*64
  with self.assertRaises(ValueError):a.validate_manifest(x)
 def test_m128_source_manifest_cannot_relabel(self):
  x=self.fixture();x['profile']='qwen2-public-pv16-pair-assets-m128-v1'
  with self.assertRaises(ValueError):a.validate_manifest(x)
 def test_closed_without_linked_contract(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'manifest.json';raw=a.R.encoded(self.fixture());p.write_bytes(raw)
   with self.assertRaises(ValueError):a.verify(p,a.R.sha(raw),rows=16,enable_raw_kv=True)
 def test_snapshot_modes(self):
  identity=dict(profile=a.PROFILE,manifest='/test/manifest.json',manifest_sha256='a'*64,enable_raw_kv=True)
  x=dict(rows=16,fresh_profile=True,fresh_assets=identity)
  self.assertEqual(a.snapshot_mode(x,True,enable_raw_kv=True),identity)
  for mode in (False,1,None):
   with self.assertRaises(ValueError):a.snapshot_mode(x,mode,enable_raw_kv=True)
if __name__=='__main__':unittest.main()
