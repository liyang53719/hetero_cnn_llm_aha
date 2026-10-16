"""Single opt-in M16 rebuild and original Public execution, with private payloads.

Bootstrap checks the clean event checkout, composes only the eight pinned files
in an independent local clone, then re-execs here. The resumed process calls the
published setup directly: setup alone owns its nested producer process groups.
The original 1680-second origin survives re-exec. No retry or network Git fallback.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

from candidates.qwen2_resident_matrix.raw_kv_public_fresh import assets, setup

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
MODULE='candidates.qwen2_resident_matrix.raw_kv_public_run.run_ci'
PREFIX='candidates/qwen2_resident_matrix/raw_kv_public_run/'
CONTRACT=PREFIX+'launch-contract.json'
WORKFLOW='.github/workflows/raw-kv-public-m16.yml'
OWN=(PREFIX+'run_ci.py',PREFIX+'test_run_ci.py',PREFIX+'admission.py',PREFIX+'test_admission.py',PREFIX+'README.md',WORKFLOW)
PROFILE='qwen2-public-m16-launch-v1'
BASE_SETUP_COMMIT='2879c375df143d4439c7c30ea43af77df02455a6'
TOTAL=1680
SETUP_BUDGET=600
NUMERIC_BUDGET=930
WALL_BUDGET=900
GRACE=5
RECEIPT=1
PHASES=('preflight','clone','compose','setup','numeric','finalize')
OUTPUTS=('summary.json','progress.json','source_hashes.json')
PASS='PASS_FRESH_PUBLIC_M16_OBSERVED_GATES'
VALIDATED='VALIDATED_ACTUAL_POSTFLIGHT_INCOMPLETE'
IMPORTED_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
BASE_SETUP_SHA256={
 'candidates/qwen2_resident_matrix/raw_kv_public_fresh/'+name:value for name,value in {
 'setup.py':'a4c5f24341747f8c89cd3e13d12c51b5fe9ba93973e53eb472d59a31adcfe9e5',
 'test_setup.py':'36fc51f3faf6f4875da0ab4ee9500877ba613bf3ce70b066c6c78d5a4c48caec',
 'SETUP_PLAN.md':'d80ee507f0017c4ce0b1c2f6b9e2096913f5b2818693f6c671cde819ed73efc4',
 'setup_profile.json':'2676d0aff83d86c2bc1d80dc1f80aab511c2f311d315719f13602f7cf16c60d4'}.items()}


def need(ok):
    if not ok:raise ValueError('launch_contract')


def read_bytes(path,limit=2*1024*1024):
    path=assets.safe_path(path)
    need(path.stat().st_size<=limit)
    with path.open('rb') as f:raw=f.read(limit+1)
    need(len(raw)<=limit)
    return raw


def contract_snapshot(*,composed=False):
    """The contract hash is derived from the exact bytes parsed, never reread."""
    raw=read_bytes(ROOT/CONTRACT,131072);value=assets.json_bytes(raw,limit=131072)
    fixed=dict(schema=1,profile=PROFILE,base_setup_commit=BASE_SETUP_COMMIT,rows=16,past_tokens=0,
        enable_raw_kv=True,setup_budget=SETUP_BUDGET,numeric_budget=NUMERIC_BUDGET,
        numeric_wall_budget=WALL_BUDGET,total_budget=TOTAL)
    need(type(value) is dict and set(value)==set(fixed)|{'source_sha256','generated_sha256'})
    for key,want in fixed.items():need(type(value[key]) is type(want) and value[key]==want)
    pins=assets.read_json(ROOT/'candidates/qwen2_resident_matrix/raw_kv_public_fresh/pins.json')
    names=set(pins['source_paths'])|set(BASE_SETUP_SHA256)|set(OWN)
    need(type(value['source_sha256']) is dict and set(value['source_sha256'])==names)
    need(value['generated_sha256']==pins['generated_sha256']['enabled'] and len(value['generated_sha256'])==8)
    need(all(value['source_sha256'].get(k)==v for k,v in BASE_SETUP_SHA256.items()))
    need(all(value['source_sha256'].get(k)==v for k,v in setup.BASE_VERIFIER_SHA256.items()))
    need(value['source_sha256'][OWN[0]]==IMPORTED_SHA256)
    expected=dict(value['source_sha256'])
    if composed:expected.update(value['generated_sha256'])
    blobs={} if composed else {CONTRACT:hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
    for name,identity in expected.items():
        need(assets.digest(identity))
        content=read_bytes(ROOT/name,4*1024*1024)
        need(assets.sha(content)==identity)
        if not composed:blobs[name]=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
    return dict(contract_sha256=assets.sha(raw),sources=expected,original_sources=value['source_sha256'],
                generated=value['generated_sha256'],git_blobs=blobs)


def environment(private):
    env=setup.child_environment(private)
    for key in tuple(env):
        if key.startswith('GIT_'):env.pop(key)
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0',
        GIT_NO_LAZY_FETCH='1',GIT_ALLOW_PROTOCOL='file',QWEN2_PUBLIC_RUN_CHILD='1')
    return env


def git_identity(commit,blobs,private):
    need(setup.canonical_commit(commit))
    env=environment(private)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,env=env,timeout=10).decode().strip()
    need(head==commit)
    raw=subprocess.check_output(['git','ls-tree','-rz','--full-tree','HEAD'],cwd=ROOT,env=env,timeout=10)
    need(len(raw)<16*1024*1024)
    found={}
    for item in raw.split(b'\0'):
        if not item:continue
        left,name=item.split(b'\t',1);mode,kind,identity=left.decode().split()
        if name.decode() in blobs:
            need(kind=='blob' and mode in ('100644','100755'))
            found[name.decode()]=identity
    need(found==blobs)


def diagnostic(error,phase,sources,code=None):
    value=setup.safe_diagnostic(error,phase='preflight',sources=sources,exit_code=code)
    value['phase']=phase if phase in PHASES else 'preflight'
    return value


def publish(evidence,summary):
    need({p.name for p in evidence.iterdir()}<=set(OUTPUTS))
    progress={k:summary[k] for k in ('schema','status','phase','elapsed_seconds')}
    if progress['status']==PASS:progress['status']='TERMINAL_RECEIPT_PENDING'
    setup.atomic_json(evidence/'progress.json',progress,1024)
    setup.atomic_json(evidence/'summary.json',summary,8192)


class Budget:
    def __init__(self,started_ns,end_ns):
        need(type(started_ns) is int and type(end_ns) is int and end_ns-started_ns==TOTAL*10**9)
        need(started_ns<=time.monotonic_ns()<end_ns)
        self.started=started_ns;self.end=end_ns
        self.old={sig:signal.getsignal(sig) for sig in (signal.SIGALRM,signal.SIGTERM)}
        need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0))
        signal.signal(signal.SIGALRM,self.expired);signal.signal(signal.SIGTERM,self.interrupted)
    @staticmethod
    def expired(signum,frame):raise TimeoutError()
    @staticmethod
    def interrupted(signum,frame):raise InterruptedError()
    def remaining(self,end=None):
        value=(min(self.end,end or self.end)-time.monotonic_ns())/1e9
        if value<=0:raise TimeoutError()
        return value
    def arm(self,end=None):signal.setitimer(signal.ITIMER_REAL,self.remaining(end))
    def disarm(self):signal.setitimer(signal.ITIMER_REAL,0)
    def close(self):
        self.disarm()
        for sig,handler in self.old.items():signal.signal(sig,handler)
    def command(self,argv,*,private,cwd,phase,cap,extra_env=None,end_ns=None):
        self.disarm()
        phase_end=min(self.end,end_ns if end_ns is not None else time.monotonic_ns()+int(cap*10**9))
        timeout=self.remaining(phase_end)-GRACE-RECEIPT
        if timeout<=0:raise TimeoutError()
        try:
            with (private/'logs'/(phase+'.log')).open('xb') as log:
                code=setup.run_group(argv,cwd=cwd,env=dict(environment(private),**(extra_env or {})),log=log,timeout=timeout,grace=GRACE)
        finally:self.arm(phase_end-RECEIPT*10**9 if end_ns is not None else None)
        if type(code) is not int or code!=0:
            error=RuntimeError('child_exit');error.exit_code=code;raise error
        return code


def context_read(path,identity):
    raw=read_bytes(path,131072);need(assets.digest(identity) and assets.sha(raw)==identity)
    context=assets.json_bytes(raw,limit=131072)
    need(type(context) is dict and set(context)=={'schema','private','evidence','checkout_commit','started_ns','deadline_ns',
        'contract_sha256','source_sha256','git_blobs','generated_sha256'})
    need(type(context['schema']) is int and context['schema']==1)
    private=assets.safe_path(context['private'],directory=True);evidence=assets.safe_path(context['evidence'],directory=True)
    need(assets.safe_path(path)==private/'context.json' and private!=evidence and
         not private.is_relative_to(evidence) and not evidence.is_relative_to(private))
    need(type(context['started_ns']) is int and type(context['deadline_ns']) is int and
         context['deadline_ns']-context['started_ns']==TOTAL*10**9 and
         context['started_ns']<=time.monotonic_ns()<context['deadline_ns'])
    need(setup.canonical_commit(context['checkout_commit']) and type(context['git_blobs']) is dict and
         set(context['git_blobs'])==set(context['source_sha256'])|{CONTRACT} and
         all(setup.canonical_commit(v) for v in context['git_blobs'].values()))
    return context,private,evidence


def check_context(context,private,*,composed):
    frozen=contract_snapshot(composed=composed)
    need(frozen['contract_sha256']==context['contract_sha256'] and
         frozen['original_sources']==context['source_sha256'] and frozen['generated']==context['generated_sha256'])
    git_identity(context['checkout_commit'],context['git_blobs'],private)
    for name in frozen['generated'] if composed else ():
        original=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT,env=environment(private),timeout=10)
        need(assets.sha(original)==context['source_sha256'][name])
    need(ROOT.resolve()==(private/'checkout').resolve())
    return frozen


def compose(context,private):
    check_context(context,private,composed=False)
    from candidates.qwen2_resident_matrix.raw_kv_public_fresh import prepare
    result=prepare.prepare(private/'overlay',enable_raw_kv=True)
    need(result['generated']==context['generated_sha256'])
    for name,identity in result['generated'].items():
        target=assets.safe_path(ROOT/name);raw=read_bytes(private/'overlay'/name)
        need(assets.sha(raw)==identity and assets.file_sha(target)==context['source_sha256'][name])
        temporary=target.with_name(target.name+'.launch-pending')
        with temporary.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temporary,target)
    check_context(context,private,composed=True)


def validate_actual(value,sources):
    need(type(value) is dict and value.get('status')=='PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES' and
         value.get('native_acceptance')=='PASS_OBSERVED_ONLY' and value.get('actual_dataflow_pass') is True and
         value.get('full_29_node_acceptance') is False and type(value.get('rows')) is int and value['rows']==16 and
         value.get('enable_raw_kv') is True and value.get('fresh_profile') is True and value.get('old_pass_inherited') is False and
         value.get('rtl_executed') is False and value.get('scala_executed') is False and
         value.get('source_sha256')==sources and value.get('source_sha256_after')==sources)
    comparison=value['comparison'];need(comparison['fixed_arithmetic_pass'] is True and comparison['full_29_node_acceptance'] is False)
    need(comparison['acceptance_requires_all_assigned_official_observed_node_gates'] is True and
         comparison['official_target']=='official_self_cache')
    official=comparison['methods']['official_self_cache'];stages=official['stages']
    need(official['failed_stages']==[] and official['numerical_status']=='PASS_OBSERVED_ONLY' and
         set(stages)==set(assets.shapes())-{'mask'})
    execution=value['execution'];host=execution['host'];counts=host['accepted'];terminal=host['launch_result']
    need(execution['status']=='PUBLIC21_PC0_20_SOFTWARE_EXECUTED' and execution['full_block_software_model_executed'] is True and
         execution['same_owner_and_banks'] is True and execution['same_physical_memory_and_services'] is True and
         host['reset_required'] is False and terminal['status'] is None and type(terminal['completed']) is int and
         terminal['completed']==21 and type(terminal['jobs']) is int and terminal['jobs']==17)
    for name,want in (('completion_fire',21),('request_fire',17),('owner_result_fire',17),('result_fire',1)):
        need(type(counts[name]) is int and counts[name]==want)
    need(type(counts['raw_kv_parent_edges']) is int and counts['raw_kv_parent_edges']>0 and
         [item['pc'] for item in host['completions']]==list(range(21)) and
         all(type(item['pc']) is int and item['status'] is None for item in host['completions']))
    attention=[item['report'] for item in execution['reports'] if item['kind']=='Attention' and
               item['pcs']==[10,11,12] and all(type(pc) is int for pc in item['pcs'])]
    need(len(attention)==1)
    fence=attention[0]['final_ack_fence'];traffic=attention[0]['accepted']
    need(fence['terminal_strictly_after_final_ack'] is True and type(fence['final_ack_tick']) is int and
         type(fence['terminal_tick']) is int and fence['terminal_tick']>fence['final_ack_tick'] and
         type(traffic['requests']) is int and type(traffic['responses']) is int and traffic['requests']>0 and traffic['requests']==traffic['responses'])
    assigned=0
    for name,stage in stages.items():
        need(stage['metrics']['finite'] is True and type(stage['observed_elements']) is int and stage['observed_elements']>0)
        if name=='softmax_fp32':need(stage['verdict']['passed'] is None and stage['verdict']['status']=='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE')
        else:need(stage['verdict']['passed'] is True);assigned+=1
    need(assigned==27 and len(stages)==28)
    return dict(assigned_official_gates=27,observed_fields=28,full_29_node_acceptance=False,
        native_acceptance='PASS_OBSERVED_ONLY',actual_dataflow_pass=True,fixed_arithmetic_pass=True)


def canonical_actual(value):
    """Match original JSON serialization (including tuples), rejecting nonfinite data."""
    return assets.json_bytes(assets.encoded(value),limit=2*1024*1024)


def check_actual_json(path,actual,sources):
    """Validate both representations, preserving bool/int/float distinctions."""
    validate_actual(actual,sources)
    raw=read_bytes(path,2*1024*1024)
    saved=assets.json_bytes(raw,limit=2*1024*1024)
    validate_actual(saved,sources)
    need(assets.same(saved,canonical_actual(actual)))
    return assets.sha(raw)


def expected_entry_sources(frozen):
    pins=assets.read_json(ROOT/'candidates/qwen2_resident_matrix/raw_kv_public_fresh/pins.json')
    names=pins['source_paths']
    need(type(names) is list and len(names)==183 and len(set(names))==183 and set(names)<=set(frozen['sources']))
    return {name:frozen['sources'][name] for name in names}


def numeric(context,private,*,deadline_ns=None):
    """One supervised child: the 930s envelope already includes admission/preparation."""
    from . import admission
    if deadline_ns is None:
        raw=os.environ.get('QWEN2_PUBLIC_NUMERIC_DEADLINE_NS','')
        need(raw.isdecimal());deadline_ns=int(raw)
    need(type(deadline_ns) is int and deadline_ns<=context['deadline_ns'])
    def remaining():
        if time.monotonic_ns()>=deadline_ns:raise TimeoutError()
    remaining()
    before=check_context(context,private,composed=True)
    identity=admission.verify_setup(private/'assets',private/'setup_evidence/summary.json',
        checkout_commit=context['checkout_commit'],enable_raw_kv=True,rows=16)
    remaining()
    entry=importlib.import_module('candidates.qwen2_resident_matrix.dense_block_reduce.check_public_numeric')
    path,snapshot=entry.prepare(private/'snapshot',identity.library_receipt,None,None,rows=16,
        enable_raw_kv=True,fresh_profile=True,fresh_manifest=identity.manifest,fresh_manifest_sha256=identity.manifest_sha256)
    admission.revalidate(identity);remaining()
    need(snapshot['source_sha256']==expected_entry_sources(before)==entry.source_hashes(enable_raw_kv=True,fresh_profile=True))
    actual=entry.run(private/'actual',path,assets.file_sha(path),wall_budget=900,enable_raw_kv=True,fresh_profile=True)
    remaining()
    result=validate_actual(actual,snapshot['source_sha256'])
    # Durable diagnostic checkpoint only: runtime gates passed, but saved JSON
    # consistency, identity revalidation and child completion are still pending.
    validated=dict(result,schema=1,status=VALIDATED,rows=16,enable_raw_kv=True,fresh_profile=True,
        postflight_complete=False,numerical_acceptance=False,
        runtime_actual_sha256=assets.sha(assets.encoded(canonical_actual(actual))),
        launch_contract_sha256=context['contract_sha256'],setup_receipt_sha256=identity.receipt_sha256,
        snapshot_sha256=assets.file_sha(path),source_manifest_sha256=assets.sha(assets.encoded(before['sources'])),
        actual_source_manifest_sha256=assets.sha(assets.encoded(snapshot['source_sha256'])))
    remaining();setup.atomic_json(private/'numeric.validated.json',validated,8192);remaining()
    actual_receipt_sha256=check_actual_json(private/'actual/summary.json',actual,snapshot['source_sha256'])
    admission.revalidate(identity);need(check_context(context,private,composed=True)==before)
    result.update(schema=1,status=PASS,rows=16,enable_raw_kv=True,fresh_profile=True,
        launch_contract_sha256=context['contract_sha256'],setup_receipt_sha256=identity.receipt_sha256,
        actual_receipt_sha256=actual_receipt_sha256,snapshot_sha256=assets.file_sha(path),
        source_manifest_sha256=assets.sha(assets.encoded(before['sources'])),
        actual_source_manifest_sha256=assets.sha(assets.encoded(snapshot['source_sha256'])))
    remaining()
    setup.atomic_json(private/'numeric.complete.json',result,8192)
    remaining()
    return result


def safe_validated_receipt(private,context,frozen):
    """Allowlisted runtime-validation evidence; never an execution credential."""
    value=assets.read_json(private/'numeric.validated.json',limit=8192)
    fixed=dict(schema=1,status=VALIDATED,rows=16,enable_raw_kv=True,fresh_profile=True,
        postflight_complete=False,numerical_acceptance=False,assigned_official_gates=27,
        observed_fields=28,full_29_node_acceptance=False,native_acceptance='PASS_OBSERVED_ONLY',
        actual_dataflow_pass=True,fixed_arithmetic_pass=True)
    hashes={'runtime_actual_sha256','launch_contract_sha256','setup_receipt_sha256','snapshot_sha256',
            'source_manifest_sha256','actual_source_manifest_sha256'}
    need(type(value) is dict and set(value)==set(fixed)|hashes)
    need(all(assets.same(value[key],want) for key,want in fixed.items()))
    need(all(assets.digest(value[key]) for key in hashes))
    need(value['launch_contract_sha256']==context['contract_sha256'] and
         value['source_manifest_sha256']==assets.sha(assets.encoded(frozen['sources'])) and
         value['actual_source_manifest_sha256']==assets.sha(assets.encoded(expected_entry_sources(frozen))) and
         value['setup_receipt_sha256']==assets.file_sha(private/'assets/SETUP.json'))
    raw=read_bytes(private/'snapshot/SNAPSHOT.json',2*1024*1024)
    snapshot=assets.json_bytes(raw,limit=2*1024*1024)
    need(value['snapshot_sha256']==assets.sha(raw) and
         assets.same(snapshot['source_sha256'],expected_entry_sources(frozen)))
    return value


def safe_numeric_receipt(private,context,frozen):
    value=assets.read_json(private/'numeric.complete.json',limit=8192)
    expected={'schema','status','rows','enable_raw_kv','fresh_profile','launch_contract_sha256','setup_receipt_sha256',
        'actual_receipt_sha256','snapshot_sha256','source_manifest_sha256','actual_source_manifest_sha256',
        'assigned_official_gates','observed_fields','full_29_node_acceptance','native_acceptance','actual_dataflow_pass','fixed_arithmetic_pass'}
    need(type(value) is dict and set(value)==expected)
    for key,want in dict(schema=1,status=PASS,rows=16,enable_raw_kv=True,fresh_profile=True,assigned_official_gates=27,
        observed_fields=28,full_29_node_acceptance=False,native_acceptance='PASS_OBSERVED_ONLY',actual_dataflow_pass=True,fixed_arithmetic_pass=True).items():
        need(type(value[key]) is type(want) and value[key]==want)
    for key in expected:
        if key.endswith('sha256'):need(assets.digest(value[key]))
    need(value['launch_contract_sha256']==context['contract_sha256'] and
         value['source_manifest_sha256']==assets.sha(assets.encoded(frozen['sources'])) and
         value['actual_receipt_sha256']==assets.file_sha(private/'actual/summary.json') and
         value['setup_receipt_sha256']==assets.file_sha(private/'assets/SETUP.json') and
         value['snapshot_sha256']==assets.file_sha(private/'snapshot/SNAPSHOT.json'))
    actual=assets.read_json(private/'actual/summary.json',limit=2*1024*1024)
    snapshot=assets.read_json(private/'snapshot/SNAPSHOT.json',limit=2*1024*1024)
    need(snapshot['source_sha256']==expected_entry_sources(frozen))
    validate_actual(actual,snapshot['source_sha256'])
    need(value['actual_source_manifest_sha256']==assets.sha(assets.encoded(snapshot['source_sha256'])))
    return value


def summary_new(started):
    return dict(schema=1,status='NOT_RUN',phase='preflight',elapsed_seconds=round((time.monotonic_ns()-started)/1e9,6),
                rows=16,enable_raw_kv=True,fresh_profile=True,rtl_executed=False,scala_executed=False,full_29_node_acceptance=False)


def finish(evidence,summary,budget,error=None,sources=(),deadline_ns=None):
    if error is not None:
        summary.update(status='TIMEOUT' if isinstance(error,(TimeoutError,subprocess.TimeoutExpired)) else
            'INTERRUPTED' if isinstance(error,(InterruptedError,KeyboardInterrupt)) else 'FAILED')
        summary.setdefault('diagnostic',diagnostic(error,summary['phase'],sources,getattr(error,'exit_code',None)))
    summary['elapsed_seconds']=round((time.monotonic_ns()-budget.started)/1e9,6)
    try:
        budget.arm(deadline_ns)
        if evidence is not None:
            for name in OUTPUTS:(evidence/(name+'.pending')).unlink(missing_ok=True)
            publish(evidence,summary)
        budget.remaining(deadline_ns)
    except BaseException:
        summary['status']='TIMEOUT' if time.monotonic_ns()>=min(budget.end,deadline_ns or budget.end) else 'FAILED'
        if evidence is not None:
            try:(evidence/'summary.json').unlink(missing_ok=True)
            except OSError:pass
    finally:budget.close()
    return (0 if summary['status']==PASS else 1),summary


def bootstrap(private,evidence,commit):
    started=time.monotonic_ns();budget=Budget(started,started+TOTAL*10**9)
    summary=summary_new(started);out=None;frozen={}
    try:
        budget.arm();need(setup.canonical_commit(commit));frozen=contract_snapshot()
        git_identity(commit,frozen['git_blobs'],Path(private))
        private,out=setup.fresh_directories(private,evidence)
        (private/'logs').mkdir();(private/'tmp').mkdir()
        context=dict(schema=1,private=str(private),evidence=str(out),checkout_commit=commit,started_ns=started,
            deadline_ns=budget.end,contract_sha256=frozen['contract_sha256'],source_sha256=frozen['original_sources'],
            git_blobs=frozen['git_blobs'],generated_sha256=frozen['generated'])
        setup.atomic_json(private/'context.json',context,131072)
        setup.atomic_json(out/'source_hashes.json',dict(schema=1,launch_contract_sha256=frozen['contract_sha256'],
            source_sha256=frozen['sources'],generated_sha256=frozen['generated']),131072)
        summary.update(status='RUNNING',phase='clone');publish(out,summary)
        budget.command(['git','clone','--no-local','--no-checkout','--',str(ROOT),str(private/'checkout')],
            private=private,cwd=ROOT,phase='clone',cap=45)
        budget.command(['git','-c','core.hooksPath=/dev/null','checkout','--detach',commit],
            private=private,cwd=private/'checkout',phase='checkout',cap=30)
        summary['phase']='compose';publish(out,summary)
        identity=assets.sha(assets.encoded(context))
        command=[sys.executable,'-B','-m',MODULE,'--internal-compose','--context',str(private/'context.json'),'--context-sha256',identity]
        budget.command(command,private=private,cwd=private/'checkout',phase='compose',cap=60)
        need(contract_snapshot()==frozen)
        budget.disarm()
        # Same PID and same absolute deadline; setup retains sole inner-group ownership.
        os.chdir(private/'checkout')
        os.execve(sys.executable,[sys.executable,'-B','-m',MODULE,'--resume','--context',str(private/'context.json'),
            '--context-sha256',identity],environment(private))
        raise RuntimeError('exec_returned')
    except BaseException as error:return finish(out,summary,budget,error,frozen.get('sources',{}))


def project_setup_failure(summary,value,sources):
    statuses={'NOT_RUN','SETUP_FAILED','SETUP_TIMEOUT','SETUP_INTERRUPTED'}
    need(type(value) is dict and value.get('status') in statuses)
    summary['setup_status']=value['status']
    if value.get('phase') in setup.PHASES:summary['setup_phase']=value['phase']
    if value.get('reason') in setup.REASONS:summary['setup_reason']=value['reason']
    if 'diagnostic' in value and value.get('phase') in setup.PHASES:
        summary['diagnostic']=setup.validate_diagnostic(value['diagnostic'],value['phase'],sources)


def resume(context,private,evidence):
    budget=Budget(context['started_ns'],context['deadline_ns']);summary=summary_new(budget.started);frozen={};numeric_end=None
    try:
        budget.arm();frozen=check_context(context,private,composed=True)
        summary.update(status='RUNNING',phase='setup',launch_contract_sha256=context['contract_sha256']);publish(evidence,summary)
        # Published setup rejects inherited timers and cleans every producer itself.
        budget.disarm()
        code,setup_summary=setup.run(private/'assets',private/'setup_evidence',checkout_commit=context['checkout_commit'],
            enable_raw_kv=True,deadline_ns=min(budget.end,time.monotonic_ns()+SETUP_BUDGET*10**9))
        budget.arm()
        if code!=0:
            project_setup_failure(summary,setup_summary,frozen['sources'])
            error=RuntimeError('setup_exit');error.exit_code=code;raise error
        need(setup_summary['status']==setup.SETUP_STATUS)
        need(check_context(context,private,composed=True)==frozen)
        summary['phase']='numeric';publish(evidence,summary)
        numeric_end=min(budget.end,time.monotonic_ns()+NUMERIC_BUDGET*10**9)
        numeric_deadline=numeric_end-(GRACE+RECEIPT)*10**9
        budget.command([str(private/'assets/venv/bin/python'),'-B','-m',MODULE,'--internal-numeric',
            '--context',str(private/'context.json'),'--context-sha256',assets.file_sha(private/'context.json')],
            private=private,cwd=ROOT,phase='numeric',cap=NUMERIC_BUDGET,
            extra_env={'QWEN2_PUBLIC_NUMERIC_DEADLINE_NS':str(numeric_deadline)},end_ns=numeric_end)
        result=safe_numeric_receipt(private,context,frozen)
        need(check_context(context,private,composed=True)==frozen)
        summary.update(result,phase='finalize')
        return finish(evidence,summary,budget,sources=frozen['sources'],deadline_ns=numeric_end)
    except BaseException as error:
        if summary['phase']=='numeric' and numeric_end is not None and time.monotonic_ns()<numeric_end-RECEIPT*10**9:
            try:
                budget.arm(numeric_end-RECEIPT*10**9)
                summary['validated_actual']=safe_validated_receipt(private,context,frozen)
            except Exception:pass
            try:
                budget.arm(numeric_end-RECEIPT*10**9)
                failure=assets.read_json(private/'numeric.failure.json',limit=2048)
                summary['diagnostic']=setup.validate_diagnostic(failure,'numeric',frozen.get('sources',{}))
                if type(getattr(error,'exit_code',None)) is int:summary['diagnostic']['exit_code']=error.exit_code
            except Exception:pass
        return finish(evidence,summary,budget,error,frozen.get('sources',{}),deadline_ns=numeric_end)


def main(argv=None):
    context={};private=None
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true');p.add_argument('--private',type=Path);p.add_argument('--evidence',type=Path)
    p.add_argument('--checkout-commit');p.add_argument('--resume',action='store_true')
    p.add_argument('--internal-compose',action='store_true');p.add_argument('--internal-numeric',action='store_true')
    p.add_argument('--context',type=Path);p.add_argument('--context-sha256');a=p.parse_args(argv)
    try:
        internal=sum((a.resume,a.internal_compose,a.internal_numeric))
        if internal:
            need(internal==1 and not a.execute and os.environ.get('QWEN2_PUBLIC_RUN_CHILD')=='1')
            context,private,evidence=context_read(a.context,a.context_sha256)
            if a.internal_compose:compose(context,private);return 0
            if a.internal_numeric:numeric(context,private);return 0
            code,summary=resume(context,private,evidence)
        else:
            need(a.execute and a.private is not None and a.evidence is not None and setup.canonical_commit(a.checkout_commit))
            need(os.environ.get('GITHUB_RUN_ATTEMPT','1')=='1')
            if 'GITHUB_SHA' in os.environ:need(os.environ['GITHUB_SHA']==a.checkout_commit)
            code,summary=bootstrap(a.private,a.evidence,a.checkout_commit)
        print(json.dumps(summary,sort_keys=True,allow_nan=False));return code
    except BaseException as error:
        if a.internal_numeric or a.internal_compose:
            traceback.print_exc()  # captured private log only
            if private is not None:
                try:
                    phase='numeric' if a.internal_numeric else 'compose'
                    failure=diagnostic(error,phase,context.get('source_sha256',{}))
                    setup.atomic_json(private/(phase+'.failure.json'),failure,2048)
                except BaseException:pass
        else:print(json.dumps(dict(schema=1,status='NOT_RUN',diagnostic=diagnostic(error,'preflight',OWN)),sort_keys=True))
        return 1


if __name__=='__main__':raise SystemExit(main())
