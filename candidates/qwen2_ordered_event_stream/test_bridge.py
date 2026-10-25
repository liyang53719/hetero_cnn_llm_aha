"""Control fixtures only: never imports the actual owner or runs arithmetic."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('_bridge_fixture', Path(__file__).with_name('bridge.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

class BridgeTests(unittest.TestCase):
    def fixture(self, capture_fail=False, service_fail=False, pending=False, driver_fail=False):
        events=[]
        class Capture:
            def __init__(self,*args): events.append('capture_construct')
            def __enter__(self): events.append('capture_enter'); return self
            def __exit__(self,*args): events.append('capture_exit')
            def seal(self):
                events.append('capture_seal')
                if capture_fail: raise ValueError('missing actual field')
                return {'status':'fixture_only'}
        class Trace(Capture):
            def __init__(self,*args):
                events.append('trace_construct');self.events=[('fixture_partial',0,())]
            def seal(self):
                events.append('trace_seal')
                if service_fail: raise ValueError('foreign ticket')
                return {'complete':True,'count':1}
            def raw_receipt(self):return {'complete':False,'count':1,'fixture':True}
        def bind(x,p,j,**kw):
            self.assertEqual(kw['ordered_fold'],True)
            events.append('bind'); return NS(check=lambda x:events.append('binding_check'))
        def execute(x,p,j,**kw):
            self.assertEqual(kw,dict(final_ack_stall=5,enable_raw_kv=False))
            events.append('driver_terminal')
            if driver_fail: raise ValueError('fixture driver failed')
            return {'original_driver':True}
        def bindings(*args):
            self.assertIn('bind',events); return NS()
        observer=NS(load_observer=lambda p:(NS(Observation=Capture,bind=None),NS(PackedFields=None)),
                    bindings=bindings,ServiceTrace=Trace)
        helper=NS(load_exact=lambda p:None,lanes=lambda w,e:None)
        modules={}
        for name in ('candidates','candidates.qwen2_resident_matrix','candidates.qwen2_resident_matrix.production_qk16_model'):
            modules[name]=ModuleType(name);modules[name].__path__=[]
        modules[list(modules)[-1]].direct_transport=NS(bind=bind,execute_attention_owner=execute)
        modules[list(modules)[-1]].ordered_work=NS()
        b.make_service_trace=lambda o,service,profile,bind,path: Trace(service,profile,bind)
        b.make_observation=lambda *a:Capture(*a)
        profile=dict(qk_profile=2,pv_profile=0,raw_kv_transport=False,exact_helper='fixture',event_stream_max_bytes=1000000,event_stream_max_events=1000)
        with patch.dict(sys.modules,modules),patch.object(b,'load_observer_runtime',return_value=(helper,observer)):
            dispatch,state=b.make_dispatch(profile,enabled=True,event_stream_path='/fixture/events.q2evt')
        x=NS(attention_owner=NS(),matrix_service=NS(owner=None))
        physical=NS(pending=object() if pending else None)
        return dispatch,state,x,physical,NS(tag=12,kind='Attention',m=16),events

    def test_default_off_has_no_import(self):
        with patch.object(b,'load_observer_runtime',side_effect=AssertionError('import')):
            dispatch,state=b.make_dispatch({})
        self.assertIsNone(dispatch);self.assertEqual(state['invocations'],0)
    def test_nonbool_enable_rejected(self):
        with self.assertRaises(ValueError): b.make_dispatch({},enabled=1)
    def test_pv2_rejected_before_import(self):
        with self.assertRaises(ValueError):
            b.make_dispatch(dict(qk_profile=2,pv_profile=2,raw_kv_transport=False),enabled=True)
    def test_rawkv_rejected_before_import(self):
        with self.assertRaises(ValueError):
            b.make_dispatch(dict(qk_profile=2,pv_profile=0,raw_kv_transport=True),enabled=True)
    def test_monitor_enter_and_exit_failures_do_not_replace_driver(self):
        for stage in ('enter','exit'):
            events=[]
            class Context:
                def __enter__(self):
                    events.append('enter')
                    if stage=='enter':raise OSError('monitor busy')
                    return self
                def __exit__(self,*args):
                    events.append('exit')
                    if stage=='exit':raise OSError('cleanup failed')
            state={'service_error':None,'capture_error':None}
            def driver():events.append('driver_final_ack');return {'original':True}
            self.assertEqual(b.observe_driver(Context(),Context(),driver,state),{'original':True})
            self.assertIn('driver_final_ack',events)
            self.assertTrue(state['service_error']);self.assertTrue(state['capture_error'])
    def test_driver_exception_not_swallowed_or_replaced_by_cleanup(self):
        class Context:
            def __enter__(self):return self
            def __exit__(self,*args):raise OSError('cleanup failed')
        state={'service_error':None,'capture_error':None}
        original=RuntimeError('original driver fault')
        def driver():raise original
        try:b.observe_driver(Context(),Context(),driver,state)
        except RuntimeError as error:self.assertIs(error,original)
        else:self.fail('driver error swallowed')
        self.assertTrue(state['service_error']);self.assertTrue(state['capture_error'])
    def test_context_return_true_cannot_suppress_driver_exception(self):
        class Context:
            def __enter__(self):return self
            def __exit__(self,*args):return True
        state={'service_error':None,'capture_error':None}
        def driver():raise RuntimeError('original')
        with self.assertRaisesRegex(RuntimeError,'original'):b.observe_driver(Context(),Context(),driver,state)

    def test_missing_storage_admission_rejected_before_import(self):
        with patch.object(b,'load_observer_runtime',side_effect=AssertionError('import')):
            with self.assertRaisesRegex(ValueError,'admitted'):
                b.make_dispatch(dict(qk_profile=2,pv_profile=0,raw_kv_transport=False),enabled=True)
    def test_real_driver_result_preserved_and_seal_after_terminal(self):
        d,s,x,p,j,e=self.fixture();self.assertEqual(d(x,p,j),{'original_driver':True})
        self.assertLess(e.index('bind'),e.index('capture_construct'))
        self.assertLess(e.index('driver_terminal'),e.index('binding_check'))
        self.assertLess(e.index('binding_check'),e.index('capture_seal'))
    def test_driver_failure_keeps_partial_raw_not_sealed(self):
        d,s,x,p,j,e=self.fixture(driver_fail=True)
        with self.assertRaises(ValueError):d(x,p,j)
        self.assertEqual(s['service_events_raw'],{'complete':False,'count':1,'fixture':True})
        self.assertIsNone(s['service_events'])
        self.assertNotIn('capture_seal',e)
    def test_duplicate_dispatch_rejected(self):
        d,s,x,p,j,e=self.fixture();d(x,p,j)
        with self.assertRaises(ValueError):d(x,p,j)
        self.assertEqual(e.count('driver_terminal'),1)
    def test_wrong_pc_rejected(self):
        d,s,x,p,j,e=self.fixture();j.tag=13
        with self.assertRaises(ValueError):d(x,p,j)
        self.assertEqual(e,[])
    def test_pending_ack_rejects_seal(self):
        d,s,x,p,j,e=self.fixture(pending=True)
        with self.assertRaises(ValueError):d(x,p,j)
        self.assertNotIn('capture_seal',e)
    def test_capture_failure_does_not_change_driver_result(self):
        d,s,x,p,j,e=self.fixture(capture_fail=True)
        self.assertEqual(d(x,p,j),{'original_driver':True})
        self.assertIsNone(s['capture_report']);self.assertIn('missing actual field',s['capture_error'])
    def test_service_failure_is_recorded_not_hidden(self):
        d,s,x,p,j,e=self.fixture(service_fail=True);d(x,p,j)
        self.assertIsNone(s['service_events']);self.assertIn('foreign ticket',s['service_error'])

if __name__=='__main__':unittest.main()
