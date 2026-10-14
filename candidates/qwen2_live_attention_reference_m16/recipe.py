#!/usr/bin/env python3
"""Independent M16 official Attention AST oracle. Default: stdlib NOT_EXECUTED."""
from __future__ import annotations
import argparse
import ast
import types
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACKAGE = 'candidates/qwen2_live_attention_reference_m16'
PREFIX_PACKAGE = 'candidates/qwen2_live_qkv_inputs'
PINS_SHA256 = 'fabdd6e8aa252f55516ef9c83ecbed39a0ea26f6e0e1f2e6eff1e6bd2d109192'
OUTPUT_PREFIX = 'work/qwen2_live_attention_reference_m16_20261014'
ROWS = 16
MODEL_SOURCE = 'config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py'
STAGES = {'bootstrap-capture':'BOOTSTRAP_REFERENCE.json', 'capture':'REFERENCE.json', 'audit':'AUDIT.json'}
# The reviewed prefix module contains only stdlib definitions. Never import its
# optional capture module or replace its recipe globals. Its source is hash-bound.
_prefix_path = ROOT / PREFIX_PACKAGE / 'recipe.py'
if _prefix_path.is_symlink() or _prefix_path.resolve() != _prefix_path or hashlib.sha256(_prefix_path.read_bytes()).hexdigest() != '89aba5a7ac13b0fd91129d0be5d6eb89373b099a4886991e1cd3492267450523':
    raise ValueError('reviewed prefix module identity changed before import')
P = types.ModuleType('_qwen2_m16_prefix_recipe')
P.__file__ = str(_prefix_path)
exec(compile(_prefix_path.read_bytes(), str(_prefix_path), 'exec'), P.__dict__)
Rejected, need, same, fields, exact_keys = P.Rejected, P.need, P.same, P.fields, P.exact_keys
sha, stamp, json_bytes, parse_json = P.sha, P.stamp, P.json_bytes, P.parse_json
safe_path, checked, digest, timestamp = P.safe_path, P.checked, P.digest, P.timestamp
write_new, start_output, head_to_token = P.write_new, P.start_output, P.head_to_token
TOKEN_MAJOR = frozenset(('q','k','repeat_k','repeat_v','pv'))
NAMES = frozenset(('x','n0','qr','q','kr','k','v','cos','sin','repeat_k','repeat_v','mask','scores','logits','softmax_fp32','prob','pv','att'))


def load_pins(root=ROOT):
    raw = safe_path(root, PACKAGE + '/pins.json').read_bytes()
    need(sha(raw) == PINS_SHA256, 'Attention recipe pin file drift')
    return parse_json(raw)


def prefix_pins(root, pins):
    value = P.load_pins(root)
    need(P.PINS_SHA256 == pins['prefix_pins_sha256'], 'reviewed prefix pin identity drift')
    return value



def normalized_prefix_references(pins):
    """Normalize old metadata labels only; never open saved reference payloads."""
    return {n:{("token_major_sha256" if k=="historical_archive_sha256" else k):v
               for k,v in spec.items()} for n,spec in pins["references"].items()}

RUNTIME_IDENTITY_SCOPE = P.RUNTIME_IDENTITY_SCOPE
python_identity = P.python_identity

