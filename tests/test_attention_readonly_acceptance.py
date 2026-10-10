"""Offline trust-boundary controls only: no capture, compiler, model or DUT."""
from copy import deepcopy
from contextlib import nullcontext
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import zipfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('attention_readonly',
    ROOT / 'tools/attention_acceptance/run_readonly.py')
route = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(route)


def run_record():
    return dict(id=route.RUN_ID, run_attempt=route.ATTEMPT,
        head_sha=route.PRODUCTION_COMMIT, head_branch='main', name=route.WORKFLOW_NAME,
        path=route.WORKFLOW_PATH, event='push', status='completed', conclusion='failure',
        repository=dict(id=route.REPOSITORY_ID, full_name=route.REPOSITORY),
        head_repository=dict(id=route.REPOSITORY_ID, full_name=route.REPOSITORY))


def job_records():
    return [dict(id=job_id, name=role, run_id=route.RUN_ID, run_attempt=route.ATTEMPT,
                 head_sha=route.PRODUCTION_COMMIT, status='completed', conclusion='success',
                 started_at='2026-10-10T02:00:00Z', completed_at='2026-10-10T06:00:00Z')
            for role, job_id in route.JOB_IDS.items()]


def make_zip(rows=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in rows or [(name, b'{"sealed":true}\n') for name in route.MEMBERS]:
            archive.writestr(name, raw)
    return stream.getvalue()


def artifact_record(role, raw):
    return dict(id=route.KNOWN_ARTIFACT_IDS.get(role, 11660000000),
        name=f'host-attention-block-{role}-proof-{route.PRODUCTION_COMMIT}-1',
        expired=False, digest='sha256:' + route.digest(raw), size_in_bytes=len(raw),
        created_at='2026-10-10T04:00:00Z', workflow_run=dict(id=route.RUN_ID,
            head_sha=route.PRODUCTION_COMMIT, head_branch='main',
            repository_id=route.REPOSITORY_ID, head_repository_id=route.REPOSITORY_ID))


def build_evidence():
    transfer = dict(schema=1, source_commit=route.PRODUCTION_COMMIT,
        status='BUILT_HOST_ATTENTION_BLOCK_NOT_NUMERICAL_PASS',
        scope='QWEN35_LAYER3_ATTENTION_BLOCK_M1', numerical_pass=False,
        **{key: hashlib.sha256(key.encode()).hexdigest() for key in route.BUILD_KEYS})
    manifest = {'source.py': 'a' * 64}
    transfer['source_manifest_sha256'] = route.digest((json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode())
    ready = dict(binary_sha256=transfer['binary_sha256'])
    summary = dict(status='PASS_HOST_ATTENTION_BLOCK_BUILD_ONLY', stage='complete',
        git_head=route.PRODUCTION_COMMIT, source_immutability_verified=True,
        numerical_acceptance=False, frozen_recipe_block_acceptance=False,
        native_full_block_acceptance=False, full128_executed=False, overall_pass=False,
        build_transfer=transfer, build=ready)
    hashes = {key: transfer[key] for key in route.BUILD_KEYS}
    hashes['source_sha256'] = {**manifest, **{name: 'a' * 64 for name in route.BUILD_COMPACT_WRAPPERS}}
    evidence = {role: {'summary.json': deepcopy(summary), 'source_input_hashes.json': deepcopy(hashes)}
                for role in route.JOB_IDS}
    for role in ('pass', 'fault'):
        evidence[role]['source_input_hashes.json']['source_sha256'].update(
            {name: 'b' * 64 for name in route.CONSUMER_EXTRA_SOURCES})
    return evidence


def test_original_aggregate_failure_does_not_erase_successful_producer_jobs():
    route.verify_run(run_record())
    assert set(route.verify_jobs(job_records())) == set(route.JOB_IDS)


@pytest.mark.parametrize('key,value', [('id', 123), ('run_attempt', 2), ('head_sha', 'a'*40),
    ('head_branch', 'candidate'), ('path', 'other.yml'), ('name', 'other'), ('event', 'pull_request')])
def test_wrong_original_run_is_rejected(key, value):
    run = run_record()
    run[key] = value
    with pytest.raises(ValueError, match='run identity'):
        route.verify_run(run)


def test_fork_run_is_rejected():
    run = run_record()
    run['head_repository']['id'] += 1
    with pytest.raises(ValueError, match='repository'):
        route.verify_run(run)


@pytest.mark.parametrize('key,value', [('id', 123), ('run_attempt', 2), ('head_sha', 'a'*40),
    ('name', 'fault-copy'), ('run_id', 123), ('conclusion', 'failure'), ('status', 'mystery')])
def test_wrong_or_failed_job_is_rejected(key, value):
    jobs = job_records()
    jobs[-1][key] = value
    with pytest.raises(ValueError):
        route.verify_jobs(jobs)


def test_duplicate_job_is_rejected():
    jobs = job_records()
    jobs.append(deepcopy(jobs[0]))
    with pytest.raises(ValueError, match='duplicate'):
        route.verify_jobs(jobs)


def test_pending_does_not_download_or_accept_artifacts(tmp_path):
    class Client:
        def json(self, path):
            if path.endswith('/attempts/1'):
                return run_record()
            assert path.endswith('/attempts/1/jobs?per_page=100')
            jobs = job_records()
            jobs[-1].update(status='in_progress', conclusion=None, completed_at=None)
            return dict(total_count=len(jobs), jobs=jobs)

        def archive(self, artifact_id):
            pytest.fail('pending must not download artifacts')

    provenance = {'acceptance': False}
    assert route.collect(Client(), tmp_path, provenance) is None
    assert provenance['acceptance'] is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('key,value', [('id', 123), ('expired', True), ('digest', None),
    ('size_in_bytes', route.MAX_ZIP_BYTES + 1), ('created_at', '2026-10-10T01:00:00Z')])
def test_wrong_artifact_metadata_is_rejected(key, value):
    artifact = artifact_record('build', make_zip())
    artifact[key] = value
    with pytest.raises(ValueError):
        route.select_artifact([artifact], 'build', job_records()[0])


def test_artifact_run_and_attempt_cannot_be_swapped():
    artifact = artifact_record('fault', make_zip())
    artifact['workflow_run']['head_sha'] = 'b' * 40
    with pytest.raises(ValueError, match='source run'):
        route.select_artifact([artifact], 'fault', job_records()[-1])
    artifact = artifact_record('fault', make_zip())
    artifact['name'] = artifact['name'][:-1] + '2'
    with pytest.raises(ValueError, match='missing'):
        route.select_artifact([artifact], 'fault', job_records()[-1])


def test_zip_digest_is_checked_before_parsing_or_writing(tmp_path):
    raw = make_zip()
    artifact = artifact_record('build', raw)
    corrupted = b'x' * len(raw)
    with pytest.raises(ValueError, match='ZIP digest'):
        route.admit_archive(corrupted, artifact, tmp_path / 'build')
    assert list(tmp_path.iterdir()) == []


def test_authenticated_zip_yields_exact_compact_member_pins(tmp_path):
    raw = make_zip()
    artifact = artifact_record('build', raw)
    values, pins = route.admit_archive(raw, artifact, tmp_path / 'build')
    assert set(values) == set(route.MEMBERS)
    for name in route.MEMBERS:
        data = (tmp_path / 'build' / name).read_bytes()
        assert pins[name] == {'sha256': route.digest(data), 'bytes': len(data)}


@pytest.mark.parametrize('rows', [
    [('summary.json', b'{}')],
    [('summary.json', b'{}'), ('summary.json', b'{}')],
    [('summary.json', b'{}'), ('../source_input_hashes.json', b'{}')],
    [('summary.json', b'{}'), ('source_input_hashes.json', b'{}'), ('weights.npz', b'raw')],
    [('summary.json', b'{"a":1,"a":2}'), ('source_input_hashes.json', b'{}')],
    [('summary.json', b'{"value":NaN}'), ('source_input_hashes.json', b'{}')],
])
def test_unsafe_zip_members_and_json_rejected(tmp_path, rows):
    with pytest.warns(UserWarning) if len(rows) > 1 and rows[0][0] == rows[-1][0] else nullcontext():
        raw = make_zip(rows)
    with pytest.raises(ValueError):
        route.admit_archive(raw, artifact_record('build', raw), tmp_path / 'build')
    assert list(tmp_path.iterdir()) == []


def test_zip_symlink_rejected(tmp_path):
    link = zipfile.ZipInfo('summary.json')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    raw = make_zip([(link, b'{}'), ('source_input_hashes.json', b'{}')])
    with pytest.raises(ValueError, match='member'):
        route.admit_archive(raw, artifact_record('build', raw), tmp_path / 'build')


def test_build_receipt_preserves_original_package_elf_sv_and_source_pins():
    evidence = build_evidence()
    trusted = route.trusted_build(evidence)
    assert trusted == {key: evidence['build']['summary.json']['build_transfer'][key]
                       for key in route.BUILD_KEYS}


@pytest.mark.parametrize('mutation', ['source', 'package', 'build', 'build_only', 'hashes',
                                    'extra_source', 'missing_reference', 'reference_drift', 'manifest'])
def test_build_or_source_rebinding_is_rejected(mutation):
    evidence = build_evidence()
    if mutation == 'source':
        evidence['fault']['source_input_hashes.json']['source_sha256']['source.py'] = 'b' * 64
    elif mutation == 'package':
        evidence['pass']['summary.json']['build_transfer']['package_sha256'] = 'b' * 64
    elif mutation == 'build':
        evidence['fault']['summary.json']['build']['binary_sha256'] = 'b' * 64
    elif mutation == 'build_only':
        evidence['build']['summary.json']['numerical_acceptance'] = True
    elif mutation == 'extra_source':
        evidence['pass']['source_input_hashes.json']['source_sha256']['arbitrary.py'] = 'b' * 64
    elif mutation == 'missing_reference':
        del evidence['pass']['source_input_hashes.json']['source_sha256'][next(iter(route.CONSUMER_EXTRA_SOURCES))]
    elif mutation == 'reference_drift':
        evidence['pass']['source_input_hashes.json']['source_sha256'][next(iter(route.CONSUMER_EXTRA_SOURCES))] = 'c' * 64
    elif mutation == 'manifest':
        for role in evidence:
            evidence[role]['source_input_hashes.json']['source_sha256']['source.py'] = 'd' * 64
    else:
        evidence['build']['source_input_hashes.json']['binary_sha256'] = 'b' * 64
    with pytest.raises(ValueError):
        route.trusted_build(evidence)


def test_collection_only_fetches_authenticated_original_compact_artifacts(tmp_path):
    evidence = build_evidence()
    archives = {role: make_zip([(name, json.dumps(evidence[role][name]).encode())
                              for name in route.MEMBERS]) for role in route.JOB_IDS}
    artifacts = [artifact_record(role, raw) for role, raw in archives.items()]
    calls = []

    class Client:
        def json(self, path):
            calls.append(path)
            if path.endswith('/attempts/1'):
                return run_record()
            if '/jobs?' in path:
                return dict(total_count=3, jobs=job_records())
            assert path.endswith('/artifacts?per_page=100')
            return dict(total_count=3, artifacts=artifacts)

        def archive(self, artifact_id):
            calls.append(artifact_id)
            role = next(row['name'].split('-')[3] for row in artifacts if row['id'] == artifact_id)
            return archives[role]

    provenance = {}
    result = route.collect(Client(), tmp_path, provenance)
    assert result == evidence
    assert len([call for call in calls if isinstance(call, int)]) == 3
    assert all(row['archive_digest_verified'] for row in provenance['artifacts'].values())
    assert all(set(row['member_digests']) == set(route.MEMBERS)
               for row in provenance['artifacts'].values())


def test_checker_command_keeps_frozen_source_and_current_checker_separate(tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_SHA', 'c' * 40)
    pins = {role: {'member_digests': {name: {'sha256': 'd' * 64} for name in route.MEMBERS}}
            for role in ('pass', 'fault')}
    command = route.checker_command(tmp_path / 'checker', tmp_path / 'production', tmp_path / 'output',
        route.trusted_build(build_evidence()), {'artifacts': pins})
    assert command[2] == str(tmp_path / 'checker' / route.CHECKER_PATH)
    assert command[command.index('--repo') + 1] == str(tmp_path / 'production')
    assert command[command.index('--expected-commit') + 1] == route.PRODUCTION_COMMIT
    assert os.environ['GITHUB_SHA'] == 'c' * 40
    assert '--expected-pass-summary-sha256' in command
    assert '--expected-fault-hashes-sha256' in command


def test_main_pending_writes_no_acceptance_and_never_calls_checker(tmp_path, monkeypatch):
    monkeypatch.setattr(route, 'checker_identity', lambda *_: {'commit': 'c' * 40})
    monkeypatch.setattr(route, 'GitHub', lambda _: object())
    monkeypatch.setattr(route, 'collect', lambda *_: None)
    monkeypatch.setattr(route.subprocess, 'run', lambda *_args, **_kwargs: pytest.fail('checker called'))
    output = tmp_path / 'evidence'
    code = route.main(['--checker-repo', str(tmp_path / 'checker'), '--production-repo',
                       str(tmp_path / 'production'), '--output', str(output)])
    report = json.loads((output / 'provenance.json').read_text())
    assert code == 75 and report['status'] == route.PENDING and report['acceptance'] is False
    assert not (output / 'acceptance.json').exists()


def test_main_checker_failure_is_retained_without_acceptance(tmp_path, monkeypatch):
    monkeypatch.setattr(route, 'checker_identity', lambda *_: {'commit': 'c' * 40})
    monkeypatch.setattr(route, 'GitHub', lambda _: object())
    monkeypatch.setattr(route, 'collect', lambda *_: build_evidence())
    monkeypatch.setattr(route, 'checker_command', lambda *_: ['unexecuted-test-checker'])
    monkeypatch.setattr(route.subprocess, 'run', lambda *_args, **_kwargs:
                        subprocess.CompletedProcess(['unexecuted-test-checker'], 1))
    output = tmp_path / 'evidence'
    code = route.main(['--checker-repo', str(tmp_path / 'checker'), '--production-repo',
                       str(tmp_path / 'production'), '--output', str(output)])
    report = json.loads((output / 'provenance.json').read_text())
    assert code == 1 and report['status'] == route.FAIL and report['acceptance'] is False
    assert 'checker rejected' in report['error']['message']
    assert (output / 'authenticated_input_provenance.json').exists()


def test_main_pass_requires_checker_pass_and_records_checker_identity(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('GITHUB_SHA', 'c' * 40)
    monkeypatch.setattr(route, 'checker_identity', lambda *_: {'commit': 'c' * 40})
    monkeypatch.setattr(route, 'GitHub', lambda _: object())
    monkeypatch.setattr(route, 'collect', lambda *_: build_evidence())
    monkeypatch.setattr(route, 'checker_command', lambda *_: ['unexecuted-test-checker'])
    output = tmp_path / 'evidence'

    def checker(_command, **options):
        assert options['env']['GITHUB_SHA'] == 'c' * 40
        route.write_json(output / 'acceptance.json', {'status': route.PASS, 'split_case_acceptance': True})
        return subprocess.CompletedProcess(_command, 0)

    monkeypatch.setattr(route.subprocess, 'run', checker)
    code = route.main(['--checker-repo', str(tmp_path / 'checker'), '--production-repo',
                       str(tmp_path / 'production'), '--output', str(output)])
    report = json.loads((output / 'provenance.json').read_text())
    assert code == 0 and report['status'] == route.PASS and report['acceptance'] is True
    assert report['production_commit'] == route.PRODUCTION_COMMIT
    assert report['checker']['commit'] == 'c' * 40
    assert report['acceptance_report_sha256'] == route.digest((output / 'acceptance.json').read_bytes())
    assert report['numerical_execution_performed'] is False
    logged = capsys.readouterr().out.split('ATTENTION_READONLY_PROVENANCE ', 1)[1]
    fallback = json.loads(logged)
    assert fallback['status'] == route.PASS and fallback['acceptance'] is True
    assert fallback['checker']['commit'] == 'c' * 40
    assert fallback['production_commit'] == route.PRODUCTION_COMMIT
    assert fallback['acceptance_report_sha256'] == report['acceptance_report_sha256']
    assert fallback['cache_full_prefix_bytes_independently_verified'] is False
    assert 'consumer_evidence' not in fallback
    assert len(logged) < 8192


def test_log_fallback_retains_archive_and_member_provenance_without_full_json():
    raw = make_zip()
    metadata = artifact_record('build', raw)
    members = {name: {'sha256': 'a' * 64, 'bytes': 100} for name in route.MEMBERS}
    fallback = route.log_receipt({'status': route.PENDING, 'acceptance': False,
        'original_jobs': {'build': job_records()[0]}, 'artifacts': {'build': {
            'github_metadata': metadata, 'archive_digest_verified': True, 'member_digests': members}},
        'consumer_evidence': {'must_not_appear': 'large payload'}})
    assert fallback['artifacts']['build']['github_archive_sha256'] == metadata['digest']
    assert fallback['artifacts']['build']['member_digests'] == members
    assert fallback['original_jobs']['build']['id'] == route.JOB_IDS['build']
    assert 'consumer_evidence' not in fallback


def test_workflow_is_one_bounded_read_only_job_with_exact_completed_run_filter():
    workflow = yaml.safe_load((ROOT / '.github/workflows/attention-block-readonly-acceptance.yml').read_text())
    trigger = workflow.get('on', workflow.get(True))
    assert set(trigger) == {'push', 'workflow_run'}
    assert trigger['workflow_run'] == {'workflows': [route.WORKFLOW_NAME], 'types': ['completed']}
    assert workflow['permissions'] == {'contents': 'read', 'actions': 'read'}
    assert list(workflow['jobs']) == ['acceptance']
    job = workflow['jobs']['acceptance']
    assert job['timeout-minutes'] <= 15
    assert str(route.RUN_ID) in job['if'] and route.PRODUCTION_COMMIT in job['if']
    assert route.WORKFLOW_PATH in job['if'] and 'run_attempt == 1' in job['if']
    checkouts = [step['with'] for step in job['steps'] if step.get('uses') == 'actions/checkout@v4']
    assert checkouts == [dict(ref='${{ github.sha }}', path='checker', **{'persist-credentials': False}),
                         dict(ref=route.PRODUCTION_COMMIT, path='production', **{'persist-credentials': False})]
    commands = '\n'.join(step.get('run', '') for step in job['steps'])
    for forbidden in ('sbt ', 'verilator ', 'collect_qwen35', '--build-only', 'gh workflow',
                      'gh run rerun', 'torch', 'huggingface', 'safetensors'):
        assert forbidden not in commands
    assert 'run_readonly.py' in commands
    assert '--production-repo production' in commands
    artifact = next(step for step in job['steps'] if step.get('uses') == 'actions/upload-artifact@v4')
    assert artifact['if'] == 'always()'
    assert all(name.endswith('.json') for name in artifact['with']['path'].splitlines())
