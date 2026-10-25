"""Exercise worker outcome ordering with stdlib-only fakes, never a DUT/ELF."""
import contextlib,importlib,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import runtime_admission,worker
from test_cache_fallback import Tests as Harness

class WorkerPolicy(Harness):
    # Inherited synthetic tests are not repeated; only reuse setup/helpers.
    def execute_fake(self,late_snapshot=None,runner_error=None):
        self.router.leave_normal();self.oracle.state='CLOSED';self.oracle.comparison_attempted=True
        self.oracle.require_clean=lambda:worker.need(not self.oracle.denied,'sticky synthetic oracle')
        self.oracle.report=lambda:dict(state=self.oracle.state,denied=list(self.oracle.denied))
        runtime=SimpleNamespace(matrix=SimpleNamespace(configure_library=lambda value:None),
             dense=SimpleNamespace(selected_library=lambda value:None))
        comparison=dict(observed_domain_passed=True,full29_numeric_pass=False)
        def run_actual(*args,**kwargs):
            if runner_error is not None:raise runner_error
            return {},dict(status='ACTUAL_INVENTORY_COMPLETE_NUMERIC_TEMP',comparison=comparison)
        fake_modules=dict(runtime_closure=SimpleNamespace(verify_graph=lambda *a:None),
             **{'qwen2_ordered_fullgraph_entry.runner':SimpleNamespace(run_actual=run_actual),
                'qwen2_ordered_fullgraph_entry.terminal_comparator':SimpleNamespace(make_comparator=lambda *a,**k:None),
                'qwen2_ordered_fullgraph_entry.stream':SimpleNamespace()})
        config=dict(self.cfg,runtime_graph={},providers={},profile={},oracle_root=str(self.root/'never_read_oracle'),
             oracle_exports={},source_manifest_sha256='synthetic',profile_sha256='synthetic',
             runtime_manifest_sha256='synthetic',input_manifest_sha256='synthetic',
             resources=dict(event_limit=2478403,trace_bytes=0),rotary_provenance=dict(synthetic=True))
        config['runtime_files']=dict(config['runtime_files'],**{config['elf']:dict(sha256='synthetic')})
        def snapshot(config,out,stage,*args,**kwargs):
            if stage=='WORKER_FINAL' and late_snapshot is not None:late_snapshot()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(worker,'install_oracle',return_value=(self.oracle,type(self.oracle))))
            stack.enter_context(patch.object(runtime_admission,'normal_initialize',return_value=(runtime,self.router,(),None,[])))
            stack.enter_context(patch.object(runtime_admission,'snapshot',side_effect=snapshot))
            stack.enter_context(patch.dict(sys.modules,{'native_binding':SimpleNamespace(load_library=lambda *a:(object(),dict(synthetic=True)))}))
            stack.enter_context(patch.object(worker,'verify_tempdir',return_value=None))
            stack.enter_context(patch.object(worker.importlib,'import_module',side_effect=lambda name:fake_modules[name]))
            stack.enter_context(patch.object(worker,'event_totals',return_value=dict(synthetic=True)))
            return worker.execute(config,'synthetic',self.out,dict(run_id='synthetic'))
    def test_fake_success_report(self):
        result=self.execute_fake();self.assertTrue(result['passed']);self.assertEqual(result['runtime_policy']['denied'],[])
    def test_final_snapshot_unresolved_fallback_cannot_leave_pass(self):
        path=self.source()
        def late():
            import _frozen_importlib_external as frozen
            with patch.object(frozen,'exec',lambda *a,**k:None,create=True),self.active():self.load(path)
        with self.assertRaisesRegex(ValueError,'final runtime qualification failed'):self.execute_fake(late_snapshot=late)
        result=json.loads((self.out/'WORKER_RESULT.json').read_text())
        self.assertFalse(result['passed']);self.assertIn('final_runtime_policy_error',result)
        self.assertEqual(result['runtime_policy']['bytecode_cache_events'][0]['status'],'REJECTED_UNRESOLVED')
    def test_original_error_preserved_with_late_denial(self):
        original=LookupError('synthetic original fixture error')
        def late():
            with self.active():self.router.audit('socket.connect',())
        with self.assertRaises(LookupError) as caught:self.execute_fake(late_snapshot=late,runner_error=original)
        self.assertIs(caught.exception,original)
        result=json.loads((self.out/'WORKER_RESULT.json').read_text())
        self.assertEqual(result['error'],dict(type='LookupError',detail=str(original)))
        self.assertIn('final_runtime_audit_error',result);self.assertIn('final_runtime_policy_error',result)
        self.assertEqual(result['runtime_policy']['denied'][0]['kind'],'network_or_child_process_forbidden')

# Reuse helper behavior without running the imported test class a second time.
if __name__=='__main__':
    names=['test_fake_success_report','test_final_snapshot_unresolved_fallback_cannot_leave_pass','test_original_error_preserved_with_late_denial']
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(WorkerPolicy(name) for name in names))
    raise SystemExit(not result.wasSuccessful())