def check_runtime(runtime, pins):
    required = set(pins['runtime_requirements']) | {'python', 'torch_build', 'affinity', 'environment',
                'new_process', 'historical_runtime_equivalence_claimed', 'native_files', 'identity_scope'}
    exact_keys(runtime, required, 'runtime')
    fields(runtime, pins['runtime_requirements'], 'reference runtime')
    fields(runtime, {'python': sys.version, 'new_process': True,
                    'historical_runtime_equivalence_claimed': False,
                    'identity_scope': RUNTIME_IDENTITY_SCOPE}, 'runtime claims/Python/identity scope')
    environment = pins['capture_environment']
    exact_keys(environment, {'ATEN_CPU_CAPABILITY','OMP_NUM_THREADS','MKL_NUM_THREADS',
                            'OPENBLAS_NUM_THREADS','PYTHONPATH','PYTHONNOUSERSITE'}, 'capture environment pin')
    fields(environment, {'ATEN_CPU_CAPABILITY':None, 'OMP_NUM_THREADS':'4', 'MKL_NUM_THREADS':'4',
                         'OPENBLAS_NUM_THREADS':'1', 'PYTHONNOUSERSITE':'1'}, 'capture environment policy')
    need(type(environment['PYTHONPATH']) is str and Path(environment['PYTHONPATH']).is_absolute(),
         'absolute pinned capture import environment required')
    need(same(runtime['environment'], environment), 'runtime environment coverage/dispatch/thread/import drift')
    affinity = sorted(os.sched_getaffinity(0))
    need(bool(affinity) and same(runtime['affinity'], affinity), 'runtime affinity identity/type/order drift')
    build = runtime['torch_build']
    need(type(build) is str and bool(build) and len(build) < 1024 * 1024, 'Torch build text required')
    need(sha(build.encode()) == pins['runtime_requirements']['torch_build_sha256'], 'Torch build text pin drift')
    for token in ('TORCH_VERSION=2.10.0', 'COMMIT_SHA=' + pins['runtime_requirements']['torch_commit'],
                  'USE_CUDA=0', 'CPU capability usage: AVX512'):
        need(token in build, 'Torch build configuration flag missing')
    libraries = runtime['native_files']
    exact_keys(libraries, {'python', 'torch_C', 'numpy_multiarray', 'libtorch_cpu.so',
                          'libc10.so', 'libtorch_python.so'}, 'key runtime libraries')
    for name, item in libraries.items():
        exact_keys(item, {'path', 'bytes', 'sha256'}, 'runtime library ' + name)
        need(type(item['bytes']) is int and item['bytes'] > 0 and type(item['path']) is str and
             Path(item['path']).is_absolute() and '..' not in Path(item['path']).parts and
             '\x00' not in item['path'] and '\n' not in item['path'], 'invalid current-runtime file receipt')
        digest(item['sha256'], 'runtime library ' + name)
        if name in ('libtorch_cpu.so', 'libc10.so', 'libtorch_python.so'):
            need(Path(item['path']).name == name, 'runtime library basename drift')
    need(same(libraries['python'], python_identity()), 'runtime interpreter file identity drift')
    need(same(libraries, runtime_files(ROOT, pins)), 'runtime native byte/hash identity drift')

def runtime_files(root, pins):
    result = {}
    for name, spec in pins['runtime_native_files'].items():
        path = Path(spec['path'])
        path = path if path.is_absolute() else safe_path(root, spec['path'])
        need(path.is_file(), 'missing runtime file ' + name)
        raw = path.read_bytes()
        fields({'bytes':len(raw), 'sha256':sha(raw)}, {k:spec[k] for k in ('bytes','sha256')}, 'runtime file ' + name)
        result[name] = {'path':str(path.resolve()), 'bytes':len(raw), 'sha256':sha(raw)}
    exact_keys(result, {'python','torch_C','numpy_multiarray','libtorch_cpu.so','libc10.so','libtorch_python.so'}, 'six native files')
    return result


def mask_bytes():
    """Explicit wrapper parameter; exact cold BF16 words, no helper provenance claim."""
    return b''.join(struct.pack('<H', 0xff7f if k > q else 0)
                    for q in range(ROWS) for k in range(ROWS))


def verify_mask(raw, pins, *, exported=False):
    need(type(raw) is bytes, 'mask payload bytes required')
    expected = mask_bytes()
    if exported:
        expected = P.widen_bf16(expected)
    need(raw == expected, 'mask shape/diagonal/allowed/future exact-word mismatch')
    contract = pins['mask_contract']
    fields({'bytes':len(raw),'sha256':sha(raw)},
           {'bytes':contract['export_bytes' if exported else 'native_bytes'],
            'sha256':contract['export_sha256' if exported else 'native_sha256']}, 'mask identity')
    return {'shape':[1,1,ROWS,ROWS], 'allowed_elements':136, 'future_elements':120,
            'diagonal_elements':ROWS, 'allowed_word_u16':0, 'future_word_u16':0xff7f,
            'all_words_checked':True, 'dut_observed':False}


