#!/usr/bin/env python3
"""Five raw Qwen2 tail roles only. Default: stdlib metadata, NOT_EXECUTED."""
from __future__ import annotations

import argparse
import ast
import datetime as dt
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
PACKAGE = 'candidates/qwen2_live_tail_inputs_m128'
OUTPUT_PREFIX = 'work/qwen2_live_tail_inputs_m128'
PINS_SHA256 = 'b521249da785c6a221a03a1dac9b2eda385ecac45dc945b3814716422c6fa3a0'
QKV = 'candidates/qwen2_live_qkv_inputs_m128/recipe.py'
PACKER = 'chisel/continuous_prefill/scripts/pack_owner_block_fixture.py'
ROLES = ('wo', 'gamma1', 'wg', 'wu', 'wd')
SHAPES = {'wo': [1536,1536], 'gamma1': [1536], 'wg': [8960,1536],
          'wu': [8960,1536], 'wd': [1536,8960]}
STATUS = 'FIVE_PINNED_TAIL_INPUT_ROLES_READY_NO_MODEL_EXECUTION'


class Rejected(ValueError):
    """Fail-closed source, metadata, path, or byte gate."""


def need(condition, message):
    if not condition:
        raise Rejected(message)


def same(a, b):
    if type(a) is not type(b):
        return False
    if type(b) is dict:
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in b)
    if type(b) is list:
        return len(a) == len(b) and all(same(x,y) for x,y in zip(a,b))
    return a == b


def fields(actual, expected, label):
    need(type(actual) is dict and all(k in actual and same(actual[k],v)
         for k,v in expected.items()), label + ' identity/type/geometry drift')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()


def parse(raw):
    def pairs(items):
        result = {}
        for k,v in items:
            need(k not in result, 'duplicate JSON key: '+k)
            result[k] = v
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


def file_identity(path):
    need(path.is_file() and not path.is_symlink(), 'regular file required: '+str(path))
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            size += len(chunk)
            digest.update(chunk)
    return {'bytes':size,'sha256':digest.hexdigest()}


def checked(root, relative, expected):
    path = safe_path(root,relative)
    need(path.is_file() and path.stat().st_size == expected['bytes'], 'file length: '+relative)
    raw = path.read_bytes()
    fields({'bytes':len(raw),'sha256':sha(raw)},
           {k:expected[k] for k in ('bytes','sha256')},relative)
    return raw


def load_pins(root=ROOT):
    raw = safe_path(root,PACKAGE+'/pins.json').read_bytes()
    need(sha(raw) == PINS_SHA256, 'pin file drift')
    return parse(raw)


def ast_identity(node):
    return {'line_start':node.lineno,'line_end':node.end_lineno,
            'ast_sha256':sha(ast.dump(node,include_attributes=False).encode())}


def function(tree, name):
    result = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == name]
    need(len(result) == 1, 'missing/ambiguous AST function: '+name)
    return result[0]


def conversion_functions(root, pins):
    """Execute only two original byte-transform function definitions, no imports."""
    tree = ast.parse(checked(root,QKV,pins['sources'][QKV]))
    nodes = [function(tree,name) for name in ('widen_bf16','transpose_words')]
    for node in nodes:
        need(same(ast_identity(node),pins['conversion_ast'][node.name]), 'conversion AST drift')
    namespace = {'need':need}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),QKV+'#byte-functions','exec'),namespace)
    return namespace['widen_bf16'], namespace['transpose_words']


