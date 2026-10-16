"""One private native16→128 validation attempt; original Public is never invoked."""
from __future__ import annotations
import argparse
import hashlib
import subprocess
import json
import math
import os
import platform
import re
from pathlib import Path
import signal
import sys
import time

from candidates.qwen2_resident_matrix.raw_kv_public_fresh import assets, setup
from candidates.qwen2_resident_matrix.raw_kv_public_m128_run import run_ci as prior
from . import runtime

ROOT=Path(__file__).resolve().parents[3]
MODULE='candidates.qwen2_resident_matrix.raw_kv_native_qkv_run.run_ci'
SOURCE='candidates/qwen2_resident_matrix/raw_kv_native_qkv_run/run_ci.py'
IMPORTED_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
PHASE_MODULE='candidates.qwen2_resident_matrix.raw_kv_native_qkv_run.phase'
TOTAL=900
LIMITS={'preflight':20,'environment':120,'acquisition':420,'kernel':30,'native16':60,'native128':120}
OUTPUTS=('summary.json','progress.json','source_hashes.json')
PASS='PASS_NATIVE_QKV_M16_M128'
PHASES=('preflight','cpu_qualification','clone','compose','environment','acquisition','kernel','native16','native128','finalize')


def need(ok):
    if not ok:raise ValueError('native_validation_contract')


CPU_FLAGS=('avx512f','avx512vl','avx512bw','avx512dq','fma')
CPU_LIMIT=2*1024*1024
CPU_SECONDS=5


class CpuUnsuitable(Exception):
    """Only well-formed pre-package hardware ineligibility permits placement two."""


def cpu_eligibility(raw,*,system,machine,override_absent):
    need(system=='Linux' and machine=='x86_64' and override_absent is True)
    need(type(raw) is bytes and 0<len(raw)<=CPU_LIMIT)
    blocks=re.split(r'\n[ \t]*\n(?:[ \t]*\n)*',raw.decode('ascii').strip())
    need(0<len(blocks)<=4096)
    seen=set();common=None
    for block in blocks:
        fields={}
        for line in block.splitlines():
            need(':' in line)
            key,value=line.split(':',1);key=key.strip();value=value.strip()
            need(key not in fields);fields[key]=value
        identifier=fields.get('processor','')
        need(re.fullmatch(r'0|[1-9][0-9]*',identifier) is not None and identifier not in seen)
        seen.add(identifier)
        need('flags' in fields)
        tokens=fields['flags'].split()
        need(0<len(tokens)<=4096 and len(tokens)==len(set(tokens)) and
             all(re.fullmatch(r'[a-z0-9_]{1,64}',token) is not None for token in tokens))
        flags=set(tokens);common=flags if common is None else common & flags
    flags={name:name in common for name in CPU_FLAGS}
    return dict(schema=1,status='ELIGIBLE_FOR_BACKEND_CHECK' if all(flags.values()) else 'CPU_UNSUITABLE',
                flags=flags,processor_records=len(seen),eligibility_only=True,backend_qualified=False)


def validate_cpu_eligibility(value):
    need(type(value) is dict and set(value)=={'schema','status','flags','processor_records','eligibility_only','backend_qualified'})
    need(type(value['schema']) is int and value['schema']==1 and value['eligibility_only'] is True and
         value['backend_qualified'] is False and type(value['processor_records']) is int and 1<=value['processor_records']<=4096)
    need(type(value['flags']) is dict and set(value['flags'])==set(CPU_FLAGS) and
         all(type(v) is bool for v in value['flags'].values()))
    need(value['status']==('ELIGIBLE_FOR_BACKEND_CHECK' if all(value['flags'].values()) else 'CPU_UNSUITABLE'))
    return value


def qualify_cpu(summary):
    summary['phase']='cpu_qualification'
    with open('/proc/cpuinfo','rb') as stream:raw=stream.read(CPU_LIMIT+1)
    result=cpu_eligibility(raw,system=platform.system(),machine=platform.machine(),
                           override_absent='ATEN_CPU_CAPABILITY' not in os.environ)
    summary['cpu_eligibility']=validate_cpu_eligibility(result)
    if result['status']=='CPU_UNSUITABLE':raise CpuUnsuitable()
    return result


