"""Original M128 comparison geometry over verified current-job reference outputs.

Only call build_views after the same-host admission verifier has checked every
record, producer receipt, byte identity and alias. This module grants no launch.
"""
import math
from pathlib import Path
from ..attention_packed_m16_assets import reuse as R
from ..raw_kv_public_fresh import assets as original
from ..attention_packed_m128_assets import origin as O
from .contract import PROFILE


def record(root,item):
 R.need(root == 'origin' and type(item) is dict and
        set(item)=={'path','bytes','sha256'},'linked artifact schema')
 return dict(root=root,**item)

def path(roots,item):
 R.need(type(roots) is dict and set(roots)=={'origin'},'one explicit immutable origin')
 R.need(type(item) is dict and set(item)=={'root','path','bytes','sha256'} and item['root'] in roots,'linked root selector')
 return R.checked(Path(roots[item['root']]),{k:item[k] for k in ('path','bytes','sha256')},content=True)

def build_views(*,manifest_path,manifest_sha256,origin_assets,origin_manifest,
                native_result,exported,library_receipt,library,origin_identity,m16_prerequisite,payload_paths,producer_generated_sha256):
 roots=dict(origin=str(R.safe_path(origin_assets,directory=True)))
 roles={'embeddings':'embed_tokens.rows_0_255','gamma0':'input_layernorm.weight',
  'gamma1':'post_attention_layernorm.weight','wq':'self_attn.q_proj.weight','bq':'self_attn.q_proj.bias',
  'wk':'self_attn.k_proj.weight','bk':'self_attn.k_proj.bias','wv':'self_attn.v_proj.weight',
  'bv':'self_attn.v_proj.bias','wo':'self_attn.o_proj.weight','wg':'mlp.gate_proj.weight',
  'wu':'mlp.up_proj.weight','wd':'mlp.down_proj.weight'}
 native=origin_manifest['native'];seq=origin_manifest['sequential'];red=origin_manifest['reduced']
 lookup={'raw_stages/'+n:record('origin',v) for n,v in seq['outputs'].items()}
 lookup.update({'tensors/candidate_'+n+'.f32le':record('origin',v) for n,v in seq['tensors'].items()})
 for method in R.METHODS:
  lookup.update({'references/%s/%s.f32le'%(method,n):record('origin',v) for n,v in native['outputs']['bf16'][method].items()})
 comparison=[record('origin',v) for v in (*seq['outputs'].values(),*seq['tensors'].values(),*red['outputs'].values())]
 comparison += [record('origin',v) for v in R.records(native['outputs'])]
 original_input=dict(token_ids=list(range(128)),positions=list(range(128)),input_x_sha256=O.INPUT_X_SHA256,
  intermediate_preloads=0,rope_theta=1000000.0,
  rope_table_recipe='FP32 exponent/powf/reciprocal/phase multiply/sinf/cosf then BF16; positions0..255 only',
  readonly_bytes=original.ARENA_BYTES,readonly_sha256=O.ARENA_SHA256)
 arena=record('origin',origin_manifest['readonly']['arena']);table=record('origin',origin_manifest['readonly']['table'])
 spec=dict(model=original.MODEL,revision=original.REVISION,layer=0,original_input=original_input,
  fresh_profile=PROFILE,metadata_sha256={str(manifest_path):manifest_sha256},payloads={
   role:dict(path=payload_paths[name],
    bytes=original.TENSOR_PINS[name]['bytes'],sha256=original.TENSOR_PINS[name]['sha256'],shape=original.TENSOR_PINS[name]['shape'])
   for role,name in roles.items()},
  comparison_only={str(i):dict(v,path=str(path(roots,v))) for i,v in enumerate(comparison)},
  oracle_arena=dict(arena,path=str(path(roots,arena))))
 identity=dict(profile=PROFILE,manifest=str(manifest_path),manifest_sha256=manifest_sha256,enable_raw_kv=True)
 provenance=dict(profile=PROFILE,fresh_assets=identity,new_official_forward_executed=True,
  native_execution_reused=False,oracle_execution_reused=False,historical_receipts_reused=False,
  actual_chain_executed=False,old_pass_inherited=False,full_29_node_acceptance=False,
  origin_identity=origin_identity,m16_prerequisite=m16_prerequisite,
  origin_before_after_unchanged=True,original_m128_numerical_pass_inherited=False,native_result_sha256=native['result']['sha256'],
  native_status=native_result['status'],native_vs_independent_failed_stages=native_result['modes']['bf16']['phases'][0]['failed_stages'],
  producer_sha256=producer_generated_sha256,
  sequential_cpp_sha256=original.CPP_SHA256['sequential'],reduced_cpp_sha256=original.CPP_SHA256['reduced'])
 reference=dict(fresh_profile=PROFILE,roots=roots,directory=str(Path(roots['origin'])/Path(table['path']).parent),
  table_path=str(path(roots,table)),fresh_lookup=lookup,inputs=dict(original_input,position_ids=list(range(128))),
  threshold_policy=native_result['policy'],official_reference_identity=native_result['identity'],tensors=exported,
  prior_failures={},fresh_provenance=provenance,
  artifacts=[dict(v,path=k) for k,v in lookup.items()],native_execution_reused=False,
  oracle_execution_reused=False,old_pass_inherited=False)
 reduced_lookup={'raw_stages/'+n:record('origin',v) for n,v in red['outputs'].items()}
 reduced=dict(fresh_profile=PROFILE,roots=roots,directory=str(Path(roots['origin'])/'reduced'),rows=128,past_tokens=0,
  result_sha256=red['run']['sha256'],readonly_input=dict(path=str(path(roots,arena)),bytes=original.ARENA_BYTES,
  sha256=O.ARENA_SHA256,input_x_sha256=O.INPUT_X_SHA256),fresh_lookup=reduced_lookup,
  artifacts=[dict(v,path=k) for k,v in reduced_lookup.items()],actual_chain_executed=False,
  native_acceptance=False,fresh_provenance=provenance)
 return dict(input_spec=spec,reference=reference,independent_reference=reduced,provenance=provenance,
             library_receipt=str(library_receipt),library=str(library))

def read_reference_bytes(reference,relative):
 R.need(type(reference) is dict and reference.get('fresh_profile')==PROFILE and relative in reference['fresh_lookup'],'linked comparison lookup')
 item=reference['fresh_lookup'][relative];p=path(reference['roots'],item);raw=p.read_bytes()
 R.need(len(raw)==item['bytes'] and R.sha(raw)==item['sha256'],'late comparison byte drift')
 return raw

def read_native_reference(reference,raw,*,rows,method,name,shape):
 R.need(type(reference) is dict and reference.get('fresh_profile')==PROFILE and type(rows) is int and rows==128 and method in R.METHODS and name in O.shapes() and
        R.same(list(shape),O.shapes()[name]),'linked native comparison layout')
 item=reference['fresh_lookup']['references/%s/%s.f32le'%(method,name)]
 R.need(set(item)=={'root','path','bytes','sha256'} and item['root']=='origin' and
        type(item['bytes']) is int and item['bytes']==4*math.prod(shape) and
        len(raw)==item['bytes'] and R.sha(raw)==item['sha256'],'linked native bytes')
 from ..official_bf16.reference_layout import decode_qk
 if name in ('q','k'):return decode_qk(raw,shape,'token_major')
 import numpy as np
 return np.frombuffer(raw,dtype='<f4').reshape(shape)
