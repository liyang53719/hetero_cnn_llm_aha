#!/usr/bin/env python3
"""Compare actual 4096-MAC real16 L2 outputs and wall cycles with frozen 512 proof.

No hardware timing signoff or model throughput is inferred. Full archived
outputs, Host bytes, geometry, and output order are checked before metrics.
"""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,math,re,struct
from pathlib import Path
from verify_host_block_gate import verify,tagged
from audit_matrix_topology import audit as topology

BASE_SOURCE='9f06249ca11fcee35c0cd4d3e51c0b2fe0dfec30'
CLOCK_HZ=800_000_000
USEFUL=1_498_202_112
VALUES=1_409_024


def require(ok: bool,message: str) -> None:
    if not ok: raise ValueError(message)


def sha(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()


def metrics(counters: dict,peak: int) -> dict:
    def number(key):
        value=counters[key]
        require(type(value) in (int,str) and re.fullmatch('[0-9]+',str(value)) is not None,'invalid counter '+key)
        return int(value)
    cycles=number('cycles');useful=number('useful_macs');executed=number('executed_macs')
    require(type(peak) is int and peak in (512,4096),'invalid peak')
    require(cycles>0 and 0<useful<=executed<=cycles*peak,'MAC counter bounds')
    return {'matrix_macs_per_cycle':peak,'clock_target_hz':CLOCK_HZ,'cycles':cycles,
        'useful_macs':useful,'executed_macs':executed,
        'latency_ms_at_target_clock':cycles/CLOCK_HZ*1000,
        'useful_wall_mac_utilization':useful/(cycles*peak),
        'executed_wall_mac_utilization':executed/(cycles*peak),
        'useful_fraction_of_executed_macs':useful/executed,
        'useful_gmac_per_s_at_target_clock':useful*CLOCK_HZ/cycles/1e9,
        'peak_tmac_per_s_at_target_clock':peak*CLOCK_HZ/1e12,
        'ddr_read_bytes':number('read_bytes'),'ddr_write_ack_bytes':number('write_ack_bytes')}


def full_csv(out: Path,manifest: dict) -> int:
    count=0
    with gzip.open(out/'all_owner_elements.csv.gz','rt',newline='') as f:
        rows=csv.reader(f);require(next(rows,None)==['pc','tensor','index','actual_hex','reference_hex'],'CSV header')
        for op in manifest['schedule']:
            for name in op['outputs']:
                a=(out/f'tensors/{name}_actual.f32le').read_bytes();b=(out/f'tensors/{name}_reference.f32le').read_bytes()
                require(len(a)==len(b)==manifest['tensors'][name]['words']*4 and a==b,'tensor mismatch '+name)
                for i,((x,),(y,)) in enumerate(zip(struct.iter_unpack('<I',a),struct.iter_unpack('<I',b))):
                    require(x&0x7f800000!=0x7f800000,'nonfinite output')
                    require(next(rows,None)==[str(op['pc']),name,str(i),f'{x:08x}',f'{y:08x}'],'CSV row differs')
                    count+=1
        require(next(rows,None) is None,'extra CSV rows')
    require(count==VALUES,'full two-layer coverage required');return count


def compare(current: Path,baseline: Path) -> dict:
    require((baseline/'source_base_commit.txt').read_text().strip()==BASE_SOURCE,'wrong frozen 512 source')
    results=[];manifests=[]
    for out,peak in ((baseline,512),(current,4096)):
        require((out/'gate.exit').read_text().strip()=='0','unfinished numerical gate')
        r=verify(out,False);m=json.loads((out/'fixture/manifest.json').read_text())
        require((m['tokens'],m.get('layers'),m['shape']['H'],m['shape']['F'],m['commands'],m['descriptors'])==(16,2,1536,8960,42,430),'not fixed real16 L2')
        require(r['matrix_macs']==peak and r['checked_fp32']==VALUES,'wrong Matrix or coverage')
        require(int(r['counters']['useful_macs'])==USEFUL,'changed useful workload')
        full_csv(out,m);results.append(r);manifests.append(m)
    require(manifests[0]==manifests[1],'allocation/command/weight contract changed')
    copied=[]
    names=['input_x.f32le','host_commands.bin','host_descriptors.bin']
    names += [name+'_actual.f32le' for op in manifests[0]['schedule'] for name in op['outputs']]
    for name in names:
        a=baseline/'tensors'/name;b=current/'tensors'/name
        require(a.read_bytes()==b.read_bytes(),'old/new ACTUAL mismatch: '+name)
        copied.append({'file':name,'bytes':a.stat().st_size,'sha256':sha(a)})
    physical=topology(current/'generated/HostBlockTop.sv',4096)
    pairs=[metrics(r['counters'],p) for r,p in zip(results,(512,4096))]
    durations=[]
    logs=[tagged((o/'run.log').read_text(),'OWNER_COMPLETION') for o in (baseline,current)]
    previous=[0,0]
    for pc,op in enumerate(manifests[0]['schedule']):
        ends=[int(rows[pc]['cycle']) for rows in logs]
        costs=[end-start for end,start in zip(ends,previous)]
        require(all(c>=0 for c in costs),'nonmonotonic cycle count')
        durations.append({'pc':pc,'opcode':op['opcode'],'baseline_cycles':costs[0],'matrix4096_cycles':costs[1]})
        previous=ends
    return {'schema':1,'status':'PASS_MATRIX4096_REAL16_TWO_LAYER_EXACT_COMPARISON',
        'baseline_source':BASE_SOURCE,'tested_source':(current/'source_base_commit.txt').read_text().strip(),
        'tokens':16,'layers':2,'checked_fp32':VALUES,'bit_differences':0,'actual_files_compared':copied,
        'baseline_512':pairs[0],'matrix4096':pairs[1],
        'wall_cycle_speedup':pairs[0]['cycles']/pairs[1]['cycles'],
        'latency_reduction_fraction':1-pairs[1]['cycles']/pairs[0]['cycles'],
        'topology':physical,'per_command_durations':durations,
        'scope':{'synthetic_weights':True,'host_commands':42,'one_idma':True,'single_logical_matrix':True,
                 'handwritten_rtl_modified':False,'official_model_quality':False,'full_q1024_model':False,
                 'dc_timing_signoff':False,'latency_is_target_frequency_conversion':True},
        'logs_sha256':{'baseline':sha(baseline/'run.log'),'matrix4096':sha(current/'run.log')}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--current',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        require(not a.output.exists(),'preserve previous report');r=compare(a.current.resolve(),a.baseline.resolve())
        text=json.dumps(r,indent=2)+'\n'
        with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,TypeError,KeyError,OSError) as e:raise SystemExit('MATRIX4096_COMPARISON_REJECTED: '+str(e))