def run_cpu_qualification(summary,budget):
    end=min(budget.end,time.monotonic_ns()+CPU_SECONDS*10**9)
    budget.arm(end)
    try:
        try:result=qualify_cpu(summary)
        except CpuUnsuitable:
            budget.remaining(end);raise
        budget.remaining(end)
        return result
    finally:budget.arm()


class Budget(prior.Budget):
    """Reuse reviewed process-group cleanup, with a distinct fixed900s origin."""
    def __init__(self,started_ns,end_ns):
        need(type(started_ns) is int and type(end_ns) is int and end_ns-started_ns==TOTAL*10**9)
        need(started_ns<=time.monotonic_ns()<end_ns)
        self.started=started_ns;self.end=end_ns
        self.old={sig:signal.getsignal(sig) for sig in (signal.SIGALRM,signal.SIGTERM)}
        need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0))
        signal.signal(signal.SIGALRM,self.expired);signal.signal(signal.SIGTERM,self.interrupted)


def diagnostic(error,phase,sources):
    value=setup.safe_diagnostic(error,phase='preflight',sources=sources,exit_code=getattr(error,'exit_code',None))
    value['phase']=phase if phase in PHASES else 'preflight'
    return value


def publish(evidence,summary):
    need({p.name for p in evidence.iterdir()}<=set(OUTPUTS))
    progress={k:summary[k] for k in ('schema','status','phase','elapsed_seconds')}
    if progress['status']==PASS:progress['status']='TERMINAL_RECEIPT_PENDING'
    setup.atomic_json(evidence/'progress.json',progress,1024)
    setup.atomic_json(evidence/'summary.json',summary,65536)


def new_summary(start):
    return dict(schema=1,status='NOT_RUN',phase='preflight',elapsed_seconds=round((time.monotonic_ns()-start)/1e9,6),
                profile=runtime.PROFILE,native_rows=[16,128],public_executed=False,rtl_executed=False,
                packages_started=False,compile_started=False,native_started=False,
                postflight_complete=False,numerical_acceptance=False)


def finish(out,summary,budget,error=None,sources=()):
    if error is not None:
        summary.update(status='CPU_UNSUITABLE' if isinstance(error,CpuUnsuitable) else
                       'TIMEOUT' if isinstance(error,(TimeoutError,subprocess.TimeoutExpired)) else
                       'INTERRUPTED' if isinstance(error,(InterruptedError,KeyboardInterrupt)) else 'FAILED',
                       postflight_complete=False,numerical_acceptance=False,
                       diagnostic=diagnostic(error,summary['phase'],sources))
    summary['elapsed_seconds']=round((time.monotonic_ns()-budget.started)/1e9,6)
    try:
        budget.arm()
        if out is not None:
            # Only known atomic staging files, after all child cleanup; never follow links.
            for name in OUTPUTS:
                temporary=out/(name+'.pending')
                if temporary.is_symlink() or temporary.is_file():temporary.unlink()
            publish(out,summary)
        budget.remaining()
    except BaseException:
        summary.update(status='TIMEOUT' if time.monotonic_ns()>=budget.end else 'FAILED',
                       postflight_complete=False,numerical_acceptance=False)
        if out is not None:
            try:(out/'summary.json').unlink(missing_ok=True)
            except OSError:pass
    finally:budget.close()
    return (0 if summary['status']==PASS else 2 if summary['status']=='CPU_UNSUITABLE' else 1),summary


def read_launch(path,identity):
    raw=prior.read_bytes(path,262144);need(assets.digest(identity) and assets.sha(raw)==identity)
    c=assets.json_bytes(raw,limit=262144)
    need(type(c) is dict and set(c)=={'schema','private','evidence','checkout_commit','start_ns','deadline_ns',
         'contract_sha256','sources','git_blobs','generated'})
    need(type(c['schema']) is int and c['schema']==1 and setup.canonical_commit(c['checkout_commit']))
    private=assets.safe_path(c['private'],directory=True);out=assets.safe_path(c['evidence'],directory=True)
    need(assets.safe_path(path)==private/'launch.json' and private!=out and
         not private.is_relative_to(out) and not out.is_relative_to(private))
    need(type(c['start_ns']) is int and type(c['deadline_ns']) is int and c['deadline_ns']-c['start_ns']==TOTAL*10**9)
    need(c['start_ns']<=time.monotonic_ns()<c['deadline_ns'])
    need(type(c['sources']) is dict and type(c['generated']) is dict and type(c['git_blobs']) is dict and
         set(c['git_blobs'])==set(c['sources']) and set(c['generated'])<=set(c['sources']) and
         all(runtime.relative_name(n) and assets.digest(h) for n,h in c['sources'].items()) and
         all(runtime.relative_name(n) and assets.digest(h) for n,h in c['generated'].items()) and
         all(setup.canonical_commit(h) for h in c['git_blobs'].values()) and assets.digest(c['contract_sha256']))
    return c,private,out


