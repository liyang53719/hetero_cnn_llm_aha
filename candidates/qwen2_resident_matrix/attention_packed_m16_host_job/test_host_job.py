"""Actual original Host metadata to exact typed admission; control-only."""
import ast,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from . import prepare

CODE=r'''
import ctypes,time,sys,types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ctypes.CDLL=lambda *a,**k: (_ for _ in ()).throw(AssertionError('no native load'))
from candidates.qwen2_resident_matrix.ffn_public import fixture,model,execute_numeric
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job
from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner,OfficialPrefixOwner
from candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding import ProfiledMatrixService
from candidates.qwen2_resident_matrix.raw_kv_parent.model import ParentLoan, DenseReductionOwner, down
from candidates.qwen2_resident_matrix.attention_packed_m16_entry.cold_construct import ControlLibrary
from candidates.qwen2_resident_matrix.attention_packed_owner.test_owner import Scalar
from candidates.qwen2_resident_matrix.attention_packed_m16.profile import PackedM16PublicProfile
from candidates.qwen2_resident_matrix.attention_packed_m16_entry import contract
from candidates.qwen2_resident_matrix.dense_block_reduce import profile as matrix_profiles
f=fixture.make_qwen2_21_fixture(16);s=Scalar();m=ProfiledMatrixService(ControlLibrary(),matrix_profiles.QWEN2_QKV_PROFILE)
o=OfficialAttentionOwner(m,s);region=f.config.regions[3]
dense=DenseReductionOwner(down.PrefixWorkspace(region.base,16384,f.config.epoch+1,128),enable_ffn_tiles=True,enable_ffn_window=True,enable_ffn_drain=True,enable_dense_drain=True,enable_k_window=True)
parent=ParentLoan(owner=dense,enabled=True)
x=execute_numeric.PublicExecution(model.PublicFrontend(f.memory,f.config),parent.owner,SimpleNamespace(event=lambda e:None),time.monotonic()+10,
 host=model.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),prefix_owner=OfficialPrefixOwner(s),attention_owner=o,matrix_service=m)
for pc in range(10):
 j=x.advance_to_request()['ordinary_request'];assert j.tag&65535==pc
 assert x._host_edge(request_ready=True)['request_fire']
 assert x._host_edge(owner_result=SimpleNamespace(tag=j.tag,status=None,write_bytes=j.write_bytes,useful_macs=0,executed_macs=0))['owner_result_fire']
 x.completion_ready=True;assert x._host_edge()['completion_fire'];x.completion_ready=False
j=x.advance_to_request()['ordinary_request']
assert type(j) is model.group.PrefixJob and type(j) is not Job
assert (x.host.pc,x.host.completed,x.host.jobs)==(12,10,10)
assert len(x.host.scanner.trace)==62 and o.ports()['job_ready']
# Reproduce the original precise type rejection on the same Host request.
import candidates.qwen2_resident_matrix.attention_packed_m16.profile as current
old_source=Path(current.__file__).read_text().replace('from ..ffn_public import model as public','from ..ffn_public.prefix_owners import Job').replace('type(job) is not public.group.PrefixJob','type(job) is not Job')
old=types.ModuleType(current.__name__+'_old_guard');old.__package__=current.__package__;sys.modules[old.__name__]=old
exec(compile(old_source,current.__file__,'exec'),old.__dict__)
try:old.PackedM16PublicProfile('missing','0'*64,'missing','0'*64).install(o,parent,j,7)
except ValueError as e:assert str(e)=='exact idle original M16 Public packed profile required'
else:raise AssertionError('old real-Host failure not reproduced')
profile=PackedM16PublicProfile('missing','0'*64,'missing','0'*64)
class ReachedSourceGate(Exception):pass
with patch.object(contract,'snapshot',side_effect=ReachedSourceGate):
 try:profile.install(o,parent,j,7)
 except ReachedSourceGate:pass
 else:raise AssertionError('real Host job did not reach unchanged source gate')
 # Lookalike original fixture remains rejected in this full-program variant.
 fake=Job(**vars(j))
 for bad in (fake,SimpleNamespace(**vars(j))):
  try:profile.install(o,parent,bad,7)
  except ValueError:pass
  else:raise AssertionError('noncanonical Host job accepted')
 # Each original admission guard remains active before source/library mutation.
 for field,value in (('state','locked'),('poison',True)):
  old=getattr(o,field);setattr(o,field,value)
  try:profile.install(o,parent,j,7)
  except ValueError:pass
  else:raise AssertionError('busy/poison owner accepted')
  finally:setattr(o,field,old)
 parent.owner.lease=object()
 try:profile.install(o,parent,j,7)
 except ValueError:pass
 else:raise AssertionError('retained bank lease accepted')
 parent.owner.lease=None
assert o.packed_schedule is None and parent.raw.owner is None
print('PASS_ACTUAL_HOST_PREFIX_METADATA_TO_TYPED_INSTALL_CONTROL_ONLY')
'''
class Tests(unittest.TestCase):
 def test_only_exact_import_and_type_guard_changes(self):
  with tempfile.TemporaryDirectory() as d:
   a=prepare.prior.compose(Path(d)/'old');b=prepare.compose(Path(d)/'new')
   old=(a/prepare.TARGET).read_text();new=(b/prepare.TARGET).read_text()
   self.assertEqual(new,prepare.repair(old))
   self.assertEqual(new.replace('from ..ffn_public import model as public','from ..ffn_public.prefix_owners import Job').replace('type(job) is not public.group.PrefixJob','type(job) is not Job'),old)
 def test_actual_host_request_and_all_prior_guards(self):
  with tempfile.TemporaryDirectory() as d:
   out=prepare.compose(Path(d)/'source')
   r=subprocess.run([sys.executable,'-B','-c',CODE],cwd=out,capture_output=True,text=True,timeout=10)
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertIn('PASS_ACTUAL_HOST',r.stdout)
 def test_generated_source_closure(self):
  with tempfile.TemporaryDirectory() as d:
   out=prepare.compose(Path(d)/'source')
   code='from candidates.qwen2_resident_matrix.attention_packed_m16_entry.contract import snapshot; print(len(snapshot()))'
   r=subprocess.run([sys.executable,'-B','-c',code],cwd=out,capture_output=True,text=True,timeout=10)
   self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'316')
if __name__=='__main__':unittest.main()
