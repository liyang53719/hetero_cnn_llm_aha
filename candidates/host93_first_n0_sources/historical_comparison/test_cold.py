"""Tiny stdlib-only source/gate fixtures. No native or numerical library imports."""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ['N0_COMPARISON_SOURCE_REPO']).resolve()
HELPER = Path(os.environ['N0_COMPARISON_REFERENCE_WORKER']).resolve()
WORKER_BYTES = 21000
WORKER_SHA256 = 'e2d1a644e369147772ccd3e6b074559a9b29e9230ace172a3f4bcb4594794800'

def load_worker(raw):
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise ValueError('isolation')
    if type(raw) is not bytes or len(raw) != WORKER_BYTES:
        raise ValueError('length')
    if hashlib.sha256(raw).hexdigest() != WORKER_SHA256:
        raise ValueError('digest')
    module = types.ModuleType('cold_n0_comparator')
    module.__file__ = str(HERE/'n0_compare.py')
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module

with (HERE/'n0_compare.py').open('rb') as stream:
    WORKER_RAW = stream.read(WORKER_BYTES + 1)
n = load_worker(WORKER_RAW)
SCRIPT = (REPO/n.SCRIPT_PATH).read_bytes()
CONTRACT = (REPO/n.CONTRACT_PATH).read_bytes()
BRIDGE_CONTRACT_BYTES = 1970
BRIDGE_CONTRACT_SHA256 = '299ec18b8e0990a4e8b95f1b95cbf9747e860b56376630438522df598fe460ae'

def load_bridge_contract(raw):
    if type(raw) is not bytes or len(raw) != BRIDGE_CONTRACT_BYTES:
        raise ValueError('bridge contract length')
    if hashlib.sha256(raw).hexdigest() != BRIDGE_CONTRACT_SHA256:
        raise ValueError('bridge contract digest')
    return json.loads(raw)

def bridge_contract_from_environment(environment):
    value = environment.get('N0_COMPARISON_BRIDGE_CONTRACT')
    if not isinstance(value, str) or not value:
        raise ValueError('bridge contract environment')
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('bridge contract absolute path')
    raw = n.read_fixed(path, BRIDGE_CONTRACT_BYTES, BRIDGE_CONTRACT_SHA256)
    return load_bridge_contract(raw)

class Symbol:
    def __init__(self, label, calls):
        self.label, self.calls = label, calls
        self.shape, self.size = tuple(n.SHAPE), n.ELEMENTS
    def astype(self, dtype):
        self.calls.append(('astype', self.label, dtype)); return Symbol(self.label + '64', self.calls)
    def reshape(self, shape):
        self.calls.append(('reshape', self.label, shape)); return self
    def view(self, dtype):
        self.calls.append(('view', self.label, dtype)); return self
    def __sub__(self, other):
        self.calls.append(('subtract', self.label, other.label)); return Symbol('error', self.calls)
    def __ne__(self, other):
        return Symbol('different', self.calls)
    def tobytes(self):
        return self.label.encode()

class FakeNumpy:
    float32, float64, uint32 = 'f32', 'f64', 'u32'
    def __init__(self):
        self.calls = []
        self.linalg = types.SimpleNamespace(norm=self.norm)
    def asarray(self, value, dtype):
        self.calls.append(('asarray', value.label, dtype)); return value
    def isfinite(self, value):
        return types.SimpleNamespace(all=lambda: True)
    def norm(self, value):
        self.calls.append(('norm', value.label)); return {'a64': 2., 'r64': 2., 'error': .25}[value.label]
    def abs(self, value):
        return Symbol('abs(' + value.label + ')', self.calls)
    def max(self, value):
        self.calls.append(('max', value.label)); return .03125 if value.label == 'abs(error)' else 1.
    def mean(self, value):
        self.calls.append(('mean', value.label)); return .005
    def flatnonzero(self, value):
        self.calls.append(('flatnonzero', value.label)); return types.SimpleNamespace(size=0)
    def dot(self, a, b):
        self.calls.append(('dot', a.label, b.label)); return 4.
    def ascontiguousarray(self, value):
        return value

