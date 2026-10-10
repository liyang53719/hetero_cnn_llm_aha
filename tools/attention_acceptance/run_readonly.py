#!/usr/bin/env python3
"""Read-only re-admission of one frozen Attention build and its original cases.

Only GitHub-authenticated compact proof ZIPs are downloaded. Their API-provided
archive digests establish the trust boundary before member digests are derived.
No build archive, ELF, weights, tensors, capture, simulator or EDA is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = 'liyang53719/hetero_cnn_llm_aha'
REPOSITORY_ID = 1345575853
RUN_ID, ATTEMPT = 38015586840, 1
PRODUCTION_COMMIT = '98c7d80f65c5f05b55726c5239a6e9ec15d1b53f'
WORKFLOW_NAME = 'qwen35-production-Host-Attention-Block'
WORKFLOW_PATH = '.github/workflows/host-bf16-attention-block.yml'
CHECKER_PATH = '.github/scripts/verify_attention_block_split.py'
JOB_IDS = {'build': 114105000691, 'pass': 114118686395, 'fault': 114118685810}
KNOWN_ARTIFACT_IDS = {'build': 11657479094, 'pass': 11659653260}
MEMBERS = ('summary.json', 'source_input_hashes.json')
BUILD_KEYS = ('package_sha256', 'binary_sha256', 'rtl_sha256',
              'build_ready_sha256', 'source_manifest_sha256', 'toolchain_sha256')
# The original compact build adds these wrappers to the sealed source manifest.
BUILD_COMPACT_WRAPPERS = frozenset((CHECKER_PATH, '.github/workflows/host-bf16-attention-core.yml'))
# The consumer adds exactly these official reference helpers; all remain bound
# to the frozen Git checkout by the aggregate checker, never ignored.
CONSUMER_EXTRA_SOURCES = frozenset(('scripts/rebuild_qk_norm256_corpora.py',
    'scripts/run_qwen35_bf16_audit.py', 'scripts/run_qwen35_prefix_chain.py'))
MAX_ZIP_BYTES, MAX_MEMBER_BYTES = 8 * 1024 * 1024, 16 * 1024 * 1024
PASS = 'PASS_ATTENTION_BLOCK_SPLIT_FROZEN_RECIPE_AND_FAULT_PROTOCOL'
PENDING = 'PENDING_ATTENTION_BLOCK_READONLY_ACCEPTANCE'
FAIL = 'FAIL_ATTENTION_BLOCK_READONLY_ACCEPTANCE'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate JSON key: ' + key)
        value[key] = item
    return value


def decode(raw):
    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=lambda _: require(False, 'nonfinite JSON'))
    require(type(value) is dict, 'JSON object required')
    return value


def sha256(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'invalid SHA256')
    return value


def write_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def timestamp(value):
    require(type(value) is str, 'missing GitHub timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, 'timezone required')
    return parsed


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, url):
        return None


class GitHub:
    """GET-only client. Never forward the Actions token to artifact storage."""
    def __init__(self, token):
        require(bool(token), 'GITHUB_TOKEN is required')
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path):
        require(path.startswith('/repos/' + REPOSITORY + '/actions/'), 'unexpected API path')
        return urllib.request.Request('https://api.github.com' + path, headers={
            'Accept': 'application/vnd.github+json', 'Authorization': 'Bearer ' + self.token,
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'attention-readonly-acceptance'})

    def json(self, path):
        with self.opener.open(self.request(path), timeout=30) as response:
            require(response.status == 200, 'GitHub API response is not 200')
            raw = response.read(4 * 1024 * 1024 + 1)
        require(len(raw) <= 4 * 1024 * 1024, 'oversized GitHub API response')
        return decode(raw)

    def archive(self, artifact_id):
        path = f'/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip'
        try:
            response = self.opener.open(self.request(path), timeout=30)
        except urllib.error.HTTPError as error:
            require(error.code == 302, 'artifact download did not return a signed redirect')
            location = error.headers.get('Location', '')
            parsed = urllib.parse.urlsplit(location)
            require(parsed.scheme == 'https' and not parsed.username and not parsed.password and
                    parsed.port in (None, 443) and parsed.hostname and
                    (parsed.hostname.endswith('.blob.core.windows.net') or
                     parsed.hostname.endswith('.githubusercontent.com')),
                    'unexpected artifact storage origin')
            # A fresh request deliberately has no Authorization header.
            response = self.opener.open(urllib.request.Request(location), timeout=60)
        with response:
            require(response.status == 200, 'artifact download response is not 200')
            raw = response.read(MAX_ZIP_BYTES + 1)
        require(0 < len(raw) <= MAX_ZIP_BYTES, 'empty/oversized compact artifact ZIP')
        return raw


def verify_run(run):
    expected = dict(id=RUN_ID, run_attempt=ATTEMPT, head_sha=PRODUCTION_COMMIT,
                    head_branch='main', name=WORKFLOW_NAME, path=WORKFLOW_PATH, event='push')
    for key, wanted in expected.items():
        require(type(run.get(key)) is type(wanted) and run[key] == wanted,
                'original run identity mismatch: ' + key)
    for key in ('repository', 'head_repository'):
        require(run.get(key, {}).get('id') == REPOSITORY_ID and
                run[key].get('full_name') == REPOSITORY, 'original repository mismatch')


def verify_jobs(rows):
    require(type(rows) is list, 'missing original job inventory')
    jobs = {}
    for role, job_id in JOB_IDS.items():
        matches = [row for row in rows if row.get('name') == role or row.get('id') == job_id]
        require(len(matches) == 1, 'missing/duplicate original job: ' + role)
        job = matches[0]
        for key, wanted in dict(id=job_id, name=role, run_id=RUN_ID,
                                run_attempt=ATTEMPT, head_sha=PRODUCTION_COMMIT).items():
            require(type(job.get(key)) is type(wanted) and job[key] == wanted,
                    'original job identity mismatch: ' + role + ':' + key)
        require(job.get('status') in ('queued', 'waiting', 'pending', 'in_progress', 'completed'),
                'unknown job status: ' + role)
        if job['status'] == 'completed':
            require(job.get('conclusion') == 'success', 'original job did not succeed: ' + role)
            require(timestamp(job['completed_at']) >= timestamp(job['started_at']), 'invalid job interval')
        else:
            require(job.get('conclusion') is None, 'nonterminal job has a conclusion')
        jobs[role] = job
    return jobs


def select_artifact(rows, role, job):
    name = f'host-attention-block-{role}-proof-{PRODUCTION_COMMIT}-{ATTEMPT}'
    matches = [row for row in rows if row.get('name') == name]
    require(len(matches) == 1, 'missing/duplicate compact proof: ' + role)
    artifact = matches[0]
    require(type(artifact.get('id')) is int and artifact['id'] > 0 and
            (role not in KNOWN_ARTIFACT_IDS or artifact['id'] == KNOWN_ARTIFACT_IDS[role]),
            'unexpected original artifact identity: ' + role)
    require(artifact.get('expired') is False, 'original compact proof has expired')
    require(type(artifact.get('size_in_bytes')) is int and
            0 < artifact['size_in_bytes'] <= MAX_ZIP_BYTES, 'compact artifact size bound')
    origin = artifact.get('workflow_run', {})
    for key, wanted in dict(id=RUN_ID, head_sha=PRODUCTION_COMMIT, head_branch='main',
                            repository_id=REPOSITORY_ID, head_repository_id=REPOSITORY_ID).items():
        require(type(origin.get(key)) is type(wanted) and origin[key] == wanted,
                'artifact source run mismatch: ' + key)
    require(timestamp(job['started_at']) <= timestamp(artifact['created_at']) <=
            timestamp(job['completed_at']), 'artifact is outside original job interval')
    require(type(artifact.get('digest')) is str and artifact['digest'].startswith('sha256:'),
            'GitHub artifact digest is required')
    sha256(artifact['digest'][7:])
    return artifact


def admit_archive(raw, artifact, destination):
    """Authenticate the complete ZIP before opening or deriving member pins."""
    require(len(raw) == artifact['size_in_bytes'], 'artifact ZIP byte count mismatch')
    require(digest(raw) == artifact['digest'][7:], 'GitHub artifact ZIP digest mismatch')
    values, pins = {}, {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        require(len(entries) == len(MEMBERS) and {row.filename for row in entries} == set(MEMBERS),
                'compact ZIP must contain exactly the two root JSON files')
        for entry in entries:
            mode = entry.external_attr >> 16
            require(not entry.is_dir() and not entry.flag_bits & 1 and
                    stat.S_IFMT(mode) in (0, stat.S_IFREG) and
                    0 < entry.file_size <= MAX_MEMBER_BYTES, 'invalid compact ZIP member')
            data = archive.read(entry)
            require(len(data) == entry.file_size, 'truncated compact ZIP member')
            values[entry.filename] = decode(data)
            pins[entry.filename] = {'sha256': digest(data), 'bytes': len(data)}
        destination.mkdir()
        for name in MEMBERS:
            (destination / name).write_bytes(archive.read(name))
    return values, pins


def trusted_build(evidence):
    summary, hashes = (evidence['build'][name] for name in MEMBERS)
    for key, wanted in dict(status='PASS_HOST_ATTENTION_BLOCK_BUILD_ONLY', stage='complete',
                            git_head=PRODUCTION_COMMIT, source_immutability_verified=True,
                            numerical_acceptance=False, frozen_recipe_block_acceptance=False,
                            native_full_block_acceptance=False, full128_executed=False,
                            overall_pass=False).items():
        require(type(summary.get(key)) is type(wanted) and summary[key] == wanted,
                'invalid original build proof: ' + key)
    transfer = summary['build_transfer']
    for key, wanted in dict(schema=1, source_commit=PRODUCTION_COMMIT,
                            status='BUILT_HOST_ATTENTION_BLOCK_NOT_NUMERICAL_PASS',
                            scope='QWEN35_LAYER3_ATTENTION_BLOCK_M1', numerical_pass=False).items():
        require(type(transfer.get(key)) is type(wanted) and transfer[key] == wanted,
                'invalid build transfer: ' + key)
    trusted = {key: sha256(transfer.get(key)) for key in BUILD_KEYS}
    for key in BUILD_KEYS:
        require(hashes.get(key) == trusted[key], 'build hash/transfer mismatch: ' + key)
    sources = hashes.get('source_sha256')
    require(type(sources) is dict and sources, 'missing build source closure')
    require(BUILD_COMPACT_WRAPPERS <= sources.keys(), 'missing original build compact wrappers')
    manifest = {name: value for name, value in sources.items() if name not in BUILD_COMPACT_WRAPPERS}
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    require(digest(manifest_bytes) == trusted['source_manifest_sha256'],
            'original sealed build source manifest digest mismatch')
    for role in ('pass', 'fault'):
        consumer = evidence[role]
        consumer_sources = consumer['source_input_hashes.json'].get('source_sha256')
        require(type(consumer_sources) is dict and
                consumer_sources.keys() - sources.keys() == CONSUMER_EXTRA_SOURCES and
                all(consumer_sources.get(name) == value for name, value in sources.items()),
                'build/consumer source closure mismatch: ' + role)
        require(consumer['summary.json'].get('build_transfer') == transfer and
                consumer['summary.json'].get('build') == summary['build'],
                'build/consumer immutable build mismatch: ' + role)
    require(evidence['pass']['source_input_hashes.json']['source_sha256'] ==
            evidence['fault']['source_input_hashes.json']['source_sha256'],
            'pass/fault complete source closure mismatch')
    return trusted


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], timeout=60).decode().strip()


def checker_identity(checker_root, production_root):
    require(checker_root != production_root and checker_root not in production_root.parents and
            production_root not in checker_root.parents, 'independent sibling checkouts required')
    commit = git(checker_root, 'rev-parse', 'HEAD')
    require(re.fullmatch('[0-9a-f]{40}', commit), 'invalid checker commit')
    require(not os.environ.get('GITHUB_SHA') or os.environ['GITHUB_SHA'] == commit,
            'checker checkout differs from actual GITHUB_SHA')
    require(git(production_root, 'rev-parse', 'HEAD') == PRODUCTION_COMMIT,
            'production checkout differs from frozen commit')
    require(not git(production_root, 'status', '--porcelain', '--untracked-files=normal'),
            'production checkout must be clean')
    files = {}
    for name in (CHECKER_PATH, 'tools/attention_acceptance/run_readonly.py',
                 '.github/workflows/attention-block-readonly-acceptance.yml'):
        raw = (checker_root / name).read_bytes()
        committed = subprocess.check_output(['git', '-C', str(checker_root), 'show', commit + ':' + name], timeout=60)
        require(raw == committed, 'checker source drift: ' + name)
        files[name] = digest(raw)
    return {'commit': commit, 'source_sha256': files}


def collect(client, output, provenance):
    base = f'/repos/{REPOSITORY}/actions/runs/{RUN_ID}'
    run = client.json(base + f'/attempts/{ATTEMPT}')
    verify_run(run)
    page = client.json(base + f'/attempts/{ATTEMPT}/jobs?per_page=100')
    require(page.get('total_count') == len(page.get('jobs', [])), 'incomplete original job page')
    jobs = verify_jobs(page['jobs'])
    provenance.update(original_run=run, original_jobs=jobs)
    if any(job['status'] != 'completed' for job in jobs.values()):
        return None
    page = client.json(base + '/artifacts?per_page=100')
    require(page.get('total_count') == len(page.get('artifacts', [])), 'incomplete artifact page')
    evidence, artifacts = {}, {}
    provenance['artifacts'] = artifacts
    for role in JOB_IDS:
        artifact = select_artifact(page['artifacts'], role, jobs[role])
        evidence[role], pins = admit_archive(client.archive(artifact['id']), artifact, output / role)
        artifacts[role] = {'github_metadata': artifact, 'archive_digest_verified': True,
                           'member_digests': pins, 'original_job_id': jobs[role]['id']}
    return evidence


def checker_command(checker_root, production_root, output, trusted, provenance):
    args = [sys.executable, '-B', str(checker_root / CHECKER_PATH), '--repo', str(production_root),
            '--pass-compact', str(output / 'pass'), '--fault-compact', str(output / 'fault'),
            '--expected-commit', PRODUCTION_COMMIT, '--output', str(output / 'acceptance.json')]
    for key in BUILD_KEYS:
        args += ['--expected-' + key.replace('_', '-'), trusted[key]]
    for role in ('pass', 'fault'):
        for label, member in zip(('summary', 'hashes'), MEMBERS):
            args += [f'--expected-{role}-{label}-sha256',
                     provenance['artifacts'][role]['member_digests'][member]['sha256']]
    return args


def log_receipt(provenance):
    """Small durable log fallback if GitHub refuses the proof artifact upload."""
    fields = ('schema', 'status', 'acceptance', 'production_commit', 'original_run_id',
              'original_run_attempt', 'recovery_run_id', 'recovery_run_attempt', 'checker',
              'trusted_build', 'source_closure_counts', 'acceptance_report_sha256',
              'cache_full_prefix_bytes_independently_verified', 'error', 'reason')
    receipt = {key: provenance[key] for key in fields if key in provenance}
    receipt['original_jobs'] = {role: {key: job.get(key) for key in
        ('id', 'name', 'run_attempt', 'head_sha', 'status', 'conclusion')}
        for role, job in provenance.get('original_jobs', {}).items()}
    receipt['artifacts'] = {role: dict(
        id=record['github_metadata']['id'], name=record['github_metadata']['name'],
        github_archive_sha256=record['github_metadata']['digest'],
        archive_digest_verified=record['archive_digest_verified'],
        member_digests=record['member_digests'])
        for role, record in provenance.get('artifacts', {}).items()}
    receipt['scope'] = ('Original compact CI attestations only. Full-cache preservation remains '
        'live-attested; cache prefix bytes are not independently rehashed here. '
        'No new numerical execution, native full-block, M128, timing, or QoR acceptance.')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checker-repo', type=Path, required=True)
    parser.add_argument('--production-repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    checker_root, production_root, output = (value.resolve() for value in
                                            (args.checker_repo, args.production_repo, args.output))
    require(not output.exists(), 'new recovery output directory required')
    require(output != production_root and production_root not in output.parents,
            'recovery evidence cannot dirty the frozen production checkout')
    output.mkdir(parents=True)
    provenance = dict(schema=1, status=FAIL, production_commit=PRODUCTION_COMMIT,
        original_run_id=RUN_ID, original_run_attempt=ATTEMPT,
        recovery_run_id=os.environ.get('GITHUB_RUN_ID'), recovery_run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
        observed_at=datetime.now(timezone.utc).isoformat(), acceptance=False,
        trust_origin='GitHub API artifact.digest over ZIP; member digests derived only after verification',
        numerical_execution_performed=False, build_performed=False, live_authority_reissued=False,
        source_rebinding=False, downloaded_payloads=False,
        cache_full_prefix_bytes_independently_verified=False)
    code = 1
    try:
        provenance['checker'] = checker_identity(checker_root, production_root)
        evidence = collect(GitHub(os.environ.get('GITHUB_TOKEN')), output, provenance)
        if evidence is None:
            provenance.update(status=PENDING, reason='Original build/pass/fault jobs are not all terminal success.')
            code = 75
        else:
            trusted = trusted_build(evidence)
            provenance['trusted_build'] = trusted
            provenance['sealed_build_source_manifest_reconstructed'] = True
            provenance['source_closure_counts'] = {role: len(value['source_input_hashes.json']['source_sha256'])
                                                    for role, value in evidence.items()}
            write_json(output / 'authenticated_input_provenance.json', provenance)
            command = checker_command(checker_root, production_root, output, trusted, provenance)
            # Preserve GITHUB_SHA: it names the checker commit, not the frozen DUT.
            result = subprocess.run(command, cwd=checker_root, timeout=360,
                                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            require(result.returncode == 0, 'updated aggregate checker rejected original evidence')
            report = decode((output / 'acceptance.json').read_bytes())
            require(report.get('status') == PASS and report.get('split_case_acceptance') is True,
                    'aggregate checker did not issue the bounded split-case acceptance')
            provenance.update(status=PASS, acceptance=True,
                              acceptance_report_sha256=digest((output / 'acceptance.json').read_bytes()))
            code = 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        provenance['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        write_json(output / 'provenance.json', provenance)
        print(provenance['status'])
        # The original workflow logs retain this bounded receipt even if the
        # later upload-artifact step hits account quota. Never print full input
        # summaries or the duplicated multi-megabyte consumer evidence.
        print('ATTENTION_READONLY_PROVENANCE ' + json.dumps(log_receipt(provenance),
                                                           sort_keys=True, separators=(',', ':')))
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
                stream.write(provenance['status'] + '\n\n')
                stream.write(f'Original run {RUN_ID}, attempt {ATTEMPT}, production commit {PRODUCTION_COMMIT}.\n\n')
                stream.write('Read-only admission of the original independent same-DUT cold0/carried1 cases. '
                             'No build, capture, ELF execution, weights, or NPZ downloads. '
                             'Native full-block, M128, timing, and QoR remain open.\n')
                if code == 75:
                    stream.write('\nPENDING is not acceptance. The exact original workflow completion triggers a new check.\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
