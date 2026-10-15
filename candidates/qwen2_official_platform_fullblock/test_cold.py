"""Real cold imports/source lineage, explicit admission and metadata boundaries."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from . import closure,recipe as R,job,gates,comparator
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


class ColdTests(unittest.TestCase):
    def test_exact_source_derived_files(self):
        proof=json.loads((HERE/'DERIVATION.json').read_bytes())
        for name,record in proof['files'].items():
            raw=(ROOT/record['source']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),record['sha256'])
            text=raw.decode()
            for replacement in record['replacements']:
                self.assertEqual(text.count(replacement['before']),replacement['count'])
                text=text.replace(replacement['before'],replacement['after'])
            self.assertEqual((HERE/name).read_text(),text,name)

    def test_run_body_only_binding_changes(self):
        old=ast.parse((ROOT/'candidates/qwen2_fullblock_ci_dut/runner.py').read_text())
        new=ast.parse((HERE/'runner.py').read_text())
        def function(tree,name):return next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        # The entire actual numerical run and its fixed schedule are unchanged.
        self.assertEqual(ast.dump(function(old,'run'),include_attributes=False),ast.dump(function(new,'run'),include_attributes=False))
        for module in ('tail','statistics','runtime_adapter'):
            self.assertIn('from candidates.qwen2_fullblock_ci_dut import '+module,(HERE/'runner.py').read_text())

    def test_native_verifier_preserved(self):
        old=ast.parse((ROOT/'candidates/qwen2_fullblock_ci_dut/recipe.py').read_text())
        new=ast.parse((HERE/'recipe.py').read_text())
        def function(tree,name):return next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        self.assertEqual(ast.dump(function(old,'_native_binding'),include_attributes=False),ast.dump(function(new,'_native_binding'),include_attributes=False))

    def test_real_closure_includes_all_executed_sources(self):
        files=closure.source_manifest()
        self.assertGreaterEqual(len(files),350)
        for path in (closure.WORKFLOW,closure.CACHE+'/compare.py',
            'candidates/qwen2_fullblock_ci_dut/platform_freeze.py',
            'candidates/qwen2_fullblock_ci_dut/runtime_adapter.py',
            'candidates/qwen2_resident_matrix/ffn_public/fullgraph_numerical_receipt.json'):
            self.assertIn(path,files)
        self.assertFalse(any(p.startswith('work/') and not p.startswith('work/runtime_recovery/') for p in files))
        self.assertFalse(any('authorization/' in p for p in files))

    def test_cold_actual_entry_imports_no_tensor_runtime(self):
        code='from candidates.qwen2_official_platform_fullblock import runner,recipe,job; import sys; assert not any(x.split(".")[0] in ("numpy","torch","transformers") for x in sys.modules); print("COLD")'
        result=subprocess.run([sys.executable,'-B','-c',code],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'COLD')

    def test_default_runner_is_actual_cold_entry(self):
        result=subprocess.run([sys.executable,'-B',str(HERE/'runner.py')],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout);self.assertEqual(value['status'],'NOT_EXECUTED')
        self.assertIs(value['actual_execution_authorized'],False)

    def test_pair_runtime_real_adapter_loads(self):
        r,l=R.P.runtime()
        self.assertEqual(Path(r.__file__).resolve(),ROOT/'candidates/qwen2_official_cpu_platform_reference/recipe.py')
        self.assertEqual(Path(l.__file__).resolve(),ROOT/'candidates/qwen2_official_cpu_platform_reference/lifecycle.py')

    def test_no_default_binding_or_authority(self):
        with patch.object(R,'load_pins',side_effect=AssertionError('unexpected input read')):
            self.assertEqual(R.bind_pair()['status'],'NOT_EXECUTED')
        with self.assertRaises(ValueError):job.authorize()
        with patch.object(job,'authorize',side_effect=ValueError('missing external approval')),patch.object(job.subprocess,'run') as run:
            with self.assertRaises(ValueError):job.actual()
            run.assert_not_called()

    def test_actual_uses_only_successful_binder_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);calls=[]
            def run(args,**kwargs):
                calls.append((args,os.getenv(R.BINDING_ENV)))
                return type('Done',(),{'returncode':0})()
            bound=dict(status=R.STATUS,reference_outputs_checked=29,policy_conditions_satisfied=True,binding_sha256='a'*64)
            with patch.object(job,'ROOT',root),patch.object(job,'authorize',return_value={'source_closure_sha256':'b'*64}),\
                patch.object(job,'bind',return_value=bound),patch.object(job.subprocess,'run',side_effect=run),patch.dict(os.environ,{},clear=False):
                self.assertEqual(job.actual(),'ACTUAL_PROCESS_COMPLETED_REQUIRES_AGGREGATE')
            self.assertEqual(len(calls),2);self.assertTrue(all(pin=='a'*64 for _,pin in calls))

    def test_bind_failure_prevents_any_dut_subprocess(self):
        with patch.object(job,'authorize',return_value={}),patch.object(job,'bind',side_effect=ValueError('pair mismatch')),\
             patch.object(job.subprocess,'run') as run:
            with self.assertRaises(ValueError):job.actual()
            run.assert_not_called()

    def test_no_old_expected_output_gate(self):
        source=(HERE/'recipe.py').read_text()
        self.assertNotIn('source_expectations(',source)
        self.assertNotIn('fixed_expectations_match',source)
        self.assertIn('P.compare_pair(receipts)',source)
        self.assertIn("pair_payload_bytes_equal=True",source)
        self.assertIn('independent_new_numeric_review_claimed=False',source)

class ContextSmokeTests(unittest.TestCase):
    def test_context_uses_real_local_helpers_and_actual_source(self):
        current=closure.digest()
        platform=dict(python={},libpython={},python_version=[3,12,14],scope='synthetic-cold-only')
        native=dict(native_library={},native_receipt={})
        with patch.dict(os.environ,{R.CLOSURE_ENV:current}),patch.object(R,'_platform_observation',return_value=platform) as observe,\
             patch.object(R,'_native_binding',return_value=native) as native_read:
            context=R.execution_context()
        self.assertEqual(context['source_closure_sha256'],current)
        self.assertEqual(observe.call_count,2);native_read.assert_called_once()

if __name__=='__main__':unittest.main()
