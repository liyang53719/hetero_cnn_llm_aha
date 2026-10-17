"""Independent parent-owned full M128 array replay; imports are stdlib-only.

Repeated entry admission may use decode_native=False for exact hashes/metadata.
Only this CLI uses decode_native=True and emits the independently replayed
receipt. The live parent must additionally observe its zero exit and cleanup.
"""
import argparse
import ast
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import stat
import sys
import time
import types
import re

HERE=Path(__file__).resolve().parent
VERIFY_PROFILE='qwen2-fresh-parent-m128-native-verification-v1'
VERIFY_STATUS='PASS_ORIGINAL_M128_NATIVE_AND_SCALAR_GATES'


def driver(expected_sha256=None):
    path=HERE/'driver.py';spec=importlib.util.spec_from_file_location('fresh_m128_verifier_driver',path)
    raw=path.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest()!=expected_sha256:
        raise ValueError('parent-bound producer driver hash')
    module=importlib.util.module_from_spec(spec)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def cold_modules(d):
    """Exact original metadata functions with explicit local import bindings.

    No original numerical module or candidates namespace is imported. Only
    reviewed relative import statements are rebound; all helper bodies stay
    unchanged. This prevents composed/original source-tree cache mixtures.
    """
    sources,_=d.verify_sources(d.ROOT)
    def bound(name,relative,bindings=None,expected_imports=()):
        bindings={} if bindings is None else bindings
        path=d.ROOT/relative;raw=path.read_bytes()
        d.need(d.sha(raw)==sources[relative],'cold metadata source')
        tree=ast.parse(raw)
        removed=[n for n in tree.body if isinstance(n,ast.ImportFrom) and n.level]
        d.need(tuple(ast.unparse(n) for n in removed)==tuple(expected_imports),'exact metadata import-only adaptation')
        tree.body=[n for n in tree.body if n not in removed]
        module=types.ModuleType(name);module.__file__=str(path);module.__dict__.update(bindings)
        exec(compile(tree,str(path),'exec'),module.__dict__)
        return module
    prefix='candidates/qwen2_resident_matrix/'
    qkv=bound('cold_original_qkv',prefix+'raw_kv_native_qkv/kernel.py')
    qk=bound('cold_original_qk',prefix+'raw_kv_native_qk/kernel.py',dict(previous=qkv),
        ('from ..raw_kv_native_qkv import kernel as previous',))
    phase=bound('cold_original_phase',prefix+'raw_kv_native_qk_run/phase.py',dict(kernel=qk,qkv_kernel=qkv),
        ('from ..raw_kv_native_qk import kernel','from ..raw_kv_native_qkv import kernel as qkv_kernel'))
    diagnostic=bound('cold_original_dispatch',prefix+'raw_kv_native_qk_run/dispatch_diagnostic.py')
    gate=bound('cold_original_gate',d.BASE_REL+'gate.py',dict(phase=phase,diagnostic=diagnostic),
        ('from ..raw_kv_native_qk_run import phase','from ..raw_kv_native_qk_run import dispatch_diagnostic as diagnostic'))
    assets=bound('cold_original_assets',prefix+'raw_kv_public_fresh/assets.py')
    workload=bound('cold_original_workload',prefix+'dense_block_reduce/reference/workload.py')
    # The unchanged ACK parser only needs the original stage names and widths.
    # Supply their exact source-pinned workload projection without importing a
    # numerical model merely to parse a stdout receipt.
    widths=dict(workload.STAGES)
    R=types.SimpleNamespace(STAGE_NAMES=tuple(widths),require=d.need,
        make_layout=lambda:dict(max_tokens=256,regions=[dict(name=n,words=w*256) for n,w in widths.items()]))
    path=d.ROOT/'scripts/qwen2_rms_rope_prefill_candidate.py';raw=path.read_bytes()
    d.need(d.sha(raw)==sources[path.relative_to(d.ROOT).as_posix()],'original ACK source')
    node=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='software_ack')
    namespace=dict(re=re,R=R)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    return dict(qkv=qkv,qk=qk,phase=phase,gate=gate,assets=assets,workload=workload,
        rms=types.SimpleNamespace(software_ack=namespace['software_ack']),
        builder=types.SimpleNamespace(FLAGS=['-O2','-std=c++17','-ffp-contract=off','-fno-fast-math']))