def check_contract(pins):
    fields(pins['contract'], {'recipe_id':'qwen2-live-attention-reference-m16-v1',
           'rows':ROWS,'token_ids':list(range(ROWS)),'position_ids':list(range(ROWS)),
           'past_tokens':0,'direct_gamma':True,'groups':6,'q_heads':12,'kv_heads':2,
           'head_dim':128,'attention_dropout':0.0,'old_pass_inherited':False,
           'intermediate_preloads':0,'full_official_forward_executed':False,
           'actual_driver_executed':False,'mlp_executed':False,'rtl_executed':False}, 'Attention contract')
    exact_keys(pins['references'], NAMES, '18 reference nodes')
    need(len(pins['official_ast_nodes']) == 27, '27 official nodes required')
    pp = prefix_pins(ROOT, pins)
    need(same(pins['official_ast_nodes'][:15],pp['official_ast_nodes']), 'prefix AST identity drift')
    need(same(pins['prefix_references'],normalized_prefix_references(pp)), 'prefix reference identity drift')
    for key in ('tensors','roles','runtime_requirements'):
        need(same(pins[key],pp[key]), 'prefix dependency drift: ' + key)
    spans = [(n['line_start'],n['line_end']) for n in pins['official_ast_nodes'][15:]]
    need(spans == [(184,193),(280,280),(281,281),(283,283),(285,289),(291,297),
                   (300,300),(301,301),(302,302),(304,308),(310,310),(311,311)], 'Attention source span drift')
    for name,spec in pins['references'].items():
        shape = (pp['references'][name]['shape'] if name in pp['references'] else
                 [1,ROWS,1536] if name == 'att' else [1,1,ROWS,ROWS] if name == 'mask' else
                 [1,12,ROWS,128] if name in ('repeat_k','repeat_v','pv') else [1,12,ROWS,ROWS])
        is_fp32 = name == 'softmax_fp32'
        exact_keys(spec, {'shape','bytes','native_dtype','export_dtype','sha256','token_major_sha256',
                         'native_bytes','native_sha256','native_stride','storage_offset','is_contiguous'}, name)
        fields(spec, {'shape':shape,'bytes':math.prod(shape)*4,
                      'native_bytes':math.prod(shape)*(4 if is_fp32 else 2),
                      'native_dtype':'torch.float32' if is_fp32 else 'torch.bfloat16',
                      'export_dtype':'FP32 unchanged' if is_fp32 else 'FP32 exact BF16 widening',
                      'storage_offset':0}, name + ' geometry/dtype')
    fields(pins['mask_contract'], {'shape':[1,1,ROWS,ROWS],'native_dtype':'torch.bfloat16','past':0,
           'allowed_word_u16':0,'future_word_u16':0xff7f,'allowed_elements':136,
           'future_elements':120,'diagonal_elements':ROWS,'native_bytes':512,
           'export_bytes':1024,'dut_observed':False}, 'cold causal mask')
    verify_mask(mask_bytes(), pins)
    verify_mask(P.widen_bf16(mask_bytes()), pins, exported=True)
    fields(pins['softmax_observation'], {'source':'torch.nn.functional.softmax.__code__ return event',
           'calls':1,'native_dtype':'torch.float32','expression_rewritten':False}, 'softmax observer')
    need(pins['reference_freeze']['status'] in ('BOOTSTRAP_UNACCEPTED', 'FROZEN_FROM_REVIEWED_ATTENTION_BOOTSTRAP'), 'freeze status')
    need(pins['reference_freeze']['numeric_acceptance_claimed'] is False, 'reference is not DUT acceptance')


def official_nodes(root, pins):
    source = safe_path(root, MODEL_SOURCE).read_text()
    tree = ast.parse(source)
    by_span = {(n.lineno,n.end_lineno,type(n).__name__):n for n in ast.walk(tree) if hasattr(n,'lineno')}
    result = []
    for spec in pins['official_ast_nodes']:
        node = by_span.get((spec['line_start'],spec['line_end'],spec['node_type']))
        need(node is not None, 'missing official AST node')
        need(sha(ast.get_source_segment(source,node).encode()) == spec['source_sha256'] and
             sha(ast.dump(node,include_attributes=False).encode()) == spec['ast_sha256'], 'official AST identity drift')
        result.append(node)
    need(len(result)==27, 'official AST coverage')
    return result


def source_check(root, pins):
    need((root/'.git').exists(), 'checkout root required')
    check_contract(pins)
    P.source_check(root, prefix_pins(root,pins))
    for path,pin in pins['sources'].items():
        checked(root,path,pin)
    official_nodes(root,pins)
    return {'pinned_source_files':len(pins['sources']),'official_ast_nodes':27,
            'raw_tensors':8,'input_roles':9,'reference_nodes':18,'payload_bytes':7085056}


