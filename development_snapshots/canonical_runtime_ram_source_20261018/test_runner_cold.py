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
runner = types.ModuleType('runtime_ram_gate_runner_v1')
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
        return dict(status='RUNTIME_MEMORY_UNIT_BEHAVIOR_PASS', checks=123,
                    max_synthetic_arena_bytes=1024, adapter_runtime_bound=False,
                    canonical_input_sha_verified=False, full_host_ready=False,
                    launch_ready=False, eda_executed=False)

    def diagnostic(self, case, path):
        member={1:'N0RetirementAdapter',2:'stage_aw',3:'payload_',4:'RuntimeOwner::RuntimeOwner'}[case]
        return (str(path)+":10:5: error: '"+member+"' is private within this context\n").encode()

    def test_09_expected_nonzero_requires_clean_exit_one(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); fake=FakeOS('compiler_fail')
            with fake.patches():
                result,_=runner.bounded('negative_1',['mock'],root,root,30,30,expected_exit=1)
            self.assertEqual(result['exit_code'],1)
            self.assertEqual(result['expected_exit'],1)
            self.assertEqual(result['status'],'PASS')
            self.assertTrue(result['cleanup_confirmed'])
            for code in (True,2,-9,None):
                with self.assertRaises(ValueError):
                    runner.bounded('never',['mock'],root,root,30,30,expected_exit=code)

    def test_10_pinned_inputs_and_drift(self):
        copied,verified=runner.prepare_inputs(HERE)
        self.assertEqual(len(copied),10)
        self.assertEqual(set(copied),set(runner.BUILD_NAMES))
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name,raw in copied.items(): (root/name).write_bytes(raw)
            (root/'BUILD_INPUT_PINS.json').write_bytes((HERE/'BUILD_INPUT_PINS.json').read_bytes())
            self.assertEqual(runner.prepare_inputs(root),(copied,verified))
            (root/'runtime_ram.hpp').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'source input drift'): runner.prepare_inputs(root)

    def test_11_exact_behavior_schema_and_earned_scope(self):
        good=self.good()
        self.assertEqual(runner.validate_behavior(good),good)
        bad=[[],None,dict(good,extra=1),{k:v for k,v in good.items() if k!='checks'},
             dict(good,status='PASS'),dict(good,checks=True),dict(good,checks=0),
             dict(good,checks=-1),dict(good,max_synthetic_arena_bytes=True),
             dict(good,max_synthetic_arena_bytes=1025)]
        for key in ('adapter_runtime_bound','canonical_input_sha_verified','full_host_ready','launch_ready','eda_executed'):
            bad.extend([dict(good,**{key:True}),dict(good,**{key:0})])
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError): runner.validate_behavior(value)
        self.assertEqual(runner.strict_json(json.dumps(good).encode()),good)
        for raw in (b'{"checks":1,"checks":2}',b'{"checks":NaN}',b'{} trailing',b'\xff'):
            with self.assertRaises((ValueError,UnicodeError)): runner.strict_json(raw)

    def test_12_negative_diagnostic_exact_private_member_only(self):
        source=HERE/'negative_public_access.cpp'
        for case in (1,2,3,4):
            good=self.diagnostic(case,source)
            self.assertEqual(runner.validate_negative(case,good,source)['status'],'EXPECTED_PRIVATE_ACCESS_REJECTED')
            bad=[b'',good+good,good.replace(b'is private within this context',b'was not declared'),
                 good.replace(b'error:',b'fatal error:'),good.replace(str(source).encode(),b'other.cpp'),
                 good+b'x.cpp:1:1: error: unexpected syntax\n',good+b'internal compiler error: crash\n',
                 good+b'CANONICAL_RUNTIME_UNIT_TEST\n',b'error: unknown argument\n']
            for raw in bad:
                with self.subTest(case=case,raw=raw),self.assertRaises(ValueError): runner.validate_negative(case,raw,source)
            if case!=4:
                clang=good.replace(b'is private within this context',b"is a private member of 'RuntimeOwner'")
            else:
                clang=(str(source)+":10:5: error: calling a private constructor of class 'canonical_runtime_v1::RuntimeOwner'\n").encode()
            self.assertEqual(runner.validate_negative(case,clang,source)['case'],case)
        with self.assertRaises(ValueError): runner.validate_negative(1,self.diagnostic(2,source),source)

    def test_13_original_supervision_preserved_except_exit_contract(self):
        delta=json.loads((HERE/'RUNNER_DELTA.json').read_text())
        source=(HERE/'run_behavior.py').read_bytes();lines=source.splitlines(keepends=True)
        funcs={n.name:b''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
        for name,expected in delta['retained_function_bytes'].items():
            self.assertEqual(runner.digest(funcs[name]),expected)
        bounded=funcs['bounded'].decode()
        restored=bounded.replace(', expected_exit=0):','):').replace(
            "    require(type(expected_exit) is int and expected_exit in (0, 1), 'unsupported expected exit')\n",'').replace(
            'cleanup_budget_seconds=5, expected_exit=expected_exit)','cleanup_budget_seconds=5)').replace(
            "record['exit_code'] == expected_exit","record['exit_code'] == 0")
        self.assertEqual(runner.digest(restored.encode()),delta['original_bounded'])

    def mock_main(self, mode='pass'):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); compiler=root/'mock-compiler';compiler.write_bytes(b'not executed; dynamic identity test')
            output=root/'results';stages=[]
            def fake_bounded(label,command,directory,destination,wall,cpu,expected_exit=0):
                stages.append((label,wall,cpu,expected_exit))
                receipt=dict(status='PASS',expected_exit=expected_exit,exit_code=expected_exit,
                             cleanup_confirmed=True,reaped=True,group_state='absent')
                runner.save(destination/(label+'.json'),receipt)
                if mode=='fail' and label=='compile_O0':
                    receipt.update(status='FAIL',exit_code=1)
                    runner.save(destination/(label+'.json'),receipt)
                    raise ValueError('mock compile failure')
                log=b'mock version' if label=='compiler_version' else b''
                if label.startswith('run_'):
                    good=self.good()
                    if mode=='mismatch' and label=='run_O2':good['checks']+=1
                    log=json.dumps(good).encode()
                if label.startswith('negative_'):
                    self.assertIn('-UCANONICAL_RUNTIME_UNIT_TEST',command)
                    self.assertNotIn('-DCANONICAL_RUNTIME_UNIT_TEST',command)
                    self.assertIn('-fsyntax-only',command)
                    self.assertEqual(command[-1],str(directory/'negative_public_access.cpp'))
                    log=self.diagnostic(int(label[-1]),directory/'negative_public_access.cpp')
                    if mode=='bad_negative':log=b'x.cpp:1:1: error: syntax\n'
                (destination/(label+'.log')).write_bytes(log)
                return receipt,log
            with mock.patch.object(runner,'bounded',side_effect=fake_bounded), \
                 mock.patch.object(runner.shutil,'which',return_value=str(compiler)), \
                 mock.patch.object(sys,'argv',['mock','--output',str(output)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                code=runner.main()
            result=json.loads((output/'RESULT.json').read_text())
            self.assertEqual(result['compiler']['sha256'],hashlib.sha256(compiler.read_bytes()).hexdigest())
            self.assertTrue((output/'build/runtime_ram.hpp').exists())
            for name in runner.BUILD_NAMES:
                self.assertEqual((output/'build'/name).read_bytes(),(HERE/name).read_bytes())
            self.assertFalse(result['adapter_runtime_bound'])
            self.assertFalse(result['canonical_input_sha_verified'])
            return code,result,stages

    def test_14_mocked_serial_success(self):
        code,result,stages=self.mock_main()
        self.assertEqual(code,0)
        self.assertEqual(result['status'],'BOUNDED_TINY_RUNTIME_RAM_BEHAVIOR_PASS')
        self.assertEqual(stages,[('compiler_version',5,2,0),('compile_O0',30,30,0),('run_O0',10,5,0),
            ('compile_O2',30,30,0),('run_O2',10,5,0)]+[('negative_'+str(i),30,30,1) for i in range(1,5)])
        self.assertEqual(result['behavior']['O0'],result['behavior']['O2'])
        self.assertEqual(set(result['negative_results']),{'1','2','3','4'})

    def test_15_failure_preserves_and_stops_no_retry(self):
        code,result,stages=self.mock_main('fail')
        self.assertEqual(code,1);self.assertEqual(result['status'],'FAIL')
        self.assertEqual(len(stages),2);self.assertEqual(result['stages']['compile_O0']['exit_code'],1)

    def test_16_o0_o2_disagreement_rejects_before_negative(self):
        code,result,stages=self.mock_main('mismatch')
        self.assertEqual(code,1);self.assertEqual(len(stages),5)
        self.assertEqual(result['negative_results'],{})

    def test_17_nonprivate_failure_never_passes_gate(self):
        code,result,stages=self.mock_main('bad_negative')
        self.assertEqual(code,1);self.assertEqual(len(stages),6)
        self.assertEqual(result['negative_results'],{})

    def test_18_source_cpp_projection_matches_v2(self):
        pins=json.loads((HERE/'BUILD_INPUT_PINS.json').read_text())
        self.assertEqual(pins['source_directory'],'production_host_runtime_ram_source_v2_20261018')
        self.assertEqual(pins['source_manifest']['sha256'],'a3d130cb7aa1b0e47e8abe5b7731f88ff81af4ab144bcc2a11bf5782cb4d2f20')
        self.assertIn(b'for(const auto& range:',(HERE/'test_runtime_ram.cpp').read_bytes())
        self.assertNotIn(b'#define CANONICAL_RUNTIME_UNIT_TEST',(HERE/'runtime_ram.hpp').read_bytes())

    def test_19_original_eight_constructed_mixed_diagnostics(self):
        source=HERE/'negative_public_access.cpp'
        suffixes=(b'virtual memory exhausted: Cannot allocate memory\n',
                  b'driver: ERROR: unexpected compiler failure\n')
        for case in (1,2,3,4):
            good=self.diagnostic(case,source)
            self.assertEqual(runner.validate_negative(case,good,source)['case'],case)
            for suffix in suffixes:
                with self.subTest(case=case,suffix=suffix),self.assertRaises(ValueError):
                    runner.validate_negative(case,good+suffix,source)
        # Scope is finite: ordinary unclassified context is still allowed.
        self.assertEqual(runner.validate_negative(1,self.diagnostic(1,source)+b'ordinary context\n',source)['case'],1)

if __name__=='__main__':
    unittest.main(verbosity=2)
