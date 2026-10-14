import contextlib
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from . import gates,runner


class CostColdTests(unittest.TestCase):
    def test_default_never_loads_numeric_or_stimuli(self):
        stream=io.StringIO()
        with patch.object(runner,'setup_dependencies',side_effect=AssertionError('native setup forbidden')), \
             patch.object(gates,'load_inputs',side_effect=AssertionError('input read forbidden')),contextlib.redirect_stdout(stream):
            self.assertEqual(runner.main([]),0)
        value=json.loads(stream.getvalue())
        self.assertEqual(value['status'],'NOT_EXECUTED')
        self.assertFalse(value['numerical_acceptance'] or value['actual_execution_authorized'])

    def test_review_refusal_precedes_input_loading(self):
        for value in (None,'','0'*64):
            with patch.object(gates,'load_inputs',side_effect=AssertionError('input read forbidden')):
                with self.assertRaises(ValueError):runner.run(gates.OUTPUT_ROOT/'not_admitted',reviewed_source_manifest=value)
        self.assertFalse((gates.OUTPUT_ROOT/'not_admitted').exists())

    def test_original_driver_and_no_fullchain_claims(self):
        source=(gates.HERE/'runner.py').read_text()
        self.assertIn('driver.execute_dense(original.numeric.model,owner,bridge,memory,job,out,deadline,trace,',source)
        self.assertNotIn('owner_tick=',source)
        self.assertNotIn('PV32PublicExecution',source)
        self.assertNotIn('publish_completions',source)
        self.assertIn("service.bind_dense_job(job,'dense_o')",source)
        self.assertIn('fullblock_runtime_bound_established=False',source)
        self.assertIn('service.retire_owner_response(owner);service.release(owner)',source)

    def test_real_initialized_original_O_service(self):
        argv=[sys.executable,'-B']
        if sys.flags.optimize:argv.append('-O')
        argv += [str(gates.HERE/'controls.py'),'--initialized-only']
        r=subprocess.run(argv,cwd=gates.ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        v=json.loads(r.stdout)
        self.assertEqual(v['status'],'PASS_REAL_INITIALIZED_O_CONTROL_ONLY')
        self.assertEqual(v['matrix_dense_fma'],0)
        self.assertEqual(v['owner_ticks'],0)
        self.assertTrue(v['original_OfficialDenseLibraryAdapter'])
        self.assertTrue(v['retained_cold_debts']['matrix_owned'])
        self.assertFalse(v['model_inputs_loaded'] or v['numerical_acceptance'] or v['terminal_fabricated'])
        self.assertGreaterEqual(len(v['negative_controls']),12)


if __name__=='__main__':unittest.main()
