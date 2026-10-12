"""Cold synthetic software gate. No downloaded weights or RTL generation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
SOURCE_DIRS=tuple(Path(__file__).parent / name for name in ('', 'conv', 'prep'))


def source_files():
    return sorted(p for directory in SOURCE_DIRS for p in directory.iterdir()
                  if p.is_file() and p.suffix in ('.py','.cpp'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in source_files()}
    tests=sorted(p for directory in SOURCE_DIRS for p in directory.glob('test_*.py'))
    report=dict(scope='SYNTHETIC_TYPED_RMS_DENSE_CONV_INPUT_PREP_SOFTWARE_ONLY',status='RUNNING',
        source_sha256=sources,discovered_tests=[str(p.relative_to(ROOT)) for p in tests],
        suites=[],test_count=0,rtl_executed=False,checkpoint_payload_used=False)
    failed=False
    for path in tests:
        name='.'.join(path.relative_to(ROOT).with_suffix('').parts)
        argv=[sys.executable,'-m','unittest',name,'-v']
        started=time.monotonic()
        try:
            result=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=120)
            code=result.returncode; log=result.stdout+result.stderr
        except subprocess.TimeoutExpired as e:
            code=124
            log=str(e)+'\n'+(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace')
        logfile='__'.join(path.relative_to(Path(__file__).parent).with_suffix('').parts)+'.log'
        (args.out/logfile).write_text(log)
        found=re.findall(r'^Ran (\d+) tests? in ',log,re.M)
        count=int(found[-1]) if found else 0
        ok=code==0 and count>0 and re.search(r'^OK$',log,re.M) is not None and 'skipped=' not in log
        failed |= not ok
        report['test_count']+=count
        report['suites'].append(dict(module=name,argv=argv,returncode=code,test_count=count,
            passed=ok,seconds=time.monotonic()-started,log=logfile,log_sha256=hashlib.sha256(log.encode()).hexdigest()))
        (args.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print(name,count,'PASS' if ok else 'FAIL',flush=True)
    after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in source_files()}
    report['sources_unchanged']=sources==after
    failed |= not report['sources_unchanged'] or not tests
    report['status']='FAILED' if failed else 'PASS_SYNTHETIC_SOFTWARE_ONLY'
    (args.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(1 if failed else 0)


if __name__=='__main__':main()
