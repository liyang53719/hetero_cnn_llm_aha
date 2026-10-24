"""Source-pinned, bounded scalar identity tests; no build/download/model/RTL.

External GNU timeout -k 2s 60s is required. Audit denies network and children;
all ctypes.dlopen is denied in cold phases, only None in actual scalar probes.
Python/NumPy imports are not a native-code sandbox or full environment closure.
"""
import argparse
import ctypes  # Stdlib current-process handle initializes BEFORE audited phases.
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
    parser.add_argument('--pins', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads(args.pins.read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (50, 50))
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[name] = '1'
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    pins = manifest['files']
    def capture():
        return {name: digest(root / name) for name in pins}
    before = capture()
    if before != pins or digest(Path(sys.executable).resolve()) != manifest['interpreter_sha256']:
        raise ValueError('reviewed source/interpreter pin mismatch')
    phase, denied, loads = 'cold', [], []
    def audit(event, arguments):
        blocked = event.startswith(('subprocess.', 'socket.')) or event in (
            'os.system', 'os.posix_spawn', 'os.posix_spawnp', 'os.fork', 'os.forkpty',
            'os.exec', 'os.spawn', 'pty.spawn')
        if event == 'ctypes.dlopen':
            name = arguments[0]
            loads.append(dict(phase=phase, library=None if name is None else str(name)))
            blocked = phase != 'actual_scalar' or name is not None
        if blocked:
            denied.append(event)
            raise RuntimeError('bounded test denied operation: ' + event)
    sys.addaudithook(audit)
    def expired(signum, frame):
        raise TimeoutError('55 second bounded test alarm')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(55)
    started, suites, error = time.monotonic(), {}, None
    try:
        for phase, module in (
                ('cold_scalar', 'candidates.qwen35_gdn_prefill.test_scalar_identity.ScalarBindingColdTests'),
                ('synthetic_transport', 'candidates.qwen35_gdn_prefill.test_full_driver'),
                ('cold_backend_regression', 'candidates.qwen35_gdn_prefill.chunk.test_backend_selection'),
                ('cold_policy_regression', 'candidates.qwen35_gdn_prefill.chunk.test_equal_heads_exp_policy'),
                ('actual_scalar', 'candidates.qwen35_gdn_prefill.test_scalar_identity.ScalarBindingActualArithmeticTests')):
            suite = unittest.defaultTestLoader.loadTestsFromName(module)
            expected = suite.countTestCases()
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            suites[phase] = dict(tests=result.testsRun, success=result.wasSuccessful(),
                expected=expected, skipped=len(result.skipped), errors=len(result.errors), failures=len(result.failures))
            if (not result.wasSuccessful() or result.skipped or not expected or result.testsRun != expected):
                raise RuntimeError('nonempty complete non-skipped suite required: ' + phase)
    except BaseException as exc:
        error = dict(type=type(exc).__name__, message=str(exc))
    finally:
        signal.alarm(0)
        after = capture()
        loaded = sorted({str(Path(module.__file__).resolve().relative_to(root))
                         for module in tuple(sys.modules.values())
                         if isinstance(getattr(module, '__file__', None), str) and
                         Path(module.__file__).suffix == '.py' and
                         Path(module.__file__).resolve().is_relative_to(root)})
        loaded_pinned = all(name in pins for name in loaded)
        report = dict(scope='SCALAR_CALLABLE_GUARD_COLD_CONTROL_AND_SMALL_ACTUAL_SCALAR_ONLY',
            numerical_acceptance=None, full_block_acceptance=None, rtl_passed=0, rtl_total=5,
            full_block_executed=False, rtl_executed=False, suites=suites, error=error,
            denied_operations=denied, ctypes_loads_after_hook=loads,
            prehook_initialization='stdlib ctypes current-process handle only',
            source_pins_before=before, source_pins_after=after, pins_unchanged=before == after == pins,
            loaded_repo_python_sources=loaded, loaded_repo_sources_pinned=loaded_pinned,
            bounds=dict(cpu_affinity=sorted(os.sched_getaffinity(0)), memory_bytes=resource.getrlimit(resource.RLIMIT_AS),
                cpu_seconds=resource.getrlimit(resource.RLIMIT_CPU), alarm_seconds=55, external_timeout_seconds=60,
                subprocess_and_network_denied=True, automatic_build=False),
            elapsed_seconds=time.monotonic()-started, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            pin_scope=manifest['pin_scope'])
        (args.out / 'result.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
        print('SCALAR_IDENTITY_RESULT ' + json.dumps({k: v for k, v in report.items()
              if k not in ('source_pins_before', 'source_pins_after')}, sort_keys=True), flush=True)
    return 0 if len(suites) == 5 and not error and not denied and before == after and loaded_pinned else 1


if __name__ == '__main__':
    raise SystemExit(main())
