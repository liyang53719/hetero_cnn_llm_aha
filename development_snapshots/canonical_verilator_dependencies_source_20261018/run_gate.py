#!/usr/bin/env python3
"""Fixed five-package acquisition gate; opaque bytes only, never installation/execution."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PLAN_SHA256 = '579b2f3020afd5b8a7325150edf6f5ef52698b63c49667c02bdd11ef2c612e68'
PINNED_TOTAL = 2466616
FUNCTIONS = ('require', 'save', 'group_state', 'observe_exit', 'bounded')


def require(ok, why):
    if not ok: raise ValueError(why)


def digest(raw):
    return {'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}


def clean(path):
    path=Path(path).absolute()
    require('..' not in path.parts and all(not x.is_symlink() for x in (path,*path.parents)), 'unsafe path')
    return path


def checked(path, pin):
    path=clean(path)
    require(path.is_file() and path.stat().st_size == pin['bytes'] <= 2*1024*1024, 'fixed source size')
    with path.open('rb') as stream: raw=stream.read(pin['bytes']+1)
    require(digest(raw)==pin, 'fixed source digest')
    return raw


def plan():
    raw=(HERE/'GATE_PLAN.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest()==PLAN_SHA256, 'fixed gate plan drift')
    return json.loads(raw)


def project_supervisor(raw):
    """Exact fixed function projection, with narrow policy/timer edits.

    WNOWAIT observation, anchored kill-before-reap, cleanup and receipts remain
    the published functions. No full runner module or native-test main is loaded.
    """
    tree=ast.parse(raw); lines=raw.splitlines(keepends=True)
    selected={node.name:b''.join(lines[node.lineno-1:node.end_lineno])
              for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in FUNCTIONS}
    require(tuple(selected)==FUNCTIONS, 'published function selection drift')
    before=selected['bounded'].decode()
    replacements=[
        ("env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})", 'env=None)'),
        ('        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))',
         '        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n'
         '        allowed = os.sched_getaffinity(0)\n'
         '        require(bool(allowed), "empty inherited CPU affinity")\n'
         '        os.sched_setaffinity(0, {min(allowed)})'),
        ('        finally:\n            if child is not None:',
         '        finally:\n            signal.setitimer(signal.ITIMER_REAL, 0)\n'
         '            if child is not None:')]
    after=before
    for old,new in replacements:
        require(after.count(old)==1, 'exact supervisor projection anchor')
        after=after.replace(old,new,1)
    restored=after
    for old,new in reversed(replacements):
        require(restored.count(new)==1, 'exact supervisor reverse projection')
        restored=restored.replace(new,old,1)
    require(restored==before, 'published supervisor reverse projection failed')
    selected['bounded']=after.encode()
    projected=b'\n\n'.join(selected[name] for name in FUNCTIONS)+b'\n'
    return projected, {name:digest(data) for name,data in selected.items()}


def supervisor(projected):
    # The projection was derived only from the same fixed source bytes above.
    namespace={'__builtins__':__builtins__, 'os':os, 'resource':resource,
               'signal':signal, 'subprocess':subprocess, 'time':time, 'json':json,
               'AS_LIMIT':512*1024*1024}
    exec(compile(projected,'published_WNOWAIT_projection','exec',dont_inherit=True),namespace)
    return namespace


def alarm_available():
    require(hasattr(signal,'pthread_sigmask'), 'signal-mask query unavailable')
    blocked=signal.pthread_sigmask(signal.SIG_BLOCK,[])
    require(signal.SIGALRM not in blocked, 'inherited SIGALRM block refused without changes')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0), 'inherited real timer refused without changes')


def expired(_signal,_frame):
    raise TimeoutError('shared absolute acquisition deadline')


def arm(deadline):
    remaining=deadline-time.monotonic()
    require(remaining>0, 'absolute acquisition deadline exhausted')
    signal.setitimer(signal.ITIMER_REAL,remaining)


def preflight(repo, worker):
    p=plan();repo=clean(repo);worker=clean(worker)
    require(repo.is_dir() and worker.is_dir(),'explicit existing input directories')
    raw=checked(repo/p['supervisor_source']['repository_path'],p['supervisor_source']['pin'])
    projected,identities=project_supervisor(raw)
    frozen={name:checked(worker/name,pin) for name,pin in p['worker_files'].items()}
    require(set(frozen)=={'acquire_dependencies.py','DEPENDENCY_PLAN.json','published_acquire.py'},'fixed three-source snapshot')
    require(checked(repo/p['acquirer_repository_path'],p['worker_files']['published_acquire.py'])==frozen['published_acquire.py'],'original acquirer/snapshot mismatch')
    selected=json.loads(frozen['DEPENDENCY_PLAN.json'])
    require(selected['group']=='debian-build-dependencies5' and selected['artifact_count']==len(selected['artifacts'])==5,'fixed five-package group')
    require(selected['limits']=={'elapsed_check_seconds':160,'socket_timeout_seconds':30,'total_transfer_bytes':4194304},'shared worker limits')
    require(sum(x['known_size_bytes'] for x in selected['artifacts'])==PINNED_TOTAL and all(0<x['known_size_bytes']<x['max_transfer_bytes']<=2097152 for x in selected['artifacts']),'exact package byte policy')
    return p,frozen,projected,identities


def freeze(path, raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)


def postflight(root, selected, plan_pin):
    root=clean(root)
    expected={x['relative_destination'] for x in selected['artifacts']}|{'ACQUISITION.json'}
    entries=list(root.iterdir())
    require({x.name for x in entries}==expected,'exact successful artifact inventory; cleanup leftovers are incomplete')
    for path in entries:
        mode=path.lstat().st_mode
        require(stat.S_ISREG(mode) and not path.is_symlink() and stat.S_IMODE(mode)==0o600,'regular nonexecutable0600 artifact')
    receipt_path=root/'ACQUISITION.json';require(receipt_path.stat().st_size<=65536,'receipt cap')
    receipt=json.loads(receipt_path.read_bytes())
    require(receipt['status']=='VERIFIED_OPAQUE_BYTES_ONLY' and receipt['group']==selected['group'],'worker evidence scope')
    require(receipt['fixed_plan_sha256']==plan_pin['sha256'] and receipt['terminal_success'] is False,'fixed plan/nonterminal contract')
    for name in ('extracted','installed','executed','host_compilation_or_rtl_evidence'):
        require(receipt[name] is False,'unearned package execution claim')
    require(len(receipt['artifacts'])==5,'five receipt rows')
    total=0
    for row,pin in zip(receipt['artifacts'],selected['artifacts']):
        require(row['relative_destination']==pin['relative_destination'] and row['origin_url']==pin['url'] and row['transport']==selected['transport'],'artifact origin/order')
        require(row['size_bytes']==pin['known_size_bytes'] and row['sha256']==pin['sha256'],'receipt size/SHA')
        path=root/pin['relative_destination'];require(path.stat().st_size==pin['known_size_bytes'],'artifact exact size')
        h=hashlib.sha256();count=0
        with path.open('rb') as stream:
            while True:
                chunk=stream.read(65536)
                if not chunk:break
                count+=len(chunk);require(count<=pin['known_size_bytes'],'artifact grew');h.update(chunk)
        require(count==pin['known_size_bytes'] and h.hexdigest()==pin['sha256'],'actual artifact SHA')
        total+=count
    require(total==receipt['received_bytes']==PINNED_TOTAL,'exact received total')
    return receipt


def execute(repo,worker,output,started):
    stop=started+180;prestop=started+10
    alarm_available();previous=signal.signal(signal.SIGALRM,expired)
    created=False;runner=None
    try:
        arm(prestop)
        p,frozen,projected,identities=preflight(repo,worker)
        output=clean(output);repo=clean(repo);worker=clean(worker)
        require(output.parent.is_dir() and not output.exists(),'fresh existing-parent output')
        require(not any(output.is_relative_to(x) or x.is_relative_to(output) for x in (repo,worker,HERE)),'output disjoint from all source directories')
        output.mkdir(mode=0o700);created=True;source=output/'source';source.mkdir(mode=0o700)
        for name,raw in frozen.items():freeze(source/name,raw)
        runner=supervisor(projected)
        runner['save'](output/'GATE_PLAN_RECEIPT.json',{'status':'STARTED_NOT_ACQUIRED','gate_plan_sha256':PLAN_SHA256,'projected_functions':identities,'budget':p['budget'],'platform_environment_inherited_not_logged':True})
        now=time.monotonic();require(now<prestop,'shared preflight10 exhausted')
        work_stop=min(now+160,started+170);arm(work_stop)
        command=[sys.executable,'-I','-S','-B',str(source/'acquire_dependencies.py'),'--repo',str(repo),'--output',str(output/'artifacts'),'--shared-start-monotonic',str(started),'--work-deadline-monotonic',str(work_stop),'--execute-reviewed-acquisition']
        failure=None;record=None
        try:
            remaining=work_stop-time.monotonic();require(remaining>0,'work exhausted before spawn')
            record,_=runner['bounded']('acquire',command,output,output,remaining,160)
        except BaseException as error:failure=error
        arm(stop)
        if failure is not None:raise failure
        require(record['cleanup_confirmed'] and record['exit_code']==0,'original child exit and cleanup required')
        receipt=postflight(output/'artifacts',json.loads(frozen['DEPENDENCY_PLAN.json']),p['worker_files']['DEPENDENCY_PLAN.json'])
        for name,raw in frozen.items():
            checked(source/name,digest(raw));checked(worker/name,digest(raw))
        checked(repo/p['supervisor_source']['repository_path'],p['supervisor_source']['pin'])
        checked(repo/p['acquirer_repository_path'],p['worker_files']['published_acquire.py'])
        require(time.monotonic()<stop,'final shared deadline')
        result={'status':'EVIDENCE_PENDING_OUTER_EXIT0','terminal_success':False,'acceptance_requires':'original outer exit0, elapsed<=180 and independent opaque-artifact actual review','received_bytes':receipt['received_bytes'],'artifact_count':5,'child_cleanup_confirmed':record['cleanup_confirmed'],'packages_extracted':False,'packages_installed':False,'packages_executed':False,'source_built':False,'host_executed':False,'entry_to_postflight_seconds':round(time.monotonic()-started,6)}
        runner['save'](output/'RESULT.json',result)
        require(time.monotonic()<stop,'final receipt completed after total180')
        return result
    except BaseException as error:
        if created and runner is not None:
            try:
                arm(stop);runner['save'](output/'FAILURE.json',{'status':'FAIL_PRESERVED_NO_RETRY','terminal_success':False,'error_type':type(error).__name__,'packages_executed':False})
            except BaseException:pass
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


def main():
    started=time.monotonic();parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True);parser.add_argument('--worker-source',type=Path,required=True)
    parser.add_argument('--output',type=Path);parser.add_argument('--execute-reviewed-acquisition',action='store_true')
    a=parser.parse_args()
    if a.execute_reviewed_acquisition:
        require(a.output is not None,'fresh output required');result=execute(a.repo,a.worker_source,a.output,started)
    else:
        require(a.output is None,'SOURCE preflight creates no output')
        p,_,_,_=preflight(a.repo,a.worker_source)
        result={'status':'SOURCE_PREFLIGHT_ONLY','budget':p['budget'],'child_started':False,'network_started':False}
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use python -I -S -B')
    main()
