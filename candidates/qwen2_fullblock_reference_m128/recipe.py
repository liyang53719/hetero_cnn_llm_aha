#!/usr/bin/env python3
"""Qwen2 M128 full-block source candidate. Only stdlib metadata checks are enabled."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACKAGE = 'candidates/qwen2_fullblock_reference_m128'
PINS_SHA256 = '65a98bd5cbe299b5c3d06f925dc74c9724bf5e2a75d3c22146ddbd1d8fcfd08e'
MODEL_SOURCE = 'config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py'
ACTIVATION_SOURCE = PACKAGE + '/official/activations.py'
NAMES = frozenset(('x','n0','qr','q','kr','k','v','cos','sin','repeat_k','repeat_v',
    'mask','scores','logits','softmax_fp32','prob','pv','att','cache_k','cache_v',
    'o','r','n1','gate','up','silu','act','down','y'))
TOKEN_MAJOR = frozenset(('q','k','repeat_k','repeat_v','pv','cache_k','cache_v'))
TAIL_NAMES = ('self_attn.o_proj.weight','post_attention_layernorm.weight',
              'mlp.gate_proj.weight','mlp.up_proj.weight','mlp.down_proj.weight')
LAYOUT_RULE = ('q/k/repeat_k/repeat_v/pv/cache_k/cache_v: fixed B,H,T,D to B,T,H*D; '
              'scores/logits/prob/softmax_fp32 remain B,H,Q,K; PV to att is original310/311; '
              'cache_k/cache_v are cold semantic aliases, DynamicCache not executed; never selected by error')
DISABLED_REASON = ('SOURCE_ONLY: numerical capture, payload audit, actual, RTL, download, '
                   'compile and CI are not authorized or enabled; independent review and '
                   'a separately authorized, freshly sealed execution contract are required')


class Rejected(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise Rejected(message)


def same(a, b):
    if type(a) is not type(b):
        return False
    if type(b) is dict:
        return a.keys() == b.keys() and all(same(a[k],b[k]) for k in b)
    if type(b) is list:
        return len(a) == len(b) and all(same(x,y) for x,y in zip(a,b))
    return a == b


def fields(actual, expected, label):
    need(type(actual) is dict and all(k in actual and same(actual[k],v)
         for k,v in expected.items()), label + ' identity/type/geometry drift')


def exact_keys(actual, expected, label):
    need(type(actual) is dict and set(actual) == set(expected), label + ' inventory drift')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()


def parse(raw):
    def pairs(items):
        result = {}
        for key,value in items:
            need(key not in result, 'duplicate JSON key: '+key)
            result[key] = value
        return result
    def nonfinite(value):
        raise Rejected('nonfinite JSON: '+value)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite)


def safe_path(root, relative):
    need(type(relative) is str and relative and '\\' not in relative,
         'unsafe path spelling')
    p = Path(relative)
    need(not p.is_absolute() and all(s not in ('','.','..') for s in relative.split('/')),
         'canonical repository-relative path required')
    current = root.resolve()
    for part in p.parts:
        current /= part
        need(not current.is_symlink(), 'symlink path refused: '+relative)
    need(current.resolve().is_relative_to(root.resolve()), 'path escaped root')
    return current


def checked(root, relative, pin):
    path = safe_path(root,relative)
    need(path.is_file() and path.stat().st_size == pin['bytes'], 'file size drift: '+relative)
    raw = path.read_bytes()
    fields({'bytes':len(raw),'sha256':sha(raw)},
           {k:pin[k] for k in ('bytes','sha256')},relative)
    return raw


def stat_only(root, relative, expected_bytes):
    path = safe_path(root,relative)
    need(path.is_file() and path.stat().st_size == expected_bytes,
         'missing/wrong-sized payload; not read: '+relative)
    return {'bytes':path.stat().st_size,'payload_read':False,'payload_rehashed':False}


def load_pins(root=ROOT):
    raw = safe_path(root,PACKAGE+'/pins.json').read_bytes()
    need(sha(raw) == PINS_SHA256, 'candidate pin file drift')
    return parse(raw)


def require_supported_python():
    need(sys.implementation.name == 'cpython' and list(sys.version_info[:2]) == [3,12],
         'CPython 3.12 required; pinned AST hashes do not support cross-version normalization')


def deny_execution(*args, **kwargs):
    # Deliberately unconditional: CLI flags, mutable dicts, environment variables,
    # receipts or old approvals cannot unlock this source-only revision.
    raise Rejected(DISABLED_REASON)


def require_frozen_references(pins):
    need(pins['reference_freeze']['status'] == 'FROZEN_FROM_INDEPENDENT_REVIEW',
         '29-node reference is NOT_CAPTURED; a source plan is not a frozen oracle')
    for name,spec in pins['references'].items():
        for key in ('sha256','native_sha256','token_major_sha256'):
            need(type(spec[key]) is str and re.fullmatch('[0-9a-f]{64}',spec[key]) and
                 spec[key] != '0'*64, name+' requires captured reviewed '+key)
        need(type(spec['native_stride']) is list and len(spec['native_stride']) == len(spec['shape'])
             and all(type(n) is int and n > 0 for n in spec['native_stride']), 'captured strides required')
        need(type(spec['storage_offset']) is int and spec['storage_offset'] >= 0 and
             type(spec['is_contiguous']) is bool, 'captured storage metadata required')
    for key in ('bootstrap_manifest_sha256','independent_review_sha256'):
        value = pins['reference_freeze'][key]
        need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) and value != '0'*64,
             'reviewed freeze evidence required')


def check_contract(pins):
    fields(pins, {'schema':1,'recipe_id':'qwen2-fullblock-reference-m128-source-v1',
        'repository':'liyang53719/hetero_cnn_llm_aha',
        'base_commit':'995f07b7a53f642d2de5e67d31e8342f6e304cc9'}, 'candidate')
    fields(pins['contract'], {'rows':128,'token_ids':list(range(128)),
        'position_ids':list(range(128)),'past_tokens':0,'hidden_size':1536,
        'intermediate_size':8960,'q_heads':12,'kv_heads':2,'head_dim':128,'groups':6,
        'hidden_act':'silu','rms_norm_eps':1e-6,'rope_theta':1000000.0,
        'direct_gamma':True,'attention_dropout':0.0,'source_only':True,
        'capture_authorized':False,'actual_authorized':False,'intermediate_preloads':0,
        'full_official_forward_executed':False,'dynamic_cache_executed':False,
        'old_pass_inherited':False,'numerical_acceptance_claimed':False}, 'contract')
    fields(pins['reference_freeze'], {'status':'NOT_CAPTURED_SOURCE_ONLY',
        'bootstrap_manifest_sha256':None,'independent_review_sha256':None,
        'numeric_acceptance_claimed':False}, 'unfrozen reference')
    need(len(pins['model_ast_nodes']) == 38 and len(pins['activation_ast_nodes']) == 14,
         '38 model plus 14 activation nodes required')
    need([(s['line_start'],s['line_end']) for s in pins['model_ast_nodes'][27:]] ==
         [(168,180),(231,231),(730,730),(732,732),(763,763),(313,313),
          (776,776),(779,779),(780,780),(781,781),(782,782)], 'original model delta drift')
    exact_keys(pins['references'],NAMES,'29 references')
    large = ('x','n0','qr','att','o','r','n1','down','y')
    heads = ('q','repeat_k','repeat_v','pv','scores','logits','prob','softmax_fp32')
    shapes = {**{n:[1,128,1536] for n in large},**{n:[1,12,128,128] for n in heads},
        **{n:[1,128,256] for n in ('kr','v')},**{n:[1,2,128,128] for n in ('k','cache_k','cache_v')},
        **{n:[128,128] for n in ('cos','sin')},'mask':[1,1,128,128],
        **{n:[1,128,8960] for n in ('gate','up','silu','act')}}
    need(pins['layout_rule'] == LAYOUT_RULE, 'fixed named layout rule drift')
    fields(pins['mask_contract'], {'shape':[1,1,128,128],'native_dtype':'torch.bfloat16',
        'allowed_word_u16':0,'future_word_u16':0xff7f,'allowed_elements':8256,
        'future_elements':8128,'diagonal_elements':128,'native_bytes':32768,
        'export_bytes':65536,'dut_observed':False}, 'explicit cold mask contract')
    for name,spec in pins['references'].items():
        need(same(spec['shape'],shapes[name]), name+' exact native output shape')
        fp32 = name == 'softmax_fp32'
        fields(spec, {'bytes':math.prod(spec['shape'])*4,
            'native_bytes':math.prod(spec['shape'])*(4 if fp32 else 2),
            'native_dtype':'torch.float32' if fp32 else 'torch.bfloat16',
            'export_dtype':'FP32 unchanged' if fp32 else 'FP32 exact BF16 widening',
            'sha256':None,'native_sha256':None,'token_major_sha256':None,
            'native_stride':None,'storage_offset':None,'is_contiguous':None,
            'capture_status':'NOT_CAPTURED'}, name+' unfrozen geometry')
    need(sum(s['bytes'] for s in pins['references'].values()) == 32571392,
         '29-output byte budget drift')
    fields(pins['budget'], {'export_bytes_per_capture':32571392,
        'native_mask_sidecar_bytes':32768,'payload_bytes_per_capture':32604160,
        'bootstrap_plus_frozen_payload_bytes':65208320,
        'per_capture_cap_bytes':35651584,'total_cap_bytes':72351744,
        'native_dumps_retained':False,'peak_rss_estimate':None,
        'wall_seconds_estimate':None}, 'planned disk budget')
    need(pins['budget']['total_cap_bytes'] == 69*(1 << 20), '69 MiB total cap required')
    need(len(pins['raw_tensors']) == 13 and len({s['local_name'] for s in pins['raw_tensors']}) == 13,
         'thirteen unique raw tensors required')
    need(sum(s['bytes'] for s in pins['raw_tensors']) == 94382080, 'raw13 byte sum')
    exact_keys(pins['producer_roles'],('x','gamma0','wq','wk','wv','bq','bk','bv','rope','wo','gamma1','wg','wu','wd'),
               'fourteen producer metadata roles')
    need(sum(s['bytes'] for s in pins['producer_roles'].values()) == 94916608, 'role14 byte sum')
    fields(pins['runtime_requirements'], {'implementation':'cpython','python_major_minor':[3,12],
        'torch':'2.10.0+cpu','numpy':'2.3.5','capability':'AVX512','threads':4,
        'interop_threads':1,'deterministic_algorithms':True}, 'runtime')
    fields(pins['acceptance'], {'dut_executed':False,'full_29_node_acceptance':False,
        'softmax_fp32_verdict':'DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE',
        'softmax_fp32_passed':None,'mask_dut_observed':False,
        'partial_causal_positions_per_field':99072,'unobserved_future_positions_per_field':97536,
        'policy_changed':False}, 'scope/acceptance')


def official_nodes(root, specs, path, sources):
    source = checked(root,path,sources[path]).decode()
    tree = ast.parse(source,filename=path)
    by_span = {(n.lineno,n.end_lineno,type(n).__name__):n for n in ast.walk(tree) if hasattr(n,'lineno')}
    result = []
    for spec in specs:
        need(spec['path'] == path, 'official node source path drift')
        node = by_span.get((spec['line_start'],spec['line_end'],spec['node_type']))
        need(node is not None, 'missing official AST node')
        need(sha(ast.get_source_segment(source,node).encode()) == spec['source_sha256'] and
             sha(ast.dump(node,include_attributes=False).encode()) == spec['ast_sha256'],
             'whole official source/AST identity drift: '+spec.get('label',str(spec['line_start'])))
        result.append(node)
    return result


def metadata_check(root,pins):
    """Only pinned JSON/header/source bytes and payload stat; no producer/raw read."""
    manifests = {key:parse(checked(root,spec['path'],spec))
                 for key,spec in pins['input_metadata'].items()}
    prefix,tail = manifests['prefix_raw'],manifests['tail_raw']
    fields(prefix, {'status':'RECOVERED_PINNED_QWEN2_PREFIX_SUBSET_ONLY','payload_bytes':7085056},'prefix raw manifest')
    fields(tail, {'status':'VERIFIED_PINNED_QWEN2_FIVE_TAIL_RAW_TENSORS_ONLY',
        'payload_bytes':87297024,'model_id':pins['model_id'],'revision':pins['revision']},'tail raw manifest')
    fields(prefix['contract'], {'model_id':pins['model_id'],'revision':pins['revision'],'rows':128},'prefix checkpoint')
    need(len(prefix['tensors']) == 8 and len(tail['tensors']) == 5, 'explicit 8+5 manifest schemas')
    joined = prefix['tensors']+tail['tensors']
    need(len({s['local_name'] for s in joined}) == 13, 'overlapping raw manifests')
    by_name = {s['local_name']:s for s in joined}
    origin = {s['local_name']:key for key,value in [('prefix_raw',prefix),('tail_raw',tail)] for s in value['tensors']}
    header_raw = checked(root,pins['shard']['header']['path'],pins['shard']['header'])
    need(len(header_raw) == 38536 and struct.unpack('<Q',header_raw[:8])[0]+8 == len(header_raw), 'header framing')
    header = parse(header_raw[8:])
    for spec in pins['raw_tensors']:
        current = by_name.get(spec['local_name'])
        key = origin.get(spec['local_name'])
        need(key is not None and spec['manifest_role'] == key, 'raw manifest origin drift')
        need(spec['path'] == str(Path(pins['input_metadata'][key]['path']).parent/current['file']),
             'raw path differs from its original manifest')
        fields(current,{k:spec[k] for k in ('name','local_name','shape','dtype','bytes','sha256',
               'start','end','source_shape','source_data_offsets')},'raw identity '+spec['local_name'])
        fields(header[spec['name']],{'dtype':'BF16','shape':spec['source_shape'],
               'data_offsets':spec['source_data_offsets']},'original checkpoint header')
        need(spec['bytes'] == math.prod(spec['shape'])*2 and spec['end']+1-spec['start'] == spec['bytes'],
             'raw tensor geometry/range')
        need(spec['start'] == len(header_raw)+spec['source_data_offsets'][0], 'absolute raw range')
        stat_only(root,spec['path'],spec['bytes'])
    pre_ready,tail_ready = manifests['prefix_ready'],manifests['tail_ready']
    fields(pre_ready, {'status':'PINNED_PREFIX_INPUTS_READY_NO_MODEL_EXECUTION',
        'subset_manifest_sha256':pins['input_metadata']['prefix_raw']['sha256']},'prefix readiness')
    fields(tail_ready, {'status':'FIVE_PINNED_TAIL_INPUT_ROLES_READY_NO_MODEL_EXECUTION',
        'model_id':pins['model_id'],'revision':pins['revision'],
        'raw_manifest':pins['input_metadata']['tail_raw']},'tail readiness')
    need(len(pre_ready['roles']) == 9 and len(tail_ready['roles']) == 5, '9+5 role metadata closure')
    for ready_key,ready in [('prefix_ready',pre_ready),('tail_ready',tail_ready)]:
        directory = str(Path(pins['input_metadata'][ready_key]['path']).parent)
        for name,record in ready['roles'].items():
            spec = pins['producer_roles'][name]
            need(same(record,spec['record']), 'producer role metadata drift: '+name)
            fields(spec,{k:record[k] for k in ('bytes','sha256')},'producer identity '+name)
            need(spec['path'] == directory+'/'+record['file'], 'role path binding')
            stat_only(root,spec['path'],spec['bytes'])
    need(same(tail_ready['before'],tail_ready['after']), 'tail producer source/input boundary drift')
    return {'raw_tensors':13,'producer_roles':14,'raw_payload_read':False,
            'producer_payload_read':False,'payload_rehash':False,'payload_stat_only':True}


def source_check(root,pins):
    require_supported_python()
    need(root == ROOT and root.resolve() == ROOT and (root/'.git').exists(), 'exact checkout root required')
    check_contract(pins)
    for path,spec in pins['sources'].items():
        checked(root,path,spec)
    model = official_nodes(root,pins['model_ast_nodes'],MODEL_SOURCE,pins['sources'])
    activation = official_nodes(root,pins['activation_ast_nodes'],ACTIVATION_SOURCE,pins['sources'])
    for node in pins['torch_boundary_nodes']:
        official_nodes(root,[node],node['path'],pins['sources'])
    ap = parse(checked(root,'candidates/qwen2_live_attention_reference_m128/pins.json',
                       pins['sources']['candidates/qwen2_live_attention_reference_m128/pins.json']))
    # The first 27 records inherit exactly their original AST identities. Labels and
    # source excerpts in the mapping are explanatory and not executable rewrites.
    for actual,expected in zip(pins['model_ast_nodes'][:27],ap['official_ast_nodes']):
        fields(actual,{k:expected[k] for k in ('line_start','line_end','node_type','source_sha256','ast_sha256')},
               'unchanged original27')
    need(same(pins['prior18_expectations'],ap['references']), 'prior18 reproduction expectations drift')
    config = parse(checked(root,pins['config_source'],pins['sources'][pins['config_source']]))
    fields(config,{'hidden_size':1536,'intermediate_size':8960,'hidden_act':'silu',
        'num_attention_heads':12,'num_key_value_heads':2,'rms_norm_eps':1e-6,
        'rope_theta':1000000.0,'max_position_embeddings':32768},'official config')
    source = checked(root,ACTIVATION_SOURCE,pins['sources'][ACTIVATION_SOURCE])
    need(sha(source) == '10c37e915ce2b52d539a5b52ecaaf644e2b0c56d282db00778098d74342ebeee',
         'official activation file hash')
    need(hashlib.sha1(b'blob '+str(len(source)).encode()+b'\0'+source).hexdigest() ==
         '2355fb5fed678d0de6e2c53f52644a35a691a34e', 'official activation Git blob identity')
    mapping = activation[-2]
    need(isinstance(mapping,ast.Assign) and isinstance(mapping.value,ast.Dict), 'whole original ACT2CLS assignment')
    selected = [v for k,v in zip(mapping.value.keys,mapping.value.values)
                if isinstance(k,ast.Constant) and k.value == 'silu']
    need(len(selected) == 1 and ast.dump(selected[0],include_attributes=False) ==
         "Attribute(value=Name(id='nn', ctx=Load()), attr='SiLU', ctx=Load())", 'original silu mapping')
    for label,closure in pins['preserved_execution_closures'].items():
        need(closure['count'] == {'m128':169,'m16':188}[label] == len(closure['sha256']), 'preservation closure size')
        for path,digest in closure['sha256'].items():
            need(sha(safe_path(root,path).read_bytes()) == digest, 'preserved '+label+' source drift: '+path)
    for spec in pins['runtime_native_files'].values():
        path = Path(spec['path']) if Path(spec['path']).is_absolute() else safe_path(root,spec['path'])
        need(path.is_file() and path.stat().st_size == spec['bytes'], 'native runtime stat drift')
    return {**metadata_check(root,pins),'model_ast_nodes':len(model),'activation_ast_nodes':len(activation),
            'reference_nodes':29,'pinned_sources':len(pins['sources']),
            'preserved_m128_sources':169,'preserved_m16_sources':188,'native_runtime_rehashed':False}


def plan(pins):
    return {'status':'NOT_EXECUTED_SOURCE_ONLY','reference_freeze':pins['reference_freeze'],
        'planned_model_ast_nodes':38,'planned_activation_ast_nodes':14,
        'planned_reference_nodes':29,'budget':pins['budget'],
        'capture_enabled':False,'actual_enabled':False,'next_gate':'INDEPENDENT_SOURCE_REVIEW',
        'later_steps':['explicit capture authorization and fresh execution seal',
            'one bootstrap from raw, no verdict','independent bootstrap review',
            'separate immutable freeze with observed29 hashes',
            'one distinct frozen reproduction from raw, exact29 hash match'],
        'full_official_forward_executed':False,'dynamic_cache_executed':False,
        'numerical_acceptance_claimed':False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default=str(ROOT))
    parser.add_argument('--action',default='check')
    parser.add_argument('--execute',action='store_true')
    for name in ('out','subset','inputs','reference','authorization'):
        parser.add_argument('--'+name)
    args = parser.parse_args(argv)
    try:
        # Reject mutation/execution intent before source reads, import, or mkdir.
        if args.action not in ('check','plan') or args.execute or any(
            getattr(args,n) is not None for n in ('out','subset','inputs','reference','authorization')):
            deny_execution()
        root = Path(args.root).absolute()
        need(root == ROOT and root.resolve() == ROOT, 'exact checkout root required')
        pins = load_pins(root)
        coverage = source_check(root,pins)
        result = plan(pins)
        result.update(cold_check='PASS',coverage=coverage,torch_imported='torch' in sys.modules,
                      numpy_imported='numpy' in sys.modules,transformers_imported='transformers' in sys.modules,
                      output_files_written=False,raw_payload_read=False,producer_payload_read=False,
                      numeric_executed=False,rtl_executed=False,network_used=False)
        print(json.dumps(result,sort_keys=True,allow_nan=False))
        return 0
    except (Rejected,OSError,ValueError,TypeError,KeyError) as error:
        print(json.dumps({'status':'REJECTED','reason':str(error)},sort_keys=True),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
