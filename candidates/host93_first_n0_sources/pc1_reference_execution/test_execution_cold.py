"""Pure synthetic/mock execution-contract tests. No child, ELF execution or arrays."""
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
PINS = {'run_reference.py': (14870, 'a1eef5869774d6b66aa332966d1de7a3b0cbca5fad640e65d9ee666d609f9684'),
        'dependency_gate.py': (5104, '57207b29c56024c2288afe9faffbc81bd2bd921868dc44badc428fd03673554c')}

def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn', 'ctypes.dlopen'):
        raise RuntimeError('COLD_NATIVE_NETWORK_FORBIDDEN')
    if event == 'import' and str(args[0]).split('.')[0] in ('numpy', 'torch', 'ctypes'):
        raise RuntimeError('COLD_NUMERICAL_IMPORT_FORBIDDEN')
sys.addaudithook(audit)

def load(name):
    raw = (HERE/name).read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != PINS[name]:
        raise RuntimeError('COLD_FIXED_SOURCE_IDENTITY')
    out = types.ModuleType(name)
    out.__file__ = str(HERE/name)
    exec(compile(raw, str(HERE/name), 'exec', dont_inherit=True), out.__dict__)
    return out
R, D = load('run_reference.py'), load('dependency_gate.py')

class Supervision(unittest.TestCase):
    def setUp(self):
        self.calls, self.stages, self.result = [], [], {'full_models_executed': False}
        self.owner = {'deadline': 210, 'handler': object()}
        self.before = mock.Mock()
        self.binary = mock.Mock(return_value={'identity': 'fixed'})
        self.clock = mock.patch.object(R.time, 'monotonic', return_value=0)
        self.clock.start(); self.addCleanup(self.clock.stop)
        self.behavior = {}
        def phase(*args):
            self.calls.append(args)
            name = args[2].removeprefix('pc1_reference_')
            value = self.behavior.get(name)
            if isinstance(value, BaseException):
                raise value
            raw = {'compile': '{}', 'micro': json.dumps({'status': 'PASS_NATIVE_MICRO', 'full_arrays_read': False, 'official_raw_numeric_pass': None}), 'full_models': json.dumps({'status': 'COMPLETE_TWO_MODEL_DIAGNOSTIC', 'elements': 196608})}[name]
            return value or ({'exit_code': 0, 'cleanup_confirmed': True}, raw, {'maxrss_kib_cumulative_parent_children': 12000})
        self.supervisor = types.SimpleNamespace(run_phase=phase)
    def go(self, stop=210):
        return R.supervised_sequence(self.supervisor, 'support', 'base', {'programs': {'g++': '/fixed/g++'}}, Path('/model'), Path('/search'), Path('/work'), {'PATH': '/search'}, stop, self.owner, self.before, self.binary, self.stages, self.result)
    def bad(self, phase, field, value):
        record = {'exit_code': 0, 'cleanup_confirmed': True}
        usage = {'maxrss_kib_cumulative_parent_children': 12000}
        if field in record: record[field] = value
        else: usage[field] = value
        self.behavior[phase] = (record, '{}', usage)
    def test_three_phases_same_owner_deadline(self):
        self.assertEqual(self.go(), {'identity': 'fixed'})
        self.assertEqual([a[2] for a in self.calls], ['pc1_reference_compile','pc1_reference_micro','pc1_reference_full_models'])
        for a in self.calls:
            self.assertEqual(a[8], 210); self.assertIs(a[9], self.owner)
        self.assertEqual(self.before.call_count, 6)
        self.assertEqual(self.binary.call_count, 5)
        self.assertTrue(self.result['full_models_executed'])
    def test_phase_limits(self):
        self.go()
        self.assertEqual([(a[7]['total_seconds'], a[7]['work_seconds'], a[7]['cpu_seconds']) for a in self.calls], [(45,30,30),(20,5,3),(120,105,100)])
        for a in self.calls:
            self.assertEqual(a[7]['as_bytes'],512*1024**2); self.assertEqual(a[7]['log_bytes'],65536)
    def test_fixed_argv(self):
        self.go(); argv=self.calls[0][3]
        self.assertEqual(argv[:3], ['/fixed/g++','-B','/search/'])
        self.assertEqual(tuple(argv[3:11]), R.FLAGS)
        self.assertEqual(self.calls[1][3], ['/model/pc1_reference','--micro'])
        self.assertEqual(self.calls[2][3], ['/model/pc1_reference','--full','/model/inputs','/model/outputs'])
    def test_compile_failure_stops(self):
        first=RuntimeError('first'); self.behavior['compile']=first
        with self.assertRaises(RuntimeError) as c: self.go()
        self.assertIs(c.exception,first); self.assertEqual(len(self.calls),1); self.assertEqual(len(self.stages),1)
        self.assertFalse(self.result['full_models_executed'])
    def test_micro_failure_stops(self):
        self.behavior['micro']=RuntimeError('micro')
        with self.assertRaises(RuntimeError): self.go()
        self.assertEqual(len(self.calls),2); self.assertFalse(self.result['full_models_executed'])
    def test_full_failure_extent_unknown(self):
        self.behavior['full_models']=RuntimeError('full')
        with self.assertRaises(RuntimeError): self.go()
        self.assertIsNone(self.result['full_models_executed']); self.assertEqual(len(self.stages),3)
    def test_exit_nonzero(self):
        self.bad('compile','exit_code',7)
        with self.assertRaisesRegex(ValueError,'PHASE_EXIT_OR_CLEANUP'): self.go()
        self.assertEqual(len(self.calls),1); self.assertEqual(self.stages[0]['record']['exit_code'],7)
    def test_exit_boolean_rejected(self):
        self.bad('compile','exit_code',False)
        with self.assertRaises(ValueError): self.go()
    def test_cleanup_false(self):
        self.bad('compile','cleanup_confirmed',False)
        with self.assertRaises(ValueError): self.go()
    def test_rss_gate(self):
        self.bad('compile','maxrss_kib_cumulative_parent_children',393217)
        with self.assertRaisesRegex(ValueError,'RSS_GATE'): self.go()
    def test_rss_boolean_rejected(self):
        self.bad('compile','maxrss_kib_cumulative_parent_children',True)
        with self.assertRaises(ValueError): self.go()
    def test_binary_change(self):
        self.binary.side_effect=[{'identity':'fixed'}, {'identity':'changed'}]
        with self.assertRaisesRegex(ValueError,'BINARY_CHANGED'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_preflight_before_child(self):
        self.before.side_effect=ValueError('preflight')
        with self.assertRaises(ValueError): self.go()
        self.assertEqual(self.calls,[])
    def test_postflight_stops_later_child(self):
        self.before.side_effect=[None,ValueError('postflight')]
        with self.assertRaises(ValueError): self.go()
        self.assertEqual(len(self.calls),1)
    def test_compile_window_preserves_tail(self):
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_PHASE_WINDOW'): self.go(69)
        self.assertEqual(self.calls,[])
    def test_full_window_preserves_tail(self):
        R.time.monotonic.side_effect=[0,0,45,45,66]
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_PHASE_WINDOW'): self.go()
        self.assertEqual(len(self.calls),2)
    def test_front_drift_rechecked_before_dispatch(self):
        R.time.monotonic.side_effect=[0,180]
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_PHASE_WINDOW'): self.go()
        self.assertEqual(self.calls,[])
    def test_final_binary_drift_rejected(self):
        self.binary.side_effect=[{'identity':'fixed'}]*4+[{'identity':'changed'}]
        with self.assertRaisesRegex(ValueError,'BINARY_CHANGED_POSTFLIGHT'): self.go()
        self.assertEqual(len(self.calls),3)
    def test_exact_full_window_boundary(self):
        R.time.monotonic.side_effect=[0,0,45,45,65,65]
        self.go(); self.assertEqual(len(self.calls),3)
    def test_invalid_micro_json(self):
        self.behavior['micro']=({'exit_code':0,'cleanup_confirmed':True},'{}',{'maxrss_kib_cumulative_parent_children':1})
        with self.assertRaisesRegex(ValueError,'NATIVE_MICRO_RESULT'): self.go()
        self.assertEqual(len(self.calls),2)
    def test_full_bad_stdout_no_complete_receipt(self):
        self.behavior['full_models']=({'exit_code':0,'cleanup_confirmed':True},'{}',{'maxrss_kib_cumulative_parent_children':1})
        with self.assertRaisesRegex(ValueError,'FULL_MODEL_RESULT'): self.go()
        self.assertTrue(self.result['full_models_executed'])
        self.assertNotIn('status', self.result)

class FailureAndLoader(unittest.TestCase):
    def test_first_failure_preserved_when_receipt_fails(self):
        first=ValueError('native'); second=OSError('receipt')
        with mock.patch.object(R,'write_result',side_effect=second):
            self.assertIs(R.save_preserving_failure(Path('/fake'),{},first),first)
    def test_receipt_failure_if_no_first(self):
        second=OSError('receipt')
        with mock.patch.object(R,'write_result',side_effect=second):
            self.assertIs(R.save_preserving_failure(Path('/fake'),{},None),second)
    def test_timer_restore_cannot_mask_first(self):
        first=ValueError('first'); second=OSError('timer')
        with mock.patch.object(R.signal,'setitimer',side_effect=second), mock.patch.object(R.signal,'signal') as sig:
            self.assertIs(R.restore_preserving_failure('old',first),first)
            sig.assert_called_once_with(signal.SIGALRM,'old')
    def test_handler_restore_cannot_mask_first(self):
        first=ValueError('first')
        with mock.patch.object(R.signal,'setitimer'), mock.patch.object(R.signal,'signal',side_effect=OSError('handler')):
            self.assertIs(R.restore_preserving_failure('old',first),first)
    def test_restore_failure_if_no_first(self):
        first=OSError('timer')
        with mock.patch.object(R.signal,'setitimer',side_effect=first), mock.patch.object(R.signal,'signal',side_effect=OSError('handler')):
            self.assertIs(R.restore_preserving_failure('old',None),first)
    def test_no_work_no_receipt(self):
        with mock.patch.object(R,'write_result') as w:
            self.assertIsNone(R.save_preserving_failure(None,{},None)); w.assert_not_called()
    def test_receipt_exclusive_and_finite(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'receipt.json'; R.write_result(p,{'status':'INCOMPLETE'})
            self.assertEqual(json.loads(p.read_bytes()),{'status':'INCOMPLETE'})
            with self.assertRaises(ValueError): R.write_result(p,{})
            with self.assertRaises(ValueError): R.write_result(Path(t)/'nan',{'bad':float('nan')})
    def test_module_samebuffer_and_tamper(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x.py'; raw=b'value = 37\n'; p.write_bytes(raw)
            pin=(len(raw),hashlib.sha256(raw).hexdigest())
            self.assertEqual(R.module(p,pin,'cold').value,37)
            p.write_bytes(b'value = 38\n')
            with self.assertRaisesRegex(ValueError,'SOURCE_HASH'): R.module(p,pin,'bad')
    def test_loader_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x'; p.write_bytes(b''); q=Path(t)/'link'; q.symlink_to(p)
            with self.assertRaises(ValueError): R.read(q,(0,hashlib.sha256(b'').hexdigest()))
    def test_explicit_execute_required(self):
        with self.assertRaisesRegex(ValueError,'REQUIRE_EXPLICIT'): R.run(Path('/unused'),False)
    def test_existing_timer_rejected(self):
        with mock.patch.object(R.signal,'getitimer',return_value=(1.0,0.0)):
            with self.assertRaisesRegex(ValueError,'TIMER_OWNERSHIP'): R.run(Path('/unused'),True)
    def test_parent_hard_limit_reject_and_firsterror(self):
        with mock.patch.object(R.signal,'getitimer',return_value=(0.0,0.0)), mock.patch.object(R.signal,'pthread_sigmask',return_value=set()), mock.patch.object(R.signal,'getsignal',return_value='old'), mock.patch.object(R.signal,'signal') as sig, mock.patch.object(R.signal,'setitimer') as timer, mock.patch.object(R.resource,'getrlimit',return_value=(1,1)), mock.patch.object(R.resource,'setrlimit') as setlimit:
            with self.assertRaisesRegex(ValueError,'INHERITED_HARD_LIMIT'): R.run(Path('/unused'),True)
            setlimit.assert_not_called(); self.assertEqual(timer.call_args.args,(signal.ITIMER_REAL,0)); self.assertEqual(sig.call_args.args,(signal.SIGALRM,'old'))

class DependencyContract(unittest.TestCase):
    def setUp(self):
        self.rows={f'/usr/fake/{i}':{'bytes':1,'sha256':'a'*64,'mode':'0755','kind':'dynamic_elf','elf':{'needed':[]}} for i in range(10)}
        self.catalog={'schema':'PC1_FIXED_COMPILER_DEPENDENCIES_V1','files':self.rows,'resolutions':{},'libraries':{'libc.so.6':'/usr/fake/9'},'programs':dict(zip(('g++','cc1plus','collect2','as','ld'),list(self.rows)[:5]))}
        self.evidence={'euid':1000,'egid':1000,'groups':[],'uid_map':'1000 0 1','gid_map':'1000 0 1','observed':{p:{'covering_mount':{'options':['ro','nosuid','nodev']},'chain':{'parent':{'mode':'0755','writable_by_current_process':False}}} for p in self.rows}}
        self.g=types.SimpleNamespace(need=R.need,MIB=1024**2,checked=lambda *a,**k:b'elf')
        self.observer=types.SimpleNamespace(userns_evidence=lambda *a:self.evidence)
        self.mount=types.SimpleNamespace(descriptor_snapshot=lambda *a:{'stable':True})
        self.reader=mock.patch.object(D,'elf_reader',return_value=(lambda raw:{'needed':[]},{'inverse_exact':True})); self.reader.start(); self.addCleanup(self.reader.stop)
        self.resolve=mock.patch.object(Path,'resolve',lambda p,strict=False:p); self.resolve.start(); self.addCleanup(self.resolve.stop)
    def go(self): return D.verify(self.g,self.observer,self.mount,Path('/repo'),self.catalog)
    def test_finite_catalog_pass(self): self.assertEqual(len(self.go()['files']),10)
    def test_namespace_rejected(self):
        self.evidence['euid']=0
        with self.assertRaises(ValueError): self.go()
    def test_readwrite_mount_rejected(self):
        self.evidence['observed']['/usr/fake/0']['covering_mount']['options']=['rw','nosuid','nodev']
        with self.assertRaises(ValueError): self.go()
    def test_writable_parent_rejected(self):
        self.evidence['observed']['/usr/fake/0']['chain']['parent']['mode']='0775'
        with self.assertRaises(ValueError): self.go()
    def test_needed_closure_rejected(self):
        D.elf_reader.return_value=(lambda raw:{'needed':['unknown.so']},{})
        self.rows['/usr/fake/0']['elf']={'needed':['unknown.so']}
        with self.assertRaises(ValueError): self.go()
    def test_unknown_library_rejected(self):
        self.catalog['libraries']={'unrecognized.so':'/usr/fake/9'}
        with self.assertRaises(ValueError): self.go()
    def test_resolution_drift_rejected(self):
        self.catalog['resolutions']={'/usr/fake/link':'/usr/fake/0'}
        with self.assertRaises(ValueError): self.go()
    def test_five_programs_required(self):
        del self.catalog['programs']['ld']
        with self.assertRaises(ValueError): self.go()
    def test_hash_gate_failure_propagates(self):
        self.mount.descriptor_snapshot=mock.Mock(side_effect=ValueError('bytes changed'))
        with self.assertRaisesRegex(ValueError,'bytes changed'): self.go()

class Projection(unittest.TestCase):
    def fixture(self):
        raw = b'def elf_dependencies(raw):\n    require(len(raw)<=32*MIB, "size")\n    stringsz = 1\n    require(0<stringsz<=MIB, "string")\n    return {"needed": [], "interpreter": INTERPRETER}\n'
        pin = lambda data: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        g = types.SimpleNamespace(need=R.need, ELF_SOURCE='fixed.py', SOURCE_FILES={'fixed.py': pin(raw)}, checked=lambda *a:raw, pin=pin)
        return g, raw
    def test_exact_two_bound_projection(self):
        g,raw=self.fixture(); reader,proof=D.elf_reader(g,Path('/source'))
        self.assertEqual(reader(b''), {'needed':[], 'interpreter':'/lib64/ld-linux-x86-64.so.2'})
        self.assertTrue(proof['inverse_exact']); self.assertEqual(proof['cap_only_substitutions'],2)
        self.assertEqual(proof['original'],g.pin(raw+b'\n'))
    def test_projection_missing_anchor_fail_closed(self):
        g,raw=self.fixture(); g.checked=lambda *a:raw.replace(b'32*MIB',b'31*MIB')
        with self.assertRaises(ValueError): D.elf_reader(g,Path('/source'))
    def test_projection_duplicate_function_fail_closed(self):
        g,raw=self.fixture(); g.checked=lambda *a:raw+raw
        with self.assertRaises(ValueError): D.elf_reader(g,Path('/source'))
    def test_binary_pie_and_closed_dependencies(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'binary'; data=bytearray(64); data[16]=3; p.write_bytes(data)
            g=types.SimpleNamespace(need=R.need,MIB=1024**2,pin=lambda raw:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},checked=lambda path,*a,**k:path.read_bytes())
            meta={'interpreter':'/lib64/ld-linux-x86-64.so.2','needed':['libc.so.6']}
            with mock.patch.object(D,'elf_reader',return_value=(lambda raw:meta,{})):
                self.assertEqual(D.check_binary(g,Path('/repo'),{'libraries':{'libc.so.6':'fixed'}},p)['elf'],meta)
                with self.assertRaises(ValueError): D.check_binary(g,Path('/repo'),{'libraries':{}},p)
                data[16]=2; p.write_bytes(data)
                with self.assertRaises(ValueError): D.check_binary(g,Path('/repo'),{'libraries':{}},p)

if __name__ == '__main__':
    unittest.main(verbosity=2)
