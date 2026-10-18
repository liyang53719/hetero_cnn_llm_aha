#!/usr/bin/env python3
"""Fixed official source acquisition gate; selected Git blobs only, no build/execution."""
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
PLAN_SHA256 = '0364eca36b872927d3032223d968699af5e73c4e316a161b031e3d5d5999545f'
PINNED_TOTAL = 11747893
PINNED_COUNT = 473
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
        ('resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024)',
         'resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024)'),
        ("if record['log_bytes'] > 65536:", "if record['log_bytes'] > 131072:"),
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
    require(set(frozen)=={'acquire_official_source.py','SOURCE_PLAN.json','acquire_base.py','FIXED_CORE_MEMBERS.json'},'fixed four-source snapshot')
    require(checked(repo/p['acquirer_repository_path'],p['worker_files']['acquire_base.py'])==frozen['acquire_base.py'],'original acquirer/snapshot mismatch')
    selected=json.loads(frozen['FIXED_CORE_MEMBERS.json']);policy=json.loads(frozen['SOURCE_PLAN.json'])
    require(selected['revision']==policy['commit']==p['commit'] and selected['tree_sha']==policy['tree']==p['tree'],'fixed selected commit/tree')
    require(selected['count']==len(selected['members'])==PINNED_COUNT and selected['blob_bytes']==sum(x['bytes'] for x in selected['members'])==PINNED_TOTAL,'fixed473 member totals')
    require(policy['limits']==p['worker_limits'],'fixed worker policy')
    require(policy['archive_sha256_before_fetch'] is None and policy['prefix_status']=='EXACT_UNTESTED_HYPOTHESIS' and policy['redirect_status']=='EXACT_UNTESTED_HYPOTHESIS','quarantine identity and unmeasured transport boundary')
    return p,frozen,projected,identities


def freeze(path, raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)


