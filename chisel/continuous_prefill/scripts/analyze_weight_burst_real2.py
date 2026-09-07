#!/usr/bin/env python3
"""Account the measured burst improvement and remaining single-port limits.

Consume a full actual-output comparison, not a capacity-only performance claim.
Completion intervals include command/operand transport. Fused QK/Softmax/PV are
one timing category. All seconds/bandwidth use the un-signed-off 800MHz target.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re
from pathlib import Path

OPS = ['SFU_RMSNORM','MATRIX_GEMM','SFU_VECTOR','SFU_ROPE','MATRIX_GEMM',
       'SFU_VECTOR','SFU_ROPE','MATRIX_GEMM','SFU_VECTOR','KV_APPEND','MATRIX_QK',
       'SFU_SOFTMAX','MATRIX_PV','MATRIX_GEMM','SFU_VECTOR','SFU_RMSNORM',
       'MATRIX_GEMM','MATRIX_GEMM','SFU_ACTIVATION','MATRIX_GEMM','SFU_VECTOR']
CATEGORIES = {'MATRIX_GEMM':'dense_including_operand_transport',
              'SFU_RMSNORM':'norm','SFU_VECTOR':'vector','SFU_ROPE':'rope',
              'KV_APPEND':'kv_copy','MATRIX_QK':'attention_fused',
              'SFU_SOFTMAX':'attention_fused','MATRIX_PV':'attention_fused',
              'SFU_ACTIVATION':'activation'}


def require(ok, message):
    if not ok: raise ValueError(message)


def integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, 'invalid '+name)
    return value


def analyze(r: dict) -> dict:
    require(r['status']=='PASS_WEIGHT_BURST_REAL16_TWO_LAYER_EXACT_COMPARISON','unverified comparison')
    for key,value in {'tokens':16,'layers':2,'host_commands':42,'checked_fp32':1409024,'bit_differences':0}.items():
        require(type(r[key]) is int and r[key]==value,'wrong fixed scope: '+key)
    for key in ('tested_source','baseline_source'):
        require(isinstance(r[key],str) and re.fullmatch('[0-9a-f]{40}',r[key]),'source identity')
    old,new=r['baseline4096'],r['burst4096']
    for m in (old,new):
        c=integer(m['cycles'],'cycles',1)
        for key,value in {'matrix_macs_per_cycle':4096,'clock_target_hz':800000000,
                          'useful_macs':1498202112,'executed_macs':1524105216,
                          'ddr_read_bytes':385152512,'ddr_write_ack_bytes':5636096}.items():
            require(type(m[key]) is int and m[key]==value,'wrong measurement: '+key)
        require(m['executed_macs']<=c*4096,'capacity exceeded')
        for key,count in [('useful_wall_mac_utilization',m['useful_macs']),
                          ('executed_wall_mac_utilization',m['executed_macs'])]:
            require(math.isclose(m[key],count/(c*4096),rel_tol=1e-12),'inflated utilization')
    require(math.isclose(r['cycle_speedup'],old['cycles']/new['cycles'],rel_tol=1e-12),'inflated speedup')
    entries=r['per_command_durations'];require(len(entries)==42,'incomplete intervals')
    groups={name:[0,0] for name in sorted(set(CATEGORIES.values()))}
    for pc,item in enumerate(entries):
        require(type(item['pc']) is int and item['pc']==pc and item['opcode']==OPS[pc%21],'wrong command sequence')
        for i,key in enumerate(('baseline4096_cycles','burst4096_cycles')):
            groups[CATEGORIES[item['opcode']]][i]+=integer(item[key],key)
    require([sum(x[i] for x in groups.values()) for i in (0,1)]==[old['cycles']-1,new['cycles']-1], 'lost/double-counted cycles')
    read_beats=new['ddr_read_bytes']//64;write_beats=new['ddr_write_ack_bytes']//64
    bursts=integer(r['read_bursts'],'read bursts',1)
    hits=integer(r['cached_logical_beats'],'cache hits')
    transfers=integer(r['idma_transfers'],'iDMA transfers',1)
    require(bursts<=read_beats<=16*bursts and hits==read_beats-bursts and transfers==bursts+write_beats,'invalid burst conservation')
    require(new['cycles']>=read_beats,'faster than one 512-bit read beat/clock')
    rows=[dict(category=name,baseline_cycles=a,burst_cycles=b,
               cycles_saved=a-b,burst_wall_fraction=b/new['cycles'],
               speedup=a/b if b else None) for name,(a,b) in groups.items()]
    return {'schema':1,'status':'PASS_MEASURED_WEIGHT_BURST_SCALING',
            'tested_source':r['tested_source'],'baseline_source':r['baseline_source'],
            'cycle_speedup':r['cycle_speedup'],'per_category':rows,'receipt_tail_cycles':1,
            'idma_transfer_reduction_fraction':1-transfers/(read_beats+write_beats),
            'cached_logical_beats':hits,'physical_read_beats':read_beats,
            'request_average_read_GBps_at_target':new['ddr_read_bytes']*800000000/new['cycles']/1e9,
            'optimistic_read_only_lower_bound_cycles':read_beats,
            'single_512bit_read_port_peak_GBps_at_target':51.2,
            'useful_wall_utilization_upper_bound_from_reads':new['useful_macs']/(read_beats*4096),
            'bound_assumptions':'One 512-bit AXI read beat each NPU clock, existing unchanged FP32-container traffic. Ignore all compute, write, dependency and control overhead. This is a lower bound on latency, NOT a forecast.',
            'scope':{'real16_synthetic_two_layers':True,'full_q1024_model':False,
                     'physical_timing_signoff':False,'requires_complete_actual_comparison':True}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--comparison',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        require(not a.output.exists() and not a.output.is_symlink(),'preserve prior result')
        raw=a.comparison.read_bytes();result=analyze(json.loads(raw));result['comparison_sha256']=hashlib.sha256(raw).hexdigest()
        text=json.dumps(result,indent=2,allow_nan=False)+'\n'
        with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,OSError,TypeError,KeyError,ZeroDivisionError) as e:raise SystemExit('BURST_ANALYSIS_REJECTED: '+str(e))
