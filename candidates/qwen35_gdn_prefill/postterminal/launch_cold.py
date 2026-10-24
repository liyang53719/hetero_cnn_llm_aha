"""One post-terminal diagnostic using the existing pinned bounded_run helper.

Not an authorization to execute. No retry, original-run signaling, or deadline
modification. The retaining root must supply all three independently reviewed SHA arguments after
the original session has terminated with verified cleanup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
import types

HERE = Path(__file__).resolve().parent


def need(ok, reason):
    if not ok: raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def check_code(path, reviewed_sha):
    """Verify the exact adapter inventory before any sibling source executes."""
    path = Path(path)
    need(path.is_absolute() and not path.is_symlink() and path.resolve(strict=True) == path,
         'unaliased adapter pins path required')
    before = path.stat()
    need(0 < before.st_size <= 65536 and digest(reviewed_sha), 'invalid reviewed adapter pins')
    raw = path.read_bytes()
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(sha(raw) == reviewed_sha and all(getattr(before, k) == getattr(after, k) for k in fields),
         'reviewed adapter pins changed')
    pins = json.loads(raw)
    need(type(pins) is dict and set(pins) == {'cold_postterminal.py', 'terminal_gate.py', 'launch_cold.py'},
         'exact adapter code inventory')
    for name, value in pins.items():
        need(type(value) is dict and set(value) == {'bytes', 'sha256'} and
             type(value['bytes']) is int and 0 < value['bytes'] <= 2 << 20 and digest(value['sha256']),
             'invalid adapter source pin: ' + name)
        codepath = HERE / name
        need(not codepath.is_symlink() and codepath.resolve(strict=True) == codepath,
             'adapter source path alias: ' + name)
        before = codepath.stat()
        code = codepath.read_bytes()
        after = codepath.stat()
        need(len(code) == value['bytes'] and sha(code) == value['sha256'] and
             all(getattr(before, k) == getattr(after, k) for k in fields), 'adapter source changed: ' + name)
    return pins


def _load_gate(pins):
    # Compile the verified bytes, not an import-cache or bytecode substitute.
    path = HERE / 'terminal_gate.py'
    raw = path.read_bytes()
    need(not path.is_symlink() and path.resolve(strict=True) == path and
         len(raw) == pins[path.name]['bytes'] and sha(raw) == pins[path.name]['sha256'],
         'terminal gate source/origin mismatch')
    module = types.ModuleType('reviewed_local_terminal_gate')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    need(Path(module.__file__) == path and module.admit_terminal_manifest.__code__.co_filename == str(path),
         'terminal gate import origin mismatch')
    return module



def main(argv=None):
    start = time.monotonic()
    def expired(sig, frame): raise TimeoutError('fixed independent diagnostic outer deadline')
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, 330)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--reviewed-config-sha256', required=True)
    parser.add_argument('--terminal-manifest', required=True)
    parser.add_argument('--reviewed-terminal-sha256', required=True)
    parser.add_argument('--reviewed-code-pins-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--include-conv', action='store_true')
    args = parser.parse_args(argv)
    code_pins = HERE/'CODE_PINS.json'
    pins = check_code(code_pins, args.reviewed_code_pins_sha256)
    terminal_gate = _load_gate(pins)
    gate = terminal_gate.admit_terminal_manifest(args.terminal_manifest, args.reviewed_terminal_sha256,
        config_path=args.config, reviewed_config_sha=args.reviewed_config_sha256)
    need(not args.include_conv or gate['include_conv_reference_arithmetic'], 'Conv arithmetic not authorized in reviewed handoff')
    interpreter = Path(gate['plan']['comparison']['python'])
    ip = gate['plan']['inputs'][str(interpreter)]
    need(Path(sys.executable).resolve() == interpreter.resolve() == Path(ip['resolved']) and
         interpreter.stat().st_size == ip['bytes'] and hashlib.sha256(interpreter.read_bytes()).hexdigest() == ip['sha256'],
         'exact frozen comparison interpreter required')
    out = args.output_dir.absolute()
    forbidden = (Path(gate['plan']['repository']), Path(gate['_plan_path']).parent,
                 Path(gate['native_manifest']).parent.parent)
    need(not out.exists() and not out.is_symlink() and out.resolve() == out and
         not any(out.is_relative_to(root.resolve()) for root in forbidden), 'fresh independent output directory required')
    need(1 in os.sched_getaffinity(0), 'reviewed CPU1 unavailable')
    runner_path, raw = terminal_gate.read_source(gate['config']['paths']['repository'], 'bounded_run')
    runner = types.ModuleType('original_bounded_run'); runner.__file__ = str(runner_path)
    exec(compile(raw, str(runner_path), 'exec', dont_inherit=True), runner.__dict__)
    need(runner.execute.__code__.co_filename == str(runner_path), 'bounded runner origin mismatch')
    os.sched_setaffinity(0, {1})
    for key, value in ((resource.RLIMIT_AS, 4 << 30), (resource.RLIMIT_CPU, 300), (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(key, (value, value))
    out.mkdir(mode=0o700); (out/'tmp').mkdir(mode=0o700)
    environment = dict(gate['plan']['environment'], TMPDIR=str(out/'tmp'))
    command = [str(interpreter), '-I', '-S', '-B', str(HERE/'cold_postterminal.py'),
        '--config', str(gate['config']['_path']), '--reviewed-config-sha256', args.reviewed_config_sha256,
        '--reviewed-code-pins-sha256', args.reviewed_code_pins_sha256,
        '--terminal-manifest', str(gate['_manifest_path']), '--reviewed-terminal-sha256', args.reviewed_terminal_sha256,
        '--output', str(out/'COLD_DIAGNOSTIC.json')]
    if args.include_conv: command.append('--include-conv')
    # Existing helper owns its child Popen and unchanged strict cleanup. No old
    # identity or PID is passed as authority. All stops derive from this start.
    signal.setitimer(signal.ITIMER_REAL, 0)
    result = runner.execute(command, cwd=HERE, env=environment, out=out/'stdout.log', err=out/'stderr.log',
        root=out, absolute_stop=start+325, stage_stop=start+300, stdout_limit=4 << 20, tree_limit=128 << 20)
    signal.setitimer(signal.ITIMER_REAL, max(.001, start+330-time.monotonic()))
    check_code(code_pins, args.reviewed_code_pins_sha256); terminal_gate.recheck_terminal_manifest(gate)
    complete = result['exit'] == 0 and result['error'] is None and result['cleanup_complete'] is True
    record = dict(status='DIAGNOSTIC_PROCESS_COMPLETE' if complete else 'INCOMPLETE_DIAGNOSTIC_PROCESS',
        numerical_acceptance=None, combined_full_run_acceptance=False, automatic_retry=False,
        original_exec_session=gate['config']['terminal']['retained_exec_session'], original_run_signaled=False, original_deadlines_changed=False,
        code_pins_sha256=args.reviewed_code_pins_sha256, reviewed_configuration_sha256=args.reviewed_config_sha256, terminal_manifest_sha256=args.reviewed_terminal_sha256,
        started_monotonic=start, work_stop=start+300, cleanup_stop=start+325, outer_stop=start+330,
        elapsed_seconds=time.monotonic()-start, cpu=1, address_space_bytes=4 << 30,
        cpu_seconds=300, sampled_rss_limit_claimed=False, supervision=result)
    need(time.monotonic()<start+330, 'original diagnostic outer deadline exceeded')
    with (out/'PROCESS.json').open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    signal.setitimer(signal.ITIMER_REAL, 0)
    print(json.dumps(record, sort_keys=True))
    return 0 if complete else 1


if __name__ == '__main__': raise SystemExit(main())
