"""Single short pre-DUT diagnostic. Only fixed enums/line numbers leave local logs."""
import argparse
import contextlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
AUTH='candidates/qwen2_official_platform_preflight_authorization_v2'
LOGS='work/qwen2_official_platform_preflight_logs'
PREFIX='HETERO_PREFLIGHT_SAFE '
PHASES=frozenset(('AUTHORIZE','BIND','BIND_RESULT','PROBE','LAUNCH_ADMISSION','COMPLETE'))
MODULES={
    **{'candidates/qwen2_official_platform_fullblock/'+n+'.py':n.upper() for n in
       ('job','recipe','gates','audit_probe','native_artifact','runner','preflight_diagnostic')},
    **{'candidates/qwen2_official_cpu_platform_reference/'+n+'.py':'REFERENCE_'+n.upper() for n in
       ('pair','recipe','validator','issuer','lifecycle')},
    **{'candidates/qwen2_fullblock_ci_dut/'+n+'.py':'RUNTIME_'+n.upper() for n in
       ('runtime_adapter','platform_freeze')},
}
ERROR_TYPES=((FileNotFoundError,'FILE_NOT_FOUND'),(PermissionError,'PERMISSION_ERROR'),
    (TimeoutError,'TIMEOUT'),(subprocess.TimeoutExpired,'TIMEOUT'),(MemoryError,'MEMORY_ERROR'),
    (AssertionError,'ASSERTION_ERROR'),(ValueError,'VALUE_ERROR'),(TypeError,'TYPE_ERROR'),
    (KeyError,'KEY_ERROR'),(ImportError,'IMPORT_ERROR'),(OSError,'OS_ERROR'),
    (RuntimeError,'RUNTIME_ERROR'))
ERRORS=frozenset(v for _,v in ERROR_TYPES)|{'NONE','OTHER'}
DEADLINE_ENV='QWEN2_PREFLIGHT_JOB_DEADLINE'


def checked(value):
    if type(value) is not dict or set(value)!={'schema','status','phase','module','line','error','dut_started'}:
        raise ValueError('invalid safe diagnostic schema')
    if (type(value['schema']) is not int or value['schema']!=1 or
        type(value['status']) is not str or value['status'] not in ('PREFLIGHT_FAILED','PREFLIGHT_READY_NO_DUT') or
        type(value['phase']) is not str or value['phase'] not in PHASES or
        type(value['module']) is not str or value['module'] not in set(MODULES.values())|{'OTHER'} or
        type(value['line']) is not int or not 0<=value['line']<=100000 or
        (value['module']=='OTHER')!=(value['line']==0) or
        type(value['error']) is not str or value['error'] not in ERRORS or
        value['dut_started'] is not False or
        (value['status']=='PREFLIGHT_READY_NO_DUT')!=(value['error']=='NONE')):
        raise ValueError('invalid safe diagnostic values')
    return dict(value)


def record(phase,*,error='OTHER',module='OTHER',line=0,success=False):
    return checked(dict(schema=1,status='PREFLIGHT_READY_NO_DUT' if success else 'PREFLIGHT_FAILED',
        phase=phase,module=module,line=line,error='NONE' if success else error,dut_started=False))


def project(error,phase,root=ROOT):
    if not isinstance(error,BaseException):raise TypeError('exception required')
    p=PurePosixPath(str(root))
    if not p.is_absolute() or '..' in p.parts or str(p)!=str(root):raise ValueError('fixed root required')
    labels={str(p)+'/'+path:label for path,label in MODULES.items()}
    result=record(phase)
    for kind,label in ERROR_TYPES:
        if isinstance(error,kind):result['error']=label;break
    trace=BaseException.__traceback__.__get__(error)
    while trace is not None:
        code=trace.tb_frame.f_code;label=labels.get(code.co_filename)
        if label is not None and code.co_name not in ('need','require') and 1<=trace.tb_lineno<=100000:
            result.update(module=label,line=trace.tb_lineno)
        trace=trace.tb_next
    return checked(result)


def read_child(path):
    # No traceback text or arbitrary JSON is propagated. Unknown logs stay unknown.
    result=None
    with path.open('rb') as stream:
        data=stream.read(4*1024*1024+1)
        if len(data)>4*1024*1024:return record('PROBE')
        for raw in data.splitlines():
            if len(raw)>2048 or not raw.startswith(PREFIX.encode()):continue
            try:value=checked(json.loads(raw[len(PREFIX):]))
            except (ValueError,TypeError,UnicodeError):continue
            if value['phase']=='PROBE':result=value
    return result or record('PROBE')


