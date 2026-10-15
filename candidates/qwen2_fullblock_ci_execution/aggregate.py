"""Validate a completed CI bootstrap locally and emit only a fixed aggregate."""
import argparse
import hashlib
import json
from pathlib import Path
from . import inputs, summary, closure
ROOT=Path(__file__).resolve().parents[2]
OUT='work/qwen2_fullblock_ci_reference/ci01/bootstrap'
DEST='work/qwen2_fullblock_ci_execution/aggregate.json'

def file_identity(path):
    h=hashlib.sha256();size=0
    with path.open('rb') as stream:
        while chunk:=stream.read(1<<20):h.update(chunk);size+=len(chunk)
    return dict(bytes=size,sha256=h.hexdigest())

def collect(*,git_sha,source_digest):
    inputs.need(ROOT==inputs.CI_ROOT and ROOT.resolve()==ROOT,'fixed CI aggregate root')
    inputs.need(source_digest==closure.digest(ROOT),'reviewed source-only closure drift')
    out=inputs.safe_path(ROOT,OUT)
    seal=json.loads((out/'SEAL.json').read_bytes())
    for key,value in dict(status='SEALED_BOOTSTRAP_OBSERVATIONS_UNACCEPTED',mode='bootstrap',run_id='ci01',
        manifest='BOOTSTRAP_REFERENCE.json',numerical_acceptance_claimed=False,dut_executed=False,retries=0).items():
        inputs.need(type(seal.get(key)) is type(value) and seal[key]==value,'bootstrap seal rejected')
    files=seal['files']
    expected_files={name+'.f32le' for name in summary.specs()}|{'mask.bf16le','BOUNDARY_BEFORE.json',
        'BOUNDARY_AFTER.json','WRAPPER_BEFORE.json','WRAPPER_AFTER.json','BOOTSTRAP_REFERENCE.json',
        'GO.json','OBSERVATIONS.json','STAGES.jsonl','stdout.log','stderr.log'}
    inputs.need(type(files) is dict and set(files)==expected_files,'exact successful bootstrap inventory')
    inputs.need(set(p.name for p in out.iterdir())==set(files)|{'SEAL.json'},'bootstrap inventory mismatch')
    for name,identity in files.items():
        inputs.need(type(name) is str and '/' not in name and '\\' not in name and name not in ('.','..'),'direct inventory file required')
        path=inputs.safe_path(ROOT,OUT+'/'+name)
        inputs.need(identity==file_identity(path),'bootstrap inventory content drift')
    record=json.loads((out/'BOOTSTRAP_REFERENCE.json').read_bytes())
    inputs.need(record.get('wrapper_boundary_unchanged') is True and record.get('dut_executed') is False,
                'reference-only stable wrapper required')
    inputs.need(record.get('status')=='BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT' and record.get('stage')=='bootstrap','bootstrap record scope')
    resources=seal['resources']
    inputs.need(resources==record['resources'] and type(resources['returncode']) is int and resources['returncode']==0 and
        resources['limit_reason'] is None and resources['cleanup_pids']==[] and
        resources['descendant_cleanup']['remaining_descendants']=={} and
        resources['overall_wall_limit_seconds']==120 and resources['external_watchdog_deadline_seconds']==122 and
        resources['independent_overall_watchdog_enabled'] is True and
        0<=resources['overall_elapsed_seconds']<=122,'successful bounded bootstrap completion required')
    for name,item in record['outputs'].items():
        inputs.need(files.get(name+'.f32le')=={k:item[k] for k in ('bytes','sha256')},'output record/payload mismatch')
    result=summary.checked_aggregate(record['outputs'],git_sha=git_sha,source_digest=source_digest)
    target=inputs.safe_path(ROOT,DEST)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x') as stream:json.dump(result,stream,sort_keys=True,allow_nan=False);stream.write('\n')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collect',action='store_true')
    p.add_argument('--git-sha');p.add_argument('--source-digest');a=p.parse_args()
    if a.collect:collect(git_sha=a.git_sha,source_digest=a.source_digest)
    # No metadata or failure details emitted here. Workflow redirects stderr locally too.
    print('AGGREGATE_READY' if a.collect else 'NOT_EXECUTED')
if __name__=='__main__':main()
