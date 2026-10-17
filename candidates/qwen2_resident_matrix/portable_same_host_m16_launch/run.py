"""One same-host producer then full-M16 attempt; source proposal until reviewed.

The frozen producer supervisor runs in this process. All later command phases
reuse its reviewed retained-leader helper. No historical PASS is an input.
External caller: TERM at 1940 seconds, KILL ten seconds later. No retries.
"""
import argparse
import hashlib
import importlib.util
import importlib.machinery
import json
import math
import os
from pathlib import Path
import resource
import signal
import sys
import time

HERE=Path(__file__).resolve().parent
OWN='candidates/qwen2_resident_matrix/portable_same_host_m16_launch/'
LAUNCH='candidates/qwen2_resident_matrix/portable_official_producer_launch/'
ENTRY='candidates/qwen2_resident_matrix/attention_packed_m16_same_host/'
SOURCE_CONTRACT=ENTRY+'SOURCE_CONTRACT.json'
PROFILE='qwen2-fresh-same-host-m16-combined-v1'
ENTRY_PROFILE='qwen2-public-pv16-packed-m16-same-host-v1'
TOTAL_SECONDS=1950
WORK_SECONDS=1940
PREPARE_SECONDS=120
FULL_WORK_SECONDS=924
FULL_CLEANUP_SECONDS=929
FULL_OUTER_SECONDS=930
LAUNCH_SHA = 'd7ac40bba0fc21b03b19dcdcd886cfffe04d94c04bf8a8d37efc77067c1d5b42'
CONTRACT_SHA = '00bb4ed7c6264d7245ad6b5715b35ece73f62490c6dc40d37826b7860504c628'
CLAIMS=dict(full_29_node_acceptance=False,full_m128_acceptance=False,rtl_execution=False,
            hardware_recipe_acceptance=False,old_pass_inherited=False)


def need(value,reason):
    if not value: raise ValueError('combined same-host M16: '+reason)


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


def load_launcher(root,pins=None):
    if pins is not None: need(pins['inputs'].get(LAUNCH+'launch.py')==LAUNCH_SHA,'frozen launcher pin')
    return cold_load('same_host_frozen_launcher',Path(root)/LAUNCH/'launch.py',LAUNCH_SHA)


def load_pins(root):
    root=Path(root).resolve(strict=True)
    need(root/OWN==HERE,'single combined source root')
    L=load_launcher(root)
    value=L.strict(L.safe(HERE/'input-contract.json'))
    need(type(value) is dict and set(value)=={'schema','profile','inputs','composed_sources','budgets','workflow'},'input contract schema')
    need(type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE,'input contract profile')
    need(encoded(value['budgets'])==encoded(dict(total=1950,outer_term=1940,setup=900,prepare=120,
        full_work=924,full_cleanup=929,full_outer=930,numeric=900)),'unchanged bounded budgets')
    need(value['workflow']=='.github/workflows/portable-same-host-m16-launch-r1.yml','exact one-shot workflow')
    for map_name in ('inputs','composed_sources'):
        sources=value[map_name];need(type(sources) is dict and sources,'complete source map')
        for name,expected in sources.items():
            need(type(name) is str and '\\' not in name and '\x00' not in name and not Path(name).is_absolute() and
                 all(p not in ('','.','..') for p in name.split('/')) and digest(expected),'source path/hash')
    need(SOURCE_CONTRACT not in value['composed_sources'],'actual commit contract must be regenerated')
    need(value['inputs'].get(LAUNCH+'launch.py')==LAUNCH_SHA and
         value['inputs'].get(LAUNCH+'launch-contract.json')==CONTRACT_SHA,'frozen producer launcher identity')
    for name,expected in value['inputs'].items():
        need(sha(L.safe(root/name,8*1024*1024))==expected,'input source drift: '+name)
    L.import_path_guard(root,value['inputs'])
    for name in ('run.py','worker.py'):
        need(value['inputs'].get(OWN+name)==sha(L.safe(HERE/name)),'active combined source')
    return value


