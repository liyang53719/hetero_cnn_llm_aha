"""Synthetic local receipts only; no numerical run, CI, private output or upload."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from candidates.qwen2_fullblock_ci_dut import aggregate as A

SHA='a'*64


def fixtures():
    identity={name:1 for name in A.IDENTITIES};identity['physical_buffers']={'private':2}
    host=dict(launch_result=dict(status=None,completed=21,jobs=17,useful_macs=6014828544,executed_macs=6598164480),
        accepted=dict(completion_fire=21,request_fire=17,owner_result_fire=17,result_fire=1),
        completions=[dict(pc=i,status=None) for i in range(21)],events=list(range(22)),
        reset_required=False,same_owner_and_banks=True)
    execution=dict(status='PUBLIC21_PC0_20_SOFTWARE_EXECUTED',host=host,same_owner_and_banks=True,
        same_physical_memory_and_services=True,full_block_executed=True,full_block_software_model_executed=True,
        reference_arithmetic_executed=False,rtl_executed=False)
    report=dict(schema=1,status=A.PASS,reviewed_source_manifest=SHA,execution=execution,
        acceptance_sealed=True,official_observed_node_pass=True,fullblock_pass=True,whole_block_terminal=True,
        finalfence=True,actual_outputs_sealed=True,old_pass_inherited=False,historical_approval_inherited=False,
        source_sha256_before={'source':'b'*64},source_sha256_after={'source':'b'*64},
        same_live_identity_initial=copy.deepcopy(identity),same_live_identity_at_pc12=copy.deepcopy(identity),
        same_live_identity_final=copy.deepcopy(identity),backend_debts={k:False for k in A.DEBTS},
        host_wall_seconds=1300.,host_cpu_seconds=1290.,peak_rss_kib=1000000,rtl_executed=False,
        full_29_node_acceptance=False,full_official_forward_executed=False,hardware_cycles=None,
        hardware_utilization=None,model_ticks_are_hardware_cycles=False,
        whole_schedule_prediction_and_observation=dict(actual_useful_macs=6014828544,actual_executed_macs=6598164480))
    report['producer_comparisons']={n:dict(official_numeric_pass=n not in {'qraw','kraw','vraw'})
        for n in ('n0','qr','q','kr','k','v','qraw','kraw','vraw')}
    for name in ('qraw','kraw','vraw'):report['producer_comparisons'][name]['official_numeric_pass']=None
    report['attention_comparisons']={n:dict(official_numeric_pass=True) for n in ('scores','logits','prob','pv','att')}
    report['attention_comparisons']['softmax_fp32']=dict(official_numeric_pass=None)
    report['tail_comparisons']={n:dict(official_numeric_pass=True) for n in ('o','r','n1','gate','up','silu','act','down','y')}
    report['cold_cache_comparisons']={n:dict(exact_cold_alias=True) for n in ('cache_k','cache_v')}
    report['official_kv_comparison']=dict(official_kv_exact_copy=True)
    report['softmax_probability_sum']=dict(passed=True)
    launch=dict(schema=1,status='PASS',returncode=0,cleanup_incomplete=False,failure_kind=None,
        acceptance_sealed=True,fullblock_pass=True,accepted_final_launch_result=True,child_status=A.PASS,
        old_pass_inherited=False,automatic_retry=False,reviewed_source_manifest=SHA,elapsed_seconds=1301.,
        peak_sampled_process_group_rss_bytes=1200000000,final_output_bytes=100000000,final_log_bytes=100)
    return report,launch


class AggregateTests(unittest.TestCase):
    def test_default_no_io(self):
        with patch.object(A.closure,'digest',side_effect=AssertionError('source read')),\
             patch.object(A,'_read',side_effect=AssertionError('receipt read')):
            self.assertEqual(A.collect(),dict(status='NOT_EXECUTED',numeric_execution_allowed=False))
            for execute in ('yes',1,None):
                with self.assertRaises(ValueError):A.collect(execute=execute)

    def test_synthetic_pass_safe_aggregate(self):
        report,launch=fixtures();summary=A.summarize(report,launch,source_digest=SHA)
        self.assertEqual(summary['status'],'PASS_OFFICIAL_OBSERVED')
        self.assertEqual(summary['public_completions'],21)
        self.assertEqual(summary['owner_jobs'],17)
        self.assertEqual(summary['accepted_launch_results'],1)
        self.assertEqual(summary['software_operation_efficiency'],6014828544/6598164480)
        self.assertEqual(summary['efficiency_kind'],'SOFTWARE_OPERATION_EFFICIENCY')
        for field in ('hardware_cycles','hardware_utilization','hardware_duty'):self.assertIsNone(summary[field])
        self.assertFalse(summary['reference_arithmetic_executed'])
        self.assertTrue(summary['dut_software_executed'])
        self.assertFalse(summary['rtl_executed'])
        A.validate_summary(summary)

    def test_each_terminal_guard_required(self):
        mutations=[lambda r,l:r.update(status='STARTED'),lambda r,l:l.update(status='STARTED'),
            lambda r,l:l.update(returncode=False),lambda r,l:l.update(returncode=1),
            lambda r,l:l.update(cleanup_incomplete=True),lambda r,l:l.update(failure_kind='SAMPLED_RSS_CAP'),
            lambda r,l:l.update(accepted_final_launch_result=False),lambda r,l:l.update(automatic_retry=True),
            lambda r,l:r.update(finalfence=False),lambda r,l:r.update(whole_block_terminal=False),
            lambda r,l:r.update(actual_outputs_sealed=False),lambda r,l:r.update(acceptance_sealed=False),
            lambda r,l:r.update(official_observed_node_pass=False),lambda r,l:r.update(fullblock_pass=False),
            lambda r,l:r.update(schema=True),lambda r,l:r.update(old_pass_inherited=True),
            lambda r,l:r.update(reviewed_source_manifest='c'*64),lambda r,l:l.update(reviewed_source_manifest='c'*64),
            lambda r,l:r.update(source_sha256_after={}),lambda r,l:r.update(full_29_node_acceptance=True),
            lambda r,l:r.update(hardware_cycles=1)]
        for mutate in mutations:
            r,l=fixtures();mutate(r,l)
            with self.subTest(mutate=mutate):self.assertNotEqual(A.summarize(r,l,source_digest=SHA)['status'],'PASS_OFFICIAL_OBSERVED')

    def test_completion_debt_and_same_live_guards(self):
        mutations=[lambda r:r['execution']['host']['launch_result'].update(completed=20),
            lambda r:r['execution']['host']['accepted'].update(result_fire=0),
            lambda r:r['execution']['host']['accepted'].update(request_fire=16),
            lambda r:r['execution']['host']['completions'][0].update(status='error'),
            lambda r:r['execution']['host']['completions'][0].update(pc=False),
            lambda r:r['execution']['host'].update(events=[]),
            lambda r:r.update(backend_debts={}),lambda r:r['backend_debts'].update(workspace_seed=1),
            lambda r:r['backend_debts'].update(workspace_seed=''),lambda r:r['backend_debts'].pop('accepted_write'),
            lambda r:r.update(same_live_identity_initial={}),
            lambda r:r['same_live_identity_final'].update(owner=2),
            lambda r:r['same_live_identity_at_pc12'].update(owner=True)]
        for mutate in mutations:
            r,l=fixtures();mutate(r)
            with self.subTest(mutate=mutate):self.assertEqual(A.summarize(r,l,source_digest=SHA)['status'],'FAILED')

    def test_failed_comparison_still_reported_as_executed(self):
        r,l=fixtures();r['tail_comparisons']['y']['official_numeric_pass']=False
        r['status']='FAIL_M128_OFFICIAL_OBSERVED_CONTRACT';l['status']='FAILED'
        summary=A.summarize(r,l,source_digest=SHA)
        self.assertEqual(summary['status'],'FAILED')
        self.assertTrue(summary['official_reference_comparison_executed'])
        self.assertEqual(summary['useful_macs'],6014828544)

    def test_mac_consistency_and_resource_bounds(self):
        for bad in (True,-1,float('nan'),float('inf'),2**54,'private'):
            r,l=fixtures();r['host_wall_seconds']=bad
            summary=A.summarize(r,l,source_digest=SHA)
            self.assertEqual(summary['status'],'FAILED');self.assertIsNone(summary['host_wall_seconds'])
        for target,key,bad in (('r','host_wall_seconds',3301),('l','elapsed_seconds',3331),
            ('l','peak_sampled_process_group_rss_bytes',3221225473),('l','final_output_bytes',1073741825),
            ('l','final_log_bytes',16777217)):
            r,l=fixtures();(r if target=='r' else l)[key]=bad
            self.assertEqual(A.summarize(r,l,source_digest=SHA)['status'],'FAILED')
        r,l=fixtures();r['execution']['host']['launch_result']['useful_macs']=7000000000
        result=A.summarize(r,l,source_digest=SHA)
        self.assertEqual(result['status'],'FAILED');self.assertIsNone(result['software_operation_efficiency'])

    def test_private_values_never_projected(self):
        r,l=fixtures();r.update(status='FAILED',failure_stage='/private/token',original_error_type='private.Exception',
            error='PRIVATESECRET',traceback='PRIVATESECRET',private_shape=[1,2],output_sha256='c'*64)
        l.update(status='FAILED',argv=['PRIVATESECRET'],supervisor_error='PRIVATESECRET')
        summary=A.summarize(r,l,source_digest=SHA);text=json.dumps(summary)
        for private in ('PRIVATESECRET','/private','private.Exception','private_shape','c'*64,'producer_comparisons','physical_buffers'):
            self.assertNotIn(private,text)
        self.assertEqual(summary['failure_stage'],'UNKNOWN');self.assertEqual(summary['exception_class'],'UNKNOWN')
        r.update(failure_stage='attention',original_error_type='MemoryError')
        summary=A.summarize(r,l,source_digest=SHA)
        self.assertEqual(summary['failure_stage'],'ATTENTION_EXECUTION');self.assertEqual(summary['exception_class'],'MemoryError')

    def test_missing_receipts_and_filename_only_never_pass(self):
        for r,l in (({},{}),({},dict(status='PASS')),(dict(status=A.PASS),dict(status='PASS'))):
            self.assertNotEqual(A.summarize(r,l,source_digest=SHA)['status'],'PASS_OFFICIAL_OBSERVED')

    def test_collect_fixed_inputs_source_before_after_and_read_failure(self):
        with patch.object(A,'ROOT',A.CI_ROOT),patch.object(A.closure,'digest',return_value=SHA) as source,\
             patch.object(A,'_read',side_effect=fixtures()) as read:
            self.assertEqual(A.collect(execute=True,source_digest=SHA)['status'],'PASS_OFFICIAL_OBSERVED')
            self.assertEqual([c.args[0] for c in read.call_args_list],[A.RESULT,A.LAUNCH])
            self.assertEqual(source.call_count,2)
        with patch.object(A,'ROOT',A.CI_ROOT),patch.object(A.closure,'digest',return_value=SHA),\
             patch.object(A,'_read',side_effect=FileNotFoundError('/SECRET')):
            result=A.collect(execute=True,source_digest=SHA)
            self.assertEqual(result['status'],'INCOMPLETE');self.assertNotIn('SECRET',json.dumps(result))
        with patch.object(A,'ROOT',A.CI_ROOT),patch.object(A.closure,'digest',side_effect=[SHA,'b'*64]),\
             patch.object(A,'_read',side_effect=fixtures()):
            with self.assertRaisesRegex(ValueError,'source closure changed'):A.collect(execute=True,source_digest=SHA)
        with patch.object(A,'ROOT',A.CI_ROOT),patch.object(A.closure,'digest',return_value='b'*64),\
             patch.object(A,'_read',side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError,'source closure drift'):A.collect(execute=True,source_digest=SHA)

    def test_read_duplicate_nonfinite_alias_and_plain_json(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(A,'ROOT',Path(directory)):
            path=Path(directory)/'fixture.json'
            for raw in ('{"x":1,"x":2}','{"x":NaN}','[]'):
                path.write_text(raw)
                with self.assertRaises(ValueError):A._read('fixture.json')
            path.write_text('{"x":1}')
            self.assertEqual(A._read('fixture.json'),{'x':1})
            alias=Path(directory)/'alias.json';alias.symlink_to(path)
            with self.assertRaisesRegex(ValueError,'alias'):A._read('alias.json')

    def test_exact_output_schema_rejects_injected_details(self):
        summary=A.summarize(*fixtures(),source_digest=SHA)
        for field,value in (('private_path','secret'),('hardware_cycles',1),('hardware_duty',.5),
                            ('public_completions',True),('software_operation_efficiency',float('nan'))):
            changed=copy.deepcopy(summary);changed[field]=value
            with self.assertRaises(ValueError):A.validate_summary(changed)


if __name__=='__main__':unittest.main()
