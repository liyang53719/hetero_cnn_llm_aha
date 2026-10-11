"""Small FP32 oracle and state/credit tests; no RTL or real-prefill forward."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shared_sfu', ROOT/'scripts/qwen2_shared_sfu_schedule.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sample(groups=3):
    values = [0.0, -0.0, 0.1, -0.1, 1., -1., 79., -79., 80., -80.,
              0.5, -0.5, 30., -30., 1e-30, -1e-30]
    return ([[m.f32_bits(v+(batch/8 if v not in (0.,80.,-80.) else 0.)) for v in values]
             for batch in range(groups)], [[m.f32_bits(.25)]*16 for _ in range(groups)])


TIMING = dict(latency_cycles=12, initiation_interval_cycles=13)


def run(groups=3, contexts=2, **kwargs):
    gate, up = sample(groups)
    return m.schedule_silu(gate,up,contexts=contexts,divider_timing=TIMING,**kwargs)


def test_unbound_timing_is_never_a_prediction():
    g,u = sample(1)
    report = m.schedule_silu(g,u,contexts=2)
    assert report['status'] == 'TIMING_UNBOUND'
    assert report['scenario_cycles'] is report['predicted_full_block_cycles'] is report['rtl_measured_cycles'] is None
    assert not report['scope']['scalar_error_status_policy_validated']
    assert not report['scope']['numerical_acceptance']
    assert not report['scope']['hardfloat_flags_generated']
    assert report['profile_kind'] == 'candidate_context_schedule'
    assert report['all_outputs_acknowledged'] is None
    assert report['events'] == report['reservations'] == []
    assert report['work']['operations_per_lane']['alu'][:8] == [21]*8
    assert report['work']['operations_per_lane']['alu'][8:10] == [4,4]


@pytest.mark.parametrize('contexts', [1,2])
def test_node_dependencies_ordered_outputs_and_real_resource_exclusion(contexts):
    gates,ups = sample(4)
    report = m.schedule_silu(gates,ups,contexts=contexts,divider_timing=TIMING)
    assert report['status'] == 'SCENARIO_DRAINED'
    assert report['resources_drained'] and report['all_output_handshakes_completed']
    assert report['output_count'] == report['accepted_groups'] == report['retired_groups'] == 4
    assert report['peak_contexts'] == contexts
    assert report['predicted_full_block_cycles'] is None
    assert report['outputs'] == [dict(batch=b, value=[m.ordered_reference(gates[b][lane],ups[b][lane])['value']
                  for lane in range(16)],cycle=report['outputs'][b]['cycle']) for b in range(4)]
    writes = {}
    for event in report['events']:
        if event['event'] == 'writeback':
            writes.setdefault((event['batch'],event['lane']),[]).append(event)
    for (batch,lane),events in writes.items():
        reference = m.ordered_reference(gates[batch][lane],ups[batch][lane])['nodes']
        assert [(e['node'],e['value']) for e in events] == [(n['node'],n['value']) for n in reference]
        assert all(a['cycle'] < b['cycle'] for a,b in zip(events,events[1:]))
    intervals = {}
    for reservation in report['reservations']:
        intervals.setdefault(reservation['resource'],[]).append(reservation)
    for reservations in intervals.values():
        ordered = sorted(reservations,key=lambda x:x['start'])
        assert all(a['end'] <= b['start'] for a,b in zip(ordered,ordered[1:]))
    all_writes = [(e['cycle'],e['lane']) for e in report['events'] if e['event']=='writeback']
    assert len(set(all_writes)) == len(all_writes), 'single physical lane write port double booked'
    live = {}
    for event in report['events']:
        if event['event'] == 'input_fire':
            assert event['slot'] not in live
            live[event['slot']] = (event['batch'],event['generation'])
        elif event['event'] == 'issue':
            assert live[event['slot']] == (event['batch'],event['generation'])
        elif event['event'] == 'context_release':
            assert event['reason']=='output_fire'
            assert live.pop(event['slot'])[0] == event['batch']
    assert not live


def test_two_contexts_overlap_divider_wait_without_extra_alu_ports():
    one,two = run(contexts=1),run(contexts=2)
    assert two['scenario_cycles'] < one['scenario_cycles']
    assert [x['value'] for x in two['outputs']] == [x['value'] for x in one['outputs']]
    overlap = False
    for div in two['reservations']:
        if div['resource'].startswith('silu.divider'):
            alu_resource = div['resource'].replace('divider','alu')
            overlap |= any(a['resource']==alu_resource and a['batch']!=div['batch'] and
                           div['start'] <= a['start'] < div['end'] for a in two['reservations'])
    assert overlap
    assert any(e['event']=='alu_blocked_by_divider' for e in two['events'])
    for event in two['events']:
        if event['event']=='alu_blocked_by_divider':
            assert not any(r['resource']==f"silu.alu.{event['lane']:02d}" and r['start']==event['cycle']
                           for r in two['reservations'])


def test_output_backpressure_holds_data_and_contexts_until_fire():
    blocked = run(groups=5, output_ready=lambda _:False,max_cycles=160)
    assert blocked['status']=='SCENARIO_LIMIT_REACHED'
    assert blocked['scenario_cycles'] is None and not blocked['resources_drained']
    assert blocked['accepted_groups']==2 and blocked['outputs']==[]
    offers = [e for e in blocked['events'] if e['event']=='output_offer']
    assert len(offers)>10 and {e['batch'] for e in offers} == {0}
    assert all(e['value']==offers[0]['value'] for e in offers)
    assert not any(e['event']=='context_release' for e in blocked['events'])
    released = run(groups=5, output_ready=lambda cycle:cycle>=160 and cycle%5==0)
    assert released['status']=='SCENARIO_DRAINED'
    assert [o['batch'] for o in released['outputs']]==list(range(5))
    assert released['outputs'][0]['cycle']>=160
    terminal = released['events'][-1]
    assert terminal['event']=='terminal'
    assert terminal['cycle']>=max(r['end'] for r in released['reservations'])


@pytest.mark.parametrize('fault', ['numerical','tag','underflow'])
def test_poison_drains_all_accepted_dividers_without_success_publication(fault):
    options = ({'injected_errors':{(0,0,'reciprocal')}} if fault=='numerical' else
               {'corrupt_divider_tags':{(0,0)}} if fault=='tag' else
               {'injected_flags':{(0,0,'reciprocal'):3}})
    report = run(groups=5,**options)
    assert report['status']=='POISON_DRAINED' and report['resources_drained']
    assert report['outputs']==[] and not report['all_output_handshakes_completed']
    assert report['poison']['kind']==('divider_tag' if fault=='tag' else 'numerical_injected')
    poisoned = next(i for i,e in enumerate(report['events']) if e['event']=='poison')
    assert not any(e['event'] in ('issue','input_fire','output_fire') for e in report['events'][poisoned+1:])
    issued = sum(e['event']=='issue' and e['node']=='reciprocal' for e in report['events'])
    returned = sum(e['event']=='divider_return' for e in report['events'])
    assert issued==returned and issued>1
    assert all(e['reason']=='poison_drain' for e in report['events'] if e['event']=='context_release')


def test_injected_flags_preserve_policy_without_claiming_automatic_flag_validation():
    # Original ExpNegative ignores internal flags; NX alone is allowed for Add.
    accepted = run(groups=1,injected_flags={(0,0,'exp_scale'):3,(0,0,'denominator'):1})
    assert accepted['status']=='SCENARIO_DRAINED'
    assert not accepted['numerical_acceptance']
    rejected = run(groups=1,injected_flags={(0,0,'denominator'):3})
    assert rejected['status']=='POISON_DRAINED'
    assert not rejected['outputs']
    # A finite result can carry UF; the test checks supplied status routing.
    w = next(e for e in rejected['events'] if e['event']=='writeback' and e['node']=='denominator' and e['lane']==0)
    assert w['value']==m.f32_bits(2.0) and w['flags']==3


def test_resource_state_ledger_is_explicit_and_not_double_borrowed():
    a,b = m.resource_budget(1),m.resource_budget(2)
    assert a['added_arithmetic_units']==b['added_arithmetic_units']==0
    assert a['divider_result_queue_entries']==b['divider_result_queue_entries']==0
    assert a['extra_context_bits']==0 and b['extra_context_bits']==2896
    assert b['extra_batch_ordinal_bits']==20 and b['divider_owner_bits']==32
    assert b['added_logical_register_bits']==2950
    assert sum(b['context_fields_bits'].values())==181
    assert b['output_offer_valid_bits']==1
    assert b['output_offer_context_bits']==1
    assert 'waiting_divider is derived' in b['derived_control']
    assert b['write_ports_per_lane']==b['alu_issue_ports_per_lane']==1
    assert 'NOT also borrowed' in b['allocation']


def test_later_context_fault_cannot_withdraw_an_earlier_stalled_offer():
    g=[[m.f32_bits(80.)]*16,[m.ONE]*16]
    u=[[m.ONE]*16 for _ in g]
    fault={(1,0,'up_multiply')}
    blocked=m.schedule_silu(g,u,contexts=2,divider_timing=TIMING,
        output_ready=lambda _:False,injected_errors=fault,max_cycles=90)
    assert blocked['status']=='SCENARIO_LIMIT_REACHED'
    assert blocked['poison']['kind']=='numerical_injected'
    assert not blocked['resources_drained'] and blocked['outputs']==blocked['output_drains']==[]
    assert blocked['pending_output_offer']['batch']==0
    offers=[e for e in blocked['events'] if e['event']=='output_offer']
    assert offers[0]['cycle'] < blocked['poison']['cycle'] < offers[-1]['cycle']
    assert all(e['batch']==0 and e['value']==offers[0]['value'] for e in offers)
    assert not any(e['event']=='context_release' for e in blocked['events'])
    drained=m.schedule_silu(g,u,contexts=2,divider_timing=TIMING,
        output_ready=lambda cycle:cycle>=90,injected_errors=fault)
    assert drained['status']=='POISON_DRAINED' and drained['resources_drained']
    assert drained['outputs']==[] and [x['batch'] for x in drained['output_drains']]==[0]
    assert drained['output_drains'][0]['value']==offers[0]['value']
    assert not drained['all_output_handshakes_completed']
    fire=next(e for e in drained['events'] if e['event']=='output_fire')
    assert fire['cycle']==90 and fire['poisoned_drain']
    release=next(e for e in drained['events'] if e['event']=='context_release' and e['batch']==0)
    assert release['cycle']==fire['cycle'] and release['reason']=='output_fire'


def test_numeric_oracle_overflow_is_diagnostic_rejection_and_drains_without_invented_flags():
    g=[[m.f32_bits(2.)]*16,[m.ONE]*16]
    u=[[0x7f7fffff]*16,[m.ONE]*16]
    report=m.schedule_silu(g,u,contexts=2,divider_timing=TIMING,
        injected_flags={(0,0,'up_multiply'):5})
    assert report['status']=='DIAGNOSTIC_DOMAIN_REJECTED_DRAINED'
    assert report['resources_drained'] and report['poison']['kind']=='numeric_oracle_domain'
    assert report['outputs']==[] and not report['numerical_acceptance']
    assert not any(e['event']=='writeback' and e['batch']==0 and e['lane']==0
                   and e['node']=='up_multiply' for e in report['events'])
    assert sum(e['event']=='issue' and e['node']=='reciprocal' for e in report['events']) == sum(
        e['event']=='divider_return' for e in report['events'])


def test_invalid_profiles_domains_and_source_drift_are_rejected(tmp_path):
    g,u=sample(1)
    for timing in ({'latency_cycles':3}, {'latency_cycles':4,'initiation_interval_cycles':3},
                   {'latency_cycles':True,'initiation_interval_cycles':3}):
        with pytest.raises(ValueError):m.schedule_silu(g,u,divider_timing=timing)
    with pytest.raises(ValueError):m.schedule_silu(g,u,contexts=3)
    with pytest.raises(ValueError):m.schedule_silu(g*65,u*65)
    with pytest.raises(ValueError):m.schedule_silu([[0x7f800000]*16],u)
    with pytest.raises(ValueError):m.schedule_silu(g,[u[0][:-1]])
    for name in m.SOURCE_PINS:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    changed=tmp_path/'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala'
    changed.write_text(changed.read_text()+'\n// source identity mutation\n')
    with pytest.raises(ValueError,match='source identity changed'):m.verify_sources(tmp_path)


def test_cli_defaults_to_unbound_and_refuses_accidental_large_run(tmp_path):
    output=tmp_path/'result.json'
    subprocess.run([sys.executable,str(ROOT/'scripts/qwen2_shared_sfu_schedule.py'),'--out',str(output)],check=True)
    report=json.loads(output.read_text())
    assert report['status']=='TIMING_UNBOUND'
    run=subprocess.run([sys.executable,str(ROOT/'scripts/qwen2_shared_sfu_schedule.py'),'--groups','71680'],capture_output=True,text=True)
    assert run.returncode!=0 and 'no full M128 microstep runs' in run.stderr


def test_frozen_cpp_helpers_match_every_rounding_node_and_signed_zero(tmp_path):
    recipe=m._load('shared_sfu_frozen_recipe','scripts/qwen2_block_recipe_model.py')
    helpers,_,identity=recipe.extract_sources(ROOT)
    arithmetic=recipe.section(helpers,'static uint32_t bits','struct Stage')
    # Instrument the frozen source itself; do not replace its exp polynomial.
    arithmetic=arithmetic.replace('static float add(float a,float b){return a+b;}',
        'static float add(float a,float b){float v=a+b;trace.push_back(bits(v));return v;}')
    arithmetic=arithmetic.replace('static float mul(float a,float b){return a*b;}',
        'static float mul(float a,float b){float v=a*b;trace.push_back(bits(v));return v;}')
    arithmetic=arithmetic.replace('unsigned k=unsigned(z);','unsigned k=unsigned(z);trace.push_back(k);')
    source=r'''#include <cstdint>
#include <cstring>
#include <cmath>
#include <cfenv>
#include <iostream>
#include <vector>
#include <xmmintrin.h>
static std::vector<uint32_t> trace;
'''+arithmetic+r'''
int main(){
  if(std::fesetround(FE_TONEAREST)!=0)return 2;
  _mm_setcsr(_mm_getcsr() & ~((1u<<15)|(1u<<6)));
  uint32_t gb,ub;
  while(std::cin>>gb>>ub){
    trace.clear();float g=fp(gb),u=fp(ub),e=expneg(g);
    if(std::abs(g)>=80)trace.push_back(bits(e));
    float d=add(1.0f,e),r=1.0f/d;trace.push_back(bits(r));
    float s=mul(r,std::signbit(g)?e:1.0f),v=mul(mul(s,g),u);
    std::cout<<bits(v);for(auto x:trace)std::cout<<" "<<x;std::cout<<"\n";
  }
}
'''
    cpp=tmp_path/'sfu_oracle.cpp';binary=tmp_path/'sfu_oracle';cpp.write_text(source)
    subprocess.run(['g++',*recipe.FLAGS,str(cpp),'-o',str(binary)],check=True,capture_output=True,text=True)
    gates,ups=sample(2)
    pairs=[(g,u) for gg,uu in zip(gates,ups) for g,u in zip(gg,uu)]
    pairs += [(0x80000000,m.ONE),(0x00000001,m.ONE),(0x80000001,m.ONE),
              (m.f32_bits(80)-1,m.f32_bits(.125)),(m.f32_bits(-80)-1,m.f32_bits(.125))]
    oracle=subprocess.run([str(binary)],input=''.join(f'{g} {u}\n' for g,u in pairs),
                          capture_output=True,text=True,check=True)
    lines=oracle.stdout.splitlines();assert len(lines)==len(pairs)
    for (g,u),line in zip(pairs,lines):
        expected=list(map(int,line.split()));actual=m.ordered_reference(g,u)
        assert actual['value']==expected[0]
        assert [x['value'] for x in actual['nodes']]==expected[1:]
    assert m.ordered_reference(0x80000000,m.ONE)['value']==0x80000000
    assert identity['section_sha256']==recipe.SECTION_SHA256