def check_launch(c,private,*,composed):
    frozen=runtime.snapshot(composed=composed)
    need(frozen['sources'].get(SOURCE)==IMPORTED_SHA256)
    need(frozen['contract_sha256']==c['contract_sha256'] and frozen['generated']==c['generated'])
    expected=dict(c['sources'])
    if composed:expected.update(c['generated'])
    need(assets.same(frozen['sources'],expected))
    prior.git_identity(c['checkout_commit'],c['git_blobs'],private)
    for name,identity in c['sources'].items():
        raw=(subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT,env=prior.environment(private),timeout=10)
             if composed and name in c['generated'] else prior.read_bytes(ROOT/name,4194304))
        need(assets.sha(raw)==identity and
             hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==c['git_blobs'][name])
    need(ROOT.resolve()==private/'checkout')
    return frozen


def compose(c,private):
    budget=Budget(c['start_ns'],c['deadline_ns'])
    try:
        budget.arm();frozen=check_launch(c,private,composed=False)
        workspace=private/'workspace'
        runtime.prepare_outputs(workspace)
        for name,digest in frozen['generated'].items():
            raw=prior.read_bytes(workspace/'overlays'/name)
            need(assets.sha(raw)==digest)
            target=assets.safe_path(ROOT/name)
            need(assets.file_sha(target)==c['sources'][name]);target.write_bytes(raw)
        check_launch(c,private,composed=True)
        context=runtime.make_context(workspace,c['checkout_commit'],c['start_ns'],c['deadline_ns'],runtime.snapshot(composed=True))
        setup.atomic_json(workspace/'validation_context.json',context,262144)
        setup.atomic_json(workspace/'context.json',runtime.old_setup_context(context,runtime.snapshot(composed=True)),131072)
        for name in ('logs','tmp'):(workspace/name).mkdir()
        budget.remaining()
    finally:budget.close()


def bootstrap(private,out,commit):
    start=time.monotonic_ns();budget=Budget(start,start+TOTAL*10**9);summary=new_summary(start);frozen={};evidence=None
    try:
        budget.arm();private=setup.no_symlinks(Path(private).absolute());out=setup.no_symlinks(Path(out).absolute())
        need(private!=out and not private.is_relative_to(out) and not out.is_relative_to(private))
        private.mkdir(parents=True,exist_ok=False);out.mkdir(parents=True,exist_ok=False)
        private=assets.safe_path(private,directory=True);evidence=assets.safe_path(out,directory=True)
        for name in ('logs','tmp'):(private/name).mkdir()
        frozen=runtime.snapshot();need(frozen['sources'].get(SOURCE)==IMPORTED_SHA256)
        prior.git_identity(commit,frozen['git_blobs'],private)
        c=dict(schema=1,private=str(private),evidence=str(evidence),checkout_commit=commit,start_ns=start,deadline_ns=budget.end,
               contract_sha256=frozen['contract_sha256'],sources=frozen['sources'],git_blobs=frozen['git_blobs'],generated=frozen['generated'])
        setup.atomic_json(private/'launch.json',c,262144)
        setup.atomic_json(evidence/'source_hashes.json',dict(schema=1,contract_sha256=c['contract_sha256'],
            source_sha256=c['sources'],generated_sha256=c['generated'],generated_module_sha256=frozen['generated_module_sha256']),262144)
        summary.update(status='RUNNING',checkout_commit=commit,contract_sha256=frozen['contract_sha256'])
        run_cpu_qualification(summary,budget);publish(evidence,summary)
        summary['phase']='clone';publish(evidence,summary)
        budget.command(['git','clone','--no-local','--no-checkout','--',str(ROOT),str(private/'checkout')],private=private,cwd=ROOT,phase='clone',cap=45)
        budget.command(['git','-c','core.hooksPath=/dev/null','checkout','--detach',commit],private=private,cwd=private/'checkout',phase='checkout',cap=30)
        summary['phase']='compose';publish(evidence,summary)
        identity=assets.file_sha(private/'launch.json')
        command=[sys.executable,'-B','-m',MODULE,'--internal-compose','--context',str(private/'launch.json'),'--context-sha256',identity]
        budget.command(command,private=private,cwd=private/'checkout',phase='compose',cap=60)
        need(runtime.snapshot()==frozen);budget.disarm()
        os.chdir(private/'checkout')
        os.execve(sys.executable,[sys.executable,'-B','-m',MODULE,'--resume','--context',str(private/'launch.json'),
                  '--context-sha256',identity],prior.environment(private))
        raise RuntimeError('exec_returned')
    except BaseException as error:return finish(evidence,summary,budget,error,frozen.get('sources',{}))


