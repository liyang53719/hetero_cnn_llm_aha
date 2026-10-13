"""Bounded synthetic actual one-RMS/two-N32 control, not official calibration."""
import time,unittest
from dataclasses import replace
from . import driver as d
from ..qwen35_35b_prefill import test_prefix_driver as original
setUpModule=original.setUpModule

class AbDriverTests(unittest.TestCase):
    setUpClass=classmethod(original.PrefixTests.setUpClass.__func__)
    setUp=original.PrefixTests.setUp
    def run_ab(self,**kwargs):
        return d.execute_ab(self.hidden,self.weight,dict(a=self.nk[:131072],b=self.nk[131072:262144]),
            tokens=16,profiles={n:replace(self.profile,identity='synthetic_separate_n32_'+n) for n in ('a','b')},
            matrix=self.matrix,vector=self.vector,deadline=time.monotonic()+45,**kwargs)
    def test_same_actual_rms_two_n32_terminals_fixed_resources(self):
        seen=[];report,memory=self.run_ab(observe=lambda *x:seen.append(x))
        self.assertEqual([x[0] for x in seen],['input_norm','a','b'])
        self.assertEqual(report['status'],'PASS_TYPED_AB_EXECUTION_ONLY')
        self.assertTrue(report['actual_rms_region_consumed_by_both'])
        self.assertEqual(report['matrix_service']['dense_fma_calls'],16777216)
        self.assertEqual(len(report['terminals']),3)
        self.assertFalse(report['combined_ab_tensor_materialized'])
        for stage in report['stages'][1:]:
            self.assertEqual(stage['report']['input_sha256'][0],report['actual_rms_output_sha256'])
        self.assertEqual(len([r for r in memory.regions.values() if not r.readonly and r.published]),3)
        self.assertIsNone(self.matrix.owner);self.assertIsNone(self.vector.client)
    def test_a_final_ack_error_blocks_b(self):
        def controls(stage,i,driver):
            if stage!='a':return {}
            return dict(ack_error=driver.pending_ack is not None and driver.counts['write_data_bytes']==driver.job.write_bytes)
        report,memory=self.run_ab(controls=controls)
        self.assertEqual(report['status'],'FAILED');self.assertEqual(report['failed_stage'],'a')
        self.assertEqual(len(report['terminals']),2)
        self.assertEqual(len([r for r in memory.regions.values() if not r.readonly and r.published]),1)
    def test_b_interruption_retains_inflight_evidence(self):
        def controls(stage,i,driver):
            if stage=='b' and driver.pending_ack is not None:raise TimeoutError('bounded B test interruption')
            return {}
        with self.assertRaises(d.PrefixExecutionError) as error:self.run_ab(controls=controls)
        self.assertEqual(error.exception.snapshot['stage'],'b')
        self.assertFalse(error.exception.snapshot['output_published'])
        self.assertEqual(len(error.exception.execution_report['terminals']),2)
        self.assertEqual(len(error.exception.partial_output),1024)
