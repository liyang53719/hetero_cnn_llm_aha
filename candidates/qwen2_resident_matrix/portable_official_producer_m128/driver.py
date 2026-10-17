"""Fresh, source-only M128 producer extension; no numerical work on import.

The live parent must first qualify full M16 on the current host and exact shared
Public library. This fresh interpreter calls the unchanged paired native gate
once at128, with the current-job native16 small gate. The parent separately
replays all native/scalar arrays and observes exit/cleanup before qualification.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
REL = 'candidates/qwen2_resident_matrix/portable_official_producer_m128/'
BASE_REL = 'candidates/qwen2_resident_matrix/portable_official_producer/'
PREREQUISITE_REL = 'candidates/qwen2_resident_matrix/attention_packed_m128_same_host/'
PREREQUISITE_FILES = ('contract.py','prerequisite.py','terminal_m16.py','m16-composed-sources.json','compatible-sources.json')
BASE_SHA = '068d2bdca403b1209c91a03b8bf89b91d9b7f6f4dcd6431a329473fde0702139'
BASE_LOCK_SHA = '95da2c022df48bf3d940e5b439075487a561787bd45fa98edf076b7c91005346'
RUNNER_SHA = 'd7bd12077675984ed7cc20e57a55729fd62e66b773008fa631673086a5a87a64'
PROFILE = 'qwen2-fresh-same-host-m128-producer-v1'
STATUS = 'COMPLETE_FRESH_M128_REFERENCE_OUTPUTS'
CONTEXT_PROFILE = 'qwen2-fresh-same-host-m128-context-v1'
METHODS = ('official_self_cache', 'independent_self_cache')
MODES = ('bf16', 'fp32')
ROWS = 128
PAST = 0
WORK_SECONDS, CLEANUP_SECONDS, RECEIPT_SECONDS = 290, 299, 300
CAPS = dict(compile=10, arena_and_table=30, native128=120, scalar=45, independent_postflight=30)
CLAIMS = dict(actual_chain_executed=False, full_public_admission=False,
    full_29_node_acceptance=False, rtl_execution=False,
    hardware_recipe_acceptance=False, old_pass_inherited=False)
INPUT_SHA = 'ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df'
ARENA_SHA = 'e96def26157427fc60a44f1af7a9a8443010eb5327c1ccb9b93c3b0e70fcafe7'
IMPORTED_DRIVER_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
IMPORTED_LOCK_SHA = hashlib.sha256((HERE/'source-lock.json').read_bytes()).hexdigest()
CONTEXT_KEYS = {'schema','profile','parent_pid','root','workspace','upstream_workspace',
    'created_ns','producer_deadline_ns','deadline_ns','cleanup_deadline_ns','receipt_deadline_ns',
    'attempt_nonce','ci','host','driver_sha256','source_lock_sha256','python','upstream'}
UPSTREAM_KEYS = {'producer_manifest','qualification','native16_result','m16_prerequisite','combined_library'}
TOP_KEYS = {'schema','profile','status','rows','past_tokens','attempt_nonce','ci','host','roots','upstream',
    'parent_context_sha256','runtime_identity','runtime_observation','source_sha256','source_manifest_sha256',
    'driver_sha256','source_lock_sha256','payload','readonly','sequential','reduced','native','dispatch','libraries',
    'claims','original_small_gate_revalidated'}


def need(ok, reason):
    if not ok:
        raise ValueError('fresh M128 producer: ' + reason)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def same(left, right):
    return encoded(left) == encoded(right)


def digest(value, length=64):
    return type(value) is str and len(value)==length and all(c in '0123456789abcdef' for c in value)


def load_checked(name, path, expected):
    path=Path(path).absolute()
    need(all(not p.is_symlink() for p in (path,*path.parents)), 'source symlink')
    info=path.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size<=2*1024*1024,'source file')
    raw=path.read_bytes();need(sha(raw)==expected,'source hash')
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    need(path.read_bytes()==raw,'source import drift')
    return module


def baseline(root=ROOT):
    need(Path(root).resolve()==ROOT,'selected original source root')
    return load_checked('m128_exact_m16_driver',ROOT/BASE_REL/'driver.py',BASE_SHA)


def verify_sources(root=ROOT):
    b=baseline(root)
    old,_=b.verify_sources(root)
    need(sha((ROOT/BASE_REL/'source-lock.json').read_bytes())==BASE_LOCK_SHA,'immutable M16 lock')
    raw=(HERE/'source-lock.json').read_bytes()
    need(sha(raw)==IMPORTED_LOCK_SHA,'M128 source lock drift')
    lock=b.strict(raw)
    need(set(lock)=={'schema','sources'} and type(lock['schema']) is int and lock['schema']==1,'M128 source lock schema')
    sources=lock['sources']
    need(type(sources) is dict and all(sources.get(k)==v for k,v in old.items()),'complete upstream source closure')
    expected=set(old)|{BASE_REL+'driver.py',BASE_REL+'source-lock.json',REL+'verify.py',REL+'replay_original.py'}|{PREREQUISITE_REL+n for n in PREREQUISITE_FILES}
    need(set(sources)==expected,'exact M128 dependency closure')
    for name,expected_sha in sources.items():
        need(digest(expected_sha) and b.record(ROOT,ROOT/name,limit=8*1024*1024)['sha256']==expected_sha,'source drift')
        path=ROOT/name
        if path.suffix=='.py':
            need(not path.with_suffix('.pyc').exists() and not any((path.parent/'__pycache__').glob(path.stem+'.*.pyc')),'source cache')
            for parent in path.parents:
                if parent==ROOT: break
                init=parent/'__init__.py'
                need(not init.exists() or init.relative_to(ROOT).as_posix() in sources,'unpinned initializer')
    need(sha(Path(__file__).read_bytes())==IMPORTED_DRIVER_SHA,'M128 driver drift')
    return sources,sha(raw)


def modules(root=ROOT):
    sources,lock_sha=verify_sources(root)
    b=baseline(root)
    m,_,_=b.modules(root)
    return b,m,sources,lock_sha


def workspace_path(root, workspace):
    b=baseline(root)
    workspace=b.workspace_path(root,workspace)
    need(workspace.name=='producer128','fixed extension output namespace')
    need(not workspace.is_relative_to(workspace.parent/'m16') and not (workspace.parent/'m16').is_relative_to(workspace),'separate outputs')
    return workspace


def pointer(path, b):
    path=Path(path).absolute()
    return dict(path=str(path),sha256=b.record(path.parent,path)['sha256'])


def resolve_pointer(item,b):
    need(type(item) is dict and set(item)=={'path','sha256'} and type(item['path']) is str and digest(item['sha256']),'origin pointer')
    path=Path(item['path'])
    need(path.is_absolute() and '..' not in path.parts and pointer(path,b)==item,'origin pointer bytes')
    return path


def rooted(item, root):
    need(root in ('current','upstream') and type(item) is dict and set(item)=={'path','bytes','sha256'},'record origin')
    return dict(root=root,**item)


def origin_records(value, root):
    if type(value) is dict:
        if set(value)=={'path','bytes','sha256'}: return rooted(value,root)
        return {k:origin_records(v,root) for k,v in value.items()}
    if type(value) is list: return [origin_records(v,root) for v in value]
    return value


def resolve_artifact(workspace, manifest, item):
    b=baseline()
    need(type(manifest) is dict and type(manifest.get('roots')) is dict and set(manifest['roots'])=={'current','upstream'},'two explicit artifact origins')
    workspace=Path(workspace).absolute()
    need(manifest['roots']==dict(current=str(workspace),upstream=str(workspace.parent/'m16/setup/producer')),'fixed current-job artifact roots')
    need(type(item) is dict and set(item)=={'root','path','bytes','sha256'} and item['root'] in manifest['roots'],'rooted record fields')
    return b.resolve(manifest['roots'][item['root']],{k:item[k] for k in ('path','bytes','sha256')})


def all_records(value):
    if type(value) is dict:
        if set(value)=={'root','path','bytes','sha256'}:
            yield value
        else:
            for child in value.values(): yield from all_records(child)
    elif type(value) is list:
        for child in value: yield from all_records(child)


def validate_ci(ci):
    need(type(ci) is dict and set(ci)=={'commit','run_id','run_attempt'} and digest(ci['commit'],40),'CI commit')
    need(type(ci['run_id']) is str and ci['run_id'].isascii() and ci['run_id'].isdecimal() and int(ci['run_id'])>0 and ci['run_attempt']=='1','first CI attempt')


def validate_context(value,root,workspace,end_ns,nonce,ci,*,parent_pid,now_ns,host,python):
    need(type(value) is dict and set(value)==CONTEXT_KEYS,'context fields')
    need(type(value['schema']) is int and value['schema']==1 and value['profile']==CONTEXT_PROFILE,'context profile')
    need(type(value['parent_pid']) is int and value['parent_pid']==parent_pid and parent_pid>1,'actual live owning parent')
    need(value['root']==str(root) and value['workspace']==str(workspace) and value['upstream_workspace']==str(workspace.parent/'m16/setup/producer'),'context namespace')
    validate_ci(ci)
    need(digest(nonce) and value['attempt_nonce']==nonce and same(value['ci'],ci) and same(value['host'],host),'context identity')
    need(value['python']==str(python) and Path(python).is_absolute(),'same private interpreter')
    for key in ('created_ns','producer_deadline_ns','deadline_ns','cleanup_deadline_ns','receipt_deadline_ns'):
        need(type(value[key]) is int,'typed absolute deadline')
    start=value['created_ns']
    need(start<=now_ns<end_ns==value['deadline_ns']==start+WORK_SECONDS*10**9 and
         value['producer_deadline_ns']==start+260*10**9 and
         value['cleanup_deadline_ns']==start+CLEANUP_SECONDS*10**9 and
         value['receipt_deadline_ns']==start+RECEIPT_SECONDS*10**9,'shared260/290/299/300 envelope')
    need(value['driver_sha256']==IMPORTED_DRIVER_SHA and value['source_lock_sha256']==IMPORTED_LOCK_SHA,'context source identity')
    need(type(value['upstream']) is dict and set(value['upstream'])==UPSTREAM_KEYS,'upstream context inventory')
    return value


def launch_context(root,workspace,end_ns,attempt_nonce,ci,path,expected_sha):
    b=baseline(root);workspace=workspace_path(root,workspace);path=Path(path).absolute()
    need(path==workspace.parent/'M128_CONTEXT.json','fixed M128 context location')
    raw=path.read_bytes();need(sha(raw)==expected_sha and digest(expected_sha),'context hash')
    need(b.record(path.parent,path,limit=65536)['sha256']==expected_sha,'context regular file')
    value=b.strict(raw,65536)
    # The exact private venv path, not its resolved shared base executable.
    expected_python=workspace.parent/'m16/setup/venv/bin/python'
    validate_context(value,ROOT,workspace,end_ns,attempt_nonce,ci,parent_pid=os.getppid(),
        now_ns=time.monotonic_ns(),host=live_host(),python=expected_python)
    need(Path(sys.executable).absolute()==expected_python and sys.version_info[:3]==(3,12,15)
         and sys.flags.isolated and sys.dont_write_bytecode and not sys.flags.optimize,'isolated pinned private runtime')
    need(os.environ.get('GITHUB_SHA')==ci['commit'] and os.environ.get('GITHUB_RUN_ID')==ci['run_id']
         and os.environ.get('GITHUB_RUN_ATTEMPT')==ci['run_attempt'],'actual triggering CI environment')
    verify_sources(root)
    need(path.read_bytes()==raw,'context admission drift')
    return value


def live_host():
    boot=Path('/proc/sys/kernel/random/boot_id').read_bytes().strip()
    need(os.uname().sysname=='Linux' and os.uname().machine=='x86_64' and len(boot)==36,'current Linux host')
    return dict(host_sha256=sha(os.uname().nodename.encode()),boot_sha256=sha(boot),machine='x86_64',system='Linux')


def verify_upstream(root,workspace,context,*,hash_only=False):
    b=baseline(root);up=Path(context['upstream_workspace']);job=Path(workspace).parent
    origin=context['upstream']
    expected=dict(producer_manifest=up/'PRODUCER_M16.json',qualification=job/'m16/setup/QUALIFICATION.json',
        native16_result=up/'native16/RESULT.json',m16_prerequisite=job/'M16_PREREQUISITE.json')
    for name,path in expected.items(): need(resolve_pointer(origin[name],b)==path,'exact current-job upstream '+name)
    lib=origin['combined_library']
    need(type(lib) is dict and set(lib)=={'receipt','binary'},'same Public library origin')
    for role,name in (('receipt','official_bf16_compile.json'),('binary','official_bf16_matrix_silu.so')):
        need(resolve_pointer(lib[role],b)==job/'m16/setup/tiny/build'/name,'same-job Public library path')
    qualified=b.strict(expected['qualification'].read_bytes())
    need(qualified.get('schema')==1 and qualified.get('profile')=='qwen2-fresh-same-host-m16-producer-qualified-v1' and
         qualified.get('status')=='PASS_FRESH_M16_PRODUCER' and qualified.get('attempt_nonce')==context['attempt_nonce'] and
         same(qualified.get('ci'),context['ci']) and qualified.get('host_sha256')==sha(encoded(context['host'])) and
         type(qualified.get('child_exit_code')) is int and qualified['child_exit_code']==0 and
         qualified.get('owned_group_cleanup_complete') is True and qualified.get('producer_native_gate_validated') is True and
         qualified.get('producer_manifest_sha256')==origin['producer_manifest']['sha256'],'fresh upstream parent qualification')
    if hash_only:
        value=b.validate_manifest(b.strict(expected['producer_manifest'].read_bytes()))
        original_sources,original_lock=b.verify_sources(root)
        need(value['source_sha256']==original_sources and value['source_lock_sha256']==original_lock and
             value['driver_sha256']==BASE_SHA,'upstream exact original producer sources')
        def check_records(node):
            if type(node) is dict:
                if set(node)=={'path','bytes','sha256'}:b.resolve(up,node)
                else:
                    for child in node.values():check_records(child)
            elif type(node) is list:
                for child in node:check_records(child)
        for field in ('payload','readonly','sequential','reduced','native','libraries'):check_records(value[field])
    else:
        value=b.verify_handoff(root,up,origin['producer_manifest']['sha256'],decode_native=False)
    need(value['attempt_nonce']==context['attempt_nonce'] and same(value['ci'],context['ci']) and
         same(value['host'],context['host']) and qualified['runtime_identity_sha256']==sha(encoded(value['runtime_identity'])) and
         value['native']['result']['sha256']==origin['native16_result']['sha256'],'upstream native/runtime binding')
    verify_full_prerequisite(root,context,qualified)
    return value


def verify_full_prerequisite(root,context,qualified):
    """Load the one strict entry prerequisite verifier from exact current bytes.

    A private import namespace avoids mixed composed-source module caches. No
    numerical module, ELF, subprocess or historical authority is loaded here.
    """
    sources,_=verify_sources(root)
    prefix='_fresh_m128_prerequisite_verified'
    names=[prefix,*[prefix+'.'+n for n in ('contract','terminal_m16','prerequisite')]]
    need(not any(n in sys.modules for n in names),'prerequisite import namespace collision')
    package=types.ModuleType(prefix);package.__path__=[str(ROOT/PREREQUISITE_REL)]
    sys.modules[prefix]=package
    try:
        for name in ('contract','terminal_m16','prerequisite'):
            relative=PREREQUISITE_REL+name+'.py'
            module=load_checked(prefix+'.'+name,ROOT/relative,sources[relative])
            sys.modules[prefix+'.'+name]=module
            setattr(package,name,module)
        item=context['upstream']['m16_prerequisite']
        result=package.prerequisite.verify(Path(item['path']),item['sha256'],
            m16_root=Path(context['workspace']).parent/'m16',parent_pid=context['parent_pid'],
            ci=context['ci'],attempt_nonce=context['attempt_nonce'],host_sha256=sha(encoded(context['host'])),
            runtime_identity_sha256=qualified['runtime_identity_sha256'])
        library=result['library']
        need(library['receipt']==context['upstream']['combined_library']['receipt'] and
            {k:library['binary'][k] for k in ('path','sha256')}==context['upstream']['combined_library']['binary'],
            'context exact same full-M16 Public receipt/ELF')
        need(result['records']['producer_manifest']==context['upstream']['producer_manifest'] and
            result['records']['producer_qualification']==context['upstream']['qualification'],
            'full-M16 authenticated producer pointers')
        return result
    finally:
        for name in names:sys.modules.pop(name,None)


def check_dispatch(m,observations):
    need(type(observations) is dict and set(observations)==set(MODES),'dispatch inventory')
    for item in observations.values():
        m['gate'].diagnostic.validate_verbose(item)
        need(item['status'] in ('COMPLETE_DIAGNOSTIC','NO_ONEDNN_EXECUTION_OBSERVED') or
             m['gate'].diagnostic.has_only_informational_unknowns(item),'incomplete dispatch')
    bf16=observations['bf16']
    if bf16['status']!='NO_ONEDNN_EXECUTION_OBSERVED':
        need(bf16['exec_records']==9,'BF16 execution count')
        roles={}
        for item in bf16['records']:
            need(item['primitive']=='matmul' and all(item['descriptors'].get(k,{}).get('dtype')=='bf16' for k in ('src','wei','dst')),'BF16 dispatch dtype')
            roles[item['role']]=roles.get(item['role'],0)+item['count']
        need(roles==dict(QKV_KV=2,DENSE_HIDDEN=2,MLP=3,ATTENTION_SQUARE=2),'M128 observed execution roles')
    return json.loads(encoded(observations))


def native_m128(root,workspace,context,end_ns,upstream):
    b,m,sources,_=modules(root);up=Path(context['upstream_workspace'])
    with b.bounded(b.phase_end(end_ns,CAPS['native128'])):
        m['gate'].environment()
        runner=up/'generated'/m['qk'].ORIGINAL
        m['gate'].verify_runner(root,runner)
        native=m['phase']._generated(runner,RUNNER_SHA)
        qkv,qk=m['qkv'].verify(up/'qkv_library'),m['qk'].verify(up/'qk_library')
        identity,observed,recipe=b.runtime_observation(m,native,up,qkv,qk,load_recipe=True)
        need(same(identity,upstream['runtime_identity']) and same(observed,upstream['runtime_observation']),'same fresh native16 runtime')
        capture=m['capture'].Capture(workspace/'native128_dispatch',__import__('torch'))
        result=native.run_gate(Path(root),up/'payload',workspace/'native128',tokens=128,
            carried=False,threads=4,small_gate=up/'native16/RESULT.json',qkv_recipe=recipe,diagnostics=capture)
        need(same(result['identity'],identity),'original native runtime')
        raw=(workspace/'native128/RESULT.json').read_bytes()
        need(same(b.strict(raw),result),'native in-memory/disk receipt')
        m['phase'].verify_exports(result,workspace/'native128',128)
        report=m['phase'].project_result(result,tokens=128,result_sha256=sha(raw),source_sha256=sources,
            contract_sha256=b.POLICY_SHA,generated_module_sha256=RUNNER_SHA,library=qk,qkv_library=qkv,
            payload_manifest_sha256=upstream['payload']['manifest']['sha256'],
            m16_result_sha256=context['upstream']['native16_result']['sha256'])
        need(report['status']=='COMPLETE_NATIVE_VALIDATION','native128 numerical gate')
        dispatch=check_dispatch(m,capture.report());recipe.revalidate()
        _,after,_=b.runtime_observation(m,native,up,qkv,qk,load_recipe=False)
        need(same(after,observed),'runtime/fenv drift')
        b.save(workspace/'native128/VALIDATED.json',report)
        b.save(workspace/'native128/DISPATCH.json',dispatch)
        b.save(workspace/'native128/RUNTIME.json',dict(identity=identity,observation=observed))
        verify_sources(root)
    return result,identity,observed,dispatch


def fresh_directory(path):
    path=Path(path).absolute()
    need(all(not p.is_symlink() for p in (path,*path.parents)),'private directory symlink')
    path.mkdir(mode=0o700)
    need(stat.S_IMODE(path.stat().st_mode)==0o700,'exclusive0700 directory')
    return path


def scalar_references(root,workspace,context,end_ns):
    b,m,sources,_=modules(root);up=Path(context['upstream_workspace'])
    rms,builder=m['rms'],m['builder'];original,header,_=builder.regenerate_sources(root)
    reduced,_=builder.transform(original,(Path(root)/builder.PROFILE_REL).read_bytes())
    need(sha(original)==m['assets'].CPP_SHA256['sequential'] and sha(reduced)==m['assets'].CPP_SHA256['reduced'] and
         sha(header)==m['assets'].HEADER_SHA256,'both exact original C++ references')
    layout=rms.R.make_layout();rms.G.validate_layout(layout)
    compiler=b.compiler_record(m,up);records={}
    for role,source in (('sequential',original),('reduced',reduced)):
        out=fresh_directory(workspace/role)
        (out/'candidate.cpp').write_bytes(source);(out/'block_layout.h').write_bytes(header)
        argv=[compiler['path'],*builder.FLAGS,str(out/'candidate.cpp'),'-o',str(out/'candidate')]
        done=m['owner'].run(root,argv,cwd=out,log=out/'compile.log',end_ns=b.phase_end(end_ns,CAPS['compile']))
        b.save(out/'compile.json',dict(schema=1,status='COMPILED',producer=m['assets'].PRODUCERS[role],argv=argv,
            compiler=compiler,returncode=0,source_sha256=sources,cpp_sha256=sha(source),header_sha256=sha(header),
            binary_sha256=b.record(workspace,out/'candidate')['sha256'],elapsed_seconds=done['elapsed_seconds'],requested_timeout_seconds=10))
        records[role]=dict(producer=m['assets'].PRODUCERS[role],**{k:b.record(workspace,out/file) for k,file in
            (('cpp','candidate.cpp'),('header','block_layout.h'),('executable','candidate'),('compile','compile.json'))})
    ro=fresh_directory(workspace/'readonly');arena_end=b.phase_end(end_ns,CAPS['arena_and_table'])
    # Original --tables binary invocation uses the exact retained-leader helper;
    # do not call rms.generate_tables, whose historical subprocess is unowned.
    m['owner'].run(root,[str(workspace/'sequential/candidate'),'--tables',str(ro/'tables.f32le')],
        cwd=ro,log=ro/'tables.log',end_ns=min(arena_end,b.phase_end(end_ns,10)))
    with b.bounded(arena_end):
        import numpy as np
        arrays=rms.table_values(ro/'tables.f32le')
        for trig in ('cos','sin'):
            doubled=np.concatenate((arrays[trig+'_bf16'],arrays[trig+'_bf16']),axis=1)
            need(rms.R.sha(doubled.tobytes())==rms.TABLE_DIGESTS[trig],'original BF16 trig table identity')
            need(np.array_equal(rms.D.bf16(arrays[trig]).view('<u4'),arrays[trig+'_bf16'].view('<u4')),'original table rounding')
        need(b.record(workspace,ro/'tables.f32le')['sha256']==b.TABLE_SHA,'original table bytes')
        _,payload=m['payload'].load_payload(Path(root),up/'payload')
        inputs=rms.write_arena(layout,payload,128,0,ro,ro/'tables.f32le')
        need(inputs['readonly_sha256']==ARENA_SHA and inputs['input_x_sha256']==INPUT_SHA,'true128 current checkpoint arena')
    readonly=dict(arena=b.record(workspace,ro/'readonly_arena.f32le'),table=b.record(workspace,ro/'tables.f32le'),
        input_x=b.record(workspace,ro/'input_x.f32le'),input_x_sha256=inputs['input_x_sha256'],intermediate_preloads=0)
    for role in ('sequential','reduced'):
        out=workspace/role;empty=out/'empty_cache.f32le'
        with empty.open('xb') as stream: stream.write(b'')
        raw=fresh_directory(out/'raw_stages')
        argv=[str(out/'candidate'),str(ro/'readonly_arena.f32le'),'128',str(raw),'0',str(empty),str(empty)]
        done=m['owner'].run(root,argv,cwd=out,log=out/'stdout.log',end_ns=b.phase_end(end_ns,CAPS['scalar']))
        stdout=(out/'stdout.log').read_bytes();need(len(stdout)<=16384,'software stdout bound')
        ack=rms.software_ack(stdout.decode(),128,0)
        inventory=m['workload'].output_inventory(128)
        need(len(inventory)==22 and {p.name for p in raw.iterdir()}==set(inventory),'all22 original raw outputs')
        outputs={name:b.record(workspace,raw/name) for name in inventory}
        m['workload'].validate_sealed_inventory(128,outputs)
        # Native/scalar arrays are independently decoded by the parent verifier.
        # Production retains original per-reference12 semantic and cache checks.
        with b.bounded(end_ns):
            actual=rms.C.load_actual(raw,ro/'readonly_arena.f32le',ro/'input_x.f32le',layout,128)
            semantics=rms.N.audit_semantics(actual,None,rms.G.config_for(layout),'bf16')
            need(len(semantics)==12 and all(v is True for v in semantics.values()),'scalar original semantics')
            for name in ('cache_k','cache_v'):
                cache=np.fromfile(raw/(name+'.f32le'),dtype='<f4').reshape(1,128,2,128).transpose(0,2,1,3)
                need(np.array_equal(cache.view('<u4'),actual[name].view('<u4')),'raw cache append')
            b.save(out/'run.json',dict(schema=1,status='COMPLETE_REFERENCE_ONLY',producer=m['assets'].PRODUCERS[role],argv=argv,
                returncode=0,software_ack=ack,readonly_sha256=inputs['readonly_sha256'],input_x_sha256=inputs['input_x_sha256'],
                table_sha256=b.TABLE_SHA,output_sha256={n:r['sha256'] for n,r in outputs.items()},actual_chain_executed=False,
                stdout=b.record(workspace,out/'stdout.log'),empty_cache=b.record(workspace,empty),elapsed_seconds=done['elapsed_seconds'],requested_timeout_seconds=45))
            records[role].update(run=b.record(workspace,out/'run.json'),outputs=outputs)
            if role=='sequential':
                tensors=fresh_directory(out/'tensors');exported=rms.C.export_actual(actual,tensors)
                b.save(out/'exports.json',exported)
                records[role].update(export_receipt=b.record(workspace,out/'exports.json'),
                    tensors={r['name']:b.record(workspace,tensors/r['path']) for r in exported})
    verify_sources(root)
    return readonly,records


def validate_manifest(value):
    need(type(value) is dict and set(value)==TOP_KEYS,'manifest fields')
    need(type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE and value['status']==STATUS,'manifest profile')
    need(type(value['rows']) is int and value['rows']==128 and type(value['past_tokens']) is int and value['past_tokens']==0,'true128 past0')
    validate_ci(value['ci'])
    need(digest(value['attempt_nonce']) and all(digest(value[k]) for k in ('parent_context_sha256','driver_sha256','source_lock_sha256','source_manifest_sha256')),'manifest identities')
    need(same(value['claims'],CLAIMS) and value['original_small_gate_revalidated'] is True,'nonacceptance scope')
    need(sha(encoded(value['source_sha256']))==value['source_manifest_sha256'],'source map digest')
    need(set(value['native'])=={'producer','result','outputs'} and value['native']['producer']=='generated-paired-qkv-qk.run_gate','original paired producer')
    need(set(value['native']['outputs'])==set(MODES) and
         all(set(value['native']['outputs'][mode])==set(METHODS) for mode in MODES),'native modes/methods')
    need(sum(len(stages) for methods in value['native']['outputs'].values() for stages in methods.values())==116,'native116 inventory')
    need(all(len(value[role]['outputs'])==22 for role in ('sequential','reduced')),'two22 scalar inventories')
    return value


def produce_m128(root,workspace,end_ns,*,attempt_nonce,ci,context_path,context_sha256):
    workspace=workspace_path(root,workspace)
    context=launch_context(root,workspace,end_ns,attempt_nonce,ci,context_path,context_sha256)
    b=baseline(root)
    upstream=verify_upstream(root,workspace,context)
    work_end=context['producer_deadline_ns']
    b.remaining(work_end)
    fresh_directory(workspace)
    result,identity,observation,dispatch=native_m128(root,workspace,context,work_end,upstream)
    readonly,refs=scalar_references(root,workspace,context,work_end)
    sources,lock_sha=verify_sources(root)
    outputs={mode:{method:{name:rooted(b.record(workspace,workspace/'native128'/entry[kind+'_file']),'current')
        for name,entry in result['modes'][mode]['phases'][0]['stages'].items()}
        for method,kind in zip(METHODS,('native','independent'))} for mode in MODES}
    value=dict(schema=1,profile=PROFILE,status=STATUS,rows=128,past_tokens=0,attempt_nonce=attempt_nonce,ci=ci,
        host=observation['host'],roots=dict(current=str(workspace),upstream=context['upstream_workspace']),upstream=context['upstream'],
        parent_context_sha256=context_sha256,runtime_identity=identity,runtime_observation=observation,
        source_sha256=sources,source_manifest_sha256=sha(encoded(sources)),driver_sha256=IMPORTED_DRIVER_SHA,source_lock_sha256=lock_sha,
        payload=origin_records(upstream['payload'],'upstream'),readonly=origin_records(readonly,'current'),
        **origin_records(refs,'current'),native=dict(producer='generated-paired-qkv-qk.run_gate',
            result=rooted(b.record(workspace,workspace/'native128/RESULT.json'),'current'),outputs=outputs),
        dispatch=dispatch,libraries=origin_records(upstream['libraries'],'upstream'),claims=CLAIMS,original_small_gate_revalidated=True)
    validate_manifest(value);manifest_sha=b.save(workspace/'PRODUCER_M128.json',value)
    launch_context(root,workspace,end_ns,attempt_nonce,ci,context_path,context_sha256)
    b.remaining(work_end)
    return dict(path=str(workspace/'PRODUCER_M128.json'),sha256=manifest_sha)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','workspace','context'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--deadline-ns',type=int,required=True)
    for name in ('attempt-nonce','commit','run-id','run-attempt','context-sha256'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args(argv)
    produce_m128(a.root,a.workspace,a.deadline_ns,attempt_nonce=a.attempt_nonce,
        ci=dict(commit=a.commit,run_id=a.run_id,run_attempt=a.run_attempt),context_path=a.context,context_sha256=a.context_sha256)
    return 0


if __name__=='__main__':raise SystemExit(main())
