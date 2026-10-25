"""R2 cancellation/monitor-failure delta tests, stdlib control fixtures only."""
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
fixture=load('_r2_bridge_control','test_bridge.py');bridge=fixture.b
raw_fixture=load('_r2_raw_control','test_stream.py');stream=raw_fixture.stream

class Context:
    def __init__(self,enter=None,leave=None):self.enter_error=enter;self.leave_error=leave;self.closed=False
    def __enter__(self):
        if self.enter_error is not None:raise self.enter_error
        return self
    def __exit__(self,*args):
        self.closed=True
        if self.leave_error is not None:raise self.leave_error

class ResourceFaults(unittest.TestCase):
    def state(self):return {'service_error':None,'capture_error':None}
    def test_cleanup_systemexit_never_replaces_original_driver_error(self):
        for kind in (RuntimeError,SystemExit,KeyboardInterrupt):
            original=kind('original driver');state=self.state();a=Context(leave=SystemExit('monitor cleanup'));b=Context(leave=MemoryError('receipt cleanup'))
            def driver():raise original
            try:bridge.observe_driver(a,b,driver,state)
            except BaseException as actual:self.assertIs(actual,original)
            else:self.fail('original driver exception suppressed')
            self.assertTrue(a.closed and b.closed);self.assertTrue(state['service_error'] and state['capture_error'])
    def test_cleanup_keyboardinterrupt_preserves_existing_driver_error(self):
        original=RuntimeError('original');state=self.state()
        def driver():raise original
        try:bridge.observe_driver(Context(leave=KeyboardInterrupt()),Context(),driver,state)
        except BaseException as actual:self.assertIs(actual,original)
        else:self.fail('original lost')
    def test_cleanup_keyboardinterrupt_without_original_error_is_cancellation(self):
        cancel=KeyboardInterrupt('cancel');a=Context();b=Context(leave=cancel);state=self.state()
        try:bridge.observe_driver(a,b,lambda:17,state)
        except BaseException as actual:self.assertIs(actual,cancel)
        else:self.fail('cancellation swallowed')
        self.assertTrue(a.closed and b.closed)
    def test_monitor_systemexit_cleanup_preserves_successful_driver_return(self):
        state=self.state();self.assertEqual(bridge.observe_driver(Context(leave=SystemExit('monitor')),Context(),lambda:17,state),17)
        self.assertIn('SystemExit',state['service_error'])
    def test_monitor_systemexit_setup_falls_back(self):
        state=self.state();called=[]
        self.assertEqual(bridge.observe_driver(Context(enter=SystemExit('monitor')),Context(),lambda:called.append('driver_ack') or 17,state),17)
        self.assertEqual(called,['driver_ack']);self.assertIn('SystemExit',state['service_error'])
    def test_monitor_keyboardinterrupt_setup_cancels_and_closes_prior_context(self):
        cancel=KeyboardInterrupt('cancel');a=Context();state=self.state()
        try:bridge.observe_driver(a,Context(enter=cancel),lambda:self.fail('driver after cancel'),state)
        except BaseException as actual:self.assertIs(actual,cancel)
        else:self.fail('cancel swallowed')
        self.assertTrue(a.closed)
    def test_driver_systemexit_and_keyboardinterrupt_without_monitor_failure_propagate(self):
        for kind in (SystemExit,KeyboardInterrupt):
            original=kind('driver');state=self.state()
            def driver():raise original
            try:bridge.observe_driver(Context(),Context(),driver,state)
            except BaseException as actual:self.assertIs(actual,original)
            else:self.fail('driver BaseException swallowed')
    def test_raw_receipt_failure_preserves_driver_failure_and_success(self):
        for failed in (False,True):
            d,s,x,p,j,e=fixture.BridgeTests().fixture(driver_fail=failed)
            make=bridge.make_service_trace
            def broken(*args):
                trace=make(*args)
                def receipt():raise MemoryError('receipt snapshot failed')
                trace.raw_receipt=receipt;return trace
            with patch.object(bridge,'make_service_trace',new=broken):
                if failed:
                    with self.assertRaisesRegex(ValueError,'fixture driver failed'):d(x,p,j)
                else:self.assertEqual(d(x,p,j),{'original_driver':True})
            self.assertIn('MemoryError',s['service_events_raw_error']);self.assertIn('MemoryError',s['service_error'])
            self.assertIsNone(s['service_events'])
    def test_raw_receipt_keyboardinterrupt_keeps_original_driver_error(self):
        d,s,x,p,j,e=fixture.BridgeTests().fixture(driver_fail=True);make=bridge.make_service_trace
        def broken(*args):
            trace=make(*args)
            def receipt():raise KeyboardInterrupt('receipt cancel')
            trace.raw_receipt=receipt;return trace
        with patch.object(bridge,'make_service_trace',new=broken):
            with self.assertRaisesRegex(ValueError,'fixture driver failed'):d(x,p,j)
    def test_raw_receipt_keyboardinterrupt_without_driver_error_propagates(self):
        d,s,x,p,j,e=fixture.BridgeTests().fixture();make=bridge.make_service_trace;cancel=KeyboardInterrupt('cancel')
        def broken(*args):
            trace=make(*args)
            def receipt():raise cancel
            trace.raw_receipt=receipt;return trace
        with patch.object(bridge,'make_service_trace',new=broken):
            try:d(x,p,j)
            except BaseException as actual:self.assertIs(actual,cancel)
            else:self.fail('cancellation lost')
    def test_monitor_stop_systemexit_sticky_not_service_exception(self):
        service_fixture=load('_r2_service_control','test_service_trace.py')
        case=service_fixture.BindingFixture();case.setUp()
        try:
            trace=case.make();trace.__enter__()
            with patch.object(case.monitor,'get_tool',side_effect=SystemExit('monitor cleanup')):trace.stop()
            self.assertIn('SystemExit',trace.error);self.assertTrue(trace.closed)
        finally:case.tearDown()
    def test_monitor_stop_keyboardinterrupt_is_explicit_cancellation(self):
        service_fixture=load('_r2_service_control_cancel','test_service_trace.py')
        case=service_fixture.BindingFixture();case.setUp();cancel=KeyboardInterrupt('cancel')
        try:
            trace=case.make();trace.__enter__()
            with patch.object(case.monitor,'get_tool',side_effect=cancel):
                try:trace.stop()
                except BaseException as actual:self.assertIs(actual,cancel)
                else:self.fail('cancellation swallowed')
        finally:case.tearDown()
    def test_storage_systemexit_converts_to_capturable_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            w=stream.EventWriter(Path(directory)/'events',**raw_fixture.limits());real=w.file
            class File:
                def write(self,data):raise SystemExit('storage hook fault')
                def close(self):real.close()
            w.file=File()
            try:
                with self.assertRaisesRegex(OSError,'capture storage failure'):w.append(next(raw_fixture.fixture()))
            finally:w.close_incomplete()
            self.assertIn('SystemExit',w.error);self.assertFalse(w.raw_complete)
    def test_storage_keyboardinterrupt_remains_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            w=stream.EventWriter(Path(directory)/'events',**raw_fixture.limits());real=w.file;cancel=KeyboardInterrupt('cancel')
            class File:
                def write(self,data):raise cancel
                def close(self):real.close()
            w.file=File()
            try:
                try:w.append(next(raw_fixture.fixture()))
                except BaseException as actual:self.assertIs(actual,cancel)
                else:self.fail('cancellation swallowed')
            finally:w.close_incomplete()

if __name__=='__main__':unittest.main()
