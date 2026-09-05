#!/usr/bin/env python3
"""Block on all-row replay then assemble ACTUAL attention outputs for OProj."""
import array
import fcntl
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    directory=ROOT/'work/results/q1024_captured_attention_payload'
    with (directory/'coordinator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        paths=sorted(directory.glob('qt[0-9][0-9].json'));assert len(paths)==64,'Incomplete replay; no output substitution'
        fp=array.array('I',[0])*(1024*1536);sources={};identity=None
        for qt,path in enumerate(paths):
            r=json.loads(path.read_text());assert r['status']=='PASS' and r['qt']==qt
            if identity is None:identity=r['identity']
            assert r['identity']==identity
            actual=Path(r['output']);assert sha(actual)==r['output_sha256']
            assert sha(Path(r['log']))==r['log_sha256']
            words=[int(s,16) for s in actual.read_text().splitlines()];assert len(words)==24576
            fnv=0xcbf29ce484222325
            for w in words:fnv=((fnv^w)*0x100000001b3)&((1<<64)-1)
            assert f'{fnv:016x}'==r['output_hash']
            for h in range(12):
                for row in range(16):
                    start=((qt*16+row)*12+h)*128
                    fp[start:start+128]=array.array('I',words[(h*16+row)*128:(h*16+row+1)*128])
            sources[path.name]=sha(path)
        for path,h in identity.items():assert sha(ROOT/path)==h
        assert all((w&0x7f800000)!=0x7f800000 for w in fp),'Nonfinite actual result'
        bf=array.array('H',(((w+0x7fff+((w>>16)&1))>>16)&0xffff for w in fp))
        if sys.byteorder!='little':fp.byteswap();bf.byteswap()
        fpath=directory/'attention_actual_token_major_fp32.bin'
        bpath=directory/'attention_actual_token_major_bf16.bin'
        fpath.write_bytes(fp.tobytes());bpath.write_bytes(bf.tobytes())
        result=dict(status='PASS_CAPTURED_ATTENTION_TO_OPROJ_INPUT',rows=1024,columns=1536,
                    fp32_sha256=sha(fpath),bf16_sha256=sha(bpath),rounding='BF16_RNE',
                    receipt_sha256=sources,source='Actual Matrix/SFU normalized outputs, not golden replacement',
                    full_decoder_pass=False,integrated_cycles=None)
        (ROOT/'reports/execution/Q1024_ATTENTION_OPROJ_INPUT_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
        print(result['status'],flush=True)
if __name__=='__main__':main()
