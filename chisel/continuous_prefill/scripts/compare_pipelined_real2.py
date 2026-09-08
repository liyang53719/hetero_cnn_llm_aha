#!/usr/bin/env python3
"""Full actual-output comparison against frozen burst and 512-MAC gates.
All cycle-to-time conversions use the target 800 MHz, not physical signoff.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from compare_matrix4096_real2 import compare, full_csv, metrics, require
from verify_host_block_gate import verify, tagged

BURST_SOURCE='cc2f9424daf2e35ca7dd5940305de7e09bbf623b'

def audit(current:Path, burst:Path, baseline512:Path)->dict:
    vs512=compare(current,baseline512)
    scope=json.loads((current/'generated/SCOPE.json').read_text())
    require(scope.get('pipelined') is True and scope.get('dense_contexts')==5 and scope.get('silu_lanes')==16,'not production pipeline')
    require((burst/'source_base_commit.txt').read_text().strip()==BURST_SOURCE,'wrong frozen burst baseline')
    require((burst/'gate.exit').read_text().strip()=='0','unfinished burst baseline')
    old=verify(burst,False);new=verify(current,False)
    old_manifest=json.loads((burst/'fixture/manifest.json').read_text())
    m=json.loads((current/'fixture/manifest.json').read_text())
    require(old_manifest==m,'changed Host/weight/layout contract')
    require(full_csv(burst,m)==full_csv(current,m)==1409024,'incomplete output comparison')
    matched=[]
    for name in ['input_x.f32le','host_commands.bin','host_descriptors.bin']+[n+'_actual.f32le' for op in m['schedule'] for n in op['outputs']]:
        a=(current/'tensors'/name).read_bytes();b=(burst/'tensors'/name).read_bytes()
        require(a==b,'actual output differs from burst baseline: '+name)
        matched.append({'name':name,'bytes':len(a),'sha256':hashlib.sha256(a).hexdigest()})
    a=metrics(old['counters'],4096);b=metrics(new['counters'],4096)
    require(a['cycles']==82001446 and a['useful_macs']==b['useful_macs']==1498202112,'wrong fixed work')
    ends=[tagged((p/'run.log').read_text(),'OWNER_COMPLETION') for p in (burst,current)]
    prev=[0,0];durations=[]
    for pc,op in enumerate(m['schedule']):
        end=[int(x[pc]['cycle']) for x in ends];cost=[x-y for x,y in zip(end,prev)]
        require(min(cost)>=0,'nonmonotonic command timing')
        durations.append({'pc':pc,'opcode':op['opcode'],'burst_cycles':cost[0],'pipeline_cycles':cost[1]});prev=end
    require(sum(x['burst_cycles'] for x in durations)+1==a['cycles'],'unaccounted baseline cycles')
    require(sum(x['pipeline_cycles'] for x in durations)+1==b['cycles'],'unaccounted pipeline cycles')
    for x in (a,b):x['whole_request_ddr_read_gbytes_per_s_at_target']=x['ddr_read_bytes']*800000000/x['cycles']/1e9
    return {'schema':1,'status':'PASS_PIPELINED_REAL16_TWO_LAYER_ALL_OUTPUT_COMPARISON',
        'tested_source':vs512['tested_source'],'burst_source':BURST_SOURCE,'tokens':16,'layers':2,
        'commands':42,'owner_jobs':38,'checked_fp32':1409024,'bit_differences':0,
        'baseline_512':vs512['baseline_512'],'baseline_4096_burst':a,'pipeline_4096':b,
        'speedup_vs_512':vs512['wall_cycle_speedup'],'speedup_vs_4096_burst':a['cycles']/b['cycles'],
        'actual_files_compared':matched,'per_command_durations':durations,'topology':vs512['topology'],
        'counters':new['counters'],'scope':{'same_synthetic_weights':True,'same_host_graph':True,
        'same_memory_service_delay_policy':True,'block_launch':False,'host_intermediate_copy':False,
        'full_network_q1024':False,'official_weights':False,'physical_timing_signoff':False,
        'all_time_values_target_clock_only':True}}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('current','burst','baseline512','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    try:
        require(not a.output.exists() and not a.output.is_symlink(),'never overwrite evidence')
        r=audit(a.current,a.burst,a.baseline512);text=json.dumps(r,indent=2,allow_nan=False)+'\n'
        with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,KeyError,TypeError,OSError) as e:raise SystemExit('PIPELINE_COMPARISON_REJECTED: '+str(e))