def child():
    try:
        from . import audit_probe
        code=audit_probe.main(['--initialized-only'])
        if code!=0:raise RuntimeError('initialized control failed')
        result=record('PROBE',success=True)
    except BaseException as error:
        try:result=project(error,'PROBE')
        except BaseException:result=record('PROBE')
        try:traceback.print_exc()
        except BaseException:pass
    print(PREFIX+json.dumps(result,sort_keys=True),flush=True)
    return 0 if result['status']=='PREFLIGHT_READY_NO_DUT' else 2


def configure():
    from . import job,recipe
    if job.AUTH!='candidates/qwen2_official_platform_fullblock_authorization' or recipe.AUTH!=job.AUTH:
        raise ValueError('unexpected authorization namespace')
    job.AUTH=recipe.AUTH=AUTH
    job.POLICY={**job.POLICY,'job_total_minutes':15,'diagnostic_only':True,'dut_invocations':0,
        'maximum_invocations':0,'dut_inner_seconds':0,'dut_outer_seconds':0}
    return job,recipe


def remaining():
    raw=os.getenv(DEADLINE_ENV,'')
    if not raw.isascii() or not raw.isdecimal() or len(raw)>12:
        raise ValueError('explicit job deadline required')
    left=int(raw)-time.time()
    if not 0<left<=900:raise ValueError('job deadline invalid or expired')
    return left


def launch_admission(job,review):
    # Read-only admission conditions from the reviewed supervisor, no receipt,
    # child creation, numerical driver, or claim that process launch succeeded.
    from . import gates
    gates.require_review(review['source_closure_sha256'])
    gates.require_budget()
    data=gates.data_path('work/qwen2_live_qkv_inputs_m128/ci01')
    gates.reference_path(str(gates.REFERENCE.relative_to(ROOT)))
    out=ROOT/job.OUT
    out.parent.mkdir(parents=True,exist_ok=True)
    gates.fresh_output(out,data)
    gates.require(out.parent.is_dir(),'reviewed work root required')
    paths=[out.with_name(out.name+s) for s in ('.LAUNCH.json','.stdout.log','.stderr.log','.HEARTBEAT.json')]
    gates.require(all(not p.exists() and not p.is_symlink() for p in paths),'single-use launch outputs required')


def run():
    started=time.monotonic()
    phase='AUTHORIZE';logs=ROOT/LOGS
    logs.mkdir(parents=True,exist_ok=True)
    with (logs/'preflight.log').open('x') as detail:
        with contextlib.redirect_stdout(detail),contextlib.redirect_stderr(detail):
            try:
                remaining();job,recipe=configure();review=job.authorize()
                phase='BIND';bound=job.bind()
                phase='BIND_RESULT'
                job.need(bound['status']==recipe.STATUS and bound['reference_outputs_checked']==29 and
                    bound['policy_conditions_satisfied'] is True,'conditional binder required')
                os.environ[recipe.BINDING_ENV]=bound['binding_sha256']
                phase='PROBE'
                job.need(min(remaining(),120-(time.monotonic()-started))>=92,
                    'insufficient job/step budget for initialized control')
                child_log=logs/'initialized-control.log'
                with child_log.open('xb') as stream:
                    result=subprocess.run([sys.executable,'-B','-m',
                        'candidates.qwen2_official_platform_fullblock.preflight_diagnostic','child'],
                        cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=90,check=False)
                safe=read_child(child_log)
                if result.returncode!=0:
                    if safe['status']!='PREFLIGHT_FAILED':safe=record('PROBE')
                    return safe
                if safe['status']!='PREFLIGHT_READY_NO_DUT':return record('PROBE')
                phase='LAUNCH_ADMISSION';remaining();launch_admission(job,review)
                return record('COMPLETE',success=True)
            except BaseException as error:
                try:safe=project(error,phase)
                except BaseException:safe=record(phase)
                try:traceback.print_exc()
                except BaseException:pass
                return safe


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('admit','capture','preflight','child'))
    args=parser.parse_args(argv)
    if args.action=='child':return child()
    if args.action in ('admit','capture'):
        job,_=configure();getattr(job,args.action)();return 0
    try:result=run()
    except BaseException as error:
        # Even failure to create the local diagnostic log has a safe terminal.
        try:result=project(error,'AUTHORIZE')
        except BaseException:result=record('AUTHORIZE')
    print(json.dumps(checked(result),sort_keys=True))
    return 0 if result['status']=='PREFLIGHT_READY_NO_DUT' else 2


if __name__=='__main__':raise SystemExit(main())