def replay_source(original):
    """Allow only six geometry literals plus function/diagnostic renaming.

    In particular the arithmetic BF16 >>16 remains byte-for-byte unchanged.
    """
    tree=ast.parse(original)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_small_gate')
    text=ast.get_source_segment(original.decode() if type(original) is bytes else original,node)
    replacements={
        'def validate_small_gate(':'def validate_m128_gate(',
        "'tokens': 16":"'tokens': 128",
        'ids = list(range(phase * 16, (phase + 1) * 16))':'ids = list(range(phase * 128, (phase + 1) * 128))',
        "receipt['past_tokens'] != phase * 16":"receipt['past_tokens'] != phase * 128",
        'expected_shapes(config, 16, phase * 16)':'expected_shapes(config, 128, phase * 128)',
    }
    for before,after in replacements.items():
        if text.count(before)!=1:raise ValueError('original array validator adaptation drift')
        text=text.replace(before,after)
    return text.replace('M16','M128')


def validate_replay_source(d):
    raw=(d.ROOT/'scripts/qwen2_layer0_model_gate.py').read_bytes()
    expected=ast.parse(replay_source(raw)).body[0]
    installed=(HERE/'replay_original.py').read_bytes();tree=ast.parse(installed)
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
    d.need(len(functions)==1 and ast.dump(functions[0],include_attributes=False)==ast.dump(expected,include_attributes=False),'exact geometry-only replay body')
    d.need(len([n for n in ast.walk(functions[0]) if isinstance(n,ast.Constant) and type(n.value) is int and n.value==128])==6,'exact six geometric substitutions')
    shifts=[n for n in ast.walk(functions[0]) if isinstance(n,ast.BinOp) and isinstance(n.op,ast.RShift)]
    d.need(len(shifts)==1 and isinstance(shifts[0].right,ast.Constant) and shifts[0].right.value==16,'original BF16 storage shift')
    return installed


def replay_arrays(d,b,m,native,workspace,upstream,manifest):
    import numpy as np
    raw=validate_replay_source(d)
    # Original functions, thresholds, rounding, and semantic helpers supply the
    # execution namespace; neither a substitute comparator nor producer report
    # can decide the parent-owned verdict.
    namespace=dict(native.__dict__)
    exec(compile(raw,str(HERE/'replay_original.py'),'exec'),namespace)
    _,payload=m['payload'].load_payload(d.ROOT,upstream/'payload')
    embeddings=(np.frombuffer(payload['embed_tokens.rows_0_255'],dtype='<u2').astype('<u4')<<16).view('<f4').reshape(256,1536)
    config=b.strict((d.ROOT/native.SOURCE/'config.json').read_bytes())
    namespace['validate_m128_gate'](workspace/'native128/RESULT.json',manifest['runtime_identity'],
        manifest['payload']['manifest']['sha256'],native.load_policy(d.ROOT),config,embeddings,False,4)


