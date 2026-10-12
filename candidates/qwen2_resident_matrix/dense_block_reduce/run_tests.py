#!/usr/bin/env python3
"""Run each discovered small reduction suite in a fresh interpreter.

Imports are isolated so exact observer bytecode/source guards stay strict.
No archived tensors, download, full prefill, Chisel or RTL is invoked here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
FAILURE_TAIL_BYTES=16*1024
FAILURE_TAIL_LINES=80


def failure_tail(log):
    """Bound CI console output; keep the complete child log in the artifact."""
    with log.open('rb') as f:
        f.seek(max(0,log.stat().st_size-FAILURE_TAIL_BYTES))
        tail=f.read().decode('utf-8',errors='replace')
    return '\n'.join(tail.splitlines()[-FAILURE_TAIL_LINES:])


def run(out,timeout=120):
    out=Path(out).resolve()
    if out.exists() or not 1<=timeout<=300:raise ValueError('fresh bounded test output required')
    files=sorted(HERE.rglob('test_*.py'))
    if not files or any(p.is_symlink() for p in files):raise ValueError('regular complete test discovery required')
    def inventory():return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.rglob('test_*.py'))}
    hashes=inventory();out.mkdir(parents=True)
    r=dict(schema=1,status='RUNNING',source_sha256=hashes,results=[],total_tests=0,skips_allowed=False)
    def save():(out/'summary.json').write_text(json.dumps(r,indent=2)+'\n')
    save()
    for p in files:
        relative=str(p.relative_to(ROOT));name=relative[:-3].replace('/','.')
        argv=[sys.executable,'-u','-m','unittest',name,'-v'];log=out/(str(len(r['results'])).zfill(2)+'-'+p.stem+'.log')
        start=time.monotonic()
        with log.open('w') as f:
            try:code=subprocess.run(argv,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                code=124
                f.write(f'\nIsolated suite timed out after {timeout} seconds.\n')
        text=log.read_text();counts=re.findall(r'^Ran (\d+) tests? in .*$',text,re.M)
        count=int(counts[0]) if len(counts)==1 else 0
        passed=code==0 and count>0 and bool(re.search(r'^OK$',text,re.M))
        r['results'].append(dict(path=relative,argv=argv,returncode=code,tests=count,passed=passed,
            host_wall_seconds=time.monotonic()-start,log=log.name,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
        r['total_tests']+=count;save();print(relative,code,count,passed,flush=True)
        if not passed:
            print(f'FAILED isolated suite: {relative}; full log: {log}',flush=True)
            print(f'--- failure tail (at most {FAILURE_TAIL_BYTES} bytes / {FAILURE_TAIL_LINES} lines) ---',flush=True)
            print(failure_tail(log),flush=True)
            print('--- end failure tail ---',flush=True)
    r.update(source_unchanged=hashes==inventory())
    r['status']='PASS' if r['source_unchanged'] and all(x['passed'] for x in r['results']) else 'FAIL'
    save();return r

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--timeout',type=int,default=120);a=p.parse_args()
    r=run(a.out,a.timeout);return 0 if r['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
