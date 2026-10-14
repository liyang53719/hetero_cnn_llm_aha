import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('resource_schedule',ROOT/'scripts/qwen2_prefill_resource_schedule.py')
m=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


@pytest.mark.parametrize('tokens,contexts',[(128,1),(1024,5)])
def test_full_stage_coverage_and_existing_source_counts(tokens,contexts):
    r=m.report(ROOT,tokens,contexts)
    x=r['reservation_result']
    assert r['status']=='UNBOUND_RESOURCE_RESERVATION_MODEL'
    assert len(r['stages'])==len(x['completed_owners'])==19
    assert [p for s in r['stages'] for p in s['public_stages']]==[
        'input_norm','q','q_bias','q_rope','k','k_bias','k_rope','v','v_bias',
        'kv_append','qk','softmax','pv','oproj','attn_residual','post_norm',
        'gate','up','silu_mul','down','residual']
    bound=m.BOUND.calculate(tokens)
    assert x['metrics']['useful_macs']==bound['total_useful_macs']
    assert x['metrics']['dense_weight_read_bytes']==bound['weight_ingress_bytes']
    assert x['metrics']['external_write_bytes']==x['metrics']['acknowledged_write_bytes']
    assert x['metrics']['executed_macs']>=x['metrics']['useful_macs']
    assert x['metrics']['silu_vector_groups']==tokens*8960//16
    assert x['metrics']['silu_lane_primitive_groups']==3360*tokens
    # Source formula: 2 Norm = 3656M scalar+vector issues, QKV bias 128M,
    # Q/K RoPE 336M, two elementwise residuals 192M.
    stages=x['stage_metrics']
    norms=[stages[n] for n in ('input_norm','post_norm')]
    norm_issues=sum(sum(v for k,v in s.items() if k.endswith('_requests')) for s in norms)
    assert norm_issues==3656*tokens
    assert sum(stages[n]['core_vector_requests'] for n in ('q_bias','k_bias','v_bias'))==128*tokens
    assert sum(stages[n]['core_vector_requests'] for n in ('q_rope','k_rope'))==336*tokens
    assert sum(stages[n]['elementwise_vector_requests'] for n in ('attn_residual','residual'))==192*tokens
    attention=stages['attention']
    expected=m.ATT.calculate(tokens,contexts)
    assert attention['useful_macs']==expected['macs']['useful_total']
    assert sum(v for k,v in attention.items() if k.startswith('scalar_') and k.endswith('_requests'))==expected['attention_bounds']['required_scalar_requests_lower_bound']
    assert attention['external_read_bytes']+attention['external_write_bytes']==expected['traffic']['external_total_bytes']
    assert x['timing_work_units']['command_admission']==21
    assert x['timing_work_units']['owner_switch']==19
    assert x['timing_work_units']['terminal_fence']==1
    assert x['synthetic_scheduled_cycles'] is None
    assert r['unbound_timing_parameters']==list(m.TIMING_KEYS)
    assert not any(r['scope'].values())
    assert r['predicted_full_block_cycles'] is r['rtl_measured_cycles'] is r['rtl_measured_utilization'] is None
    assert r['unresolved_traffic']['command_tensor_policy_metadata_bytes'] is None
    assert r['attention_schedule']['qk_contexts']==contexts
    assert r['known_sfu_source_lower_bounds']['silu16_any_nonsaturated_group_ii_at_least']==38
    assert r['known_sfu_source_lower_bounds']['scalar_div_actual_latency_and_ii'] is None
    assert r['dense_weight_bank_layout']['reserved_bytes_per_live_half']==40960
    for pool,peak in x['peak_owned'].items(): assert peak<=m.CAPACITIES[pool]


def test_small_synthetic_scenario_closes_owned_buffers_and_terminal_ack():
    profile=m.timing_profile(True)
    result=m.Scheduler(profile).run(m.iter_events(2,5),require_terminal=True)
    assert result['synthetic_scheduled_cycles']>0
    assert result['synthetic_scheduled_cycles']==sum(
        count*profile['parameters'][key] for key,count in result['timing_work_units'].items())
    assert result['successful_path_ownership_closed']
    assert result['peak_owned']['metadata']==5
    assert result['peak_owned']['contexts']==5
    assert result['peak_owned']['matrix_results']==1
    assert result['peak_owned']['idma_transaction']==1
    assert result['peak_owned']['silu_inputs']==result['peak_owned']['silu_outputs']==1
    intervals=result['sample_reservations']
    assert all(a['end']<=b['start'] for a,b in zip(intervals,intervals[1:]))


