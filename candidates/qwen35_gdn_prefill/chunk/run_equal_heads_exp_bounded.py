"""Bounded source-pinned test runner; never compile, fetch, or spawn a child.

Invoke under external timeout 30s. The inner alarm is 25s and CPU limit 20s.
The manifest is generated/reviewed before execution, not accepted from a receipt.
"""
import argparse
import ctypes  # Interpreter handle initialization precedes the cold test phase.
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
import unittest


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pins', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    manifest = json.loads(args.pins.read_text())
    if args.out.exists():
        raise ValueError('new output directory required')
    args.out.mkdir(parents=True)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    os.environ['OPENBLAS_NUM_THREADS'] = os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['MKL_NUM_THREADS'] = os.environ['NUMEXPR_NUM_THREADS'] = '1'
    sys.dont_write_bytecode = True
    library = Path(manifest['native_library']).resolve(strict=True)
    os.environ['GDN_VECTOR16_R2_LIBRARY'] = str(library)
    sys.path.insert(0, str(root))
    pins = manifest['files']
    def capture():
        return {name: digest(Path(name) if Path(name).is_absolute() else root / name)
                for name in pins}
    before = capture()
    if before != pins:
        raise ValueError('pre-execution source/library/receipt/interpreter pin mismatch')
    if digest(Path(sys.executable).resolve()) != manifest['interpreter_sha256']:
        raise ValueError('interpreter does not match reviewed pins')
    denied, loads = [], []
    phase = 'cold'
    def audit(event, arguments):
        blocked = event.startswith(('subprocess.', 'socket.')) or event in (
            'os.system', 'os.posix_spawn', 'os.posix_spawnp', 'os.fork', 'os.forkpty',
            'os.exec', 'os.spawn', 'pty.spawn')
        if event == 'ctypes.dlopen':
            name = arguments[0]
            loads.append(dict(phase=phase, library=None if name is None else str(name)))
            blocked = phase == 'cold' or (name is not None and Path(name).resolve() != library)
        if blocked:
            denied.append(event)
            raise RuntimeError('bounded test denied operation: ' + event)
    sys.addaudithook(audit)
    def expired(signum, frame):
        raise TimeoutError('25 second bounded test alarm')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(25)
    started = time.monotonic()
    results, probe_report = {}, None
    error = None
    try:
        for name, module in (
                ('cold', 'candidates.qwen35_gdn_prefill.chunk.test_equal_heads_exp_policy'),
                ('range_regression', 'candidates.qwen35_35b_exp.test_range_contract')):
            phase = name
            suite = unittest.defaultTestLoader.loadTestsFromName(module)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            results[name] = dict(tests=result.testsRun, success=result.wasSuccessful(),
                                 skip_count=len(result.skipped), errors=len(result.errors),
                                 failures=len(result.failures))
            if not result.wasSuccessful() or result.skipped or result.testsRun != 4:
                raise RuntimeError('expected exactly four successful non-skipped tests: ' + name)
        phase = 'scalar_dispatch_probe'
        from candidates.qwen35_gdn_prefill.chunk.probe_equal_heads_exp_dispatch import probe
        probe_report = probe(library)
    except BaseException as exc:
        error = dict(type=type(exc).__name__, message=str(exc))
    finally:
        signal.alarm(0)
        after = capture()
        report = dict(
            scope='EQUAL_HEADS_POLICY_GATES_RANGE_REGRESSION_AND_SCALAR_DISPATCH_ONLY',
            numerical_acceptance=None, full_block=False, rtl_executed=False,
            suites=results, scalar_dispatch_probe=probe_report, error=error,
            ctypes_loads_after_hook=loads, cold_phase_all_dlopen_denied=True,
            prehook_initialization='stdlib ctypes interpreter handle only',
            source_pins_before=before, source_pins_after=after,
            pins_unchanged=before == after == pins, denied_operations=denied,
            elapsed_seconds=time.monotonic()-started,
            bounds=dict(cpu_affinity=sorted(os.sched_getaffinity(0)),
                        memory_bytes=resource.getrlimit(resource.RLIMIT_AS),
                        cpu_seconds=resource.getrlimit(resource.RLIMIT_CPU),
                        inner_alarm_seconds=25, required_external_timeout_seconds=30,
                        subprocess_and_network_denied=True, automatic_build=False),
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            pin_scope=manifest['pin_scope'])
        (args.out / 'result.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
        print('EQUAL_HEADS_EXP_RESULT ' + json.dumps({k:v for k,v in report.items()
              if k not in ('source_pins_before', 'source_pins_after')}, sort_keys=True), flush=True)
    return 0 if len(results) == 2 and probe_report is not None and not error and not denied and before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