def require_frozen_references(pins):
    check_contract(pins)
    freeze = pins['reference_freeze']
    need(freeze['status']=='FROZEN_FROM_REVIEWED_ATTENTION_BOOTSTRAP','Attention bootstrap is unaccepted')
    for key in ('bootstrap_manifest_sha256','independent_review_sha256'):
        digest(freeze[key],key)
    for name,spec in pins['references'].items():
        for key in ('sha256','token_major_sha256','native_sha256'):
            digest(spec[key],name+' '+key)
            need(spec[key] != '0'*64,'placeholder reference refused')
        need(type(spec['native_stride']) is list and len(spec['native_stride']) == len(spec['shape']) and
             all(type(n) is int and n > 0 for n in spec['native_stride']), 'native strides required')
        need(type(spec['is_contiguous']) is bool,'native contiguity type')
        if name not in TOKEN_MAJOR:
            need(spec['sha256']==spec['token_major_sha256'],'unchanged-layout hash drift')
        if name in pins['prefix_references']:
            fields(spec,pins['prefix_references'][name],'prefix9 frozen exact reproduction')
    fields(pins['references']['mask'], {'sha256':pins['mask_contract']['export_sha256'],
           'native_sha256':pins['mask_contract']['native_sha256']}, 'mask frozen hashes')
    need(pins['references']['pv']['token_major_sha256'] == pins['references']['att']['sha256'], 'fixed PV to att layout mismatch')


def recipe_identity(root):
    return {n:sha(safe_path(root,PACKAGE+'/'+n).read_bytes()) for n in ('recipe.py','capture.py','pins.json')}


def stage_path(root,value):
    need(type(value) is str and re.fullmatch(re.escape(OUTPUT_PREFIX)+
         r'/[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}/[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',value),
         'expected work/qwen2_live_attention_reference_m16_20261014/<run-id>/<stage-id>')
    return safe_path(root,value)


def fresh_output(root,value,inputs=()):
    out=stage_path(root,value)
    need(not out.exists(),'output already exists; select a fresh identity')
    for source in inputs:
        need(not out.is_relative_to(source) and not source.is_relative_to(out),'output overlaps input')
    return out


def read_inputs(root,pins,subset,inputs):
    pp=prefix_pins(root,pins)
    _,values,subset_sha,sd=P.read_subset(root,pp,subset)
    _,inputs_sha,ip=P.read_inputs(root,pp,inputs,subset,subset_sha)
    need(sd != ip,'input aliases refused')
    return values,subset_sha,inputs_sha


