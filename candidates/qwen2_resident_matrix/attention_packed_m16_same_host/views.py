"""Single-root fresh-reference views. Construct only after strict admission.

Numerical arrays are decoded only by the unchanged post-terminal comparator.
"""
from ..raw_kv_public_fresh.assets import (resolve_artifact, records, need, sha, shapes,
    MODEL, REVISION, INPUT_X_SHA256, ARENA_BYTES, ARENA_SHA256, TENSOR_PINS,
    CPP_SHA256, METHODS)
from .contract import PROFILE

def build_views(workspace, path, expected_sha256, manifest, exported, native_result, directories, *, enable_raw_kv):
    def absolute(item):
        return str(resolve_artifact(workspace,item))
    role_names = {'embeddings':'embed_tokens.rows_0_255','gamma0':'input_layernorm.weight',
        'gamma1':'post_attention_layernorm.weight', 'wq':'self_attn.q_proj.weight','bq':'self_attn.q_proj.bias',
        'wk':'self_attn.k_proj.weight','bk':'self_attn.k_proj.bias','wv':'self_attn.v_proj.weight',
        'bv':'self_attn.v_proj.bias','wo':'self_attn.o_proj.weight','wg':'mlp.gate_proj.weight',
        'wu':'mlp.up_proj.weight','wd':'mlp.down_proj.weight'}
    comparison_records = list(manifest['sequential']['outputs'].values()) + list(manifest['sequential']['tensors'].values())
    comparison_records += list(manifest['reduced']['outputs'].values()) + list(records(manifest['native']['outputs']))
    original_input = dict(token_ids=list(range(16)),positions=list(range(16)),input_x_sha256=INPUT_X_SHA256,
        intermediate_preloads=0,rope_theta=1000000.0,
        rope_table_recipe='FP32 exponent/powf/reciprocal/phase multiply/sinf/cosf then BF16; positions0..255 only',
        readonly_bytes=ARENA_BYTES,readonly_sha256=ARENA_SHA256)
    spec = dict(model=MODEL,revision=REVISION,layer=0,original_input=original_input,
        fresh_profile=PROFILE,metadata_sha256={str(path):expected_sha256},payloads={
            role:dict(path=absolute(manifest['payload']['tensors'][name]),bytes=TENSOR_PINS[name]['bytes'],
                      sha256=TENSOR_PINS[name]['sha256'],shape=TENSOR_PINS[name]['shape']) for role,name in role_names.items()},
        comparison_only={str(i):dict(item,path=absolute(item)) for i,item in enumerate(comparison_records)},
        oracle_arena=dict(manifest['readonly']['arena'],path=absolute(manifest['readonly']['arena'])))
    lookup = {'raw_stages/'+name:item for name,item in manifest['sequential']['outputs'].items()}
    lookup.update({'tensors/candidate_'+name+'.f32le':item for name,item in manifest['sequential']['tensors'].items()})
    for method in METHODS:
        lookup.update({'references/%s/%s.f32le'%(method,name):item
                       for name,item in manifest['native']['outputs']['bf16'][method].items()})
    identity = dict(profile=PROFILE,manifest=str(path),manifest_sha256=expected_sha256,enable_raw_kv=enable_raw_kv)
    provenance = dict(profile=PROFILE,fresh_assets=identity,new_official_forward_executed=True,
        historical_receipts_reused=False,actual_chain_executed=False,
        native_result_sha256=manifest['native']['result']['sha256'],native_status=native_result['status'],
        native_vs_independent_failed_stages=native_result['modes']['bf16']['phases'][0]['failed_stages'],
        producer_sha256=manifest['producer_generated_sha256'],
        producer_manifest_sha256=manifest['producer_manifest_sha256'],
        producer_receipt_sha256=manifest['producer_receipt_sha256'],
        attempt_nonce=manifest['attempt_nonce'],
        native_execution_reused=False,oracle_execution_reused=False,old_pass_inherited=False,
        sequential_cpp_sha256=CPP_SHA256['sequential'],reduced_cpp_sha256=CPP_SHA256['reduced'])
    reference = dict(fresh_profile=PROFILE,workspace=str(workspace),directory=str(resolve_artifact(workspace,manifest['readonly']['table']).parent),
        table_path=absolute(manifest['readonly']['table']),fresh_lookup=lookup,inputs=dict(original_input,position_ids=list(range(16))),
        threshold_policy=native_result['policy'],official_reference_identity=native_result['identity'],
        tensors=exported,prior_failures={},
        fresh_provenance=provenance,artifacts=[dict(item,path=name) for name,item in lookup.items()],
        native_execution_reused=False,oracle_execution_reused=False,old_pass_inherited=False)
    reduced = dict(fresh_profile=PROFILE,workspace=str(workspace),directory=str(directories['reduced'].parent),rows=16,past_tokens=0,
        result_sha256=manifest['reduced']['run']['sha256'],readonly_input=dict(path=absolute(manifest['readonly']['arena']),
        bytes=ARENA_BYTES,sha256=ARENA_SHA256,input_x_sha256=INPUT_X_SHA256),
        fresh_lookup={'raw_stages/'+name:item for name,item in manifest['reduced']['outputs'].items()},
        artifacts=[dict(item,path='raw_stages/'+name) for name,item in manifest['reduced']['outputs'].items()],
        actual_chain_executed=False,native_acceptance=False,fresh_provenance=provenance)
    return dict(input_spec=spec,reference=reference,independent_reference=reduced,provenance=provenance,
                library_receipt=manifest['library']['receipt']['path'],library=manifest['library']['binary']['path'])


def read_reference_bytes(reference, relative):
    """Comparison-only: call solely after the original whole-terminal gate opens."""
    need(reference.get('fresh_profile') == PROFILE and relative in reference['fresh_lookup'],
         'fresh reference lookup outside sealed inventory')
    item = reference['fresh_lookup'][relative]
    path = resolve_artifact(reference['workspace'],item)
    raw = path.read_bytes()
    need(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'fresh comparison payload drift')
    return raw


def read_native_reference(reference, raw, *, rows, method, name, shape):
    """Late original decoder; fresh producer metadata fixes token-major Q/K."""
    need(type(rows) is int and rows == 16 and method in METHODS and name in shapes() and
         tuple(shape) == tuple(shapes()[name]), 'fresh reference logical layout differs')
    item = reference['fresh_lookup']['references/%s/%s.f32le'%(method,name)]
    need(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'fresh native comparison bytes differ')
    from candidates.qwen2_resident_matrix.official_bf16.reference_layout import decode_qk
    if name in ('q','k'):
        return decode_qk(raw,shape,'token_major')
    import numpy as np
    return np.frombuffer(raw,dtype='<f4').reshape(shape)