def test_repeat_preserves_ordered_body_and_matches_explicit_small_execution():
    body=[m.acquire('tile','core_bytes',64),
          m.op('read',('idma',),{'read_64b_service':1},{'external_read_bytes':64}),
          m.op('compute',('scalar',),{'scalar_add':2}),m.release('tile')]
    profile=m.timing_profile(True)
    compact=m.Scheduler(profile).run([m.repeat(3,body,'test')])
    expanded=m.Scheduler(profile).run(body*3)
    for key in ('synthetic_scheduled_cycles','metrics','timing_work_units','peak_owned'):
        assert compact[key]==expanded[key]
    with pytest.raises(m.ReservationError,match='leaks'):
        m.Scheduler().run([m.repeat(2,[m.acquire('leak','core_bytes',64)],'bad')])


def test_conflicting_reservations_and_unaudited_overlap_are_rejected():
    book=m.ReservationBook()
    book.reserve(('A.bank0',),5,label='read')
    with pytest.raises(m.ReservationError,match='double reservation'):
        book.reserve(('A.bank0',),1,start=4)
    with pytest.raises(m.ReservationError,match='overlap'):
        book.reserve(('A.bank1',),1,start=4)
    with pytest.raises(m.ReservationError,match='unknown physical'):
        book.reserve(('imaginary_port',),1)


def begin():
    return dict(event='owner_begin',name='test',requires=['x'],public_stages=['test'])


def test_missing_write_ack_and_early_buffer_release_are_model_errors():
    scheduler=m.Scheduler()
    scheduler.execute(begin())
    scheduler.execute(m.acquire('output','core_bytes',64))
    scheduler.execute(dict(event='write',tag='pending',bytes=64))
    with pytest.raises(m.ReservationError,match='until its ACK'):
        scheduler.execute(m.release('output'))
    with pytest.raises(m.ReservationError,match='IDMA reused'):
        scheduler.execute(m.read_span(64))
    with pytest.raises(m.ReservationError,match='final ACK'):
        scheduler.execute(dict(event='owner_end',name='test',produces=['y']))
    scheduler.execute(dict(event='ack',tag='pending'))
    scheduler.execute(m.release('output'))
    scheduler.execute(dict(event='owner_end',name='test',produces=['y']))
    with pytest.raises(m.ReservationError,match='missing terminal'):
        scheduler.run([],require_terminal=True)
    scheduler.execute(dict(event='block_done'))
    assert scheduler.run([],require_terminal=True)['successful_path_ownership_closed']
    with pytest.raises(m.ReservationError,match='after terminal'):
        scheduler.execute(m.op('extra'))


def test_capacity_context_reuse_and_uncommitted_dependency_are_rejected():
    with pytest.raises(m.ReservationError,match='capacity'):
        m.Scheduler().execute(m.acquire('extra','contexts',6))
    scheduler=m.Scheduler()
    scheduler.execute(m.acquire('ctx','contexts',1))
    scheduler.execute(m.acquire('pending','metadata',1))
    with pytest.raises(m.ReservationError,match='Matrix drain'):
        scheduler.execute(m.release('ctx'))
    with pytest.raises(m.ReservationError,match='duplicate allocation'):
        scheduler.execute(m.acquire('ctx','contexts',1))
    with pytest.raises(m.ReservationError,match='consumer before'):
        m.Scheduler().execute(dict(event='owner_begin',name='o',requires=['att'],public_stages=['o']))


def test_timing_cannot_silently_become_hardware_prediction():
    profile=m.timing_profile(True)
    profile['synthetic']=False
    with pytest.raises(m.ReservationError,match='only permits explicit synthetic'):
        m.Scheduler(profile)
    profile=m.timing_profile()
    profile['parameters']['scalar_div']=9
    result=m.Scheduler(profile).run([m.scalar('div')])
    assert result['synthetic_scheduled_cycles'] is None
    assert result['sample_reservations']==[]
    profile['parameters'].pop('write_64b_ack')
    with pytest.raises(m.ReservationError,match='every timing key'):
        m.Scheduler(profile)


