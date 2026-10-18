#!/usr/bin/env python3
"""Source-only fixed firtool acquisition plus one member, never binary execution."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PLAN_SHA256 = 'd3f217a299840117e3758058271f500d1f25e986ac078ae64bc39d61d047d8f1'
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
        ('resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))',
         'resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))'),
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


def preflight(repo, acquisition):
    p=plan(); repo=clean(repo); acquisition=clean(acquisition)
    require(repo.is_dir() and acquisition.is_dir(), 'existing explicit source roots required')
    raw=checked(repo/p['supervisor_source']['repository_path'],
                {key:p['supervisor_source'][key] for key in ('bytes','sha256')})
    projected, identities=project_supervisor(raw)
    frozen={name:checked(acquisition/name,pin) for name,pin in p['acquisition_files'].items()}
    frozen['acquire_firtool_member.py']=checked(HERE/'acquire_firtool_member.py',p['member_helper'])
    for group, budget in p['groups'].items():
        item=json.loads(frozen['plans/'+group+'.json'])
        require(item['limits']['total_transfer_bytes']==budget['byte_cap'] and
                item['limits']['elapsed_check_seconds']==budget['total_wall_seconds'] and
                item['limits']['socket_timeout_seconds']==30, 'fixed acquisition budget drift')
    return p,frozen,projected,identities


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


def receipt_matches(receipt, selected):
    require(receipt['status']=='VERIFIED_OPAQUE_BYTES_ONLY' and receipt['group']==selected['group'], 'acquisition status')
    for key in ('extracted','installed','executed','host_compilation_or_rtl_evidence'):
        require(receipt[key] is False, 'unearned execution claim')
    rows=receipt['artifacts']; expected=selected['artifacts']
    require(len(rows)==len(expected), 'artifact receipt count')
    for row,pin in zip(rows,expected):
        require(row['relative_destination']==pin['relative_destination'] and row['sha256']==pin['sha256'] and
                row['origin_url']==pin['url'] and row['transport']==selected['transport'], 'artifact receipt identity')
        require(type(row['size_bytes']) is int and 0<=row['size_bytes']<pin['max_transfer_bytes'] and
                pin['known_size_bytes'] in (None,row['size_bytes']), 'artifact receipt size')
    require(receipt['received_bytes']==sum(row['size_bytes'] for row in rows) and
            receipt['received_bytes']<=selected['limits']['total_transfer_bytes'], 'received byte receipt total')


def member_receipt_matches(root,p,receipt):
    root=clean(root);m=clean(root/'MEMBER.json')
    require(m.is_file() and m.stat().st_size<=65536,'bounded member receipt')
    raw=m.read_bytes();member=json.loads(raw);policy=p['member_policy']
    require(member['status']=='MEMBER_BYTES_PREPARED_PENDING_OUTER_EXIT0' and member['terminal_success'] is False,'member state')
    require(member['member_name']==policy['allowlist_member'] and member['extracted_member_count']==1,'single allowlist member')
    require(member['binary_relative_destination']=='firtool' and member['archive_relative_destination']=='llvm-firtool-1.62.1-linux-x64.jar','fixed member paths')
    require(member['archive_sha256']==policy['archive_sha256'] and member['binary_sha256']==policy['binary_sha256'],'member pins')
    require(member['archive_bytes']==receipt['received_bytes']==member['received_bytes'],'archive receipt size binding')
    require(member['archive_receipt_sha256']==hashlib.sha256((root/'ACQUISITION.json').read_bytes()).hexdigest(),'archive receipt binding')
    for key in ('binary_executed','installed','rtl_generated','host_executed'):require(member[key] is False,'unearned member execution')
    binary=clean(root/'firtool');archive=clean(root/member['archive_relative_destination'])
    require(binary.is_file() and 0<binary.stat().st_size==member['binary_bytes']<=policy['member_cap_bytes'],'member actual size')
    require(archive.is_file() and archive.stat().st_size==member['archive_bytes']<policy['archive_transfer_cap_bytes'],'archive actual size')
    require((binary.stat().st_mode&0o7777)==0o600 and member['binary_mode_octal']=='0600','member non-executable0600')
    with binary.open('rb') as stream:content=stream.read(policy['member_cap_bytes']+1)
    require(len(content)==member['binary_bytes'] and hashlib.sha256(content).hexdigest()==policy['binary_sha256'],'member postflight actual SHA')
    entries=list(root.iterdir())
    allowed={'llvm-firtool-1.62.1-linux-x64.jar','ACQUISITION.json','firtool','MEMBER.json'}
    require({x.name for x in entries}==allowed and all(x.is_file() and not x.is_symlink() for x in entries),'exact successful artifact inventory')
    return member


def execute(group, repo, acquisition, output, started):
    p=plan(); budget=p['groups'][group]
    work_stop=started+budget['work_deadline_offset_seconds']; stop=started+budget['total_wall_seconds']
    alarm_available()  # Query only; refuse before any filesystem/process side effect.
    previous=signal.signal(signal.SIGALRM,expired)
    output_created=False; runner=None
    try:
        arm(work_stop)
        p,frozen,projected,identities=preflight(repo,acquisition)
        output=clean(output); repo=clean(repo); acquisition=clean(acquisition)
        require(output.parent.is_dir() and not output.exists(), 'fresh existing-parent output required')
        require(not any(output.is_relative_to(x) or x.is_relative_to(output) for x in (repo,acquisition.parent,HERE)),
                'output must be disjoint from repository and source candidates')
        output.mkdir(mode=0o700);output_created=True
        source=output/'source'/'acquisition';source.mkdir(parents=True)
        for name,raw in frozen.items():
            target=source/name;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as handle:handle.write(raw)
        runner=supervisor(projected)
        command=[sys.executable,'-I','-S','-B',str(source/'acquire_firtool_member.py'),
                 '--acquisition-source',str(source),'--repository',str(repo),
                 '--output-root',str(output/'artifacts'),'--execute-reviewed-acquisition']
        runner['save'](output/'GATE_PLAN_RECEIPT.json', {'status':'STARTED_NOT_ACQUIRED','group':group,
            'gate_plan_sha256':PLAN_SHA256,'budget':budget,'projected_functions':identities,
            'platform_environment_inherited_not_logged':True})
        failure=None; record=None
        try:
            remaining=work_stop-time.monotonic();require(remaining>0,'work budget exhausted before spawn')
            record,_=runner['bounded']('acquire',command,output,output,remaining,budget['cpu_seconds'])
        except BaseException as error:
            failure=error
        # No phase gets a fresh total budget. Published cleanup has at most five
        # seconds; this timer covers the remaining receipt/postflight interval.
        arm(stop)
        if failure is not None:raise failure
        receipt_path=clean(output/'artifacts'/'ACQUISITION.json')
        require(not (output/'artifacts'/'FAILED.json').exists(), 'conflicting acquisition terminal records')
        require(receipt_path.stat().st_size<=65536,'acquisition receipt cap')
        receipt=json.loads(receipt_path.read_bytes())
        receipt_matches(receipt,json.loads(frozen['plans/'+group+'.json']))
        member=member_receipt_matches(output/'artifacts',p,receipt)
        for name,raw in frozen.items():
            checked(source/name,digest(raw))
        require(time.monotonic()<stop,'final deadline exceeded')
        result={'status':'EVIDENCE_PENDING_OUTER_EXIT0','group':group,
                'terminal_success':False,
                'acceptance_requires':'independent outer exit0 plus elapsed-budget and receipt review',
                'child_cleanup_confirmed':record['cleanup_confirmed'],'packages_executed':False,
                'source_assembled':False,'hardware_elaborated':False,'received_bytes':receipt['received_bytes'],
                'member':member,'binary_executed':False,'installed':False,
                'entry_to_postflight_seconds':round(time.monotonic()-started,6),
                'post_commit_cleanup_warning_present':(output/'artifacts'/'CLEANUP_WARNING.json').exists()}
        runner['save'](output/'RESULT.json',result)
        require(time.monotonic()<stop,'final receipt completed after absolute deadline')
        return result
    except BaseException as error:
        if output_created and runner is not None:
            try:
                arm(stop)
                runner['save'](output/'RESULT.json',{'status':'FAIL_PRESERVED_NO_RETRY','error_type':type(error).__name__,
                                                  'packages_executed':False})
            except BaseException:pass
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


def main():
    started=time.monotonic()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--acquisition-source',type=Path,required=True)
    parser.add_argument('--group',choices=('firtool',),required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--execute-reviewed-acquisition',action='store_true')
    args=parser.parse_args()
    if args.execute_reviewed_acquisition:
        require(args.output is not None,'fresh output required')
        result=execute(args.group,args.repo,args.acquisition_source,args.output,started)
    else:
        require(args.output is None,'source check creates no output')
        p,_,_,_=preflight(args.repo,args.acquisition_source)
        result={'status':'SOURCE_PREFLIGHT_ONLY','group':args.group,'budget':p['groups'][args.group],
                'child_started':False,'network_started':False}
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use python -I -S -B')
    main()
