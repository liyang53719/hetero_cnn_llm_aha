"""Synthetic control-only orchestration. All DUT/registry/observer roles mocked.

Executing the newly prepared runner with these mocks is NOT M128/native/model
execution. No target package is imported; only synthetic bytes/control events.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType,SimpleNamespace as NS,MappingProxyType
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent;OVER=HERE/'overlay/candidates/qwen2_ordered_fullgraph_entry'
PACKAGE='_m128_draft_runner_control'
pkg=ModuleType(PACKAGE);pkg.__path__=[str(OVER)];sys.modules[PACKAGE]=pkg

def load(name,path):
    spec=importlib.util.spec_from_file_location(PACKAGE+'.'+name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module
runner=load('runner',OVER/'runner.py')
gate_module=load('oracle_path_gate',OVER/'oracle_path_gate.py')
actual_bridge_control=load('bridge_control_only',OVER/'bridge.py')
bridge=ModuleType(PACKAGE+'.bridge');sys.modules[bridge.__name__]=bridge
registry=ModuleType(PACKAGE+'.registry');sys.modules[registry.__name__]=registry
stream=ModuleType(PACKAGE+'.stream');stream.artifact_evidence=lambda *a,**k:{'mock':'raw stream receipt'};sys.modules[stream.__name__]=stream
rope_package=ModuleType(PACKAGE+'.rope_operand_capture');rope_package.__path__=[];sys.modules[rope_package.__name__]=rope_package
rope=ModuleType(rope_package.__name__+'.rope_capture');sys.modules[rope.__name__]=rope

class SyntheticRunnerSeam(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.out=self.root/'run';self.events=[]
        self.oracle=self.root/'sealed_oracle';self.oracle.mkdir();(self.oracle/'fake.txt').write_text('NOT AN ORACLE')
        self.guard=gate_module.ExactOraclePathGate([self.oracle],[self.oracle/'fake.txt'])
        with patch.object(gate_module.sys,'addaudithook'):self.guard.install({},'')
        self.xbytes=b'\0'*(128*1536*4);self.silubytes=b'SYNTHETIC-SILU-SEAL'
        self.ropebytes=MappingProxyType({'cos':b'SYNTHETIC-COS','sin':b'SYNTHETIC-SIN'})
        self.provider=lambda offset:self.xbytes[offset:offset+64]
        self.providers={'x':self.provider}
        self.physical=NS(regions={'x':dict(readonly=True,provider=self.provider,base=4096,extent=len(self.xbytes))},metadata_port=lambda:'metadata',raw=lambda a,n:self.xbytes)
        self.fixture=NS(config=NS(regions=[None,None,None,NS(base=0,limit=10000)]))
        self.execution=NS(prefix_owner=object());self.memory=object();self.actual={'mock':'actual'}
        self.token=NS(consumed=False);self.oldgate=NS(opened=False,library=lambda value:value)
        self.state=dict(invocations=0,capture=None,capture_report={},capture_error=None,service_error=None,service_events={'count':0})
        self.profile=dict(rows=128,profile_id='ordered_fullgraph_m128_terminal_capture_v1',epoch=1,wall_budget=1800,
            qk_profile=2,pv_profile=0,raw_kv_transport=False,event_stream_max_bytes=1,event_stream_max_events=1,input_spec={},input_views={'x':dict(shape=[128,1536],bytes=len(self.xbytes),sha256=hashlib.sha256(self.xbytes).hexdigest())})
        self.admission=dict(execution_authorized=True,**{k:'SYNTHETIC-NOT-ADMITTED' for k in ('source_manifest_sha256','profile_sha256','elf_sha256','runtime_manifest_sha256','input_manifest_sha256','run_id')})
        parent=self
        class Context:
            def __enter__(_):parent.events.append('oldgate_enter');return parent.oldgate
            def __exit__(_, *exc):parent.events.append('oldgate_exit')
        class Capture:
            def __init__(_,**kw):parent.events.append('rope_construct');parent.assertIs(kw['owner'],parent.execution.prefix_owner)
            def __enter__(_):parent.events.append('rope_enter');return _
            def __exit__(_, *exc):parent.events.append('rope_exit')
            def seal(_,**kw):
                parent.assertTrue(parent.token.consumed);parent.assertIs(kw['terminal'],parent.token)
                parent.events.append('rope_seal');return {'mock':'rope-report'},parent.ropebytes
        rope.RopeOperandCapture=Capture
        registry._TerminalEvidence=NS
        def dispatch(*args):
            self.events.append('pc12_dispatch');self.state['invocations']+=1;self.state['capture']=NS(data=NS(fields={}))
        bridge.make_dispatch=lambda *a,**kw:(dispatch,self.state)
        def prefix(*a):self.events.append('original_prefix');return {'mock':'prefix'}
        def suffix(*a,**kw):
            self.events.append('original_suffix');kw['attention_dispatch'](None,None,None)
            return self.actual,{'native_acceptance':'LEGACY_NOT_PASS'}
        def terminal(*a):self.events.append('original_terminal');return self.token
        def seal(**kw):
            self.events.append('original_registry_seal');self.token.consumed=True
            kw['sealed_payloads']['silu']=self.silubytes
            return {'mock':'registry'}
        def live(*args):self.events.append('original_live_recheck')
        registry.terminal_snapshot=terminal;registry.seal_registry=seal;registry._live_terminal=live
        self.runtime=NS(policy=NS(reference_gate=lambda x:Context(),ObservedSiluLibrary=lambda *a:object(),OfficialPrefixOwner=lambda x:object(),OfficialAttentionOwner=lambda *a:object()),
            fixtures=NS(make_qwen2_21_fixture=lambda *a:self.fixture),prefix=NS(PhysicalMemory=lambda *a:self.physical),physical_adapter=NS(FullGraphMemory=lambda *a:self.memory),
            original=NS(numeric=NS(model=NS(PrefixWorkspace=lambda *a:object()),CappedTrace=lambda:object())),owner_module=NS(DenseReductionOwner=lambda *a,**k:object()),
            library=NS(td_reset=lambda:0),selected=NS(sf_reset=lambda:0),binding=NS(ProfiledMatrixService=lambda *a:object()),profiles=NS(QWEN2_QKV_PROFILE=object()),scalar=NS(ScalarService=lambda:object()),
            public=NS(PublicFrontend=lambda *a:object(),group=NS(HostControl=lambda **k:object())),execution=NS(ReducedPublicExecution=lambda *a,**k:self.execution,execute_public_prefix=prefix),suffix=NS(execute_public_suffix=suffix))
    def tearDown(self):self.tmp.cleanup()
    def run_fixture(self,callback=None):
        return runner.run_actual(self.runtime,self.providers,self.profile,self.out,enabled=True,admission=self.admission,oracle_gate=self.guard,compare_after_terminal=callback)
    def callback(self,actual,observation,reg,*,terminal_values):
        self.events.append('compare');self.assertEqual(self.guard.state,'COMPARING')
        self.assertIs(actual,self.actual);self.assertIs(terminal_values['readonly_x'],self.xbytes)
        self.assertIs(terminal_values['sealed_silu'],self.silubytes);self.assertIs(terminal_values['rope_operands'],self.ropebytes)
        self.assertEqual(terminal_values['rope_physical_shape'],[128,64]);return {'status':'SYNTHETIC_ONLY_TEMP'}
    def test_original_sequence_and_same_payloads(self):
        _,report=self.run_fixture(self.callback)
        self.assertEqual(self.events,['oldgate_enter','rope_construct','rope_enter','original_prefix','rope_exit','original_suffix','pc12_dispatch','original_terminal','original_registry_seal','rope_seal','original_live_recheck','compare','oldgate_exit'])
        self.assertEqual(self.guard.state,'CLOSED');self.assertEqual(report['numeric_acceptance'],'TEMP')
    def test_default_off_has_no_constructor(self):
        with self.assertRaises(ValueError):runner.run_actual(None,{}, {},self.out)
        self.assertEqual(self.events,[])
    def test_old_m16_profile_rejected(self):
        self.profile['rows']=16
        with self.assertRaises(ValueError):self.run_fixture(self.callback)
        self.assertEqual(self.events,[])
    def test_x_hash_mismatch_never_opens_oracle(self):
        self.profile['input_views']['x']['sha256']='0'*64
        with self.assertRaises(ValueError):self.run_fixture(self.callback)
        self.assertNotIn('compare',self.events);self.assertEqual(self.guard.state,'SEALED')
    def test_rope_failure_never_opens_oracle(self):
        def bad(*a,**kw):raise ValueError('incomplete true operands')
        with patch.object(rope.RopeOperandCapture,'seal',bad):
            with self.assertRaises(ValueError):self.run_fixture(self.callback)
        self.assertNotIn('compare',self.events);self.assertEqual(self.guard.state,'SEALED')
    def test_terminal_failure_prevents_registry(self):
        def bad(*a):raise ValueError('not original terminal')
        with patch.object(registry,'terminal_snapshot',bad):
            with self.assertRaises(ValueError):self.run_fixture(self.callback)
        self.assertNotIn('original_registry_seal',self.events);self.assertEqual(self.guard.state,'SEALED')
    def test_final_live_recheck_failure_keeps_oracle_sealed(self):
        def bad(*a):raise ValueError('live debt returned')
        with patch.object(registry,'_live_terminal',bad):
            with self.assertRaises(ValueError):self.run_fixture(self.callback)
        self.assertNotIn('compare',self.events);self.assertEqual(self.guard.state,'SEALED')
    def test_caught_early_oracle_attempt_fails_after_whole_terminal(self):
        original=self.runtime.execution.execute_public_prefix
        def prefix(*a):
            try:self.guard.audit('open',(self.oracle/'fake.txt','r',0))
            except gate_module.OracleAccessDenied:pass
            return original(*a)
        self.runtime.execution.execute_public_prefix=prefix
        with self.assertRaises(gate_module.OracleAccessDenied):self.run_fixture(self.callback)
        self.assertIn('original_suffix',self.events);self.assertIn('original_terminal',self.events)
        self.assertNotIn('original_registry_seal',self.events);self.assertNotIn('compare',self.events)
        report=json.loads((self.out/'orchestration.json').read_text())
        self.assertEqual(report['status'],'FAIL');self.assertEqual(len(report['oracle_isolation']['denied']),1)
    def test_caught_relative_denial_fails_without_comparator(self):
        original=self.runtime.execution.execute_public_prefix
        def prefix(*a):
            try:self.guard.audit('open',('relative.txt','r',0))
            except gate_module.OracleAccessDenied:pass
            return original(*a)
        self.runtime.execution.execute_public_prefix=prefix
        with self.assertRaises(gate_module.OracleAccessDenied):self.run_fixture(None)
        self.assertIn('original_terminal',self.events);self.assertNotIn('original_registry_seal',self.events)
        report=json.loads((self.out/'orchestration.json').read_text());self.assertEqual(report['status'],'FAIL')
        self.assertEqual(len(report['oracle_isolation']['denied']),1)
    def test_foreign_monitor_busy_fallback_reaches_whole_terminal_then_fails(self):
        parent=self
        class Busy:
            def __enter__(self):raise ValueError('foreign slot retained')
            def __exit__(self,*exc):parent.fail('unentered foreign observer cleanup attempted')
        original=self.runtime.suffix.execute_public_suffix
        def suffix(*a,**kw):
            return actual_bridge_control.observe_driver(Busy(),Busy(),lambda:original(*a,**kw),self.state)
        self.runtime.suffix.execute_public_suffix=suffix
        with self.assertRaisesRegex(ValueError,'passive observation'):self.run_fixture(self.callback)
        self.assertIn('original_suffix',self.events);self.assertIn('original_terminal',self.events)
        self.assertNotIn('original_registry_seal',self.events);self.assertNotIn('compare',self.events)
        report=json.loads((self.out/'orchestration.json').read_text());self.assertEqual(report['status'],'FAIL')
        self.assertIsNotNone(report['service_observation_error']);self.assertEqual(self.guard.state,'SEALED')
    def test_comparator_failure_closes_oracle_and_records_fail(self):
        def bad(*a,**k):raise ValueError('compare failure')
        with self.assertRaises(ValueError):self.run_fixture(bad)
        self.assertEqual(self.guard.state,'CLOSED');self.assertEqual(json.loads((self.out/'orchestration.json').read_text())['status'],'FAIL')

if __name__=='__main__':
    if any(n in sys.modules for n in ('numpy','torch','transformers')):raise RuntimeError('ML import forbidden')
    unittest.main(verbosity=2)
