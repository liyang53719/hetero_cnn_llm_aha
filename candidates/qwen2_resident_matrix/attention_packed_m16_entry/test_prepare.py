"""Cold source-only checks; no native load, producer or numerical admission."""
import ast,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from . import prepare as p
class PreparationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.root=p.compose(Path(cls.temp.name)/'tree')
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def child(self,body):
  code="import ctypes\nctypes.CDLL=lambda *a,**k:(_ for _ in ()).throw(AssertionError('native load prohibited'))\n"+body
  r=subprocess.run([sys.executable,'-B','-c',code],cwd=self.root,text=True,capture_output=True,timeout=20)
  self.assertEqual(r.returncode,0,r.stderr+r.stdout)
 def test_installed_source_and_three_layer_equality(self):
  self.child("""
from candidates.qwen2_resident_matrix.attention_packed_m16_entry import contract
from candidates.qwen2_resident_matrix.ffn_public import check_fullgraph_numeric as inner
from candidates.qwen2_resident_matrix.official_bf16 import check_numeric as official
from candidates.qwen2_resident_matrix.dense_block_reduce import check_public_numeric as entry
s=contract.snapshot()
assert inner.source_hashes()==s
assert official.source_hashes(fresh_profile=True,enable_raw_kv=True)==s
assert entry.source_hashes(fresh_profile=True,enable_raw_kv=True)==s
""")
 def test_closed_mode_and_run_before_artifacts(self):
  self.child("""
from candidates.qwen2_resident_matrix.dense_block_reduce import check_public_numeric as e
for raw,fresh,packed in ((False,True,True),(True,False,True),(True,True,False),(True,True,1),(True,True,None)):
 try:e.run('/absent/out','/absent/snapshot','0'*64,enable_raw_kv=raw,fresh_profile=fresh,enable_packed=packed)
 except ValueError:pass
 else:raise AssertionError('invalid mode admitted')
try:e.run('/absent/out','/absent/snapshot','0'*64,enable_raw_kv=True,fresh_profile=True,enable_packed=True)
except (ValueError,__import__('subprocess').CalledProcessError):pass
else:raise AssertionError('entry ran without genuine Git or snapshot')
""")
 def test_observer_union_rebinding(self):
  self.child("""
from candidates.qwen2_resident_matrix.attention_packed_m16_entry import contract
from candidates.qwen2_resident_matrix.attention_packed_observation import monitor
monitor.source_check(contract.snapshot())
""")
 def test_owner_type_and_physical_source_unchanged(self):
  pins=p.check()
  for name in ('ffn_attention/attention_owner.py','official_bf16/owners.py','ffn_attention/matrix_numeric.cpp',
               'ffn_public/execute_numeric.py','ffn_public/fullgraph_execution.py'):
   relative='candidates/qwen2_resident_matrix/'+name
   self.assertEqual(pins['generated'][relative],p.packed.check()['generated'][relative])
 def test_source_drift_rejected_before_entry(self):
  self.child("""
from candidates.qwen2_resident_matrix.attention_packed_m16_entry import contract
p=contract.ROOT/'candidates/qwen2_resident_matrix/ffn_public/prefix_owners.py'
raw=p.read_bytes()
try:
 p.write_bytes(raw+bytes([10])+b'# source drift'+bytes([10]))
 try:contract.snapshot()
 except ValueError:pass
 else:raise AssertionError('source mutation accepted')
finally:p.write_bytes(raw)
""")
 def test_actual_execution_projection_rejects_gate_or_arithmetic_edit(self):
  with tempfile.TemporaryDirectory() as temporary:
   base=Path(temporary)/'fresh';p.fresh.prepare(base,enable_raw_kv=True)
   before={name:(base/name if (base/name).exists() else p.ROOT/name).read_text() for name in p.TARGETS}
   after={name:(self.root/name).read_text() for name in p.TARGETS}
   p.check_scope(before,after)
   for old,new in (("gate.opened=True","gate.opened=False"),
    ("shared_scalar=scalar.ScalarService()","shared_scalar=scalar.ScalarService(); shared_scalar.reset()"),
    ("report['comparison']=compare(s,actual,inputs,capture,silu_bytes,native)","report['comparison']={}")):
    changed=dict(after);self.assertEqual(changed[p.TARGETS[0]].count(old),1)
    changed[p.TARGETS[0]]=changed[p.TARGETS[0]].replace(old,new)
    with self.assertRaises(ValueError):p.check_scope(before,changed)
class ContextTests(unittest.TestCase):
 def fixture(self):
  from . import contract as c
  sources={'original.py':'a'*64}
  raw=(json.dumps(sources,sort_keys=True,separators=(',',':'))+'\n').encode()
  return c,sources,dict(profile=c.PROFILE,attempt=1,pid=c.os.getpid(),started=1000.,work_deadline=1924.,
   outer_deadline=1930.,source_manifest_sha256=c.hashlib.sha256(raw).hexdigest())
 def test_exact_bounded_context(self):
  from unittest.mock import patch
  c,s,v=self.fixture()
  with patch.object(c,'snapshot',return_value=s),patch.object(c,'git_context',return_value={}),patch.object(c.time,'monotonic',return_value=1010.):
   self.assertEqual(c.authorize_run(v),s)
 def test_wrong_expired_or_extended_context(self):
  from unittest.mock import patch
  for key,value in (('pid',True),('attempt',True),('started',False),('work_deadline',1925.),
   ('outer_deadline',1931.),('source_manifest_sha256','0'*64),('profile','foreign')):
   c,s,v=self.fixture();v[key]=value
   with patch.object(c,'snapshot',return_value=s),patch.object(c,'git_context',return_value={}),patch.object(c.time,'monotonic',return_value=1010.):
    with self.assertRaises(ValueError):c.authorize_run(v)
  c,s,v=self.fixture()
  with patch.object(c,'snapshot',side_effect=AssertionError('late preflight')),patch.object(c.time,'monotonic',return_value=1924.):
   with self.assertRaises(ValueError):c.authorize_run(v)
 def test_preflight_consumes_same_deadline(self):
  from unittest.mock import patch
  c,s,v=self.fixture()
  with patch.object(c,'snapshot',return_value=s),patch.object(c,'git_context',return_value={}),patch.object(c.time,'monotonic',side_effect=[1010.,1924.]):
   with self.assertRaises(ValueError):c.authorize_run(v)
 def test_none_and_boolean_profile_flags(self):
  from unittest.mock import patch
  c,_,_=self.fixture()
  for value in (None,False,1):
   with patch.object(c,'snapshot',side_effect=AssertionError('mode gate late')):
    with self.assertRaises(ValueError):c.modes(fresh_profile=True,enable_raw_kv=True,enable_packed=value,rows=16)
 def test_git_environment_redirection_rejected(self):
  from unittest.mock import patch
  c,_,_=self.fixture()
  with patch.dict(c.os.environ,{'GIT_DIR':'/foreign'}),patch.object(c.subprocess,'run',side_effect=AssertionError('redirected git')):
   with self.assertRaises(ValueError):c.git_context()
if __name__=='__main__':unittest.main()
