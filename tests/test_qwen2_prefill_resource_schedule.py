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
