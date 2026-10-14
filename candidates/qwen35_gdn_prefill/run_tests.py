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
SOURCE_DIRS=tuple(Path(__file__).parent / name for name in ('', 'conv', 'prep', 'chunk', 'gated_norm', 'elementwise', 'native'))
SOURCE_DIRS += tuple(Path(__file__).parent.parent / name for name in (
    'qwen35_35b_prefill', 'qwen35_35b_payload', 'qwen35_35b_payload/tests',
    'qwen35_35b_rms', 'qwen35_35b_projection_reference', 'qwen35_35b_conv', 'qwen35_35b_ab', 'qwen35_35b_prep', 'qwen35_35b_exp', 'qwen35_35b_gated_norm', 'qwen35_35b_output', 'qwen35_35b_postnorm', 'shared_resource_timing'))
PAYLOAD_DEPENDENCIES = tuple('src/heteronpu/' + name + '.py' for name in (
    '__init__', 'config', 'model_geometry', 'weight_header_contract',
    'qwen35_dense_contract', 'pinned_block_payload', 'pinned_gdn_payload',
    'qwen_family_contracts', 'abi_validation', 'cgra_sfu', 'command',
    'dtypes', 'kv_engine', 'matrix_engine', 'scheduler'))


def source_files():
    from candidates.qwen35_35b_payload.packer import selection
    plan = selection(ROOT)
    bundle = json.loads((ROOT / plan['bundle']['path']).read_bytes())
    records = [plan[key] for key in ('bundle', 'config', 'forward', 'index', 'profile')]
    records += [shard['header'] for shard in bundle['shards']]
    paths = {p for directory in SOURCE_DIRS for p in directory.iterdir()
             if p.is_file() and p.suffix in ('.py', '.cpp', '.c', '.json')}
    paths.add(ROOT / "config/upstream/weight_headers/qwen3_5_35b_a3b/activations.py")
    paths.update(ROOT / name for name in PAYLOAD_DEPENDENCIES)
    paths.update(ROOT / record['path'] for record in records)
    from candidates.shared_resource_timing.model import SOURCE_PINS
    paths.update(ROOT / pin.path for pin in SOURCE_PINS)
    return sorted(paths)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in source_files()}
    tests=sorted(p for directory in SOURCE_DIRS for p in directory.glob('test_*.py'))
    report=dict(scope='SYNTHETIC_GDN_TYPED_FULLBLOCK_CONTROL_AND_COMPONENT_SOFTWARE_ONLY',status='RUNNING',
        source_sha256=sources,discovered_tests=[str(p.relative_to(ROOT)) for p in tests],
        suites=[],test_count=0,rtl_executed=False,checkpoint_payload_used=False)
    failed=False
    for path in tests:
        name='.'.join(path.relative_to(ROOT).with_suffix('').parts)
        pytest_suite = path.parent == ROOT / 'candidates/qwen35_35b_payload/tests'
        argv=([sys.executable,'-m','pytest',str(path),'-o','addopts=','-q','--disable-warnings'] if pytest_suite
              else [sys.executable,'-m','unittest',name,'-v'])
        started=time.monotonic()
        try:
            result=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=120)
            code=result.returncode; log=result.stdout+result.stderr
        except subprocess.TimeoutExpired as e:
            code=124
            log=str(e)+'\n'+(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace')
        relative = (path.relative_to(Path(__file__).parent) if path.is_relative_to(Path(__file__).parent)
                    else path.relative_to(Path(__file__).parent.parent))
        logfile='__'.join(relative.with_suffix('').parts)+'.log'
        (args.out/logfile).write_text(log)
        found=(re.findall(r'\b(\d+) passed\b',log) if pytest_suite
               else re.findall(r'^Ran (\d+) tests? in ',log,re.M))
        count=int(found[-1]) if found else 0
        complete=(not re.search(r'\b\d+ (?:skipped|xfailed|xpassed|deselected)\b',log) if pytest_suite
                  else re.search(r'^OK$',log,re.M) is not None and 'skipped=' not in log)
        ok=code==0 and count>0 and complete
        failed |= not ok
        report['test_count']+=count
        report['suites'].append(dict(module=name,argv=argv,returncode=code,test_count=count,
            framework='pytest' if pytest_suite else 'unittest', passed=ok,
            seconds=time.monotonic()-started,log=logfile,log_sha256=hashlib.sha256(log.encode()).hexdigest()))
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