def public_layout(root, pins):
    """Evaluate original metadata allocation/stride prefix, without any file I/O.

    The source's out.exists() guard is omitted because no output is involved.
    All nodes after records=[] (public encoding and writing) are excluded.
    """
    tree = ast.parse(checked(root,PACKER,pins['sources'][PACKER]))
    align, pack = function(tree,'align'), function(tree,'pack')
    prefix = []
    for node in pack.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id == 'records' for t in node.targets):
            break
        if isinstance(node,ast.If) and ast.unparse(node.test) == 'out.exists()':
            continue
        prefix.append(node)
    need(same(ast_identity(align),pins['layout_ast']['align']), 'alignment AST drift')
    need(same([ast_identity(n) for n in prefix],pins['layout_ast']['prefix_nodes']), 'allocation AST drift')
    chain = function(pack,'chain')
    strides = [chain.body[i] for i in (0,1,3)]
    need(same([ast_identity(n) for n in strides],pins['layout_ast']['chain_stride_nodes']), 'stride AST drift')
    namespace = {'shape':dict(H=1536,F=8960,HEADS=12,KVHEADS=2,HD=128,MAX_TOKENS=1024),
                 'tokens':128,'relocate':0}
    args = ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[])
    derived = ast.FunctionDef(name='layout',args=args,body=prefix+[
        ast.Return(value=ast.Name(id='tensors',ctx=ast.Load()))],decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[align,derived],type_ignores=[])),
                 PACKER+'#metadata-prefix','exec'),namespace)
    tensors = namespace['layout']()
    result = {}
    for role in ROLES:
        local = dict(tensors=tensors,name=role)
        exec(compile(ast.Module(body=strides,type_ignores=[]),PACKER+'#metadata-strides','exec'),local)
        t = tensors[role]
        result[role] = {'address':t['address'],'shape':list(t['dims']),
            'descriptor_shape4':list(local['dims']),'descriptor_stride3':list(local['strides']),
            'reserved_bytes':t['words']*4,'readonly':t['readonly'],'virtual':t['virtual']}
    return result


def check_contract(pins):
    fields(pins,{'schema':1,'recipe_id':'qwen2-live-tail-inputs-m128-v1',
        'model_id':'Qwen/Qwen2-1.5B-Instruct','revision':'ba1cf1846d7df0a0591d6c00649f57e798519da8',
        'rows':128,'max_tokens':1024,'raw_bytes':87297024,'output_bytes':87300096,
        'raw_directory':'work/qwen2_tail_ranges_20261014'},'contract')
    fields(pins['runtime_requirements'],{'python_major_minor':[3,12],
        'implementation':'cpython','numeric_packages':[]},'runtime contract')
    need(set(pins['roles']) == set(ROLES) and len(pins['tensors']) == 5, 'five exact tail roles')
    need([t['role'] for t in pins['tensors']] == list(ROLES), 'tail tensor order/coverage')
    for t in pins['tensors']:
        role = t['role']; source_shape = SHAPES[role]
        fields(t,{'dtype':'BF16','shape':source_shape,'source_shape':source_shape,
                  'bytes':math.prod(source_shape)*2},role+' raw')
        vector = role == 'gamma1'; shape = [1,1536] if vector else source_shape[::-1]
        width = 4 if vector else 2
        fields(pins['roles'][role],{'file':role+'.bin','source_local_name':t['local_name'],
            'source_shape':source_shape,'shape':shape,'element_strides':[shape[1],1],
            'byte_strides':[shape[1]*width,width],'descriptor_shape4':shape+[1,1],
            'descriptor_stride3':[shape[1],1,1],'dtype':'float32' if vector else 'uint16',
            'storage_encoding':'IEEE754_FP32_LE' if vector else 'BF16_LE',
            'descriptor_dtype':7 if vector else 5,'bytes':math.prod(shape)*width,
            'reserved_bytes':math.prod(shape)*4,'unused_guard_bytes':math.prod(shape)*(4-width),
            'readonly':True,'virtual':False,'transposed':not vector,'widened':vector},role+' physical')
    fields(pins['boundaries'],{'full_checkpoint_sha256_verified':False,'historical_pass_inherited':False,
        'old_full_manifest_recreated':False,'official_forward_executed':False,'numerical_model_executed':False,
        'rtl_executed':False,'network_used':False,'intermediate_preloads':0},'scope')


