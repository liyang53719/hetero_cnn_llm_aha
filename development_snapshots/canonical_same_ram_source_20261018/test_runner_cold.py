"""Mock-only Linux waitid/cleanup tests. No compiler, executable or real signal."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
pins = json.loads((HERE / 'PROJECT_SOURCE_HASHES.json').read_text())['files']
raw = (HERE / 'run_behavior.py').read_bytes()
if dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) != pins['run_behavior.py']:
    raise ValueError('runner changed before source execution')
runner = types.ModuleType('same_ram_portable_runner_v2')
runner.__file__ = str(HERE / 'run_behavior.py')
sys.modules[runner.__name__] = runner
exec(compile(raw, 'run_behavior.py', 'exec', dont_inherit=True), runner.__dict__)


class FakeOS:
    def __init__(self, mode):
        self.mode, self.child, self.calls, self.time = mode, None, [], 0.0
        self.probes, self.post_reap_probes = 0, 0

    def spawn(self, command, **kwargs):
        if self.mode == 'spawn_fail':
            raise OSError('mock spawn failure')
        kwargs['stdout'].write(b'mock child diagnostic\n')
        kwargs['stdout'].flush()
        if not kwargs['start_new_session']:
            raise ValueError('fresh group required')
        self.child = types.SimpleNamespace(pid=424242, returncode=None, wait=self.wait)
        return self.child

    def waitid(self, kind, pid, flags):
        self.probes += 1
        if not flags & runner.os.WNOWAIT or pid != 424242:
            raise ValueError('must retain original unreaped child identity')
        if self.probes == 1:
            if self.mode in ('timeout', 'reap_unknown'):
                raise runner.subprocess.TimeoutExpired(['mock'], 30)
            if self.mode == 'interrupt':
                raise KeyboardInterrupt('mock interrupt')
            if self.mode == 'other_exception':
                raise RuntimeError('mock waitid failure')
        status = 1 if self.mode in ('compiler_fail', 'wait_one_present') else 0
        if self.mode in ('timeout', 'interrupt', 'other_exception', 'reap_unknown'):
            return None  # same original child is still running before cleanup
        return types.SimpleNamespace(si_pid=pid, si_code=runner.os.CLD_EXITED, si_status=status)

    def kill(self, pgid, sig):
        self.calls.append((pgid, sig))
        if pgid != 424242:
            raise ValueError('wrong original process group')
        if sig == signal.SIGKILL:
            if self.child.returncode is not None:
                raise ValueError('must never signal a reaped/reusable PGID')
            return
        if self.child.returncode is None:
            return  # alive or zombie leader anchors original group
        self.post_reap_probes += 1
        if self.mode in ('wait_zero_present', 'wait_one_present') and self.post_reap_probes == 1:
            return  # finite read-only recheck after reap
        raise ProcessLookupError('mock group absent')

    def wait(self, timeout):
        if (424242, signal.SIGKILL) not in self.calls:
            raise ValueError('must handle original group before reaping leader')
        if self.mode == 'reap_unknown':
            raise runner.subprocess.TimeoutExpired(['mock reap'], timeout)
        if self.mode in ('timeout', 'interrupt', 'other_exception'):
            self.child.returncode = -signal.SIGKILL
        else:
            self.child.returncode = 1 if self.mode in ('compiler_fail', 'wait_one_present') else 0
        return self.child.returncode

    def sleep(self, seconds):
        self.time += max(seconds, 0.001)

    def patches(self):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(runner.subprocess, 'Popen', side_effect=self.spawn))
        stack.enter_context(mock.patch.object(runner.os, 'waitid', side_effect=self.waitid))
        stack.enter_context(mock.patch.object(runner.os, 'killpg', side_effect=self.kill))
        stack.enter_context(mock.patch.object(runner.time, 'monotonic', side_effect=lambda: self.time))
        stack.enter_context(mock.patch.object(runner.time, 'sleep', side_effect=self.sleep))
        return stack


class RunnerCold(unittest.TestCase):
    def scenario(self, mode, expected_exception):
        with tempfile.TemporaryDirectory() as temporary:
            output, fake = Path(temporary), FakeOS(mode)
            with fake.patches():
                if expected_exception:
                    with self.assertRaises(expected_exception):
                        runner.bounded('compile', ['mock-c++', 'test.cpp'], output, output, 30, 30)
                else:
                    runner.bounded('compile', ['mock-c++', 'test.cpp'], output, output, 30, 30)
            record = json.loads((output / 'compile.json').read_text())
            self.assertEqual(record['status'], 'FAIL' if expected_exception else 'PASS')
            self.assertEqual(record['argv'], ['mock-c++', 'test.cpp'])
            self.assertTrue((output / 'compile.log').exists())
            self.assertLessEqual(record['seconds'], 5.001)
            if mode == 'spawn_fail':
                self.assertFalse(record['spawn_handle_acquired'])
                self.assertFalse(record['cleanup_confirmed'])
                self.assertEqual(fake.calls, [])
            else:
                self.assertEqual((output / 'compile.log').read_bytes(), b'mock child diagnostic\n')
                self.assertTrue(record['anchor_confirmed'])
                self.assertEqual(record['kill_result'], 'signal_sent_before_reap')
                self.assertEqual(fake.calls.count((424242, signal.SIGKILL)), 1)
                self.assertEqual(record['cleanup_confirmed'], mode != 'reap_unknown')
            return record

    def test_01_compiler_failure_retains_log_and_cleans_group(self):
        self.assertEqual(self.scenario('compiler_fail', ValueError)['exit_code'], 1)

    def test_02_timeout_kills_before_reap(self):
        record = self.scenario('timeout', runner.subprocess.TimeoutExpired)
        self.assertTrue(record['timed_out'])
        self.assertEqual(record['exit_code'], -signal.SIGKILL)

    def test_03_keyboard_interrupt_same_cleanup(self):
        record = self.scenario('interrupt', KeyboardInterrupt)
        self.assertEqual(record['parent_exception']['type'], 'KeyboardInterrupt')

    def test_04_other_exception_same_cleanup(self):
        self.scenario('other_exception', RuntimeError)

    def test_05_unknown_reap_not_clean(self):
        record = self.scenario('reap_unknown', runner.subprocess.TimeoutExpired)
        self.assertFalse(record['reaped'])
        self.assertFalse(record['cleanup_confirmed'])

    def test_06_spawn_failure_no_identity_guess(self):
        self.scenario('spawn_fail', OSError)

    def test_07_wait_zero_and_present_group(self):
        record = self.scenario('wait_zero_present', None)
        self.assertEqual(record['exit_code'], 0)
        self.assertTrue(record['reaped'])
        self.assertEqual(record['group_state'], 'absent')

    def test_08_wait_one_and_present_group(self):
        self.assertEqual(self.scenario('wait_one_present', ValueError)['exit_code'], 1)

    def test_09_top_level_failure_retains_build_and_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiler = root / 'mock-compiler'
            compiler.write_bytes(b'mocked compiler identity, never executed')
            output = root / 'results'
            fake = FakeOS('compiler_fail')
            with fake.patches(), mock.patch.object(runner.shutil, 'which', return_value=str(compiler)), \
                 mock.patch.object(runner, 'prepare_inputs', return_value=(
                    {n: b'mocked source\n' for n in ('initialization_ram.hpp',
                     'v1_initialization_ram.hpp', 'test_initialization_ram.cpp')}, {'mock': {}})), \
                 mock.patch.object(sys, 'argv', ['mock', '--compiler', str(compiler), '--output', str(output)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 1)
            result = json.loads((output / 'RESULT.json').read_text())
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(result['compiler']['bytes'], len(compiler.read_bytes()))
            self.assertEqual(result['compiler']['sha256'], hashlib.sha256(compiler.read_bytes()).hexdigest())
            self.assertEqual(result['stages']['compiler_version']['exit_code'], 1)
            self.assertTrue((output / 'build/test_initialization_ram.cpp').exists())
            self.assertTrue((output / 'compiler_version.log').exists())
            self.assertFalse((output / 'compile.json').exists())


    def test_10_same_directory_pins_relocate_and_reject_drift(self):
        copied, verified = runner.prepare_inputs(HERE)
        self.assertEqual(set(copied), {'initialization_ram.hpp', 'v1_initialization_ram.hpp',
                                      'test_initialization_ram.cpp'})
        self.assertEqual(len(verified), 3)
        with tempfile.TemporaryDirectory() as temporary:
            detached = Path(temporary)
            for name, raw in copied.items():
                (detached / name).write_bytes(raw)
            (detached / 'BUILD_INPUT_PINS.json').write_bytes((HERE / 'BUILD_INPUT_PINS.json').read_bytes())
            with mock.patch.object(runner, 'HERE', detached):
                self.assertEqual(runner.prepare_inputs(detached), (copied, verified))
                (detached / 'initialization_ram.hpp').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'source input drift'):
                    runner.prepare_inputs(detached)

if __name__ == '__main__':
    unittest.main(verbosity=2)
