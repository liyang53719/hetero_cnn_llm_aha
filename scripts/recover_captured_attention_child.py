#!/usr/bin/env python3
"""Recover a completed orphan's numerical evidence; never invent its exit code."""
import argparse,fcntl,hashlib,json,math,os,re,select,struct,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--qt',type=int,required=True);a=ap.parse_args()
    assert 0<=a.qt<64
    out=ROOT/'work/results/q1024_captured_attention_payload'
    lock=(out/'coordinator.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    common=(ROOT/'work/results/q1024_continuous/coordinator.lock').open('a');fcntl.flock(common,fcntl.LOCK_EX|fcntl.LOCK_NB)
    path=out/f'qt{a.qt:02d}.json';old=path.read_bytes();r=json.loads(old)
    assert r['status']=='RUNNING' and r['qt']==a.qt
    p=Path(f'/proc/{r["pid"]}')
    if p.exists():
        assert f'+QT={a.qt}'.encode() in (p/'cmdline').read_bytes()
        try:
            fd=os.pidfd_open(r['pid']);ev=select.poll();ev.register(fd,select.POLLIN)
            print(f'WAIT_EXISTING_CHILD pid={r["pid"]} qt={a.qt}',flush=True)
            assert ev.poll(600000),'Still live; no restart authorized'
            os.close(fd)
        except ProcessLookupError:pass
    for rel,h in r['identity'].items():assert sha(ROOT/rel)==h
    log=Path(r['log']);text=log.read_text()
    assert not re.search(r'Error:|Fatal:|%Error',text)
    matches=re.findall(r'Q1024_CAPTURED_ATTENTION_QT_PASS qt=(\d+) rows_heads=(\d+) tasks=(\d+) merges=(\d+) cycles=(\d+) hash=([0-9a-f]+)',text)
    assert len(matches)==1,'No complete evidence: preserve output and investigate'
    q,rows,tasks,merges,cycles=map(int,matches[0][:5]);h=matches[0][5]
    assert q==a.qt and rows==192 and tasks==12*((q+2)//2) and merges==192*(q//8)
    actual=out/f'qt{q:02d}.fp32.memh';lines=actual.read_text().splitlines()
    assert len(lines)==24576 and all(re.fullmatch('[a-fA-F0-9]{8}',s) for s in lines)
    words=[int(s,16) for s in lines];fnv=0xcbf29ce484222325
    for w in words:fnv=((fnv^w)*0x100000001b3)&((1<<64)-1)
    assert f'{fnv:016x}'==h
    expected=[int(s,16) for s in (ROOT/'work/results/q1024_post_projection/attention_vectors/expected_fp32.memh').read_text().splitlines()]
    def f(w):return struct.unpack('<f',struct.pack('<I',w))[0]
    maximum=0.0
    for i,w in enumerate(words):
        head=i//2048;row=(i//128)%16;dim=i%128
        av=f(w);ex=f(expected[(head*1024+q*16+row)*128+dim]);assert math.isfinite(av) and math.isfinite(ex)
        error=abs(av-ex);assert error<=0.002,(q,head,row,dim,error);maximum=max(maximum,error)
    backup=path.with_suffix('.orphan_original.json');assert not backup.exists();backup.write_bytes(old)
    r.update(status='PASS',returncode=None,exit_code_retrievable=False,
             recovery='Independent full-output verification after original coordinator disappeared; original child not rerun',
             recovery_time=time.time(),original_receipt_sha256=sha(backup),
             rows_heads=rows,tasks=tasks,merges=merges,partition_cycles=cycles,output_hash=h,
             output=str(actual),output_sha256=sha(actual),output_words=len(words),log_sha256=sha(log),
             independent_max_error=maximum,independent_fp32_comparisons=len(words))
    path.write_text(json.dumps(r,indent=2)+'\n')
    report={k:r[k] for k in ['qt','status','returncode','exit_code_retrievable','recovery','original_receipt_sha256','independent_max_error','independent_fp32_comparisons','output_sha256','log_sha256']}
    (ROOT/'reports/execution/Q1024_ORPHAN_CHILD_RECOVERY.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
if __name__=='__main__':main()
