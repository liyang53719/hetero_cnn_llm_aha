"""Cold proofs only. Synthetic metadata is never a run/review receipt."""
import ast
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('ci_reference_recipe',HERE/'recipe.py')
R = importlib.util.module_from_spec(spec);spec.loader.exec_module(R)

class ColdTests(unittest.TestCase):
    def test_original_capture_exact_identity(self):
        specs = json.loads((HERE/'dependencies.json').read_bytes())
        for name in ('capture.py','guard.py','lifecycle.py','recipe.py','pins.json'):
            self.assertEqual(R.identity(R.ROOT/R.OLD/name),specs[R.OLD+'/'+name])
        self.assertEqual(specs[R.OLD+'/pins.json']['sha256'],R.O.PINS_SHA256)

    def test_source_manifest(self):
        self.assertGreater(R.source_manifest()['bytes'],0)

    def test_imports_cold(self):
        self.assertFalse(any(n.split('.')[0] in ('torch','numpy','transformers') for n in sys.modules))

    def test_source_cli(self):
        p = subprocess.run([sys.executable,'-B',str(HERE/'recipe.py')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result['status'],'NOT_EXECUTED_SOURCE_ONLY')
        self.assertFalse(result['model_executed']);self.assertFalse(result['numeric_execution_allowed'])

    def test_guard_default_is_cold(self):
        p = subprocess.run([sys.executable,'-B',str(HERE/'guard.py')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertFalse(json.loads(p.stdout)['numeric_execution_allowed'])

    def test_non_ci_generation_rejected(self):
        if R.ROOT != R.CI_ROOT:
            with self.assertRaisesRegex(R.Rejected,'exact CI root'):R.derive_bindings()
            with self.assertRaisesRegex(R.Rejected,'exact CI checkout'):R.runtime_pins()

    def test_no_freeze_fallback(self):
        with self.assertRaisesRegex(R.Rejected,'freeze not reviewed'):R.require_frozen_references({})

    def test_direct_capture_cannot_run(self):
        C = R.legacy('capture.py')
        with self.assertRaises(C.CaptureDisabled):C.capture(R.ROOT,{},Path('/tmp/never_written'))

    def test_fixed_paths_and_runtime_policy(self):
        self.assertEqual(str(R.CI_ROOT),'/home/runner/work/hetero_cnn_llm_aha/hetero_cnn_llm_aha')
        self.assertEqual(R.INPUT_PATHS['tail_raw'],R.TAIL+'/raw/FRESH_ACQUISITION.json')
        self.assertEqual(R.PYTHON_IDENTITY['bytes'],17752)
        pins = R.O.load_pins()
        self.assertEqual(pins['runtime_requirements']['threads'],4)
        self.assertEqual(pins['runtime_requirements']['interop_threads'],1)
        self.assertTrue(pins['runtime_requirements']['deterministic_algorithms'])
        self.assertEqual(pins['runtime_requirements']['capability'],'AVX512')

    def test_resolved_python_must_be_inside_setup_prefix(self):
        with patch.object(R,'PYTHON_PREFIX',Path('/nonexistent-ci-python')):
            with self.assertRaisesRegex(R.Rejected,'setup-python'):R.observed_python()

    def test_observed_python_hash_must_match(self):
        with patch.object(R,'PYTHON_PREFIX',Path(sys.executable).resolve().parent), \
             patch.object(R,'identity',return_value=dict(bytes=17752,sha256='0'*64)):
            with self.assertRaisesRegex(R.Rejected,'ELF identity'):R.observed_python()

    def effective(self):
        old = R.O.load_pins()
        b = dict(input_metadata={k:dict(path=p,bytes=1,sha256='1'*64) for k,p in R.INPUT_PATHS.items()})
        with patch.object(R,'bindings',return_value=b),patch.object(R,'runtime_pins',return_value=copy.deepcopy(old)):
            return old,R.load_pins()

    def test_effective_binding_preserves_all_math(self):
        old,new = self.effective()
        changed = {'sources','input_metadata','raw_tensors','producer_roles'}
        for key in old.keys()-changed:self.assertEqual(old[key],new[key],key)
        for before,after in zip(old['raw_tensors'],new['raw_tensors']):
            self.assertEqual({k:v for k,v in before.items() if k!='path'},
                             {k:v for k,v in after.items() if k!='path'})
        for key,before in old['producer_roles'].items():
            self.assertEqual({k:v for k,v in before.items() if k!='path'},
                             {k:v for k,v in new['producer_roles'][key].items() if k!='path'})
        R.O.check_contract(new)

    def test_no_historical_work_receipts_in_effective_sources(self):
        old,new = self.effective()
        allowed = set(R.INPUT_PATHS.values())
        self.assertFalse(any(p.startswith('work/') and not p.startswith('work/runtime_recovery/') and p not in allowed for p in new['sources']))
        self.assertEqual(len(new['model_ast_nodes']),38)
        self.assertEqual(len(new['activation_ast_nodes']),14)

    def test_unlisted_historical_source_cannot_be_silently_dropped(self):
        pins = R.O.load_pins()
        pins['sources']['work/unreviewed/extra.json'] = dict(bytes=1,sha256='0'*64)
        with patch.object(R,'bindings',return_value={}),patch.object(R,'runtime_pins',return_value=pins):
            with self.assertRaisesRegex(R.Rejected,'exclusion inventory'):R.load_pins()

    def test_historical_source_identity_must_match_code_pinned_original(self):
        pins = R.O.load_pins()
        path = sorted(R.HISTORICAL_WORK_SOURCES)[0]
        pins['sources'][path] = dict(bytes=1,sha256='0'*64)
        with patch.object(R,'bindings',return_value={}),patch.object(R,'runtime_pins',return_value=pins):
            with self.assertRaisesRegex(R.Rejected,'historical source identity'):R.load_pins()

    def test_oracle_reader_has_no_full_tail_reader(self):
        tree = ast.parse((HERE/'recipe.py').read_text())
        node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='metadata_check')
        calls = [n.func.attr for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertIn('input_metadata',calls)
        for forbidden in ('audit_raw','read_new','materialize','read_subset'):self.assertNotIn(forbidden,calls)

    def test_unchanged_original_limits(self):
        L = R.legacy('lifecycle.py')
        self.assertEqual((L.WALL_SECONDS,L.RSS_BYTES,L.LOG_RETAIN_BYTES,L.LOG_EMITTED_LIMIT,L.POLL_SECONDS),
                         (120,1536*(1<<20),65536,16*(1<<20),0.02))

    def test_lifecycle_review_requires_new_bindings(self):
        source = (HERE/'lifecycle.py').read_text()
        self.assertIn("'independent CI source-policy review'",source)
        self.assertIn('ci_binding_policy=recipe.bootstrap_policy()',source)
        self.assertIn('observed_bindings_independently_reviewed=False',source)
        self.assertIn("'maximum_invocations','no_retry','exclusive_numeric_slot'",source)

    def test_no_receipt_generation_in_source(self):
        tree = ast.parse((HERE/'recipe.py').read_text())
        constants = {n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
        self.assertNotIn('APPROVED_SOURCE_FOR_SINGLE_BOOTSTRAP',constants)
        self.assertNotIn('FROZEN_FROM_INDEPENDENT_REVIEW',constants)
        self.assertNotIn('APPROVED_FOR_FREEZE',constants)

if __name__ == '__main__':unittest.main()
