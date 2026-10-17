"""Genuine Git-backed constructor check with no DUT ELF and no numerical jobs.

The only ctypes load allowed is libc for the unchanged ScalarService fenv
probe. Matrix ABI calls use an explicit control-only stub; this is not native
arithmetic evidence. The original Public frontend may accept its metadata
launch, but no clock edge, command, memory payload or numerical job is issued.
"""
import ctypes,time
from . import contract
class Function:
 def __init__(self,name):self.name=name
 def __call__(self,*args):
  if self.name=='matrix_accumulator_bytes':return 5*16*256*4
  if self.name=='matrix_accumulator_address':return 1
  if self.name in ('matrix_guard_enable','matrix_state'):return 0
  raise AssertionError('unexpected control-only Matrix ABI call')
class ControlLibrary:
 def __getattr__(self,name):
  value=Function(name);setattr(self,name,value);return value

def check():
 before=contract.snapshot();git=contract.git_context()
 original=ctypes.CDLL;loads=[]
 def only_libc(name,*args,**kwargs):
  if name is not None:raise AssertionError('DUT/native library loading prohibited')
  loads.append('libc-fenv');return original(name,*args,**kwargs)
 ctypes.CDLL=only_libc
 try:
  from ..dense_block_reduce import check_public_numeric as entry
  (modules,dense,_,native),new=entry.runtime(enable_raw_kv=True,fresh_profile=True)
  helper,original_execution,fixtures,public,prefix,_,scalar,_,_,_,_,_=modules
  owner_module,binding,profiles,execution,_,_=new
  from ..official_bf16 import execution as policy
  service=binding.ProfiledMatrixService(ControlLibrary(),profiles.QWEN2_QKV_PROFILE)
  shared=scalar.ScalarService();attention=policy.OfficialAttentionOwner(service,shared)
  fixture=fixtures.make_qwen2_21_fixture(128,7)
  physical=prefix.PhysicalMemory(fixture,{})
  region=fixture.config.regions[3];n=original_execution.numeric
  owner=owner_module.DenseReductionOwner(n.model.PrefixWorkspace(region.base,region.limit-region.base,8,2560),
   enable_dense_drain=True,enable_k_window=True,enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True)
  x=execution.ReducedPublicExecution(public.PublicFrontend(physical.metadata_port(),fixture.config),owner,
   n.CappedTrace(),time.monotonic()+5,fixture=fixture,
   host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
   prefix_owner=policy.OfficialPrefixOwner(shared),attention_owner=attention,matrix_service=service)
  contract.need(type(x) is execution.ReducedPublicExecution and x.owner is owner and
   x.attention_owner is attention and x.prefix_owner.scalar is shared and service.owner is None and
   shared.client is None and attention.ports()['job_ready'] and not x.counts and not physical.counts,
   'actual original constructors or initial debt changed')
  contract.need(contract.snapshot()==before,'constructor source drift')
  return dict(status='PASS_GIT_BACKED_ORIGINAL_CONSTRUCTORS_CONTROL_ONLY',git=git,source_files=len(before),
   ctypes_loads=loads,original_public_events=21,numerical_jobs=0,native_arithmetic=False,
   payload_reads=0,parent_ticks=0,source_recheck='UNCHANGED')
 finally:ctypes.CDLL=original

if __name__=='__main__':
 import json
 print(json.dumps(check(),sort_keys=True))
