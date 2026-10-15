"""Cold receipt-only tests: unchanged acceptance and fixed safe diagnostics."""
import ast
import copy
import hashlib
import inspect
import json
import unittest
from unittest.mock import patch
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


def diagnostic_fixtures():
    report,launch=fixtures()
    for index,(stage,path,flag,metric_path) in enumerate(A.NODE_SPECS):
        row=report
        for key in path:row=row[key]
        if stage=='SOFTMAX_SUM':
            row['max_abs']=0.00001
        elif path[0]!='same_run_cache_original_comparisons':
            row['metrics']=dict(max_abs=0.001+index/100000,mean_abs=0.0001+index/1000000)
    return report,launch


def change(path,value,delete=False):
    def mutate(report,launch):
        obj={'report':report,'launch':launch}[path[0]]
        for key in path[1:-1]:obj=obj[key]
        if delete:del obj[path[-1]]
        else:obj[path[-1]]=value
    return mutate


class AcceptanceDiagnosticTests(unittest.TestCase):
    def summary(self,report,launch):
        return A.summarize(report,launch,source_digest=SHA)

    def test_original_total_pass_expression_is_frozen(self):
        tree=ast.parse(inspect.getsource(A.summarize))
        expression=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and
            any(isinstance(t,ast.Name) and t.id=='passed' for t in n.targets))
        digest=hashlib.sha256(ast.dump(expression,include_attributes=False).encode()).hexdigest()
        self.assertEqual(digest,'916f9c8cd71e94acc2c24fde1769c9ffa870513140b1d60c7d5c4dc1e044056c')

    def test_exact_24_node_schema_and_original_metrics_only(self):
        report,launch=diagnostic_fixtures();before=copy.deepcopy((report,launch))
        summary=self.summary(report,launch);diagnostics=summary['acceptance_diagnostics']
        expected=('PRODUCER_N0','PRODUCER_QR','PRODUCER_Q','PRODUCER_KR','PRODUCER_K','PRODUCER_V',
            'ATTENTION_SCORES','ATTENTION_LOGITS','ATTENTION_PROB','ATTENTION_PV','ATTENTION_ATT',
            'TAIL_O','TAIL_R','TAIL_N1','TAIL_GATE','TAIL_UP','TAIL_SILU','TAIL_ACT','TAIL_DOWN','TAIL_Y',
            'CACHE_K','CACHE_V','OFFICIAL_KV','SOFTMAX_SUM')
        self.assertEqual(tuple(n['stage'] for n in diagnostics['nodes']),expected)
        self.assertEqual(summary['status'],'PASS_OFFICIAL_OBSERVED')
        self.assertEqual(diagnostics['failure_stages'],[])
        self.assertEqual((report,launch),before)
        for node,(_,path,flag,metric_path) in zip(diagnostics['nodes'],A.NODE_SPECS):
            row=A._field(report,path);metrics=A._field(row,metric_path)
            self.assertIs(node['official_numeric_pass'],row[flag])
            self.assertEqual(node['max_abs'],metrics['max_abs'])
            self.assertEqual(node['mean_abs'],None if node['stage']=='SOFTMAX_SUM' else metrics['mean_abs'])
        self.assertEqual(sum(map(len,diagnostics['gates'].values())),120)
        self.assertTrue(all(v is True for group in diagnostics['gates'].values() for v in group.values()))

    def test_numeric_failure_and_launch_failure_are_distinct(self):
        report,launch=diagnostic_fixtures();report['tail_comparisons']['y']['official_numeric_pass']=False
        numeric=self.summary(report,launch)
        report,launch=diagnostic_fixtures();launch['acceptance_sealed']=False
        launch_failed=self.summary(report,launch)
        for summary in (numeric,launch_failed):
            self.assertEqual(summary['status'],'FAILED')
            self.assertTrue(summary['official_reference_comparison_executed'])
        self.assertEqual(numeric['acceptance_diagnostics']['failure_stages'],['NUMERIC'])
        self.assertIs(numeric['acceptance_diagnostics']['gates']['NUMERIC']['TAIL_Y'],False)
        self.assertEqual(launch_failed['acceptance_diagnostics']['failure_stages'],['LAUNCH'])
        self.assertIs(launch_failed['acceptance_diagnostics']['gates']['LAUNCH']['ACCEPTANCE_SEALED'],False)
        self.assertTrue(all(n['official_numeric_pass'] for n in launch_failed['acceptance_diagnostics']['nodes']))

    def test_every_direct_acceptance_gate_has_failure_and_missing_evidence(self):
        for group,gate,receipt,path,expected in A.DIRECT_GATES:
            if receipt=='summary':
                target=('report','execution','host','launch_result',path[0])
            else:target=(receipt,*path)
            bad=(not expected if type(expected) is bool else expected+1 if type(expected) is int else 'PRIVATE_VALUE')
            for delete in (False,True):
                report,launch=diagnostic_fixtures();change(target,bad,delete)(report,launch)
                with self.subTest(group=group,gate=gate,delete=delete):
                    summary=self.summary(report,launch);diagnostics=summary['acceptance_diagnostics']
                    self.assertNotEqual(summary['status'],'PASS_OFFICIAL_OBSERVED')
                    self.assertIs(diagnostics['gates'][group][gate],None if delete else False)
                    self.assertIn(group,diagnostics['failure_stages'])
                    self.assertNotIn('PRIVATE_VALUE',json.dumps(summary,allow_nan=False))

    def test_each_numeric_node_failure_and_missing_flag_remain_unaccepted(self):
        for stage,path,flag,_ in A.NODE_SPECS:
            for delete in (False,True):
                report,launch=diagnostic_fixtures();change(('report',*path,flag),False,delete)(report,launch)
                # A failed cache verdict remains structurally complete when its
                # existing metrics/verdict agree; do not recompute them here.
                if path[0]=='same_run_cache_original_comparisons' and not delete:
                    row=A._field(report,path);row['metrics']['max_abs']=0.04;row['verdict']['passed']=False
                with self.subTest(stage=stage,delete=delete):
                    summary=self.summary(report,launch);diagnostics=summary['acceptance_diagnostics']
                    self.assertEqual(summary['status'],'FAILED')
                    self.assertIs(diagnostics['gates']['NUMERIC'][stage],None if delete else False)
                    self.assertIn('NUMERIC',diagnostics['failure_stages'])
                    if not delete:
                        self.assertTrue(summary['official_reference_comparison_executed'])
                        self.assertEqual(diagnostics['failure_stages'],['NUMERIC'])

    def test_all_compound_predicates_have_specific_fixed_failure_gates(self):
        cases=[
            ('SOURCE','UNCHANGED_RECORDS',('report','source_sha256_after'),{}),
            ('HOST','COMPLETION_SEQUENCE',('report','execution','host','completions'),[]),
            ('HOST','EVENT_SEQUENCE',('report','execution','host','events'),[]),
            ('LIVE','IDENTITY_CHAIN',('report','same_live_identity_at_pc12'),{}),
            ('LIVE','DEBTS_CLEAR',('report','backend_debts'),{}),
            ('COMPARISON','PRODUCER_STRUCTURE',('report','producer_comparisons','PRIVATE_KEY'),{}),
            ('COMPARISON','ATTENTION_STRUCTURE',('report','attention_comparisons','PRIVATE_KEY'),{}),
            ('COMPARISON','TAIL_STRUCTURE',('report','tail_comparisons','PRIVATE_KEY'),{}),
            ('COMPARISON','PRODUCER_DIAGNOSTIC_ONLY',('report','producer_comparisons','qraw','official_numeric_pass'),True),
            ('COMPARISON','ATTENTION_DIAGNOSTIC_ONLY',('report','attention_comparisons','softmax_fp32','official_numeric_pass'),True),
            ('COMPARISON','LEGACY_CACHE_STRUCTURE',('report','cold_cache_comparisons','PRIVATE_KEY'),{}),
            ('COMPARISON','LEGACY_CACHE_ALIAS_TYPES',('report','cold_cache_comparisons','cache_k','exact_cold_alias'),1),
            ('COMPARISON','OFFICIAL_KV_COPY_TYPE',('report','official_kv_comparison','official_kv_exact_copy'),1),
            ('COMPARISON','LEGACY_CROSS_ORACLE_FLAG_TYPE',('report','legacy_cross_oracle_contract_pass'),1),
            ('COMPARISON','COPY_STRUCTURE',('report','same_run_cache_comparison','PRIVATE_KEY'),{}),
            ('COMPARISON','OFFICIAL_COPY_AGREEMENT',('report','same_run_cache_comparison','official_kv_exact_copy'),True),
            ('COMPARISON','CACHE_NUMERIC_STRUCTURE',('report','same_run_cache_original_comparisons','PRIVATE_KEY'),{}),
            ('MACS','OBSERVED_USEFUL',('report','whole_schedule_prediction_and_observation','actual_useful_macs'),1),
            ('MACS','OBSERVED_EXECUTED',('report','whole_schedule_prediction_and_observation','actual_executed_macs'),1)]
        for name in ('cache_k','cache_v'):
            base=('report','same_run_cache_original_comparisons',name)
            for gate,path,bad in (
                ('FINITE',('finite',),False),('ELEMENT_COUNT',('observed_elements',),1),
                ('ORIGIN',('origin',),'PRIVATE_VALUE'),('VERDICT_CONTRACT',('verdict','contract'),'PRIVATE_VALUE'),
                ('LIMITS',('verdict','limits'),{}),('VERDICT_AGREEMENT',('verdict','passed'),False),
                ('METRICS_VALID',('metrics','max_abs'),True),('POLICY_AGREEMENT',('metrics','mean_abs'),0.006)):
                cases.append(('COMPARISON',name.upper()+'_'+gate,(*base,*path),bad))
        covered=set()
        for group,gate,path,bad in cases:
            report,launch=diagnostic_fixtures();change(path,bad)(report,launch)
            with self.subTest(group=group,gate=gate):
                summary=self.summary(report,launch);diagnostics=summary['acceptance_diagnostics']
                self.assertEqual(summary['status'],'FAILED')
                self.assertIsNot(diagnostics['gates'][group][gate],True)
                self.assertIn(group,diagnostics['failure_stages'])
                self.assertNotIn('PRIVATE_',json.dumps(summary,allow_nan=False))
                covered.add((group,gate))
        expected={(group,gate) for group,names in A.EXTRA_GATES.items() if group not in ('NUMERIC','RESOURCES') for gate in names}
        self.assertEqual(covered,expected)

    def test_each_resource_presence_and_budget_gate(self):
        paths={'HOST_WALL':('report','host_wall_seconds'),'HOST_CPU':('report','host_cpu_seconds'),
            'SUPERVISOR_WALL':('launch','elapsed_seconds'),'PEAK_RSS':('report','peak_rss_kib'),
            'SAMPLED_GROUP_RSS':('launch','peak_sampled_process_group_rss_bytes'),
            'OUTPUT_BYTES':('launch','final_output_bytes'),'LOG_BYTES':('launch','final_log_bytes')}
        for gate,_,limit in A.RESOURCE_GATES:
            for bad in (None,True,-1,float('nan'),float('inf'),'PRIVATE_VALUE',10**400):
                report,launch=diagnostic_fixtures();change(paths[gate],bad)(report,launch)
                with self.subTest(gate=gate,bad=type(bad).__name__):
                    summary=self.summary(report,launch)
                    self.assertEqual(summary['status'],'FAILED')
                    self.assertIsNone(summary['acceptance_diagnostics']['gates']['RESOURCES'][gate])
                    self.assertIn('RESOURCES',summary['acceptance_diagnostics']['failure_stages'])
            if limit is not None:
                report,launch=diagnostic_fixtures()
                change(paths[gate],limit//1024+1 if gate=='PEAK_RSS' else limit+1)(report,launch)
                summary=self.summary(report,launch)
                self.assertEqual(summary['status'],'FAILED')
                self.assertIs(summary['acceptance_diagnostics']['gates']['RESOURCES'][gate],False)

    def test_missing_receipts_have_explicit_fixed_unknown_gates(self):
        summary=self.summary({},{});diagnostics=summary['acceptance_diagnostics']
        self.assertEqual(summary['status'],'INCOMPLETE')
        self.assertEqual(diagnostics['failure_stages'],list(A.DIAGNOSTIC_GROUPS))
        self.assertTrue(all(v is None for group in diagnostics['gates'].values() for v in group.values()))
        self.assertTrue(all(n['official_numeric_pass'] is None and n['max_abs'] is None and n['mean_abs'] is None
            for n in diagnostics['nodes']))

    def test_invalid_node_metrics_and_flags_are_null_not_coerced(self):
        for stage,path,flag,metric_path in A.NODE_SPECS:
            for metric in ('max_abs','mean_abs'):
                for bad in (True,False,'PRIVATE_VALUE',{'PRIVATE_KEY':'PRIVATE_VALUE'},[],float('nan'),float('inf'),-1,10**400):
                    report,launch=diagnostic_fixtures()
                    change(('report',*path,*metric_path,metric),bad)(report,launch)
                    with self.subTest(stage=stage,metric=metric,bad=type(bad).__name__):
                        summary=self.summary(report,launch);node=next(n for n in summary['acceptance_diagnostics']['nodes'] if n['stage']==stage)
                        self.assertIsNone(node[metric]);self.assertNotIn('PRIVATE_',json.dumps(summary,allow_nan=False))
                        # Optional display metrics never replace the old numeric
                        # acceptance flags. Cache metrics were already required.
                        self.assertEqual(summary['status'],'FAILED' if stage in ('CACHE_K','CACHE_V') else 'PASS_OFFICIAL_OBSERVED')
            for bad in (None,0,1,'PRIVATE_VALUE',[],{}):
                report,launch=diagnostic_fixtures();change(('report',*path,flag),bad)(report,launch)
                summary=self.summary(report,launch)
                self.assertEqual(summary['status'],'FAILED')
                self.assertIsNone(summary['acceptance_diagnostics']['gates']['NUMERIC'][stage])

    def test_undeclared_fields_and_private_metadata_are_never_projected(self):
        report,launch=diagnostic_fixtures()
        secret={'path':'/PRIVATE_VALUE','shape':['PRIVATE_VALUE'],'stride':[999],
            'sha256':'f'*64,'metadata':{'PRIVATE_KEY':'PRIVATE_VALUE'},'traceback':'PRIVATE_VALUE'}
        report.update(secret);launch.update(secret)
        for _,path,_,metric_path in A.NODE_SPECS:
            row=A._field(report,path);row.update(secret)
            if metric_path:row['metrics'].update(secret)
        # Deliberately invalid expected text still emits only false/null gates.
        report['same_run_cache_original_comparisons']['cache_k']['origin']='/PRIVATE_VALUE'
        report['failure_stage']='/PRIVATE_VALUE';report['original_error_type']='PRIVATE_VALUE'
        summary=self.summary(report,launch);serialized=json.dumps(summary,allow_nan=False)
        for text in ('PRIVATE_VALUE','PRIVATE_KEY','f'*64,'shape','stride','metadata','traceback'):
            self.assertNotIn(text,serialized)
        A.validate_summary(summary)

    def test_diagnostics_cannot_promote_original_failure(self):
        good=self.summary(*diagnostic_fixtures())['acceptance_diagnostics']
        report,launch=diagnostic_fixtures();launch['acceptance_sealed']=False
        with patch.object(A,'_acceptance_diagnostics',return_value=good):
            self.assertEqual(self.summary(report,launch)['status'],'FAILED')

    def test_strict_validator_rejects_modified_or_extended_diagnostics(self):
        good=self.summary(*diagnostic_fixtures())
        mutations=[
            lambda d:d.update(PRIVATE_KEY='PRIVATE_VALUE'),lambda d:d.update(schema=True),
            lambda d:d['gates'].update(PRIVATE_KEY={}),lambda d:d['gates']['LAUNCH'].update(PRIVATE_KEY=True),
            lambda d:d['gates']['LAUNCH'].update(STATUS=1),lambda d:d['gates']['LAUNCH'].update(STATUS='PASS'),
            lambda d:d['gates']['LAUNCH'].pop('STATUS'),lambda d:d['nodes'].append(copy.deepcopy(d['nodes'][0])),
            lambda d:d['nodes'][0].update(stage='PRIVATE_VALUE'),lambda d:d['nodes'][0].update(shape=[1]),
            lambda d:d['nodes'][0].update(official_numeric_pass=1),lambda d:d['nodes'][0].update(official_numeric_pass=False),
            lambda d:d['nodes'][0].update(max_abs=True),lambda d:d['nodes'][0].update(max_abs=float('nan')),
            lambda d:d['nodes'][0].update(mean_abs=float('inf')),lambda d:d['nodes'][0].update(max_abs=10**400),
            lambda d:d['nodes'][-1].update(mean_abs=0.0),lambda d:d.update(failure_stages=['PRIVATE_VALUE']),
            lambda d:d.update(failure_stages=['LAUNCH']),lambda d:d['nodes'].reverse()]
        for mutate in mutations:
            value=copy.deepcopy(good);mutate(value['acceptance_diagnostics'])
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):A.validate_summary(value)


if __name__=='__main__':unittest.main()
