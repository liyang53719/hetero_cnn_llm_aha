"""Explicit, separately frozen launcher; default CLI is plan-only."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from ..attention_packed_m16_assets import reuse as R
from ..attention_packed_m16_assets import producer as P
from . import receipt,supervisor

HERE=Path(__file__).resolve().parent
OWN=('launch.py','receipt.py','supervisor.py','test_launch.py','README.md')
PROFILE='qwen2-packed-m16-reference-launch-portable-v1'
CHILD=r'''
import hashlib,json,os,signal,sys
from pathlib import Path
# Popen intentionally runs under a blocked parent mask until ownership is
# recorded. Exec inherits that mask, so reset it before any producer imports.
signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM,signal.SIGTERM,signal.SIGINT})
code,origin,output,control,expected_json,python_json=sys.argv[1:]
sys.path.insert(0,code)
import reuse as R
import producer as P
expected=R.strict_json(expected_json.encode())
python_expected=R.strict_json(python_json.encode())
R.need(R.same(R.snapshot(),expected),'isolated asset source snapshot')
R.need(sys.implementation.name==python_expected['implementation'] and
       list(sys.version_info[:3])==python_expected['version'],'isolated interpreter version')
R.need(R.file_hash(Path(sys.executable).resolve())==python_expected['sha256'],'isolated interpreter identity')
result=P.produce(origin,output,work_seconds=120)
raw=(Path(output)/'M16_REFERENCES.json').read_bytes()
R.need(R.same(R.strict_json(raw),result) and R.same(R.snapshot(),expected),'child final receipt/source equality')
P.save(Path(control)/'child_exit.json',dict(schema=1,status='CHILD_REFERENCE_PREPARATION_COMPLETE',
    pid=os.getpid(),receipt_sha256=R.sha(raw),asset_source_sha256=expected,
    python_sha256=python_expected['sha256'],python_version=list(sys.version_info[:3])))
'''


def load_contract(expected_sha):
    R.need(R.digest(expected_sha),'explicit reviewed launcher contract digest required')
    contract_path=R.safe_path(HERE/'contract.json')
    R.need(contract_path.stat().st_size<=R.MAX_JSON,'launcher contract size')
    raw=contract_path.read_bytes()
    R.need(R.sha(raw)==expected_sha,'launcher contract digest')
    value=R.strict_json(raw)
    receipt.exact(value,('schema','profile','status','asset_contract_sha256','asset_sources','launcher_sources',
        'origin_commit','python','work_seconds','cleanup_seconds','outer_seconds','attempts','claims',
        'historical_execution_claim'))
    R.need(type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE
        and value['status']=='REPRODUCIBLE_PROPOSAL_EXECUTION_UNAUTHORIZED'
        and value['historical_execution_claim'] is False
        and value['asset_contract_sha256']==R.PINS_SHA256
        and all(type(value[k]) is int and value[k]==v for k,v in
                (('work_seconds',120),('cleanup_seconds',5),('outer_seconds',126),('attempts',1)))
        and value['origin_commit']==R.contract()['origin_commit']
        and R.same(value['claims'],R.contract()['claims']),'exact bounded launcher contract')
    receipt.exact(value['python'],('lexical_relative_path','implementation','version','bytes','sha256'))
    R.need(value['python']['lexical_relative_path']=='private/assets/venv/bin/python'
        and type(value['python']['bytes']) is int and value['python']['bytes']>0
        and R.digest(value['python']['sha256']) and value['python']['implementation']=='cpython'
        and R.same(value['python']['version'],[3,12,14]),'interpreter contract')
    R.need(set(value['launcher_sources'])==set(OWN) and
        {name:R.file_hash(HERE/name) for name in OWN}==value['launcher_sources'],'launcher source freeze')
    R.need(R.same(R.snapshot(),value['asset_sources']),'five-file asset freeze')
    return value


def environment(control,incoming=None):
    incoming=os.environ if incoming is None else incoming
    for key in ('ATEN_CPU_CAPABILITY','LD_PRELOAD','LD_LIBRARY_PATH','PYTHONHOME','PYTHONPATH',
                'ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA','MKL_CBWR'):
        R.need(not incoming.get(key),'unreviewed runtime override')
    return dict(PATH='/usr/bin:/bin',HOME=str(control/'home'),TMPDIR=str(control/'tmp'),
        HF_HOME=str(control/'hf'),LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',
        OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4')


def interpreter(origin,contract,python_path):
    # Validate the trusted venv parent first, then allow its normal executable
    # symlink chain while pinning the resolved regular file and bytes separately.
    parent=R.safe_path(origin/'private/assets/venv/bin',directory=True)
    lexical=parent/'python'
    R.need(Path(python_path).absolute()==lexical,'explicit retained-venv interpreter argument')
    resolved=lexical.resolve(strict=True)
    R.safe_path(resolved)
    expected=contract['python']
    R.need(resolved.stat().st_size==expected['bytes']
        and R.file_hash(resolved)==expected['sha256'],'retained venv interpreter identity')
    return lexical


def interpreter_identity(python):
    resolved=python.resolve(strict=True)
    return dict(lexical_path=str(python),resolved_path=str(resolved),bytes=resolved.stat().st_size,
        sha256=R.file_hash(resolved))


def classify(error,phase):
    if isinstance(error,(InterruptedError,KeyboardInterrupt)):return 'CANCELLED'
    if isinstance(error,TimeoutError):return 'TIMED_OUT'
    if phase=='child':return 'FAILED_CHILD'
    if phase=='postflight':return 'FAILED_RECEIPT'
    return 'FAILED_PREFLIGHT'


def safe_summary(status,phase,started,contract_sha,*,exit_code=None,cleanup=None,verified=None,launch_receipt_sha=None):
    R.need(status in {'RUNNING','COMPLETE_REFERENCE_PREPARATION_ONLY','FAILED_PREFLIGHT','FAILED_CHILD',
        'FAILED_RECEIPT','FAILED_CLEANUP','TIMED_OUT','CANCELLED'},'safe status')
    R.need(phase in {'preflight','child','postflight','complete'},'safe phase')
    value=dict(schema=1,profile=PROFILE,status=status,phase=phase,
        elapsed_seconds=round(max(0,time.monotonic()-started),6),
        contract_sha256=contract_sha if R.digest(contract_sha) else None,
        numerical_acceptance=False,full_29_node_acceptance=False,ready_for_actual=False)
    if exit_code is not None:
        R.need(type(exit_code) is int and -255<=exit_code<=255,'safe child exit bound')
        value['child_exit_code']=exit_code
    if cleanup is not None:R.need(type(cleanup) is bool,'cleanup type');value['cleanup_complete']=cleanup
    if verified is not None:
        R.need(R.digest(verified['receipt_sha256']),'private receipt digest')
        R.need(all(type(verified[k]) is int and 0<verified[k]<=512 for k in
                   ('fresh_artifacts','origin_artifacts')),'public artifact count bounds')
        value['receipt_sha256']=verified['receipt_sha256']
        value['fresh_artifacts']=verified['fresh_artifacts'];value['origin_artifacts']=verified['origin_artifacts']
    if launch_receipt_sha is not None:
        R.need(R.digest(launch_receipt_sha),'private launch receipt digest')
        value['launch_receipt_sha256']=launch_receipt_sha
    return value


def completion(work,contract,contract_sha,child_pid,verified,python_identity):
    """Private evidence of observed child exit; caller must observe launcher exit."""
    return dict(schema=1,profile=PROFILE,status='VALIDATED_REFERENCE_CHILD_EXIT_ONLY',
        contract_sha256=contract_sha,launcher_source_sha256=contract['launcher_sources'],
        asset_source_sha256=contract['asset_sources'],origin_commit=contract['origin_commit'],
        interpreter=dict(contract=contract['python'],runtime=python_identity),launcher_pid=os.getpid(),
        child=dict(pid=child_pid,returncode=0,cleanup_complete=True,
            completion_marker=P.record(work,work/'control/child_exit.json')),
        references=P.record(work,work/'references/M16_REFERENCES.json'),
        context=P.record(work,work/'control/context.json'),verification=verified,
        caller_must_observe_launcher_exit=True,ready_for_actual=False,**R.contract()['claims'])


def launch(origin,workspace,*,contract_sha256,python_path):
    """One explicit attempt. Never called by cold tests or the default CLI."""
    started=time.monotonic();outer=started+126;phase='preflight';child=None;libc=None
    code=None;summary=None;failure=None;control=None;out=None;contract=None
    # SIGTERM/ALRM exceptions remain caught inside this context until children
    # are reaped; the inherited signal handlers are restored only afterward.
    with P.deadline(120) as work_end:
        try:
            contract=load_contract(contract_sha256)
            origin=R.safe_path(origin,directory=True)
            work=P.output_root(origin,workspace)
            R.need(not work.is_relative_to(R.HERE) and not R.HERE.is_relative_to(work),'launcher/source overlap')
            work.mkdir(mode=0o700)
            control=work/'control';control.mkdir(mode=0o700)
            for name in ('home','tmp','hf'):(control/name).mkdir(mode=0o700)
            out=work/'references'
            env=environment(control)
            python=interpreter(origin,contract,python_path)
            python_identity=interpreter_identity(python)
            before=R.verify_reuse(origin,metadata_only=False)
            R.need(before['origin_commit']==contract['origin_commit'],'origin commit')
            P.save(control/'context.json',dict(origin=str(origin),output=str(out),contract_sha256=contract_sha256,
                asset_sources=contract['asset_sources'],origin_before=before,python=python_identity,environment=env))
            libc=supervisor.enable_subreaper()
            phase='child'
            command=[str(python),'-I','-B','-c',CHILD,str(R.HERE),str(origin),str(out),str(control),
                R.encoded(contract['asset_sources']).decode(),R.encoded(contract['python']).decode()]
            with (control/'stdout.log').open('xb') as stdout,(control/'stderr.log').open('xb') as stderr:
                blocked=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM,signal.SIGTERM,signal.SIGINT})
                try:
                    process=subprocess.Popen(command,cwd=control,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
                    child=supervisor.Child(process)
                finally:
                    signal.pthread_sigmask(signal.SIG_SETMASK,blocked)
                code=child.wait(work_end)
            R.need(code==0,'reference child exit failure')
            R.need(child.clean_exit(),'reference child left descendants')
            phase='postflight'
            marker_path=R.below(control,'child_exit.json')
            R.need(marker_path.stat().st_size<=R.MAX_JSON,'child completion marker bound')
            marker=R.strict_json(marker_path.read_bytes())
            receipt.exact(marker,('schema','status','pid','receipt_sha256','asset_source_sha256','python_sha256','python_version'))
            R.need(type(marker['schema']) is int and marker['schema']==1 and
                marker['status']=='CHILD_REFERENCE_PREPARATION_COMPLETE' and type(marker['pid']) is int
                and marker['pid']==process.pid and R.same(marker['asset_source_sha256'],contract['asset_sources'])
                and marker['python_sha256']==contract['python']['sha256']
                and R.same(marker['python_version'],contract['python']['version']),'isolated child completion binding')
            verified=receipt.validate(origin,out,child_returncode=code,sources=contract['asset_sources'],origin_before=before)
            R.need(marker['receipt_sha256']==verified['receipt_sha256'],'child/disk receipt mismatch')
            R.need(load_contract(contract_sha256)==contract and interpreter(origin,contract,python_path)==python
                and R.same(interpreter_identity(python),python_identity),'postflight launcher/interpreter changed')
            supervisor.restore_subreaper(libc);libc=None
            launch_receipt=completion(work,contract,contract_sha256,process.pid,verified,python_identity)
            R.need(launch_receipt['references']['sha256']==verified['receipt_sha256'],'launch receipt exact output binding')
            P.save(work/'LAUNCH_RECEIPT.json',launch_receipt)
            summary=safe_summary('COMPLETE_REFERENCE_PREPARATION_ONLY','complete',started,contract_sha256,
                exit_code=0,cleanup=True,verified=verified,launch_receipt_sha=R.file_hash(work/'LAUNCH_RECEIPT.json'))
        except BaseException as error:
            failure=error;clean=True
            # Ignore repeat termination and the work alarm until owned children
            # have received TERM, their cleanup reserve, fallback KILL and reap.
            with P.protected_cleanup():
                if child is not None:
                    try:clean=child.terminate(outer)
                    except BaseException:clean=False
                try:
                    if out is not None:(out/'M16_REFERENCES.json').unlink(missing_ok=True)
                    if control is not None:(control/'child_exit.json').unlink(missing_ok=True)
                    if control is not None:(control.parent/'LAUNCH_RECEIPT.json').unlink(missing_ok=True)
                except BaseException:clean=False
                if libc is not None and clean:
                    try:supervisor.restore_subreaper(libc);libc=None
                    except BaseException:clean=False
                summary=safe_summary(classify(error,phase) if clean else 'FAILED_CLEANUP',phase,started,
                    contract_sha256,exit_code=code,cleanup=clean)
    # Public evidence is a fixed allowlist. Logs/context/full receipts stay in
    # control/references and are never printed, attached or copied to evidence.
    if control is not None:
        # The final evidence write consumes the same outer ceiling. On failure,
        # no partial success-named evidence survives the atomic save helper.
        old_alarm=signal.getsignal(signal.SIGALRM)
        def expired(_signal,_frame):raise TimeoutError('outer reference-launch deadline')
        try:
            left=outer-time.monotonic()
            R.need(left>0,'outer reference-launch deadline')
            signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,left)
            P.save(control.parent/'summary.json',summary)
        except BaseException:
            summary=safe_summary('FAILED_CLEANUP',phase,started,contract_sha256,
                exit_code=code,cleanup=False)
            try:(control.parent/'LAUNCH_RECEIPT.json').unlink(missing_ok=True)
            except BaseException:pass
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_alarm)
    if failure is not None:
        return summary
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description='Default: plan only. Execution requires separately reviewed explicit authorization.')
    parser.add_argument('--origin',required=True);parser.add_argument('--workspace',required=True)
    parser.add_argument('--python',required=True,help='Retained origin-venv interpreter; absolute paths stay private.')
    parser.add_argument('--contract-sha256',required=True)
    parser.add_argument('--execute-reference-preparation',action='store_true')
    args=parser.parse_args(argv)
    started=time.monotonic()
    try:
        if not args.execute_reference_preparation:
            contract=load_contract(args.contract_sha256)
            value=dict(schema=1,profile=PROFILE,status='PLAN_ONLY_NO_EXECUTION',work_seconds=120,
                cleanup_seconds=5,outer_seconds=126,attempts=1,asset_sources=contract['asset_sources'],
                numerical_acceptance=False,ready_for_actual=False)
        else:
            value=launch(args.origin,args.workspace,contract_sha256=args.contract_sha256,python_path=args.python)
    except BaseException as error:
        value=safe_summary(classify(error,'preflight'),'preflight',started,args.contract_sha256,cleanup=False)
    print(json.dumps(value,sort_keys=True))
    return 0 if value['status'] in ('PLAN_ONLY_NO_EXECUTION','COMPLETE_REFERENCE_PREPARATION_ONLY') else 1


if __name__=='__main__':raise SystemExit(main())
