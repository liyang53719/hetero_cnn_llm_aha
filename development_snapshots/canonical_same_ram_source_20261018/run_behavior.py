"""Reviewed-gate-only single-TU RAM test; bounded children and retained receipts."""
import argparse
import hashlib
import json
import os
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


def bounded(label, command, directory, output, wall_seconds, cpu_seconds):
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
                  cleanup_budget_seconds=5)
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
            record['status'] = ('PASS' if failure is None and record['exit_code'] == 0
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


def prepare_inputs(root):
    pins = json.loads((HERE / 'BUILD_INPUT_PINS.json').read_text())
    copied, verified = {}, {}
    for name, record in pins['files'].items():
        require(name and '\\' not in name and not name.startswith('/') and
                all(p not in ('', '.', '..') for p in name.split('/')), 'relative input key required')
        path = root / name
        require(path.resolve().is_relative_to(root), 'input resolves outside workspace')
        raw = path.read_bytes()
        require(digest(raw) == {k: record[k] for k in ('bytes', 'sha256')}, 'source input drift: ' + name)
        verified[name] = digest(raw)
        if record.get('build_name'):
            name = record['build_name']
            require(name in ('initialization_ram.hpp', 'v1_initialization_ram.hpp',
                             'test_initialization_ram.cpp'), 'unexpected build name')
            require(name not in copied, 'duplicate build file')
            copied[name] = raw
    require(len(copied) == 3, 'exactly two actual headers and one test translation unit required')
    return copied, verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='c++', help='existing compiler name or path; never installs software')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = HERE
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), 'fresh output directory required')
    # No child starts and no output is created until all relative inputs match.
    copied, verified = prepare_inputs(root)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status='STARTED', input_hashes=verified, stages={},
                  canonical_input_sha_verified=False, max_instantiated_ram_bytes=64,
                  actual_model=False, eda_executed=False, tensor_payload=False,
                  full_host_ready=False, build_and_logs_retained=True)
    save(output / 'RESULT.json', report)
    try:
        work = output / 'build'
        work.mkdir(exist_ok=False)
        for name, raw in copied.items():
            (work / name).write_bytes(raw)  # same verified byte buffers reach compiler
        selected = shutil.which(args.compiler)
        require(selected is not None, 'existing requested compiler not found')
        compiler = Path(selected).resolve(strict=True)
        require(compiler.is_file(), 'existing standard compiler missing')
        report['compiler'] = dict(requested=args.compiler, resolved=str(compiler),
                                  **digest(compiler.read_bytes()))
        save(output / 'RESULT.json', report)
        version, version_log = bounded('compiler_version', [str(compiler), '--version'], work, output, 5, 2)
        report['stages']['compiler_version'] = version
        report['compiler']['version'] = version_log.decode('utf-8', errors='replace')
        save(output / 'RESULT.json', report)
        command = [str(compiler), '-std=c++17', '-O0', '-Wall', '-Wextra', '-Werror', '-pedantic',
                   '-I', str(work), str(work / 'test_initialization_ram.cpp'), '-o', str(work / 'ram_test')]
        compilation, _ = bounded('compile', command, work, output, 30, 30)
        report['stages']['compile'] = compilation
        save(output / 'RESULT.json', report)
        execution, run_log = bounded('run', [str(work / 'ram_test')], work, output, 10, 5)
        report['stages']['run'] = execution
        actual = json.loads(run_log)
        require(actual['status'] == 'PASS' and type(actual['checks']) is int and actual['checks'] >= 100,
                'unexpected behavior result')
        require(actual['v1_alias_bypass_observed'] is True, 'safe v1 regression control missing')
        a, b = bytes.fromhex(actual['actual_a_hex']), bytes.fromhex(actual['actual_b_hex'])
        expected_a = bytes.fromhex('00017f80ff1020304050607090a0b0c0')
        expected_b = bytes.fromhex('deadbeefaa5500ff')
        require(a == expected_a and b == expected_b, 'sealed bytes differ from independent fixed vector')
        actual_sha = hashlib.sha256(a + b).hexdigest()
        require(actual_sha == hashlib.sha256(expected_a + expected_b).hexdigest(), 'test-vector hash mismatch')
        report.update(status='BOUNDED_SYNTHETIC_CPP_BEHAVIOR_PASS', behavior=actual,
                      observed_same_buffer_bytes=len(a) + len(b), observed_sha256=actual_sha,
                      python_hashlib_verified=True, rejected_hard_cap_request_was_not_allocated=True)
    except BaseException as error:
        report['status'] = 'FAIL'
        report['exception'] = dict(type=type(error).__name__, message=str(error))
    finally:
        # Failed stages have their own retained receipt even if they raised before
        # returning. Do not replace unknown cleanup with an assumed success.
        for label in ('compiler_version', 'compile', 'run'):
            path = output / (label + '.json')
            if path.exists():
                report['stages'][label] = json.loads(path.read_text())
        save(output / 'RESULT.json', report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] == 'BOUNDED_SYNTHETIC_CPP_BEHAVIOR_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
