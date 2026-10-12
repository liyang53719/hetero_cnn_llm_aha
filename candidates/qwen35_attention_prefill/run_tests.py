"""Cold source and synthetic projection-prefix gate; no model download or RTL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from .run_projection_prefix import SOURCE_FILES
from .run_norm_rope import SOURCE_FILES as NORM_ROPE_SOURCE_FILES

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    dependencies={'candidates/qwen35_gdn_prefill/test_rms_owner.py',
        'candidates/qwen35_gdn_prefill/prep/scalar.py', 'candidates/qwen35_gdn_prefill/conv/scalar.py'}
    paths=sorted(set(SOURCE_FILES) | set(NORM_ROPE_SOURCE_FILES) | dependencies | {str(p.relative_to(ROOT)) for p in DIRECTORY.rglob('*')
        if p.is_file() and p.suffix in ('.py','.json','.cpp')})
    def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    sources=hashes()
    tests=sorted(DIRECTORY.rglob('test_*.py'))
    report=dict(status='RUNNING',scope='SYNTHETIC_TYPED_L3_PROJECTION_PREFIX_ONLY',source_sha256=sources,
        discovered_tests=[str(p.relative_to(ROOT)) for p in tests],suites=[],tests=0,
        checkpoint_payload_used=False,official_forward_executed=False,rtl_executed=False)
    failed=False
    child_environment = {**os.environ, 'PYTHONPATH': str(ROOT / 'src')}
    for path in tests:
        module='.'.join(path.relative_to(ROOT).with_suffix('').parts)
        argv=[sys.executable,'-B','-m','unittest',module,'-v'];start=time.monotonic()
        try:
            result=subprocess.run(argv,cwd=ROOT,env=child_environment,capture_output=True,text=True,timeout=180)
            code,log=result.returncode,result.stdout+result.stderr
        except subprocess.TimeoutExpired as error:
            code,log=124,str(error)+'\n'+(error.stdout or b'').decode(errors='replace')+(error.stderr or b'').decode(errors='replace')
        counts=re.findall(r'^Ran (\d+) tests? in ',log,re.M)
        count=int(counts[-1]) if counts else 0
        passed=code==0 and count>0 and re.search(r'^OK$',log,re.M) is not None and 'skipped=' not in log
        failed |= not passed
        filename=module.replace('.','__')+'.log'
        (args.out/filename).write_text(log)
        report['tests']+=count
        report['suites'].append(dict(module=module,tests=count,returncode=code,passed=passed,
            elapsed_seconds=time.monotonic()-start,log=filename,log_sha256=hashlib.sha256(log.encode()).hexdigest()))
        (args.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print(module,count,'PASS' if passed else 'FAIL',flush=True)
    report['sources_unchanged']=hashes()==sources
    report['status']='PASS_SYNTHETIC_TYPED_L3_PREFIX_ONLY' if tests and not failed and report['sources_unchanged'] else 'FAILED'
    (args.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if report['status'].startswith('PASS_') else 1)


if __name__=='__main__':main()