def postflight(root, table, policy, pins):
    root=clean(root)
    files={'SOURCE.json','source.tar.gz'}|{'verilator/'+x['path'] for x in table['members']}
    directories={'verilator'}
    for name in files:
        directories.update(str(x) for x in Path(name).parents if str(x)!='.')
    seen_files=set();seen_dirs=set();total_tree=0
    for parent,dirs,names in os.walk(root,followlinks=False):
        require(len(seen_dirs)+len(dirs)<=1024 and len(seen_files)+len(names)<=1024,'finite selected output inventory')
        for name in dirs:
            path=Path(parent)/name;require(not path.is_symlink() and stat.S_ISDIR(path.lstat().st_mode),'regular source directory')
            seen_dirs.add(path.relative_to(root).as_posix())
        for name in names:
            path=Path(parent)/name;meta=path.lstat()
            require(stat.S_ISREG(meta.st_mode) and not path.is_symlink() and stat.S_IMODE(meta.st_mode)==0o600,'regular nonexecutable0600 source data')
            total_tree+=meta.st_size;require(total_tree<=80*1024*1024,'artifact tree soft limit80MiB')
            seen_files.add(path.relative_to(root).as_posix())
    require(seen_files==files and seen_dirs==directories,'exact selected output inventory; leftovers are incomplete')
    receipt_path=root/'SOURCE.json';require(receipt_path.stat().st_size<=256*1024,'source receipt cap256KiB')
    receipt=json.loads(receipt_path.read_bytes())
    require(receipt['status']=='SELECTED_SOURCE_PREPARED_PENDING_OUTER_EXIT0_AND_REVIEW' and receipt['terminal_success'] is False,'nonterminal selected source evidence')
    require(receipt['commit']==table['revision'] and receipt['tree']==table['tree_sha'],'receipt commit/tree')
    require(receipt['fixed_members_sha256']==pins['FIXED_CORE_MEMBERS.json']['sha256'] and receipt['fixed_plan_sha256']==pins['SOURCE_PLAN.json']['sha256'],'receipt fixed input pins')
    require(receipt['archive_api_url']==policy['archive_api_url'] and receipt['exact_archive_prefix']==policy['exact_prefix'],'fixed official source origin/root')
    require(receipt['transport']=='default-platform-HTTPS-one-exact-official-302-no-retry','source transport scope')
    require(receipt['archive_complete'] is True and receipt['cleanup_errors']==[],'complete archive and clean worker')
    for name in ('installed','source_executed','native_executed','host_compilation_or_rtl_evidence','archive_sha256_is_independent_provenance'):
        require(receipt[name] is False,'unearned source execution/provenance claim')
    require(0<receipt['expanded_bytes']<=128*1024*1024 and 0<receipt['tar_entries']<=12000,'expanded source limits')
    archive=root/'source.tar.gz';size=archive.stat().st_size
    require(0<size<64*1024*1024 and size==receipt['received_bytes']==receipt['retained_archive_bytes'],'archive transfer bytes')
    digest=hashlib.sha256();count=0
    with archive.open('rb') as stream:
        while True:
            block=stream.read(65536)
            if not block:break
            count+=len(block);require(count<=size,'archive grew');digest.update(block)
    require(count==size and digest.hexdigest()==receipt['archive_sha256_observed'],'observed quarantine SHA unchanged')
    rows=receipt['verified_members'];require(len(rows)==PINNED_COUNT,'fixed verified member count')
    rows_by_path={x['path']:x for x in rows}
    require(len(rows_by_path)==len(rows) and set(rows_by_path)=={x['path'] for x in table['members']},'exact unique member receipt paths')
    total=0
    for pin in table['members']:
        row=rows_by_path[pin['path']];path=root/'verilator'/pin['path']
        require(row['bytes']==pin['bytes'] and row['git_blob_sha1']==pin['git_blob_sha'] and row['original_git_mode']==pin['mode'] and row['materialized_mode']=='0600','member fixed identity metadata')
        require(path.stat().st_size==pin['bytes']<=1024*1024,'member actual size cap')
        with path.open('rb') as stream:raw=stream.read(pin['bytes']+1)
        require(len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256_observed'],'member actual observed SHA256')
        git=hashlib.sha1(b'blob '+str(len(raw)).encode('ascii')+b'\0'+raw).hexdigest()
        require(git==pin['git_blob_sha'],'member independent fixed Git blob')
        total+=len(raw)
    require(total==receipt['selected_bytes']==PINNED_TOTAL,'fixed selected total bytes')
    return receipt


def execute(repo,worker,output,started):
    stop=started+420;prestop=started+10
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
        work_stop=min(now+400,started+410);arm(work_stop)
        command=[sys.executable,'-I','-S','-B',str(source/'acquire_official_source.py'),'--repository',str(repo),'--output-root',str(output/'artifacts'),'--shared-start-monotonic',str(started),'--work-deadline-monotonic',str(work_stop),'--execute-reviewed-acquisition']
        failure=None;record=None
        try:
            remaining=work_stop-time.monotonic();require(remaining>0,'work exhausted before spawn')
            record,_=runner['bounded']('acquire',command,output,output,remaining,400)
        except BaseException as error:failure=error
        arm(stop)
        if failure is not None:raise failure
        require(record['cleanup_confirmed'] and record['exit_code']==0,'original child exit and cleanup required')
        receipt=postflight(output/'artifacts',json.loads(frozen['FIXED_CORE_MEMBERS.json']),json.loads(frozen['SOURCE_PLAN.json']),p['worker_files'])
        for name,raw in frozen.items():
            checked(source/name,digest(raw));checked(worker/name,digest(raw))
        checked(repo/p['supervisor_source']['repository_path'],p['supervisor_source']['pin'])
        checked(repo/p['acquirer_repository_path'],p['worker_files']['acquire_base.py'])
        require(time.monotonic()<stop,'final shared deadline')
        result={'status':'EVIDENCE_PENDING_OUTER_EXIT0','terminal_success':False,'acceptance_requires':'original outer exit0, elapsed<=420 and independent selected-source actual review','received_bytes':receipt['received_bytes'],'selected_count':PINNED_COUNT,'selected_bytes':receipt['selected_bytes'],'archive_sha256_observed':receipt['archive_sha256_observed'],'archive_sha256_is_independent_provenance':False,'child_cleanup_confirmed':record['cleanup_confirmed'],'source_built':False,'source_executed':False,'native_executed':False,'host_executed':False,'entry_to_postflight_seconds':round(time.monotonic()-started,6)}
        runner['save'](output/'RESULT.json',result)
        require(time.monotonic()<stop,'final receipt completed after total420')
        return result
    except BaseException as error:
        if created and runner is not None:
            try:
                arm(stop);runner['save'](output/'FAILURE.json',{'status':'FAIL_PRESERVED_NO_RETRY','terminal_success':False,'error_type':type(error).__name__,'source_executed':False})
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
