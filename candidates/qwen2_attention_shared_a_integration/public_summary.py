"""Strict post-execution aggregate projection; never copies private strings."""
import argparse
import json
from pathlib import Path
SUCCESS=('M1_OLD','M1_BANKED','M2_OLD','M2_BANKED','M2_BANKED_STALLED')
FAULTS=('abort_fill','abort_memory_read','abort_memory_write','abort_matrix','bank_port_fault','producer_changed')
NAMES=SUCCESS+FAULTS
OFFERS=('abort','drain','job','k_window','local_reset','tile_control','tile_read','tile_write','window')
SCALAR={1:dict(add=312,bf=6936,div=12,mul=168),2:dict(add=936,bf=19272,div=24,mul=504)}
def need(ok):
    if not ok:raise ValueError('invalid aggregate receipt')
def obj(x):need(type(x) is dict);return x
def count(x,limit=100000000):need(type(x) is int and 0<=x<=limit);return x
def exact(x,want):need(type(x) is type(want) and x==want);return x
def flag(x,want):need(type(x) is bool and x is want)
def subset_counts(x,keys):
    x=obj(x);need(set(x)<=set(keys));return {k:count(v) for k,v in x.items()}

def sanitize(r):
    r=obj(r);exact(r['status'],'PASS_SMALL_BANKED_KV_LOAN')
    for k in ('m128_executed','fullblock_executed','rtl_executed','ci_executed','public21_executed'):flag(r[k],False)
    cases=r['cases'];need(type(cases) is list and len(cases)==11)
    banked=[];denials=0;releases=0
    for i,c in enumerate(cases):
        c=obj(c);name=NAMES[i];exact(c['name'],name)
        fault=i>=5;rows=2 if i in (2,3,4) else 1;is_banked=i not in (0,2)
        exact(c['rows'],rows);flag(c['banked'],is_banked);exact(c['mode'],name if fault else None)
        exact(obj(c['terminal'])['status'],'Protocol' if fault else None)
        exact(obj(c['prefix_terminal'])['status'],None)
        exact(c['prefix_ack_bytes'],rows*2048);exact(c['prefix_published_bytes'],rows*2048)
        flag(c['output_published'],False);flag(c['injected'],fault);flag(c['fault_debt_held'],fault)
        matrix=obj(c['matrix']);mc=obj(matrix['counters']);count(matrix['normal_fma_calls'])
        flag(matrix['reset_required'],fault)
        for k in ('owner_acquires','owner_releases','owner_responses'):exact(mc[k],1)
        if not fault:
            exact(c['terminal']['write_bytes'],rows*6144);exact(matrix['normal_fma_calls'],73728 if rows==1 else 221184)
            exact(mc['normal_steps'],144 if rows==1 else 432);exact(mc['normal_results'],mc['normal_steps'])
            scalar=subset_counts(c['scalar_calls'],SCALAR[rows]);need(scalar==SCALAR[rows])
            reads=subset_counts(c['read_bytes'],('q','k','v'));need(set(reads)=={'q','k','v'})
            exact(reads['q'],rows*6144)
            expected_k=rows*1024 if is_banked else 6144 if rows==1 else 18432
            exact(reads['k'],expected_k);exact(reads['v'],expected_k)
        if not is_banked:exact(c['loan'],None);exact(c['external_denials'],0);continue
        loan=obj(c['loan']);flag(loan['active'],False)
        for k in ('shared_payload_identity_unchanged','same_dense_tile_attention_banks'):flag(loan[k],True)
        for k in ('payload_bytearray_allocated','production_public_checkpoint_executed','rtl_executed','model_edges_are_hardware_cycles'):flag(loan[k],False)
        exact(loan['authority'],'REAL_SYNTHETIC_KVAPPEND')
        le=subset_counts(loan['loan_events'],('edges','loans','releases','route_faults'))
        exact(le['loans'],1);exact(le['releases'],1);exact(le.get('route_faults',0),1 if name=='bank_port_fault' else 0)
        be=subset_counts(loan['bank_events'],('bank_edges','read_accesses','write_accesses'))
        exact(be['bank_edges'],le['edges']+1+le.get('route_faults',0))
        offers=subset_counts(loan['blocked_offers'],OFFERS);need(set(offers)==set(OFFERS))
        for value in offers.values():exact(value,3 if fault else 2)
        exact(c['external_denials'],39 if fault else 26);denials+=c['external_denials'];releases+=le['releases']
        if not fault:
            cache=obj(obj(c['owner'])['resident_cache']);cc=subset_counts(cache['counts'],('leases','fill_requests','fill_commits','read_requests','consume_acks','bank_read_accesses','bank_write_accesses','response_latency_edges'))
            exact(cache['outstanding'],0);exact(cache['valid_lines'],0)
            exact(cache['capacity_bytes'],704512);exact(cache['kv_reserved_bytes'],262144);exact(cache['valid_metadata_bytes'],512)
            exact(cc['leases'],1);exact(cc['fill_requests'],rows*32);exact(cc['fill_commits'],rows*32)
            exact(cc['read_requests'],160 if rows==1 else 512)
            exact(cc['consume_acks'],cc['fill_requests']+cc['read_requests'])
            exact(cc['bank_read_accesses'],be['read_accesses']);exact(cc['bank_write_accesses'],be['write_accesses'])
            exact(be['read_accesses'],cc['read_requests']*2);exact(be['write_accesses'],cc['fill_requests']*2)
            holds=count(c['local_hold_edges']);need(holds>0 if name=='M2_BANKED_STALLED' else holds==0)
            need(cc['response_latency_edges']>=cc['consume_acks'])
            banked.append(dict(case=name,external_read_bytes=sum(reads.values()),local_fills=cc['fill_commits'],local_hits=cc['read_requests'],
              local_consume_acks=cc['consume_acks'],local_response_edges=cc['response_latency_edges'],local_hold_edges=holds,
              physical_bank_reads=be['read_accesses'],physical_bank_writes=be['write_accesses'],shared_model_edges=le['edges'],
              normal_issue_count=mc['normal_steps'],normal_fma_count=matrix['normal_fma_calls'],scalar_calls=scalar))
    comp=r['comparisons'];need(type(comp) is list and len(comp)==2);comparisons=[]
    for i,c in enumerate(comp):
        c=obj(c);expected=dict(case=('M1','M2')[i],output_bit_diff_count=0,intermediate_bit_diff_count=0,observed_fields=10,
          old_external_read_bytes=(18432,49152)[i],banked_external_read_bytes=(8192,16384)[i],old_kv_read_bytes=(12288,36864)[i],banked_kv_read_bytes=(2048,4096)[i])
        need(set(c)==set(expected))
        for k,v in expected.items():exact(c[k],v)
        comparisons.append(expected)
    return dict(status='PASS_SMALL_SHARED_A_INTEGRATION',scope='SYNTHETIC_SMALL_ONLY',arithmetic='UNCHANGED_LIVE_PV32',
      comparisons=comparisons,successful_banked_cases=banked,cases_passed=11,fault_cases_passed=6,fault_cases=list(FAULTS),
      released_loans=releases,rejected_direct_offers=denials,cache_capacity_bytes=262144,A_capacity_bytes=704512,valid_metadata_bytes=512,
      local_outstanding_limit=1,minimum_local_response_edges=1,route='NEW_TWO_BANK_SOFTWARE_ROUTE',
      fault_backend_reset='REQUIRED_BEFORE_NEXT_SHARED_MATRIX_WORK',dense_ready_scope='A_ADMISSION_ONLY',
      public21='NOT_EXECUTED',m128='NOT_EXECUTED',fullblock='NOT_EXECUTED',rtl='NOT_EXECUTED',hardware_cycles='NOT_ESTABLISHED')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);need(not out.exists());out.write_text(json.dumps(sanitize(json.loads(Path(a.input).read_text())),indent=2,sort_keys=True,allow_nan=False)+'\n')
