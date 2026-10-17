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
    for name in V.REQUIRED_SOURCES:
        sources[V.PREFIX+name]=hash_of(name)
    for name,value in V.OBSERVER_CODE_PINS.items():
        sources[V.PREFIX+'attention_packed_tiled_observation/'+name]=value
    return sources


def fixture(snapshot_path):
    sources=source_map()
    identity=dict(profile=V.PROFILE,manifest='/synthetic/INPUTS.json',manifest_sha256=hash_of('manifest'),enable_raw_kv=True)
    provenance=dict(profile=V.PROFILE,fresh_assets=identity,new_official_forward_executed=False,
        native_execution_reused=True,oracle_execution_reused=True,historical_receipts_reused=True,
        actual_chain_executed=False,old_pass_inherited=False,full_29_node_acceptance=False,
        origin_identity=dict(profile=V.PROFILE,origin='/synthetic/origin',
            origin_manifest_sha256=V.ORIGIN_MANIFEST_SHA256,payload_bytes_hashed=True,
            actual_chain_executed=False,old_pass_inherited=False,full_29_node_acceptance=False),
        m16_prerequisite=dict(m16_completion_verified=True,m128_verdict_inherited=False,
            old_pass_inherited=False,full_29_node_acceptance=False),original_m128_numerical_pass_inherited=False,
        native_result_sha256=V.NATIVE_RESULT_SHA256,native_status='PASS_BF16_STAGE_BUDGET',
        native_vs_independent_failed_stages=[],producer_sha256=hash_of('producer'),
        sequential_cpp_sha256=hash_of('sequential'),reduced_cpp_sha256=hash_of('reduced'),
        origin_before_after_unchanged=True)
    def lookup(shapes):
        return {n:dict(root='origin',path='synthetic/'+n,bytes=4*V.math.prod(shape),sha256=hash_of(n))
                for n,shape in shapes.items()}
    roots={'origin':'/synthetic/origin/private/assets'}
    original=dict(token_ids=list(range(V.ROWS)),positions=list(range(V.ROWS)),
        input_x_sha256=V.INPUT_X_SHA256,readonly_sha256=V.ARENA_SHA256,intermediate_preloads=0,readonly_bytes=188043264)
    references=lookup(V.REFERENCE_SHAPES);reduced=lookup(V.RAW_SHAPES)
    for i,name in enumerate(V.WIDTHS):
        reduced['raw_stages/phase_%d_%s_recipe.f32le'%(i,name)]['sha256']=hash_of(name)
    reduced['raw_stages/silu.f32le']['sha256']=hash_of('silu')
    reference=dict(fresh_profile=V.PROFILE,roots=roots,directory=roots['origin']+'/readonly',
        table_path=roots['origin']+'/readonly/rope_full.f32le',fresh_lookup=references,
        inputs=dict(original,position_ids=list(range(V.ROWS))),threshold_policy=V.THRESHOLDS,
        official_reference_identity={},tensors=[dict(name=n,shape=shape,
            export_shape=([1,V.ROWS,1536 if n=='q' else 256] if n in ('q','k') else shape),
            path='candidate_'+n+'.f32le',sha256=references['tensors/candidate_'+n+'.f32le']['sha256'])
            for n,shape in sorted(V.NATIVE_SHAPES.items())],prior_failures={},fresh_provenance=provenance,
        artifacts=[dict(v,path=n) for n,v in references.items()],native_execution_reused=True,
        oracle_execution_reused=True,old_pass_inherited=False)
    independent=dict(fresh_profile=V.PROFILE,roots=roots,directory=roots['origin']+'/reduced',
        rows=V.ROWS,past_tokens=0,result_sha256=hash_of('reduced_run'),
        readonly_input=dict(path=roots['origin']+'/readonly/readonly_arena.f32le',bytes=188043264,
            sha256=V.ARENA_SHA256,input_x_sha256=V.INPUT_X_SHA256),fresh_lookup=reduced,
        artifacts=[dict(v,path=n) for n,v in reduced.items()],actual_chain_executed=False,
        native_acceptance=False,fresh_provenance=provenance)
    loaded={n:dict(bytes=4,sha256=hash_of(n)) for n in
            ('x','rope','gamma0','gamma1','bq','bk','bv','wq','wk','wv','wo','wg','wu','wd')}
    loaded['x']=dict(bytes=V.ROWS*1536*4,sha256=V.INPUT_X_SHA256)
    s=dict(schema=1,status='PREPARED_REDUCED_PUBLIC21_NOT_EXECUTED',rows=V.ROWS,epoch=7,
        enable_packed=True,enable_raw_kv=True,fresh_profile=True,raw_kv_source_profile=V.PROFILE,
        reduction_policy=V.POLICY,old_pass_inherited=False,source_sha256=sources,
        source_manifest_sha256=V.sha(V.encoded(sources,pretty=True)),input_spec=dict(original_input=original,
        fresh_profile=V.PROFILE,metadata_sha256={identity['manifest']:identity['manifest_sha256']}),
        binaries=dict(compile_receipt='/synthetic/compile.json',compile_sha256=V.COMPILE_SHA256,
            library='/synthetic/library.so',library_sha256=V.LIBRARY_SHA256),
        loaded_inputs=loaded,metadata={},fresh_assets=identity,reference=reference,independent_reference=independent,
        host_tools={},original_snapshot='/synthetic/original/SNAPSHOT.json',original_snapshot_sha256=hash_of('original_snapshot'),
        policy={},prelaunch_intermediate_payloads=[])
    raw=V.encoded(s,pretty=True);snapshot_sha=V.sha(raw)
    actual={n:dict(bytes=V.ROWS*w*4,sha256=hash_of(n)) for n,w in V.ACTUAL_WIDTHS.items()}
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
        job=dict(kind='Attention',m=V.ROWS,tag=(7<<16)|12,write_bytes=V.ROWS*1536*4,
            a=1,b=2,c=3,dst=4,k=128,n=1536,activation_bf16=False,weight_bf16=False,output_bf16=False),
        terminal=dict(status=None,tag=(7<<16)|12,write_bytes=V.ROWS*1536*4,cycles=1,executed_macs=1,useful_macs=1),accepted_retirement=retirement,
        trace_api='CPython sys.monitoring pinned packed run LINE and actual scalar/tick PY_RETURN',prior_observation_results_inherited=False,full_29_node_gate=False,
        whole_block_terminal_observed=False,physical_publication_observed=False,hardware_simulation=False,
        future_scores_observed=False,numerical_policy='official-bf16-v1',native_acceptance='NOT_EVALUATED_BY_OBSERVER',
        matrix_binary_provenance_verified_by_observer=False,pv_bf16_boundary='actual store words; ACK coverage requires accepted successful owner terminal')
    observed={n:metric([V.CAUSAL_WORDS if n in V.CAUSAL else V.PV_WORDS if n=='pv' else V.SILU_WORDS],n) for n in V.OBSERVED}
    methods={}
    for method in ('official_self_cache','independent_self_cache'):
        stages={}
        for name,shape in V.STAGE_SHAPES.items():
            count=V.math.prod(shape);n=V.CAUSAL_WORDS if name in V.CAUSAL else count
            m=metric([n] if name in V.CAUSAL or name=='pv' else shape,name)
            role='block' if name=='y' else 'operator'
            verdict=(dict(contract=None,passed=None,status='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE') if name=='softmax_fp32'
                else dict(contract='spec/numerical_contract.md:'+role,limits=V.THRESHOLDS[role],passed=True))
            stages[name]=dict(metrics=m,verdict=verdict,original_shape=shape,
                coverage='actual_causal_positions_only' if name in V.CAUSAL else 'complete',
                observed_elements=n,unobserved_elements=count-n)
        methods[method]=dict(stages=stages,failed_stages=[],numerical_status='PASS_OBSERVED_ONLY')
    old=dict(whole_outputs={n:metric([1,V.ROWS,w],n) for n,w in V.WIDTHS.items()},
        actual_observed_nodes={n:metric([1,V.ROWS,8960] if n=='silu' else observed[n]['shape'],n) for n in V.OBSERVED},
        fixed_arithmetic_pass=True)
    c=dict(whole_outputs={n:metric([V.ROWS*w],n) for n,w in V.WIDTHS.items()},actual_observed_nodes=observed,
        fixed_arithmetic_pass=True,methods=methods,thresholds=V.THRESHOLDS,historical_diagnostic_failures={},
        full_29_node_acceptance=False,missing_nodes=['explicit_mask_tensor'],
        partially_observed_nodes=['scores','logits','prob','softmax_fp32'],future_score_materialization=False,
        new_official_forward_executed=False,native_execution_reused=True,
        reference_layout=dict(qk_storage='token_major',**provenance),
        reference_reuse=V.REFERENCE_REUSE,
        old_sequential_producer_diagnostic=old,independent_reference=s['independent_reference'],
        official_target='official_self_cache',independent_self_cache_is_auxiliary=True,
        old_sequential_producer_is_auxiliary=True,acceptance_requires_all_assigned_official_observed_node_gates=True)
    outputs={n:dict(bytes=v['bytes'],written_bytes=v['bytes'],ack_bytes=v['bytes'],terminal=True,published=True,
        sha256=v['sha256']) for n,v in actual.items() if n not in ('gate','up')}
    physical_write_bytes=sum(v['bytes'] for v in outputs.values())
    for name in ('gate','up','scores','probabilities','workspace'):
        extent=V.ROWS*V.ACTUAL_WIDTHS[name]*4 if name in ('gate','up') else V.HEADS*V.ROWS*V.ROWS*4
        outputs[name]=dict(bytes=extent,written_bytes=0,ack_bytes=0,terminal=False,published=False,sha256=hash_of(name+'virtual'))
    host=dict(launch_result=dict(status=None,completed=21,jobs=17,write_bytes=physical_write_bytes),
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
    r=dict(status=V.PASS,policy=V.POLICY,rows=V.ROWS,source_sha256=sources,source_sha256_after=sources,
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
            method['stages']['softmax_fp32']['metrics']=metric([V.CAUSAL_WORDS],'softmax_fp32',error=100)
        self.validate()

    def test_old_sequential_failure_is_auxiliary(self):
        old=self.r['comparison']['old_sequential_producer_diagnostic']
        old['whole_outputs']['y']=metric([1,V.ROWS,1536],'y',error=1)
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


    def rebound(self):
        self.r['snapshot_sha256']=V.sha(V.encoded(self.s,pretty=True))
        return self.validate()

    def test_m128_geometry_keeps_dot_width_and_head_dimension(self):
        expected={'dot_parts':([12,128,128,16],3145728,1585152),
            'normalizer':([12,128,3],4608,4608),
            'pv_raw':([12,128,128],196608,196608),
            'pv_bf16':([12,128,128],196608,196608)}
        for name in V.FIELDS:
            shape,total,observed=expected.get(name,([12,128,128],196608,99072))
            actual,presence,frequency=V.field_geometry(name)
            self.assertEqual(actual,shape);self.assertEqual(len(presence),total)
            self.assertEqual(sum(presence),observed);self.assertEqual(frequency[::2],presence)
            self.assertEqual(frequency[1::2],b'\x00'*total)
        self.assertEqual(V.SILU_WORDS,1146880)
        self.assertEqual(len(V.ACTUAL_WIDTHS),19)
        self.assertEqual(len(V.RAW_SHAPES),22);self.assertEqual(len(V.REFERENCE_SHAPES),109)
        self.assertEqual(sum(V.ROWS*w*4 for n,w in V.ACTUAL_WIDTHS.items() if n not in ('gate','up')),13369344)

    def test_each_capture_field_requires_complete_once_only_mask(self):
        for name in V.FIELDS:
            for key,value in (('observed_words',0),('writes',0),('identical_repeats',1),
                              ('presence_sha256',hash_of('partial')),('frequency_sha256',hash_of('repeat'))):
                r=copy.deepcopy(self.r);r['observation']['fields'][name][key]=value
                with self.subTest(name=name,key=key),self.assertRaises(V.InvalidReceipt):self.validate(r)

    def test_every_required_source_is_required(self):
        for name in V.REQUIRED_SOURCES:
            sources=dict(self.sources);del sources[V.PREFIX+name]
            with self.subTest(name=name),self.assertRaises(V.InvalidReceipt):V.source_map(sources)
        for key in ('../bad.py','/bad.py','x//bad.py','x/./bad.py','x\\bad.py','x\x00.py'):
            sources=dict(self.sources);sources[key]=hash_of('bad')
            with self.subTest(key=key),self.assertRaises(V.InvalidReceipt):V.source_map(sources)

    def test_source_pins_close_observer_production_bytes(self):
        for name in V.OBSERVER_CODE_PINS:
            sources=dict(self.sources);sources[V.PREFIX+'attention_packed_tiled_observation/'+name]=hash_of('changed')
            with self.assertRaises(V.InvalidReceipt):V.source_map(sources)
        # Generated observer pins are linked by the caller's complete source map.
        sources=dict(self.sources);sources[V.PREFIX+'attention_packed_tiled_observation/pins.json']=hash_of('rebound')
        V.source_map(sources)

    def test_reference_scope_and_typed_geometry_rejected_even_rebound(self):
        for path,value in [
            (('independent_reference','rows'),16),(('independent_reference','rows'),128.0),
            (('independent_reference','past_tokens'),1),(('independent_reference','past_tokens'),False),
            (('reference','oracle_execution_reused'),False),
            (('reference','fresh_provenance','new_official_forward_executed'),True),
            (('reference','fresh_provenance','original_m128_numerical_pass_inherited'),True),
            (('reference','fresh_provenance','native_result_sha256'),hash_of('other native')),
            (('reference','fresh_provenance','origin_before_after_unchanged'),False),
            (('input_spec','original_input','input_x_sha256'),hash_of('M16 input')),
            (('loaded_inputs','x','bytes'),16*1536*4),
            (('binaries','library_sha256'),hash_of('other library')),
            (('fresh_assets','profile'),'qwen2-public-pv16-packed-m16-linked-v1')]:
            self.r,self.s,self.sources=fixture(self.snapshot)
            obj=self.s
            for key in path[:-1]:obj=obj[key]
            obj[path[-1]]=value
            with self.subTest(path=path,value=value),self.assertRaises(V.InvalidReceipt):self.rebound()

    def test_fixed_metric_binds_frozen_late_reference(self):
        lookup=self.s['independent_reference']['fresh_lookup']
        lookup['raw_stages/phase_14_y_recipe.f32le']['sha256']=hash_of('late changed')
        self.s['independent_reference']['artifacts']=[dict(v,path=n) for n,v in lookup.items()]
        with self.assertRaisesRegex(V.InvalidReceipt,'FIXED_REFERENCE_HASH'):self.rebound()

    def test_no_reference_root_remap_or_path_traversal(self):
        for field,value in (('root','fresh'),('path','../escape'),('path','/absolute'),
                            ('path','./same'),('bytes',True),('bytes',4)):
            self.r,self.s,self.sources=fixture(self.snapshot)
            self.s['reference']['fresh_lookup']['raw_stages/silu.f32le'][field]=value
            with self.subTest(field=field),self.assertRaises(V.InvalidReceipt):self.rebound()

    def test_extra_critical_fields_are_rejected(self):
        paths=[(),('comparison',),('comparison','whole_outputs','y'),
            ('comparison','methods','official_self_cache','stages','y'),
            ('comparison','methods','official_self_cache','stages','y','metrics'),
            ('observation',),('observation','fields','dot_parts'),('observation','job'),
            ('observation','terminal'),('observation','accepted_retirement'),('execution',),
            ('execution','host'),('execution','host','launch_result'),('execution','host','accepted'),
            ('execution','host','completions',0),('execution','memory','outputs','y')]
        for path in paths:
            r=copy.deepcopy(self.r);obj=r
            for key in path:obj=obj[key]
            obj['unrecognized_malicious_field']={'script':'never execute this'}
            with self.subTest(path=path),self.assertRaises(V.InvalidReceipt):self.validate(r)
        for path in ((),('reference',),('independent_reference',),('reference','fresh_provenance'),
                     ('fresh_assets',),('binaries',),('loaded_inputs','x')):
            self.r,self.s,self.sources=fixture(self.snapshot);obj=self.s
            for key in path:obj=obj[key]
            obj['unknown']=1
            with self.subTest(snapshot_path=path),self.assertRaises(V.InvalidReceipt):self.rebound()

    def test_malicious_json_type_depth_and_duplicate_boundaries(self):
        raw_cases=(b'{"x":-Infinity}',b'{"x":18446744073709551616}',b'{"x":"\\ud800"}',
            b'{"\\udfff":0}',b'{"x":"\\u0000"}',b'{"x":0,"x":false}',
            b'{"a":{"x":0,"x":1}}',b'['+b'0,'*16384+b'0]')
        for raw in raw_cases:
            with self.subTest(raw=raw[:80]),self.assertRaises(V.InvalidReceipt):V.strict_json(raw)
        with self.assertRaises(V.InvalidReceipt):V.strict_json(b' '* (V.MAX_JSON+1))

    def test_errors_do_not_echo_private_data(self):
        self.r['status']='private/malicious/path'
        try:self.validate()
        except V.InvalidReceipt as exc:
            self.assertNotIn('private',str(exc));self.assertRegex(str(exc),'^[A-Z_]+$')
        else:self.fail('invalid receipt accepted')

    def test_actual_report_capacity_does_not_expand_control_bound(self):
        raw=V.encoded({'bounded_diagnostics':['x'*8192]*300})
        self.assertGreater(len(raw),V.MAX_CONTROL_JSON)
        self.assertEqual(len(V.strict_json(raw)['bounded_diagnostics']),300)
        with self.assertRaises(V.InvalidReceipt):V.strict_json(raw,max_bytes=V.MAX_CONTROL_JSON)
        self.summary.write_bytes(raw)
        V.read_bound(self.summary,V.sha(raw))
        with self.assertRaises(V.InvalidReceipt):V.read_bound(self.summary,V.sha(raw),max_bytes=V.MAX_CONTROL_JSON)
        for limit in (True,0,V.MAX_JSON+1):
            with self.subTest(limit=limit),self.assertRaises(V.InvalidReceipt):V.strict_json(b'{}',max_bytes=limit)

    def test_no_dut_or_native_imports(self):
        tree=ast.parse(Path(V.__file__).read_text())
        names={n.names[0].name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import)}
        names|={n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
        self.assertLessEqual(names,{'hashlib','json','math','os','pathlib','stat'})

if __name__=='__main__':unittest.main()