def validate_composition(L,pins,root,commit):
    root=Path(root).resolve(strict=True)
    need(digest(commit,40),'actual triggering commit')
    expected=pins['composed_sources']
    for name,digest_value in expected.items():
        need(sha(L.safe(root/name,8*1024*1024))==digest_value,'composed source drift: '+name)
    raw=L.safe(root/SOURCE_CONTRACT)
    contract=L.strict(raw)
    wanted=dict(schema=1,profile=ENTRY_PROFILE,git_head=commit,sources=expected,scope='FRESH_M16_ASSIGNED27_ONLY')
    need(encoded(contract)==encoded(wanted),'runtime-generated actual-commit source contract')
    sources=dict(expected);sources[SOURCE_CONTRACT]=sha(raw)
    L.import_path_guard(root,sources)
    return sources


def read_context(L,path,expected):
    need(digest(expected),'parent context digest')
    raw=L.safe(path,65536);need(sha(raw)==expected,'parent context bytes')
    value=L.strict(raw,65536)
    common={'schema','profile','parent_pid','origin','out','ci','host','attempt_nonce','producer_receipt_sha256'}
    keys={'same-host-m16-prepare-v1':common|{'deadline_ns'},
          'same-host-m16-run-v1':common|{'source_manifest_sha256','entry_manifest_sha256','started','work_deadline','outer_deadline'}}
    need(type(value) is dict and value.get('profile') in keys and set(value)==keys[value['profile']],'parent context fields')
    need(type(value['schema']) is int and value['schema']==1 and type(value['parent_pid']) is int and value['parent_pid']>1,'parent context schema/PID')
    for key in ('origin','out'):
        p=value[key];need(type(p) is str and Path(p).is_absolute() and '..' not in Path(p).parts,'parent context path')
    ci=value['ci'];need(type(ci) is dict and set(ci)=={'commit','run_id','run_attempt'} and digest(ci['commit'],40) and
        type(ci['run_id']) is str and ci['run_id'].isascii() and ci['run_id'].isdecimal() and int(ci['run_id'])>0 and ci['run_attempt']=='1','parent context CI')
    need(digest(value['attempt_nonce']) and digest(value['producer_receipt_sha256']) and encoded(value['host'])==encoded(L.host()),'parent attempt/host')
    if value['profile']=='same-host-m16-prepare-v1':
        need(type(value['deadline_ns']) is int and value['deadline_ns']>time.monotonic_ns(),'prepare deadline')
    else:
        need(all(type(value[k]) in (int,float) and math.isfinite(value[k]) and value[k]>0 for k in ('started','work_deadline','outer_deadline')),'full deadlines')
        need(value['work_deadline']==value['started']+924 and value['outer_deadline']==value['started']+930 and
             value['started']<=time.monotonic()<value['work_deadline'],'full fixed envelope')
        need(digest(value['source_manifest_sha256']) and digest(value['entry_manifest_sha256']),'full source/admission digest')
    return value


def timing_seconds(value):
    # Serialization ceiling only; never a work budget or acceptance threshold.
    return type(value) in (int,float) and 0<=value<=2**53 and math.isfinite(value)


def phase_snapshot():
    """Parent-only seconds; RUSAGE_CHILDREN accounts for already reaped children.

    Descendants are included only to the extent their usage is propagated by
    waited-for children. This is not per-process or per-edge attribution.
    """
    try:
        wall=time.monotonic();usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        values=(wall,usage.ru_utime,usage.ru_stime)
        return tuple(float(v) for v in values) if all(timing_seconds(v) for v in values) else None
    except TimeoutError: raise
    except Exception: return None


def unavailable_phase_timing(reason):
    return dict(schema=1,diagnostic_only=True,acceptance=False,scope='PARENT_RUSAGE_CHILDREN_DELTA',
        status='UNAVAILABLE',reason=reason,wall_seconds=None,
        reaped_children_user_cpu_seconds=None,reaped_children_system_cpu_seconds=None)


