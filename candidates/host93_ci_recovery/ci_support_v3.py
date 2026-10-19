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


def diagnostic_defaults():
    return {'exit_code': None, 'final_reap_signal': None, 'receipt_timed_out': None,
            'cleanup_confirmed': None, 'waitid_code': None, 'waitid_status': None,
            'kill_attempted': None, 'kill_result': 'UNKNOWN', 'native_record_status': 'UNKNOWN',
            'failure_code': 'UNKNOWN', 'failure_boundary': 'UNKNOWN',
            'child_user_cpu_seconds': None, 'child_system_cpu_seconds': None,
            'child_maxrss_kib_cumulative': None}


def terminal_observation(support, evidence, name, argv, cwd, limits, record, result, failure, boundary, allow_read=True):
    """Finite numeric projection only. No raw exception/log/path escapes."""
    safe = diagnostic_defaults()
    safe['failure_boundary'] = 'NONE' if failure is None else boundary
    if result is not None:
        for key in ('child_user_cpu_seconds', 'child_system_cpu_seconds'):
            value = result.get(key)
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                safe[key] = value
        value = result.get('maxrss_kib_cumulative_parent_children')
        if type(value) is int and value >= 0:
            safe['child_maxrss_kib_cumulative'] = value
    if record is None and allow_read:
        try:
            path = Path(evidence) / 'native.json'
            pin = support.identity(path, 1024**2)
            raw = support.checked_read(path, pin['bytes'], pin['sha256'])
            def unique(pairs):
                obj = {}
                for key, value in pairs:
                    require(key not in obj, 'duplicate private receipt key')
                    obj[key] = value
                return obj
            record = json.loads(raw, object_pairs_hook=unique)
        except BaseException:
            record = None
    if type(record) is not dict:
        safe['failure_code'] = 'SUPERVISOR_TIMEOUT_CLASSIFICATION' if isinstance(failure, TimeoutError) else 'RECEIPT_UNAVAILABLE'
        return safe
    # Bind the self-produced receipt to this exact original invocation privately.
    if not (record.get('stage') == 'native' and record.get('argv') == list(argv) and
            record.get('cwd') == str(cwd) and record.get('expected_exit') == 0 and
            record.get('cpu_limit_seconds') == limits['cpu_seconds'] and
            record.get('address_space_limit_bytes') == limits['as_bytes']):
        safe['failure_code'] = 'RECEIPT_INVALID'
        return safe
    status = record.get('status')
    if status not in ('PASS', 'FAIL') or type(record.get('seconds')) not in (int, float) or not math.isfinite(record['seconds']) or record['seconds'] < 0:
        safe['failure_code'] = 'RECEIPT_PARTIAL'
        return safe
    safe['native_record_status'] = status
    code = record.get('exit_code')
    if type(code) is int and -255 <= code <= 255 and record.get('reaped') is True:
        safe['exit_code'] = code
        if code < 0: safe['final_reap_signal'] = -code
    if type(record.get('timed_out')) is bool: safe['receipt_timed_out'] = record['timed_out']
    event = record.get('exit_observed_while_unreaped')
    if (type(event) is dict and event.get('pid') == record.get('pid') and
            type(event.get('code')) is int and 1 <= event['code'] <= 6 and
            type(event.get('status')) is int and 0 <= event['status'] <= 255):
        safe['waitid_code'], safe['waitid_status'] = event['code'], event['status']
    if type(record.get('kill_attempted')) is bool: safe['kill_attempted'] = record['kill_attempted']
    kill_names = {'not_requested':'NOT_REQUESTED', 'signal_sent_before_reap':'SIGNAL_SENT_BEFORE_REAP',
                  'group_already_absent':'GROUP_ALREADY_ABSENT'}
    safe['kill_result'] = kill_names.get(record.get('kill_result'), 'UNKNOWN')
    if (record.get('spawn_handle_acquired') is True and record.get('anchor_confirmed') is True and
            record.get('reaped') is True and record.get('group_state') == 'absent' and
            record.get('cleanup_confirmed') is True):
        safe['cleanup_confirmed'] = True
    elif record.get('group_state') == 'present' and record.get('cleanup_confirmed') is False:
        safe['cleanup_confirmed'] = False
    exception = record.get('parent_exception')
    sampler_messages = ('sample sink required', 'leader sample row cap exceeded',
                        'original leader PID/starttime changed', 'leader identity changed across status read',
                        'proc memory unit', 'duplicate memory metric', 'negative memory metric',
                        'clock ticks', 'leader sample line cap', 'sample WNOWAIT anchor mismatch')
    if failure is None:
        safe['failure_code'] = 'NONE'
    elif type(exception) is dict and exception.get('type') == 'ValueError' and exception.get('message') in sampler_messages:
        safe['failure_code'] = 'SAMPLER_CONTRACT'
    elif safe['receipt_timed_out'] is True or isinstance(failure, TimeoutError):
        safe['failure_code'] = 'SUPERVISOR_TIMEOUT_CLASSIFICATION'
    elif record.get('output_limit_exceeded') is True:
        safe['failure_code'] = 'LOG_LIMIT'
    elif safe['final_reap_signal'] is not None:
        safe['failure_code'] = 'CHILD_SIGNAL'
    elif safe['exit_code'] not in (None, 0):
        safe['failure_code'] = 'CHILD_EXIT_NONZERO'
    elif safe['cleanup_confirmed'] is not True:
        safe['failure_code'] = 'CLEANUP_UNCONFIRMED'
    elif status == 'PASS':
        safe['failure_code'] = 'PHASE_POSTFLIGHT'
    else:
        safe['failure_code'] = 'UNKNOWN'
    return safe


