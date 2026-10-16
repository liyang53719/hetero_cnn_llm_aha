"""Cold provenance-only fixtures; synthetic ELF bytes are never loaded."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import library_origin as v
from ..official_bf16 import dense_silu as original

class OriginTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.origin=self.root/'origin';self.execution=self.root/'execution';self.output=self.root/'library';self.output.mkdir()
  for r in (self.origin,self.execution):
   for n in (*original.SOURCE_CLOSURE,'candidates/qwen2_resident_matrix/official_bf16/dense_silu.py'):
    p=r/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('source '+n)
  self.binary=self.output/'lib.so';self.binary.write_bytes(b'\x7fELFsynthetic cold bytes')
  self.compiler=dict(path='/usr/bin/test-compiler',sha256='a'*64,version='test only')
  self.receipt=self.output/'compile.json'
  self.data=dict(schema=1,returncode=0,policy=original.POLICY_VERSION,status='PASS',selected_silu_entrypoint='sf_vector_bf16_v1',original_silu_entrypoint='sf_vector',library=str(self.binary),library_sha256=v.sha(self.binary),compiler=self.compiler,argv=[self.compiler['path'],*original.STRICT_FLAGS,*(str(self.origin/n) for n in original.TRANSLATION_UNITS),'-o',str(self.binary)],source_sha256={n:v.sha(self.origin/n) for n in original.SOURCE_CLOSURE})
 def call(self):
  self.receipt.write_text(json.dumps(self.data))
  with patch.object(v,'loaded_original',return_value=original), patch.object(original,'compiler_identity',return_value=self.compiler):
   return v.verify(self.receipt,v.sha(self.receipt),origin_root=self.origin,execution_root=self.execution,library_sha256=v.sha(self.binary))
 def test_real_imported_method_identity(self):
  self.assertIs(v.loaded_original(original.ROOT),original)
  with patch.object(original,'compiler_identity',return_value=self.compiler):
   with self.assertRaises(ValueError):v.loaded_original(original.ROOT)
 def test_wrong_import_tree(self):
  with self.assertRaises(ValueError):v.loaded_original(self.execution)
 def test_equal_bytes_distinct_paths(self):self.assertEqual(self.call(),self.data)
 def test_moved_argv_not_forged(self):
  self.data['argv']=[x.replace(str(self.origin),str(self.execution)) for x in self.data['argv']]
  with self.assertRaises(ValueError):self.call()
 def test_execution_source_drift(self):
  (self.execution/original.SOURCE_CLOSURE[0]).write_text('drift')
  with self.assertRaises(ValueError):self.call()
 def test_origin_source_drift(self):
  (self.origin/original.SOURCE_CLOSURE[1]).write_text('drift')
  with self.assertRaises(ValueError):self.call()
 def test_verifier_source_drift(self):
  (self.execution/'candidates/qwen2_resident_matrix/official_bf16/dense_silu.py').write_text('drift')
  with self.assertRaises(ValueError):self.call()
 def test_canonical_receipt_fields(self):
  for field,value in (('schema',True),('returncode',False)):
   old=self.data[field];self.data[field]=value
   with self.assertRaises(ValueError):self.call()
   self.data[field]=old
 def test_duplicate_keys_and_nonfinite(self):
  for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
   self.receipt.write_bytes(raw)
   with self.assertRaises(ValueError):v.metadata(self.receipt,hashlib.sha256(raw).hexdigest())
 def test_symlink_rejected(self):
  self.call();alias=self.root/'alias';alias.symlink_to(self.receipt)
  with self.assertRaises(ValueError):v.metadata(alias,v.sha(self.receipt))
if __name__=='__main__':unittest.main()
