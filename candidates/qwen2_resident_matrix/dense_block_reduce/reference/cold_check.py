"""Run the small suite in a temporary source tree with no work/ artifacts."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from . import builder as b

DEPENDENCIES=tuple(b.GENERATOR_PINS)+(
    'tests/test_qwen2_rms_rope_policy_diagnostic.py',
    'chisel/continuous_prefill/tests/qwen2_block.cpp',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala',
)

CHILD=r'''
import json,os,pathlib,sys,unittest
cold=pathlib.Path.cwd();original=pathlib.Path(os.environ['QKV_COLD_FORBIDDEN_ROOT'])
assert not (cold/'work').exists()
def reject_original_tree(event,args):
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        path=pathlib.Path(os.fsdecode(args[0])).resolve()
        if path.is_relative_to(original):
            raise RuntimeError('cold test attempted original-tree file read: '+str(path))
sys.addaudithook(reject_original_tree)
from candidates.qwen2_resident_matrix.dense_block_reduce.reference import builder as b
assert b.ROOT==cold
suite=unittest.defaultTestLoader.loadTestsFromName('candidates.qwen2_resident_matrix.dense_block_reduce.reference.test_builder')
result=unittest.TextTestRunner(verbosity=2).run(suite)
original_cpp,header,_=b.regenerate_sources()
changed,_=b.transform(original_cpp,(b.ROOT/b.PROFILE_REL).read_bytes())
print(json.dumps(dict(tests_run=result.testsRun,passed=result.wasSuccessful(),
    original_cpp_sha256=b.sha(original_cpp),header_sha256=b.sha(header),
    candidate_cpp_sha256=b.sha(changed),profile_sha256=b.file_sha(b.ROOT/b.PROFILE_REL),
    work_directory_present=(cold/'work').exists(),original_tree_python_reads_forbidden=True)))
sys.exit(0 if result.wasSuccessful() else 1)
'''

def check():
    source_files=[b.ROOT/name for name in DEPENDENCIES]
    source_files.extend(p for p in b.HERE.rglob('*') if p.is_file()
                        and '__pycache__' not in p.parts and p.suffix not in ('.log',)
                        and p.name!='COLD_CHECK.json')
    git_dir=subprocess.run(['git','rev-parse','--absolute-git-dir'],cwd=b.ROOT,
                           capture_output=True,text=True,check=True,timeout=5).stdout.strip()
    files={str(path.relative_to(b.ROOT)):b.file_sha(path) for path in source_files}
    with tempfile.TemporaryDirectory(prefix='qkv_reference_cold_') as name:
        cold=Path(name)
        for relative in files:
            target=cold/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(b.ROOT/relative,target)
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',
            OMP_NUM_THREADS='1',PYTHONPATH=str(cold),GIT_DIR=git_dir,GIT_WORK_TREE=str(cold),
            QKV_COLD_FORBIDDEN_ROOT=str(b.ROOT))
        for variable in ('GIT_COMMON_DIR','GIT_INDEX_FILE'):env.pop(variable,None)
        started=time.monotonic()
        done=subprocess.run([sys.executable,'-c',CHILD],cwd=cold,env=env,
                            capture_output=True,text=True,timeout=30)
        elapsed=time.monotonic()-started
        report=dict(schema=1,status='PASS' if done.returncode==0 else 'FAIL',
            scope='Source regeneration, syntax-only, isolated dot arithmetic and provenance tests; no full-block execution',
            copied_source_sha256=files,python=sys.executable,returncode=done.returncode,
            wall_seconds=elapsed,stdout=done.stdout,stderr=done.stderr,
            git_access='Existing repository Git object database read-only for guarded HEAD source checks; no checkout/work data copied',
            full_reference_rerun=False,new_native_executed=False,rtl_executed=False)
        if done.returncode==0:report['checks']=json.loads(done.stdout.strip().splitlines()[-1])
    b.require(all(b.file_sha(b.ROOT/relative)==digest for relative,digest in files.items()),
              'source changed during cold test')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',type=Path)
    args=parser.parse_args()
    if args.receipt:
        b.require(args.receipt.resolve().is_relative_to(b.HERE) and not args.receipt.exists(),
                  'fresh receipt inside reference/ required')
    report=check()
    if args.receipt:args.receipt.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));sys.exit(report['returncode'])