def safe_report(workspace,name,context):
    from . import phase
    raw=prior.read_bytes(workspace/('phase_'+name+'.json'),32768)
    value=assets.json_bytes(raw,limit=32768)
    value=phase.validate_report(value)
    need(value['tokens']==(16 if name=='native16' else 128) and value['contract_sha256']==context['contract_sha256'] and
         value['source_manifest_sha256']==assets.sha(assets.encoded(context['source_sha256'])) and
         value['generated_module_sha256']==context['generated_module_sha256'])
    from candidates.qwen2_resident_matrix.raw_kv_native_qkv import kernel
    library=kernel.verify(workspace/'recipe_library')
    need(value['library_sha256']==library['library_sha256'] and value['library_receipt_sha256']==library['receipt_sha256'] and
         value['recipe_pins_sha256']==library['pins_sha256'] and
         value['result_sha256']==assets.file_sha(workspace/name/'RESULT.json') and
         value['payload_manifest_sha256']==assets.file_sha(workspace/'payload/manifest.json'))
    if name=='native128':need(value['m16_result_sha256']==assets.file_sha(workspace/'native16/RESULT.json'))
    return value


def run_kernel(workspace,context,budget,phase_end):
    """Sole compiler-group owner: no enclosing child supervisor can kill cleanup."""
    from . import phase
    from candidates.qwen2_resident_matrix.raw_kv_native_qkv import kernel
    budget.disarm()
    try:
        library=kernel.build(workspace/'recipe_library',execute=True,deadline_ns=phase_end-6*10**9)
    finally:
        budget.arm(phase_end-10**9)
    current,found=runtime.read_context(workspace/'validation_context.json')
    need(found==workspace and assets.same(current,context))
    need(assets.same(kernel.verify(workspace/'recipe_library'),library))
    report=phase.validate_kernel_report(dict(schema=1,status='COMPLETE_KERNEL_BUILD',numerical_execution=False,
        library_sha256=library['library_sha256'],library_receipt_sha256=library['receipt_sha256'],
        source_manifest_sha256=assets.sha(assets.encoded(context['source_sha256'])),contract_sha256=context['contract_sha256'],
        generated_module_sha256=context['generated_module_sha256'],recipe_pins_sha256=library['pins_sha256']))
    setup.atomic_json(workspace/'phase_kernel.json',report,4096)
    budget.remaining(phase_end-10**9)
    return report