def boundary_snapshot(root,pins,directories,native=False):
    source_check(root,pins)
    need(same(load_pins(root),pins),'in-memory pins drift')
    paths=[safe_path(root,p) for p in pins['sources']]
    paths += [safe_path(root,PACKAGE+'/'+n) for n in ('recipe.py','capture.py','pins.json')]
    paths += [Path(sys.executable).resolve(),Path('/usr/bin/gcc').resolve()]
    for directory in directories:
        need(directory.is_dir() and not directory.is_symlink(),'missing/aliased input directory')
        for path in sorted(directory.rglob('*')):
            need(not path.is_symlink(),'input symlink refused')
            if path.is_file(): paths.append(path)
    result={str(p):{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in paths}
    if native: result['native_files']=runtime_files(root,pins)
    return result


def finish_boundary(root,pins,directories,before,out,native=False):
    after=boundary_snapshot(root,pins,directories,native=native)
    write_new(out/'BOUNDARY_AFTER.json',json_bytes(after))
    need(same(before,after),'source/input/tool identity changed; no completion manifest')
    return {'before_file':'BOUNDARY_BEFORE.json','after_file':'BOUNDARY_AFTER.json',
            'before_sha256':sha(json_bytes(before)),'after_sha256':sha(json_bytes(after)),
            'unchanged':True,'native_files_checked':native}


def report(root,pins,stage):
    return {'contract':pins['contract'],'stage':stage,'recorded_utc':stamp(),
            'recipe':recipe_identity(root),'source_pins_sha256':PINS_SHA256}


def token_bytes(name,raw,shape):
    return head_to_token(raw,shape) if name in TOKEN_MAJOR else raw


def expected_comparison(pins):
    return {name:{'logical_sha256':s['sha256'],'token_major_sha256':s['token_major_sha256'],
                  'native_sha256':s['native_sha256'],'frozen_reference_hash_matches':True}
            for name,s in pins['references'].items()}


def prefix_comparison(pins):
    return {name:{'logical_sha256':s['sha256'],'token_major_sha256':s['token_major_sha256'],
                  'fresh_recomputed_matches_frozen_prefix':True}
            for name,s in pins['prefix_references'].items()}


def verify_reference_metadata(root,pins,subset,inputs,reference,subset_sha,inputs_sha):
    """Metadata-only API: no oracle payload read, Torch import, or caller env requirement."""
    require_frozen_references(pins)
    value=parse_json(safe_path(stage_path(root,reference),'REFERENCE.json').read_bytes())
    exact_keys(value, {'contract','stage','recorded_utc','recipe','source_pins_sha256','status','subset','inputs',
        'subset_manifest_sha256','input_ready_sha256','official_ast_nodes','outputs','runtime',
        'official_ast_subset_executed','full_official_forward_executed','transformers_imported',
        'posthoc_oracle_only','numerical_acceptance_claimed','old_pass_inherited','actual_or_typed_input_read',
        'prefix_saved_reference_read','cold_cache_semantics','mask_contract','mask_verification',
        'softmax_observation','rotary_cache_max_position_embeddings','original_config_max_position_embeddings',
        'configuration_equivalence_claimed','layout_rule','reference_freeze','reference_hash_comparison',
        'prefix9_reproduction','boundary'}, 'reference manifest')
    fields(value, {'contract':pins['contract'],'stage':'capture','recipe':recipe_identity(root),
        'source_pins_sha256':PINS_SHA256,'status':'FRESH_OFFICIAL_AST_ATTENTION_CAPTURE_ONLY',
        'subset':subset,'inputs':inputs,'subset_manifest_sha256':subset_sha,'input_ready_sha256':inputs_sha,
        'official_ast_nodes':pins['official_ast_nodes'],'official_ast_subset_executed':True,
        'full_official_forward_executed':False,'transformers_imported':False,'posthoc_oracle_only':True,
        'numerical_acceptance_claimed':False,'old_pass_inherited':False,'actual_or_typed_input_read':False,
        'prefix_saved_reference_read':False,'cold_cache_semantics':'past=0; current K/V only; no Cache implementation executed',
        'mask_contract':pins['mask_contract'],'mask_verification':verify_mask(mask_bytes(),pins),
        'softmax_observation':pins['softmax_observation'],'rotary_cache_max_position_embeddings':256,
        'original_config_max_position_embeddings':32768,'configuration_equivalence_claimed':False,
        'layout_rule':pins['layout_rule'],'reference_freeze':pins['reference_freeze'],
        'reference_hash_comparison':expected_comparison(pins),'prefix9_reproduction':prefix_comparison(pins)},'reference')
    timestamp(value['recorded_utc'])
    # This verifies recorded runtime environment and current file identities. It
    # intentionally does NOT require caller PYTHONPATH/OMP values or import torch.
    check_runtime(value['runtime'],pins)
    exact_keys(value['outputs'],pins['references'],'reference outputs')
    for name,spec in pins['references'].items():
        need(same(value['outputs'][name],{**spec,'file':name+'.f32le'}),'reference record drift: '+name)
    boundary=value['boundary']
    exact_keys(boundary,{'before_file','after_file','before_sha256','after_sha256','unchanged','native_files_checked'},'boundary')
    fields(boundary,{'before_file':'BOUNDARY_BEFORE.json','after_file':'BOUNDARY_AFTER.json',
           'unchanged':True,'native_files_checked':True},'boundary claims')
    digest(boundary['before_sha256'],'boundary before'); digest(boundary['after_sha256'],'boundary after')
    need(boundary['before_sha256']==boundary['after_sha256'],'boundary differs')
    return value


def read_reference_payloads(root,pins,reference,manifest):
    """Open only after the consumer has sealed actual execution; stdlib byte checks."""
    require_frozen_references(pins)
    directory=stage_path(root,reference)
    result={}
    for name,spec in pins['references'].items():
        need(same(manifest['outputs'][name],{**spec,'file':name+'.f32le'}),'payload metadata drift')
        raw=checked(directory,name+'.f32le',{'bytes':spec['bytes'],'sha256':spec['sha256']})
        need(sha(token_bytes(name,raw,spec['shape']))==spec['token_major_sha256'],'fixed layout hash mismatch')
        words=struct.iter_unpack('<I',raw)
        native=bytearray()
        for (word,) in words:
            need((word&0x7f800000)!=0x7f800000,'nonfinite reference')
            if name=='softmax_fp32': native.extend(struct.pack('<I',word))
            else:
                need(word&0xffff==0,'BF16 export is not exact widening')
                native.extend(struct.pack('<H',word>>16))
        need(sha(native)==spec['native_sha256'],'native logical hash mismatch')
        result[name]=raw
    verify_mask(result['mask'],pins,exported=True)
    verify_mask(checked(directory,'mask.bf16le',{'bytes':pins['mask_contract']['native_bytes'],
                'sha256':pins['mask_contract']['native_sha256']}),pins)
    need(token_bytes('pv',result['pv'],pins['references']['pv']['shape'])==result['att'],'official PV->att layout bytes differ')
    for filename in ('BOUNDARY_BEFORE.json','BOUNDARY_AFTER.json'):
        data=safe_path(directory,filename).read_bytes()
        key='before_sha256' if 'BEFORE' in filename else 'after_sha256'
        need(sha(data)==manifest['boundary'][key],'persisted boundary hash mismatch')
    return result


def audit(root,pins,subset,inputs,reference,out):
    paths=[P.stage_path(root,subset),P.stage_path(root,inputs),stage_path(root,reference)]
    before=boundary_snapshot(root,pins,paths,native=True)
    _,ss,ins=read_inputs(root,pins,subset,inputs)
    manifest=verify_reference_metadata(root,pins,subset,inputs,reference,ss,ins)
    values=read_reference_payloads(root,pins,reference,manifest)
    start_output(out);write_new(out/'BOUNDARY_BEFORE.json',json_bytes(before))
    boundary=finish_boundary(root,pins,paths,before,out,native=True)
    result=report(root,pins,'audit')
    result.update(status='VERIFIED_ATTENTION_REFERENCE_ARTIFACTS_ONLY',reference=reference,
        reference_sha256=sha(safe_path(stage_path(root,reference),'REFERENCE.json').read_bytes()),
        outputs_verified=len(values),reference_hash_comparison=expected_comparison(pins),
        prefix9_reproduction=prefix_comparison(pins),mask_verification=verify_mask(values['mask'],pins,exported=True),
        boundary=boundary,numerical_acceptance_claimed=False,model_execution_in_this_audit=False)
    write_new(out/'AUDIT.json',json_bytes(result));return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default=str(ROOT))
    parser.add_argument('--action',choices=('check',*STAGES),default='check')
    parser.add_argument('--execute',action='store_true')
    for key in ('out','subset','inputs','reference'): parser.add_argument('--'+key)
    args=parser.parse_args(argv)
    try:
        root=Path(args.root).absolute()
        need(root==ROOT and root.resolve()==ROOT,'--root must identify this checkout')
        pins=load_pins(root);coverage=source_check(root,pins)
        if args.action=='check':
            need(not any((args.execute,args.out,args.subset,args.inputs,args.reference)),'cold check accepts no execution/path options')
            if pins['reference_freeze']['status']!='BOOTSTRAP_UNACCEPTED': require_frozen_references(pins)
            result={'status':'NOT_EXECUTED','cold_check':'PASS',**coverage,
                    'reference_freeze_status':pins['reference_freeze']['status'],
                    'torch_imported':'torch' in sys.modules,'numpy_imported':'numpy' in sys.modules,
                    'network_used':False,'raw_payload_read':False,'model_executed':False,
                    'rtl_executed':False,'outputs_written':False}
        else:
            need(args.execute,'--execute required; nothing executed')
            need(args.out and args.subset and args.inputs,'explicit fresh output/subset/inputs required')
            need(bool(args.reference)==(args.action=='audit'),'unexpected/missing --reference')
            paths=[P.stage_path(root,args.subset),P.stage_path(root,args.inputs)]
            if args.reference: paths.append(stage_path(root,args.reference))
            need(len(set(paths))==len(paths),'input aliases refused')
            out=fresh_output(root,args.out,paths)
            if args.action=='audit': result=audit(root,pins,args.subset,args.inputs,args.reference,out)
            else:
                module=types.ModuleType('_qwen2_attention_capture')
                module.__file__=str(HERE/'capture.py')
                exec(compile((HERE/'capture.py').read_bytes(),module.__file__,'exec'),module.__dict__)
                result=module.capture(root,pins,args.subset,args.inputs,out,bootstrap=args.action=='bootstrap-capture',recipe=sys.modules[__name__])
            result={'status':result['status'],'stage':args.action,'out':args.out,
                    'manifest_sha256':sha((out/STAGES[args.action]).read_bytes())}
        print(json.dumps(result,sort_keys=True));return 0
    except (Rejected,OSError,ValueError,KeyError,TypeError,ImportError) as error:
        print(json.dumps({'status':'REJECTED','reason':str(error)},sort_keys=True),file=sys.stderr);return 2


if __name__=='__main__': raise SystemExit(main())
