#!/usr/bin/env python3
"""One bounded real RTL segment. Never infer full-model PASS from projections."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        digest=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--projection',type=int,choices=(0,1,2),required=True);parser.add_argument('--segment',type=int,required=True);parser.add_argument('--retry-failed',action='store_true');args=parser.parse_args()
    assert args.segment>=0
    assert shutil.disk_usage(ROOT).free>50*1024**3
    directory=ROOT/f'work/results/q1024_continuous/p{args.projection}'
    directory.mkdir(parents=True,exist_ok=True)
    lock=(directory.parent/'controller.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    receipt=directory/f'segment_{args.segment:03d}.json'
    old_receipt=None;attempt=0;archive=None
    if receipt.exists():
        old_receipt=json.loads(receipt.read_text())
        if not args.retry_failed or old_receipt['status']!='FAILED':
            raise SystemExit('Receipt exists: only an explicitly failed attempt may be retried')
        if Path(f"/proc/{old_receipt.get('pid',0)}").exists():
            raise SystemExit('Prior PID still exists; inspect before retrying')
        attempt=old_receipt.get('attempt',0)+1
        archive=directory/f'segment_{args.segment:03d}.attempt{attempt-1}.failed.json'
        assert not archive.exists()
    elif args.retry_failed:
        raise SystemExit('No failed receipt to retry')
    sim=ROOT/'work/upstream/idma/target/sim/vcs/simv_group8_checkpoint'
    fixtures=ROOT/'work/results/qwen2_group8_pinned_idma'
    manifest_path=ROOT/'work/results/qwen2_q1024_projection_fixtures/result.json'
    manifest=json.loads(manifest_path.read_text())
    assert manifest['rows']==1024
    for item in manifest['output'].values(): assert sha(ROOT/item['path'])==item['sha256']
    identity={str(p.relative_to(ROOT)):sha(p) for p in (sim,manifest_path,fixtures/'projection_commands.memh',fixtures/'records.memh',fixtures/'projection_addresses.memh')}
    env=os.environ.copy();env.pop('QWEN_RESTORE_PATH',None)
    previous=None
    if args.segment:
        previous=json.loads((directory/f'segment_{args.segment-1:03d}.json').read_text())
        assert previous['projection']==args.projection
        # Migrate first receipt: recipe can change; executable and input identity cannot.
        previous_design={k:v for k,v in previous['identity'].items() if not k.startswith('scripts/')}
        assert previous['status']=='CHECKPOINT' and previous_design==identity
        previous_recipe=Path(previous['command'][-1])
        expected_recipe=previous.get('control_recipe_sha256') or previous['identity'].get(str(previous_recipe.relative_to(ROOT)))
        assert expected_recipe and sha(previous_recipe)==expected_recipe, 'saved recipe changed'
        for path,expected in previous['checkpoint_files'].items(): assert sha(Path(path))==expected
        env['QWEN_RESTORE_PATH']=previous['checkpoint']
    suffix=f'_attempt{attempt}' if attempt else ''
    checkpoint=directory/f'segment_{args.segment:03d}{suffix}.chk'
    assert not checkpoint.exists()
    assert not any(c in str(checkpoint) for c in '{}\n\r')
    control=directory.parent/'next_control.tcl'
    control.write_text('set qwen_checkpoint_target {'+str(checkpoint)+'}\n')
    env['QWEN_SAVE_PATH']=str(checkpoint);env['MIN_AVAILABLE_KIB']='10485760'
    recipe=ROOT/('scripts/q1024_projection_segment_v2.tcl' if previous else 'scripts/q1024_projection_start.tcl')
    if previous and args.projection==0:
        recipe=ROOT/'scripts/q1024_projection_q_segment.tcl'
    cmd=[str(ROOT/'scripts/run_memory_capped.sh'),'timeout','600',str(sim),f'+PROJECTION={args.projection}','+BATCHES=64','+FULL_Q1024',f'+COMMANDS={fixtures}/projection_commands.memh',f'+RECORDS={fixtures}/records.memh',f'+ADDR={fixtures}/projection_addresses.memh','-ucli','-do',str(recipe)]
    logfile=directory/f'segment_{args.segment:03d}{suffix}.log'
    result=dict(status='RUNNING',projection=args.projection,segment=args.segment,identity=identity,command=cmd,cwd=str(ROOT),started_unix=time.time(),log=str(logfile),cpu_affinity='8-23',memory_max='30G')
    result['control_recipe_sha256']=sha(recipe)
    result['attempt']=attempt
    if archive:
        archive.write_bytes(receipt.read_bytes())
        result['prior_failed_receipt']=str(archive)
    result['next_control_sha256']=sha(control)
    with logfile.open('w') as output:
        proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT)
        result['pid']=proc.pid;receipt.write_text(json.dumps(result,indent=2)+'\n')
        code=proc.wait()
    result['returncode']=code;result['log_sha256']=sha(logfile)
    log=logfile.read_text()
    try:
        assert code==0 and not re.search(r'Fatal:|Error-\[|Error:',log)
        if previous:
            restored=re.search(r'^SEGMENT_ENTRY_CYCLE (\d+)$',log,re.M)
            assert restored and int(restored[1])==previous['saved_cycle']
        marker=re.search(r'^GROUP8_PINNED_IDMA_NUMERICAL_PASS .*$',log,re.M)
        if marker:
            assert 'batches=64 ' in marker[0] and 'full_fixture=1' in marker[0]
            fields={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',marker[0])}
            columns=1536 if args.projection==0 else 256
            assert fields['projection']==args.projection
            assert fields['checked_bf16']==1024*columns
            assert fields['useful_macs']==1024*columns*1536
            assert fields['wall_cycles']>0 and fields['useful_macs']<=512*fields['wall_cycles']
            result.update(status='PROJECTION_NUMERICAL_COMPLETE',marker=marker[0],full_model_complete=False)
        else:
            saved=re.search(r'^SEGMENT_SAVED_CYCLE (\d+)$',log,re.M)
            assert saved and int(saved[1])>(previous['saved_cycle'] if previous else 0)
            files=[checkpoint,Path(str(checkpoint)+'.ucli')]+sorted(Path(str(checkpoint)+'.FILES').rglob('*'))
            assert checkpoint.is_file() and Path(str(checkpoint)+'.ucli').is_file() and len(files)>2
            result.update(status='CHECKPOINT',saved_cycle=int(saved[1]),checkpoint=str(checkpoint),checkpoint_files={str(p):sha(p) for p in files if p.is_file()})
    except (AssertionError,ValueError):
        result['status']='FAILED';receipt.write_text(json.dumps(result,indent=2)+'\n');raise
    receipt.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','projection','segment')}))


if __name__=='__main__': main()