def resume(c,private,out):
    budget=Budget(c['start_ns'],c['deadline_ns']);summary=new_summary(budget.started);frozen={};reports={}
    workspace=private/'workspace'
    try:
        budget.arm();frozen=check_launch(c,private,composed=True)
        context,found=runtime.read_context(workspace/'validation_context.json');need(found==workspace)
        summary.update(status='RUNNING',contract_sha256=c['contract_sha256'],checkout_commit=c['checkout_commit'])
        run_cpu_qualification(summary,budget);publish(out,summary)
        for name,cap in LIMITS.items():
            if name=='environment':summary['packages_started']=True
            if name=='kernel':summary['compile_started']=True
            if name in ('native16','native128'):summary['native_started']=True
            summary['phase']=name;summary['elapsed_seconds']=round((time.monotonic_ns()-budget.started)/1e9,6);publish(out,summary)
            need(check_launch(c,private,composed=True)==frozen)
            runtime.read_context(workspace/'validation_context.json')
            phase_end=min(budget.end,time.monotonic_ns()+cap*10**9)
            if name=='kernel':
                run_kernel(workspace,context,budget,phase_end)
            else:
                if name in ('preflight','environment','acquisition'):
                    command=setup.phase_command(name,workspace)
                else:
                    command=[str(workspace/'venv/bin/python'),'-B','-m',PHASE_MODULE,'--phase',name,
                             '--context',str(workspace/'validation_context.json')]
                budget.command(command,private=private,cwd=ROOT,phase=name,cap=cap,end_ns=phase_end,
                               extra_env={'QWEN2_NATIVE_QKV_PHASE_END_NS':str(phase_end)})
            need(check_launch(c,private,composed=True)==frozen)
            runtime.read_context(workspace/'validation_context.json')
            if name in ('preflight','environment','acquisition'):
                setup.phase_receipt(workspace,name,frozen['original_setup_sources'])
            elif name in ('native16','native128'):
                reports[name]=safe_report(workspace,name,context)
                need(reports[name]['status']=='COMPLETE_NATIVE_VALIDATION')
                summary['native_results']=dict(reports)
        need(set(reports)=={'native16','native128'})
        need(all(reports['native16'][key]==reports['native128'][key] for key in
                 ('library_sha256','library_receipt_sha256','recipe_pins_sha256','generated_module_sha256','payload_manifest_sha256')))
        need(check_launch(c,private,composed=True)==frozen)
        budget.remaining()
        summary.update(status=PASS,phase='finalize',postflight_complete=True,numerical_acceptance=True,native_results=reports)
        return finish(out,summary,budget,sources=frozen['sources'])
    except BaseException as error:
        name=summary['phase']
        if name in LIMITS:
            try:
                budget.arm()
                failure=assets.read_json(workspace/(name+'.failure.json'),limit=2048)
                if name in ('preflight','environment','acquisition'):
                    failure=setup.validate_diagnostic(failure,name,frozen['original_setup_sources'])
                else:
                    need(type(failure) is dict and failure.get('phase')==name)
                    failure=dict(failure,phase='preflight')
                    failure=setup.validate_diagnostic(failure,'preflight',frozen['sources'])
                    failure['phase']=name
                summary['child_diagnostic']=failure
            except Exception:pass
        if summary['phase'] in ('native16','native128'):
            try:
                budget.arm();reports[summary['phase']]=safe_report(workspace,summary['phase'],context)
                summary['native_results']=dict(reports)
            except Exception:summary['native_diagnostic_status']='UNAVAILABLE'
        if summary['phase']=='environment':
            try:
                value=assets.read_json(workspace/'backend.failure.json',limit=4096)
                from candidates.qwen2_resident_matrix.raw_kv_public_m128_run import launch
                summary['backend_preflight']=launch.validate_backend_failure(value,frozen['original_setup_sources'])
            except Exception:pass
        return finish(out,summary,budget,error,frozen.get('sources',{}))