def source_check(root, pins):
    need(list(sys.version_info[:2]) == pins['runtime_requirements']['python_major_minor'] and
         sys.implementation.name == pins['runtime_requirements']['implementation'],
         'Python 3.12 CPython required for exact pinned AST fields; no cross-version normalization')
    check_contract(pins)
    for name, expected in pins['sources'].items():
        checked(root,name,expected)
    authority = parse(checked(root,pins['authority_pin'],pins['sources'][pins['authority_pin']]))
    fields(authority,{k:pins[k] for k in ('model_id','revision')},'checkpoint authority')
    header_raw = checked(root,pins['shard']['header']['path'],pins['shard']['header'])
    need(len(header_raw) == 38536 and struct.unpack('<Q',header_raw[:8])[0]+8 == len(header_raw),'header length/prefix')
    header = parse(header_raw[8:])
    by_name = {t['local_name']:t for t in authority['tensors']}
    for t in pins['tensors']:
        need(same({k:v for k,v in t.items() if k != 'role'},by_name.get(t['local_name'])), 'original tensor pin drift')
        fields(header[t['name']],{'dtype':t['dtype'],'shape':t['source_shape'],
                                'data_offsets':t['source_data_offsets']},'header tensor')
        need(t['start'] == len(header_raw)+t['source_data_offsets'][0] and
             t['end']+1 == len(header_raw)+t['source_data_offsets'][1] and
             t['end']-t['start']+1 == t['bytes'], 'absolute tensor range drift')
        cursor = t['start']
        for segment in t['segments']:
            need(segment['start'] == cursor and 0 < segment['bytes'] <= 8388608 and
                 segment['end']+1 == cursor+segment['bytes'], 'segment layout drift')
            cursor = segment['end']+1
        need(cursor == t['end']+1, 'segment span coverage')
    need(sum(len(t['segments']) for t in pins['tensors']) == 14, '14 segment pins')
    layout = public_layout(root,pins)
    for role in ROLES:
        fields(pins['roles'][role],layout[role],role+' public21 allocation')
    conversion_functions(root,pins)
    return {'pinned_sources':len(pins['sources']),'byte_transform_functions':2,
            'roles':5,'raw_bytes':pins['raw_bytes'],'output_bytes':pins['output_bytes'],
            'public21_layout':'pinned original allocation/stride AST; BF16 dtype5 weights, FP32 dtype7 gamma1'}


def verify_http(receipt, segment, pins):
    start,end = segment['start'],segment['end']
    expected = {'requested_url':pins['shard']['url'],'request_range':f'bytes={start}-{end}',
        'status':206,'content_range':f"bytes {start}-{end}/{pins['shard']['checkpoint_file_bytes']}",
        'bytes':segment['bytes'],'sha256':segment['sha256']}
    need(type(receipt) is dict and set(receipt) == set(expected)|{'acquired_at'}, 'HTTP receipt fields')
    fields(receipt,expected,'HTTP receipt')
    need(type(receipt['acquired_at']) is str, 'acquisition time type')
    time = dt.datetime.fromisoformat(receipt['acquired_at'])
    need(time.utcoffset() == dt.timedelta(0), 'UTC acquisition time')


def validate_raw_bytes(raw, tensor):
    need(type(raw) is bytes and len(raw) == tensor['bytes'] and sha(raw) == tensor['sha256'],
         'raw tensor bytes/hash: '+tensor['role'])
    for segment in tensor['segments']:
        offset = segment['start']-tensor['start']
        part = raw[offset:offset+segment['bytes']]
        need(len(part) == segment['bytes'] and sha(part) == segment['sha256'], 'raw segment bytes/hash')


def read_raw(root, pins):
    authority = pins['acquisition_manifest']
    manifest = parse(checked(root,authority['path'],authority))
    fields(manifest,{'schema':1,'status':'VERIFIED_PINNED_QWEN2_FIVE_TAIL_RAW_TENSORS_ONLY',
        'model_id':pins['model_id'],'revision':pins['revision'],'payload_bytes':pins['raw_bytes'],
        'header_sha256':pins['shard']['header']['sha256'],
        'payload_pin_sha256':pins['sources'][pins['authority_pin']]['sha256'],
        'full_checkpoint_sha256_verified':False,'historical_pass_inherited':False,
        'materialization_executed':False,'official_forward_executed':False,'rtl_executed':False},'acquisition metadata')
    need(type(manifest['tensors']) is list and len(manifest['tensors']) == 5, 'raw manifest exact coverage')
    raw = {}
    for t,record in zip(pins['tensors'],manifest['tensors'],strict=True):
        expected = {k:v for k,v in t.items() if k != 'segments'}
        expected.update(file='raw/'+t['local_name']+'.bin',http_receipt_complete=True)
        need(set(record) == set(expected)|{'http_ranges'}, 'raw record fields')
        fields(record,expected,'raw manifest record')
        need(len(record['http_ranges']) == len(t['segments']), 'HTTP receipt coverage')
        for segment,receipt in zip(t['segments'],record['http_ranges'],strict=True):
            verify_http(receipt,segment,pins)
        data = checked(root,pins['raw_directory']+'/'+record['file'],t)
        validate_raw_bytes(data,t)
        raw[t['role']] = data
    return raw