def scalar_metadata(d,b,m,workspace,value,role):
    rms=m['rms'];producer=value[role]
    expected={'producer','cpp','header','executable','compile','run','outputs'}
    if role=='sequential':expected|={'export_receipt','tensors'}
    d.need(type(producer) is dict and set(producer)==expected and producer['producer']==m['assets'].PRODUCERS[role],'scalar manifest inventory')
    resolve=lambda item:d.resolve_artifact(workspace,value,item)
    cpp,header,binary=(resolve(producer[k]) for k in ('cpp','header','executable'))
    built=b.strict(resolve(producer['compile']).read_bytes())
    keys={'schema','status','producer','argv','compiler','returncode','source_sha256','cpp_sha256','header_sha256','binary_sha256','elapsed_seconds','requested_timeout_seconds'}
    d.need(type(built) is dict and set(built)==keys,'compile receipt fields')
    compiler=value['runtime_observation']['compiler']
    d.need(type(built['schema']) is int and built['schema']==1 and built['status']=='COMPILED' and
        built['producer']==producer['producer'] and type(built['returncode']) is int and built['returncode']==0 and
        d.same(built['source_sha256'],value['source_sha256']) and built['compiler']==compiler,'compile binding')
    d.need(cpp==workspace/role/'candidate.cpp' and header==cpp.parent/'block_layout.h' and binary==cpp.parent/'candidate' and
        built['argv']==[compiler['path'],*m['builder'].FLAGS,str(cpp),'-o',str(binary)] and
        producer['cpp']['sha256']==built['cpp_sha256']==m['assets'].CPP_SHA256[role] and
        producer['header']['sha256']==built['header_sha256']==m['assets'].HEADER_SHA256 and
        built['binary_sha256']==producer['executable']['sha256'],'exact C++/flags/headers')
    with binary.open('rb') as stream:d.need(stream.read(4)==b'\x7fELF','scalar ELF')
    m['assets']._finite_seconds(built['elapsed_seconds'],10)
    d.need(type(built['requested_timeout_seconds']) is int and built['requested_timeout_seconds']==10,'compiler10 cap')
    run=b.strict(resolve(producer['run']).read_bytes())
    keys={'schema','status','producer','argv','returncode','software_ack','readonly_sha256','input_x_sha256','table_sha256','output_sha256','actual_chain_executed','stdout','empty_cache','elapsed_seconds','requested_timeout_seconds'}
    d.need(type(run) is dict and set(run)==keys,'scalar receipt fields')
    d.need(type(run['schema']) is int and run['schema']==1 and run['status']=='COMPLETE_REFERENCE_ONLY' and
        run['producer']==producer['producer'] and type(run['returncode']) is int and run['returncode']==0 and
        run['actual_chain_executed'] is False and run['readonly_sha256']==d.ARENA_SHA and run['input_x_sha256']==d.INPUT_SHA and
        run['table_sha256']==b.TABLE_SHA and run['output_sha256']=={n:r['sha256'] for n,r in producer['outputs'].items()},'scalar run binding')
    # Compile/run receipts are local producer records; root selectors appear only
    # in the top manifest. No unbound extra origin is accepted within receipts.
    stdout=b.resolve(workspace,run['stdout']);empty=b.resolve(workspace,run['empty_cache'])
    d.need(stdout==workspace/role/'stdout.log' and run['stdout']['bytes']<=16384 and
        empty==workspace/role/'empty_cache.f32le' and run['empty_cache']['bytes']==0 and run['empty_cache']['sha256']==d.sha(b''),'stdout/empty paths')
    inventory=m['workload'].output_inventory(128)
    d.need(len(inventory)==22 and set(producer['outputs'])==set(inventory),'all22 scalar outputs')
    rawdir=workspace/role/'raw_stages'
    d.need(rawdir.is_dir() and not rawdir.is_symlink() and stat.S_IMODE(rawdir.stat().st_mode)==0o700 and
        {p.name for p in rawdir.iterdir()}==set(inventory),'exclusive0700 exact output directory')
    for name,size in inventory.items():d.need(resolve(producer['outputs'][name])==rawdir/name and producer['outputs'][name]['bytes']==size,'full128 raw output shape')
    arena=resolve(value['readonly']['arena'])
    d.need(run['argv']==[str(binary),str(arena),'128',str(rawdir),'0',str(empty),str(empty)],'exact one true128 scalar command')
    d.need(rms.software_ack(stdout.read_text(),128,0)==run['software_ack'],'original software ACK')
    m['assets']._finite_seconds(run['elapsed_seconds'],45)
    d.need(type(run['requested_timeout_seconds']) is int and run['requested_timeout_seconds']==45,'scalar45 cap')
    return rawdir


def scalar_arrays(d,b,m,workspace,value,role,rawdir):
    import numpy as np
    rms=m['rms'];layout=rms.R.make_layout();rms.G.validate_layout(layout)
    resolve=lambda item:d.resolve_artifact(workspace,value,item)
    actual=rms.C.load_actual(rawdir,resolve(value['readonly']['arena']),resolve(value['readonly']['input_x']),layout,128)
    semantics=rms.N.audit_semantics(actual,None,rms.G.config_for(layout),'bf16')
    d.need(len(semantics)==12 and all(v is True for v in semantics.values()),'independent scalar12 semantics')
    for name in ('cache_k','cache_v'):
        cache=np.fromfile(rawdir/(name+'.f32le'),dtype='<f4').reshape(1,128,2,128).transpose(0,2,1,3)
        d.need(np.array_equal(cache.view('<u4'),actual[name].view('<u4')),'independent raw cache append')
    if role=='sequential':
        for name,array in actual.items():
            if name not in value[role]['tensors']:continue
            exported=rms.N.export_value(array,name)
            item=value[role]['tensors'][name]
            d.need(exported.tobytes()==resolve(item).read_bytes(),'sequential actual/export array equality')


