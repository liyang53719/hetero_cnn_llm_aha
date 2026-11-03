"""One independent original AVX512 reference job; never a DEFAULT retry or fallback."""
import hashlib
import json
import os
from pathlib import Path
import re
from fixture_gate import strict_json, need
import subprocess

SOURCE='candidates/p0_original_avx512_reference_20261103/v1/SOURCE_MANIFEST.json'

def git(*args):
    return subprocess.check_output(['git', *args], env={'PATH':'/usr/bin:/bin'}, timeout=15)

LAUNCH='ci_launch/p0_original_avx512_reference_20261103_once.json'
DEFAULT_FAILED_RUN=41734412224


def main():
    need(os.environ.get('GITHUB_EVENT_NAME')=='push' and os.environ.get('GITHUB_REF')=='refs/heads/main' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','PRECHECK_PIN')
    event=strict_json(os.environ['GITHUB_EVENT_PATH']);head=os.environ['GITHUB_SHA'];parent=git('rev-parse',head+'^').decode().strip()
    need(event['after']==head and event['before']==parent and not event['forced'] and not event['deleted'],'PRECHECK_PIN')
    need(git('rev-list','--count',parent+'..'+head).strip()==b'1' and git('diff-tree','--no-commit-id','--name-status','-r',head).decode().strip()=='A\t'+LAUNCH,'PRECHECK_PIN')
    v=strict_json(LAUNCH)
    need(set(v)=={'schema','source_commit','source_manifest_sha256','nonce','scope','default_failed_run_id'},'PRECHECK_PIN')
    need(v['schema']=='P0_AVX512_ONE_SHOT_V1' and v['scope']=='REFERENCE_ONLY_NO_DUT_NO_EDA_THREE_JSON','PRECHECK_PIN')
    need(type(v['default_failed_run_id'])is int and v['default_failed_run_id']==DEFAULT_FAILED_RUN,'PRECHECK_PIN')
    need(v['source_commit']==parent and re.fullmatch('[0-9a-f]{64}',v['source_manifest_sha256']) and re.fullmatch('[0-9a-f]{32}',v['nonce']),'PRECHECK_PIN')
    need(hashlib.sha256(git('show',parent+':'+SOURCE)).hexdigest()==v['source_manifest_sha256'],'PRECHECK_PIN')
    identity=dict(schema='P0_AVX512_ONE_SHOT_IDENTITY_V1',run_id=int(os.environ['GITHUB_RUN_ID']),source_commit=parent,launch_commit=head,source_manifest_sha256=v['source_manifest_sha256'],nonce=v['nonce'],default_failed_run_id=v['default_failed_run_id'])
    with (Path(os.environ['RUNNER_TEMP'])/'p0-avx512-identity.json').open('x') as f:json.dump(identity,f,sort_keys=True);f.write('\n')
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('source_sha='+parent+'\n')

if __name__=='__main__':main()
