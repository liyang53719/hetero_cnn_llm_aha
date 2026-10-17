"""Exact explicit M128 selection edits over the successful M16 entry.

This module is preparation only; generated identities must be frozen separately.
"""
import ast
REDUCED='candidates/qwen2_resident_matrix/dense_block_reduce/check_public_numeric.py'
OFFICIAL='candidates/qwen2_resident_matrix/official_bf16/check_numeric.py'
FULL='candidates/qwen2_resident_matrix/ffn_public/check_fullgraph_numeric.py'
TRANSPORT='candidates/qwen2_resident_matrix/raw_kv_public/model.py'

def replace_once(text,old,new):
 if text.count(old)!=1:raise ValueError('exact M128 composition anchor')
 return text.replace(old,new)

def entry(text,target):
 if target not in (REDUCED,OFFICIAL,FULL):raise ValueError('entry target')
 if target in (REDUCED,OFFICIAL):
  text=replace_once(text,'from ..attention_packed_m16_entry import admission as fresh_assets','from ..attention_packed_m128_assets import admission as fresh_assets')
  text=replace_once(text,'from ..attention_packed_m16_entry import contract as packed_contract','from ..attention_packed_m128_entry import contract as packed_contract')
  text=replace_once(text,'fresh same-input sequential/block-pair outputs; explicitly reused verified native M16 outputs; original gates retained','explicitly reused same-input M128 sequential/block-pair and native outputs; original gates retained')
 else:
  text=replace_once(text,'from ..attention_packed_m16_entry import contract','from ..attention_packed_m128_entry import contract')
 if target==REDUCED:
  text=replace_once(text,"rows==16,'linked packed public21 rows must be exactly 16'","rows==128,'linked packed public21 rows must be exactly 128'")
  text=replace_once(text,'reference_sha256,rows=16,*','reference_sha256,rows=128,*')
  text=replace_once(text,'wall_budget=900,enable_raw_kv=False','wall_budget=2400,enable_raw_kv=False')
  text=replace_once(text,'enable_packed=enable_packed,rows=16)','enable_packed=enable_packed,rows=128)')
  text=replace_once(text,"0<wall_budget<=900,'fresh bounded packed M16 run required'","0<wall_budget<=2400,'fresh bounded packed M128 run required'")
  text=replace_once(text,'from ..attention_packed_observation.monitor import PackedAttentionMonitoringObservation','from ..attention_packed_tiled_observation.monitor import PackedAttentionMonitoringObservation')
  text=replace_once(text,'from ..attention_packed_m16.profile import PackedM16PublicProfile','from ..attention_packed_m128_entry.profile import PackedM128PublicProfile')
  text=replace_once(text,'packed_profile=PackedM16PublicProfile(','packed_profile=PackedM128PublicProfile(')
 return text

def transport(text):
 text=replace_once(text,'from ..attention_packed_m16.profile import PackedM16PublicProfile','from ..attention_packed_m16.profile import PackedM16PublicProfile\n            from ..attention_packed_m128_entry.profile import PackedM128PublicProfile')
 return replace_once(text,'type(packed_profile) in (PackedPublicProfile,PackedM16PublicProfile)','type(packed_profile) in (PackedPublicProfile,PackedM16PublicProfile,PackedM128PublicProfile)')

def unchanged_functions(before,after,names):
 def functions(text):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
 a,b=functions(before),functions(after)
 if any(a[n]!=b[n] for n in names):raise ValueError('original arithmetic/comparison body changed')
