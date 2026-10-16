"""COLD SYNTHETIC fixtures only. No DUT, native, producer, or tensor execution."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest

if __package__:
    from . import terminal_validator as V
else:
    import terminal_validator as V


def hash_of(label):
    return V.sha(label.encode())


def metric(shape, label, *, error=0.0):
    n=V.math.prod(shape);different=1 if error else 0
    return dict(shape=shape,elements=n,max_abs=error,mean_abs=error/n,relative_l2=error,
        cosine=1.0,normalized_max_abs=error,different_elements=different,bit_exact=not different,
        first_difference_flat=0 if different else None,actual_f32_sha256=hash_of(label),
        reference_f32_sha256=hash_of(label+'reference') if different else hash_of(label),finite=True)


def source_map():
    sources={'spec/numerical_contract.md':V.THRESHOLDS['sha256']}
    for name in ('attention_packed_m16_entry/pins.json','attention_packed_m16_entry/contract.py',
        'attention_packed_observation/monitor.py','attention_packed_observation/capture.py',
        'dense_block_reduce/check_public_numeric.py','official_bf16/check_numeric.py',
        'ffn_public/fullgraph_execution.py'):
        sources['candidates/qwen2_resident_matrix/'+name]=hash_of(name)
    return sources


def fixture(snapshot_path):
    sources=source_map()
    provenance=dict(native_execution_reused=True,new_official_forward_executed=False,actual_chain_executed=False)
    s=dict(schema=1,status='PREPARED_REDUCED_PUBLIC21_NOT_EXECUTED',rows=16,epoch=7,
        enable_packed=True,enable_raw_kv=True,fresh_profile=True,raw_kv_source_profile=V.PROFILE,
        reduction_policy=V.POLICY,old_pass_inherited=False,source_sha256=sources,
        source_manifest_sha256=V.sha(V.encoded(sources,pretty=True)),input_spec={},binaries={},
        loaded_inputs={},metadata={},fresh_assets={},reference=dict(threshold_policy=V.THRESHOLDS,
        fresh_provenance=provenance,prior_failures={}),independent_reference=dict(native_acceptance=False))
    raw=V.encoded(s,pretty=True);snapshot_sha=V.sha(raw)
    actual={n:dict(bytes=16*w*4,sha256=hash_of(n)) for n,w in V.ACTUAL_WIDTHS.items()}
    fields={}
    for name in V.FIELDS:
        shape,presence,frequency=V.field_geometry(name)
        fields[name]=dict(shape=shape,words=len(presence),observed_words=sum(presence),
            raw_sha256=hash_of('pv' if name=='pv_bf16' else name),presence_sha256=V.sha(presence),
            frequency_sha256=V.sha(frequency),writes=sum(presence),identical_repeats=0)
    retirement=dict(state='idle',poison=False,same_services=True,same_job=True,matrix_released=True,
        matrix_reset_required=False,client_retired=True,memory_pending=False,scalar_released=True,
        scratch_pending=False,scratch_leased=False,scratch_request=False,scratch_write_tag=False,packed_memory_tag=False)
    observation=dict(schema=V.OBSERVER,source_version=V.OBSERVER,
        status='COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED',source_sha256=sources,observer_error=None,
        fields=fields,packed_multiplicity=dict(causal_field=1,normalizer_per_head_query=1,pv_word=1,
        legacy_probability_repeats=8,legacy_normalizer_repeats='8*(query+1)',synthetic_repeats=0),
        job=dict(kind='Attention',m=16,tag=(7<<16)|12,write_bytes=16*1536*4),
        terminal=dict(status=None,tag=(7<<16)|12,write_bytes=16*1536*4),accepted_retirement=retirement,
        trace_api='synthetic',prior_observation_results_inherited=False,full_29_node_gate=False,
        whole_block_terminal_observed=False,physical_publication_observed=False,hardware_simulation=False,
        future_scores_observed=False,numerical_policy='official-bf16-v1',native_acceptance='NOT_EVALUATED_BY_OBSERVER',
        matrix_binary_provenance_verified_by_observer=False,pv_bf16_boundary='synthetic')
    observed={n:metric([1632 if n in V.CAUSAL else 24576 if n=='pv' else 143360],n) for n in V.OBSERVED}
    methods={}
    for method in ('official_self_cache','independent_self_cache'):
        stages={}
        for name,shape in V.STAGE_SHAPES.items():
            count=V.math.prod(shape);n=1632 if name in V.CAUSAL else count
            m=metric([n] if name in V.CAUSAL or name=='pv' else shape,name)
            role='block' if name=='y' else 'operator'
            verdict=(dict(contract=None,passed=None,status='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE') if name=='softmax_fp32'
                else dict(contract='spec/numerical_contract.md:'+role,limits=V.THRESHOLDS[role],passed=True))
            stages[name]=dict(metrics=m,verdict=verdict,original_shape=shape,
                coverage='actual_causal_positions_only' if name in V.CAUSAL else 'complete',
                observed_elements=n,unobserved_elements=count-n)
        methods[method]=dict(stages=stages,failed_stages=[],numerical_status='PASS_OBSERVED_ONLY')
    old=dict(whole_outputs={n:metric([1,16,w],n) for n,w in V.WIDTHS.items()},
        actual_observed_nodes={n:metric([1,16,8960] if n=='silu' else observed[n]['shape'],n) for n in V.OBSERVED},
        fixed_arithmetic_pass=True)
    c=dict(whole_outputs={n:metric([16*w],n) for n,w in V.WIDTHS.items()},actual_observed_nodes=observed,
        fixed_arithmetic_pass=True,methods=methods,thresholds=V.THRESHOLDS,historical_diagnostic_failures={},
        full_29_node_acceptance=False,missing_nodes=['explicit_mask_tensor'],
        partially_observed_nodes=['scores','logits','prob','softmax_fp32'],future_score_materialization=False,
        new_official_forward_executed=False,native_execution_reused=True,
        reference_layout=dict(qk_storage='token_major',**provenance),
        reference_reuse='fresh same-input sequential/block-pair outputs; explicitly reused verified native M16 outputs; original gates retained',
        old_sequential_producer_diagnostic=old,independent_reference=s['independent_reference'],
        official_target='official_self_cache',independent_self_cache_is_auxiliary=True,
        old_sequential_producer_is_auxiliary=True,acceptance_requires_all_assigned_official_observed_node_gates=True)
    outputs={n:dict(bytes=v['bytes'],written_bytes=v['bytes'],ack_bytes=v['bytes'],terminal=True,published=True,
        sha256=v['sha256']) for n,v in actual.items() if n not in ('gate','up')}
    host=dict(launch_result=dict(status=None,completed=21,jobs=17,write_bytes=sum(v['bytes'] for v in outputs.values())),
        accepted=dict(request_fire=17,owner_result_fire=17,completion_fire=21,result_fire=1),
        reset_required=False,same_owner_and_banks=True,model_ticks_are_hardware_cycles=False,events=list(range(22)),
        completions=[dict(pc=i,status=None,signal=i+1) for i in range(21)],requests=[{} for _ in range(17)])
    e=dict(status='PUBLIC21_PC0_20_SOFTWARE_EXECUTED',same_owner_and_banks=True,
        same_physical_memory_and_services=True,full_block_executed=True,full_block_software_model_executed=True,
        attention_suffix_executed=True,public_host_python_model_executed=True,scala_host_executed=False,
        rtl_executed=False,actual_idma=False,protocol_model_ticks_are_hardware_cycles=False,
        reference_arithmetic_executed=False,hardware_cycles=None,full_wall_mac_utilization=None,
        native_acceptance='NOT_EVALUATED_BY_EXECUTION_SEE_COMPARISON',
        inherited_native_acceptance_label='UNCHANGED_FAIL_POLICY_PENDING',host=host,
        reports=[dict(pcs=x) for x in [[10,11,12],[13],[14],[15],[16,17,18],[19],[20]]],
        memory=dict(outputs=outputs),matrix=dict(reset_required=False,hardware_simulation=False,same_accumulator_resource=True))
    r=dict(status=V.PASS,policy=V.POLICY,rows=16,source_sha256=sources,source_sha256_after=sources,
        input_spec=s['input_spec'],binaries=s['binaries'],snapshot=str(snapshot_path),snapshot_sha256=snapshot_sha,
        rtl_executed=False,scala_executed=False,hardware_cycles=None,prelaunch_intermediate_payloads=[],old_pass_inherited=False,
        native_acceptance='PASS_OBSERVED_ONLY',enable_raw_kv=True,raw_kv_source_profile=V.PROFILE,fresh_profile=True,
        fresh_assets=s['fresh_assets'],fresh_provenance=provenance,loaded_inputs=s['loaded_inputs'],metadata=s['metadata'],
        prefix_execution=[dict(pc=i) for i in range(10)],prefix_host_wall_seconds=1,execution=e,
        whole_terminal_host_wall_seconds=2,observation=observation,sealed_actual_outputs=actual,sealed_silu_sha256=hash_of('silu'),
        comparison=c,executed_imports_observed=sorted(sources),full_29_node_acceptance=False,actual_dataflow_pass=True,
        host_wall_seconds=3,host_cpu_seconds=2,host_peak_rss_kib=1)
    return copy.deepcopy((r,s,sources))


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.snapshot=Path(self.tmp.name)/'snapshot.json';self.summary=Path(self.tmp.name)/'summary.json'
        self.r,self.s,self.sources=fixture(self.snapshot)

    def validate(self,r=None):
        r=self.r if r is None else r
        self.snapshot.write_bytes(V.encoded(self.s,pretty=True))
        self.summary.write_bytes(V.encoded(r,pretty=True))
        return V.validate_terminal(self.summary,V.sha(self.summary.read_bytes()),self.sources,
            self.snapshot,V.sha(self.snapshot.read_bytes()))

    def test_cold_success_scope(self):
        v=self.validate()
        self.assertEqual(v['assigned_official_gates'],27)
        self.assertEqual(v['official_observed_stages'],28)
        self.assertFalse(v['full_29_node_acceptance']);self.assertFalse(v['rtl_acceptance'])
        self.assertFalse(v['hardware_acceptance']);self.assertFalse(v['execution_authenticated_by_this_validator'])
        self.assertLess(len(V.encoded(v)),1400)
        self.assertNotIn(str(self.summary),json.dumps(v))

    def test_reject_every_missing_top_field(self):
        for k in list(self.r):
            with self.subTest(k=k):
                r=copy.deepcopy(self.r);del r[k]
                with self.assertRaises(V.InvalidReceipt):self.validate(r)

    def test_reject_mutations(self):
        mutations=[
            (('status',),'PASS'),(('rows',),True),(('full_29_node_acceptance',),True),
            (('rtl_executed',),True),(('hardware_cycles',),1),(('old_pass_inherited',),True),
            (('native_acceptance',),'FULL_PASS'),(('source_sha256_after','spec/numerical_contract.md'),hash_of('bad')),
            (('snapshot_sha256',),hash_of('bad')),(('prelaunch_intermediate_payloads',),['private']),
            (('execution','host','launch_result','completed'),20),(('execution','host','launch_result','jobs'),16),
            (('execution','host','launch_result','status'),'Protocol'),(('execution','host','accepted','result_fire'),2),
            (('execution','host','reset_required'),True),(('execution','host','events'),list(range(21))),
            (('execution','memory','outputs','y','ack_bytes'),0),
            (('comparison','fixed_arithmetic_pass'),False),
            (('comparison','methods','official_self_cache','numerical_status'),'PASS'),
            (('comparison','methods','official_self_cache','failed_stages'),['q']),
            (('comparison','methods','official_self_cache','stages','q','verdict','passed'),False),
            (('comparison','methods','official_self_cache','stages','softmax_fp32','verdict','passed'),True),
            (('comparison','methods','official_self_cache','stages','prob','observed_elements'),3072),
            (('comparison','methods','official_self_cache','stages','prob','coverage'),'complete'),
            (('comparison','methods','official_self_cache','stages','y','metrics','finite'),False),
            (('observation','status'),'INCOMPLETE'),(('observation','observer_error'),'private error'),
            (('observation','fields','dot_parts','observed_words'),49152),
            (('observation','fields','normalizer','identical_repeats'),8),
            (('observation','fields','prob_bf16','presence_sha256'),hash_of('future')),
            (('observation','fields','pv_bf16','frequency_sha256'),hash_of('double')),
            (('observation','accepted_retirement','scratch_pending'),True),
            (('observation','terminal','status'),'Protocol'),
            (('comparison','independent_self_cache_is_auxiliary'),False),
        ]
        for path,value in mutations:
            with self.subTest(path=path):
                r=copy.deepcopy(self.r);target=r
                for key in path[:-1]:target=target[key]
                target[path[-1]]=value
                with self.assertRaises(V.InvalidReceipt):self.validate(r)

    def test_reject_unknown_or_missing_stage_or_capture(self):
        for path,key in [(('comparison','methods','official_self_cache','stages'),'y'),
                         (('comparison','whole_outputs'),'q'),(('observation','fields'),'pv_raw')]:
            for action in ('remove','add'):
                r=copy.deepcopy(self.r);target=r
                for part in path:target=target[part]
                if action=='remove':del target[key]
                else:target['unknown']=copy.deepcopy(target[key])
                with self.subTest(path=path,action=action),self.assertRaises(V.InvalidReceipt):self.validate(r)

    def test_original_boundary_pass_and_auxiliary_failure(self):
        for method in ('official_self_cache','independent_self_cache'):
            stage=self.r['comparison']['methods'][method]['stages']['y']
            stage['metrics']=metric(V.STAGE_SHAPES['y'],'y',error=0.05)
            stage['metrics']['mean_abs']=0.01
        # Both exact original inclusive boundaries pass.
        self.validate()
        auxiliary=self.r['comparison']['methods']['independent_self_cache']
        auxiliary['stages']['y']['metrics']['max_abs']=1.0
        auxiliary['stages']['y']['verdict']['passed']=False
        auxiliary['failed_stages']=['y'];auxiliary['numerical_status']='FAIL'
        self.validate()
        # An auxiliary failure must still be reported consistently.
        auxiliary['numerical_status']='PASS_OBSERVED_ONLY'
        with self.assertRaises(V.InvalidReceipt):self.validate()

    def test_original_official_failure_recomputed(self):
        stage=self.r['comparison']['methods']['official_self_cache']['stages']['y']
        stage['metrics']=metric(V.STAGE_SHAPES['y'],'y',error=0.05001)
        with self.assertRaises(V.InvalidReceipt):self.validate()

    def test_fp32_diagnostic_not_new_gate(self):
        for method in self.r['comparison']['methods'].values():
            method['stages']['softmax_fp32']['metrics']=metric([1632],'softmax_fp32',error=100)
        self.validate()

    def test_old_sequential_failure_is_auxiliary(self):
        old=self.r['comparison']['old_sequential_producer_diagnostic']
        old['whole_outputs']['y']=metric([1,16,1536],'y',error=1)
        old['fixed_arithmetic_pass']=False
        self.validate()

    def test_unknown_acceptance_claim(self):
        self.r['execution']['future_native_acceptance']=True
        with self.assertRaises(V.InvalidReceipt):self.validate()

    def test_inherited_nonacceptance_labels_remain_allowed(self):
        self.r['execution']['reports'][1]['report']={
            'native_m128_and_fp32_final_acceptance':'UNCHANGED_FAIL_POLICY_PENDING'}
        self.validate()
        self.r['execution']['reports'][1]['report']['native_m128_and_fp32_final_acceptance']='PASS'
        with self.assertRaises(V.InvalidReceipt):self.validate()

    def test_unknown_nested_native_pass_rejected(self):
        self.r['execution']['reports'][1]['report']={'native_acceptance':'PASS_OBSERVED_ONLY'}
        with self.assertRaises(V.InvalidReceipt):self.validate()

    def test_failed_owner_status_not_hidden_by_top_pass(self):
        self.r['prefix_execution'][4]['report']={'terminal':{'status':'Protocol'}}
        with self.assertRaises(V.InvalidReceipt):self.validate()

    def test_same_byte_hash(self):
        self.validate();self.summary.write_bytes(self.summary.read_bytes()+b'\n')
        with self.assertRaises(V.InvalidReceipt):
            V.validate_terminal(self.summary,hash_of('wrong'),self.sources,self.snapshot,V.sha(self.snapshot.read_bytes()))

    def test_strict_json_boundaries(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":1e999}',
                    b'['*50+b'0'+b']'*50,b'"'+b'x'*8193+b'"',b' '* (V.MAX_JSON+1)):
            with self.subTest(case=len(raw)),self.assertRaises(V.InvalidReceipt):V.strict_json(raw)

    def test_no_symlink_or_nonregular(self):
        self.validate();other=Path(self.tmp.name)/'link';other.symlink_to(self.summary)
        with self.assertRaises(V.InvalidReceipt):V.read_bound(other,V.sha(self.summary.read_bytes()))
        with self.assertRaises(V.InvalidReceipt):V.read_bound(Path(self.tmp.name),hash_of('x'))

    def test_source_map_exact_and_encoding_distinction(self):
        self.assertNotEqual(V.sha(V.encoded(self.sources)),V.sha(V.encoded(self.sources,pretty=True)))
        self.sources['extra.py']=hash_of('extra')
        with self.assertRaises(V.InvalidReceipt):self.validate()

    def test_cached_import_audit_can_be_empty(self):
        self.r['executed_imports_observed']=[]
        self.validate()

    def test_no_dut_or_native_imports(self):
        tree=ast.parse(Path(V.__file__).read_text())
        names={n.names[0].name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import)}
        names|={n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
        self.assertLessEqual(names,{'hashlib','json','math','os','pathlib','stat'})

if __name__=='__main__':unittest.main()