def run_phase(support, base, name, argv, cwd, evidence, environment, limits, shared_stop, owner=None, diagnostics=None):
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
    require(diagnostics is None or type(diagnostics) is dict and not diagnostics, 'empty caller diagnostic sink')
    old_alarm = signal.signal(signal.SIGALRM, interrupted)
    old_term = signal.signal(signal.SIGTERM, interrupted)
    runner, before, record, raw, failure, result = None, None, None, None, None, None
    boundary = 'PREPARE'
    native_entered = False
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
        boundary = 'NATIVE_SUPERVISION'
        native_entered = True
        record, raw = runner['bounded']('native', list(argv), Path(cwd), Path(evidence),
                                         stop - time.monotonic(), limits['cpu_seconds'])
        boundary = 'USAGE_OR_POSTFLIGHT'
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
            if failure is None:
                require(record is not None and record['exit_code'] == 0 and record['cleanup_confirmed'],
                        'phase native exit or owned-group cleanup')
        except BaseException as post_error:
            if failure is None:
                failure = post_error
        finally:
            if diagnostics is not None:
                try:
                    diagnostics.update(terminal_observation(support, evidence, name, argv, cwd, limits,
                        record, result, failure, boundary, native_entered and time.monotonic() < phase_stop))
                except BaseException as diagnostic_error:
                    diagnostics.update(diagnostic_defaults())
                    if failure is None:
                        failure = diagnostic_error
                        diagnostics['failure_boundary'] = 'USAGE_OR_POSTFLIGHT'
                        if isinstance(diagnostic_error, TimeoutError):
                            diagnostics['failure_code'] = 'SUPERVISOR_TIMEOUT_CLASSIFICATION'
            if time.monotonic() >= phase_stop and failure is None:
                failure = TimeoutError('phase diagnostic deadline exhausted')
                if diagnostics is not None:
                    diagnostics['failure_code'] = 'SUPERVISOR_TIMEOUT_CLASSIFICATION'
                    diagnostics['failure_boundary'] = 'USAGE_OR_POSTFLIGHT'
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGALRM, old_alarm)
            if owner is not None:
                remaining = shared_stop - time.monotonic()
                signal.setitimer(signal.ITIMER_REAL, max(0.001, remaining))
                if remaining <= 0 and failure is None:
                    failure = TimeoutError('coordinator shared deadline exhausted')
                    if diagnostics is not None:
                        diagnostics['failure_code'] = 'SUPERVISOR_TIMEOUT_CLASSIFICATION'
                        diagnostics['failure_boundary'] = 'USAGE_OR_POSTFLIGHT'
    if failure is not None:
        raise failure
    return record, raw, result
