"""Actual original HostControl M128 request, without any native arithmetic."""
import subprocess,sys,tempfile,unittest
from pathlib import Path
from . import prepare
from ..attention_packed_m16_host_job.test_host_job import CODE as M16_CODE

def code():
 s=M16_CODE
 start=s.index('# Reproduce the original precise type rejection')
 end=s.index("profile=PackedM16PublicProfile(",start)
 s=s[:start]+s[end:]
 s=s.replace('make_qwen2_21_fixture(16)','make_qwen2_21_fixture(128)')
 s=s.replace('from candidates.qwen2_resident_matrix.attention_packed_m16.profile import PackedM16PublicProfile','from candidates.qwen2_resident_matrix.attention_packed_m128_entry.profile import PackedM128PublicProfile')
 s=s.replace('from candidates.qwen2_resident_matrix.attention_packed_m16_entry import contract','from candidates.qwen2_resident_matrix.attention_packed_m128_entry import contract')
 s=s.replace('profile=PackedM16PublicProfile(','profile=PackedM128PublicProfile(')
 s=s.replace("assert type(j) is model.group.PrefixJob and type(j) is not Job","assert type(j) is model.group.PrefixJob and type(j) is not Job and j.m==128")
 return s

class Tests(unittest.TestCase):
 def test_real_host_m128_exact_admission_before_source_gate(self):
  with tempfile.TemporaryDirectory() as d:
   out=prepare.compose(Path(d)/'source')
   r=subprocess.run([sys.executable,'-B','-c',code()],cwd=out,capture_output=True,text=True,timeout=15)
   self.assertEqual(r.returncode,0,r.stderr);self.assertIn('PASS_ACTUAL_HOST',r.stdout)
 def test_installed_source_closure_without_native_load(self):
  with tempfile.TemporaryDirectory() as d:
   out=prepare.compose(Path(d)/'source')
   script=r"""import ctypes
ctypes.CDLL=lambda *a,**k:(_ for _ in ()).throw(AssertionError('native forbidden'))
from candidates.qwen2_resident_matrix.attention_packed_m128_entry.contract import snapshot
from candidates.qwen2_resident_matrix.dense_block_reduce import check_public_numeric as entry
from candidates.qwen2_resident_matrix.official_bf16 import check_numeric as prior
from candidates.qwen2_resident_matrix.ffn_public import check_fullgraph_numeric as base
from candidates.qwen2_resident_matrix.attention_packed_m128_assets import admission
expected=snapshot()
assert entry.source_hashes(fresh_profile=True,enable_raw_kv=True)==expected
assert prior.source_hashes(fresh_profile=True,enable_raw_kv=True)==expected
assert base.source_hashes()==expected
assert admission.source_snapshot(enable_raw_kv=True)==expected
from pathlib import Path
for action in (
 lambda: entry.prepare(Path('must-not-exist'),None,None,None,rows=16,enable_raw_kv=True,fresh_profile=True,enable_packed=True),
 lambda: admission.snapshot_mode(dict(fresh_profile=True,rows=128,fresh_assets=dict(profile='qwen2-public-pv16-packed-m16-linked-v1',manifest='/missing',manifest_sha256='0'*64,enable_raw_kv=True)),True,enable_raw_kv=True)):
 try:action()
 except ValueError:pass
 else:raise AssertionError('cross-profile accepted')
assert not Path('must-not-exist').exists()
target=Path('candidates/qwen2_resident_matrix/attention_packed_owner/schedule.py');raw=target.read_bytes()
try:
 target.write_bytes(raw+b'\n# source drift negative\n')
 try:entry.source_hashes(fresh_profile=True,enable_raw_kv=True)
 except ValueError:pass
 else:raise AssertionError('installed source drift accepted')
finally:target.write_bytes(raw)
assert snapshot()==expected
print(len(expected))
"""
   r=subprocess.run([sys.executable,'-B','-c',script],cwd=out,capture_output=True,text=True,timeout=15)
   self.assertEqual(r.returncode,0,r.stderr);self.assertGreater(int(r.stdout),316)
if __name__=='__main__':unittest.main()
