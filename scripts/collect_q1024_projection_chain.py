#!/usr/bin/env python3
"""Validate the full continuous projection chain, excluding failed attempts."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--projection',type=int,choices=(0,1,2),required=True);args=parser.parse_args()
    directory=ROOT/f'work/results/q1024_continuous/p{args.projection}'
    receipts=sorted(directory.glob('segment_[0-9][0-9][0-9].json'))
    assert receipts
    previous_cycle=0;identity=None;chain=[];final=None
    for index,path in enumerate(receipts):
        r=json.loads(path.read_text());assert r['segment']==index and r['projection']==args.projection
        assert r['returncode']==0
        current_identity={k:v for k,v in r['identity'].items() if not k.startswith('scripts/')}
        if identity is None:identity=current_identity
        assert current_identity==identity
        log_path=Path(r['log']);assert sha(log_path)==r['log_sha256'];log=log_path.read_text()
        assert not re.search(r'Error:|Error-\[|Fatal:',log)
        if index:
            entry=re.search(r'^SEGMENT_ENTRY_CYCLE (\d+)$',log,re.M)
            assert entry and int(entry[1])==previous_cycle
        if r['status']=='CHECKPOINT':
            assert r['saved_cycle']>previous_cycle
            for p,value in r['checkpoint_files'].items():assert sha(Path(p))==value
            previous_cycle=r['saved_cycle']
        else:
            assert r['status']=='PROJECTION_NUMERICAL_COMPLETE' and index==len(receipts)-1
            match=re.search(r'^GROUP8_PINNED_IDMA_NUMERICAL_PASS .*$',log,re.M);assert match
            final={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',match[0])}
        chain.append(dict(segment=index,attempt=r.get('attempt',0),receipt_sha256=sha(path),log_sha256=r['log_sha256'],status=r['status']))
    assert final and final['projection']==args.projection and final['batches']==64 and final['full_fixture']==1
    columns=1536 if args.projection==0 else 256;tiles=columns//32;groups=(tiles+7)//8
    assert final['checked_bf16']==1024*columns and final['useful_macs']==1024*columns*1536
    assert final['flat_requests']==(tiles*96 if tiles<=8 else groups*1536)+(48*groups+16*tiles)*64
    assert final['read_bytes']==1536*columns*2+groups*49152*64 and final['write_bytes']==1024*columns*2
    assert final['wall_cycles']>previous_cycle and final['useful_macs']<=512*final['wall_cycles']
    for p,value in identity.items():assert sha(ROOT/p)==value
    result=dict(status='PASS_Q1024_SINGLE_PROJECTION_NUMERICAL',projection=('Q','K','V')[args.projection],rows=1024,columns=columns,depth=1536,
        counters=final,chain=chain,identity=identity,nominal_clock_hz=800000000,
        useful_mac_utilization=final['useful_macs']/(512*final['wall_cycles']),
        nominal_projection_latency_seconds=final['wall_cycles']/800000000,
        full_model_prefill_tokens_per_second=None,
        nonclaims=['Layer0 single projection only; no complete decoder/full model',
                   'Layer0 norm supplied as operator input; RMSNorm excluded from ROI',
                   'Golden row memoization valid only for position-independent layer0 norm/raw QKV; RTL computed all1024 rows',
                   'DDR bandwidth ceiling100/40GBps; not bank/refresh/latency calibration',
                   'Modified RTL timing/area still needs DC closure'])
    out=ROOT/f'reports/execution/Q1024_CONTINUOUS_{result["projection"]}_RESULT.json'
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ('status','projection','useful_mac_utilization','nominal_projection_latency_seconds')}))


if __name__=='__main__':main()
