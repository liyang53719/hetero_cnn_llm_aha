"""Source-only M16 tests: no CDLL, compiler, producer or Public launch."""
import ast,hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from . import prepare

class PreparationTests(unittest.TestCase):
 def test_closed_composition_reverse(self):
  with tempfile.TemporaryDirectory() as d:
   out=prepare.compose(Path(d)/'out');base=prepare.prior.compose(Path(d)/'base')
   installed=prepare.verify_installed(out)
   self.assertEqual(installed['candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp'],prepare.prior.owner.native.check()['generated']['candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp'])
   r=subprocess.run(['patch','--batch','--fuzz=0','-R','-p1','-i',str(prepare.HERE/'m16.patch')],cwd=out,capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr)
   for n in prepare.TARGETS:self.assertEqual((out/n).read_bytes(),(base/n).read_bytes())
 def test_schedule_only_domain_changes(self):
  with tempfile.TemporaryDirectory() as d:
   out=prepare.compose(Path(d)/'out');n=prepare.TARGETS[0]
   def body(path):
    tree=ast.parse(path.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef));return next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='run').body
   a,b=body(prepare.ROOT/n),body(out/n)
   self.assertEqual([ast.dump(x) for x in a[1:]],[ast.dump(x) for x in b[1:]])
   namespace={'PrefixFault':ValueError,'type':type,'int':int}
   domain=ast.Module(body=[b[0]],type_ignores=[])
   for m in (1,2,16):
    namespace['j']=type('Job',(),{'m':m})();exec(compile(domain,'domain','exec'),namespace)
   for m in (True,1.0,0,3,17,128):
    namespace['j']=type('Job',(),{'m':m})()
    with self.assertRaises(ValueError):exec(compile(domain,'domain','exec'),namespace)
 def test_installed_drift(self):
  with tempfile.TemporaryDirectory() as d:
   out=prepare.compose(Path(d)/'out');target=out/prepare.TARGETS[0];target.write_text(target.read_text()+'\n# drift\n')
   with self.assertRaises(ValueError):prepare.verify_installed(out)
 def test_helper_and_silu_closure(self):
  p=prepare.check()
  for name in prepare.EXTRA:self.assertIn(name,p['sources'])
  with tempfile.TemporaryDirectory() as d:
   out=prepare.compose(Path(d)/'out')
   # A fresh interpreter imports helpers only from this composed tree. CDLL
   # is prohibited; library plan must not invoke a native load or compiler.
   code="""import ctypes,subprocess
ctypes.CDLL=lambda *a,**k: (_ for _ in ()).throw(AssertionError('native load'))
subprocess.run=lambda *a,**k: (_ for _ in ()).throw(AssertionError('compiler'))
from candidates.qwen2_resident_matrix.attention_packed_m16.library import plan
from candidates.qwen2_resident_matrix.attention_packed_m16.profile import PackedM16PublicProfile
p=plan()
assert p['status']=='PREPARATION_ONLY' and len(p['sources'])==4
assert len(p['translation_units'])==2 and p['compiler_timeout_seconds']==30
assert not p['full_public_admitted']
"""
   r=subprocess.run([sys.executable,'-c',code],cwd=out,capture_output=True,text=True,timeout=10)
   self.assertEqual(r.returncode,0,r.stderr)
 def test_canonical_profile_rejects_before_mutation(self):
  with tempfile.TemporaryDirectory() as d:
   out=prepare.compose(Path(d)/'out')
   code="""import sys,json,hashlib,tempfile
sys.path.insert(0,sys.argv[1])
from pathlib import Path
from types import SimpleNamespace
from candidates.qwen2_resident_matrix.attention_packed_m16.profile import PackedM16PublicProfile
from candidates.qwen2_resident_matrix.raw_kv_public.model import PublicKvTransport
from candidates.qwen2_resident_matrix.raw_kv_parent.model import ParentLoan
from candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding import ProfiledMatrixService
from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job
from candidates.qwen2_resident_matrix.attention_packed_owner.test_owner import Scalar
m=ProfiledMatrixService.__new__(ProfiledMatrixService);m.owner=None;m.lib=SimpleNamespace(matrix_state=lambda:0)
o=OfficialAttentionOwner(m,Scalar());p=ParentLoan(enabled=True);raw=p.raw
for rows,version in ((1,1),(2,1),(128,1),(True,1),(16,True),(16,2)):
 j=Job('Attention',65537,1048576,2097152,4194304,rows,1536,128,int(rows)*6144,c=3145728)
 try: PackedM16PublicProfile('missing','0'*64,version).install(o,p,j,7)
 except ValueError: pass
 else: raise AssertionError('invalid M16 profile admitted')
 assert p.raw is raw and o.packed_schedule is None and p.owner.clock==0
j=Job('Attention',65537,1048576,2097152,4194304,16,1536,128,16*6144,c=3145728)
with tempfile.TemporaryDirectory() as d:
 r=Path(d)/'receipt.json'
 for data in ({'schema':True,'returncode':0},{'schema':1,'returncode':False},{'schema':1,'returncode':0}):
  r.write_text(json.dumps(data));h=hashlib.sha256(r.read_bytes()).hexdigest()
  try: PackedM16PublicProfile(str(r),h).install(o,p,j,7)
  except ValueError: pass
  else: raise AssertionError('malformed combined receipt admitted')
  assert p.raw is raw and o.packed_schedule is None and p.owner.clock==0
"""
   r=subprocess.run([sys.executable,'-I','-c',code,str(out)],capture_output=True,text=True,timeout=10)
   self.assertEqual(r.returncode,0,r.stderr)
 def test_full_launch_closed(self):
  for rows in (16,128):
   with self.assertRaises(ValueError):prepare.authorize_full_numeric(rows=rows)

if __name__=='__main__':unittest.main()
