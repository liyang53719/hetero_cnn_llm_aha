"""Pure source/file/mocks only: never import the oracle or execute reference/DUT."""
import ast,hashlib,importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;CODE=ROOT/'code';OLD=ROOT.parent/'r3/code'
sys.path.insert(0,str(CODE))
import boundary,durable
spec=importlib.util.spec_from_file_location('_review_worker',CODE/'worker.py');worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
CONFIG=json.loads((ROOT/'PRIVATE_CONFIG.json').read_text())
def node(path,name):return next(n for n in ast.parse(Path(path).read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)
class Recovery(unittest.TestCase):
    def test_complete_seal_and_real_terminal_metadata_without_values(self):
        boundary.verify_pins(CONFIG)
        gate=worker.terminal_gate(CONFIG)
        self.assertEqual(gate['status'],'BOTH_SAVED_PUBLIC3_TERMINALS_ADMITTED')
        self.assertFalse(gate['reference_values_loaded'])
        self.assertEqual(gate['original_attempt_state'],'FAILED_RETAINED')
    def test_exact_recipe_collector_primitives_and_supervisor_core(self):
        for name in ('reference_capture.py','primitives.py','artifacts.py','module_inventory.py','runtime_closure.py'):
            self.assertEqual((CODE/name).read_bytes(),(OLD/name).read_bytes())
        for name in ('limits','identity','kill_active_if_owned','cleanup_deadline_signal','parent_work_budget_signal','install_parent_guards','live_usage','same_group_descendants','require_output_budget','Budget','supervise'):
            self.assertEqual(ast.dump(node(CODE/'launch.py',name)),ast.dump(node(OLD/'launch.py',name)))
    def test_oracle_has_only_frozen_inputs_and_values_decode_after_recipe(self):
        source=(CODE/'worker.py').read_text();main=source[source.index('def main():'):]
        self.assertLess(main.index('gate=terminal_gate(config)'),main.index('module=load_bound'))
        self.assertLess(main.index("STAGES.mark('BEFORE_RECIPE'"),main.index('reference=capture_reference('))
        self.assertLess(main.index('reference=capture_reference('),main.index('guard.reference_complete=True'))
        self.assertLess(main.index("STAGES.mark('RECIPE_COMPLETE'"),main.index('guard.reference_complete=True'))
        self.assertLess(main.index('guard.reference_complete=True'),main.index('comparison=compare_completed_reference('))
        call=next(n for n in ast.walk(node(CODE/'worker.py','main')) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='capture_reference')
        self.assertEqual(ast.unparse(call.args[2]),'inputs');self.assertEqual(len(call.args),5)
        self.assertNotIn('saved_fields(',main[:main.index('reference=capture_reference(')])
    def test_archived_values_denied_until_reference_complete_and_always_readonly(self):
        g=boundary.Boundary(CONFIG,ROOT/'tmp/new_output')
        path=Path(CONFIG['original_attempt'])/'pair/artifacts/OUTPUT_0.u32le'
        with self.assertRaisesRegex(ValueError,'unavailable'):g.audit('open',(str(path),'r',os.O_RDONLY))
        for name in ('qr','kr','v'):g.audit('open',(CONFIG['inputs'][name]['path'],'r',os.O_RDONLY))
        g.reference_complete=True;g.audit('open',(str(path),'r',os.O_RDONLY))
        with self.assertRaises(ValueError):g.audit('open',(str(path),'w',os.O_WRONLY))
        with self.assertRaises(ValueError):g.audit('os.remove',(str(path),-1))
    def test_process_native_external_runtime_and_unknown_files_denied(self):
        g=boundary.Boundary(CONFIG,ROOT/'tmp/new_output')
        for event,args in [('ctypes.dlopen',('libm.so.6',)),('subprocess.Popen',()),('socket.connect',()),('import',('numpy',)),('import',('candidates.x',)),('import',('ctypes',)),('open',('/tmp/unpinned.bin','r',os.O_RDONLY))]:
            with self.assertRaises(ValueError):g.audit(event,args)
    def test_actual_hook_allows_atomic_phase_and_deny_artifact_before_reference(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as d:
            out=Path(d);g=boundary.Boundary(CONFIG,out);active=[True]
            def hook(event,args):
                if active[0]:g.audit(event,args)
            sys.addaudithook(hook)
            try:
                stages=durable.Stages(out/'stages');stages.mark('BEFORE_RECIPE');stages.mark('RECIPE_COMPLETE');g.reference_complete=True
                stages.mark('COMPARISON_COMPLETE');stages.mark('POSTFLIGHT_COMPLETE')
            finally:active[0]=False
            paths=sorted((out/'stages').glob('*.json'));self.assertEqual(len(paths),4)
            rows=[json.loads(p.read_text()) for p in paths]
            self.assertEqual([r['stage'] for r in rows],['BEFORE_RECIPE','RECIPE_COMPLETE','COMPARISON_COMPLETE','POSTFLIGHT_COMPLETE'])
            self.assertTrue(all(r['cpu_ns']>0 and r['monotonic_ns']>0 for r in rows))
            self.assertFalse(list((out/'stages').glob('*.pending')))
    def test_atomic_stage_failure_and_duplicate_do_not_destroy_prior_evidence(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as d:
            p=Path(d)/'stage.json';durable.atomic_json(p,{'original':True});before=p.read_bytes()
            with self.assertRaises(FileExistsError):durable.atomic_json(p,{'new':True})
            self.assertEqual(p.read_bytes(),before);self.assertTrue(p.with_suffix('.json.pending').exists())
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as d:
            p=Path(d)/'stage.json'
            with patch.object(durable.os,'rename',side_effect=OSError('injected publish failure')):
                with self.assertRaises(OSError):durable.atomic_json(p,{'stage':'BEFORE_RECIPE'})
            self.assertFalse(p.exists());self.assertTrue(p.with_suffix('.json.pending').exists())
    def test_no_actual_attempt_or_authorization_in_new_profile(self):
        self.assertFalse(CONFIG['actual_execution_authorized']);self.assertTrue(CONFIG['reference_only'])
        self.assertFalse(CONFIG['DUT_reexecution_permitted']);self.assertFalse((ROOT/'attempts').exists());self.assertFalse((ROOT/'ROOT_GO.json').exists())
        self.assertEqual(CONFIG['limits']['cpu_seconds'],180);self.assertEqual(CONFIG['limits']['wall_seconds'],240)
        self.assertEqual(CONFIG['limits']['child_cpu_seconds']+CONFIG['limits']['parent_cpu_abort_hard'],180)
    def test_source_only_reference_closure_no_ctypes_or_libm_fma(self):
        recipe=Path(CONFIG['oracle_harness']).read_text()
        tree=ast.parse(recipe)
        imports={a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
        imports.update(n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module)
        self.assertFalse(imports&{'ctypes','numpy','subprocess'})
        arithmetic=Path(CONFIG['reference_sources']['arithmetic']['path'])
        for name in ('exact','rn','ref_add','ref_mul','ref_div','ref_bf'):
            self.assertNotIn('ctypes',ast.unparse(node(arithmetic,name)))
        p=Path(CONFIG['oracle_harness']).parent
        for path in (p/'INPUT_PINS.json',p/'schedule.py'):
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),CONFIG['files'][str(path)]['sha256'])
    def test_unneeded_header_payloads_denied_before_reference_and_outside_integrity(self):
        g=boundary.Boundary(CONFIG,ROOT/'tmp/new_output')
        headers=[p for p in CONFIG['files'] if p.endswith('.header.bin')]
        self.assertTrue(headers)
        for path in headers:
            with self.assertRaises(ValueError):g.audit('open',(path,'r',os.O_RDONLY))
            g.reference_complete=True
            with self.assertRaises(ValueError):g.audit('open',(path,'r',os.O_RDONLY))
            g.integrity=True;g.audit('open',(path,'r',os.O_RDONLY));g.integrity=False;g.reference_complete=False
    def test_saved_fields_validate_real_archive_without_reference_calculation(self):
        for i in range(2):
            fields=worker.saved_fields(CONFIG,i)
            self.assertEqual(len(fields),10);self.assertEqual(fields['normalizer']['shape'],(12,16,3))
            self.assertEqual(fields['normalizer']['frequency'].typecode,'H')
        original=Path.read_text
        target=Path(CONFIG['original_attempt'])/'pair/artifacts/CAPTURE_0_FIELDS.json'
        def changed(path,*a,**kw):
            text=original(path,*a,**kw)
            if path==target:
                value=json.loads(text);value['normalizer']['shape']=[12,17,3];return json.dumps(value)
            return text
        with patch.object(Path,'read_text',changed):
            with self.assertRaises(ValueError):worker.saved_fields(CONFIG,0)
    def test_failed_reference_never_releases_archived_outputs(self):
        source=ast.unparse(node(CODE/'worker.py','main'))
        self.assertNotIn('finally:\n        guard.reference_complete',source)
        self.assertNotIn('execute_component',source);self.assertNotIn('load_library',source)
if __name__=='__main__':unittest.main(verbosity=2)
