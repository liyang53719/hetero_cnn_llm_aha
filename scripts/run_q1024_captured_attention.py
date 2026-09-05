#!/usr/bin/env python3
"""All1024 queries/all12 heads; automatic bounded numerical partitions, not trace timing."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'work/results/q1024_captured_attention_payload';out.mkdir(exist_ok=True)
    lock=(out/'coordinator.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    # Build script holds common heavy-task lock, then release it before simulation.
    if not (out/'identity.json').exists():
        subprocess.run(['taskset','-c','8-23','bash','scripts/run_attention_sequencer_e2.sh'],
                       cwd=ROOT,env={**os.environ,'BUILD_ONLY':'1'},check=True)
    common=(ROOT/'work/results/q1024_continuous/coordinator.lock').open('a');fcntl.flock(common,fcntl.LOCK_EX)
    sim=ROOT/'work/results/attention_sequencer_e2/obj/tb'
    vectors=ROOT/'work/results/q1024_post_projection/attention_vectors'
    source_manifest=ROOT/'work/results/attention_sequencer_e2/inputs.sha256'
    subprocess.run(['sha256sum','--check',str(source_manifest)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    identity={str(p.relative_to(ROOT)):sha(p) for p in [sim,source_manifest,vectors/'manifest.json',*sorted(vectors.glob('*.memh'))]}
    if (out/'identity.json').exists():assert json.loads((out/'identity.json').read_text())==identity
    else:(out/'identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    receipts=[]
    for qt in range(64):
        assert shutil.disk_usage(ROOT).free>50*1024**3
        receipt=out/f'qt{qt:02d}.json'
        if receipt.exists():
            old=json.loads(receipt.read_text());assert old['status']=='PASS' and old['identity']==identity
            assert sha(Path(old['log']))==old['log_sha256']
            assert sha(Path(old['output']))==old['output_sha256'];receipts.append(old);continue
        log=out/f'qt{qt:02d}.log'
        actual=out/f'qt{qt:02d}.fp32.memh'
        assert not actual.exists(), 'Preserve prior partial output; inspect failure before retry'
        cmd=['bash','scripts/run_memory_capped.sh','timeout','--signal=INT','--kill-after=30s','600',
             str(sim),f'+VECTORS={vectors}','+FULL_Q1024',f'+QT={qt}',f'+OUTPUT={actual}']
        state=dict(status='RUNNING',qt=qt,command=cmd,cwd=str(ROOT),start=time.time(),identity=identity,log=str(log))
        print(f'CAPTURED_ATTENTION_START qt={qt} rows={qt*16}..{qt*16+15} heads=all12',flush=True)
        with log.open('w') as stream:
            p=subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                env={**os.environ,'MIN_AVAILABLE_KIB':'10485760','MEMORY_HIGH':'24G','MEMORY_MAX':'30G'})
            state['pid']=p.pid;receipt.write_text(json.dumps(state,indent=2)+'\n');rc=p.wait()
        state.update(returncode=rc,end=time.time(),log_sha256=sha(log))
        text=log.read_text();m=re.search(r'Q1024_CAPTURED_ATTENTION_QT_PASS qt=(\d+) rows_heads=(\d+) tasks=(\d+) merges=(\d+) cycles=(\d+) hash=([0-9a-f]+)',text)
        passed=rc==0 and m is not None and not re.search(r'Error:|Fatal:',text)
        if passed:
            q,rows,tasks,merges,cycles=map(int,m.groups()[:5]);passed=(q==qt and rows==192 and tasks==12*((qt+2)//2) and merges==192*(qt//8))
            state.update(rows_heads=rows,tasks=tasks,merges=merges,partition_cycles=cycles,output_hash=m[6])
        if passed:
            words=actual.read_text().splitlines()
            passed=len(words)==24576 and all(re.fullmatch('[0-9a-fA-F]{8}',w) for w in words)
            fnv=0xcbf29ce484222325
            for w in words:fnv=((fnv^int(w,16))*0x100000001b3)&((1<<64)-1)
            passed=passed and f'{fnv:016x}'==state['output_hash']
            state.update(output=str(actual),output_sha256=sha(actual),output_words=len(words))
        state['status']='PASS' if passed else 'FAIL';receipt.write_text(json.dumps(state,indent=2)+'\n')
        if not passed:raise SystemExit(f'STOP first failure {log}; no automatic retry or threshold relaxation')
        receipts.append(state)
    assert sum(r['rows_heads'] for r in receipts)==12288
    assert sum(r['tasks'] for r in receipts)==12672
    assert sum(r['merges'] for r in receipts)==43008
    for path,h in identity.items():assert sha(ROOT/path)==h
    report=dict(status='PASS_Q1024_ALL_ROW_ATTENTION_NUMERICAL_PARTITIONS',identity=identity,
                queries=1024,heads=12,fp32_outputs=1572864,tasks=12672,merges=43008,
                partitions=[dict(qt=r['qt'],log_sha256=r['log_sha256'],output_hash=r['output_hash'],output_sha256=r['output_sha256']) for r in receipts],
                integrated_cycles=None,full_model_tokens_per_second=None,
                nonclaims=['Not full decoder or model','Independent query-tile numerical jobs, not uninterrupted controller performance',
                           'Actual bias/RoPE files feed Matrix/SFU; tensor-memory and SFU service sequencing still TB-side'])
    (ROOT/'reports/execution/Q1024_CAPTURED_ATTENTION_RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'],flush=True)
if __name__=='__main__':main()
