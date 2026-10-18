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
runner = types.ModuleType('canonical16_gate_runner_v1')
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

    def spec(self):
        return json.loads((HERE/'INPUT_SPEC.json').read_text())

    def good(self):
        spec=self.spec()
        return dict(status='CANONICAL16_SAME_RAM_VERIFIED',inputs=[dict(index=i,name=r['name'],
                    base=r['base'],bytes=r['bytes'],actual_sha256=r['sha256'])
                    for i,r in enumerate(spec['inputs'])],ram_base=spec['ram_base'],ram_bytes=spec['ram_bytes'],
                    declared_coverage_bytes=94920448,same_ram_offsets_verified=True,coverage_sealed=True,
                    token_redeemed_once=True,sha256_passes=4,sha256_total_bytes=379681792,
                    full_host_ready=False,launch_ready=False,eda_executed=False)

    def test_09_exact_nine_same_byte_inputs(self):
        copied,verified=runner.prepare_inputs(HERE)
        self.assertEqual(len(copied),9)
        for n,b in copied.items():self.assertEqual(verified[n],runner.digest(b))
        self.assertEqual(len(self.spec()['inputs']),16)
        self.assertEqual(sum(r['bytes'] for r in self.spec()['inputs']),94920448)

    def test_10_actual_result_schema_and_failures(self):
        good=self.good();self.assertEqual(runner.validate_behavior(good,self.spec()),good)
        bad=[]
        for k,v in [('sha256_passes',3),('ram_base',True),('coverage_sealed',1),('launch_ready',True),('extra',0)]:
            bad.append(dict(good,**{k:v}))
        for mutate in ('hash','order','missing','duplicate','bool'):
            v=json.loads(json.dumps(good))
            if mutate=='hash':v['inputs'][0]['actual_sha256']='0'*64
            if mutate=='order':v['inputs'][:2]=v['inputs'][:2][::-1]
            if mutate=='missing':v['inputs'].pop()
            if mutate=='duplicate':v['inputs'][1]=v['inputs'][0]
            if mutate=='bool':v['inputs'][0]['index']=False
            bad.append(v)
        for v in bad:
            with self.subTest(value=v),self.assertRaises(ValueError):runner.validate_behavior(v,self.spec())

    def test_11_default_never_starts_child_or_reads_payload(self):
        with mock.patch.object(runner.subprocess,'Popen',side_effect=AssertionError('child')), \
             mock.patch.object(runner,'check_providers',side_effect=AssertionError('payload')), \
             mock.patch.object(sys,'argv',['mock']),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(),0)
        self.assertEqual(json.loads(output.getvalue())['status'],'SOURCE_CHECK_ONLY')

    def test_12_run_address_space_record_is_one_gib(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary);fake=FakeOS('wait_zero_present')
            with fake.patches():runner.bounded('run',['mock'],output,output,120,120,as_limit=1073741824)
            record=json.loads((output/'run.json').read_text())
            self.assertEqual(record['address_space_limit_bytes'],1073741824)
            self.assertEqual(record['cpu_limit_seconds'],120)

    def test_13_source_relocation_and_drift(self):
        copied,verified=runner.prepare_inputs(HERE)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for n,b in copied.items():(root/n).write_bytes(b)
            (root/'BUILD_INPUT_PINS.json').write_bytes((HERE/'BUILD_INPUT_PINS.json').read_bytes())
            with mock.patch.object(runner,'HERE',root):
                self.assertEqual(runner.prepare_inputs(root),(copied,verified))
                (root/'canonical16_binding.hpp').write_bytes(b'drift')
                with self.assertRaises(ValueError):runner.prepare_inputs(root)

    def test_14_mocked_end_to_end_no_native(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);repo=root/'repo';repo.mkdir();providers=root/'providers';providers.mkdir()
            compiler=root/'compiler';compiler.write_bytes(b'fake compiler never executed')
            output=root/'results';stages=[]
            def bounded(label,command,directory,destination,wall,cpu,as_limit=268435456):
                stages.append((label,wall,cpu,as_limit))
                receipt=dict(status='PASS',cleanup_confirmed=True,reaped=True,group_state='absent',exit_code=0)
                runner.save(destination/(label+'.json'),receipt)
                return receipt,json.dumps(self.good()).encode() if label=='run' else b'{}'
            with mock.patch.object(runner,'bounded',side_effect=bounded), \
                 mock.patch.object(runner,'check_providers',return_value={'mock':True}), \
                 mock.patch.object(runner,'validate_metadata',return_value={'mock':True}), \
                 mock.patch.object(runner.shutil,'which',return_value=str(compiler)), \
                 mock.patch.object(sys,'argv',['mock','--execute','--repo',str(repo),'--providers',str(providers),'--output',str(output)]), \
                 contextlib.redirect_stdout(io.StringIO()):self.assertEqual(runner.main(),0)
            result=json.loads((output/'RESULT.json').read_text())
            self.assertEqual(stages,[('compiler_version',5,2,268435456),('compile',30,30,268435456),
                                     ('metadata',10,5,268435456),('run',120,120,1073741824)])
            self.assertEqual(result['compiler']['sha256'],hashlib.sha256(compiler.read_bytes()).hexdigest())
            self.assertEqual(result['status'],'BOUNDED_CANONICAL16_SAME_RAM_PASS')
            self.assertFalse(result['full_host_ready'])

    def test_15_tiny_metadata_actual_hash_not_logged_hash(self):
        spec={'inputs':[dict(name='commands',bytes=1,sha256=hashlib.sha256(b'a').hexdigest()),
                        dict(name='descriptors',bytes=1,sha256=hashlib.sha256(b'b').hexdigest())]}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);files={'metadata.json':{},'metadata_layout.hpp':{}}
            for row,data in zip(spec['inputs'],(b'a',b'b')):
                n='host_'+row['name']+'.bin';(root/n).write_bytes(data);files[n]=runner.digest(data)
            log=json.dumps(dict(status='EXACT_SOURCE_METADATA_REPLAY_ONLY',tensor_payload_bytes_written=0,files=files)).encode()
            self.assertEqual(len(runner.validate_metadata(root,log,spec)),2)
            (root/'host_commands.bin').write_bytes(b'z')
            with self.assertRaises(ValueError):runner.validate_metadata(root,log,spec)

    def test_16_supervision_narrow_delta(self):
        delta=json.loads((HERE/'RUNNER_DELTA.json').read_text())
        source=(HERE/'run_behavior.py').read_bytes();lines=source.splitlines(keepends=True)
        functions={n.name:b''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
        for n,pin in delta['retained_function_bytes'].items():self.assertEqual(runner.digest(functions[n]),pin)
        bounded=functions['bounded'].decode().replace(', as_limit=AS_LIMIT):','):') \
            .replace('(as_limit, as_limit)','(AS_LIMIT, AS_LIMIT)') \
            .replace('address_space_limit_bytes=as_limit,','address_space_limit_bytes=AS_LIMIT,')
        self.assertEqual(runner.digest(bounded.encode()),delta['original_bounded_bytes'])

    def test_17_actual_receipt_pin_rejects_wrong_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'PROVIDERS.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):runner.check_providers(root,self.spec())

    def test_18_cpp_fixed_actual_span_evidence(self):
        source=(HERE/'consume_canonical16.cpp').read_text()
        self.assertIn('actual[i] = Sha256::hash(span.data, span.size)',source)
        self.assertIn('hex(actual[i])',source)
        self.assertNotIn('hex(row.sha256)',source)
        self.assertNotIn('view.reverify()',source)
        self.assertEqual(source.count('loader.load_next('),1)
        self.assertEqual(source.count('loader.finish()'),1)
        self.assertEqual(source.count('loader.take_ready(token)'),1)


if __name__=='__main__':unittest.main(verbosity=2)
