"""Narrow command bridge to the already reviewed consumer process ownership code.

No launcher, build, or native load occurs on import. This adapter does not modify
the published helper or any compiler/arithmetic source. Review-only proposal.
"""
import importlib.util
import hashlib
import os
from pathlib import Path
import signal
import sys
import time

HELPER = 'candidates/qwen2_resident_matrix/portable_consumer_qualification/run_ci.py'
HELPER_SHA = '9e498c425f637e53978844a6a21b4ad85899ca72f4bea79f6cd2814d2f956b9e'
CONTRACT_SHA = '23ea59a4a398555a0f025e3ac9e67cd6188dc093839ef954117f4485e090c818'
EXEC_BOOTSTRAP = 'import os,sys\nos.execv(sys.argv[1],sys.argv[1:])\n'


def load_owner(root):
    path = Path(root) / HELPER
    contract_path = path.with_name('contract.py')
    def checked(file, expected):
        if (any(p.is_symlink() for p in (file, *file.parents)) or not file.is_file()
                or file.stat().st_nlink != 1 or file.stat().st_size > 1024 * 1024):
            raise ValueError('ownership helper file contract')
        raw = file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('ownership helper source drift')
        return raw
    raw, contract_raw = checked(path, HELPER_SHA), checked(contract_path, CONTRACT_SHA)
    spec = importlib.util.spec_from_file_location('portable_producer_owned_commands', path)
    module = importlib.util.module_from_spec(spec)
    contract_spec = importlib.util.spec_from_file_location('contract', contract_path)
    contract = importlib.util.module_from_spec(contract_spec)
    exec(compile(contract_raw, str(contract_path), 'exec'), contract.__dict__)
    previous, search = sys.modules.get('contract'), list(sys.path)
    try:
        # The published helper imports a generic 'contract'. Supply exact checked
        # bytes, never a stale .pyc or an unrelated cached module of that name.
        sys.modules['contract'] = contract
        exec(compile(raw, str(path), 'exec'), module.__dict__)
    finally:
        sys.path[:] = search
        if previous is None:
            sys.modules.pop('contract', None)
        else:
            sys.modules['contract'] = previous
    if Path(module.c.__file__).resolve() != path.with_name('contract.py').resolve():
        raise ValueError('ownership helper contract import root')
    checked(path, HELPER_SHA); checked(contract_path, CONTRACT_SHA)
    return module


def run(root, argv, *, cwd, log, end_ns, env=None):
    """Run one exact external command and reap its owned group before return.

    end_ns includes six seconds reserved for cleanup. Every caller passes an
    absolute bounded phase end. The direct parent must allow this cleanup before
    KILL; nested compiler groups are NOT owned by the outer producer PGID.
    """
    if (type(argv) is not list or not argv or not all(type(x) is str and x and '\x00' not in x for x in argv)
            or not Path(argv[0]).is_absolute() or type(end_ns) is not int
            or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0)):
        raise ValueError('owned command argument/timer contract')
    helper = load_owner(root)
    stop = end_ns / 1e9
    work_stop = stop - 6
    if time.monotonic() >= work_stop:
        raise TimeoutError('owned command cleanup reserve')
    owner = {'process': None, 'identity': None}
    old = {s: signal.getsignal(s) for s in helper.CONTROL_SIGNALS}
    def interrupted(signum, frame):
        raise InterruptedError('owned command interrupted')
    code = None
    started = time.monotonic()
    try:
        for s in helper.CONTROL_SIGNALS:
            signal.signal(s, interrupted)
        signal.setitimer(signal.ITIMER_REAL, work_stop - time.monotonic())
        with Path(log).open('xb') as stream:
            # spawn_owned always runs Python. This explicit same-PID exec shim
            # is required for a compiler/binary; passing its ELF as Python input
            # would be incorrect. The reviewed bootstrap first unblocks signals.
            helper.spawn_owned(owner, ['-I', '-B', '-c', EXEC_BOOTSTRAP, *argv],
                cwd=Path(cwd), stdout=stream, env=dict(os.environ) if env is None else env)
            code = helper.observe_exit(owner['process'].pid, work_stop)
    finally:
        helper.protect_cleanup()
        try:
            if owner['process'] is not None:
                helper.cleanup_owned(owner, stop)
        finally:
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, helper.CONTROL_SIGNALS)
            try:
                for s, handler in old.items():
                    signal.signal(s, handler)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
    if type(code) is not int or code != 0 or time.monotonic() >= stop:
        raise ValueError('owned command failed or expired')
    return {'returncode': code, 'elapsed_seconds': time.monotonic() - started,
            'observed_exit_code': code, 'reaped_exit_code': owner['process'].returncode,
            'cleanup_complete': True, 'ownership': dict(owner['identity'])}