def source_identity(root, pins):
    names = sorted(set(pins['sources'])|{PACKAGE+'/recipe.py',PACKAGE+'/pins.json'})
    return {name:file_identity(safe_path(root,name)) for name in names}


def raw_identity(root, pins):
    names = [pins['acquisition_manifest']['path']]+[pins['raw_directory']+'/raw/'+t['local_name']+'.bin' for t in pins['tensors']]
    return {name:file_identity(safe_path(root,name)) for name in names}


def snapshot(root, pins):
    return {'sources':source_identity(root,pins),'inputs':raw_identity(root,pins),
            'physical_roles':pins['roles']}


def finish_boundary(root, pins, before):
    source_check(root,pins)
    after = snapshot(root,pins)
    need(same(after,before), 'source/input/layout changed during execution')
    return after


def stage_path(root, value):
    need(type(value) is str and re.fullmatch(re.escape(OUTPUT_PREFIX)+
         r'/[A-Za-z0-9][A-Za-z0-9_-]{0,63}/[A-Za-z0-9][A-Za-z0-9_-]{0,63}',value),
         'expected dedicated work/<run-id>/<stage-id> path')
    return safe_path(root,value)


def fresh_output(root, value, inputs=()):
    out = stage_path(root,value)
    need(not out.exists(), 'output exists; choose a fresh identity')
    for source in inputs:
        need(not out.is_relative_to(source) and not source.is_relative_to(out),'output/input overlap')
    return out


def write_new(path, raw):
    need(not path.is_symlink(), 'output symlink')
    with path.open('xb') as stream:
        stream.write(raw)


def start_output(root, relative):
    out = fresh_output(root,relative)
    out.parent.mkdir(parents=True,exist_ok=True)
    # Recheck after parent creation and before exclusive directory creation.
    out = fresh_output(root,relative)
    out.mkdir(exist_ok=False)
    return out


