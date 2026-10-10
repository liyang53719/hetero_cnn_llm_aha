#!/usr/bin/env python3
"""Skip production EDA only for an exact, source-free acceptance repair diff."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import host_attention_block_ci_scope as common

WORKFLOW = '.github/workflows/host-bf16-attention-block.yml'
ALLOWED = frozenset({
    '.github/scripts/attention_readonly_ci_scope.py',
    '.github/scripts/tests/test_attention_readonly_ci_scope.py',
    '.github/scripts/host_attention_block_ci_scope.py',
    '.github/scripts/tests/test_host_attention_block_ci_scope.py',
    '.github/scripts/verify_attention_block_split.py',
    '.github/scripts/tests/test_attention_block_split_acceptance.py',
    '.github/workflows/attention-block-readonly-acceptance.yml',
    'tools/attention_acceptance/run_readonly.py',
    'tests/test_attention_readonly_acceptance.py',
    'chisel/continuous_prefill/tests/test_host_bf16_attention_block_ci.py',
    'doc/U00_2_HOST_ATTENTION_BLOCK_CI_98C7_20261010_CN.md',
    'reports/execution/U00_2_HOST_ATTENTION_BLOCK_CI_98C7_20261010/summary.json',
    'reports/execution/U00_2_HOST_ATTENTION_BLOCK_CI_98C7_20261010/native_gap_audit.json',
    'doc/block_checklist.yaml',
})
SCOPE_JOB_BLOCK = """  # BEGIN ATTENTION_READONLY_CI_SCOPE
  readonly-scope:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    outputs:
      run_full: ${{ steps.classify.outputs.run_full }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: '${{ github.sha }}'
          fetch-depth: 0
      - name: Classify exact read-only acceptance repair
        id: classify
        env:
          BASE_SHA: ${{ github.event_name == 'push' && github.event.before || '' }}
          HEAD_SHA: ${{ github.sha }}
        run: |
          python3 .github/scripts/attention_readonly_ci_scope.py --base "$BASE_SHA" --head "$HEAD_SHA" --github-output "$GITHUB_OUTPUT"
  # END ATTENTION_READONLY_CI_SCOPE
"""
BUILD_GUARD = """    needs: readonly-scope
    if: ${{ always() && (needs.readonly-scope.result != 'success' || needs.readonly-scope.outputs.run_full != 'false') }}
"""
ACCEPTANCE_IF = "    if: ${{ always() && needs.build.result != 'skipped' }}\n"


def normalize_workflow(raw: bytes) -> bytes:
    text = raw.decode('utf-8')
    common.require(text.count('\njobs:\n') == 1, 'unknown production workflow layout')
    before, jobs = text.split('\njobs:\n', 1)
    if jobs.startswith(SCOPE_JOB_BLOCK):
        jobs = jobs[len(SCOPE_JOB_BLOCK):]
        common.require(jobs.count('  build:\n' + BUILD_GUARD) == 1, 'changed build scope wiring')
        jobs = jobs.replace('  build:\n' + BUILD_GUARD, '  build:\n', 1)
        expected = '  acceptance:\n    needs: [build, pass, fault]\n' + ACCEPTANCE_IF
        common.require(jobs.count(expected) == 1, 'changed acceptance scope wiring')
        jobs = jobs.replace(expected, '  acceptance:\n    needs: [build, pass, fault]\n    if: always()\n', 1)
    result = before + '\njobs:\n' + jobs
    common.require('ATTENTION_READONLY_CI_SCOPE' not in result and 'readonly-scope' not in result,
                   'nonliteral read-only scope wiring')
    return result.encode('utf-8')


def classify(repo: Path, base: str, head: str) -> dict:
    report = dict(run_full=True, base=base, head=head, changed_paths=[], reason='unclassified')
    try:
        common.validate_commit(repo, base, 'base')
        common.validate_commit(repo, head, 'head')
        changes = common.changed_files(repo, base, head)
        report['changed_paths'] = [row[0] for row in changes]
        common.require(changes, 'empty diff cannot prove read-only acceptance repair')
        for path, status, old_mode, new_mode in changes:
            common.require(status in {'A', 'M'} and new_mode in {'100644', '100755'}
                           and (old_mode == '000000' if status == 'A' else old_mode == new_mode),
                           'deletion, rename, mode or file-type change: ' + path)
            if path in ALLOWED:
                continue
            common.require(path == WORKFLOW and status == 'M', 'outside read-only acceptance: ' + path)
            old = common.git(repo, 'show', base + ':' + path)
            new = common.git(repo, 'show', head + ':' + path)
            common.require(normalize_workflow(old) == normalize_workflow(new),
                           'production workflow changed beyond exact scope wiring')
        report.update(run_full=False, reason='only read-only acceptance files and exact production scope wiring changed')
    except Exception as error:
        report['reason'] = str(error) or type(error).__name__
    return report


def main(argv=None):
    args = common.Parser(description=__doc__, allow_abbrev=False)
    args.add_argument('--base', default='')
    args.add_argument('--head', default='')
    args.add_argument('--github-output', default=os.environ.get('GITHUB_OUTPUT'))
    try:
        values = args.parse_args(argv)
        report = classify(Path.cwd(), values.base, values.head)
        if values.github_output:
            with Path(values.github_output).open('a', encoding='utf-8') as stream:
                stream.write('run_full=' + str(report['run_full']).lower() + '\n')
    except Exception as error:
        print(json.dumps(dict(run_full=True, reason=str(error)), sort_keys=True))
        return 1  # missing/failed output also runs full by the workflow guard
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
