"""Dormant workflow admission: one new launch file, one source commit, first attempt."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from fixture_gate import strict_json, need

LAUNCH = 'ci_launch/p0_portable_reference_default_20261103_once.json'
SOURCE = 'candidates/p0_portable_reference_20261103/default_v1/SOURCE_MANIFEST.json'


def git(*args):
    return subprocess.check_output(['git', *args], env={'PATH':'/usr/bin:/bin'}, timeout=15)


def main():
    need(os.environ.get('GITHUB_EVENT_NAME') == 'push' and os.environ.get('GITHUB_REF') == 'refs/heads/main' and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'PRECHECK_PIN')
    event = strict_json(os.environ['GITHUB_EVENT_PATH'])
    head = os.environ['GITHUB_SHA']
    need(event['after'] == head and not event['forced'] and not event['deleted'], 'PRECHECK_PIN')
    parent = git('rev-parse', head+'^').decode().strip()
    need(event['before'] == parent and git('rev-list','--count',parent+'..'+head).strip() == b'1', 'PRECHECK_PIN')
    change = git('diff-tree','--no-commit-id','--name-status','-r',head).decode().strip()
    need(change == 'A\t'+LAUNCH, 'PRECHECK_PIN')
    launch = strict_json(LAUNCH)
    need(set(launch) == {'schema','source_commit','source_manifest_sha256','nonce','scope'}, 'PRECHECK_PIN')
    need(launch['schema'] == 'P0_DEFAULT_REFERENCE_ONE_SHOT_V1' and launch['scope'] == 'REFERENCE_ONLY_NO_DUT_NO_EDA_THREE_JSON', 'PRECHECK_PIN')
    need(launch['source_commit'] == parent and re.fullmatch('[0-9a-f]{64}',launch['source_manifest_sha256']) and re.fullmatch('[0-9a-f]{32}',launch['nonce']), 'PRECHECK_PIN')
    import hashlib
    need(hashlib.sha256(git('show',parent+':'+SOURCE)).hexdigest() == launch['source_manifest_sha256'], 'PRECHECK_PIN')
    out = Path(os.environ['RUNNER_TEMP'])/'p0-default-identity.json'
    value = dict(schema='P0_DEFAULT_ONE_SHOT_IDENTITY_V1',run_id=int(os.environ['GITHUB_RUN_ID']),source_commit=parent,
                 launch_commit=head,source_manifest_sha256=launch['source_manifest_sha256'],nonce=launch['nonce'])
    with out.open('x') as stream:
        json.dump(value,stream,sort_keys=True);stream.write('\n')
    with open(os.environ['GITHUB_OUTPUT'],'a') as stream:
        stream.write('source_sha='+parent+'\n')

if __name__=='__main__':
    main()
