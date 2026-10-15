"""Strict post-run projection of the small synthetic receipt, never tensors."""
import json
from .check_small import need
POSITIVE=('M1_OLD','M1_CACHED','M2_OLD','M2_CACHED','M2_CACHED_STALLED')
NEGATIVE=('fill_abort','hit_abort','hit_wrong_epoch','hit_wrong_data','producer_change','region_write','memory_wrongtag','memory_error','memory_short')
COMPARE_KEYS=('output_bit_diff_count','intermediate_bit_diff_count','observed_fields','old_external_read_bytes','cached_external_read_bytes','old_kv_read_bytes','cached_kv_read_bytes')

def integer(value,expected=None):
    need(type(value) is int and 0<=value<=1<<31,'exact bounded nonnegative integer')
    need(expected is None or value==expected,'unexpected fixed aggregate')
    return value

def fixed(value,expected):
    need(type(value) is type(expected) and value==expected,'fixed enum/bool required')
    return expected

def sanitize(report):
    need(type(report) is dict,'report dict')
    fixed(report['status'],'PASS_SMALL_SYNTHETIC_RESIDENT_EQUIVALENCE')
    for n in ('full_m128_executed','fullblock_executed','rtl_executed','ci_executed'):fixed(report[n],False)
    need(type(report['comparisons']) is list and len(report['comparisons'])==2,'both fixed synthetic sizes required')
    comparisons=[]
    for original,name,values in zip(report['comparisons'],('M1','M2'),((0,0,10,18432,8192,12288,2048),(0,0,10,49152,16384,36864,4096))):
        need(type(original) is dict and set(original)=={'case',*COMPARE_KEYS},'exact comparison schema')
        comparisons.append(dict(case=fixed(original['case'],name),**{k:integer(original[k],v) for k,v in zip(COMPARE_KEYS,values)}))
    need(type(report['cases']) is list and len(report['cases'])==14,'all positive and negative cases required')
    local=[]
    for c,name in zip(report['cases'],POSITIVE+NEGATIVE):
        fixed(c['name'],name)
        if name in NEGATIVE:
            fixed(c['injected'],True)
            fixed(c['terminal']['status'],'Memory' if name=='memory_error' else 'Protocol')
            continue
        need(c['terminal']['status'] is None,'successful positive terminal required')
        rows=1 if name.startswith('M1') else 2
        integer(c['terminal']['executed_macs'],73728 if rows==1 else 221184)
        integer(c['owner']['accepted']['matrix_requests'],144 if rows==1 else 432)
        integer(c['write_ack_bytes'],rows*6144)
        if 'CACHED' in name:
            cache=c['owner']['resident_cache'];counts=cache['counts'];stalled=name.endswith('STALLED')
            for k,v in [('capacity_bytes',704512),('kv_reserved_bytes',262144),('valid_metadata_bytes',512),
                        ('local_packet_bytes',64),('outstanding_limit',1),('bank_word_bits',256),('banks_per_packet',2),
                        ('minimum_response_edges',1),('outstanding',0),('valid_lines',0)]:integer(cache[k],v)
            hits=160 if rows==1 else 512;fills=32*rows;acks=hits+fills
            expected={'fill_requests':fills,'fill_commits':fills,'read_requests':hits,'bank_write_accesses':2*fills,
                      'bank_read_accesses':2*hits,'consume_acks':acks,'response_latency_edges':acks*(3 if stalled else 1)}
            local.append(dict(case=name,**{k:integer(counts[k],v) for k,v in expected.items()},
                              response_hold_edges=integer(c['local_hold_edges'],1152 if stalled else 0)))
    return dict(status='PASS_SMALL_SYNTHETIC_RESIDENT_EQUIVALENCE',comparisons=comparisons,local_port_events=local,
       negative_cases_passed=9,observed_fields=10,arithmetic='UNCHANGED_LIVE_PV32',
       original_matrix_requests_m1=144,original_matrix_requests_m2=432,
       original_physical_fmas_m1=73728,original_physical_fmas_m2=221184,
       cache_capacity_bytes=262144,A_capacity_bytes=704512,valid_metadata_bytes=512,
       cache_route='NEW_TWO_BANK_64B_SOFTWARE_ROUTE_NOT_CONNECTED_OLD_A_PORT',
       global_arbiter='NOT_CONNECTED_TO_FULLCHAIN',model_edges='PROTOCOL_EVENTS_NOT_HARDWARE_CYCLES',
       m128='NOT_EXECUTED',rtl='NOT_EXECUTED',ci='NOT_EXECUTED',fullblock='NOT_EXECUTED',
       original_numerical_failures='UNCHANGED_NOT_RETESTED',lane_mapping='UNCHANGED')

if __name__=='__main__':
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--output');a=p.parse_args()
    if a.input is None:print(json.dumps({'status':'NOT_EXECUTED'}))
    else:
        need(a.output is not None and not Path(a.output).exists(),'fresh safe output required')
        Path(a.output).write_text(json.dumps(sanitize(json.loads(Path(a.input).read_text())),indent=2,sort_keys=True)+'\n')
