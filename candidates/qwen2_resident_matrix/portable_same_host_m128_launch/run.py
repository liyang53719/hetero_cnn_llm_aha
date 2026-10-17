"""Single-parent fresh full-M16 then genuine full-M128 successor.

The frozen M16 routine runs in this process with its original internal 1940/1950
checks and setup/full phase alarms. The external watchdog for this whole new
job is TERM4910/KILL4920, not a separate external M16 watchdog. No retry.
"""
import argparse
import hashlib
import importlib.util
import importlib.machinery
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
import types

HERE=Path(__file__).resolve().parent
BASE='candidates/qwen2_resident_matrix/'
OWN=BASE+'portable_same_host_m128_launch/'
M16=BASE+'portable_same_host_m16_launch/'
LAUNCH=BASE+'portable_official_producer_launch/'
PRODUCER=BASE+'portable_official_producer_m128/'
ENTRY=BASE+'attention_packed_m128_same_host/'
SOURCE_CONTRACT=ENTRY+'SOURCE_CONTRACT.json'
PROFILE='qwen2-fresh-same-host-m128-combined-v1'
ENTRY_PROFILE='qwen2-public-pv16-packed-m128-same-host-v1'
M16_RUN_SHA='9b997dcdfd1bca66af6451f0be0dbd6d9c2bf0712426200b00645f07ac3bd8fd'
LAUNCH_SHA='59dd972bd6e5ccc4871ae06bfc8d46adb07bfe642ae80a536b51843b2946b2d7'
CONTRACT_SHA='427386e6585ce663c69f0c49a64e25d9b1296d5c986c4044290315d262b1c926'
BUDGETS=dict(total=4920,outer_term=4910,m16_routine=1950,m16_transition=30,
    producer=260,reference_work=290,reference_cleanup=299,reference_outer=300,
    prepare=120,full_work=2424,full_cleanup=2429,full_outer=2430,numeric=2400)
CLAIMS=dict(full_29_node_acceptance=False,rtl_execution=False,
    hardware_recipe_acceptance=False,old_pass_inherited=False)

def need(value,reason):
    if not value: raise ValueError('combined same-host M128: '+reason)


def encoded(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def sha(raw): return hashlib.sha256(raw).hexdigest()


def digest(value,n=64): return type(value) is str and len(value)==n and all(c in '0123456789abcdef' for c in value)


def cold_load(name,path,expected):
    path=Path(path)
    need(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)) and
         path.stat().st_nlink==1 and path.stat().st_size<8*1024*1024,'checked source file')
    raw=path.read_bytes();need(sha(raw)==expected,'checked source digest')
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def load_m16(root,pins=None):
    if pins is not None: need(pins['inputs'].get(M16+'run.py')==M16_RUN_SHA,'immutable M16 routine')
    return cold_load('same_host_frozen_m16_parent',Path(root)/M16/'run.py',M16_RUN_SHA)


def load_launcher(root,pins=None):
    if pins is not None: need(pins['inputs'].get(LAUNCH+'launch.py')==LAUNCH_SHA,'immutable producer supervisor')
    return cold_load('same_host_frozen_producer_launcher',Path(root)/LAUNCH/'launch.py',LAUNCH_SHA)


def load_pins(root):
    root=Path(root).resolve(strict=True)
    need(root/OWN==HERE,'single M128 parent source root')
    L=load_launcher(root);value=L.strict(L.safe(HERE/'input-contract.json'))
    need(type(value) is dict and set(value)=={'schema','profile','inputs','composed_sources','budgets','workflow'},'input contract schema')
    need(type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE,'input contract profile')
    need(encoded(value['budgets'])==encoded(BUDGETS),'exact reviewed absolute envelopes')
    need(value['workflow']=='.github/workflows/portable-same-host-m128-launch-r1.yml','exact one-shot workflow')
    for key in ('inputs','composed_sources'):
        sources=value[key];need(type(sources) is dict and 1<=len(sources)<=512,'bounded complete source map')
        for name,expected in sources.items():
            need(type(name) is str and name and '\\' not in name and '\x00' not in name and
                 not Path(name).is_absolute() and all(p not in ('','.','..') for p in name.split('/')) and digest(expected),'source path/hash')
    need(SOURCE_CONTRACT not in value['composed_sources'],'acyclic actual-commit contract')
    fixed={M16+'run.py':M16_RUN_SHA,LAUNCH+'launch.py':LAUNCH_SHA,LAUNCH+'launch-contract.json':CONTRACT_SHA}
    need(all(value['inputs'].get(n)==h for n,h in fixed.items()),'frozen same-host M16 authority sources')
    for name,expected in value['inputs'].items():
        need(sha(L.safe(root/name,8*1024*1024))==expected,'input source drift: '+name)
    L.import_path_guard(root,value['inputs'])
    for name in ('run.py','worker.py'):
        need(value['inputs'].get(OWN+name)==sha(L.safe(HERE/name)),'active parent/worker source')
    return value