def test_dense_groups_keep_existing_row_capacity_and_five_context_limit():
    for k,n in [(1536,8960),(8960,1536)]:
        groups=list(m.dense_groups(128,k,n))
        assert all(g['contexts']<=5 for g in groups)
        assert all(g['a_words_per_bank']<=1376 and g['b_words_per_bank']<=80 for g in groups)
        for g in groups:
            addresses={d*5+c for d in range(16) for c in range(g['n_contexts'])}
            assert len(addresses)==g['b_payload_words_per_bank']
            assert max(addresses)+1==g['b_high_water_words_per_half']
            assert g['b_words_per_bank']==80
            assert max(addresses)<80
            assert max(a+80 for a in addresses)<160
        assert max(g['rows'] for g in groups)==(80 if k==1536 else 32)
        assert sum(g['rows']*g['n_contexts']*g['columns']*k for g in groups)==128*k*n
        assert sum(g['n_contexts']*g['columns']*k*2 for g in groups)==k*n*2*(2 if k==1536 else 4)


def test_source_drift_and_cli_default_report(tmp_path):
    with pytest.raises(ValueError,match='source changed'):
        m.report(tmp_path)
    output=tmp_path/'reports'/'m128.json'
    subprocess.run([sys.executable,str(ROOT/'scripts/qwen2_prefill_resource_schedule.py'),
                    '--tokens','128','--out',str(output)],check=True,capture_output=True,text=True)
    r=json.loads(output.read_text())
    assert r['reservation_result']['synthetic_scheduled_cycles'] is None
    assert not r['resources']['overlap_enabled']
    assert r['resources']['silu_scalar_lanes']==16
    assert len(r['source_sha256'])>=len(m.ATT.SOURCE_PINS)


def test_resource_set_serialization_is_stable_across_python_hash_seeds():
    import os
    code = """
import importlib.util,json
from pathlib import Path
p=Path('scripts/qwen2_prefill_resource_schedule.py')
s=importlib.util.spec_from_file_location('resource_model',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
b=m.ReservationBook();b.reserve(m.RESOURCES,3,label='all_ports')
print(json.dumps(b.samples,sort_keys=True))
"""
    outputs = [subprocess.check_output([sys.executable, '-c', code], cwd=ROOT,
               env=dict(os.environ, PYTHONHASHSEED=seed), text=True)
               for seed in ('1', '713')]
    assert outputs[0] == outputs[1]
    sample = json.loads(outputs[0])[0]
    assert sample['resources'] == sorted(m.RESOURCES)
    assert sample['start'] == 0 and sample['end'] == 3


def test_primitive_source_timing_does_not_bind_full_owner_macros():
    r=m.report(ROOT,128,1)
    binding=r['known_sfu_source_timing']
    assert binding['upstream']['commit']=='c1105e6ac6a0dd90fc80893efc4830ab609005d3'
    assert binding['scalar_wrapper']['add_mul']==[1,2,3]
    assert binding['scalar_wrapper']['div']==['D+1','D+2','D+3']
    assert binding['primitive_divider']['same_edge_output_sample_and_next_input']
    assert binding['silu_wrapper']['edge_span_formula']=='45*N+17*L+Qsum-1'
    assert not binding['scope']['rtl_calibrated']
    assert not binding['scope']['numerical_acceptance']
    assert r['known_sfu_source_lower_bounds']['version']=='v1_loose_wrapper_bounds_preserved'
    assert all(x is None for x in r['timing_profile']['parameters'].values())
    assert r['reservation_result']['synthetic_scheduled_cycles'] is None
    assert r['predicted_full_block_cycles'] is r['rtl_measured_cycles'] is None
    assert r['source_sha256']['scripts/qwen2_shared_sfu_schedule.py']==binding['model_source_sha256']


