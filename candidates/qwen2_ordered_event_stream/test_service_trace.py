"""Pure source-binding fixtures and readonly AST evidence; no DUT/native import."""
import ast
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest

from unittest.mock import patch
HERE = Path(__file__).resolve().parent
PACKAGE='_stream_service_fixture'
pkg=types.ModuleType(PACKAGE);pkg.__path__=[str(HERE)];sys.modules[PACKAGE]=pkg
spec=importlib.util.spec_from_file_location(PACKAGE+'.service_trace',HERE/'service_trace.py')
subject=importlib.util.module_from_spec(spec);sys.modules[spec.name]=subject;spec.loader.exec_module(subject)
spec=importlib.util.spec_from_file_location('_raw_event_fixture',HERE/'test_stream.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

class Monitor:
    events=types.SimpleNamespace(LINE=1,PY_RETURN=2)
    def __init__(self):self.slots={};self.callbacks={};self.locals={};self.globals={};self.calls=[];self.fail=None
    def get_tool(self,slot):return self.slots.get(slot)
    def get_events(self,slot):return self.globals.get(slot,0)
    def get_local_events(self,slot,code):return self.locals.get((slot,code),0)
    def use_tool_id(self,slot,name):
        if self.get_tool(slot) is not None:raise ValueError('busy')
        self.slots[slot]=name;self.calls.append(('reserve',slot))
    def set_local_events(self,*args):
        self.calls.append(('local',)+args)
        if self.fail=='local':raise OSError('local cleanup failure')
        self.locals[(args[0],args[1])]=args[2]
    def register_callback(self,*args):
        self.calls.append(('callback',)+args)
        if self.fail=='register':raise OSError('registration failure')
        key=(args[0],args[1]);previous=self.callbacks.get(key);self.callbacks[key]=args[2];return previous
    def free_tool_id(self,slot):self.calls.append(('free',slot));del self.slots[slot]


class BindingFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.profile={'source_root':str(self.root),'files':{},'rows':1,'event_stream_max_bytes':1000000,'event_stream_max_events':1000}
        self.traces=[]
        self.monitor=Monitor()
        self.monitor_patch=patch.object(sys,'monitoring',self.monitor);self.monitor_patch.start()
        self.saved={};self.modules=[]
        methods='\n'.join('    def '+name+'(self, *args): return True' for name in subject.METHODS if name!='acquire')
        sources=[
            ('ffn_attention.matrix_service','MatrixService',
             'class MatrixService:\n    def __init__(self): raise RuntimeError("no service construction")\n    def acquire(self, owner, mode, tag): return True\n'+methods+'\n'),
            ('official_bf16.dense_silu','OfficialMatrixService',
             'class OfficialMatrixService(MatrixService):\n    def acquire(self, owner, mode, tag):\n        return super().acquire(owner, mode, tag)\n'),
            ('dense_block_reduce.matrix_binding','ProfiledMatrixService',
             'class ProfiledMatrixService(OfficialMatrixService):\n    pass\n')]
        previous={}
        for name,cls,source in sources:
            path=self.root/'candidates/qwen2_resident_matrix'/(name.replace('.','/')+'.py')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source)
            fullname=subject.ROOT_MODULE+name
            self.saved[fullname]=sys.modules.get(fullname)
            module=types.ModuleType(fullname);module.__file__=str(path);vars(module).update(previous)
            exec(compile(source,str(path),'exec'),vars(module));sys.modules[fullname]=module
            self.profile['files'][str(path)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            previous[cls]=getattr(module,cls);self.modules.append(module)
        self.base,self.official,self.profiled=[getattr(m,c) for m,c in zip(self.modules,('MatrixService','OfficialMatrixService','ProfiledMatrixService'))]
        self.service=object.__new__(self.profiled)
        class Trace:
            METHODS=subject.METHODS
            def __enter__(self):return self
            def __exit__(self,*args):self.closed=True
            def _return(self,*args):return 'unchanged callback'
            def stop(self):self.closed=True
            def seal(self):return tuple(self.events)
        self.runtime=types.SimpleNamespace(ServiceTrace=Trace)
        self.bind_calls=[]
        def bind(method,path,pin,cls,name,ast_test):
            self.assertFalse(ast_test)
            self.assertEqual(method.__code__.co_filename,str(path))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),pin)
            self.bind_calls.append((cls,name))
            return method.__code__
        self.bind=bind

    def tearDown(self):
        for trace in self.traces:trace.stop();trace.events.close_incomplete()
        self.monitor_patch.stop()
        for name,old in self.saved.items():
            if old is None:sys.modules.pop(name,None)
            else:sys.modules[name]=old
        self.temp.cleanup()

    def test_attention_callbacks_remain_direct_with_safe_cleanup(self):
        from importlib import import_module
        bridge=import_module(PACKAGE+'.bridge')
        class Original:
            def __init__(self,owner,*args):
                self.owner=owner;self.error=None;self.tool=None;self.closed=False;self.codes={'x':object()}
            def _line(self,*args):pass
            def _return(self,*args):pass
            def __exit__(self,*args):self.stop();return False
            def fail(self,error):
                if self.error is None:self.error=str(error)
                self.stop()
        owner=types.SimpleNamespace(state='idle',poison=False)
        capture=bridge.make_observation(types.SimpleNamespace(Observation=Original),owner,1,None,{})
        self.assertIs(type(capture)._line,Original._line);self.assertIs(type(capture)._return,Original._return)
        capture.__enter__();self.monitor.fail='local';capture.fail(OSError('original capture error'))
        self.assertEqual(capture.error,'original capture error');self.assertIsNotNone(capture.tool)
    def test_busy_capture_falls_back_without_touching_foreign_slots(self):
        from importlib import import_module
        bridge=import_module(PACKAGE+'.bridge')
        class Original:
            def __init__(self,owner,*args):
                self.owner=owner;self.error=None;self.tool=None;self.closed=False;self.codes={}
            def _line(self,*args):pass
            def _return(self,*args):pass
            def __exit__(self,*args):self.stop();return False
        self.monitor.slots={3:'foreign-a',4:'foreign-b'}
        capture=bridge.make_observation(types.SimpleNamespace(Observation=Original),types.SimpleNamespace(state='idle',poison=False),1,None,{})
        state={'service_error':None,'capture_error':None};driver=[]
        trace=self.make()
        result=bridge.observe_driver(trace,capture,lambda:driver.append('original_final_ack') or 17,state)
        self.assertEqual(result,17);self.assertEqual(driver,['original_final_ack'])
        self.assertTrue(state['service_error']);self.assertTrue(state['capture_error'])
        self.assertEqual(self.monitor.slots,{3:'foreign-a',4:'foreign-b'});self.assertEqual(self.monitor.calls,[])

    def test_dormant_foreign_callback_is_restored(self):
        foreign=lambda *args:None
        self.monitor.callbacks[(4,self.monitor.events.PY_RETURN)]=foreign
        trace=self.make()
        with self.assertRaisesRegex(ValueError,'stale'):trace.__enter__()
        self.assertIs(self.monitor.callbacks[(4,self.monitor.events.PY_RETURN)],foreign)
        self.assertEqual(self.monitor.slots,{})
        self.assertTrue(trace.error)
    def test_same_lease_foreign_callback_replacement_is_restored(self):
        trace=self.make();trace.__enter__();slot=trace.tool;foreign=lambda *args:None
        self.monitor.callbacks[(slot,self.monitor.events.PY_RETURN)]=foreign
        local=dict(self.monitor.locals);trace.stop()
        self.assertIs(self.monitor.callbacks[(slot,self.monitor.events.PY_RETURN)],foreign)
        self.assertEqual(self.monitor.locals,local);self.assertIsNotNone(trace.tool)
        self.assertIn('foreign monitor callback',trace.error)
    def test_foreign_local_masks_block_install(self):
        trace=self.make()
        for slot in (3,4):self.monitor.locals[(slot,next(iter(trace.codes)))]=16
        local=dict(self.monitor.locals)
        with self.assertRaisesRegex(ValueError,'retains'):trace.__enter__()
        self.assertEqual(self.monitor.locals,local);self.assertEqual(self.monitor.calls,[])
    def test_foreign_global_mask_at_cleanup_is_preserved(self):
        trace=self.make();trace.__enter__();slot=trace.tool;self.monitor.globals[slot]=16
        callbacks=dict(self.monitor.callbacks);locals_=dict(self.monitor.locals);trace.stop()
        self.assertEqual(self.monitor.globals[slot],16)
        self.assertEqual(self.monitor.callbacks,callbacks);self.assertEqual(self.monitor.locals,locals_)
        self.assertIsNotNone(trace.tool);self.assertTrue(trace.error)

    def test_specs_without_service_construction(self):
        specs=subject.service_specs(self.profiled,self.profile)
        self.assertEqual(len(specs),9)
        self.assertIs(specs['acquire'][0],self.official.acquire)
        self.assertEqual(specs['acquire'][3],'OfficialMatrixService')
        for name in subject.METHODS[1:]:
            self.assertIs(specs[name][0],getattr(self.base,name))
            self.assertEqual(specs[name][3],'MatrixService')

    def make(self, bind=None):
        trace=subject.make_trace(self.runtime,self.service,self.profile,bind or self.bind,self.root/('events%d.bin'%len(self.traces)))
        self.traces.append(trace)
        return trace
    def test_factory_reuses_frame_sensitive_callback_exactly(self):
        trace=self.make()
        self.assertIs(type(trace)._return,self.runtime.ServiceTrace._return)
        self.assertIs(trace.service,self.service)
        with self.assertRaises(TypeError):tuple(trace.events)
        self.assertEqual(self.bind_calls,[('OfficialMatrixService','acquire')]+[('MatrixService',n) for n in subject.METHODS[1:]])
    def test_stream_seal_and_two_receipts_share_only_metadata(self):
        trace=self.make()
        with trace:
            for event in fixture.fixture():trace.events.append(event)
        sealed=trace.seal();raw=trace.raw_receipt()
        self.assertTrue(sealed['complete']);self.assertTrue(all(raw[k]==v for k,v in sealed.items()))
        self.assertIsNone(raw['monitor_residual_tool'])
        self.assertNotIn('events',sealed);self.assertEqual(self.monitor.slots,{})
    def test_foreign_slots_preserved_and_no_cleanup_attempt(self):
        self.monitor.slots={3:'foreign-a',4:'foreign-b'}
        trace=self.make()
        with self.assertRaisesRegex(ValueError,'busy'):trace.__enter__()
        self.assertEqual(self.monitor.slots,{3:'foreign-a',4:'foreign-b'})
        self.assertEqual(self.monitor.calls,[])
        with self.assertRaises(ValueError):trace.seal()
    def test_partial_registration_failure_releases_only_own_slot(self):
        self.monitor.slots={3:'foreign'};self.monitor.fail='register'
        trace=self.make()
        with self.assertRaisesRegex(OSError,'registration'):trace.__enter__()
        self.assertEqual(self.monitor.slots[3],'foreign')
        self.assertTrue(trace.error) # uncertain cleanup leaves our residual lease, never foreign

    def test_cleanup_failure_is_sticky_and_nothrow(self):
        trace=self.make();trace.__enter__();self.monitor.fail='local'
        trace.stop();self.assertTrue(trace.error);self.assertIsNotNone(trace.tool)
        calls=len(self.monitor.calls);trace.stop();self.assertEqual(len(self.monitor.calls),calls)
    def test_foreign_replacement_is_never_cleared(self):
        trace=self.make();trace.__enter__();slot=trace.tool
        self.monitor.slots[slot]='foreign-replacement'
        calls=len(self.monitor.calls);trace.stop()
        self.assertEqual(self.monitor.slots[slot],'foreign-replacement')
        self.assertEqual(len(self.monitor.calls),calls);self.assertIn('foreign',trace.error)
    def test_raw_audit_failure_does_not_stop_monitor_or_drop_release(self):
        trace=self.make();events=list(fixture.fixture());events.insert(2,('abort',2,()))
        with trace:
            for event in events:trace.events.append(event)
            self.assertIsNone(trace.error);self.assertFalse(trace.closed)
        receipt=trace.raw_receipt();self.assertTrue(receipt['raw_complete']);self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['count'],len(events))
        with self.assertRaises(ValueError):trace.seal()
    def test_initial_io_failure_does_not_stop_driver_before_callbacks(self):
        self.root.joinpath('events0.bin').write_bytes(b'existing')
        trace=self.make();entered=False
        with trace:
            entered=True
        self.assertTrue(entered);self.assertTrue(trace.error)
        self.assertFalse(trace.raw_receipt()['created'])

    def test_acquire_wrapper_only_no_double_count(self):
        trace=self.make()
        self.assertIn(self.official.acquire.__code__,trace.codes)
        self.assertNotIn(self.base.acquire.__code__,trace.codes)
        self.assertEqual(list(trace.codes.values()).count('acquire'),1)

    def test_normal_wrapper_return_frame_locals_available(self):
        code=self.official.acquire.__code__
        self.assertEqual(code.co_varnames[:4],('self','owner','mode','tag'))
        self.assertTrue(self.service.acquire(object(),'normal',12))

    def test_wrong_service_type(self):
        with self.assertRaisesRegex(ValueError,'MRO'):subject.service_specs(self.official,self.profile)

    def test_subclass_rejected(self):
        class Foreign(self.profiled):pass
        with self.assertRaisesRegex(ValueError,'MRO'):subject.service_specs(Foreign,self.profile)

    def test_source_byte_change_rejected(self):
        path=Path(self.modules[1].__file__);path.write_text(path.read_text()+'# change\n')
        with self.assertRaisesRegex(ValueError,'source pin'):subject.service_specs(self.profiled,self.profile)

    def test_module_origin_replaced_rejected(self):
        self.modules[0].__file__=str(self.root/'other.py')
        with self.assertRaisesRegex(ValueError,'origin'):subject.service_specs(self.profiled,self.profile)

    def test_module_class_replaced_rejected(self):
        self.modules[2].ProfiledMatrixService=type('Foreign',(),{})
        with self.assertRaisesRegex(ValueError,'class identity'):subject.service_specs(self.profiled,self.profile)

    def test_class_override_rejected(self):
        self.profiled.acquire=lambda *a:True
        with self.assertRaisesRegex(ValueError,'override'):subject.service_specs(self.profiled,self.profile)

    def test_instance_override_rejected(self):
        self.service.acquire=types.MethodType(self.base.acquire,self.service)
        with self.assertRaisesRegex(ValueError,'substitution'):self.make()

    def test_other_lifecycle_override_rejected(self):
        self.official.abort=lambda *a:None
        with self.assertRaisesRegex(ValueError,'override'):subject.service_specs(self.profiled,self.profile)

    def test_duplicate_code_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.make(lambda *a:self.base.acquire.__code__)

    def test_binding_failure_not_swallowed(self):
        def reject(*args):raise ValueError('strict binder rejected')
        with self.assertRaisesRegex(ValueError,'strict binder rejected'):
            self.make(reject)

    def test_trace_contract_change_rejected(self):
        self.runtime.ServiceTrace.METHODS=()
        with self.assertRaisesRegex(ValueError,'contract'):self.make()


if __name__=='__main__':unittest.main()