def validate_composition(L,pins,root,commit):
    root=Path(root).resolve(strict=True);need(digest(commit,40),'actual triggering commit')
    expected=pins['composed_sources']
    for name,value in expected.items():
        need(sha(L.safe(root/name,8*1024*1024))==value,'composed source drift: '+name)
    raw=L.safe(root/SOURCE_CONTRACT)
    wanted=dict(schema=1,profile=ENTRY_PROFILE,git_head=commit,sources=expected,scope='FRESH_M128_ASSIGNED27_ONLY')
    need(raw==encoded(wanted),'runtime-generated actual-commit contract')
    sources=dict(expected);sources[SOURCE_CONTRACT]=sha(raw)
    L.import_path_guard(root,sources)
    return sources


def read_context(L,path,expected):
    need(digest(expected),'parent context digest')
    raw=L.safe(path,65536);need(sha(raw)==expected,'parent context bytes')
    value=L.strict(raw,65536)
    common={'schema','profile','parent_pid','origin','out','ci','host','attempt_nonce','producer_receipt_sha256',
            'm16_prerequisite_sha256','producer_context_sha256'}
    keys={'same-host-m128-prepare-v1':common|{'deadline_ns'},
          'same-host-m128-run-v1':common|{'source_manifest_sha256','entry_manifest_sha256','started','work_deadline','outer_deadline'}}
    need(type(value) is dict and value.get('profile') in keys and set(value)==keys[value['profile']],'parent context fields')
    need(type(value['schema']) is int and value['schema']==1 and type(value['parent_pid']) is int and value['parent_pid']>1,'parent context schema/PID')
    for key in ('origin','out'):
        p=value[key];need(type(p) is str and Path(p).is_absolute() and '..' not in Path(p).parts,'parent context path')
    ci=value['ci'];need(type(ci) is dict and set(ci)=={'commit','run_id','run_attempt'} and digest(ci['commit'],40) and
        type(ci['run_id']) is str and ci['run_id'].isascii() and ci['run_id'].isdecimal() and int(ci['run_id'])>0 and ci['run_attempt']=='1','first triggering CI identity')
    need(encoded(value['host'])==encoded(L.host()),'current host')
    for key in ('attempt_nonce','producer_receipt_sha256','m16_prerequisite_sha256','producer_context_sha256'):
        need(digest(value[key]),'parent context binding digest')
    if value['profile']=='same-host-m128-prepare-v1':
        need(type(value['deadline_ns']) is int and value['deadline_ns']>time.monotonic_ns(),'prepare deadline')
    else:
        need(all(type(value[k]) in (int,float) and math.isfinite(value[k]) and value[k]>0
                 for k in ('started','work_deadline','outer_deadline')),'finite full deadlines')
        need(value['work_deadline']==value['started']+2424 and value['outer_deadline']==value['started']+2430 and
             value['started']<=time.monotonic()<value['work_deadline'],'unchanged M128 envelope')
        need(digest(value['source_manifest_sha256']) and digest(value['entry_manifest_sha256']),'full source/manifest binding')
    return value


def prerequisite_module(L,pins,root):
    # Source-only private namespace; never execute an ambient package initializer.
    name='_fresh_m128_parent_prerequisite'
    package=types.ModuleType(name);package.__path__=[];sys.modules[name]=package
    for item in ('contract','terminal_m16','prerequisite'):
        relative=ENTRY+item+'.py';qualified=name+'.'+item
        module=cold_load(qualified,Path(root)/relative,pins['inputs'][relative])
        sys.modules[qualified]=module;setattr(package,item,module)
    return package.prerequisite


