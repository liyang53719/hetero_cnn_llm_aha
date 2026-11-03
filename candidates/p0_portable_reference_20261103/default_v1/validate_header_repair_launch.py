"""Separate first-attempt header-only launch, explicitly linked to failed run."""
import hashlib
import json
import os
from pathlib import Path
import re
from fixture_gate import strict_json, need
from validate_launch import git, SOURCE

LAUNCH='ci_launch/p0_portable_header_repair_41720209902_once.json'

def main():
    need(os.environ.get('GITHUB_EVENT_NAME')=='push' and os.environ.get('GITHUB_REF')=='refs/heads/main' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','PRECHECK_PIN')
    event=strict_json(os.environ['GITHUB_EVENT_PATH']);head=os.environ['GITHUB_SHA'];parent=git('rev-parse',head+'^').decode().strip()
    need(event['after']==head and event['before']==parent and not event['forced'] and not event['deleted'],'PRECHECK_PIN')
    need(git('rev-list','--count',parent+'..'+head).strip()==b'1' and git('diff-tree','--no-commit-id','--name-status','-r',head).decode().strip()=='A\t'+LAUNCH,'PRECHECK_PIN')
    v=strict_json(LAUNCH)
    need(set(v)=={'schema','source_commit','source_manifest_sha256','nonce','scope','failed_run_id'},'PRECHECK_PIN')
    need(v['schema']=='P0_HEADER_REPAIR_ONE_SHOT_V1' and v['scope']=='HEADER_ONLY_NO_RUNTIME_WEIGHTS_REFERENCE_EDA_THREE_JSON' and type(v['failed_run_id']) is int and v['failed_run_id']==41720209902,'PRECHECK_PIN')
    need(v['source_commit']==parent and re.fullmatch('[0-9a-f]{64}',v['source_manifest_sha256']) and re.fullmatch('[0-9a-f]{32}',v['nonce']),'PRECHECK_PIN')
    need(hashlib.sha256(git('show',parent+':'+SOURCE)).hexdigest()==v['source_manifest_sha256'],'PRECHECK_PIN')
    identity=dict(schema='P0_HEADER_REPAIR_IDENTITY_V1',run_id=int(os.environ['GITHUB_RUN_ID']),source_commit=parent,launch_commit=head,source_manifest_sha256=v['source_manifest_sha256'],nonce=v['nonce'],failed_run_id=v['failed_run_id'])
    with (Path(os.environ['RUNNER_TEMP'])/'p0-header-repair-identity.json').open('x') as f:json.dump(identity,f,sort_keys=True);f.write('\n')
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('source_sha='+parent+'\n')

if __name__=='__main__':main()