def phase_timing(before,event):
    # Do not measure an unobserved or incompletely cleaned ownership boundary.
    if type(event['observed_exit_code']) is not int:
        return unavailable_phase_timing('EXIT_UNOBSERVED')
    if event['owned_group_cleanup_complete'] is not True:
        return unavailable_phase_timing('CLEANUP_INCOMPLETE')
    if type(before) is not tuple or len(before)!=3 or not all(timing_seconds(v) for v in before):
        return unavailable_phase_timing('SNAPSHOT_UNAVAILABLE')
    after=phase_snapshot()
    if type(after) is not tuple or len(after)!=3 or not all(timing_seconds(v) for v in after):
        return unavailable_phase_timing('SNAPSHOT_UNAVAILABLE')
    delta=tuple(end-start for start,end in zip(before,after))
    if not all(timing_seconds(v) for v in delta):
        return unavailable_phase_timing('INVALID_DELTA')
    result=unavailable_phase_timing(None)
    result.update(status='AVAILABLE',wall_seconds=delta[0],
        reaped_children_user_cpu_seconds=delta[1],reaped_children_system_cpu_seconds=delta[2])
    return result


def owned_phase(L,control,argv,*,cwd,env,log,work_deadline,cleanup_deadline,journal,phase):
    """Reviewed helper ownership, with one absolute phase and no timer restart."""
    owner={'process':None,'identity':None};failure=None;code=None;cleaned=False;cleanup_failed=False
    before=None
    event=dict(phase=phase,pid=None,observed_exit_code=None,final_exit_code=None,owned_group_cleanup_complete=False,status='NOT_STARTED')
    journal.append(event)
    try:
        L.arm(work_deadline)
        before=phase_snapshot()
        with Path(log).open('xb') as stream:
            control.spawn_owned(owner,['-I','-B','-c',L.EXEC,*map(str,argv)],cwd=cwd,stdout=stream,env=env)
            event.update(pid=owner['process'].pid,status='RUNNING')
            code=control.observe_exit(owner['process'].pid,work_deadline);event['observed_exit_code']=code
            need(type(code) is int and code==0,'owned phase nonzero exit')
    except BaseException as error: failure=error
    finally:
        try: cleaned=L.finish_owned(control,owner,cleanup_deadline,cancel=failure is not None)
        except BaseException as error:
            cleanup_failed=True
            if failure is None: failure=error
        process=owner['process']
        if process is not None:
            event['pid']=process.pid
            if type(process.returncode) is int: event['final_exit_code']=process.returncode if process.returncode>=0 else 128-process.returncode
        event['owned_group_cleanup_complete']=cleaned
        try:
            if before is not None and type(event['observed_exit_code']) is int and cleaned is True:
                if time.monotonic()>=cleanup_deadline:
                    event['timing_diagnostic']=unavailable_phase_timing('DEADLINE_EXPIRED')
                    if failure is None: failure=TimeoutError('absolute phase measurement deadline')
                else:
                    # finish_owned disabled the work alarm for cleanup. Reuse only
                    # the same absolute cleanup boundary for this added read.
                    control.arm_receipt_deadline(cleanup_deadline);L.remaining(cleanup_deadline)
                    event['timing_diagnostic']=phase_timing(before,event)
                    L.remaining(cleanup_deadline)
            else: event['timing_diagnostic']=phase_timing(before,event)
        except TimeoutError as error:
            event['timing_diagnostic']=unavailable_phase_timing('INTERRUPTED')
            if failure is None: failure=error
        except Exception:
            event['timing_diagnostic']=unavailable_phase_timing('MEASUREMENT_UNAVAILABLE')
        event['status']='CLEANUP_FAILED' if cleanup_failed else 'TIMEOUT' if isinstance(failure,TimeoutError) else 'FAILED' if failure else 'PASS'
    if failure is not None: raise failure
    need(cleaned,'owned phase cleanup')
    return event