def source_preflight(root):
    pins=load_pins(root);R=load_m16(root,pins)
    old_pins,L,control=R.source_preflight(root)
    need(all(pins['inputs'].get(n)==h for n,h in old_pins['inputs'].items()),'entire frozen M16 input map retained')
    P=prerequisite_module(L,pins,root)
    driver=cold_load('fresh_m128_parent_driver',Path(root)/PRODUCER/'driver.py',pins['inputs'][PRODUCER+'driver.py'])
    driver.verify_sources(root)
    return pins,L,control,R


def restore_after_m16(L,total_work):
    # R.main returns through protect_cleanup(): all three handlers are ignored.
    # Restore cancellation before any metadata/source read, including failures.
    stop=min(total_work,time.monotonic()+30)
    L.arm(stop)
    return stop



def begin_prepare(L,total_work):
    """Restore work cancellation before source-phase resource/metadata reads."""
    started=time.monotonic();stop=min(started+120,total_work-2430)
    need(stop-started>=40,'full M128 envelope and source preparation reserve')
    work=stop-10;cleanup=stop-1
    L.arm(work)
    return stop,work,cleanup


def resource_reserves(R,L,out):
    return R.resource_reserves(L,out)


def pointer(L,path,limit=2*1024*1024):
    return dict(path=str(Path(path)),sha256=sha(L.safe(path,limit)))


def m16_observation(L,out):
    report=L.strict(L.safe(out/'m16/evidence/stage_exits.json'))
    events=[x for x in report['stages'] if x.get('phase')=='full_m16']
    need(len(events)==1,'one observed current full M16 child')
    e=events[0]
    need(e.get('status')=='PASS' and type(e.get('pid')) is int and e['pid']>1 and
         all(type(e.get(k)) is int and e[k]==0 for k in ('observed_exit_code','final_exit_code')) and
         e.get('owned_group_cleanup_complete') is True,'current full M16 zero exit and cleanup')
    return {k:e[k] for k in ('pid','observed_exit_code','final_exit_code','owned_group_cleanup_complete')}


def seal_m16_prerequisite(L,R,pins,root,out,ci):
    old_pins=R.load_pins(root)
    exact_sources=R.validate_composition(L,old_pins,out/'m16/source',ci['commit'])
    P=prerequisite_module(L,pins,root)
    path,digest_value,m16=P.seal(out/'M16_PREREQUISITE.json',m16_root=out/'m16',parent_pid=os.getpid(),
                               observed_full=m16_observation(L,out),ci=ci)
    need(m16['source_sha256']==exact_sources and path==out/'M16_PREREQUISITE.json','independent complete M16 source map')
    need(m16['host_sha256']==sha(encoded(L.host())),'same host prerequisite')
    P.verify(path,digest_value,m16_root=out/'m16',parent_pid=os.getpid(),ci=ci,
        attempt_nonce=m16['attempt_nonce'],host_sha256=m16['host_sha256'],runtime_identity_sha256=m16['runtime_identity_sha256'])
    return m16,digest_value


def make_producer_context(L,pins,root,out,ci,m16,m16_sha,created_ns):
    need(type(created_ns) is int and created_ns>0,'typed shared reference start')
    up=out/'m16/setup/producer';lib=m16['library']
    return dict(schema=1,profile='qwen2-fresh-same-host-m128-context-v1',parent_pid=os.getpid(),
        root=str(root),workspace=str(out/'producer128'),upstream_workspace=str(up),created_ns=created_ns,
        producer_deadline_ns=created_ns+260*10**9,deadline_ns=created_ns+290*10**9,
        cleanup_deadline_ns=created_ns+299*10**9,receipt_deadline_ns=created_ns+300*10**9,
        attempt_nonce=m16['attempt_nonce'],ci=ci,host=L.host(),driver_sha256=pins['inputs'][PRODUCER+'driver.py'],
        source_lock_sha256=pins['inputs'][PRODUCER+'source-lock.json'],python=str(out/'m16/setup/venv/bin/python'),
        upstream=dict(producer_manifest=pointer(L,up/'PRODUCER_M16.json'),
            qualification=pointer(L,out/'m16/setup/QUALIFICATION.json'),native16_result=pointer(L,up/'native16/RESULT.json'),
            m16_prerequisite=dict(path=str(out/'M16_PREREQUISITE.json'),sha256=m16_sha),
            combined_library=dict(receipt=lib['receipt'],binary={k:lib['binary'][k] for k in ('path','sha256')})))


