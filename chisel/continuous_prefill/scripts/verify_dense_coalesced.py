#!/usr/bin/env python3
"""Compare two actual Dense owner/iDMA/4096-MAC runs, not a timing model.

This is a COMPONENT gate. It cannot accept the full Host-graph >=50% goal.
Counter bins are exclusive and include ALL owner cycles. Bytes and numerical
work must be identical across baseline/coalesced runs. Preserve both old logs.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re, struct
from pathlib import Path

CASES = [(16,1536,64,0),(16,1536,64,1),(80,256,128,0),
         (80,256,128,1),(81,256,128,1),(33,544,64,1),
         (32,1536,64,1),(17,528,128,0),(1,16,16,0),
         (80,256,64,1),(16,544,32,1)]
BINS = ('other','a_fetch','setup','issue','writeback','weight_wait','matrix_wait')
MARKER = ('DENSE_COALESCED_PROFILE_PASS cases=13 numeric_cases=11 fault_resets=2 '
          'checked_fp32=216128 bit_differences=0 real_idma=1 physical_mac=4096 same_dut=1')

def require(ok: bool, message: str) -> None:
    if not ok: raise ValueError(message)

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

def read_run(root: Path) -> dict:
    require((root/'simulation.exit').read_text().strip()=='0','simulator did not succeed')
    require((root/'source_verify.log').read_text().strip()=='SOURCE_IMMUTABILITY_PASS','source changed or not checked')
    text=(root/'run.log').read_text(); lines=text.splitlines()
    require(lines.count(MARKER)==1,'missing/duplicate/incomplete final marker')
    require(not re.search(r'DENSE_COALESCED_PROFILE_FAIL|BURST_DENSE_FAIL|%Error|Fatal|Aborted',text),'failure in log')
    raw_profiles=[line for line in lines if line.startswith('DENSE_PROFILE ')]
    require(len(raw_profiles)==len(CASES),'incomplete profiles')
    required={'m','n','k','native','hw_cycles','useful','read_bursts','read_beats','write_bursts','write_beats',*BINS}
    profiles=[]
    for expected,line in zip(CASES,raw_profiles):
        fields=line.split()[1:]; d={}
        for field in fields:
            key,value=field.split('=',1)
            require(key not in d and re.fullmatch(r'[0-9]+',value) is not None,'duplicate or malformed counter')
            d[key]=int(value)
        require(set(d)==required,'profile schema mismatch')
        require(tuple(d[k] for k in ('m','n','k','native'))==expected,'wrong case/order')
        require(d['hw_cycles']>0 and sum(d[b] for b in BINS)==d['hw_cycles'],'lost/double-counted owner cycle')
        require(d['useful']==d['m']*d['n']*d['k'],'wrong useful work')
        require(d['useful']<=d['issue']*4096<=d['hw_cycles']*4096,'wrong issue count')
        require(d['write_beats']*64==d['m']*d['n']*4,'wrong write bytes')
        require(0<d['read_bursts']<=d['read_beats'] and 0<d['write_bursts']<=d['write_beats'],'missing actual AXI work')
        profiles.append(d)
    require(sum(d['m']*d['n'] for d in profiles)==216128,'wrong element coverage')
    actual=(root/'outputs/actual.f32le').read_bytes(); reference=(root/'outputs/reference.f32le').read_bytes()
    require(len(actual)==216128*4 and actual==reference,'full arithmetic outputs differ')
    require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<f',actual)),'nonfinite output')
    fault_lines=[line for line in lines if line.startswith('STREAM_DENSE_CASE_PASS ') and ' fault=0 ' not in line]
    require(len(fault_lines)==2 and ' fault=1 ' in fault_lines[0] and ' fault=2 ' in fault_lines[1],'missing actual read/write fault-reset cases')
    return dict(profiles=profiles,actual=actual,log_sha256=sha((root/'run.log').read_bytes()),
                actual_sha256=sha(actual),generated_sha256=sha((root/'generated/StreamingDenseProbe.sv').read_bytes()))

def compare(baseline: Path, optimized: Path) -> dict:
    old,new=read_run(baseline),read_run(optimized)
    require(old['actual']==new['actual'],'optimized DUT differs from baseline DUT')
    require(old['generated_sha256']!=new['generated_sha256'],'same generated design used as A/B')
    for name in ('sources.sha256.json','hardfloat.sha256.json'):
        a=json.loads((baseline/name).read_text()); b=json.loads((optimized/name).read_text())
        require(a==b,'different source inputs '+name)
    rows=[]
    for a,b in zip(old['profiles'],new['profiles']):
        for key in ('m','n','k','native','useful','issue','read_beats','write_beats'):
            require(a[key]==b[key],'A/B changed work or traffic '+key)
        rows.append(dict(shape=[a['m'],a['n'],a['k']],native_bf16=bool(a['native']),
                         baseline=a,coalesced=b,cycle_speedup=a['hw_cycles']/b['hw_cycles'],
                         baseline_useful_owner_utilization=a['useful']/(4096*a['hw_cycles']),
                         coalesced_useful_owner_utilization=b['useful']/(4096*b['hw_cycles']),
                         read_bursts_saved=a['read_bursts']-b['read_bursts']))
    return dict(status='PASS_DENSE_COALESCED_COMPONENT_NUMERIC_AB',cases=13,numeric_cases=11,
                checked_fp32_per_run=216128,bit_differences=0,
                physical_macs=4096,real_idma=True,per_case=rows,
                baseline_log_sha256=old['log_sha256'],coalesced_log_sha256=new['log_sha256'],
                identical_actual_sha256=old['actual_sha256'],
                full_host_graph_tested=False,full_request_perf50_accepted=False,
                scope='Real production Dense owner, Matrix arithmetic and pinned iDMA component. Not full real16 layers, not DC. Same memory service/backpressure algorithm; coalescing changes transaction timing.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True); p.add_argument('--optimized',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    try:
        require(not a.output.exists() and not a.output.is_symlink(),'preserve existing comparison')
        result=compare(a.baseline,a.optimized)
        with a.output.open('x') as f: json.dump(result,f,indent=2,allow_nan=False); f.write('\n')
        print(json.dumps(result,indent=2,allow_nan=False))
    except (ValueError,TypeError,KeyError,OSError,StopIteration) as e: raise SystemExit('COALESCED_COMPARISON_REJECTED: '+str(e))
