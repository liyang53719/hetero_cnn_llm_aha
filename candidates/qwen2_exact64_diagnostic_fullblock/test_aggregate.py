"""Synthetic receipt tests only; no model run, CI, payloads or acceptance claim."""
import ast
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from candidates.qwen2_official_platform_fullblock import aggregate as original
from candidates.qwen2_official_platform_fullblock.test_aggregate import diagnostic_fixtures as original_fixtures, SHA
from . import aggregate as A


def fixtures():
    report,launch=original_fixtures()
    for row in (report,launch):
        row.update(scope='DIAGNOSTIC_SOFTWARE_OWNER',performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',
            fullblock_pass=False,acceptance_sealed=False,chisel_full_prefill_pass=False,
            diagnostic_numeric_pass=True,diagnostic_acceptance_sealed=True)
    report.update(status=A.PASS,model_corresponds_to_current_chisel=False,eda_executed=False,
        local_retention_verified_before_seal=True,local_retention_verified_after_comparison=True)
    launch['child_status']=A.PASS
    identity={k:7 for k in A.DIAGNOSTIC_IDENTITIES};identity['original_a_payload']=[8,9]
    report['diagnostic_identity_initial']=copy.deepcopy(identity);report['diagnostic_identity_final']=copy.deepcopy(identity)
    for field in ('diagnostic_debts_at_pc12','diagnostic_backend_debts'):
        report[field]={k:False for k in A.DIAGNOSTIC_DEBTS}
    records=[]
    for pc,width in ((1,1536),(4,256)):
        elements=128*width;fmas=elements*1536;reads=128*(96+width//64*3072);writes=elements//16
        records.append(dict(scope='DIAGNOSTIC_SOFTWARE_OWNER',performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',
            job=dict(tag=0x70000|pc,m=128,n=width,k=1536),terminal=dict(status=None,useful_macs=fmas,executed_macs=fmas,write_bytes=elements*4),
            kernel_delta=dict(fmas=fmas,adds=elements*64,tiles_started=elements//64),tiles_output_acked=elements//64,
            memory=dict(read_bytes=reads*64,write_bytes=writes*64,read_requests=reads,write_requests=writes,acks=writes),
            matrix_counter_delta=dict(owner_acquires=1,owner_responses=1,owner_releases=1,dense_steps=0,normal_steps=0),
            actual_dense_fma_calls_delta=0,actual_normal_fma_calls_delta=0,partial_bytes=16384,
            final_ack_fence=dict(terminal_strictly_after_final_ack=True,held_ticks=5,final_ack_tick=101,terminal_tick=102),
            driver_counts=dict(job_fire=1,response_fire=1,memory_fire=reads+writes,memory_response_fire=reads+writes,final_ack_stall=5),
            accepted=dict(read_requests=reads,read_responses=reads,write_requests=writes,write_acks=writes,responses=reads+writes,owner_results=1),
            same_owner_and_banks=True,model_ticks_are_hardware_cycles=False,hardware_cycles=None,status=None,write_bytes=elements*4))
    report['exact64_projections']=records
    report['observed_exact64_qk_totals']=copy.deepcopy(A.accounting.EXACT_EXPECTED)
    report['observed_v_totals']=copy.deepcopy(A.accounting.V_EXPECTED)
    expected=A.accounting.WHOLE_EXPECTED
    report['matrix']=dict(counters=dict(dense_steps=expected['dense_steps'],normal_steps=expected['normal_steps']),
        dense_fma_calls=expected['dense_fma'],normal_fma_calls=expected['normal_fma'])
    report['statistics']=dict(full_fixed_array_issued_cell_opportunities=expected['opportunities'])
    report['whole_schedule_prediction_and_observation'].update(predicted=copy.deepcopy(expected),
        observed_tail=dict(dense_steps=1363968,dense_groups=162,dense_results=800,owner_acquires=114,owner_releases=114,dense_seed_acks=144),
        exact64_software=copy.deepcopy(A.accounting.EXACT_EXPECTED),exact64_matrix_stream_steps=0,
        full_fixed_array_opportunities_scope='ORIGINAL_MATRIX_EVENTS_ONLY',exact64_tree_adds_are_macs=False,
        hardware_cycles=None,hardware_utilization=None,performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',scope='DIAGNOSTIC_SOFTWARE_OWNER')
    report['shared_a_route']=dict(active=False,fault=None,shared_payload_identity_unchanged=True,
        same_dense_tile_attention_banks=True,payload_bytearray_allocated=False,production_public_checkpoint_executed=True,
        authority='ACTUAL_PUBLIC_PC9_HANDSHAKES',scope='DIAGNOSTIC_SOFTWARE_OWNER',performance='NO_GO',hardware='NOT_IMPLEMENTED',
        rtl_executed=False,model_edges_are_hardware_cycles=False,loan_events=dict(loans=1,releases=1,edges=100),
        publication=dict(authority='ACTUAL_PUBLIC_PC9_HANDSHAKES',validation='FULL_ENTRY_AND_RELEASE_CONSTANT_SIZE_CONTINUATION',
            original_physical_write_guard=True,counts=dict(full_checks=2,fast_checks=100)))
    spec=dict(bytes=4,sha256='b'*64)
    sealed={n:copy.deepcopy(spec) for n in A.retention.ACTUAL_NAMES|{'silu'}}
    inventory={'actual_'+n+'.f32le':copy.deepcopy(s) for n,s in sealed.items()}
    for name in A.retention.ATTENTION_NAMES:
        for suffix in ('.u32le','.presence','.count.u16le'):
            inventory['attention_observation/'+name+suffix]=copy.deepcopy(spec)
    inventory['attention_observation/summary.json']=copy.deepcopy(spec)
    report['sealed_actual_outputs']=sealed
    report['local_retention']=dict(schema=1,status='LOCAL_ACTUALS_RETAINED_BEFORE_ORACLE',scope='DIAGNOSTIC_SOFTWARE_OWNER',
        local_only=True,upload_authorized=False,oracle_payloads_read=False,reference_operands_in_execution=False,
        propagation_inputs_retained=['v','att','o','r','n1','gate','up'],inventory=inventory)
    postseal=dict(schema=1,status='POSTSEAL_GATE_DIAGNOSTIC_COMPLETE',scope='POSTSEAL_GATE_ERROR_ISOLATION_ONLY',
        performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',fullblock_pass=False,
        original_diagnostic_numeric_pass=True,official_gate_invocations=2,control_bit_exact=True,
        local_only=True,upload_authorized=False,resource_limits=copy.deepcopy(A.POSTSEAL_LIMITS),
        source_closure_sha256=SHA,comparison_order=list(A.POSTSEAL_STAGES),
        same_actual_seal_verified=True,same_fresh_reference_verified=True,same_runtime_verified=True,
        native_metric_authority='scripts/qwen2_layer0_model_gate.py:compare/stage_verdict',
        original_numerical_policy=dict(operator=dict(max_abs=0.03125,mean_abs=0.005)),
        host_wall_seconds=10.,host_cpu_seconds=9.,peak_rss_bytes=1000000)
    row=dict(metrics=dict(max_abs=0.001,mean_abs=0.0001),official_numeric_pass=True,
        verdict=dict(passed=True,contract='spec/numerical_contract.md:operator',limits=dict(max_abs=0.03125,mean_abs=0.005)))
    postseal['comparisons']={stage:copy.deepcopy(row) for stage in A.POSTSEAL_STAGES}
    return report,launch,postseal


def summarize(report,launch,postseal):
    return A.summarize(report,launch,source_digest=SHA,postseal=postseal)


def change(receipts,path,value,delete=False):
    current=receipts[path[0]]
    for key in path[1:-1]:current=current[key]
    if delete:del current[path[-1]]
    else:current[path[-1]]=value


def numeric_fail(report,launch,postseal,stage='gate'):
    report['tail_comparisons'][stage]['official_numeric_pass']=False
    report.update(status=A.FAIL,diagnostic_numeric_pass=False,diagnostic_acceptance_sealed=False,official_observed_node_pass=False)
    launch.update(status='FAILED',child_status=A.FAIL,returncode=1,diagnostic_numeric_pass=False,diagnostic_acceptance_sealed=False)
    postseal['original_diagnostic_numeric_pass']=False


class AggregateTests(unittest.TestCase):
    def test_synthetic_only_diagnostic_pass_and_fixed_formal_false(self):
        data=fixtures();snapshot=copy.deepcopy(data);summary=summarize(*data)
        self.assertEqual(summary['status'],A.PASS)
        self.assertTrue(summary['diagnostic_numeric_pass']);self.assertTrue(summary['diagnostic_acceptance_sealed'])
        self.assertTrue(summary['postseal_valid']);self.assertEqual(summary['acceptance_diagnostics']['failure_stages'],[])
        self.assertEqual(data,snapshot)
        for field in ('fullblock_pass','acceptance_sealed','chisel_full_prefill_pass','model_corresponds_to_current_chisel'):
            self.assertIs(summary[field],False)
        for field in ('hardware_cycles','hardware_utilization','hardware_duty'):self.assertIsNone(summary[field])
        self.assertEqual(summary['scope'],'DIAGNOSTIC_SOFTWARE_OWNER');self.assertEqual(summary['performance'],'NO_GO')
        self.assertEqual(summary['hardware_mapping'],'NOT_IMPLEMENTED')
        self.assertEqual(summary['software_operation_efficiency'],6014828544/6598164480)
        self.assertEqual(len(summary['acceptance_diagnostics']['nodes']),24)
        self.assertEqual(len(summary['acceptance_diagnostics']['postseal_nodes']),3)

    def test_original_120_gates_and_24_native_nodes_preserved(self):
        self.assertEqual(A.ORIGINAL_GATE_SCHEMA,original.DIAGNOSTIC_GATES)
        self.assertEqual(sum(map(len,A.ORIGINAL_GATE_SCHEMA.values())),120)
        self.assertEqual(A.NODE_SPECS,original.NODE_SPECS)
        def functions(module):
            return {n.name:n for n in ast.parse(Path(module.__file__).read_text()).body if isinstance(n,ast.FunctionDef)}
        old_functions=functions(original);new_functions=functions(A)
        for name in ('_comparison','_counts','_same_live','_debts','_source_records','_acceptance_diagnostics'):
            before=old_functions[name];after=new_functions[name]
            # Only the explanatory docstring changed in the diagnostic projector.
            if name=='_acceptance_diagnostics':before.body=before.body[1:];after.body=after.body[1:]
            self.assertEqual(ast.dump(before,include_attributes=False),ast.dump(after,include_attributes=False),name)

        for old,new in zip(original.DIRECT_GATES,A.ORIGINAL_DIRECT_GATES):
            self.assertEqual(old[:4],new[:4])
            if old[1] in ('ACCEPTANCE_SEALED','FULLBLOCK_PASS'):self.assertIs(new[4],False)
            elif old[1] in ('STATUS','CHILD_STATUS') and old[4]==original.PASS:self.assertEqual(new[4],A.PASS)
            elif old[4] is original._SOURCE_DIGEST:self.assertIs(new[4],A._SOURCE_DIGEST)
            else:self.assertEqual(old[4],new[4])
        # Preserve the old source byte-for-byte. This package contains a new
        # expression over fixed gates, never an imported old PASS expression.
        tree=ast.parse(Path(A.__file__).read_text())
        self.assertFalse(any(isinstance(n,ast.ImportFrom) and n.module and n.module.endswith('aggregate') for n in ast.walk(tree)))

    def test_each_direct_gate_still_required_and_never_echoed(self):
        for group,gate,receipt,path,expected in A.DIRECT_GATES:
            target=(0 if receipt in ('report','summary') else 1,*path)
            if receipt=='summary':target=(0,'execution','host','launch_result',*path)
            for missing in (False,True):
                rows=fixtures();bad=not expected if type(expected) is bool else expected+1 if type(expected) is int else 'PRIVATE_VALUE'
                change(rows,target,bad,missing)
                with self.subTest(group=group,gate=gate,missing=missing):
                    result=summarize(*rows)
                    self.assertNotEqual(result['status'],A.PASS)
                    self.assertIsNot(result['acceptance_diagnostics']['gates'][group][gate],True)
                    self.assertNotIn('PRIVATE_VALUE',json.dumps(result))

    def test_each_original_numeric_flag_is_authoritative(self):
        for stage,path,flag,_ in A.NODE_SPECS:
            for missing in (False,True):
                rows=fixtures();change(rows,(0,*path,flag),False,missing)
                if path[0]=='same_run_cache_original_comparisons' and not missing:
                    row=A._field(rows[0],path);row['metrics']['max_abs']=0.04;row['verdict']['passed']=False
                with self.subTest(stage=stage,missing=missing):
                    result=summarize(*rows)
                    self.assertEqual(result['status'],A.FAIL)
                    self.assertIs(result['acceptance_diagnostics']['gates']['NUMERIC'][stage],None if missing else False)

    def test_numeric_fail_still_supports_valid_postseal_isolation(self):
        rows=fixtures();numeric_fail(*rows);result=summarize(*rows)
        self.assertEqual(result['status'],A.FAIL);self.assertFalse(result['diagnostic_acceptance_sealed'])
        self.assertTrue(result['postseal_valid'])
        self.assertIs(result['acceptance_diagnostics']['gates']['NUMERIC']['TAIL_GATE'],False)
        self.assertEqual(len(result['acceptance_diagnostics']['nodes']),24)
        self.assertTrue(all(n['official_numeric_pass'] for n in result['acceptance_diagnostics']['postseal_nodes']))

    def test_each_postseal_component_native_fail_does_not_change_main_verdict(self):
        for stage in A.POSTSEAL_STAGES:
            rows=fixtures();r=rows[2]['comparisons'][stage]
            r['metrics']['max_abs']=0.04;r['official_numeric_pass']=False;r['verdict']['passed']=False
            result=summarize(*rows)
            self.assertEqual(result['status'],A.PASS);self.assertTrue(result['postseal_valid'])
            self.assertIs(next(n for n in result['acceptance_diagnostics']['postseal_nodes'] if n['stage']==stage)['official_numeric_pass'],False)

    def test_missing_or_bad_postseal_does_not_erase_native_nodes(self):
        baseline=summarize(*fixtures())['acceptance_diagnostics']['nodes']
        for key,bad in (('control_bit_exact',False),('official_gate_invocations',True),('official_gate_invocations',1),
            ('same_actual_seal_verified',False),('same_fresh_reference_verified',False),('same_runtime_verified',False),
            ('source_closure_sha256','b'*64),('status','PRIVATE_VALUE'),('comparison_order',[]),('comparisons',{})):
            rows=fixtures();rows[2][key]=bad;result=summarize(*rows)
            self.assertFalse(result['postseal_valid']);self.assertEqual(result['status'],A.PASS)
            self.assertEqual(result['acceptance_diagnostics']['nodes'],baseline)
            self.assertTrue(all(n['max_abs'] is None for n in result['acceptance_diagnostics']['postseal_nodes']))
        r,l,_=fixtures();result=A.summarize(r,l,source_digest=SHA)
        self.assertEqual(result['status'],A.PASS);self.assertFalse(result['postseal_valid'])
        self.assertEqual(result['acceptance_diagnostics']['nodes'],baseline)

    def test_every_extra_debt_and_identity_field_required(self):
        for field in ('diagnostic_debts_at_pc12','diagnostic_backend_debts'):
            for key in A.DIAGNOSTIC_DEBTS:
                for value in (True,0,None,'PRIVATE_VALUE'):
                    rows=fixtures();rows[0][field][key]=value
                    self.assertEqual(summarize(*rows)['status'],A.FAIL)
        for key in A.DIAGNOSTIC_IDENTITIES:
            rows=fixtures();del rows[0]['diagnostic_identity_final'][key]
            self.assertEqual(summarize(*rows)['status'],A.FAIL)
        for bad in (True,0,-1,'PRIVATE_VALUE'):
            rows=fixtures()
            for name in ('diagnostic_identity_initial','diagnostic_identity_final'):rows[0][name]['partial']=bad
            self.assertEqual(summarize(*rows)['status'],A.FAIL)
        rows=fixtures();rows[0]['diagnostic_identity_final']['original_a_payload']=[8,10]
        self.assertEqual(summarize(*rows)['status'],A.FAIL)

    def test_actual_exact64_and_matrix_counts_not_legacy_totals(self):
        paths=[('exact64_projections',0,'kernel_delta','fmas'),('exact64_projections',1,'kernel_delta','adds'),
            ('exact64_projections',0,'matrix_counter_delta','dense_steps'),('exact64_projections',1,'matrix_counter_delta','normal_steps'),
            ('exact64_projections',0,'actual_dense_fma_calls_delta'),('exact64_projections',1,'actual_normal_fma_calls_delta'),
            ('exact64_projections',0,'terminal','write_bytes'),('exact64_projections',0,'memory','acks'),
            ('exact64_projections',1,'driver_counts','response_fire'),('exact64_projections',0,'accepted','owner_results'),
            ('exact64_projections',0,'partial_bytes'),('observed_exact64_qk_totals','adds'),
            ('observed_v_totals','wide_matrix_steps'),('matrix','dense_fma_calls'),('matrix','normal_fma_calls'),
            ('matrix','counters','dense_steps'),('matrix','counters','normal_steps'),
            ('statistics','full_fixed_array_issued_cell_opportunities'),
            ('whole_schedule_prediction_and_observation','observed_tail','owner_acquires'),
            ('whole_schedule_prediction_and_observation','exact64_software','fmas'),
            ('whole_schedule_prediction_and_observation','exact64_matrix_stream_steps')]
        for path in paths:
            rows=fixtures();value=rows[0]
            for key in path:value=value[key]
            change(rows,(0,*path),value+1)
            with self.subTest(path=path):
                result=summarize(*rows);self.assertEqual(result['status'],A.FAIL);self.assertFalse(result['postseal_valid'])
        rows=fixtures();rows[0]['exact64_projections'].reverse();self.assertEqual(summarize(*rows)['status'],A.FAIL)
        rows=fixtures();rows[0]['exact64_projections'][0]['matrix_counter_delta']['unrecognized_issue']=1
        self.assertEqual(summarize(*rows)['status'],A.FAIL)

    def test_shared_a_publication_not_synthetic(self):
        for path,bad in ((('authority',),'REAL_SYNTHETIC_KVAPPEND'),(('active',),True),(('fault',),'PRIVATE_VALUE'),
            (('shared_payload_identity_unchanged',),False),(('same_dense_tile_attention_banks',),False),
            (('loan_events','releases'),0),(('publication','original_physical_write_guard'),False)):
            rows=fixtures();change(rows,(0,'shared_a_route',*path),bad)
            self.assertEqual(summarize(*rows)['status'],A.FAIL)

    def test_complete_private_51_file_inventory_and_verification_required(self):
        rows=fixtures();self.assertEqual(len(rows[0]['local_retention']['inventory']),51)
        for name in rows[0]['local_retention']['inventory']:
            mutated=copy.deepcopy(rows);del mutated[0]['local_retention']['inventory'][name]
            self.assertEqual(summarize(*mutated)['status'],A.FAIL)
        for key,bad in (('local_only',False),('upload_authorized',True),('oracle_payloads_read',True),
            ('reference_operands_in_execution',True),('propagation_inputs_retained',[])):
            mutated=fixtures();mutated[0]['local_retention'][key]=bad
            self.assertEqual(summarize(*mutated)['status'],A.FAIL)
        rows=fixtures();rows[0]['sealed_actual_outputs']['n1']['sha256']='c'*64
        self.assertEqual(summarize(*rows)['status'],A.FAIL)
        for field in ('local_retention_verified_before_seal','local_retention_verified_after_comparison'):
            rows=fixtures();rows[0][field]=False;self.assertEqual(summarize(*rows)['status'],A.FAIL)

    def test_new_contract_cannot_inherit_old_formal_pass(self):
        r,l=original_fixtures();result=A.summarize(r,l,source_digest=SHA)
        self.assertNotEqual(result['status'],A.PASS);self.assertFalse(result['diagnostic_numeric_pass'])
        for field in ('fullblock_pass','acceptance_sealed','chisel_full_prefill_pass'):
            rows=fixtures();rows[0][field]=True;self.assertEqual(summarize(*rows)['status'],A.FAIL)

    def test_fixed_sanitized_projection_and_strict_validator(self):
        rows=fixtures();secret=dict(path='/PRIVATE_VALUE',hash='f'*64,shape=[99],stride=[99],rowindex=3,
            inventory={'PRIVATE_NAME':'PRIVATE_VALUE'},error='PRIVATE_VALUE',traceback='PRIVATE_VALUE')
        for row in rows:row.update(secret)
        for group in rows[2]['comparisons'].values():group['metrics'].update(secret)
        rows[0]['failure_stage']='PRIVATE_VALUE';rows[0]['original_error_type']='PRIVATE_VALUE'
        summary=summarize(*rows);encoded=json.dumps(summary,allow_nan=False)
        for word in ('PRIVATE_VALUE','PRIVATE_NAME','f'*64,'shape','stride','rowindex','inventory','traceback'):
            self.assertNotIn(word,encoded)
        for key,value in (('private',1),('scope','PRIVATE_VALUE'),('status','PASS_OFFICIAL_OBSERVED'),
            ('performance','GO'),('fullblock_pass',True),('acceptance_sealed',True),('chisel_full_prefill_pass',True)):
            changed=copy.deepcopy(summary);changed[key]=value
            with self.assertRaises(ValueError):A.validate_summary(changed)
        changed=copy.deepcopy(summary);changed['acceptance_diagnostics']['postseal_nodes'][0]['stage']='PRIVATE_VALUE'
        with self.assertRaises(ValueError):A.validate_summary(changed)

    def test_postseal_metrics_are_finite_and_native_verdict_consistent(self):
        for stage in A.POSTSEAL_STAGES:
            for bad in (True,None,-1,float('nan'),float('inf'),10**400,'PRIVATE_VALUE'):
                rows=fixtures();rows[2]['comparisons'][stage]['metrics']['max_abs']=bad
                result=summarize(*rows);self.assertFalse(result['postseal_valid'])
                self.assertNotIn('PRIVATE_VALUE',json.dumps(result,allow_nan=False))
            rows=fixtures();rows[2]['comparisons'][stage]['verdict']['passed']=False
            self.assertFalse(summarize(*rows)['postseal_valid'])
            rows=fixtures();rows[2]['comparisons'][stage]['verdict']['limits']['max_abs']=0.05
            self.assertFalse(summarize(*rows)['postseal_valid'])

    def test_original_resources_missing_invalid_or_over_budget_fail(self):
        paths={'HOST_WALL':(0,'host_wall_seconds'),'HOST_CPU':(0,'host_cpu_seconds'),
            'SUPERVISOR_WALL':(1,'elapsed_seconds'),'PEAK_RSS':(0,'peak_rss_kib'),
            'SAMPLED_GROUP_RSS':(1,'peak_sampled_process_group_rss_bytes'),
            'OUTPUT_BYTES':(1,'final_output_bytes'),'LOG_BYTES':(1,'final_log_bytes')}
        for gate,_,limit in A.RESOURCE_GATES:
            for bad in (None,True,-1,float('nan'),float('inf'),'PRIVATE_VALUE',10**400):
                rows=fixtures();change(rows,paths[gate],bad)
                result=summarize(*rows);self.assertEqual(result['status'],A.FAIL)
                self.assertIsNone(result['acceptance_diagnostics']['gates']['RESOURCES'][gate])
            if limit is not None:
                rows=fixtures();change(rows,paths[gate],limit//1024+1 if gate=='PEAK_RSS' else limit+1)
                self.assertEqual(summarize(*rows)['status'],A.FAIL)

    def test_cold_default_reads_no_sources_receipts_or_tensor_runtime(self):
        with patch.object(A.closure,'digest',side_effect=AssertionError('source read')),patch.object(A,'_read',side_effect=AssertionError('receipt read')):
            self.assertEqual(A.collect(),dict(status='NOT_EXECUTED',numeric_execution_allowed=False))
            for value in (None,1,'yes'):
                with self.assertRaises(ValueError):A.collect(execute=value)
        code='from candidates.qwen2_exact64_diagnostic_fullblock import aggregate; import sys; assert not any(n.split(".")[0] in ("torch","numpy","transformers") for n in sys.modules)'
        result=subprocess.run([sys.executable,'-B','-c',code],cwd=A.ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_collect_only_fixed_receipts_and_source_review_before_after(self):
        with patch.object(A,'ROOT',A.CI_ROOT),patch.object(A.closure,'digest',return_value=SHA) as source,patch.object(A,'_read',side_effect=fixtures()) as read:
            result=A.collect(execute=True,source_digest=SHA)
            self.assertEqual(result['status'],A.PASS);self.assertTrue(result['postseal_valid'])
            self.assertEqual([c.args[0] for c in read.call_args_list],[A.RESULT,A.LAUNCH,A.POSTSEAL]);self.assertEqual(source.call_count,2)
        r,l,_=fixtures()
        with patch.object(A,'ROOT',A.CI_ROOT),patch.object(A.closure,'digest',return_value=SHA),patch.object(A,'_read',side_effect=[r,l,FileNotFoundError('/PRIVATE_VALUE')]):
            result=A.collect(execute=True,source_digest=SHA)
            self.assertEqual(result['status'],A.PASS);self.assertFalse(result['postseal_valid'])
            self.assertNotIn('PRIVATE_VALUE',json.dumps(result))
        with patch.object(A,'ROOT',A.CI_ROOT),patch.object(A.closure,'digest',side_effect=[SHA,'b'*64]),patch.object(A,'_read',side_effect=fixtures()):
            with self.assertRaisesRegex(ValueError,'source closure changed'):A.collect(execute=True,source_digest=SHA)
        with patch.object(A,'ROOT',A.CI_ROOT),patch.object(A.closure,'digest',return_value='b'*64),patch.object(A,'_read',side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError,'source closure drift'):A.collect(execute=True,source_digest=SHA)
        with self.assertRaisesRegex(ValueError,'fixed CI'):A.collect(execute=True,source_digest=SHA)

    def test_missing_receipts_and_strict_json(self):
        result=A.summarize({}, {}, source_digest=SHA)
        self.assertEqual(result['status'],'INCOMPLETE');self.assertFalse(result['postseal_valid'])
        self.assertTrue(all(v is None for rows in result['acceptance_diagnostics']['gates'].values() for v in rows.values()))
        with tempfile.TemporaryDirectory() as directory,patch.object(A,'ROOT',Path(directory)):
            path=Path(directory)/'fixture.json'
            for raw in ('{"x":1,"x":2}','{"x":NaN}','[]'):
                path.write_text(raw)
                with self.assertRaises(ValueError):A._read('fixture.json')
            path.write_text('{"x":1}');self.assertEqual(A._read('fixture.json'),{'x':1})
            (Path(directory)/'alias.json').symlink_to(path)
            with self.assertRaises(ValueError):A._read('alias.json')


if __name__=='__main__':unittest.main()
