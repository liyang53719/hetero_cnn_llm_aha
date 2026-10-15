"""Synthetic receipts demonstrate new cache scope with identical safe summary schema."""
import copy
import unittest
from candidates.qwen2_fullblock_ci_dut.test_aggregate import fixtures as old_fixtures,SHA
from . import aggregate as A


def fixtures():
    report,launch=old_fixtures()
    report.update(cache_contract='sealed-same-live-cold-cache-v1',reference_contract='official-ast-ci-aten-avx2-reference-v1',
        legacy_cross_oracle_contract_pass=False,
        same_run_cache_comparison=dict(scope='COLD_CACHE_IDENTITY_AND_COPY_ONLY',same_live_exact_copy=True,
            official_kv_exact_copy=False,numerical_acceptance_claimed=False,whole_block_acceptance_claimed=False,historical_run_upgraded=False))
    report['official_kv_comparison'].update(official_kv_exact_copy=False,official_numeric_pass=True)
    for row in report['cold_cache_comparisons'].values():row['exact_cold_alias']=False
    row=dict(finite=True,observed_elements=32768,origin='final sealed physical KV subspan',
        metrics=dict(max_abs=0.0078125,mean_abs=0.001),
        verdict=dict(contract='spec/numerical_contract.md:operator',limits=dict(max_abs=0.03125,mean_abs=0.005),passed=True),
        official_numeric_pass=True)
    report['same_run_cache_original_comparisons']={name:copy.deepcopy(row) for name in ('cache_k','cache_v')}
    return report,launch


class AggregateTests(unittest.TestCase):
    def test_new_contract_pass_keeps_old_exact_false(self):
        report,launch=fixtures();snapshot=copy.deepcopy(report)
        summary=A.summarize(report,launch,source_digest=SHA)
        self.assertEqual(summary['status'],'PASS_OFFICIAL_OBSERVED')
        self.assertEqual(report,snapshot)
        self.assertEqual(set(summary),set(A._empty(SHA)))
        self.assertEqual(summary['software_operation_efficiency'],6014828544/6598164480)
        self.assertIsNone(summary['hardware_cycles']);self.assertIsNone(summary['hardware_utilization'])
        self.assertEqual(summary['cache_contract'],'sealed-same-live-cold-cache-v1')
        self.assertEqual(summary['reference_contract'],'official-ast-ci-aten-avx2-reference-v1')
        for key in ('reference_contract','cache_contract'):
            changed=dict(summary);changed[key]='legacy'
            with self.assertRaises(ValueError):A.validate_summary(changed)
        for forbidden in ('same_run_cache_comparison','outputs','shape','sha256','metadata'):
            self.assertNotIn(forbidden,summary)

    def test_old_contract_cannot_gain_new_pass(self):
        report,launch=old_fixtures()
        self.assertEqual(A.summarize(report,launch,source_digest=SHA)['status'],'FAILED')

    def test_each_new_exact_and_numeric_guard_required(self):
        mutations=[lambda r:r.update(cache_contract='old'),lambda r:r.update(reference_contract='old'),
            lambda r:r['same_run_cache_comparison'].update(same_live_exact_copy=False),
            lambda r:r['same_run_cache_comparison'].update(numerical_acceptance_claimed=True),
            lambda r:r['same_run_cache_comparison'].update(official_kv_exact_copy=True),
            lambda r:r['official_kv_comparison'].update(official_numeric_pass=False),
            lambda r:r['same_run_cache_original_comparisons']['cache_k'].update(official_numeric_pass=False),
            lambda r:r['same_run_cache_original_comparisons']['cache_k']['verdict']['limits'].update(max_abs=0.05),
            lambda r:r['same_run_cache_original_comparisons']['cache_v']['metrics'].update(mean_abs=0.005000000000000001),
            lambda r:r['same_run_cache_original_comparisons']['cache_v'].update(finite=False),
            lambda r:r['same_run_cache_original_comparisons']['cache_v'].update(observed_elements=32767)]
        for mutate in mutations:
            report,launch=fixtures();mutate(report)
            self.assertEqual(A.summarize(report,launch,source_digest=SHA)['status'],'FAILED')

    def test_original_producer_attention_tail_guards_retained(self):
        for field,names in [('producer_comparisons',('n0','qr','q','kr','k','v')),
            ('attention_comparisons',('scores','logits','prob','pv','att')),
            ('tail_comparisons',('o','r','n1','gate','up','silu','act','down','y'))]:
            for name in names:
                report,launch=fixtures();report[field][name]['official_numeric_pass']=False
                self.assertEqual(A.summarize(report,launch,source_digest=SHA)['status'],'FAILED')

    def test_failed_original_cache_verdict_remains_executed(self):
        report,launch=fixtures();row=report['same_run_cache_original_comparisons']['cache_v']
        row['metrics']['mean_abs']=0.005000000000000001;row['verdict']['passed']=False;row['official_numeric_pass']=False
        summary=A.summarize(report,launch,source_digest=SHA)
        self.assertEqual(summary['status'],'FAILED');self.assertIs(summary['official_reference_comparison_executed'],True)

if __name__=='__main__':unittest.main()
