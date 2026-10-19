"""Fixed CI coordinator support, projecting the published WNOWAIT supervisor.

No native action is performed by import. The complete CI entry remains separate.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before project loads')

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import time
import types

HERE = Path(__file__).resolve().parent
PIN_BYTES = 806
PIN_SHA = 'c2fd4d03c0dc30226a22992e5cd4d347659409d7625505404bd9b714a20105d2'
SUPPORT = 'development_snapshots/canonical_host93_fixed_core_build_source_20261018/run_build_gate.py'
BASE_PLAN = 'development_snapshots/canonical_host93_fixed_core_build_source_20261018/GATE_PLAN.json'
SHARED_SECONDS = 6600


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked_bytes(path, size, expected):
    path = Path(path).absolute()
    require(type(size) is int and 0 <= size <= 4 * 1024**2 and '..' not in path.parts,
            'bounded fixed source read')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        source = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            before = os.fstat(source)
            require(stat.S_ISREG(before.st_mode) and before.st_size == size, 'source regular size')
            chunks, count = [], 0
            while count <= size:
                chunk = os.read(source, min(65536, size + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
            raw = b''.join(chunks)
            stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(len(raw) == size and sha(raw) == expected and
                    stamp(before) == stamp(os.fstat(source)) ==
                    stamp(os.stat(path.name, dir_fd=fd, follow_symlinks=False)), 'source fixed same buffer')
            return raw
        finally:
            os.close(source)
    finally:
        os.close(fd)


def module_bytes(raw, path, size, expected, name):
    require(len(raw) == size and sha(raw) == expected, 'module bytes before compile')
    result = types.ModuleType(name)
    result.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), result.__dict__)
    return result


def fixed_support(repo):
    pins = json.loads(checked_bytes(HERE / 'SUPPORT_PINS.json', PIN_BYTES, PIN_SHA))
    buffers = {name: checked_bytes(Path(repo) / name, p['bytes'], p['sha256'])
               for name, p in pins.items()}
    p = pins[SUPPORT]
    support = module_bytes(buffers[SUPPORT], Path(repo) / SUPPORT,
                           p['bytes'], p['sha256'], 'verified_published_ci_support')
    base = json.loads(buffers[BASE_PLAN])
    for pin in base['published_sources'].values():
        relative = pin['repo_relative']
        require(relative in pins and {k: pin[k] for k in ('bytes', 'sha256')} == pins[relative],
                'original supervisor and observer pins')
        pin['path'] = str(Path(repo).resolve() / relative)
    return support, base, pins


def deadline_ready():
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []) and
            signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0),
            'deadline signal blocked or timer occupied')


def remaining_work(now, shared_stop, phase_entry, total_seconds, work_seconds, cleanup=5, post=10):
    require(all(type(x) in (int, float) and math.isfinite(x) for x in (now, shared_stop, phase_entry)) and
            type(total_seconds) is int and type(work_seconds) is int and
            0 < work_seconds < total_seconds <= SHARED_SECONDS,
            'finite phase budget')
    stop = min(shared_stop - cleanup - post, phase_entry + total_seconds - cleanup - post,
               now + work_seconds)
    require(stop > now, 'no work inside remaining shared wall')
    return stop


def interrupted(_signum, _frame):
    raise TimeoutError('fixed CI phase or shared deadline')


def usage():
    value = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'user': value.ru_utime, 'system': value.ru_stime,
            'maxrss_kib_cumulative_parent_children': value.ru_maxrss}


def owned_deadline(owner, shared_stop):
    """Only the complete coordinator's current handler/timer may be inherited."""
    require(isinstance(owner, dict) and set(owner) == {'handler', 'deadline'} and
            callable(owner['handler']) and owner['deadline'] == shared_stop and
            type(shared_stop) in (int, float) and math.isfinite(shared_stop),
            'explicit coordinator deadline ownership')
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []),
            'owned deadline signal blocked')
    active, interval = signal.getitimer(signal.ITIMER_REAL)
    now = time.monotonic()
    require(signal.getsignal(signal.SIGALRM) is owner['handler'] and interval == 0 and
            0 < active <= shared_stop - now + 0.050 and now < shared_stop,
            'unowned or expired coordinator timer')


def run_phase(support, base, name, argv, cwd, evidence, environment, limits, shared_stop, owner=None):
    """Published supervisor, with explicit same-deadline coordinator ownership.

    Preparation is now covered before fresh_directory/make_runner. Only a caller
    supplying its exact installed handler and same deadline may inherit a timer.
    No timer is silently unblocked, no shared deadline is extended, and the
    original WNOWAIT child cleanup implementation remains unchanged.
    """
    if owner is None:
        deadline_ready()
    else:
        owned_deadline(owner, shared_stop)
    entry = time.monotonic()
    phase_stop = min(shared_stop, entry + limits['total_seconds'])
    require(phase_stop > entry, 'phase shared deadline already exhausted')
    old_alarm = signal.signal(signal.SIGALRM, interrupted)
    old_term = signal.signal(signal.SIGTERM, interrupted)
    runner, before, record, raw, failure, result = None, None, None, None, None, None
    try:
        signal.setitimer(signal.ITIMER_REAL, max(0.001, phase_stop - time.monotonic()))
        require(not os.path.lexists(evidence), 'fresh phase evidence')
        support.fresh_directory(evidence)
        plan = {'published_sources': copy.deepcopy(base['published_sources']),
                'phases': {name: dict(limits)}, 'environment': dict(environment)}
        runner = support.make_runner(plan, name, Path(evidence))
        before = usage()
        stop = remaining_work(time.monotonic(), shared_stop, entry,
                              limits['total_seconds'], limits['work_seconds'])
        signal.setitimer(signal.ITIMER_REAL, max(0.001, stop - time.monotonic()))
        record, raw = runner['bounded']('native', list(argv), Path(cwd), Path(evidence),
                                         stop - time.monotonic(), limits['cpu_seconds'])
    except BaseException as error:
        failure = error
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            signal.setitimer(signal.ITIMER_REAL, max(0.001, phase_stop - time.monotonic()))
            if runner is not None and before is not None:
                after = usage()
                result = {'phase': name, 'child_user_cpu_seconds': after['user'] - before['user'],
                          'child_system_cpu_seconds': after['system'] - before['system'],
                          'maxrss_kib_cumulative_parent_children': after['maxrss_kib_cumulative_parent_children'],
                          'scope': 'child processes of this coordinator; cumulative maxrss, not phase-specific',
                          'seconds': time.monotonic() - entry,
                          'projection_hashes': runner['projection_hashes']}
                runner['save'](Path(evidence) / 'USAGE.json', result)
            require(time.monotonic() < phase_stop, 'phase postflight exhausted')
        except BaseException as post_error:
            if failure is None:
                failure = post_error
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGALRM, old_alarm)
            if owner is not None:
                remaining = shared_stop - time.monotonic()
                signal.setitimer(signal.ITIMER_REAL, max(0.001, remaining))
                if remaining <= 0 and failure is None:
                    failure = TimeoutError('coordinator shared deadline exhausted')
    if failure is not None:
        raise failure
    require(record is not None and record['exit_code'] == 0 and record['cleanup_confirmed'],
            'phase native exit or owned-group cleanup')
    return record, raw, result