def qualify_m128(L,pins,root,out,context,context_sha,child,verified):
    for event in (child,verified):
        need(type(event.get('pid')) is int and event['pid']>1 and
             all(type(event.get(k)) is int and event[k]==0 for k in ('observed_exit_code','final_exit_code')) and
             event.get('owned_group_cleanup_complete') is True,'parent-owned producer/verifier completion')
    D=cold_load('fresh_m128_postflight_driver',root/PRODUCER/'driver.py',pins['inputs'][PRODUCER+'driver.py'])
    V=cold_load('fresh_m128_postflight_verifier',root/PRODUCER/'verify.py',pins['inputs'][PRODUCER+'verify.py'])
    sources,lock_sha=D.verify_sources(root)
    raw=L.safe(out/'producer128/PRODUCER_M128.json');value=D.validate_manifest(L.strict(raw));manifest_sha=sha(raw)
    need(value['source_sha256']==sources and value['source_manifest_sha256']==sha(encoded(sources)) and
         value['source_lock_sha256']==lock_sha and value['driver_sha256']==context['driver_sha256'],'exact producer source closure')
    need(value['parent_context_sha256']==context_sha and value['attempt_nonce']==context['attempt_nonce'] and
         encoded(value['ci'])==encoded(context['ci']) and encoded(value['host'])==encoded(context['host']) and
         encoded(value['upstream'])==encoded(context['upstream']),'producer parent/attempt/upstream binding')
    upstream=L.strict(L.safe(out/'m16/setup/producer/PRODUCER_M16.json'))
    need(encoded(value['runtime_identity'])==encoded(upstream['runtime_identity']) and
         encoded(value['runtime_observation'])==encoded(upstream['runtime_observation']),'same M16/M128 current runtime')
    expected=V.verification_receipt(D,value,manifest_sha,context_sha)
    verifier_raw=L.safe(out/'VERIFIED_M128_PRODUCER.json')
    need(encoded(L.strict(verifier_raw))==encoded(expected),'exact independent full-array replay receipt')
    need(sha(L.safe(out/'M128_CONTEXT.json'))==context_sha and L.safe(out/'producer128/PRODUCER_M128.json')==raw,'qualification byte stability')
    q=dict(schema=1,profile='qwen2-fresh-same-host-m128-producer-qualified-v1',status='PASS_FRESH_M128_PRODUCER',
        attempt_nonce=context['attempt_nonce'],ci=context['ci'],host_sha256=sha(encoded(value['host'])),
        runtime_identity_sha256=sha(encoded(value['runtime_identity'])),producer_manifest_sha256=manifest_sha,
        producer_source_manifest_sha256=value['source_manifest_sha256'],parent_context_sha256=context_sha,
        verifier_receipt_sha256=sha(verifier_raw),child_pid=child['pid'],child_exit_code=0,
        owned_group_cleanup_complete=True,original_array_gate_revalidated=True,claims=D.CLAIMS)
    return q,value


def independent_identity(L,pins,root,out,qualified,producer,m16,manifest_sha):
    manifest=L.strict(L.safe(out/'M128_ENTRY_MANIFEST.json'))
    need(sha(L.safe(out/'M128_ENTRY_MANIFEST.json'))==manifest_sha,'entry manifest identity')
    need(manifest['producer_manifest']==dict(path=str(out/'producer128/PRODUCER_M128.json'),sha256=qualified['producer_manifest_sha256']) and
         manifest['producer_receipt']==pointer(L,out/'M128_QUALIFICATION.json') and
         manifest['producer_context']==pointer(L,out/'M128_CONTEXT.json') and
         manifest['m16_prerequisite']==pointer(L,out/'M16_PREREQUISITE.json') and
         manifest['library']==m16['library'],'exact independent manifest/qualification/M16/library bindings')
    I=cold_load('fresh_m128_parent_identity',root/ENTRY/'identity.py',pins['inputs'][ENTRY+'identity.py'])
    return I.terminal_identity(manifest,producer,qualified,m16,manifest_sha)


