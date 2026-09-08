#!/usr/bin/env python3
"""Account for every real16 two-layer cycle in the full-output comparison.

This reads a completed comparison; it neither runs RTL nor predicts full-model
throughput. QK/Softmax/PV are a fused timing interval, not independent timings.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from compare_matrix4096_real2 import metrics

OPCODES = ['SFU_RMSNORM','MATRIX_GEMM','SFU_VECTOR','SFU_ROPE',
           'MATRIX_GEMM','SFU_VECTOR','SFU_ROPE','MATRIX_GEMM',
           'SFU_VECTOR','KV_APPEND','MATRIX_QK','SFU_SOFTMAX','MATRIX_PV',
           'MATRIX_GEMM','SFU_VECTOR','SFU_RMSNORM','MATRIX_GEMM',
           'MATRIX_GEMM','SFU_ACTIVATION','MATRIX_GEMM','SFU_VECTOR']
CATEGORY = {x: ('dense_with_io' if x=='MATRIX_GEMM' else
                'attention_fused' if x in ('MATRIX_QK','SFU_SOFTMAX','MATRIX_PV') else
                {'SFU_RMSNORM':'norm','SFU_VECTOR':'vector','SFU_ROPE':'rope',
                 'SFU_ACTIVATION':'silu_times_up','KV_APPEND':'kv_copy'}[x]) for x in OPCODES}
USEFUL = 1498202112
WEIGHT_BYTES = 374341632


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def integer(value, name: str, minimum: int=0) -> int:
    require(type(value) is int and value>=minimum, 'invalid '+name)
    return value


def validate_metrics(data: dict, peak: int) -> dict:
    require(data['matrix_macs_per_cycle']==peak and data['clock_target_hz']==800000000,
            'clock or physical MAC capacity changed')
    raw = {'cycles':integer(data['cycles'],'cycles',1),
           'useful_macs':integer(data['useful_macs'],'useful_macs',1),
           'executed_macs':integer(data['executed_macs'],'executed_macs',1),
           'read_bytes':integer(data['ddr_read_bytes'],'read_bytes',1),
           'write_ack_bytes':integer(data['ddr_write_ack_bytes'],'write_bytes',1)}
    require(raw['useful_macs']==USEFUL and raw['write_ack_bytes']==5636096,
            'wrong work or write coverage')
    require(raw['read_bytes']>=WEIGHT_BYTES, 'missing cold weight traffic')
    expected=metrics(raw,peak)
    for key,value in expected.items():
        if type(value) is float:
            require(type(data[key]) in (int,float) and math.isfinite(data[key]) and
                    math.isclose(data[key],value,rel_tol=1e-12,abs_tol=1e-15),
                    'inconsistent reported metric: '+key)
        else:
            require(type(data[key]) is int and data[key]==value, 'invalid reported counter: '+key)
    return expected


def analyze(report: dict) -> dict:
    require(report['status']=='PASS_PIPELINED_REAL16_TWO_LAYER_ALL_OUTPUT_COMPARISON',
            'comparison did not complete')
    for key,expected in {'tokens':16,'layers':2,'commands':42,'owner_jobs':38,
                         'checked_fp32':1409024,'bit_differences':0}.items():
        require(type(report[key]) is int and report[key]==expected, 'wrong fixed scope: '+key)
    require(isinstance(report['tested_source'],str) and
            re.fullmatch('[0-9a-f]{40}',report['tested_source']) is not None, 'invalid source')
    old=validate_metrics(report['baseline_512'],512)
    burst=validate_metrics(report['baseline_4096_burst'],4096)
    new=validate_metrics(report['pipeline_4096'],4096)
    require(old['cycles']==146854495 and burst['cycles']==82001446,'not frozen baselines')
    for key,value in [('speedup_vs_512',old['cycles']/new['cycles']),
                      ('speedup_vs_4096_burst',burst['cycles']/new['cycles'])]:
        require(type(report[key]) in (int,float) and math.isfinite(report[key]) and
                math.isclose(report[key],value,rel_tol=1e-12), 'inflated speedup: '+key)
    rows=report['per_command_durations'];require(len(rows)==42,'incomplete timing trace')
    sums={name:[0,0] for name in set(CATEGORY.values())}
    for pc,row in enumerate(rows):
        require(type(row['pc']) is int and row['pc']==pc and row['opcode']==OPCODES[pc%21],
                'reordered/missing command timing')
        for i,key in enumerate(('burst_cycles','pipeline_cycles')):
            sums[CATEGORY[row['opcode']]][i]+=integer(row[key],key)
    require([sum(x[i] for x in sums.values())+1 for i in (0,1)]==[burst['cycles'],new['cycles']],
            'duplicated or unaccounted request cycles')
    categories=[{'category':name,'burst_cycles':v[0],'pipeline_cycles':v[1],
                 'speedup':v[0]/v[1] if v[1] else None,
                 'pipeline_wall_fraction':v[1]/new['cycles']} for name,v in sorted(sums.items())]
    require(new['cycles']>0,'unfinished request')
    return {'schema':1,'status':'PASS_ACCOUNTED_PRODUCTION_PIPELINE_PERFORMANCE',
            'tested_source':report['tested_source'],'tokens':16,'layers':2,
            'baseline_512':old,'baseline_4096_burst':burst,'pipeline_4096':new,
            'speedup_vs_512':old['cycles']/new['cycles'],
            'speedup_vs_4096_burst':burst['cycles']/new['cycles'],
            'latency_reduction_vs_512':1-new['cycles']/old['cycles'],
            'useful_utilization_ratio_vs_512':new['useful_wall_mac_utilization']/old['useful_wall_mac_utilization'],
            'per_category':categories,'receipt_tail_cycles':1,
            'whole_request_read_gbytes_per_s_at_target':new['ddr_read_bytes']*0.8/new['cycles'],
            'cold_weight_bytes':WEIGHT_BYTES,
            'memory_model':'same frozen AXI service delay policy; not a calibrated LPDDR controller',
            'active_matrix_utilization':None,
            'active_matrix_utilization_reason':'request wall counters do not expose the complete active-issue interval',
            'scope':{'synthetic_real16_two_layers':True,'full_network_q1024':False,
                     'target_clock_only':True,'physical_timing_signoff':False,
                     'full_comparison_required':True,'no_new_hardware_execution':True}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comparison',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        require(not a.output.exists() and not a.output.is_symlink(),'preserve prior report')
        raw=a.comparison.read_bytes();r=analyze(json.loads(raw));r['comparison_sha256']=hashlib.sha256(raw).hexdigest()
        text=json.dumps(r,indent=2,allow_nan=False)+'\n'
        with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,OSError,TypeError,KeyError,ZeroDivisionError) as e:
        raise SystemExit('PIPELINE_PERFORMANCE_REJECTED: '+str(e))
