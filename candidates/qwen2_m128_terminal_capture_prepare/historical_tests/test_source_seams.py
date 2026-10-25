"""Pure stdlib source/mock checks; no DUT/ML imports or task payload reads."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
OVER=HERE/'overlay/candidates/qwen2_ordered_fullgraph_entry'
spec=importlib.util.spec_from_file_location('oracle_gate_under_test',HERE/'oracle_path_gate.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

class PathGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.oracle=self.root/'reference_pair01/capture';self.oracle.mkdir(parents=True)
        self.payload=self.oracle/'y.native.bin';self.payload.write_bytes(b'SYNTHETIC-NOT-A-TENSOR')
        self.other=self.root/'input.txt';self.other.write_text('synthetic provider')
        self.guard=g.ExactOraclePathGate([self.oracle],[self.payload])
    def tearDown(self):self.tmp.cleanup()
    def install_mock(self):
        with patch.object(g.sys,'addaudithook') as add:
            self.guard.install({},'');self.assertEqual(add.call_count,1)
    def deny(self,target,event='open'):
        with self.assertRaises(g.OracleAccessDenied):self.guard.audit(event,(target,'r',0))
    def test_exact_new_root_denied(self):self.deny(str(self.payload))
    def test_bytes_root_denied(self):self.deny(os.fsencode(self.payload))
    def test_path_object_denied(self):self.deny(self.payload)
    def test_normalized_dotdot_denied(self):
        (self.oracle/'child').mkdir();self.deny(str(self.oracle/'child/../y.native.bin'))
    def test_symlink_alias_denied(self):
        p=self.root/'alias';p.symlink_to(self.payload);self.deny(p)
    def test_hardlink_inode_denied(self):
        p=self.root/'alias.bin';os.link(self.payload,p);self.deny(p)
    def test_existing_fd_denied(self):
        with self.payload.open('rb') as f:self.deny(f.fileno())
    def test_proc_fd_alias_denied(self):
        with self.payload.open('rb') as f:self.deny('/proc/self/fd/'+str(f.fileno()))
    def test_mmap_fd_denied(self):
        with self.payload.open('rb') as f:self.deny(f.fileno(),'mmap.__new__')
    def test_anonymous_map_not_oracle(self):self.guard.audit('mmap.__new__',(-1,4096,0,0))
    def test_unrelated_input_not_oracle(self):self.guard.audit('open',(str(self.other),'r',0))
    def test_sibling_prefix_is_not_root(self):
        p=self.root/'reference_pair01/capture_old';p.mkdir();self.guard.audit('open',(p/'y.bin','r',0))
    def test_fd_inventory_denied(self):
        with self.assertRaises(g.OracleAccessDenied):self.guard.install({4:str(self.payload)},'')
    def test_maps_inventory_denied(self):
        with self.assertRaises(g.OracleAccessDenied):self.guard.install({},'00-ff r--p 0 00:00 12 '+str(self.payload))
    def test_uninstalled_comparison_denied(self):
        with self.assertRaises(g.OracleAccessDenied):self.guard.compare_after_live_terminal(lambda:None,lambda:None)
    def test_boolean_terminal_rejected(self):
        self.install_mock()
        with self.assertRaises(g.OracleAccessDenied):self.guard.compare_after_live_terminal(lambda:True,lambda:None)
        self.assertEqual(self.guard.state,'SEALED');self.deny(self.payload)
    def test_report_terminal_rejected(self):
        self.install_mock()
        with self.assertRaises(g.OracleAccessDenied):self.guard.compare_after_live_terminal(lambda:{'whole_terminal':True},lambda:None)
    def test_live_failure_does_not_open(self):
        self.install_mock();called=[]
        def bad():raise ValueError('original live terminal fails')
        with self.assertRaises(ValueError):self.guard.compare_after_live_terminal(bad,lambda:called.append(1))
        self.assertEqual(called,[]);self.deny(self.payload)
    def test_live_check_then_compare_then_closed(self):
        self.install_mock();events=[]
        def live():events.append('original-live-check');self.assertEqual(self.guard.state,'SEALED')
        def compare(*args,**kwargs):
            events.append('compare');self.guard.audit('open',(self.payload,'r',0));return (args,kwargs)
        result=self.guard.compare_after_live_terminal(live,compare,7,terminal_values={'synthetic':True})
        self.assertEqual(events,['original-live-check','compare']);self.assertEqual(result,((7,),{'terminal_values':{'synthetic':True}}))
        self.assertEqual(self.guard.state,'CLOSED');self.deny(self.payload)
    def test_caught_oracle_read_is_sticky(self):
        self.install_mock();self.deny(self.payload);calls=[]
        with self.assertRaises(g.OracleAccessDenied):self.guard.compare_after_live_terminal(lambda:None,lambda:calls.append(1))
        self.assertEqual(calls,[]);self.assertFalse(self.guard.report()['acceptance_eligible'])
    def test_caught_relative_open_is_sticky(self):
        self.install_mock();self.deny('relative.bin');self.assertEqual(len(self.guard.denied),1)
        with self.assertRaises(g.OracleAccessDenied):self.guard.require_clean()
    def test_comparison_failure_reseals(self):
        self.install_mock()
        def fail():raise RuntimeError('comparison failure')
        with self.assertRaises(RuntimeError):self.guard.compare_after_live_terminal(lambda:None,fail)
        self.assertEqual(self.guard.state,'CLOSED');self.deny(self.payload)
    def test_second_compare_rejected(self):
        self.install_mock();self.guard.compare_after_live_terminal(lambda:None,lambda:None)
        with self.assertRaises(g.OracleAccessDenied):self.guard.compare_after_live_terminal(lambda:None,lambda:None)
    def test_second_install_rejected(self):
        self.install_mock()
        with self.assertRaises(g.OracleAccessDenied):self.guard.install({},'')
    def test_relative_open_rejected_unknown_dirfd(self):self.deny('reference_pair01/capture/y.native.bin')
    def test_ancestor_dirfd_does_not_make_relative_safe(self):
        ancestor=os.open(self.root,os.O_RDONLY)
        try:
            self.guard.assert_no_inherited_oracle({ancestor:str(self.root)},'')
            self.deny('reference_pair01/capture/y.native.bin')
        finally:os.close(ancestor)
    def test_incomplete_root_enumeration_rejected(self):
        extra=self.oracle/'prob.native.bin';extra.write_bytes(b'SYNTHETIC')
        with self.assertRaises(g.OracleAccessDenied):g.ExactOraclePathGate([self.oracle],[self.payload])
    def test_duplicate_root_file_rejected(self):
        with self.assertRaises(g.OracleAccessDenied):g.ExactOraclePathGate([self.oracle],[self.payload,self.payload])
    def test_empty_payload_enumeration_rejected(self):
        with self.assertRaises(g.OracleAccessDenied):g.ExactOraclePathGate([self.oracle],[])
    def test_payload_outside_declared_root_rejected(self):
        with self.assertRaises(g.OracleAccessDenied):g.ExactOraclePathGate([self.oracle],[self.other])

class SourceSeamTests(unittest.TestCase):
    def test_no_ml_import(self):
        self.assertFalse(set(sys.modules)&{'torch','numpy','transformers'})
    def test_helper_exact_overlay(self):self.assertEqual((HERE/'oracle_path_gate.py').read_bytes(),(OVER/'oracle_path_gate.py').read_bytes())
    def test_sources_parse_without_import(self):
        for name in ('runner.py','registry.py','oracle_path_gate.py'):ast.parse((OVER/name).read_text())
    def test_runner_only_new_m128_profile(self):
        s=(OVER/'runner.py').read_text();self.assertIn("type(rows) is int and rows == 128",s)
        self.assertIn("profile.get('profile_id') == 'ordered_fullgraph_m128_terminal_capture_v1'",s)
        self.assertNotIn('make_qwen2_21_fixture(16',s)
    def test_source_order_registry_before_oracle_compare(self):
        s=(OVER/'runner.py').read_text()
        self.assertLess(s.index('registry.seal_registry'),s.index('physical.raw(input_region'))
        self.assertLess(s.index('physical.raw(input_region'),s.index('oracle_gate.compare_after_live_terminal'))
        self.assertIn('registry._live_terminal(x, physical, memory, execution_report)',s)
    def test_x_from_original_allocation(self):
        s=(OVER/'runner.py').read_text();self.assertIn("input_region = physical.regions['x']",s)
        self.assertIn("input_region['provider'] is providers['x']",s)
        self.assertIn("hashlib.sha256(input_x).hexdigest() == expected_x['sha256']",s)
    def test_single_original_silu_seal_return(self):
        s=(OVER/'registry.py').read_text();self.assertEqual(s.count("silu_library.seal(actual['act'].tobytes())"),1)
        self.assertIn("sealed_payloads['silu'] = silu",s)
        self.assertLess(s.index('terminal.consumed = True'),s.index("sealed_payloads['silu'] = silu"))
    def test_profile_budget_not_increased(self):self.assertIn("profile['wall_budget'] <= 1800",(OVER/'runner.py').read_text())
    def test_default_off_preserved(self):
        s=(OVER/'runner.py').read_text();self.assertIn('enabled=False',s);self.assertIn("'ordered fullgraph is default off'",s)
    def test_coverage_still_temp(self):
        s=(OVER/'runner.py').read_text();self.assertIn('TEMP_COVERAGE_LIMITED_NO_SYNTHESIS',s)
        self.assertIn('ACTUAL_OPERAND_CAPTURE_PENDING_NUMERIC_COMPARISON',s)
    def test_rope_same_source_and_prefix_scope(self):
        s=(OVER/'runner.py').read_text();self.assertIn('with rope_capture:',s)
        self.assertLess(s.index('registry.seal_registry'),s.index('rope_capture.seal('))
        self.assertLess(s.index('rope_capture.seal('),s.index('oracle_gate.compare_after_live_terminal'))
        p=OVER/'rope_operand_capture/rope_capture.py'
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),'25d31af4bc242344f6c545aaa56ebd32d8babd5490efa43b22508292e7bbc5d2')
    def test_trace_dependency_exact_copies(self):
        pins=json.loads((HERE/'TRACE_DEPENDENCY_PINS.json').read_text())['files']
        for name in ('bridge.py','service_trace.py','stream.py'):
            self.assertEqual(hashlib.sha256((OVER/name).read_bytes()).hexdigest(),pins[name]['sha256'])
    def test_retention_uses_raw_stream_receipt_not_tuple_json(self):
        s=(OVER/'runner.py').read_text();self.assertIn('stream.artifact_evidence(',s)
        self.assertIn("event_stream_path=out / 'attention_service_events.q2evt'",s)
        self.assertIn("observation['service_events']['count']",s)
        self.assertNotIn('json.dumps(raw_events',s)
    def test_manifest_15_roles_9_methods(self):
        m=json.loads((HERE/'SOURCE_INTERFACE_MANIFEST.json').read_text())
        self.assertEqual(m['role_count'],15);self.assertEqual(m['method_count'],9)
        for rec in m['runtime_roles'].values():
            p=rec['source'];self.assertEqual(hashlib.sha256(Path(p['path']).read_bytes()).hexdigest(),p['sha256'])
    def test_merged_closure_exact_counts(self):
        m=json.loads((HERE/'MERGED_RUNTIME_CLOSURE_DRAFT.json').read_text())
        self.assertEqual(m['original_normal_file_count'],722);self.assertEqual(m['file_count'],723)
        self.assertEqual(len(m['added_native_files']),1);self.assertEqual(len(m['runtime_graph']['files']),20)
        self.assertFalse(m['read_payloads']);self.assertFalse(m['current_hash_revalidation_performed'])
    def test_no_component_inputs_copied(self):
        m=json.loads((HERE/'MERGED_RUNTIME_CLOSURE_DRAFT.json').read_text())
        self.assertNotIn('inputs',m);self.assertFalse(any('/first/frozen/' in p for p in m['files']))
    def test_no_execution_in_generator(self):
        for name in ('prepare_interfaces.py','prepare_patch.py'):
            tree=ast.parse((HERE/name).read_text())
            self.assertFalse(any(isinstance(n,ast.Import) and any(a.name.split('.')[0] in ('torch','numpy','ctypes','transformers') for a in n.names) for n in ast.walk(tree)))

if __name__=='__main__':unittest.main(verbosity=2)