def terminal_postflight(L,pins,out,sources,qualified,qualified_sha,full_context,child):
    worktree=out/'source';workspace=out/'full_m16'
    path=worktree/ENTRY/'terminal_validator.py'
    validator=L.load_checked('same_host_independent_terminal',path,pins['composed_sources'][ENTRY+'terminal_validator.py'])
    summary=workspace/'actual/summary.json';snapshot=workspace/'snapshot/SNAPSHOT.json'
    summary_raw=L.safe(summary,4*1024*1024);snapshot_raw=L.safe(snapshot,4*1024*1024)
    validation=validator.validate_terminal(summary,sha(summary_raw),sources,snapshot,sha(snapshot_raw))
    raw=L.safe(workspace/'CHILD_RESULT.json')
    value=L.strict(raw)
    expected=dict(schema=1,profile=ENTRY_PROFILE,status='VALIDATED_FRESH_M16_CHILD_RESULT',
        attempt_nonce=qualified['attempt_nonce'],producer_receipt_sha256=qualified_sha,
        source_manifest_sha256=sha(encoded(sources)),summary_sha256=sha(summary_raw),snapshot_sha256=sha(snapshot_raw),
        validation=validation,parent_must_authenticate_exit_and_cleanup=True,full_29_node_acceptance=False,
        rtl_execution=False,hardware_recipe_acceptance=False,old_pass_inherited=False)
    need(encoded(value)==encoded(expected),'full child result/terminal binding')
    need(type(child['pid']) is int and child['pid']>1 and
         type(child['observed_exit_code']) is int and child['observed_exit_code']==0 and
         type(child['final_exit_code']) is int and child['final_exit_code']==0 and
         child['owned_group_cleanup_complete'] is True,'actual full child completion')
    need(sha(L.safe(out/'setup/QUALIFICATION.json'))==qualified_sha,'producer qualification drift')
    need(validate_composition(L,pins,worktree,qualified['ci']['commit'])==sources,'terminal source drift')
    need(L.safe(summary,4*1024*1024)==summary_raw and L.safe(snapshot,4*1024*1024)==snapshot_raw,'terminal metadata drift')
    return dict(schema=1,profile=PROFILE,status='PASS_FRESH_SAME_HOST_M16_ASSIGNED27',ci=qualified['ci'],
        attempt_nonce=qualified['attempt_nonce'],producer_receipt_sha256=qualified_sha,child_result_sha256=sha(raw),
        child_pid=child['pid'],child_exit_code=0,owned_group_cleanup_complete=True,
        elapsed_seconds=time.monotonic()-full_context['started'],validation=validation,claims=CLAIMS)



def full_failure_observation(L,pins,root,out,journal,*,sources,run_context,run_context_sha256,receipt_stop):
    """Best-effort failure projection with an untouched one-second receipt reserve."""
    stop=min(receipt_stop,run_context['outer_deadline'])
    if stop-time.monotonic()<2:
        return dict(status='DIAGNOSTIC_ONLY',diagnostic_only=True,acceptance=False,
                    origin_authenticated=False,reason='RECEIPT_RESERVE',traceback=None,progress=None)
    try:
        name=OWN+'full_failure_diagnostic.py'
        D=cold_load('same_host_full_failure_observer',root/name,pins['inputs'][name])
        return D.observe(L,pins,root,out,journal,sources=sources,run_context=run_context,
            run_context_sha256=run_context_sha256,deadline=min(time.monotonic()+1,stop-1))
    except TimeoutError:raise
    except Exception:
        return dict(status='DIAGNOSTIC_ONLY',diagnostic_only=True,acceptance=False,
                    origin_authenticated=False,reason='DIAGNOSTIC_UNAVAILABLE',traceback=None,progress=None)


def resource_reserves(L,out):
    value=L.resource_observation(out)
    minimum=dict(cpu_affinity=4,available_memory_bytes=8*1024**3,available_disk_bytes=8*1024**3)
    need(type(value) is dict and set(value)==set(minimum) and
         all(type(value[k]) is int and value[k]>=floor for k,floor in minimum.items()),'full-M16 resource reserves')
    return value


