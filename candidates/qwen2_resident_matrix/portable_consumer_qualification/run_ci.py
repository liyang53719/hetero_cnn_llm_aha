"""Future opt-in supervisor. Never execute while preparing/reviewing this proposal."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract as c

CONTROL_SIGNALS = {signal.SIGALRM, signal.SIGTERM, signal.SIGINT}
CHILD_BOOTSTRAP = ('import os, signal, sys\n'
    'signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGALRM, signal.SIGTERM, signal.SIGINT})\n'
    'os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n')

def save(path, value):
    c.atomic(path, value)

def process_identity(pid):
    with (Path('/proc') / str(pid) / 'stat').open('r') as stream:
        raw = stream.read(4097)
    c.need(len(raw) <= 4096, 'bounded owned process identity')
    fields = raw.rsplit(')', 1)[1].split()
    return dict(pid=pid, ppid=int(fields[1]), group=int(fields[2]), start=int(fields[19]))

def clean_environment(out, loader=None):
    names = ('GITHUB_ACTIONS', 'GITHUB_EVENT_NAME', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA',
             'RUNNER_OS', 'RUNNER_ARCH', 'RUNNER_ENVIRONMENT', 'ImageOS', 'ImageVersion')
    result = {name: os.environ.get(name, '') for name in names}
    result.update(PATH='/usr/bin:/bin', HOME=str(out / 'home'), TMPDIR=str(out / 'tmp'),
                  LANG='C.UTF-8', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                  PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                  GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1')
    if loader is not None:
        result.update({key: loader[key] for key in ('RUNNER_TOOL_CACHE', 'pythonLocation', 'LD_LIBRARY_PATH')})
    return result

def spawn_owned(owner, argv, *, cwd, stdout, env):
    """Transfer ownership while interruption is blocked, before unmasking."""
    old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, CONTROL_SIGNALS)
    try:
        owner['process'] = subprocess.Popen([sys.executable, '-I', '-B', '-c', CHILD_BOOTSTRAP, *argv],
            cwd=cwd, env=env, stdout=stdout, stderr=subprocess.STDOUT, start_new_session=True)
        owner['identity'] = process_identity(owner['process'].pid)
        c.need(owner['identity']['ppid'] == os.getpid() and
               owner['identity']['group'] == owner['process'].pid, 'owned new process group')
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)

def observe_exit(pid, deadline):
    """Observe, without reaping: the retained child pins PID/group ownership."""
    while True:
        state = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if state is not None:
            return state.si_status if state.si_code == os.CLD_EXITED else 128 + state.si_status
        if time.monotonic() >= deadline:
            raise TimeoutError('absolute child execution deadline')
        time.sleep(0.05)

def cleanup_owned(owner, stop):
    # WNOWAIT verifies the leader is still our waitable child, even after exit.
    # Never signal a bare PGID after another path has already reaped the leader.
    process = owner['process']
    os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    current = process_identity(process.pid)
    # If the initial /proc read itself failed, waitid still proves unreaped
    # child ownership. Establish its identity before the safety-only kill.
    if owner['identity'] is None:
        owner['identity'] = current
    c.need(current == owner['identity'] and current['ppid'] == os.getpid() and
           current['group'] == process.pid != os.getpgrp(), 'same unreaped leader start identity')
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=max(0, min(5, stop - time.monotonic())))
    c.need(time.monotonic() <= stop, 'absolute cleanup deadline')

def protect_cleanup():
    """Reviewed transition: discard pending work signals before bounded reap."""
    old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, CONTROL_SIGNALS)
    try:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for signum in CONTROL_SIGNALS:
            signal.signal(signum, signal.SIG_IGN)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)

def arm_receipt_deadline(stop):
    old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, CONTROL_SIGNALS)
    try:
        def expired(signum, frame):
            raise TimeoutError('absolute final receipt deadline')
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, max(0.000001, stop - time.monotonic()))
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)

def main():
    if sys.argv[1:] == ['--cold-import-check']:
        c.need('numpy' not in sys.modules and 'ctypes' not in sys.modules, 'cold isolated import')
        print('PASS_COLD_ISOLATED_IMPORT')
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    origin = args.origin.resolve(strict=True)
    launch = c.admit(os.environ, args.out)
    loader = c.loader(os.environ, sys.executable)
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    args.out.mkdir(parents=True)
    out = args.out.resolve(strict=True)
    evidence = out / 'evidence'
    evidence.mkdir()
    summary = dict(schema=1, profile=c.PROFILE, status='NOT_RUN', phase='contract',
                   launch_commit=launch, run_id=os.environ.get('GITHUB_RUN_ID'), run_attempt=1,
                   claims={'rtl': False, 'public_m16': False, 'full_m128': False,
                           'ninety_percent': False, 'producer_qualified': False,
                           'selected_fault_timing_qualified': False})
    save(evidence / 'summary.json', summary)
    owner = {'process': None, 'identity': None}
    failure = None
    started = time.monotonic()
    work_stop, cleanup_stop, receipt_stop = started + 150, started + 159, started + 160
    def deadline_signal(signum, frame):
        raise TimeoutError('external termination or absolute execution deadline')
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(signum, deadline_signal)
    signal.setitimer(signal.ITIMER_REAL, max(0.000001, work_stop - time.monotonic()))
    try:
        contract = c.validate(origin, here)
        summary['contract_sha256'] = c.sha(here / 'input-contract.json')
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=origin, text=True, timeout=5).strip()
        c.need(head == launch, 'actual checkout equals triggering commit')
        save(evidence / 'source_hashes.json', dict(input=contract['source_sha256'],
             proposal=contract['payload_sha256'], generated=contract['generated_sha256']))
        summary.update(status='RUNNING', phase='fixed_cases')
        save(evidence / 'summary.json', summary)
        for name in ('home', 'tmp'):
            (out / name).mkdir()
        with (out / 'private.log').open('wb') as log:
            spawn_owned(owner, ['-I', '-B', str(here / 'worker.py'), 'all', str(origin), str(out)],
                        cwd=origin, stdout=log, env=clean_environment(out, loader))
            try:
                code = observe_exit(owner['process'].pid, work_stop)
            except TimeoutError:
                summary.update(status='TIMEOUT', phase='fixed_cases')
                raise TimeoutError('deadline')
            c.need(code == 0, 'actual qualification child failed')
        result = c.result(c.read(out / 'result.json'), launch, contract)
        c.validate(origin, here)
        save(evidence / 'identities.json', result['identities'])
        summary.update(status='PASS_FIXED_ACTUAL_CASES', phase='complete',
                       library_sha256=result['library_sha256'], checks=result['checks'],
                       observations=result['observations'])
    except BaseException as error:
        failure = error
        if isinstance(error, TimeoutError):
            summary.update(status='TIMEOUT', phase='fixed_cases')
        if summary['status'] != 'TIMEOUT':
            summary['status'] = 'FAIL'
    finally:
        protect_cleanup()
        # All child stages/compiler inherit this one process group. Kill residue
        # even after success. One shared 150s execution + at most 10s reap budget.
        if owner['process'] is not None:
            try:
                cleanup_owned(owner, cleanup_stop)
            except BaseException as cleanup_error:
                summary.update(status='CLEANUP_FAILED', phase='cleanup')
                if failure is None:
                    failure = cleanup_error
        # Private worktree/builds are never published. This ephemeral runner is
        # discarded by GitHub; avoid recursive deletion or path-controlled cleanup.
        try:
            arm_receipt_deadline(receipt_stop)
            c.need(time.monotonic() < receipt_stop, 'absolute final receipt deadline')
            summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
            save(evidence / 'summary.json', summary)
        except BaseException as receipt_error:
            if failure is None:
                failure = receipt_error
        finally:
            protect_cleanup()
    if failure is not None:
        raise failure
    c.need(summary['status'] == 'PASS_FIXED_ACTUAL_CASES', 'terminal qualification or cleanup failure')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
