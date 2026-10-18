"""Mock-only Linux waitid/cleanup tests. No compiler, executable or real signal."""
import contextlib
import ast
import re
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
runner = types.ModuleType('n0_wiring_gate_runner_v1')
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

    def good(self):
        return dict(status='N0_WIRING_FIXTURE_BEHAVIOR_PASS', checks=123,
                    max_synthetic_arena_bytes=1024, modelbinding=False,
                    adapter_runtime_bound=False, canonical_input_sha_verified=False,
                    actual_n0_execution=False, full_host_ready=False,
                    launch_ready=False, eda_executed=False)

    def test_09_pinned_inputs_and_drift(self):
        copied, verified = runner.prepare_inputs(HERE)
        self.assertEqual(len(copied),15)
        self.assertEqual(set(copied),set(runner.BUILD_NAMES))
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name,raw in copied.items(): (root/name).write_bytes(raw)
            (root/'BUILD_INPUT_PINS.json').write_bytes((HERE/'BUILD_INPUT_PINS.json').read_bytes())
            self.assertEqual(runner.prepare_inputs(root),(copied,verified))
            (root/'runtime_ram.hpp').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'source input drift'):runner.prepare_inputs(root)

    def test_10_exact_schema_false_model_claims(self):
        good=self.good()
        self.assertEqual(runner.validate_behavior(good),good)
        bad=[[],None,dict(good,extra=1),{k:v for k,v in good.items() if k!='checks'},
             dict(good,status='PASS'),dict(good,checks=True),dict(good,checks=0),
             dict(good,max_synthetic_arena_bytes=True),dict(good,max_synthetic_arena_bytes=1025)]
        for key in set(good)-{'status','checks','max_synthetic_arena_bytes'}:
            bad.extend([dict(good,**{key:True}),dict(good,**{key:0})])
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):runner.validate_behavior(value)
        for raw in (b'{"checks":1,"checks":2}',b'{"checks":NaN}',b'{} trailing',b'\xff'):
            with self.assertRaises((ValueError,UnicodeError)):runner.strict_json(raw)

    def test_11_supervision_bytes_unchanged(self):
        delta=json.loads((HERE/'RUNNER_DELTA.json').read_text())
        source=(HERE/'run_behavior.py').read_bytes();lines=source.splitlines(keepends=True)
        funcs={n.name:b''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
        for name,expected in delta['retained_function_bytes'].items():
            self.assertEqual(runner.digest(funcs[name]),expected)
        self.assertFalse(delta['supervision_changed'])

    def mock_main(self, mode='pass'):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);compiler=root/'mock-compiler';compiler.write_bytes(b'not executed; dynamic identity fixture')
            output=root/'results';stages=[]
            def fake_bounded(label,command,directory,destination,wall,cpu,expected_exit=0):
                stages.append((label,wall,cpu,expected_exit))
                receipt=dict(status='PASS',expected_exit=expected_exit,exit_code=expected_exit,
                             cleanup_confirmed=True,reaped=True,group_state='absent')
                runner.save(destination/(label+'.json'),receipt)
                if label=='compile_O0':
                    self.assertIn('-O0',command);self.assertNotIn('-O2',command)
                    self.assertNotIn('-DCANONICAL_RUNTIME_UNIT_TEST',command)
                    self.assertIn(str(directory/'test_launch_payload.cpp'),command)
                if mode=='fail' and label=='compile_O0':
                    receipt.update(status='FAIL',exit_code=1)
                    runner.save(destination/(label+'.json'),receipt)
                    raise ValueError('mock compile failure')
                log=b''
                if label=='run_O0':
                    result=self.good()
                    if mode=='bad_result':result['modelbinding']=True
                    log=json.dumps(result).encode()
                (destination/(label+'.log')).write_bytes(log)
                return receipt,log
            with mock.patch.object(runner,'bounded',side_effect=fake_bounded), \
                 mock.patch.object(runner.shutil,'which',return_value=str(compiler)), \
                 mock.patch.object(sys,'argv',['mock','--output',str(output)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                code=runner.main()
            result=json.loads((output/'RESULT.json').read_text())
            self.assertEqual(result['compiler']['sha256'],hashlib.sha256(compiler.read_bytes()).hexdigest())
            for name in runner.BUILD_NAMES:
                self.assertEqual((output/'build'/name).read_bytes(),(HERE/name).read_bytes())
            self.assertFalse(result['modelbinding']);self.assertFalse(result['adapter_runtime_bound'])
            self.assertEqual(result['generated_contract'],'PENDING_MISSING_REAL_GENERATED_HEADERS')
            return code,result,stages

    def test_12_mocked_two_stage_success(self):
        code,result,stages=self.mock_main()
        self.assertEqual(code,0)
        self.assertEqual(result['status'],'BOUNDED_TINY_N0_WIRING_FIXTURE_PASS')
        self.assertEqual(stages,[('compile_O0',30,30,0),('run_O0',10,5,0)])
        self.assertEqual(result['behavior'],self.good())

    def test_13_failed_compile_retains_stops_no_retry(self):
        code,result,stages=self.mock_main('fail')
        self.assertEqual(code,1);self.assertEqual(result['status'],'FAIL')
        self.assertEqual(stages,[('compile_O0',30,30,0)])

    def test_14_model_claim_rejects_successful_process(self):
        code,result,stages=self.mock_main('bad_result')
        self.assertEqual(code,1);self.assertEqual(result['status'],'FAIL')
        self.assertEqual(len(stages),2)
        self.assertTrue(result['stages']['run_O0']['cleanup_confirmed'])

    def test_15_fixture_fields_are_existing_getter_names_only(self):
        fields=(HERE/'n0_model_fields.hpp').read_text()
        fixture=(HERE/'fixture_model.hpp').read_text().split('struct ScriptedFieldFixture',1)[0]
        ports=set(re.findall(r'require\(&d\.(\w+)==',fields))
        scalars=set(re.findall(r'scalar<\d+>\(r\.(\w+)\)',fields))
        arrays=set(re.findall(r'words\(r\.(\w+)\)',fields))
        declared=set(re.findall(r'    (?:unsigned|std::uint\d+_t|std::array<std::uint32_t,16>) (\w+)(?:=0|\{\});',fixture))
        self.assertEqual(declared,ports|scalars|arrays)
        self.assertEqual((len(ports),len(scalars),len(arrays)),(83,78,3))
        self.assertNotIn('io_completion_bits_epoch',fixture)
        self.assertNotIn('io_completion_bits_tag',fixture)

    def test_16_all_production_cpp_bytes_project_exactly(self):
        delta=json.loads((HERE/'SOURCE_DELTA.json').read_text())
        self.assertEqual(len(delta['unchanged_production_files']),12)
        for name,pin in delta['unchanged_production_files'].items():
            self.assertEqual(runner.digest((HERE/name).read_bytes()),pin)
        self.assertEqual(delta['original_source_manifest']['sha256'],
            'a8cb75840def35d5cfa3129d2808ffb1dd2a294ba3574ceceb0b3ff37a7eda33')
        self.assertFalse(delta['native_executed'])

    def test_17_missing_model_probes_not_in_gate(self):
        self.assertNotIn('compile_generated_contract.cpp',runner.BUILD_NAMES)
        self.assertNotIn('negative_model_access.cpp',runner.BUILD_NAMES)
        plan=json.loads((HERE/'EXECUTION_PLAN.json').read_text())
        self.assertEqual(plan['stage_wall_seconds_sum'],40)
        self.assertEqual(plan['stage_cpu_seconds_sum'],35)
        self.assertFalse(plan['sum_is_parent_hard_deadline'])
        self.assertEqual(plan['actual_model_contract'],'PENDING')

if __name__=='__main__':
    unittest.main(verbosity=2)