def source_preflight(root):
    """The same stdlib-only checked loaders used by cold CLI and production."""
    pins=load_pins(root);L=load_launcher(root,pins)
    launch_contract=L.load_contract(root);control=L.helper(root,launch_contract)
    control.c.validate(root,root/L.CONSUMER)
    return pins,L,control


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--out',type=Path)
    parser.add_argument('--cold-source-check',action='store_true')
    args=parser.parse_args(argv)
    started=time.monotonic();total_stop=started+1950;total_work=started+1940
    root=args.root.resolve(strict=True)
    if args.cold_source_check:
        need(args.out is None and sys.flags.isolated and not sys.flags.optimize and sys.dont_write_bytecode,'isolated-B cold-only source check')
        pins,L,control=source_preflight(root)
        need(not any(name in sys.modules for name in ('torch','numpy','ctypes','transformers','safetensors')),'no numerical cold imports')
        print(encoded(dict(schema=1,status='PASS_COLD_SOURCE_ONLY',inputs=len(pins['inputs']),composed_sources=len(pins['composed_sources'])+1,
            interpreter=list(sys.version_info[:3]),production_interpreter_required=[3,12,15],actual_chain_executed=False)).decode(),end='')
        return 0
    need(args.out is not None,'fresh output argument required')
    out=args.out.absolute()
    need(sys.version_info[:3]==(3,12,15) and sys.flags.isolated and not sys.flags.optimize and sys.dont_write_bytecode,'exact isolated-B normal hosted interpreter')
    need('..' not in out.parts and not out.exists() and not out.is_symlink() and out==out.resolve(strict=False) and
         not out.is_relative_to(root) and not root.is_relative_to(out),'fresh disjoint parent output')
    pins,L,control=source_preflight(root)
    commit=control.c.admit(os.environ,out);loader=control.c.loader(os.environ,sys.executable)
    ci=dict(commit=commit,run_id=os.environ.get('GITHUB_RUN_ID'),run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'))
    need(type(ci['run_id']) is str and ci['run_id'].isascii() and ci['run_id'].isdecimal() and int(ci['run_id'])>0 and ci['run_attempt']=='1','actual first CI run')
    resources=resource_reserves(L,out);resources_after=None
    out.mkdir(mode=0o700);(out/'evidence').mkdir()
    failure=None;phase='fresh_producer';journal=[];producer_success=False;full_success=False;full_receipt=None
    sources=full_context=full_sha=None;full_failure_diagnostic=None
    try:
        L.write_new(out/'evidence/source_hashes.json',dict(schema=1,profile=PROFILE,ci=ci,inputs=pins['inputs'],
            composed_sources_template=pins['composed_sources'],dynamic_source_contract=True,claims=CLAIMS))
        # Keep the reviewed setup supervisor at the true parent level. A second
        # outer PGID supervisor could kill it before it reaps nested compiler groups.
        need(L.main(['--root',str(root),'--out',str(out/'setup')])==0,'fresh producer supervisor returned zero')
        qualified_raw=L.safe(out/'setup/QUALIFICATION.json');qualified=L.strict(qualified_raw);qualified_sha=sha(qualified_raw)
        need(qualified['profile']==L.PROFILE and qualified['status']=='PASS_FRESH_M16_PRODUCER' and
             encoded(qualified['ci'])==encoded(ci) and qualified['owned_group_cleanup_complete'] is True and
             type(qualified['child_exit_code']) is int and qualified['child_exit_code']==0,'current parent-created producer qualification')
        producer_success=True
        producer_summary=L.strict(L.safe(out/'setup/evidence/summary.json'))
        need(producer_summary['observed_complete'] is True and producer_summary['owned_groups_cleanup_complete'] is True,'all producer stage cleanup')
        journal.extend(producer_summary['stages'])
        L.write_new(out/'evidence/producer_summary.json',producer_summary)
        env=control.clean_environment(out/'setup',loader)
        env.update(GITHUB_RUN_ID=ci['run_id'],OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
        python=out/'setup/venv/bin/python'
        phase='source_and_admission';resources_after=resource_reserves(L,out);prep_start=time.monotonic()
        prep_stop=min(prep_start+120,total_work-930)
        need(prep_stop-prep_start>=20,'full 930-second phase reserve')
        prep_work=prep_stop-10;prep_cleanup=prep_stop-1
        prepare_context=dict(schema=1,profile='same-host-m16-prepare-v1',parent_pid=os.getpid(),origin=str(root),out=str(out),
            ci=ci,host=L.host(),attempt_nonce=qualified['attempt_nonce'],producer_receipt_sha256=qualified_sha,deadline_ns=int(prep_work*1e9))
        context=out/'PREPARE_CONTEXT.json';context_sha=L.write_new(context,prepare_context)
        owned_phase(L,control,['/usr/bin/git','worktree','add','--detach',out/'source',commit],cwd=root,env=env,
            log=out/'worktree.log',work_deadline=prep_work,cleanup_deadline=prep_cleanup,journal=journal,phase='fresh_git_worktree')
        for mode in ('compose','seal'):
            owned_phase(L,control,[python,'-I','-B',root/OWN/'worker.py',mode,'--origin',root,'--out',out,'--commit',commit,
                '--context',context,'--context-sha256',context_sha],cwd=root,env=env,log=out/(mode+'.log'),
                work_deadline=prep_work,cleanup_deadline=prep_cleanup,journal=journal,phase=mode)
        L.arm(prep_stop)
        sources=validate_composition(L,pins,out/'source',commit)
        sealed=L.strict(L.safe(out/'SEALED.json'))
        expected_seal=dict(schema=1,profile=ENTRY_PROFILE,entry_manifest_sha256=sha(L.safe(out/'ENTRY_MANIFEST.json')),
            producer_receipt_sha256=qualified_sha,source_manifest_sha256=sha(encoded(sources)),attempt_nonce=qualified['attempt_nonce'],ci=ci)
        need(encoded(sealed)==encoded(expected_seal),'sealed current admission')
        need(sha(L.safe(context))==context_sha and sha(L.safe(out/'setup/QUALIFICATION.json'))==qualified_sha,'preparation identity drift')
        load_pins(root)
        phase='full_m16';full_start=time.monotonic()
        need(full_start+930<=total_work,'complete full-M16 envelope required')
        full_context=dict(schema=1,profile='same-host-m16-run-v1',parent_pid=os.getpid(),origin=str(root),out=str(out),
            ci=ci,host=L.host(),attempt_nonce=qualified['attempt_nonce'],producer_receipt_sha256=qualified_sha,
            source_manifest_sha256=sha(encoded(sources)),entry_manifest_sha256=sealed['entry_manifest_sha256'],
            started=full_start,work_deadline=full_start+924,outer_deadline=full_start+930)
        full_path=out/'RUN_CONTEXT.json';full_sha=L.write_new(full_path,full_context)
        child=owned_phase(L,control,[python,'-I','-B',root/OWN/'worker.py','run','--origin',root,'--out',out,'--commit',commit,
            '--context',full_path,'--context-sha256',full_sha],cwd=out/'source',env=env,log=out/'full_m16.log',
            work_deadline=full_start+924,cleanup_deadline=full_start+929,journal=journal,phase='full_m16')
        control.arm_receipt_deadline(full_start+930)
        full_receipt=terminal_postflight(L,pins,out,sources,qualified,qualified_sha,full_context,child)
        need(sha(L.safe(full_path))==full_sha,'full context drift')
        L.write_new(out/'evidence/full_m16_summary.json',full_receipt)
        L.remaining(full_start+930)
        full_success=True;phase='complete'
    except BaseException as error: failure=error
    finally:
        control.protect_cleanup()
        try:
            control.arm_receipt_deadline(total_stop);L.remaining(total_stop)
            if failure is not None and phase=='full_m16' and full_context is not None and sources is not None and full_sha is not None:
                full_failure_diagnostic=full_failure_observation(L,pins,root,out,journal,sources=sources,
                    run_context=full_context,run_context_sha256=full_sha,receipt_stop=total_stop)
                L.remaining(total_stop)
            if not (out/'evidence/producer_summary.json').exists() and (out/'setup/evidence/summary.json').is_file():
                summary=L.strict(L.safe(out/'setup/evidence/summary.json'));L.write_new(out/'evidence/producer_summary.json',summary)
                if not journal: journal.extend(summary['stages'])
            L.write_new(out/'evidence/stage_exits.json',dict(schema=1,profile=PROFILE,ci=ci,stages=journal))
            L.write_new(out/'evidence/summary.json',dict(schema=1,profile=PROFILE,
                status='PASS_FRESH_SAME_HOST_M16_ASSIGNED27' if full_success and failure is None else 'FAILED_SAME_HOST_M16_ATTEMPT',
                phase=phase,ci=ci,producer_qualified=producer_success,full_m16_assigned27_pass=full_success and failure is None,
                failure_kind=None if failure is None else type(failure).__name__,elapsed_seconds=time.monotonic()-started,
                full_m16_failure_diagnostic=full_failure_diagnostic,
                resources_before_setup=resources,resources_after_setup=resources_after,
                owned_groups_cleanup_complete=bool(journal) and all(x['owned_group_cleanup_complete'] for x in journal),claims=CLAIMS))
        except BaseException as error:
            if failure is None: failure=error
        finally: control.protect_cleanup()
    if failure is not None: raise failure
    need(full_success,'full same-host M16 not complete')
    return 0


if __name__=='__main__': raise SystemExit(main())