def test_saved_v0_silu_refines_only_original_host_term_without_double_count():
    r=m.observed_silu_host_bound(ROOT)
    assert r['previous']['cycles_lower_bound']==9127424
    assert r['terms']==dict(removed_old_silu_floor=430080,
        new_silu_arithmetic_edge_span=4515839,
        unchanged_other_non_dense_lower_bound=4912640,
        current_dense_lower_bound=3784704,ideal_dense_lower_bound=1462272)
    assert r['whole_block_cycles_lower_bound']==13213183
    assert r['ideal_dense_whole_block_cycles_lower_bound']==10890751
    assert r['useful_macs']==6014828544 and r['fixed_matrix_macs_per_cycle']==4096
    assert r['useful_utilization_upper_bound']==pytest.approx(0.111136279577903)
    assert r['whole_block_cycles_lower_bound']==(
        r['previous']['cycles_lower_bound']-r['terms']['removed_old_silu_floor']+
        r['terms']['new_silu_arithmetic_edge_span'])
    assert not any(r['scope'].values())
    assert r['predicted_full_block_cycles'] is r['rtl_measured_cycles'] is None
    assert r['evidence']['producer_status']=='DIAGNOSTIC_NOT_ACCEPTED'


def test_saved_silu_census_drift_and_wrong_cli_scope_are_rejected(tmp_path):
    target=tmp_path/m.V0_SILU_AUDIT;target.parent.mkdir(parents=True)
    target.write_text('{}\n')
    with pytest.raises(ValueError,match='branch evidence changed'):
        m.observed_silu_host_bound(tmp_path)
    for flags in (['--tokens','1024'],['--contexts','5'],['--synthetic-profile']):
        run=subprocess.run([sys.executable,str(ROOT/'scripts/qwen2_prefill_resource_schedule.py'),
            '--observed-silu-host-bound',*flags],capture_output=True,text=True)
        assert run.returncode!=0 and 'requires cold M128' in run.stderr


def test_resident_m128_candidate_full_dag_capacity_traffic_and_final_ack():
    r=m.report(ROOT,128,5,dense_mapping='resident_m128_nc3')
    x=r['reservation_result'];metrics=x['metrics'];phases=r['resident_dense_phases']
    assert len(x['completed_owners'])==19 and x['successful_path_ownership_closed']
    assert metrics['useful_macs']==6014828544
    assert metrics['dense_wide_issues']==1462272
    assert metrics['dense_weight_read_bytes']==93585408
    assert metrics['dense_activation_read_bytes']==13893632
    assert metrics['dense_partial_store_bytes']==metrics['dense_partial_restore_bytes']==81788928
    assert sum(p['external_d_fp32_write_bytes'] for p in phases)==11796480
    assert metrics['external_read_bytes']==128188416
    assert metrics['external_write_bytes']==metrics['acknowledged_write_bytes']==22544384
    assert x['peak_owned']['A_bytes']==524288 and x['peak_owned']['B_bytes']==262144
    assert x['peak_owned']['contexts']==5 and x['peak_owned']['metadata']<=8
    assert x['peak_owned']['matrix_results']==x['peak_owned']['dense_final_values']==1
    assert sum(r['resources']['capacities'][k] for k in ('A_bytes','B_bytes'))==768*1024
    assert r['attention_schedule']['used_a_bytes']==168*512
    assert r['attention_schedule']['used_b_bytes']==160*512
    assert r['attention_schedule']['allocated_a_bytes']==1024*512
    assert r['attention_schedule']['allocated_b_bytes']==512*512
    assert r['predicted_full_block_cycles'] is r['rtl_measured_cycles'] is None
    assert not any(r['scope'].values())
    assert not r['resources']['overlap_enabled']
    assert not any(p['accumulator_seed_interface_implemented'] for p in phases)
    floors=r['resource_issue_floors']
    assert floors['independent_resource_floors']['idma_64b_read_write']==2355200
    assert floors['independent_resource_floors']['scalar_requests']==2476288
    assert floors['serial_owners_cycles_lower_bound']==4944128
    assert floors['useful_utilization_upper_bound']==pytest.approx(0.2970117278517061)
    assert floors['serial_owners_cycles_lower_bound']==sum(
        max(s['resource_cycle_floors'].values()) for s in floors['serial_owner_floors'])
    assert not floors['primitive_latency_binding_applied']