def fixture_counts():
    c = {key: 0 for key in n.COUNT_KEYS}
    c.update(scope='FIRST_N0_M128_ONLY', status='ACK0_ACTUAL_CAPTURED', numeric_comparison='NOT_RUN',
        phase='OUTPUT', code='ACK0_COMPLETE', full_block_pass=False, root256_handles='UNKNOWN', cycle_budget=8000000,
        reduction_only_source_floor=2428928, unproven_overhead_allowance=5571072,
        cycles=3000000, launches=1, jobs=1, owner_dones=1, completion_acks=1,
        committed_bytes=786432, successful_b=12288, writeback_bytes=786432,
        post_pc=1, post_issued_jobs=1, further_eval_calls=0, actual_values=n.ELEMENTS, actual_bytes=786432)
    c.update({k: [0]*v for k, v in n.ARRAY_SIZES.items()})
    c['axi'] = {key: 0 for key in n.AXI_KEYS}
    c['axi'].update(bs=12288, strobed_bytes=786432)
    return c

def fixture_metrics(exact=False, maximum=.03125, mean=.005):
    return dict(shape=n.SHAPE[:], elements=n.ELEMENTS, finite=True,
        max_abs=maximum, mean_abs=mean, relative_l2=0.125, cosine=1., normalized_max_abs=.03125,
        different_elements=0 if exact else 10, bit_exact=exact, first_difference_flat=None if exact else 7,
        actual_f32_sha256=n.REFERENCE['sha256'] if exact else 'a'*64, reference_f32_sha256=n.REFERENCE['sha256'])

