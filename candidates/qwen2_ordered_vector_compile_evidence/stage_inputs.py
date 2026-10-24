"""Stage exact sources and unchanged existing compiler support; never start Java."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SUPPORT='candidates/qwen2_resident_matrix/production_qk16_rebase/classcompile/'
def sha(data):return hashlib.sha256(data).hexdigest()
def stage(repo,baseline,overlay,out):
    if out.exists() or out.is_symlink():raise ValueError('fresh output required')
    source_pins=json.loads((HERE/'SOURCE_PINS.json').read_text())
    runner_pins=json.loads((HERE/'RUNNER_PINS.json').read_text())
    changed=set(json.loads((HERE/'SUMMARY.json').read_text())['changed_source_paths'])
    if len(source_pins)!=92 or len(changed)!=3:raise ValueError('exact 92/3 inventory required')
    staged={}
    for rel,h in source_pins.items():
        if Path(rel).is_absolute() or '..' in Path(rel).parts:raise ValueError('unsafe source path')
        data=((overlay if rel in changed else baseline)/rel).read_bytes()
        if sha(data)!=h:raise ValueError('source identity mismatch: '+rel)
        staged['scala/'+rel]=data
    for rel,h in runner_pins.items():
        if rel=='PLANNED_SOURCE_PINS.json':data=(HERE/'SOURCE_PINS.json').read_bytes()
        elif rel=='dependency_pins.json':data=(HERE/'DEPENDENCY_PINS.json').read_bytes()
        else:
            if rel not in ('compile_only.py','owned_compile.py','strict_cleanup.py'):raise ValueError('unexpected support')
            data=(repo/SUPPORT/rel).read_bytes()
        if sha(data)!=h:raise ValueError('runner identity mismatch: '+rel)
        staged['runner/'+rel]=data
    staged['runner/RUNNER_PINS.json']=(HERE/'RUNNER_PINS.json').read_bytes()
    out.mkdir(parents=True,exist_ok=False)
    for rel,data in staged.items():
        target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return {'status':'SOURCE_STAGE_PASS','sources':92,'candidate_replacements':3,'compiler_started':False}
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('repo-root','baseline-root','candidate-overlay','out'):parser.add_argument('--'+name,required=True,type=Path)
    a=parser.parse_args();print(json.dumps(stage(a.repo_root,a.baseline_root,a.candidate_overlay,a.out)))