def sequential_exports(d,b,m,workspace,value):
    producer=value['sequential'];resolve=lambda item:d.resolve_artifact(workspace,value,item)
    exported=b.strict(resolve(producer['export_receipt']).read_bytes())
    funcs,stages,_=m['phase'].helpers();shapes=funcs['expected_shapes'](m['phase'].CONFIG,128,0)
    d.need(type(exported) is list and len(exported)==29 and [r.get('name') for r in exported]==sorted(stages) and set(producer['tensors'])==set(stages),'sequential29 export inventory')
    for item in exported:
        d.need(type(item) is dict and set(item)=={'name','path','shape','export_shape','sha256'},'sequential export fields')
        name=item['name'];shape=shapes[name]
        export=[shape[0],shape[2],shape[1]*shape[3]] if name in ('q','k') else shape
        record=producer['tensors'][name]
        d.need(item['path']=='candidate_'+name+'.f32le' and d.same(item['shape'],shape) and d.same(item['export_shape'],export) and
            item['sha256']==record['sha256'] and record['bytes']==4*math.prod(shape) and
            resolve(record)==workspace/'sequential/tensors'/item['path'],'true128 sequential export shape/hash')
    return exported


def verify_handoff(root,workspace,expected_sha256,*,context,expected_context_sha256,decode_native=False):
    """Hash-only admission or explicit independent array replay, never a forward."""
    d=driver(context['driver_sha256']);b=d.baseline(root);workspace=d.workspace_path(root,workspace)
    d.need(type(decode_native) is bool,'explicit array decode mode')
    path=workspace/'PRODUCER_M128.json';raw=path.read_bytes()
    d.need(d.digest(expected_sha256) and d.sha(raw)==expected_sha256 and b.record(workspace,path)['sha256']==expected_sha256,'manifest bytes')
    value=d.validate_manifest(b.strict(raw))
    d.need(d.sha(d.encoded(context))==expected_context_sha256 and
        value['parent_context_sha256']==expected_context_sha256 and context['workspace']==str(workspace) and context['root']==str(d.ROOT),'parent context binding')
    d.need(value['attempt_nonce']==context['attempt_nonce'] and d.same(value['ci'],context['ci']) and
        d.same(value['host'],context['host']) and d.same(value['host'],d.live_host()) and d.same(value['upstream'],context['upstream']),'current context/host/upstream')
    sources,lock_sha=d.verify_sources(root)
    d.need(value['source_sha256']==sources and value['source_lock_sha256']==lock_sha and value['driver_sha256']==d.IMPORTED_DRIVER_SHA,'manifest source closure')
    upstream=d.verify_upstream(root,workspace,context,hash_only=not decode_native)
    d.need(d.same(value['payload'],d.origin_records(upstream['payload'],'upstream')) and
        d.same(value['libraries'],d.origin_records(upstream['libraries'],'upstream')),'explicit immutable payload/library reuse')
    seen={}
    for field in ('payload','readonly','sequential','reduced','native','libraries'):
        for item in d.all_records(value[field]):
            p=d.resolve_artifact(workspace,value,item);info=p.stat();key=(info.st_dev,info.st_ino)
            d.need(key not in seen or seen[key]==str(p),'cross-origin hardlink/alias')
            seen[key]=str(p)
            d.need(item['root']==('upstream' if field in ('payload','libraries') else 'current'),'artifact role origin')
    d.need(value['readonly']['arena']['bytes']==188043264 and value['readonly']['arena']['sha256']==d.ARENA_SHA and
        value['readonly']['input_x']['bytes']==786432 and value['readonly']['input_x']['sha256']==value['readonly']['input_x_sha256']==d.INPUT_SHA and
        value['readonly']['table']['sha256']==b.TABLE_SHA and type(value['readonly']['intermediate_preloads']) is int and
        value['readonly']['intermediate_preloads']==0,'full128 arena/input/table')
    up=Path(context['upstream_workspace'])
    if decode_native:
        b,m,_,_=d.modules(root)
        native=m['phase']._generated(up/'generated'/m['qk'].ORIGINAL,d.RUNNER_SHA)
    else:
        m=cold_modules(d)
        native=None
    m['gate'].verify_runner(root,up/'generated'/m['qk'].ORIGINAL)
    qkv,qk=m['qkv'].verify(up/'qkv_library'),m['qk'].verify(up/'qk_library')
    if decode_native:
        identity,observed,_=b.runtime_observation(m,native,up,qkv,qk,load_recipe=False)
    else:
        identity,observed=upstream['runtime_identity'],upstream['runtime_observation']
        m['gate'].validate_identity(identity)
        d.need(m['gate'].environment()==observed['blas_environment'] and
            b.compiler_record(m,up)==observed['compiler'] and
            d.same(m['phase'].combined_identity(qk,qkv),identity['independent_qkv_recipe']),
            'current hash-only runtime/compiler/recipe binding')
    d.need(d.same(identity,value['runtime_identity']) and d.same(observed,value['runtime_observation']) and
        d.same(identity,upstream['runtime_identity']) and d.same(observed,upstream['runtime_observation']),'observed current runtime')
    result_path=d.resolve_artifact(workspace,value,value['native']['result'])
    d.need(result_path==workspace/'native128/RESULT.json','canonical native128 result')
    result_raw=result_path.read_bytes();result=b.strict(result_raw)
    d.need(d.same(result['identity'],identity) and result['m16_gate_sha256']==context['upstream']['native16_result']['sha256'],'current native16 small gate linkage')
    # Complete bytes/shape and unique-inode validation always precedes replay.
    m['phase'].verify_exports(result,workspace/'native128',128)
    report=m['phase'].project_result(result,tokens=128,result_sha256=d.sha(result_raw),source_sha256=sources,
        contract_sha256=b.POLICY_SHA,generated_module_sha256=d.RUNNER_SHA,library=qk,qkv_library=qkv,
        payload_manifest_sha256=value['payload']['manifest']['sha256'],m16_result_sha256=context['upstream']['native16_result']['sha256'])
    d.need(report['status']=='COMPLETE_NATIVE_VALIDATION','original native128 metadata')
    for mode in d.MODES:
        stages=result['modes'][mode]['phases'][0]['stages']
        for method,kind in zip(d.METHODS,('native','independent')):
            d.need(set(value['native']['outputs'][mode][method])==set(stages),'native exact29 stage inventory')
            for name,item in stages.items():
                d.need(d.resolve_artifact(workspace,value,value['native']['outputs'][mode][method][name])==workspace/'native128'/item[kind+'_file'],'native export canonical binding')
    d.check_dispatch(m,value['dispatch'])
    directories={role:scalar_metadata(d,b,m,workspace,value,role) for role in ('sequential','reduced')}
    sequential_exports(d,b,m,workspace,value)
    if decode_native:
        replay_arrays(d,b,m,native,workspace,up,value)
        for role,rawdir in directories.items():scalar_arrays(d,b,m,workspace,value,role,rawdir)
    d.verify_sources(root)
    d.need(path.read_bytes()==raw and result_path.read_bytes()==result_raw,'post-replay manifest/result drift')
    return value