def placement_status(evidence,commit,outcome):
    """Read-only workflow gate; only a validated early CPU miss permits a new VM."""
    need(outcome in ('success','failure') and setup.canonical_commit(commit))
    evidence=assets.safe_path(evidence,directory=True)
    need({path.name for path in evidence.iterdir()}==set(OUTPUTS))
    frozen=runtime.snapshot()
    need(frozen['sources'].get(SOURCE)==IMPORTED_SHA256)
    prior.git_identity(commit,frozen['git_blobs'],evidence)
    source=assets.read_json(evidence/'source_hashes.json',limit=262144)
    expected=dict(schema=1,contract_sha256=frozen['contract_sha256'],source_sha256=frozen['sources'],
                  generated_sha256=frozen['generated'],generated_module_sha256=frozen['generated_module_sha256'])
    need(assets.same(source,expected))
    summary=assets.read_json(evidence/'summary.json',limit=65536)
    need(type(summary) is dict and summary.get('schema')==1 and type(summary.get('schema')) is int and
         summary.get('profile')==runtime.PROFILE and summary.get('checkout_commit')==commit and
         summary.get('contract_sha256')==frozen['contract_sha256'] and
         summary.get('public_executed') is False and summary.get('rtl_executed') is False)
    need(assets.same(summary.get('native_rows'),[16,128]) and type(summary.get('elapsed_seconds')) in (int,float) and
         math.isfinite(summary['elapsed_seconds']) and 0<=summary['elapsed_seconds']<=TOTAL)
    progress=assets.read_json(evidence/'progress.json',limit=1024)
    expected_progress={key:summary[key] for key in ('schema','status','phase','elapsed_seconds')}
    if expected_progress['status']==PASS:expected_progress['status']='TERMINAL_RECEIPT_PENDING'
    need(assets.same(progress,expected_progress))
    cpu=validate_cpu_eligibility(summary.get('cpu_eligibility'))
    status=summary.get('status')
    base_keys=set(new_summary(time.monotonic_ns()))|{'checkout_commit','contract_sha256','cpu_eligibility'}
    if status=='CPU_UNSUITABLE':
        need(set(summary)==base_keys|{'diagnostic'})
        diagnostic=summary['diagnostic'];need(type(diagnostic) is dict and diagnostic.get('phase')=='cpu_qualification' and
             diagnostic.get('exception')=='OtherError' and set(diagnostic)=={'phase','exception','frames'})
        setup.validate_diagnostic(dict(diagnostic,phase='preflight'),'preflight',frozen['sources'])
        need(outcome=='failure' and summary.get('phase')=='cpu_qualification' and cpu['status']=='CPU_UNSUITABLE' and
             all(summary.get(k) is False for k in ('packages_started','compile_started','native_started','postflight_complete','numerical_acceptance')))
        return status
    if status==PASS:
        need(set(summary)==base_keys|{'native_results'})
        need(outcome=='success' and summary.get('phase')=='finalize' and cpu['status']=='ELIGIBLE_FOR_BACKEND_CHECK' and
             all(summary.get(k) is True for k in ('packages_started','compile_started','native_started','postflight_complete','numerical_acceptance')))
        from . import phase
        reports=summary.get('native_results');need(type(reports) is dict and set(reports)=={'native16','native128'})
        sources=dict(frozen['sources']);sources.update(frozen['generated'])
        for name,tokens in (('native16',16),('native128',128)):
            report=phase.validate_report(reports[name])
            need(report['tokens']==tokens and report['native_acceptance'] is True and
                 report['contract_sha256']==frozen['contract_sha256'] and
                 report['source_manifest_sha256']==assets.sha(assets.encoded(sources)) and
                 report['generated_module_sha256']==frozen['generated_module_sha256'])
        need(reports['native128']['m16_result_sha256']==reports['native16']['result_sha256'] and
             all(reports['native16'][k]==reports['native128'][k] for k in
                 ('library_sha256','library_receipt_sha256','recipe_pins_sha256','payload_manifest_sha256')))
        return PASS
    return 'FAILED'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--private',type=Path);parser.add_argument('--evidence',type=Path)
    parser.add_argument('--checkout-commit');parser.add_argument('--resume',action='store_true');parser.add_argument('--internal-compose',action='store_true')
    parser.add_argument('--context',type=Path);parser.add_argument('--context-sha256')
    parser.add_argument('--placement-status',action='store_true');parser.add_argument('--attempt-outcome');a=parser.parse_args(argv)
    try:
        if a.placement_status:
            need(not a.execute and not a.resume and not a.internal_compose and a.evidence is not None)
            print(placement_status(a.evidence,a.checkout_commit,a.attempt_outcome));return 0
        if a.resume or a.internal_compose:
            need(a.resume!=a.internal_compose and not a.execute and os.environ.get('QWEN2_PUBLIC_RUN_CHILD')=='1')
            c,private,out=read_launch(a.context,a.context_sha256)
            if a.internal_compose:compose(c,private);return 0
            code,summary=resume(c,private,out)
        else:
            need(a.execute and a.private is not None and a.evidence is not None and setup.canonical_commit(a.checkout_commit))
            need(os.environ.get('GITHUB_RUN_ATTEMPT','1')=='1')
            if 'GITHUB_SHA' in os.environ:need(os.environ['GITHUB_SHA']==a.checkout_commit)
            code,summary=bootstrap(a.private,a.evidence,a.checkout_commit)
        print(json.dumps(summary,sort_keys=True,allow_nan=False));return code
    except BaseException as error:
        print(json.dumps(dict(schema=1,status='NOT_RUN',diagnostic=diagnostic(error,'preflight',())),sort_keys=True));return 1


if __name__=='__main__':raise SystemExit(main())
