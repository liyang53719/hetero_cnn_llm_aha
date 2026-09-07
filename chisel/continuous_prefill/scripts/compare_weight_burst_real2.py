#!/usr/bin/env python3
"""Compare every actual real16/L2 output before measuring the weight supply change.

Same Matrix4096, graph, DDR layout, data recipe and one pinned iDMA. A change in
AXI transaction boundaries is not a change in useful work or stored precision.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from compare_matrix4096_real2 import full_csv, metrics, require
from verify_host_block_gate import verify, tagged

FROZEN_SOURCE = 'd3571eecf96f7c6e4578e7d8d478139e2189c3de'
VALUES, USEFUL, READ_BYTES, WRITE_BYTES = 1409024, 1498202112, 385152512, 5636096


def validate_counters(old: dict, new: dict) -> dict:
    a, b = metrics(old, 4096), metrics(new, 4096)
    require(a['useful_macs'] == b['useful_macs'] == USEFUL, 'different useful work')
    require(a['executed_macs'] == b['executed_macs'] == 1524105216, 'different arithmetic schedule')
    require(a['ddr_read_bytes'] == b['ddr_read_bytes'] == READ_BYTES, 'extra or omitted weight reads')
    require(a['ddr_write_ack_bytes'] == b['ddr_write_ack_bytes'] == WRITE_BYTES, 'short or extra writeback')
    def number(k):
        v = new[k]
        require(type(v) in (int, str) and re.fullmatch('[0-9]+', str(v)) is not None, 'invalid ' + k)
        return int(v)
    bursts, hits, transfers = (number(k) for k in ('read_bursts','weight_cache_hits','idma_transfers'))
    beats = READ_BYTES // 64
    require(number('weight_read_burst_beats') == 16, 'wrong prefetch profile')
    require(0 < bursts <= beats <= 16 * bursts and hits == beats - bursts, 'read burst/cache accounting')
    require(transfers == bursts + WRITE_BYTES // 64, 'iDMA did not carry complete traffic')
    return {'baseline4096': a, 'burst4096': b, 'cycle_speedup': a['cycles'] / b['cycles'],
            'latency_reduction_fraction': 1-b['cycles']/a['cycles'],
            'idma_transfers': transfers, 'read_bursts': bursts, 'cached_logical_beats': hits}


def compare(current: Path, baseline: Path) -> dict:
    require((baseline/'source_base_commit.txt').read_text().strip() == FROZEN_SOURCE, 'wrong frozen baseline')
    results, manifests = [], []
    for out, burst in ((baseline,1),(current,16)):
        require((out/'gate.exit').read_text().strip() == '0', 'unfinished gate')
        m = json.loads((out/'fixture/manifest.json').read_text())
        require((m['tokens'],m['layers'],m['shape']['H'],m['shape']['F'],m['commands'],m['descriptors']) == (16,2,1536,8960,42,430), 'wrong real2 geometry')
        scope=json.loads((out/'generated/SCOPE.json').read_text())
        require(scope.get('weight_read_burst_beats',1)==burst, 'wrong read burst configuration')
        r=verify(out,False)
        require(r['matrix_macs']==4096 and r['checked_fp32']==VALUES, 'Matrix/output mismatch')
        full_csv(out,m);results.append(r);manifests.append(m)
    require(manifests[0]==manifests[1], 'Host graph, weight recipe or memory layout changed')
    names=['input_x.f32le','host_commands.bin','host_descriptors.bin']
    names += [n+'_actual.f32le' for op in manifests[0]['schedule'] for n in op['outputs']]
    digests={}
    for name in names:
        a=(baseline/'tensors'/name).read_bytes();b=(current/'tensors'/name).read_bytes()
        require(a==b, 'actual predecessor/output mismatch: '+name)
        digests[name]=hashlib.sha256(a).hexdigest()
    durations=[];previous=[0,0]
    logs=[tagged((out/'run.log').read_text(),'OWNER_COMPLETION') for out in (baseline,current)]
    for pc,op in enumerate(manifests[0]['schedule']):
        ends=[int(log[pc]['cycle']) for log in logs]
        costs=[end-start for end,start in zip(ends,previous)]
        require(all(x>=0 for x in costs), 'nonmonotonic completion cycles')
        durations.append({'pc':pc,'opcode':op['opcode'],'baseline4096_cycles':costs[0],'burst4096_cycles':costs[1]})
        previous=ends
    report=validate_counters(results[0]['counters'],results[1]['counters'])
    require(sum(r['baseline4096_cycles'] for r in durations)+1==report['baseline4096']['cycles'], 'baseline cycle accounting')
    require(sum(r['burst4096_cycles'] for r in durations)+1==report['burst4096']['cycles'], 'new cycle accounting')
    report.update(schema=1,status='PASS_WEIGHT_BURST_REAL16_TWO_LAYER_EXACT_COMPARISON',
        tested_source=(current/'source_base_commit.txt').read_text().strip(),baseline_source=FROZEN_SOURCE,
        tokens=16,layers=2,host_commands=42,checked_fp32=VALUES,bit_differences=0,
        actual_files_sha256=digests,per_command_durations=durations,
        scope={'synthetic_weights':True,'host_command_driven':True,'physical_matrix_macs':4096,
               'idma_instances':1,'bounded_weight_mailbox_bytes':1024,'persistent_object_cache':False,
               'full_q1024_network':False,'official_quality':False,'dc':False})
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--current',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        require(not a.output.exists() and not a.output.is_symlink(),'never overwrite evidence')
        result=compare(a.current.resolve(),a.baseline.resolve());text=json.dumps(result,indent=2,allow_nan=False)+'\n'
        with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,KeyError,TypeError,OSError) as e:raise SystemExit('WEIGHT_BURST_COMPARISON_REJECTED: '+str(e))