def verify_correspondence(raw, output, spec):
    """Independent byte-lane/address check, not the producer transpose loop."""
    need(len(output) == spec['bytes'], 'materialized size')
    if spec['widened']:
        need(output[0::4] == bytes(len(raw)//2) and output[1::4] == bytes(len(raw)//2) and
             output[2::4] == raw[0::2] and output[3::4] == raw[1::2], 'direct gamma widening bytes')
    else:
        rows,columns = spec['source_shape']
        for row in range(rows):
            source = raw[row*columns*2:(row+1)*columns*2]
            need(output[row*2::rows*2] == source[0::2] and
                 output[row*2+1::rows*2] == source[1::2], 'transpose byte/address correspondence')


def base_report(pins, before, after):
    import resource
    return {'schema':1,'recipe_id':pins['recipe_id'],'model_id':pins['model_id'],
        'revision':pins['revision'],'pins_sha256':PINS_SHA256,
        'recorded_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'boundaries':pins['boundaries'],'before':before,'after':after,
        'torch_imported':False,'numpy_imported':False,'stdlib_only':True,
        'python_version':sys.version,'maximum_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'raw_bytes':pins['raw_bytes'],'output_bytes':pins['output_bytes']}


def materialize(root, pins, relative):
    out = fresh_output(root,relative,[safe_path(root,pins['raw_directory'])])
    source_check(root,pins)
    before = snapshot(root,pins)
    raw = read_raw(root,pins)
    widen,transpose = conversion_functions(root,pins)
    outputs,records = {},{}
    for role in ROLES:
        spec = pins['roles'][role]
        data = widen(raw[role]) if spec['widened'] else transpose(raw[role],*spec['source_shape'])
        verify_correspondence(raw[role],data,spec)
        outputs[role] = data
        records[role] = {**spec,'sha256':sha(data)}
    # Metadata, original/raw hashes, exact physical layout and all conversion
    # correspondence checks must finish before creating any output directory.
    finish_boundary(root,pins,before)
    out = start_output(root,relative)
    for role,data in outputs.items():
        write_new(out/(role+'.bin'),data)
    for role in ROLES:
        fields(file_identity(out/(role+'.bin')),
               {k:records[role][k] for k in ('bytes','sha256')},'output readback')
    after = finish_boundary(root,pins,before)
    result = base_report(pins,before,after)
    result.update(status=STATUS,roles=records,raw_manifest=pins['acquisition_manifest'],
                  output_directory=relative,original_http_timestamps_preserved=True,
                  inverse_byte_lane_audit=True,acceptance_scope='input reconstruction only')
    # This seal is absent on every failed/partial run. No resume/force exists.
    write_new(out/'INPUTS_READY.json',encoded(result))
    return result


def read_inputs(root, pins, relative, raw):
    directory = stage_path(root,relative)
    need(directory.is_dir(), 'missing materialized directory')
    need({p.name for p in directory.iterdir()} == {r+'.bin' for r in ROLES}|{'INPUTS_READY.json'},
         'unexpected/missing materialized artifact')
    ready = parse(safe_path(root,relative+'/INPUTS_READY.json').read_bytes())
    fields(ready,{'schema':1,'status':STATUS,'recipe_id':pins['recipe_id'],
        'model_id':pins['model_id'],'revision':pins['revision'],'pins_sha256':PINS_SHA256,
        'boundaries':pins['boundaries'],'output_directory':relative,
        'raw_manifest':pins['acquisition_manifest'],'raw_bytes':pins['raw_bytes'],
        'output_bytes':pins['output_bytes'],'torch_imported':False,'numpy_imported':False,
        'stdlib_only':True,'original_http_timestamps_preserved':True,'inverse_byte_lane_audit':True,
        'acceptance_scope':'input reconstruction only'},'ready receipt')
    need(type(ready['roles']) is dict and set(ready['roles']) == set(ROLES), 'ready five roles')
    current = snapshot(root,pins)
    need(same(ready['before'],current) and same(ready['after'],current), 'receipt/current boundary drift')
    for role in ROLES:
        record = ready['roles'][role]
        need(set(record) == set(pins['roles'][role])|{'sha256'}, 'role record exact fields')
        fields(record,pins['roles'][role],role+' materialized record')
        data = checked(root,relative+'/'+role+'.bin',record)
        verify_correspondence(raw[role],data,pins['roles'][role])
    return ready


def audit(root, pins, relative, output):
    directory = stage_path(root,relative)
    fresh_output(root,output,[directory,safe_path(root,pins['raw_directory'])])
    source_check(root,pins)
    before = snapshot(root,pins)
    raw = read_raw(root,pins)
    artifacts_before = {p.name:file_identity(safe_path(root,relative+'/'+p.name)) for p in directory.iterdir()}
    ready = read_inputs(root,pins,relative,raw)
    artifacts_after = {p.name:file_identity(safe_path(root,relative+'/'+p.name)) for p in directory.iterdir()}
    need(same(artifacts_before,artifacts_after), 'materialized artifact changed during audit')
    after = finish_boundary(root,pins,before)
    result = base_report(pins,before,after)
    result.update(status='VERIFIED_FIVE_TAIL_ROLES_BYTE_CORRESPONDENCE_ONLY',
                  inputs=relative,artifacts_before=artifacts_before,artifacts_after=artifacts_after,
                  roles=ready['roles'],acceptance_scope='input reconstruction only')
    out = start_output(root,output)
    write_new(out/'AUDIT.json',encoded(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action',choices=('check','materialize','audit'),default='check')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--out')
    parser.add_argument('--inputs')
    args = parser.parse_args(argv)
    if args.action == 'check':
        need(not args.execute and args.out is None and args.inputs is None, 'cold path has no execution/data/output options')
    else:
        need(args.execute and args.out is not None, 'explicit --execute and fresh --out required')
        need((args.inputs is not None) == (args.action == 'audit'), 'inputs only/required for audit')
    pins = load_pins(ROOT)
    summary = source_check(ROOT,pins)
    if args.action == 'check':
        result = dict(status='NOT_EXECUTED',cold_check='PASS',source_check=summary,
            raw_payload_read=False,outputs_written=False,torch_imported=False,numpy_imported=False,
            network_used=False,model_executed=False,rtl_executed=False)
    elif args.action == 'materialize':
        result = materialize(ROOT,pins,args.out)
    else:
        result = audit(ROOT,pins,args.inputs,args.out)
    print(json.dumps(result,sort_keys=True))
    return result


if __name__ == '__main__':
    try:
        main()
    except (Rejected,OSError,KeyError,TypeError,ValueError) as error:
        raise SystemExit('TAIL_INPUTS_REJECTED: '+str(error))