def terminal_postflight(L,pins,root,out,sources,qualified,q_sha,m16,m16_sha,producer,context,child,fresh_identity):
    work=out/'full_m128';entry=out/'source128'/ENTRY
    validator=cold_load('fresh_m128_parent_terminal',entry/'terminal_validator.py',pins['composed_sources'][ENTRY+'terminal_validator.py'])
    summary=work/'actual/summary.json';snapshot=work/'snapshot/SNAPSHOT.json'
    summary_raw=L.safe(summary,16*1024*1024);snapshot_raw=L.safe(snapshot,16*1024*1024)
    validation=validator.validate_terminal(summary,sha(summary_raw),sources,snapshot,sha(snapshot_raw),fresh_identity=fresh_identity)
    raw=L.safe(work/'CHILD_RESULT.json');value=L.strict(raw)
    expected=dict(schema=1,profile=ENTRY_PROFILE,status='VALIDATED_FRESH_M128_CHILD_RESULT',
        attempt_nonce=qualified['attempt_nonce'],producer_receipt_sha256=q_sha,m16_prerequisite_sha256=m16_sha,
        source_manifest_sha256=sha(encoded(sources)),summary_sha256=sha(summary_raw),snapshot_sha256=sha(snapshot_raw),
        validation=validation,parent_must_authenticate_exit_and_cleanup=True,full_29_node_acceptance=False,
        rtl_execution=False,hardware_recipe_acceptance=False,old_pass_inherited=False)
    need(encoded(value)==encoded(expected),'complete M128 child result/terminal binding')
    need(type(child['pid']) is int and child['pid']>1 and
         all(type(child[k]) is int and child[k]==0 for k in ('observed_exit_code','final_exit_code')) and
         child['owned_group_cleanup_complete'] is True,'actual full M128 completion')
    need(sha(L.safe(out/'M128_QUALIFICATION.json'))==q_sha and sha(L.safe(out/'M16_PREREQUISITE.json'))==m16_sha,'parent prerequisite/qualification drift')
    P=prerequisite_module(L,pins,root)
    P.verify(out/'M16_PREREQUISITE.json',m16_sha,m16_root=out/'m16',parent_pid=os.getpid(),ci=qualified['ci'],
        attempt_nonce=qualified['attempt_nonce'],host_sha256=qualified['host_sha256'],runtime_identity_sha256=qualified['runtime_identity_sha256'],
        current_sources=sources,library=m16['library'])
    need(validate_composition(L,pins,out/'source128',qualified['ci']['commit'])==sources,'M128 terminal source drift')
    need(L.safe(summary,16*1024*1024)==summary_raw and L.safe(snapshot,16*1024*1024)==snapshot_raw,'terminal metadata drift')
    return dict(schema=1,profile=PROFILE,status='PASS_FRESH_SAME_HOST_M128_ASSIGNED27',ci=qualified['ci'],
        attempt_nonce=qualified['attempt_nonce'],producer_receipt_sha256=q_sha,m16_prerequisite_sha256=m16_sha,
        child_result_sha256=sha(raw),child_pid=child['pid'],child_exit_code=0,owned_group_cleanup_complete=True,
        elapsed_seconds=time.monotonic()-context['started'],validation=validation,claims=CLAIMS)


