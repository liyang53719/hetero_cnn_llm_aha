"""Reviewed-gate-only tiny runtime tests; serial bounded children and retained receipts."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import resource
import signal
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
AS_LIMIT = 256 * 1024 * 1024


def require(ok, why):
    if not ok:
        raise ValueError(why)


def digest(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def group_state(pgid):
    try:
        os.killpg(pgid, 0)
        return 'present'
    except ProcessLookupError:
        return 'absent'
    except BaseException:
        return 'unknown'


def observe_exit(child, command, wall_seconds):
    # Linux only. Never poll()/wait() here: WNOWAIT keeps the original leader
    # unreaped, so its PID/PGID cannot be reused before group cleanup.
    deadline = time.monotonic() + wall_seconds
    while True:
        event = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if event is not None:
            require(event.si_pid == child.pid, 'unexpected waitid child identity')
            return dict(pid=event.si_pid, code=event.si_code, status=event.si_status)
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(command, wall_seconds)
        time.sleep(min(0.02, max(0, deadline - time.monotonic())))


def bounded(label, command, directory, output, wall_seconds, cpu_seconds, expected_exit=0):
    require(type(expected_exit) is int and expected_exit in (0, 1), 'unsupported expected exit')
    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT, AS_LIMIT))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    record = dict(stage=label, argv=command, cwd=str(directory), status='STARTING',
                  wall_limit_seconds=wall_seconds, cpu_limit_seconds=cpu_seconds,
                  address_space_limit_bytes=AS_LIMIT, spawn_handle_acquired=False,
                  pid=None, pgid=None, timed_out=False, parent_exception=None,
                  exit_observed_while_unreaped=None, anchor_confirmed=False,
                  kill_attempted=False, kill_result='not_requested', reaped=False,
                  group_state='unknown', cleanup_confirmed=False, exit_code=None,
                  cleanup_budget_seconds=5, expected_exit=expected_exit)
    receipt = output / (label + '.json')
    log_path = output / (label + '.log')
    save(receipt, record)
    started = time.monotonic()
    child = None
    failure = None
    with log_path.open('wb') as log:
        try:
            child = subprocess.Popen(command, cwd=directory, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=limits,
                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
            record.update(spawn_handle_acquired=True, pid=child.pid, pgid=child.pid)
            save(receipt, record)
            record['exit_observed_while_unreaped'] = observe_exit(child, command, wall_seconds)
        except BaseException as error:
            failure = error
            record['timed_out'] = isinstance(error, subprocess.TimeoutExpired)
            record['parent_exception'] = dict(type=type(error).__name__, message=str(error))
        finally:
            if child is not None:
                deadline = time.monotonic() + 5
                # Verify this is still OUR unreaped child, alive or zombie.
                # ECHILD/other errors mean no identity proof and prohibit kill.
                try:
                    event = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    require(event is None or event.si_pid == child.pid, 'cleanup anchor mismatch')
                    record['anchor_confirmed'] = True
                except BaseException as error:
                    record['anchor_error'] = dict(type=type(error).__name__, message=str(error))
                    if failure is None:
                        failure = error
                if record['anchor_confirmed']:
                    record['group_before_reap'] = group_state(child.pid)
                    if record['group_before_reap'] != 'absent':
                        record['kill_attempted'] = True
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                            record['kill_result'] = 'signal_sent_before_reap'
                        except ProcessLookupError:
                            record['kill_result'] = 'group_already_absent'
                        except BaseException as error:
                            record['kill_result'] = type(error).__name__ + ': ' + str(error)
                            if failure is None:
                                failure = error
                    try:
                        child.wait(timeout=max(0, deadline - time.monotonic()))
                    except BaseException as error:
                        record['reap_error'] = dict(type=type(error).__name__, message=str(error))
                        if failure is None:
                            failure = error
                    record['exit_code'] = child.returncode
                    record['reaped'] = child.returncode is not None
                # A zombie leader itself keeps the group present. Only AFTER
                # final reap can absence be required. All probes here are read
                # only: never signal a potentially recycled PGID after reap.
                record['group_state'] = group_state(child.pid)
                try:
                    while record['group_state'] != 'absent' and time.monotonic() < deadline:
                        time.sleep(min(0.02, max(0, deadline - time.monotonic())))
                        record['group_state'] = group_state(child.pid)
                except BaseException as error:
                    record['cleanup_probe_error'] = dict(type=type(error).__name__, message=str(error))
                    record['group_state'] = 'unknown'
                    if failure is None:
                        failure = error
                record['cleanup_confirmed'] = record['reaped'] and record['group_state'] == 'absent'
            record['seconds'] = round(time.monotonic() - started, 6)
            record['status'] = ('PASS' if failure is None and record['exit_code'] == expected_exit
                                and record['cleanup_confirmed'] else 'FAIL')
            save(receipt, record)
    record['log_bytes'] = log_path.stat().st_size
    if record['log_bytes'] > 65536:
        record['status'] = 'FAIL'
        record['output_limit_exceeded'] = True
    save(receipt, record)
    if failure is not None:
        raise failure
    require(record['status'] == 'PASS', label + ' failed; retained ' + receipt.name)
    return record, log_path.read_bytes()


BUILD_NAMES = ('axi_protocol.hpp', 'canonical16_identities.hpp', 'canonical16_runtime_binding.hpp', 'host_memory.hpp', 'n0_retirement_adapter.hpp', 'negative_public_access.cpp', 'runtime_policy.hpp', 'runtime_ram.hpp', 'sha256.hpp', 'test_runtime_ram.cpp')
STAGES = ('compiler_version', 'compile_O0', 'run_O0', 'compile_O2', 'run_O2',
          'negative_1', 'negative_2', 'negative_3', 'negative_4')
BASE_FLAGS = ['-std=c++17', '-Wall', '-Wextra', '-Werror', '-pedantic',
              '-fdiagnostics-color=never']


def prepare_inputs(root):
    pins = json.loads((root / 'BUILD_INPUT_PINS.json').read_text())
    require(set(pins['files']) == set(BUILD_NAMES), 'exact ten build inputs required')
    copied, verified = {}, {}
    for name in BUILD_NAMES:
        path = root / name
        require(path.resolve().is_relative_to(root), 'input resolves outside source directory')
        raw = path.read_bytes()
        require(digest(raw) == pins['files'][name], 'source input drift: ' + name)
        copied[name] = raw
        verified[name] = digest(raw)
    # Test-only access is defined only in the positive TU. No caller flags or
    # environment flags can inject it into any production negative compile.
    for name, raw in copied.items():
        if name != 'test_runtime_ram.cpp':
            require(re.search(rb'^\s*#\s*define\s+CANONICAL_RUNTIME_UNIT_TEST\b', raw,
                              re.MULTILINE) is None, 'production test macro definition')
    require(b'CANONICAL_RUNTIME_UNIT_TEST' not in copied['negative_public_access.cpp'],
            'negative TU must not enable or rely on test access')
    return copied, verified


def strict_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'duplicate JSON field: ' + key)
            value[key] = item
        return value
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def validate_behavior(actual):
    fields = {'status', 'checks', 'max_synthetic_arena_bytes', 'adapter_runtime_bound',
              'canonical_input_sha_verified', 'full_host_ready', 'launch_ready', 'eda_executed'}
    require(type(actual) is dict and set(actual) == fields, 'unexpected runtime result fields')
    require(actual['status'] == 'RUNTIME_MEMORY_UNIT_BEHAVIOR_PASS', 'runtime test failed')
    require(type(actual['checks']) is int and actual['checks'] > 0, 'positive actual check count required')
    require(type(actual['max_synthetic_arena_bytes']) is int and
            actual['max_synthetic_arena_bytes'] == 1024, 'unexpected synthetic arena size')
    for key in fields - {'status', 'checks', 'max_synthetic_arena_bytes'}:
        require(actual[key] is False, 'unearned runtime claim: ' + key)
    return actual


def validate_negative(case, raw, source):
    require(type(case) is int and case in (1, 2, 3, 4), 'unknown negative case')
    text = raw.decode('utf-8')
    require('CANONICAL_RUNTIME_UNIT_TEST' not in text, 'test access entered production diagnostic')
    # Narrow deny-list for known resource/driver failures. This is not a full
    # compiler-output grammar; contextual/unclassified non-error lines remain allowed.
    fatal_fragments = ('virtual memory exhausted', 'cannot allocate memory',
                       'out of memory', 'killed signal', 'segmentation fault',
                       'bus error', 'internal compiler error', 'compilation terminated')
    lowered = text.lower()
    require(not any(fragment in lowered for fragment in fatal_fragments),
            'resource or fatal compiler failure mixed with private diagnostic')
    expected = {1: 'N0RetirementAdapter', 2: 'stage_aw', 3: 'payload_',
                4: 'RuntimeOwner::RuntimeOwner'}[case]
    errors = []
    for line in text.splitlines():
        # GCC/Clang English source-positioned error format only. Unknown compiler
        # error-line shapes fail closed; this does not classify every context line.
        if re.search(r'\b(?:fatal )?error:', line, re.IGNORECASE):
            match = re.fullmatch(r'(.+):(\d+):(\d+): error: (.+)', line)
            require(match is not None, 'unrecognized or fatal negative diagnostic')
            path, line_number, column, message = match.groups()
            require(Path(path).resolve() == source.resolve(), 'negative error outside fixed TU')
            require(int(line_number) > 0 and int(column) > 0, 'invalid diagnostic position')
            private = ('is private within this context' in message or
                       'is a private member of' in message or
                       'calling a private constructor of class' in message)
            target = expected in message
            if case == 4 and 'calling a private constructor of class' in message:
                target = 'RuntimeOwner' in message
            require(private and target, 'negative failure did not match intended private interface')
            errors.append(dict(line=int(line_number), column=int(column), member=expected))
        require('internal compiler error' not in line.lower(), 'compiler internal failure')
    require(len(errors) == 1, 'exactly one intended private access error required')
    return dict(status='EXPECTED_PRIVATE_ACCESS_REJECTED', case=case,
                expected_exit=1, member=expected, matched_errors=errors, diagnostic=digest(raw))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='c++', help='existing compiler; no installation')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), 'fresh output directory required')
    copied, verified = prepare_inputs(HERE)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status='STARTED', input_hashes=verified, stages={}, behavior={},
                  negative_results={}, adapter_runtime_bound=False,
                  canonical_input_sha_verified=False, max_synthetic_arena_bytes=1024,
                  actual_model=False, full_host_ready=False, launch_ready=False,
                  eda_executed=False, tensor_payload=False, build_and_logs_retained=True)
    save(output / 'RESULT.json', report)
    try:
        work = output / 'build'
        work.mkdir(exist_ok=False)
        for name, raw in copied.items():
            (work / name).write_bytes(raw)
        selected = shutil.which(args.compiler)
        require(selected is not None, 'existing requested compiler not found')
        compiler = Path(selected).resolve(strict=True)
        require(compiler.is_file(), 'existing standard compiler missing')
        report['compiler'] = dict(requested=args.compiler, resolved=str(compiler),
                                  **digest(compiler.read_bytes()))
        save(output / 'RESULT.json', report)
        record, log = bounded('compiler_version', [str(compiler), '--version'], work, output, 5, 2)
        report['stages']['compiler_version'] = record
        report['compiler']['version'] = log.decode('utf-8', errors='replace')
        save(output / 'RESULT.json', report)
        for mode, flags in (('O0', ['-O0']), ('O2', ['-O2', '-DNDEBUG'])):
            command = [str(compiler)] + BASE_FLAGS + flags + ['-I', str(work),
                str(work / 'test_runtime_ram.cpp'), '-o', str(work / ('runtime_test_' + mode))]
            label = 'compile_' + mode
            report['stages'][label], _ = bounded(label, command, work, output, 30, 30)
            save(output / 'RESULT.json', report)
            label = 'run_' + mode
            record, log = bounded(label, [str(work / ('runtime_test_' + mode))], work, output, 10, 5)
            report['stages'][label] = record
            report['behavior'][mode] = validate_behavior(strict_json(log))
            save(output / 'RESULT.json', report)
        require(report['behavior']['O0'] == report['behavior']['O2'], 'O0/O2 result disagreement')
        for case in (1, 2, 3, 4):
            label = 'negative_' + str(case)
            command = [str(compiler)] + BASE_FLAGS + ['-O0', '-UCANONICAL_RUNTIME_UNIT_TEST',
                '-DNEGATIVE_CASE=' + str(case), '-fsyntax-only', '-I', str(work),
                str(work / 'negative_public_access.cpp')]
            record, log = bounded(label, command, work, output, 30, 30, expected_exit=1)
            report['stages'][label] = record
            report['negative_results'][str(case)] = validate_negative(case, log, work / 'negative_public_access.cpp')
            save(output / 'RESULT.json', report)
        report.update(status='BOUNDED_TINY_RUNTIME_RAM_BEHAVIOR_PASS',
            scope='pinned synthetic runtime kernel and test-only adapter; real model remains unbound')
    except BaseException as error:
        report['status'] = 'FAIL'
        report['exception'] = dict(type=type(error).__name__, message=str(error))
    finally:
        for label in STAGES:
            path = output / (label + '.json')
            if path.exists():
                report['stages'][label] = json.loads(path.read_text())
        save(output / 'RESULT.json', report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] == 'BOUNDED_TINY_RUNTIME_RAM_BEHAVIOR_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