def test_resident_dense_tile_order_capacity_and_three_tile_down_reuse():
    for name,k,n in m.BOUND.MATRICES:
        p=m.resident_dense_plan(128,k,n)
        assert p['a_c_words_per_bank']==(896 if name=='down' else 1024)
        assert p['b_words_per_bank']==512
        assert p['n_tiles_retained']==(3 if name=='down' else 1)
        for objects in (p['a_c_objects'],p['b_objects']):
            assert all(x['end_word']<=y['start_word'] for x,y in zip(objects,objects[1:]))
        cursors={}
        for tile in m.resident_dense_tiles(128,k,n):
            assert tile['contexts'] in (5,3)
            for row in range(tile['m_base'],tile['m_base']+tile['rows'],16):
                key=(row,tile['nbase'])
                assert cursors.get(key,0)==tile['kbase']
                assert tile['restore']==(tile['kbase']!=0)
                cursors[key]=tile['kbase']+256
                assert tile['final']==(cursors[key]==k)
        assert len(cursors)==8*(n//256) and set(cursors.values())=={k}
    down=m.resident_dense_plan(128,8960,1536)
    assert down['external_a_fp32_read_bytes']==128*8960*4*2
    assert down['partial_restore_bytes']==down['partial_store_bytes']==26738688
    assert sum(p['external_a_fp32_read_bytes']+p['external_weight_bf16_read_bytes']+
               p['external_d_fp32_write_bytes'] for p in
               [m.resident_dense_plan(128,k,n) for _,k,n in m.BOUND.MATRICES])==119275520
    # All six down C tiles alone consume the entire 768 KiB budget; A/B cannot fit.
    assert 128*1536*4+128*256*2+2*256*256*2>768*1024
    with pytest.raises(m.ReservationError,match='M128|partition'):
        m.report(ROOT,1024,5,dense_mapping='resident_m128_nc3')


def test_fp32_prefix_seed_preserves_order_and_independent_block_sums_do_not():
    import struct
    a=[0]*1536;a[0]=0x4b800000;a[256]=0x3f800000;a[257]=0xcb800000
    sequential=0
    for value in a:sequential=m.ATT.fp32_fma_bits(value,0x3f800000,sequential)
    seeded=0;independent=0
    for kb in range(0,len(a),256):
        # Exact FP32 snapshot roundtrip, not BF16 conversion or block summation.
        seeded=struct.unpack('<I',struct.pack('<I',seeded))[0]
        partial=0
        for value in a[kb:kb+256]:
            seeded=m.ATT.fp32_fma_bits(value,0x3f800000,seeded)
            partial=m.ATT.fp32_fma_bits(value,0x3f800000,partial)
        independent=m.ATT.fp32_add_bits(independent,partial)
    assert seeded==sequential==0 and independent==0x3f800000


def test_resident_prefix_lifetime_missing_store_ack_and_wrong_k_are_rejected():
    events=[begin(),*m.resident_dense_events(128,1536,256),
            dict(event='owner_end',name='test',produces=['y']),dict(event='block_done')]
    def run(seq):return m.Scheduler(dense_mapping='resident_m128_nc3').run(seq,require_terminal=True)
    assert run(events)['metrics']['acknowledged_write_bytes']==128*256*4
    bad=[dict(e) for e in events]
    first=next(i for i,e in enumerate(bad) if e['event']=='dense_prefix_begin')
    bad[first]['kbase']=256
    with pytest.raises(m.ReservationError,match='prefix restore'):run(bad)
    bad=list(events)
    index=next(i for i,e in enumerate(bad) if e.get('label')=='candidate_FP32_prefix_store_before_context_reuse')
    del bad[index]
    with pytest.raises(m.ReservationError,match='sink completion'):run(bad)
    bad=list(events);index=next(i for i,e in enumerate(bad) if e['event']=='ack');del bad[index]
    with pytest.raises(m.ReservationError,match='before ACK'):run(bad)
    bad=list(events);bad.insert(first+1,m.release('resident_C'))
    with pytest.raises(m.ReservationError,match='C lease release'):run(bad)
    bad=list(events);bad.insert(first+1,m.release('dense_contexts'))
    with pytest.raises(m.ReservationError,match='contexts reused'):run(bad)
    bad=[dict(e) for e in events]
    second=next(i for i,e in enumerate(bad[first+1:],first+1) if e['event']=='dense_prefix_begin')
    bad[second]['c_word_address']=bad[first]['c_word_address']
    with pytest.raises(m.ReservationError,match='physical bank span alias'):run(bad)
    bad=list(events)
    store=next(i for i,e in enumerate(bad) if e['event']=='write')
    assert bad[store+1]['event']=='ack'
    del bad[store:store+2]
    with pytest.raises(m.ReservationError,match='sink completion'):run(bad)
    bad=[e for e in events if e.get('label')!='candidate_FP32_seed_restore_before_compute']
    with pytest.raises(m.ReservationError,match='before exact FP32 seed restore'):run(bad)
    bad=[dict(e) for e in events]
    for e in bad:
        if e['event'] in ('dense_prefix_begin','dense_prefix_commit') and e['m_base']==16:e['m_base']=128
    with pytest.raises(m.ReservationError,match='logical tile range'):run(bad)
    bad=list(events);index=next(i for i,e in enumerate(bad) if e.get('label')=='resident_Dense_last_K_of_chunk');del bad[index]
    with pytest.raises(m.ReservationError,match='capture before completed context'):run(bad)
    for label in ('candidate_FP32_prefix_store_before_context_reuse','write'):
        bad=list(events)
        index=next(i for i,e in enumerate(bad) if e.get('label')==label or e['event']==label)
        moved=bad[index:index+(2 if label=='write' else 1)]
        del bad[index:index+len(moved)]
        before=next(i for i,e in enumerate(bad) if e.get('label')=='resident_Dense_increasing_K_prefix')
        bad[before:before]=moved
        with pytest.raises(m.ReservationError,match='before .*captured context'):run(bad)


def test_saved_v0_review_keeps_historical_and_current_identities_separate():
    r = m.observed_silu_host_bound(ROOT)
    review = r['evidence']['source_review']
    assert review['commit'] == 'f16df50adfb0f1f4bc668c517a2e29accffe6753'
    assert not review['h2048_borrower_included']
    for path, pair in m.V0_HOST_SOURCE_REVIEW.items():
        assert review['historical_hardware_sha256'][path] == pair['historical_sha256']
        assert review['current_hardware_sha256'][path] == pair['current_sha256']
        assert r['source_sha256'][path] == pair['current_sha256']
        assert pair['historical_sha256'] != pair['current_sha256']
    raw = (ROOT/m.V0_SILU_AUDIT).read_bytes()
    assert m.hashlib.sha256(raw).hexdigest() == m.V0_SILU_AUDIT_SHA256


@pytest.mark.parametrize('name', ['Qwen2Block.scala', 'QwenOwnerProtocol.scala'])
def test_saved_v0_review_rejects_other_old_or_current_sources(tmp_path, name):
    path = m.ATT.BASE+name
    pair = m.V0_HOST_SOURCE_REVIEW[path]
    target = tmp_path/path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((ROOT/path).read_bytes())
    assert m._current_v0_hardware_pins(tmp_path, {path: pair['historical_sha256']}) == {
        path: pair['current_sha256']}
    with pytest.raises(ValueError, match='reviewed historical source changed'):
        m._current_v0_hardware_pins(tmp_path, {path: '0'*64})
    target.write_text('// changed current default or control\n')
    with pytest.raises(ValueError, match='hardware source changed'):
        m._current_v0_hardware_pins(tmp_path, {path: pair['historical_sha256']})


def test_saved_v0_review_does_not_relax_unreviewed_source_pins(tmp_path):
    path = m.ATT.BASE+'VectorSilu.scala'
    target = tmp_path/path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((ROOT/path).read_bytes())
    expected = m.SFU.SOURCE_PINS[path]
    assert m._current_v0_hardware_pins(tmp_path, {path: expected}) == {path: expected}
    target.write_text('// altered SiLU arithmetic\n')
    with pytest.raises(ValueError, match='hardware source changed'):
        m._current_v0_hardware_pins(tmp_path, {path: expected})


@pytest.mark.parametrize('kwargs', [
    {'enable_h2048_rms_borrower': True}, {'external_elementwise_loan': True},
    {'enable_h2048_rms_borrower': 0}, {'external_elementwise_loan': None},
])
def test_saved_v0_review_rejects_nondefault_or_malformed_profile(kwargs):
    with pytest.raises(ValueError, match='default-disabled borrower/loan profile'):
        m.observed_silu_host_bound(ROOT, **kwargs)
