"""Pure control fixtures only: never imports DUT, NumPy, ELF or reads tensors."""
import importlib.util
from array import array
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PACKAGE = '_fullgraph_runner_control_fixture'
pkg = ModuleType(PACKAGE)
pkg.__path__ = [str(HERE)]
sys.modules[PACKAGE] = pkg
spec = importlib.util.spec_from_file_location(PACKAGE + '.runner', HERE / 'runner.py')
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)
from importlib import import_module
bridge = import_module(PACKAGE + '.bridge')
registry = import_module(PACKAGE + '.registry')


class ControlOnly(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name) / 'fresh'
        self.events = []
        self.gate = NS(opened=False, library=lambda x: x)
        self.state = dict(invocations=0, capture=None, capture_report={'fixture': True},
                          capture_error=None, service_error=None, service_events=[])
        self.profile = dict(rows=16, epoch=7, wall_budget=30, qk_profile=2,
                            pv_profile=0, raw_kv_transport=False, input_spec={})
        self.admission = dict(execution_authorized=True,
            **{k: 'fixture-only-not-a-real-admission' for k in (
                'source_manifest_sha256', 'profile_sha256', 'elf_sha256',
                'runtime_manifest_sha256', 'input_manifest_sha256', 'run_id')})
        events = self.events
        class Gate:
            def __enter__(_):
                events.append('gate_enter')
                return self.gate
            def __exit__(_, *args): events.append('gate_exit')
        self.fixture = NS(config=NS(regions=[None] * 3 + [NS(base=0, limit=10000)]))
        self.physical = NS(metadata_port=lambda: 'metadata')
        self.scalar = object()
        self.service = object()
        self.owner = object()
        self.execution = object()
        def reset(name):
            events.append(name)
            return 0
        def owner(workspace, **flags):
            self.assertEqual(workspace, (0,10000,8,2560))
            self.assertEqual(flags, dict(enable_dense_drain=True, enable_k_window=True,
                enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True))
            events.append('owner')
            return self.owner
        def service(lib, profile):
            self.assertIs(lib, self.runtime.library)
            self.assertEqual(profile, 'original-qkv-profile')
            events.append('service')
            return self.service
        def scalar():
            events.append('scalar')
            return self.scalar
        def prefix_owner(s):
            self.assertIs(s, self.scalar)
            return 'prefix-owner'
        def attention_owner(m,s):
            self.assertIs(m, self.service)
            self.assertIs(s, self.scalar)
            return 'attention-owner'
        def execution(front, owner_arg, trace, deadline, **kw):
            self.assertIs(owner_arg, self.owner)
            self.assertIs(kw['matrix_service'], self.service)
            self.assertEqual(kw['prefix_owner'], 'prefix-owner')
            self.assertEqual(kw['attention_owner'], 'attention-owner')
            events.append('execution')
            return self.execution
        def prefix(*args):
            self.assertIs(args[0], self.execution)
            self.assertFalse(self.gate.opened)
            events.append('prefix')
            return {'fixture':'prefix'}
        def suffix(*args, **kw):
            self.assertFalse(self.gate.opened)
            events.append('suffix')
            self.assertEqual(set(kw), {'memory','attention_dispatch'})
            kw['attention_dispatch'](self.execution, self.physical, 'pc12-fixture')
            return {'fixture':'actual'}, {'native_acceptance':'legacy-label'}
        self.runtime = NS(
            policy=NS(reference_gate=lambda _:Gate(), OfficialPrefixOwner=prefix_owner,
                OfficialAttentionOwner=attention_owner, ObservedSiluLibrary=lambda *a:'silu'),
            fixtures=NS(make_qwen2_21_fixture=lambda *a:self.fixture),
            prefix=NS(PhysicalMemory=lambda *a:self.physical),
            physical_adapter=NS(FullGraphMemory=lambda p:'memory'),
            original=NS(numeric=NS(model=NS(PrefixWorkspace=lambda *a:a),CappedTrace=lambda:'trace')),
            owner_module=NS(DenseReductionOwner=owner),
            library=NS(td_reset=lambda:reset('matrix_reset')),
            selected=NS(sf_reset=lambda:reset('silu_reset')),
            binding=NS(ProfiledMatrixService=service), profiles=NS(QWEN2_QKV_PROFILE='original-qkv-profile'),
            scalar=NS(ScalarService=scalar),
            public=NS(PublicFrontend=lambda *a:'front',group=NS(HostControl=lambda **k:k)),
            execution=NS(ReducedPublicExecution=execution,execute_public_prefix=prefix),
            suffix=NS(execute_public_suffix=suffix))
        def dispatch(*args):
            events.append('dispatch')
            self.state['invocations'] += 1
            self.state['capture'] = NS(data=NS(fields={'fixture': dict(words=array('I',[123]), observed=bytearray([1]), frequency=array('H',[1]), shape=[1])}))
        def terminal(*args):
            events.append('terminal')
            self.assertFalse(self.gate.opened)
            return 'terminal'
        def seal(**kw):
            events.append('seal')
            self.assertFalse(self.gate.opened)
            self.assertEqual(kw['terminal'], 'terminal')
            return {'fixture':'registry'}
        self.patches = [patch.object(bridge,'make_dispatch',return_value=(dispatch,self.state)),
                        patch.object(registry,'terminal_snapshot',side_effect=terminal),
                        patch.object(registry,'seal_registry',side_effect=seal)]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def run_fixture(self, **kw):
        args=dict(enabled=True,admission=self.admission)
        args.update(kw)
        return runner.run_actual(self.runtime, {'x':lambda offset:b''}, self.profile,
                                 self.out, **args)

    def test_real_constructor_call_shape_and_order(self):
        actual, report=self.run_fixture()
        self.assertEqual(actual,{'fixture':'actual'})
        self.assertEqual(self.events,['gate_enter','owner','matrix_reset','silu_reset',
            'service','scalar','execution','prefix','suffix','dispatch','terminal','seal','gate_exit'])
        self.assertEqual(report['status'],'ACTUAL_INVENTORY_COMPLETE_NUMERIC_TEMP')
        self.assertEqual(report['numeric_acceptance'],'TEMP')
        self.assertEqual(report['execution']['native_acceptance'],'NOT_EVALUATED_BY_EXECUTION')
        self.assertEqual(report['execution']['inherited_native_acceptance_label'],'legacy-label')

    def test_reference_after_whole_terminal_and_seal_only(self):
        def compare(*args):
            self.assertTrue(self.gate.opened)
            self.assertEqual(self.events[-1],'seal')
            evidence=json.loads((self.out/'actual_attention_capture/EVIDENCE.json').read_text())
            self.assertTrue(evidence['whole_terminal_verified'])
            self.assertEqual((self.out/'actual_attention_capture/0_words.bin').read_bytes(),array('I',[123]).tobytes())
            self.events.append('compare')
            return {'fixture':'not-numeric-pass'}
        _,r=self.run_fixture(compare_after_terminal=compare)
        self.assertEqual(self.events[-2: ],['compare','gate_exit'])
        self.assertEqual(r['numeric_acceptance'],'TEMP')

    def test_default_off_before_any_constructor(self):
        with self.assertRaisesRegex(ValueError,'default off'):
            runner.run_actual(None,{}, {},self.out)
        self.assertFalse(self.out.exists()); self.assertEqual(self.events,[])

    def test_unauthorized_rejected(self):
        self.admission['execution_authorized']=False
        with self.assertRaisesRegex(ValueError,'admission'): self.run_fixture()
        self.assertFalse(self.out.exists())

    def test_missing_each_admission_identity(self):
        for k in tuple(self.admission):
            if k=='execution_authorized':continue
            with self.subTest(k=k):
                a=dict(self.admission);a.pop(k)
                with self.assertRaisesRegex(ValueError,'identity'):self.run_fixture(admission=a)
        self.assertEqual(self.events,[])

    def test_m128_rejected(self):
        self.profile['rows']=128
        with self.assertRaisesRegex(ValueError,'M16 only'):self.run_fixture()

    def test_profile_mismatch_rejected(self):
        for key,value in [('qk_profile',0),('pv_profile',2),('raw_kv_transport',True)]:
            with self.subTest(key=key):
                old=self.profile[key];self.profile[key]=value
                with self.assertRaisesRegex(ValueError,'QK2'):self.run_fixture()
                self.profile[key]=old

    def test_unbounded_budget_rejected(self):
        for value in [0,-1,1801,float('inf'),float('nan'),True]:
            with self.subTest(value=value):
                self.profile['wall_budget']=value
                with self.assertRaisesRegex(ValueError,'bounded'):self.run_fixture()

    def test_existing_output_refused_preserved(self):
        self.out.mkdir();marker=self.out/'unique';marker.write_text('keep')
        with self.assertRaisesRegex(ValueError,'fresh'):self.run_fixture()
        self.assertEqual(marker.read_text(),'keep')

    def test_observer_failure_after_suffix_no_reference(self):
        self.state['capture_error']='missing actual field'
        with self.assertRaisesRegex(ValueError,'passive observation'):
            self.run_fixture(compare_after_terminal=lambda *a:self.fail('reference ran'))
        self.assertIn('terminal',self.events);self.assertNotIn('seal',self.events)
        self.assertFalse(self.gate.opened)
        r=json.loads((self.out/'orchestration.json').read_text())
        self.assertEqual(r['status'],'FAIL')
        self.assertEqual(r['attention_observation_error'],'missing actual field')
        self.assertTrue((self.out/'actual_attention_capture/0_words.bin').is_file())
        self.assertTrue(r['capture_evidence']['whole_terminal_verified'])

    def test_service_observer_failure_rejected(self):
        self.state['service_error']='foreign ticket'
        with self.assertRaisesRegex(ValueError,'passive observation'):self.run_fixture()
        self.assertIn('suffix',self.events)
        self.assertFalse(self.gate.opened)

    def test_terminal_failure_blocks_registry_and_reference(self):
        with patch.object(registry,'terminal_snapshot',side_effect=ValueError('not terminal')):
            with self.assertRaisesRegex(ValueError,'not terminal'):self.run_fixture()
        self.assertNotIn('seal',self.events);self.assertFalse(self.gate.opened)
        self.assertFalse(json.loads((self.out/'actual_attention_capture/EVIDENCE.json').read_text())['whole_terminal_verified'])
        self.assertEqual(json.loads((self.out/'orchestration.json').read_text())['status'],'FAIL')

    def test_registry_failure_keeps_reference_closed(self):
        with patch.object(registry,'seal_registry',side_effect=ValueError('missing field')):
            with self.assertRaisesRegex(ValueError,'missing field'):self.run_fixture()
        self.assertFalse(self.gate.opened)

    def test_prefix_failure_no_suffix_no_reference(self):
        self.runtime.execution.execute_public_prefix=lambda *a:(_ for _ in ()).throw(ValueError('prefix failed'))
        with self.assertRaisesRegex(ValueError,'prefix failed'):self.run_fixture()
        self.assertNotIn('suffix',self.events);self.assertFalse(self.gate.opened)

    def test_reset_failure_no_service(self):
        self.runtime.library.td_reset=lambda:1
        with self.assertRaisesRegex(ValueError,'reset'):self.run_fixture()
        self.assertNotIn('service',self.events);self.assertFalse(self.gate.opened)

    def test_no_pc12_dispatch_rejected(self):
        self.runtime.suffix.execute_public_suffix=lambda *a,**k:({}, {})
        with self.assertRaisesRegex(ValueError,'exactly once'):self.run_fixture()
        self.assertFalse(self.gate.opened)

    def test_duplicate_pc12_rejected(self):
        self.state['invocations']=1
        with self.assertRaisesRegex(ValueError,'exactly once'):self.run_fixture()
        self.assertFalse(self.gate.opened)

    def test_driver_failure_preserves_unsealed_partial_raw_events(self):
        raw = [{'event': 'fixture-partial', 'ticket': 17}]
        def suffix(*args, **kwargs):
            self.state['service_events_raw'] = raw
            self.state['service_events'] = None
            raise ValueError('driver failed')
        self.runtime.suffix.execute_public_suffix = suffix
        with self.assertRaisesRegex(ValueError,'driver failed'):self.run_fixture()
        evidence = json.loads((self.out/'actual_attention_capture/EVIDENCE.json').read_text())
        self.assertFalse(evidence['whole_terminal_verified'])
        self.assertFalse(evidence['raw_service_events']['sealed'])
        self.assertEqual(json.loads((self.out/'actual_attention_capture/raw_service_events.json').read_text()), raw)
        self.assertFalse(self.gate.opened)

    def test_raw_events_preferred_without_promoting_unsealed_trace(self):
        self.state['service_events_raw'] = [{'event': 'raw-only'}]
        self.state['service_events'] = None
        with self.assertRaisesRegex(ValueError,'passive observation'):self.run_fixture()
        evidence = json.loads((self.out/'actual_attention_capture/EVIDENCE.json').read_text())
        self.assertFalse(evidence['raw_service_events']['sealed'])
        self.assertFalse(self.gate.opened)

    def test_raw_events_preferred_over_sealed_storage(self):
        self.state['service_events_raw'] = [{'event': 'raw-original'}]
        self.state['service_events'] = [{'event': 'sealed-fixture'}]
        self.run_fixture()
        self.assertEqual(json.loads((self.out/'actual_attention_capture/raw_service_events.json').read_text()),
                         [{'event': 'raw-original'}])
        evidence = json.loads((self.out/'actual_attention_capture/EVIDENCE.json').read_text())
        self.assertTrue(evidence['raw_service_events']['sealed'])

    def test_reference_failure_preserved_after_terminal(self):
        def compare(*args):raise ValueError('reference failure')
        with self.assertRaisesRegex(ValueError,'reference failure'):
            self.run_fixture(compare_after_terminal=compare)
        self.assertTrue(self.gate.opened)
        self.assertEqual(json.loads((self.out/'orchestration.json').read_text())['status'],'FAIL')


if __name__=='__main__':unittest.main()