class Cold(unittest.TestCase):
    def test_loader_rejects_before_compile(self):
        for raw in (WORKER_RAW+b' ', bytes([WORKER_RAW[0]^1])+WORKER_RAW[1:]):
            with mock.patch('builtins.compile', side_effect=AssertionError('compile')) as spy:
                with self.assertRaises(ValueError): load_worker(raw)
                spy.assert_not_called()
    def test_loader_isolation_and_samebuffer(self):
        with mock.patch.object(sys, 'flags', types.SimpleNamespace(isolated=0,no_site=1,dont_write_bytecode=1)):
            with self.assertRaisesRegex(ValueError, 'isolation'): load_worker(WORKER_RAW)
        with mock.patch.object(Path, 'open', side_effect=AssertionError('reopen')):
            self.assertEqual(load_worker(WORKER_RAW).ELEMENTS, 196608)
    def test_cold_import(self):
        self.assertFalse(any(k.split('.')[0] in ('numpy','torch','transformers') for k in sys.modules))
    def test_default_no_execution(self):
        with mock.patch.object(n,'run',side_effect=AssertionError('run')), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(n.main([]),0)
        self.assertEqual(output.getvalue(),'N0_COMPARISON_NOT_EXECUTED\n')
    def test_missing_argument_fixed_boundary(self):
        with mock.patch.object(n,'run',side_effect=AssertionError('run')), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(n.main(['--execute']),1)
        self.assertEqual(output.getvalue(),'NOT_COMPLETED:FLAGS\n')
    def test_original_functions_source_identity(self):
        ns = n.original_namespace(SCRIPT, types.SimpleNamespace())
        self.assertTrue(all(callable(ns[k]) for k in n.FUNCTIONS))
        self.assertEqual({k for k,v in ns.items() if isinstance(v, types.FunctionType)},set(n.FUNCTIONS))
    def test_original_tamper_before_compile(self):
        bad = bytes([SCRIPT[0]^1])+SCRIPT[1:]
        with mock.patch('builtins.compile',side_effect=AssertionError('compile')) as spy:
            with self.assertRaises(n.Rejected): n.original_namespace(bad,None)
            spy.assert_not_called()
    def test_original_policy_uses_verified_buffer(self):
        ns = n.original_namespace(SCRIPT,None)
        with mock.patch.object(Path,'open',side_effect=AssertionError('reopen')), mock.patch.object(Path,'read_text',side_effect=AssertionError('reread')):
            policy=n.original_policy(ns,CONTRACT)
        self.assertEqual(policy['operator'],{'max_abs':.03125,'mean_abs':.005})
        self.assertEqual(policy['sha256'],n.ORIGINAL_CONTRACT['sha256'])
        with self.assertRaises(n.Rejected): n.BufferRoot(CONTRACT+b' ')
    def test_original_compare_calls_original_methods(self):
        fake=FakeNumpy(); ns=n.original_namespace(SCRIPT,fake)
        result=ns['compare'](Symbol('a',fake.calls),Symbol('r',fake.calls))
        self.assertEqual(result['max_abs'],.03125);self.assertEqual(result['mean_abs'],.005)
        self.assertIn(('asarray','a','f32'),fake.calls);self.assertIn(('asarray','r','f32'),fake.calls)
        self.assertIn(('astype','a','f64'),fake.calls);self.assertIn(('astype','r','f64'),fake.calls)
        self.assertIn(('mean','abs(error)'),fake.calls);self.assertIn(('max','abs(error)'),fake.calls)
    def test_original_tolerance_boundary(self):
        ns=n.original_namespace(SCRIPT,None);policy=n.original_policy(ns,CONTRACT)
        self.assertTrue(ns['stage_verdict']('n0',fixture_metrics(), 'bf16',policy)['passed'])
        for maximum,mean in ((.0312500001,.005),(.03125,.0050000001)):
            self.assertFalse(ns['stage_verdict']('n0',fixture_metrics(maximum=maximum,mean=mean),'bf16',policy)['passed'])
    def test_numeric_pass_not_replaced_by_exact(self):
        ns=n.original_namespace(SCRIPT,None); policy=n.original_policy(ns,CONTRACT)
        ns['compare']=mock.Mock(return_value=fixture_metrics(False))
        with mock.patch.object(n,'digest',side_effect=['a'*64,n.REFERENCE['sha256']]):
            result=n.evaluate(ns,None,None,policy,b'a',b'r')
        self.assertTrue(result['numeric_pass']); self.assertFalse(result['bit_exact']); self.assertFalse(result['hash_exact'])
        self.assertNotIn('first_difference_flat',result['metrics'])
    def test_exact_pass_separate(self):
        ns=n.original_namespace(SCRIPT,None);policy=n.original_policy(ns,CONTRACT);ns['compare']=lambda *_:fixture_metrics(True)
        with mock.patch.object(n,'digest',return_value=n.REFERENCE['sha256']):result=n.evaluate(ns,None,None,policy,b'r',b'r')
        self.assertTrue(result['numeric_pass']);self.assertTrue(result['bit_exact']);self.assertTrue(result['hash_exact'])
    def test_hard_metrics_gates(self):
        ns=n.original_namespace(SCRIPT,None);policy=n.original_policy(ns,CONTRACT)
        for key,value in (('shape',[1]),('elements',1),('finite',False),('max_abs',float('nan')),('different_elements',-1)):
            metrics=fixture_metrics();metrics[key]=value;ns['compare']=lambda *_:metrics
            with self.assertRaises(n.Rejected):n.evaluate(ns,None,None,policy,b'a',b'r')
    def test_reference_hash_hard_gate(self):
        ns=n.original_namespace(SCRIPT,None);policy=n.original_policy(ns,CONTRACT);ns['compare']=lambda *_:fixture_metrics()
        with mock.patch.object(n,'digest',return_value='b'*64),self.assertRaises(n.Rejected):n.evaluate(ns,None,None,policy,b'a',b'r')
    def test_capture_exact_success(self):
        counts=fixture_counts();self.assertEqual(n.capture_gate(json.dumps(counts).encode()),counts)
    def test_capture_gates(self):
        for key,value in (('status','INCOMPLETE_CYCLE_BUDGET'),('successful_b',12287),('completion_acks',0),('actual_values',196607),('actual_bytes',786431),('post_pc',2),('further_eval_calls',1),('jobs',True),('input_ar',[0]),('cycles',8000001)):
            counts=fixture_counts();counts[key]=value
            with self.assertRaises(n.Rejected):n.capture_gate(json.dumps(counts).encode())
    def test_capture_duplicate_unknown_keys_and_nonfinite(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
            with self.assertRaises(n.Rejected):n.capture_gate(raw)
        counts=fixture_counts();counts['unknown']='DO_NOT_PRINT'
        with self.assertRaises(n.Rejected):n.capture_gate(json.dumps(counts).encode())
    def test_reference_helper_fixed_buffer(self):
        raw=HELPER.read_bytes()
        with mock.patch.object(Path,'open',side_effect=AssertionError('reopen')):
            helper=n.load_reference_helper(raw)
        self.assertEqual(helper.F32_SHA256,n.REFERENCE['sha256'])
        with mock.patch('builtins.compile',side_effect=AssertionError('compile')) as spy:
            with self.assertRaises(n.Rejected):n.load_reference_helper(raw+b' ')
            spy.assert_not_called()
    def test_file_identity_size_and_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'input';p.write_bytes(b'abc')
            self.assertEqual(n.read_fixed(p,3,n.digest(b'abc')),b'abc')
            for size in (2,4):
                with self.assertRaises(n.Rejected):n.read_fixed(p,size)
            q=Path(root)/'link';q.symlink_to(p)
            with self.assertRaises(n.Rejected):n.read_fixed(q,3)
            fifo=Path(root)/'fifo';os.mkfifo(fifo)
            with self.assertRaises(n.Rejected):n.read_fixed(fifo,0)
    def test_public_allowlist_and_exclusive_receipt(self):
        report=n.new_report();raw=n.report_bytes(report)
        self.assertNotIn(b'exception',raw)
        report['unexpected']='DO_NOT_PRINT'
        with self.assertRaises(n.Rejected):n.report_bytes(report)
        with tempfile.TemporaryDirectory() as root:
            out=Path(root);n.write_receipt(out,n.new_report())
            self.assertEqual((out/'RECEIPT.json').stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError):n.write_receipt(out,n.new_report())
    def test_checked_arrays_full_shape_and_finite(self):
        def array(finite=True, shape=None, size=None, dtype='fp32le'):
            value=types.SimpleNamespace(shape=tuple(n.SHAPE if shape is None else shape),size=n.ELEMENTS if size is None else size,dtype=dtype,finite=finite)
            value.reshape=lambda _: value
            return value
        raw=bytes(n.REFERENCE['bytes'])
        fake=types.SimpleNamespace(dtype=lambda _: 'fp32le',isfinite=lambda value:types.SimpleNamespace(all=lambda:value.finite))
        for field,value in (('finite',False),('shape',[1]),('size',196607),('dtype','wrong')):
            kwargs={field:value}
            fake.frombuffer=mock.Mock(side_effect=[array(**kwargs),array()])
            with self.assertRaises(n.Rejected):n.checked_arrays(fake,raw,raw)
            fake.frombuffer=mock.Mock(side_effect=[array(),array(**kwargs)])
            with self.assertRaises(n.Rejected):n.checked_arrays(fake,raw,raw)
        fake.frombuffer=mock.Mock(side_effect=[array(),array()])
        self.assertEqual(len(n.checked_arrays(fake,raw,raw)),2)
        with self.assertRaises(n.Rejected):n.checked_arrays(fake,raw[:-1],raw)
    def test_samebuffer_launcher_no_reopen(self):
        launch_raw=(HERE/'launch.py').read_bytes()
        namespace={'__name__':'cold_launcher','__file__':str(HERE/'launch.py')}
        exec(compile(launch_raw,'<cold-launcher>','exec'),namespace)
        with mock.patch.object(Path,'open',side_effect=AssertionError('reopen')):
            loaded=namespace['load'](WORKER_RAW)
        self.assertEqual(loaded['ELEMENTS'],196608)
        for raw in (WORKER_RAW+b' ',bytes([WORKER_RAW[0]^1])+WORKER_RAW[1:]):
            with mock.patch('builtins.compile',side_effect=AssertionError('compile')) as spy:
                with self.assertRaises(ValueError):namespace['load'](raw)
                spy.assert_not_called()
    def test_bridge_v3_exact_source_contract(self):
        contract=bridge_contract_from_environment(os.environ)
        self.assertEqual(n.COUNT_KEYS,set(contract['count_keys']))
        self.assertEqual(n.ARRAY_SIZES,contract['arrays'])
    def test_bridge_environment_missing_or_relative_rejected(self):
        for environment in ({},{'N0_COMPARISON_BRIDGE_CONTRACT':''},{'N0_COMPARISON_BRIDGE_CONTRACT':'relative.json'}):
            with mock.patch.object(n,'read_fixed',side_effect=AssertionError('read')) as reader:
                with self.assertRaises(ValueError):bridge_contract_from_environment(environment)
                reader.assert_not_called()
    def test_bridge_buffer_tamper_before_parse(self):
        path=Path(os.environ['N0_COMPARISON_BRIDGE_CONTRACT'])
        raw=n.read_fixed(path,BRIDGE_CONTRACT_BYTES,BRIDGE_CONTRACT_SHA256)
        for bad in (raw+b' ',bytes([raw[0]^1])+raw[1:]):
            with mock.patch.object(json,'loads',side_effect=AssertionError('parse')) as parser:
                with self.assertRaises(ValueError):load_bridge_contract(bad)
                parser.assert_not_called()
    def test_bridge_load_parses_same_verified_buffer(self):
        path=Path(os.environ['N0_COMPARISON_BRIDGE_CONTRACT'])
        raw=n.read_fixed(path,BRIDGE_CONTRACT_BYTES,BRIDGE_CONTRACT_SHA256)
        original=json.loads
        with mock.patch.object(Path,'open',side_effect=AssertionError('reopen')),mock.patch.object(json,'loads',wraps=original) as parser:
            contract=load_bridge_contract(raw)
        self.assertEqual(parser.call_count,1)
        self.assertIs(parser.call_args.args[0],raw)
        self.assertEqual(set(contract['count_keys']),n.COUNT_KEYS)
    def test_bridge_environment_bad_sha_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'contract.json';path.write_bytes(b'x'*BRIDGE_CONTRACT_BYTES)
            with mock.patch.object(json,'loads',side_effect=AssertionError('parse')) as parser:
                with self.assertRaises(n.Rejected):bridge_contract_from_environment({'N0_COMPARISON_BRIDGE_CONTRACT':str(path)})
                parser.assert_not_called()
    def test_bridge_v3_phase_and_code(self):
        for key,value in (('phase','RTL_N0'),('code','CYCLE_BUDGET'),('phase',None),('code',0)):
            counts=fixture_counts();counts[key]=value
            with self.assertRaises(n.Rejected):n.capture_gate(json.dumps(counts).encode())
        for key in ('phase','code'):
            counts=fixture_counts();del counts[key]
            with self.assertRaises(n.Rejected):n.capture_gate(json.dumps(counts).encode())
    def test_bridge_v3_terminal_failure_not_capture(self):
        counts=dict(scope='FIRST_N0_M128_ONLY',status='CONTRACT_ERROR',phase='INPUT_LOAD',code='UNMAPPED',numeric_comparison='NOT_RUN')
        with self.assertRaises(n.Rejected):n.capture_gate(json.dumps(counts).encode())
    def test_malformed_cli_has_fixed_stdout_empty_stderr(self):
        for args in (['--UNTRUSTED_PARAMETER'],['--shared-stop','UNTRUSTED_VALUE'],['--actual'],['--execute=UNTRUSTED_VALUE'],['--exe']):
            with contextlib.redirect_stdout(io.StringIO()) as stdout,contextlib.redirect_stderr(io.StringIO()) as stderr,mock.patch.object(n,'run',side_effect=AssertionError('run')):
                self.assertEqual(n.main(args),1)
            self.assertEqual(stdout.getvalue(),'NOT_COMPLETED:FLAGS\n');self.assertEqual(stderr.getvalue(),'')
    def test_completed_numeric_fail_exit_semantics(self):
        args=['--execute','--shared-stop','100']
        for name in ('repo','reference-worker','pins','runtime-root','python','reference','actual','capture','out'):
            args+=['--'+name,'/fixed']
        report=n.new_report();report.update(status='N0_LIMITED_TOLERANCE_FAIL',stage='COMPLETE',code=None,numeric_pass=False)
        with mock.patch.object(n,'run',return_value=report),contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(n.main(args),1)
        self.assertEqual(stdout.getvalue(),'N0_LIMITED_TOLERANCE_FAIL\n')
    def test_completed_pass_and_incomplete_exit_semantics(self):
        args=['--execute','--shared-stop','100']
        for name in ('repo','reference-worker','pins','runtime-root','python','reference','actual','capture','out'):
            args+=['--'+name,'/fixed']
        for status,code,numeric,expected in (('N0_LIMITED_TOLERANCE_PASS',None,True,0),('NOT_COMPLETED','CAPTURE',None,1)):
            report=n.new_report();report.update(status=status,code=code,numeric_pass=numeric)
            with mock.patch.object(n,'run',return_value=report),contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(n.main(args),expected)
            self.assertEqual(stdout.getvalue(),status+(':'+code if code else '')+'\n')
    def test_source_no_forward_or_recovery(self):
        tree=ast.parse(WORKER_RAW)
        called=[node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)]
        self.assertNotIn('recover',called);self.assertNotIn('forward',called)
        self.assertNotIn('assert ',WORKER_RAW.decode())
        self.assertEqual(WORKER_RAW.count(b'import numpy as np'),1)
        self.assertEqual(WORKER_RAW.count(b'import torch'),1)

if __name__ == '__main__': unittest.main()