def verification_receipt(d,value,manifest_sha,context_sha):
    return dict(schema=1,profile=VERIFY_PROFILE,status=VERIFY_STATUS,attempt_nonce=value['attempt_nonce'],ci=value['ci'],
        producer_manifest_sha256=manifest_sha,parent_context_sha256=context_sha,source_manifest_sha256=value['source_manifest_sha256'],
        runtime_identity_sha256=d.sha(d.encoded(value['runtime_identity'])),host_sha256=d.sha(d.encoded(value['host'])),
        native_exports=116,native_stages=29,scalar_outputs_each=22,scalar_semantics_each=12,
        original_array_gate_revalidated=True,new_forward_executed=False,claims=d.CLAIMS)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','workspace','context','out'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('context-sha256','manifest-sha256'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args(argv);d=driver();b=d.baseline(a.root)
    context=b.strict(a.context.read_bytes(),65536)
    d.launch_context(a.root,a.workspace,context['deadline_ns'],context['attempt_nonce'],context['ci'],a.context,a.context_sha256)
    d.need(a.out.absolute()==a.workspace.absolute().parent/'VERIFIED_M128_PRODUCER.json','fixed parent verifier output')
    with b.bounded(min(context['deadline_ns'],time.monotonic_ns()+30*10**9)):
        value=verify_handoff(a.root,a.workspace,a.manifest_sha256,context=context,
            expected_context_sha256=a.context_sha256,decode_native=True)
        d.launch_context(a.root,a.workspace,context['deadline_ns'],context['attempt_nonce'],context['ci'],a.context,a.context_sha256)
        b.save(a.out,verification_receipt(d,value,a.manifest_sha256,a.context_sha256))
        b.remaining(context['deadline_ns'])
    return 0


if __name__=='__main__':raise SystemExit(main())
