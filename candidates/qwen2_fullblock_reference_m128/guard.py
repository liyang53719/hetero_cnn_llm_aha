#!/usr/bin/env python3
"""Default cold check; reviewed --mode/--run-id/--go launches exactly one bounded capture."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import recipe as R
import lifecycle as L


def processes():
    result = {}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            fields = (p/'stat').read_text().rsplit(')',1)[1].split()
            result[int(p.name)] = {'state':fields[0],'ppid':int(fields[1]),'pgrp':int(fields[2]),
                'start':int(fields[19]),'rss':max(0,int(fields[21]))*os.sysconf('SC_PAGE_SIZE')}
        except (FileNotFoundError,ProcessLookupError,PermissionError):
            continue
    return result


def tree_members(pid,known,supervisor=None,exclude=()):
    all_p = processes()
    selected = {p for p,v in all_p.items() if v['pgrp'] == pid or
        (p in known and known[p] == v['start']) or
        (supervisor is not None and v['ppid'] == supervisor and p not in exclude)}
    selected.add(pid)
    while True:
        extra = {p for p,v in all_p.items() if v['ppid'] in selected} - set(exclude)
        if extra <= selected:
            break
        selected |= extra
    live = {p:all_p[p] for p in selected if p in all_p and all_p[p]['state'] != 'Z'}
    known.update({p:v['start'] for p,v in live.items()})
    return live


def terminate_tree(pid,known,supervisor=None,exclude=()):
    # SIGKILL avoids children ignoring TERM; only this run's group/known lineage.
    live = tree_members(pid,known,supervisor,exclude)
    try:
        os.killpg(pid,signal.SIGKILL)
    except ProcessLookupError:
        pass
    for child,record in live.items():
        try:
            current = processes().get(child)
            if current is not None and current['start'] == record['start']:
                os.kill(child,signal.SIGKILL)
        except ProcessLookupError:
            pass
    return sorted(live)


def reap_descendants(worker_pid,known,supervisor,exclude=(),seconds=2):
    deadline = time.monotonic()+seconds
    reaped = []
    remaining = {}
    while True:
        for pid in list(known):
            if pid == worker_pid or pid in exclude:
                continue
            try:
                got,_ = os.waitpid(pid,os.WNOHANG)
                if got:
                    reaped.append(got)
            except ChildProcessError:
                pass
        live = tree_members(worker_pid,known,supervisor,exclude)
        current = processes()
        remaining = {pid:v for pid,v in current.items() if pid in known and
                     v['start'] == known[pid] and pid != worker_pid and pid not in exclude}
        if not remaining or time.monotonic() >= deadline:
            break
        if live:
            terminate_tree(worker_pid,known,supervisor,exclude)
        time.sleep(L.POLL_SECONDS)
    return {'reaped_descendant_pids':sorted(set(reaped)),
            'remaining_descendants':{str(pid):v for pid,v in remaining.items()},
            'cleanup_wait_limit_seconds':seconds}


def subreaper():
    libc = ctypes.CDLL(None,use_errno=True)
    if libc.prctl(36,1,0,0,0) != 0:  # Linux PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(),'cannot enable descendant cleanup')


def watchdog(worker_pid,parent_pid,stop_fd,out,deadline):
    """Independent wall/parent-liveness guard; never imports numerical packages."""
    os.set_blocking(stop_fd,False)
    start = time.monotonic()
    known = {}
    while True:
        live = tree_members(worker_pid,known,parent_pid,(os.getpid(),))
        reason = None
        if os.getppid() != parent_pid:
            reason = 'supervisor-disappeared'
        elif time.monotonic() > deadline:
            reason = 'independent-wall-watchdog'
        try:
            data = os.read(stop_fd,1)
            if data == b'1':
                return 0
            if data == b'':
                reason = 'supervisor-control-pipe-closed'
        except BlockingIOError:
            pass
        if reason:
            killed = terminate_tree(worker_pid,known,parent_pid,(os.getpid(),))
            try:
                L.write_new(R,out/'WATCHDOG.json',{'status':'FAILED_UNSEALED','reason':reason,
                    'stage':L.last_stage(R,out),'killed_pids':killed,'tracked_process_starts':known,
                    'wall_seconds':time.monotonic()-start})
            except OSError:
                pass
            return 3
        time.sleep(L.POLL_SECONDS)


def supervise(command,env,out,*,pass_fds=(),wall=L.WALL_SECONDS,rss=L.RSS_BYTES,
              pair_cap=72351744,run_cap=35651584,watchdog_enabled=True,excluded_pids=()):
    """Bound the numerical process tree, not stdlib preflight/postflight hashing."""
    subreaper()
    start = time.monotonic()
    child = watcher = selector = None
    stop_read = stop_write = None
    streams,known = {},{}
    peak,reason,cleanup = 0,None,[]
    excluded = tuple(excluded_pids)
    reaping = None
    try:
        child = subprocess.Popen(command,cwd=R.ROOT,env=env,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,pass_fds=pass_fds)
        # Every operation after successful Popen is covered by cleanup, including
        # partial watcher/selector/log setup. No worker is leaked on setup errors.
        stop_read,stop_write = os.pipe()
        if watchdog_enabled:
            watcher = subprocess.Popen([sys.executable,'-B',str(R.HERE/'guard.py'),'--watchdog',str(child.pid),
                str(os.getpid()),str(stop_read),str(out),str(start+wall)],cwd=R.ROOT,env=env,
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                pass_fds=(stop_read,),start_new_session=True)
            excluded = tuple(excluded_pids)+(watcher.pid,)
        os.close(stop_read);stop_read=None
        selector = selectors.DefaultSelector()
        for name,pipe in [('stdout',child.stdout),('stderr',child.stderr)]:
            os.set_blocking(pipe.fileno(),False)
            selector.register(pipe,selectors.EVENT_READ,name)
            streams[name] = {'bytes':0,'retained_bytes':0,'hash':hashlib.sha256(),
                             'file':(out/(name+'.log')).open('xb')}
        while selector.get_map() or child.poll() is None:
            elapsed = time.monotonic()-start
            live = tree_members(child.pid,known,os.getpid(),excluded)
            peak = max(peak,sum(v['rss'] for v in live.values()))
            if reason is None:
                if elapsed > wall:
                    reason = 'wall-limit'
                elif peak > rss:
                    reason = 'sampled-process-tree-rss-limit'
                elif L.bytes_under(out) > run_cap or L.bytes_under(out.parent) > pair_cap:
                    reason = 'disk-cap'
                elif sum(v['bytes'] for v in streams.values()) > L.LOG_EMITTED_LIMIT:
                    reason = 'emitted-log-limit'
                elif watcher and watcher.poll() is not None:
                    reason = 'independent-watchdog-exited'
                elif any(processes().get(pid,{}).get('state') in (None,'Z') for pid in excluded_pids):
                    reason = 'overall-watchdog-exited'
            if reason:
                cleanup = sorted(set(cleanup) | set(terminate_tree(child.pid,known,os.getpid(),excluded)))
            for key,_ in selector.select(L.POLL_SECONDS):
                data = os.read(key.fileobj.fileno(),65536)
                if not data:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                stream = streams[key.data]
                stream['bytes'] += len(data)
                stream['hash'].update(data)
                retained = data[:max(0,L.LOG_RETAIN_BYTES-stream['retained_bytes'])]
                stream['file'].write(retained)
                stream['file'].flush()
                stream['retained_bytes'] += len(retained)
        child.wait(timeout=2)
        leftovers = tree_members(child.pid,known,os.getpid(),excluded)
        if leftovers:
            reason = reason or 'unexpected-live-descendants'
            cleanup = sorted(set(cleanup) | set(terminate_tree(child.pid,known,os.getpid(),excluded)))
    except BaseException:
        if child is not None:
            terminate_tree(child.pid,known,os.getpid(),excluded)
            child.wait(timeout=2)
        raise
    finally:
        if selector is not None:
            selector.close()
        for stream in streams.values():
            stream['file'].close()
        if child is not None:
            for pipe in (child.stdout,child.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
        if stop_write is not None:
            try:
                os.write(stop_write,b'1')
            except BrokenPipeError:
                pass
            os.close(stop_write)
        if stop_read is not None:
            os.close(stop_read)
        if watcher is not None:
            try:
                watcher.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(watcher.pid,signal.SIGKILL)
                watcher.wait(timeout=2)
        if child is not None:
            reaping = reap_descendants(child.pid,known,os.getpid(),excluded)
            if reaping['remaining_descendants']:
                reason = reason or 'descendant-cleanup-incomplete'
    watchdog_record = None
    if watcher is not None:
        if (out/'WATCHDOG.json').exists():
            watchdog_record = {'identity':L.identity(out/'WATCHDOG.json'),
                               'receipt':R.parse((out/'WATCHDOG.json').read_bytes())}
            fired = watchdog_record['receipt']['reason']
            reason = reason or ('wall-limit' if fired == 'independent-wall-watchdog' else fired)
        elif watcher.returncode != 0:
            reason = reason or 'independent-watchdog-exited-without-receipt'
    return {'returncode':child.returncode,'limit_reason':reason,'wall_seconds':time.monotonic()-start,
        'peak_sampled_process_tree_rss_bytes':peak,'rss_is_os_hard_cap':False,
        'rss_scope':'numerical worker process group plus discovered/adopted descendants; excludes wrapper/watchdog',
        'wall_scope':'numerical worker lifetime including setup and pipe drain; excludes stdlib boundary preflight/postflight',
        'rss_poll_seconds':L.POLL_SECONDS,'rss_limit_bytes':rss,'wall_limit_seconds':wall,
        'independent_watchdog_enabled':watchdog_enabled,'independent_watchdog_record':watchdog_record,'tracked_process_starts':known,'cleanup_pids':cleanup,
        'descendant_cleanup':reaping,
        'logs':{name:{'total_bytes':v['bytes'],'sha256_all_observed_bytes':v['hash'].hexdigest(),
             'retained_bytes':v['retained_bytes'],'truncated':v['bytes']>v['retained_bytes'],
             'retained_sha256':L.identity(out/(name+'.log'))['sha256']} for name,v in streams.items()}}


def worker(fd,mode,out):
    try:
        import capture as C
        C.capture(R.ROOT,R.load_pins(),Path(out),stage=mode,recipe=R,capability_fd=int(fd))
        return 0
    except BaseException as error:
        print(json.dumps({'status':'WORKER_FAILED_UNSEALED','error_type':type(error).__name__,
                          'error':str(error)},allow_nan=False),file=sys.stderr,flush=True)
        return 2


def check_deadline(deadline,watchdog_pid=None):
    if watchdog_pid is not None:
        R.need(processes().get(watchdog_pid,{}).get('state') not in (None,'Z'), 'overall watchdog unavailable')
    R.need(time.monotonic() < deadline, 'overall 120s deadline exceeded; no seal')


def supervisor_watchdog(parent_pid,stop_fd,out,deadline):
    """Last-resort 122s guard covers parent preflight, child and postflight."""
    os.set_blocking(stop_fd,False)
    known = {}
    while True:
        tree_members(parent_pid,known,exclude=(os.getpid(),))
        reason = None
        if os.getppid() != parent_pid:
            reason = 'supervisor-disappeared'
        elif time.monotonic() >= deadline:
            reason = 'overall-122s-watchdog'
        try:
            data = os.read(stop_fd,1)
            if data == b'1':
                return 0
            if data == b'':
                reason = 'supervisor-control-pipe-closed'
        except BlockingIOError:
            pass
        if reason:
            killed = terminate_tree(parent_pid,known,exclude=(os.getpid(),))
            if out.is_dir() and not (out/'SEAL.json').exists():
                receipt = {'status':'FAILED_UNSEALED','reason':reason,'stage':L.last_stage(R,out),
                    'killed_pids':killed,'tracked_process_starts':known,'completion_seal_written':False,
                    'overall_wall_limit_seconds':120,'external_watchdog_deadline_seconds':122,
                    'partial_files':L.directory_inventory(R,out)}
                try:
                    L.write_new(R,out/'WATCHDOG.json',receipt)
                    if not (out/'FAILURE.json').exists():
                        L.write_new(R,out/'FAILURE.json',receipt)
                except OSError:
                    pass
            return 3
        time.sleep(L.POLL_SECONDS)


def run(mode,run_id,go_path):
    start = time.monotonic()  # Never reset after source/go/runtime/raw checks.
    deadline = start+L.WALL_SECONDS
    out = L.run_path(R,run_id,mode)
    read_fd,write_fd = os.pipe()
    watcher = None
    try:
        watcher = subprocess.Popen([sys.executable,'-B',str(R.HERE/'guard.py'),'--supervisor-watchdog',
            str(os.getpid()),str(read_fd),str(out),str(deadline+2)],cwd=R.ROOT,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            pass_fds=(read_fd,),start_new_session=True)
        os.close(read_fd);read_fd=None
        return run_body(mode,run_id,go_path,start,deadline,watcher.pid)
    finally:
        try:
            os.write(write_fd,b'1')
        except BrokenPipeError:
            pass
        os.close(write_fd)
        if read_fd is not None:
            os.close(read_fd)
        if watcher is not None:
            try:
                watcher.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(watcher.pid,signal.SIGKILL)
                watcher.wait(timeout=2)


def run_body(mode,run_id,go_path,start,deadline,outer_watchdog_pid):
    check_deadline(deadline,outer_watchdog_pid)
    R.require_supported_python()
    R.need(not any(n in sys.modules for n in ('torch','numpy','transformers')), 'cold wrapper required')
    pins = R.load_pins()
    R.source_check(R.ROOT,pins)
    check_deadline(deadline,outer_watchdog_pid)
    out = L.run_path(R,run_id,mode)
    R.need(not out.exists(), 'fresh output required; failed/successful runs are never overwritten or retried')
    go = L.validate_go(R,pins,go_path,run_id,mode)
    if mode == 'frozen':
        frozen = R.require_frozen_references(pins)
        R.need(frozen['bootstrap_manifest']['path'] != str((out/'REFERENCE.json').relative_to(R.ROOT)),
               'distinct frozen output required')
    R.need(L.bytes_under(out.parent)+pins['budget']['per_capture_cap_bytes'] <= pins['budget']['total_cap_bytes'],
           'pair must have room for a fresh bounded capture')
    check_deadline(deadline,outer_watchdog_pid)
    out.mkdir(parents=True,exist_ok=False)
    resources = None
    before = None
    try:
        L.write_new(R,out/'GO.json',go)
        L.progress(R,out,'wrapper-boundary-before')
        before = L.snapshot(R,pins)
        check_deadline(deadline,outer_watchdog_pid)
        L.write_new(R,out/'WRAPPER_BEFORE.json',before)
        env = {k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','OMP_','MKL_','OPENBLAS_','ATEN_'))}
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        for key,value in pins['capture_environment'].items():
            if value is not None:
                env[key] = value
        read_fd,write_fd = os.pipe()
        cap = {'schema':1,'parent_pid':os.getpid(),'run_id':run_id,'mode':mode,
               'out':str(out.relative_to(R.ROOT)),'source_manifest':R.source_manifest(),
               'go_sha256':L.identity(out/'GO.json')['sha256']}
        os.write(write_fd,R.encoded(cap))
        os.close(write_fd)
        L.progress(R,out,'worker-start')
        try:
            resources = supervise([sys.executable,'-B',str(R.HERE/'guard.py'),'--worker',str(read_fd),mode,str(out)],
                                  env,out,pass_fds=(read_fd,),wall=deadline-time.monotonic(),
                                  watchdog_enabled=False,excluded_pids=(outer_watchdog_pid,))
        finally:
            os.close(read_fd)
        check_deadline(deadline,outer_watchdog_pid)
        resources.update(overall_wall_limit_seconds=120,external_watchdog_deadline_seconds=122,
            cleanup_grace_seconds=2,independent_overall_watchdog_enabled=True,
            overall_clock_started_at='run entry before source/go/input/runtime preflight',
            overall_elapsed_seconds=time.monotonic()-start)
        R.need(resources['returncode'] == 0 and resources['limit_reason'] is None, 'bounded worker failed')
        R.need(not (out/'WATCHDOG.json').exists(), 'independent watchdog fired; never seal')
        observations = R.parse((out/'OBSERVATIONS.json').read_bytes())
        R.fields(observations, {'stage':mode,'source_manifest':before['source_manifest'],
            'status':'BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT' if mode == 'bootstrap'
                     else 'FRESH_OFFICIAL_AST_FULLBLOCK_CAPTURE_ONLY'}, 'worker observations')
        L.validate_payload_inventory(R,pins,out,observations)
        L.progress(R,out,'wrapper-boundary-after')
        after = L.snapshot(R,pins)
        check_deadline(deadline,outer_watchdog_pid)
        R.need(R.same(before,after), 'wrapper source/raw/runtime drift')
        for label in ('BEFORE','AFTER'):
            R.need(R.same(R.parse((out/('BOUNDARY_'+label+'.json')).read_bytes()),before),
                   'worker/wrapper boundary drift')
        L.write_new(R,out/'WRAPPER_AFTER.json',after)
        resources['overall_elapsed_seconds'] = time.monotonic()-start
        manifest = 'BOOTSTRAP_REFERENCE.json' if mode == 'bootstrap' else 'REFERENCE.json'
        L.write_new(R,out/manifest,{**observations,'resources':resources,
            'wrapper_boundary_unchanged':True,'go_identity':go['receipt']})
        L.progress(R,out,'validated-awaiting-seal')
        inventory = L.directory_inventory(R,out)
        seal = {'schema':1,'status':'SEALED_BOOTSTRAP_OBSERVATIONS_UNACCEPTED' if mode == 'bootstrap'
                 else 'SEALED_FRESH_FROZEN_REPRODUCTION_REFERENCE_ONLY','mode':mode,'run_id':run_id,
                'manifest':manifest,'files':inventory,'resources':resources,
                'source_manifest':before['source_manifest'],'numerical_acceptance_claimed':False,
                'dut_executed':False,'retries':0}
        projected = len(R.encoded(seal))
        R.need(L.bytes_under(out)+projected <= pins['budget']['per_capture_cap_bytes'] and
               L.bytes_under(out.parent)+projected <= pins['budget']['total_cap_bytes'], 'final seal disk admission')
        seal_raw = R.encoded(seal)
        answer = {'status':seal['status'],'out':str(out.relative_to(R.ROOT)),
                  'seal':{'bytes':len(seal_raw),'sha256':R.sha(seal_raw)},'resources':resources}
        check_deadline(deadline,outer_watchdog_pid)
        L.write_new(R,out/'SEAL.pending',seal)
        check_deadline(deadline,outer_watchdog_pid)
        R.need(not (out/'WATCHDOG.json').exists(), 'overall watchdog fired; never seal')
        # Atomic publication is the last fallible operation in the success path.
        os.rename(out/'SEAL.pending',out/'SEAL.json')
        return answer
    except BaseException as error:
        failure = {'status':'FAILED_UNSEALED','mode':mode,'run_id':run_id,'stage':L.last_stage(R,out),
            'error_type':type(error).__name__,'error':str(error),'resources':resources,
            'partial_files':L.directory_inventory(R,out),'before_captured':before is not None,
            'completion_seal_written':False,'numerical_acceptance_claimed':False,'automatic_retry':False,
            'overall_elapsed_seconds':time.monotonic()-start,'overall_wall_limit_seconds':120,
            'external_watchdog_deadline_seconds':122}
        L.write_new(R,out/'FAILURE.json',failure)
        raise


def main():
    if len(sys.argv)>1 and sys.argv[1] == '--supervisor-watchdog':
        parent,fd,out,deadline = sys.argv[2:]
        return supervisor_watchdog(int(parent),int(fd),Path(out),float(deadline))
    if len(sys.argv)>1 and sys.argv[1] == '--worker':
        return worker(*sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1] == '--watchdog':
        pid,parent,fd,out,seconds = sys.argv[2:]
        return watchdog(int(pid),int(parent),int(fd),Path(out),float(seconds))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('bootstrap','frozen'))
    parser.add_argument('--run-id')
    parser.add_argument('--go')
    args = parser.parse_args()
    try:
        if args.mode is None and args.run_id is None and args.go is None:
            return R.main([])
        R.need(all((args.mode,args.run_id,args.go)), 'explicit mode, run identity and reviewed single go required')
        print(json.dumps(run(args.mode,args.run_id,args.go),sort_keys=True,allow_nan=False))
        return 0
    except (R.Rejected,OSError,ValueError,TypeError,KeyError) as error:
        print(json.dumps({'status':'REJECTED_OR_FAILED_UNSEALED','reason':str(error)},allow_nan=False),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
