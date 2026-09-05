#!/usr/bin/env python3
"""Update only Q checkpoint metadata, preserving the <=40-line handoff."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def replace_one(text, pattern, replacement):
    updated,count=re.subn(pattern,lambda _:replacement,text,flags=re.M)
    if count!=1: raise ValueError(f'expected exactly one handoff field: {pattern}')
    return updated


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--segment',type=int,required=True);args=parser.parse_args()
    assert args.segment>=0
    directory=ROOT/'work/results/q1024_continuous/p0'
    lock=(directory.parent/'controller.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not (directory/f'segment_{args.segment+1:03d}.json').exists(), 'newer receipt exists'
    receipt_path=directory/f'segment_{args.segment:03d}.json'
    receipt=json.loads(receipt_path.read_text())
    assert receipt['projection']==0 and receipt['segment']==args.segment and receipt['status']=='CHECKPOINT'
    log_path=Path(receipt['log']);log=log_path.read_text()
    assert hashlib.sha256(log_path.read_bytes()).hexdigest()==receipt['log_sha256']
    match=re.search(r'^SEGMENT_MATRIX_STEPS (\d+)$',log,re.M);assert match
    steps=int(match[1]);cycle=receipt['saved_cycle'];next_segment=args.segment+1
    command=f'taskset -c 8-23 python3 scripts/run_q1024_projection_segment.py --projection 0 --segment {next_segment}'
    base=ROOT/'reports/execution'
    handoff=(base/'HANDOFF.md').read_text()
    assert len(handoff.splitlines())<=40
    handoff=replace_one(handoff,r'^- Q 段.*$',f'- Q 段0–{args.segment}已保存；最新{cycle}周期、{steps}个完成的Matrix step。')
    handoff=replace_one(handoff,r'^- Q receipt：.*$',f'- Q receipt：{receipt_path.relative_to(ROOT)}。')
    handoff=replace_one(handoff,r'^taskset -c 8-23 python3 scripts/run_q1024_projection_segment.py --projection 0 --segment \d+$',command)
    assert len(handoff.splitlines())<=40
    ledger=json.loads((base/'MASTER_LEDGER.json').read_text());goal=ledger['current_performance_goal']
    assert goal['status']=='ACTIVE'
    goal.update(stage=f'P2_Q1024_K_V_COMPLETE_Q_SEGMENT{args.segment}_CHECKPOINTED',q1024_Q_latest_saved_cycle=cycle,q1024_Q_next_segment=next_segment)
    action=json.loads((base/'NEXT_ACTION.json').read_text())
    action.update(stage=f'Q1024_P2_K_V_COMPLETE_Q_SEGMENT{args.segment}_CHECKPOINTED',unique_next_action=command+' ; numeric check pending. Do not rebuild simulator, alter fixtures or saved Tcl recipes.')
    progress=json.loads((base/'Q1024_Q_REPLAY_PROGRESS.json').read_text())
    assert not progress['full_q_projection_numeric_pass']
    progress.update(completed_segments=list(range(next_segment)),latest_saved_cycle=cycle,latest_completed_matrix_steps=steps,latest_receipt=str(receipt_path.relative_to(ROOT)),next_command=command)
    # All validation precedes writes; immutable execution receipts remain authority.
    (base/'HANDOFF.md').write_text(handoff)
    for name,value in [('MASTER_LEDGER.json',ledger),('NEXT_ACTION.json',action),('Q1024_Q_REPLAY_PROGRESS.json',progress)]:
        (base/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(dict(segment=args.segment,cycle=cycle,steps=steps,handoff_lines=len(handoff.splitlines()))))


if __name__=='__main__':main()