def full_failure_observation(L,pins,root,out,journal,*,sources,run_context,run_context_sha256,receipt_stop):
    """Best-effort failure projection with an untouched one-second receipt reserve."""
    stop=min(receipt_stop,run_context['outer_deadline'])
    if stop-time.monotonic()<2:
        return dict(status='DIAGNOSTIC_ONLY',diagnostic_only=True,acceptance=False,
                    origin_authenticated=False,reason='RECEIPT_RESERVE',traceback=None,progress=None)
    try:
        name=OWN+'full_failure_diagnostic.py'
        D=cold_load('same_host_m128_full_failure_observer',root/name,pins['inputs'][name])
        return D.observe(L,pins,root,out,journal,sources=sources,run_context=run_context,
            run_context_sha256=run_context_sha256,deadline=min(time.monotonic()+1,stop-1))
    except TimeoutError:raise
    except Exception:
        return dict(status='DIAGNOSTIC_ONLY',diagnostic_only=True,acceptance=False,
                    origin_authenticated=False,reason='DIAGNOSTIC_UNAVAILABLE',traceback=None,progress=None)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--out',type=Path)
    parser.add_argument('--cold-source-check',action='store_true');args=parser.parse_args(argv)
    started=time.monotonic();total_stop=started+4920;total_work=started+4910;root=args.root.resolve(strict=True)
    if args.cold_source_check:
        need(args.out is None and sys.flags.isolated and not sys.flags.optimize and sys.dont_write_bytecode,'isolated-B cold-only check')
        pins,L,control,R=source_preflight(root)
        need(not any(n in sys.modules for n in ('numpy','torch','ctypes','transformers','safetensors')),'no numerical cold imports')
        print(encoded(dict(schema=1,status='PASS_COLD_SOURCE_ONLY',inputs=len(pins['inputs']),composed_sources=len(pins['composed_sources'])+1,
            interpreter=list(sys.version_info[:3]),production_interpreter_required=[3,12,15],actual_chain_executed=False)).decode(),end='');return 0
    need(args.out is not None,'fresh output argument')
    out=args.out.absolute()
    need(sys.version_info[:3]==(3,12,15) and sys.flags.isolated and not sys.flags.optimize and sys.dont_write_bytecode,'exact isolated-B normal hosted interpreter')
    need('..' not in out.parts and not out.exists() and not out.is_symlink() and out==out.resolve(strict=False) and
         not out.is_relative_to(root) and not root.is_relative_to(out),'fresh disjoint output')
    pins,L,control,R=source_preflight(root);commit=control.c.admit(os.environ,out);loader=control.c.loader(os.environ,sys.executable)
    ci=dict(commit=commit,run_id=os.environ.get('GITHUB_RUN_ID'),run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'))
    need(type(ci['run_id']) is str and ci['run_id'].isascii() and ci['run_id'].isdecimal() and int(ci['run_id'])>0 and ci['run_attempt']=='1','first actual CI run')
    resources=resource_reserves(R,L,out);out.mkdir(mode=0o700);(out/'evidence').mkdir()
    failure=None;phase='fresh_m16';journal=[];m16_success=False;producer_success=False;full_success=False;diagnostic=None
    sources=full_context=full_sha=None;full_failure_diagnostic=None
    try:
        L.write_new(out/'evidence/source_hashes.json',dict(schema=1,profile=PROFILE,ci=ci,inputs=pins['inputs'],
            composed_sources_template=pins['composed_sources'],dynamic_source_contract=True,claims=CLAIMS))
        need(time.monotonic()+1950+300+120+2430<=total_work,'complete fixed pipeline reserve')
        code=R.main(['--root',str(root),'--out',str(out/'m16')])
        transition_stop=restore_after_m16(L,total_work)
        need(type(code) is int and code==0,'frozen full M16 routine returned zero')
        m16,m16_sha=seal_m16_prerequisite(L,R,pins,root,out,ci);L.remaining(transition_stop);m16_success=True
        L.write_new(out/'evidence/full_m16_summary.json',L.strict(L.safe(out/'m16/evidence/full_m16_summary.json')))
        env=control.clean_environment(out/'m16/setup',loader)
        env.update(GITHUB_RUN_ID=ci['run_id'],OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
        python=out/'m16/setup/venv/bin/python';phase='m128_producer';reference_start=time.monotonic_ns()
        need(reference_start/1e9+300+120+2430<=total_work,'complete reference and full M128 reserve')
        L.arm(reference_start/1e9+260);resource_reserves(R,L,out)
        context=make_producer_context(L,pins,root,out,ci,m16,m16_sha,reference_start)
        context_path=out/'M128_CONTEXT.json';context_sha=L.write_new(context_path,context)
        child=R.owned_phase(L,control,[python,'-I','-B',root/PRODUCER/'driver.py','--root',root,'--workspace',out/'producer128',
            '--deadline-ns',context['deadline_ns'],'--attempt-nonce',context['attempt_nonce'],'--commit',commit,'--run-id',ci['run_id'],
            '--run-attempt','1','--context',context_path,'--context-sha256',context_sha],cwd=root,env=env,log=out/'producer.log',
            work_deadline=context['producer_deadline_ns']/1e9,cleanup_deadline=context['cleanup_deadline_ns']/1e9,journal=journal,phase='fresh_producer')
        L.arm(context['deadline_ns']/1e9)
        manifest_sha=sha(L.safe(out/'producer128/PRODUCER_M128.json'));phase='m128_verifier'
        verified=R.owned_phase(L,control,[python,'-I','-B',root/PRODUCER/'verify.py','--root',root,'--workspace',out/'producer128',
            '--context',context_path,'--context-sha256',context_sha,'--manifest-sha256',manifest_sha,
            '--out',out/'VERIFIED_M128_PRODUCER.json'],cwd=root,env=env,log=out/'m128_verifier.log',
            work_deadline=context['deadline_ns']/1e9,cleanup_deadline=context['cleanup_deadline_ns']/1e9,journal=journal,phase='independent_m128_verifier')
        control.arm_receipt_deadline(context['receipt_deadline_ns']/1e9)
        qualified,producer=qualify_m128(L,pins,root,out,context,context_sha,child,verified)
        q_sha=L.write_new(out/'M128_QUALIFICATION.json',qualified);L.remaining(context['receipt_deadline_ns']/1e9);producer_success=True
        L.write_new(out/'evidence/producer_summary.json',dict(schema=1,profile=PROFILE,status='PASS_FRESH_M128_PRODUCER',ci=ci,
            attempt_nonce=qualified['attempt_nonce'],producer_manifest_sha256=qualified['producer_manifest_sha256'],
            producer_qualification_sha256=q_sha,verifier_receipt_sha256=qualified['verifier_receipt_sha256'],
            m16_prerequisite_sha256=m16_sha,owned_groups_cleanup_complete=True,stages=journal,claims=CLAIMS))
        phase='source_and_admission';prep_stop,prep_work,prep_cleanup=begin_prepare(L,total_work)
        resource_reserves(R,L,out)
        common=dict(schema=1,parent_pid=os.getpid(),origin=str(root),out=str(out),ci=ci,host=L.host(),
            attempt_nonce=qualified['attempt_nonce'],producer_receipt_sha256=q_sha,m16_prerequisite_sha256=m16_sha,producer_context_sha256=context_sha)
        prepare_context=dict(common,profile='same-host-m128-prepare-v1',deadline_ns=int(prep_work*1e9))
        prep_path=out/'M128_PREPARE_CONTEXT.json';prep_sha=L.write_new(prep_path,prepare_context)
        R.owned_phase(L,control,['/usr/bin/git','worktree','add','--detach',out/'source128',commit],cwd=root,env=env,log=out/'m128_worktree.log',
            work_deadline=prep_work,cleanup_deadline=prep_cleanup,journal=journal,phase='m128_git_worktree')
        for mode in ('compose','seal'):
            R.owned_phase(L,control,[python,'-I','-B',root/OWN/'worker.py',mode,'--origin',root,'--out',out,'--commit',commit,
                '--context',prep_path,'--context-sha256',prep_sha],cwd=root,env=env,log=out/('m128_'+mode+'.log'),
                work_deadline=prep_work,cleanup_deadline=prep_cleanup,journal=journal,phase='m128_'+mode)
        L.arm(prep_stop);sources=validate_composition(L,pins,out/'source128',commit)
        sealed=L.strict(L.safe(out/'M128_SEALED.json'));entry_sha=sha(L.safe(out/'M128_ENTRY_MANIFEST.json'))
        identity=independent_identity(L,pins,root,out,qualified,producer,m16,entry_sha)
        expected_seal=dict(schema=1,profile=ENTRY_PROFILE,entry_manifest_sha256=entry_sha,producer_receipt_sha256=q_sha,
            source_manifest_sha256=sha(encoded(sources)),attempt_nonce=qualified['attempt_nonce'],ci=ci,
            m16_prerequisite_sha256=m16_sha,producer_context_sha256=context_sha,terminal_identity=identity,
            terminal_identity_sha256=sha(encoded(identity)))
        need(encoded(sealed)==encoded(expected_seal),'parent-independent sealed identity')
        need(sha(L.safe(prep_path))==prep_sha and sha(L.safe(context_path))==context_sha,'preparation context drift')
        load_pins(root);phase='full_m128';full_start=time.monotonic();need(full_start+2430<=total_work,'complete full M128 envelope required')
        full_context=dict(common,profile='same-host-m128-run-v1',source_manifest_sha256=sha(encoded(sources)),
            entry_manifest_sha256=entry_sha,started=full_start,work_deadline=full_start+2424,outer_deadline=full_start+2430)
        full_path=out/'M128_RUN_CONTEXT.json';full_sha=L.write_new(full_path,full_context)
        full_child=R.owned_phase(L,control,[python,'-I','-B',root/OWN/'worker.py','run','--origin',root,'--out',out,'--commit',commit,
            '--context',full_path,'--context-sha256',full_sha],cwd=out/'source128',env=env,log=out/'full_m128.log',
            work_deadline=full_start+2424,cleanup_deadline=full_start+2429,journal=journal,phase='full_m128')
        control.arm_receipt_deadline(full_start+2430)
        receipt=terminal_postflight(L,pins,root,out,sources,qualified,q_sha,m16,m16_sha,producer,full_context,full_child,identity)
        need(sha(L.safe(full_path))==full_sha,'full M128 context drift')
        L.write_new(out/'evidence/full_m128_summary.json',receipt);L.remaining(full_start+2430);full_success=True;phase='complete'
    except BaseException as error: failure=error
    finally:
        control.protect_cleanup()
        try:
            control.arm_receipt_deadline(total_stop);L.remaining(total_stop)
            if failure is not None and phase=='m128_producer' and total_stop-time.monotonic()>=2:
                diagnostic=L.producer_failure_diagnostic(root,out,{'sources':pins['inputs']},journal,
                    deadline=min(time.monotonic()+1,total_stop-1))
                L.remaining(total_stop)
            if failure is not None and phase=='full_m128' and full_context is not None and sources is not None and full_sha is not None:
                full_failure_diagnostic=full_failure_observation(L,pins,root,out,journal,sources=sources,
                    run_context=full_context,run_context_sha256=full_sha,receipt_stop=total_stop)
                L.remaining(total_stop)
            if (out/'m16/evidence/summary.json').is_file():
                L.write_new(out/'evidence/m16_attempt_summary.json',L.strict(L.safe(out/'m16/evidence/summary.json')))
            L.write_new(out/'evidence/stage_exits.json',dict(schema=1,profile=PROFILE,ci=ci,stages=journal,
                m16_stage_exits_sha256=sha(L.safe(out/'m16/evidence/stage_exits.json')) if (out/'m16/evidence/stage_exits.json').is_file() else None))
            L.write_new(out/'evidence/summary.json',dict(schema=1,profile=PROFILE,ci=ci,
                status='PASS_FRESH_SAME_HOST_M128_ASSIGNED27' if full_success and failure is None else 'FAILED_SAME_HOST_M128_ATTEMPT',
                phase=phase,full_m16_prerequisite_pass=m16_success,producer128_qualified=producer_success,
                full_m128_assigned27_pass=full_success and failure is None,
                failure_kind=None if failure is None else type(failure).__name__,elapsed_seconds=time.monotonic()-started,
                resources_before_setup=resources,owned_groups_cleanup_complete=bool(journal) and all(x['owned_group_cleanup_complete'] for x in journal),
                producer_failure_observation=diagnostic,full_m128_failure_diagnostic=full_failure_diagnostic,claims=CLAIMS))
        except BaseException as error:
            if failure is None: failure=error
        finally: control.protect_cleanup()
    if failure is not None: raise failure
    need(full_success,'full same-host M128 incomplete');return 0


if __name__=='__main__':raise SystemExit(main())
