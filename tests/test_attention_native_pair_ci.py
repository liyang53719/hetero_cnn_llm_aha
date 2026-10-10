"""Source-only CI contracts and synthetic identity/files; no network/model/EDA."""
from pathlib import Path
import ast
import copy
import json
import os
import shlex
import subprocess
import sys
import zipfile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/attention-native-m1-pair.yml'
VALUE = yaml.safe_load(WORKFLOW.read_text())
JOB = VALUE['jobs']['native-m1-pair']
STEPS = JOB['steps']
PIN = '98c7d80f65c5f05b55726c5239a6e9ec15d1b53f'
ARCHIVE_SHA = '1cfaf045ca58704016bfecff3f079b7fa708d1d7f7043b0fb014b5da61b7bfb1'
EVIDENCE = {
    'compact/summary.json': 8 * 1024 * 1024,
    'compact/source_input_hashes.json': 8 * 1024 * 1024,
    'official_m1_preflight.json': 2 * 1024 * 1024,
    'official_m1_actual.json': 2 * 1024 * 1024,
    'input_replay.zip': 16 * 1024,
    'replay_pack.zip': 256 * 1024,
    'pack_summary.json': 64 * 1024,
    'diagnostic_tail.txt': 12 * 1024,
}


def step(name):
    return next(value for value in STEPS if value.get('id') == name or value.get('name') == name)


def index(name):
    return STEPS.index(step(name))


def test_exact_trigger_scope_excludes_helper_only_edits():
    trigger = VALUE.get('on', VALUE.get(True))  # PyYAML's YAML 1.1 spelling.
    assert set(trigger) == {'push', 'workflow_dispatch'}
    assert trigger['push']['branches'] == ['main']
    assert set(trigger['push']['paths']) == {
        '.github/workflows/attention-native-m1-pair.yml',
        'tools/attention_native/run_native_pair.py',
        'tests/test_attention_native_pair.py',
        'tests/test_attention_native_pair_ci.py',
    }
    assert VALUE['permissions'] == {'contents': 'read', 'actions': 'read'}
    assert VALUE['concurrency']['cancel-in-progress'] is False


def test_one_bounded_numerical_job_and_one_wrapper_invocation():
    assert set(VALUE['jobs']) == {'native-m1-pair'}
    assert JOB['runs-on'] == 'ubuntu-24.04'
    assert JOB['timeout-minutes'] == 220
    assert 'strategy' not in JOB
    runs = [item['run'] for item in STEPS if 'run' in item]
    assert sum('run_native_pair.py' in text for text in runs) == 1
    for text in runs:
        assert '--threads 2' not in text and '--mode fault' not in text
        assert '--build-only' not in text and 'build_candidate(' not in text
        assert 'scala.tools.nsc.Main' not in text and 'sbt -batch' not in text
        assert 'run_host_bf16_attention_block_fresh_gate.py' not in text


def test_frozen_root_and_independent_trigger_checkout():
    checkouts = [item['with'] for item in STEPS if item.get('uses') == 'actions/checkout@v4']
    assert checkouts == [
        {'ref': PIN, 'persist-credentials': False},
        {'ref': '${{ github.sha }}', 'path': 'work/attention_native_tools', 'persist-credentials': False},
    ]
    assert JOB['env']['SOURCE_SHA'] == PIN
    assert JOB['env']['BASELINE_RUN_ID'] == '38015586840'
    assert JOB['env']['BASELINE_ARCHIVE_SHA256'] == ARCHIVE_SHA
    assert JOB['env']['PYTHONDONTWRITEBYTECODE'] == '1'
    assert JOB['env']['OPENBLAS_NUM_THREADS'] == JOB['env']['OMP_NUM_THREADS'] == '2'


def test_only_original_producer_artifact_downloaded():
    downloads = [item for item in STEPS if item.get('uses') == 'actions/download-artifact@v4']
    assert len(downloads) == 1
    assert downloads[0]['with'] == {
        'name': 'host-attention-block-build-' + PIN + '-38015586840-1',
        'run-id': 38015586840,
        'github-token': '${{ github.token }}',
        'path': 'work/attention_native_download',
    }


def test_light_source_tests_precede_every_heavy_phase():
    tests = step('Test native replay boundaries before any heavy phase')
    assert tests['working-directory'] == 'work/attention_native_tools'
    assert tests['env']['PYTHONPATH'] == 'src:chisel/continuous_prefill/scripts'
    commands = [shlex.split(line) for line in tests['run'].splitlines() if '-m pytest' in line]
    assert len(commands) == 2 and '-O' not in commands[0] and '-O' in commands[1]
    expected = {'tests/test_attention_native_pair.py', 'tests/test_attention_native_pair_ci.py',
                'tests/test_attention_native_m1.py', 'tests/test_attention_native_replay_pack.py'}
    assert all(set(word for word in command if word.startswith('tests/')) == expected for command in commands)
    assert 'scripts/check_git_payloads.py' in tests['run']
    for name in ('Prepare identical original tools and pinned public sources',
                 'Install fixed official producer runtime',
                 'Download only the existing original producer archive',
                 'Reacquire pinned public model payloads locally', 'execute'):
        assert index(tests['name']) < index(name)


def test_original_tool_and_runtime_versions_are_reused():
    prior = yaml.safe_load((ROOT / '.github/workflows/attention-threads-diagnostic.yml').read_text())
    previous = prior['jobs']['same-rtl-prefix-comparison']['steps']
    old_runtime = next(item['run'] for item in previous if item.get('name') == 'Install fixed official producer runtime')
    runtime = step('Install fixed official producer runtime')['run']
    assert runtime.removeprefix('set -euo pipefail\n') == old_runtime
    tools = step('Prepare identical original tools and pinned public sources')['run']
    assert 'prepare_host_ci_tools.sh "$GITHUB_WORKSPACE/work/attention_block_ci_tools"' in tools
    assert 'prepare_pinned_idma_sources.py --output work/attention_block_ci_idma' in tools
    assert 'IDMA_EXPORT=$GITHUB_WORKSPACE/work/attention_block_ci_idma/idma_export' in tools
    assert 'uv==0.12.19' in tools
    assert next(item for item in STEPS if item.get('uses') == 'actions/setup-java@v4')['with'] == {
        'distribution': 'temurin', 'java-version': '17'}


def test_numeric_job_provenance_and_exact_wrapper_cli():
    execute = step('execute')
    assert execute['env'] == {
        'HF_HUB_OFFLINE': '1',
        'OFFLINE_TOOLS': '${{ github.workspace }}/work/attention_block_ci_runtime',
        'CURRENT_JOB_ID': '${{ steps.identity.outputs.job_id }}',
        'CURRENT_JOB_STARTED_AT': '${{ steps.identity.outputs.job_started_at }}',
    }
    argv = shlex.split(execute['run'].replace('\\\n', ''))
    assert argv[:3] == ['python', '-B', '$GITHUB_WORKSPACE/work/attention_native_tools/tools/attention_native/run_native_pair.py']
    assert dict(zip(argv[3::2], argv[4::2], strict=True)) == {
        '--source-root': '$GITHUB_WORKSPACE',
        '--output': '$GITHUB_WORKSPACE/work/attention_native_result',
        '--archive': '$GITHUB_WORKSPACE/work/attention_native_download/host_attention_block_build.tar.gz',
        '--expected-sha256': '$BASELINE_ARCHIVE_SHA256', '--expected-commit': '$SOURCE_SHA',
        '--baseline-run-id': '$BASELINE_RUN_ID',
        '--payload-layer0': '$GITHUB_WORKSPACE/work/qwen35_layer0_payload',
        '--payload-layer3': '$GITHUB_WORKSPACE/work/qwen35_layer3_payload',
        '--payload-extra': '$GITHUB_WORKSPACE/work/qwen35_prefix_payload',
        '--run-id': '$GITHUB_RUN_ID', '--job-id': '$CURRENT_JOB_ID',
        '--job-started-at': '$CURRENT_JOB_STARTED_AT',
    }
    assert 'GITHUB_JOB' not in execute['run']
    assert index('identity') < index('execute')


def identity_fixture():
    return dict(run=dict(id=12345678901, run_attempt=2, head_sha='a' * 40,
                        path='.github/workflows/attention-native-m1-pair.yml'),
                jobs=[dict(id=98765432101, name=JOB['name'], run_id=12345678901,
                           head_sha='a' * 40, status='in_progress', runner_name='runner-1',
                           started_at='2026-01-01T00:00:00Z')])


def resolve_identity(data):
    script = step('identity')['with']['script']
    harness = r'''
    const fs = require('fs');
    const data = JSON.parse(fs.readFileSync(0, 'utf8'));
    const calls = [], outputs = {};
    const context = {repo: {owner: 'owner', repo: 'repo'}, runId: 12345678901, sha: 'a'.repeat(40)};
    const github = {rest: {actions: {
      getWorkflowRunAttempt: async args => {calls.push(['run', args]); return {data: data.run};},
      listJobsForWorkflowRunAttempt: 'current-attempt-jobs'
    }}, paginate: async (method, args) => {
      if (method !== 'current-attempt-jobs') throw new Error('Unexpected API');
      calls.push(['jobs', args]); return data.jobs;
    }};
    const core = {setOutput: (key, value) => {outputs[key] = value;}};
    const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
    new AsyncFunction('github', 'context', 'core', data.script)(github, context, core)
      .then(() => console.log(JSON.stringify({outputs, calls})))
      .catch(error => {console.error(error.message); process.exitCode = 1;});
    '''
    env = dict(os.environ, GITHUB_RUN_ID='12345678901', GITHUB_RUN_ATTEMPT='2',
               RUNNER_NAME='runner-1', EXPECTED_JOB_NAME=JOB['name'], GITHUB_JOB='native-m1-pair')
    return subprocess.run(['node', '-e', harness], input=json.dumps(dict(data, script=script)),
                          text=True, capture_output=True, check=False, env=env, timeout=10)


def test_current_attempt_api_provides_numeric_job_and_original_start_time():
    result = resolve_identity(identity_fixture())
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['outputs'] == {'job_id': '98765432101', 'job_started_at': '2026-01-01T00:00:00Z'}
    for endpoint, request in data['calls']:
        assert request['run_id'] == 12345678901 and request['attempt_number'] == 2
        assert request['owner'] == 'owner' and request['repo'] == 'repo'
    assert [row[0] for row in data['calls']] == ['run', 'jobs']


@pytest.mark.parametrize('target,key,value', [
    ('run', 'id', 1), ('run', 'run_attempt', 1), ('run', 'head_sha', 'b' * 40),
    ('run', 'path', '.github/workflows/host-bf16-attention-block.yml'),
    ('job', 'id', 'native-m1-pair'), ('job', 'id', 0), ('job', 'id', 1.5),
    ('job', 'id', 9007199254740992), ('job', 'run_id', 1),
    ('job', 'name', 'Other job'), ('job', 'head_sha', 'b' * 40),
    ('job', 'runner_name', 'another-runner'), ('job', 'status', 'completed'),
    ('job', 'started_at', None), ('job', 'started_at', '2099-01-01T00:00:00Z'),
    ('job', 'started_at', '2026-01-01T00:00:00Z\njob_id=forged'),
])
def test_api_job_identity_fails_closed_on_mismatch(target, key, value):
    data = identity_fixture()
    (data['run'] if target == 'run' else data['jobs'][0])[key] = value
    assert resolve_identity(data).returncode != 0


@pytest.mark.parametrize('count', [0, 2])
def test_missing_or_ambiguous_current_job_is_rejected(count):
    data = identity_fixture()
    data['jobs'] = [copy.deepcopy(data['jobs'][0]) for _ in range(count)]
    assert resolve_identity(data).returncode != 0


def python_step(name, workspace, **extra):
    source = step(name)['run'].split("<<'PY'\n", 1)[1].removesuffix('PY\n')
    output = workspace / 'step_output.txt'
    env = dict(os.environ, GITHUB_WORKSPACE=str(workspace), GITHUB_OUTPUT=str(output), **extra)
    result = subprocess.run([sys.executable, '-B', '-c', source], capture_output=True,
                            text=True, check=False, env=env, timeout=10)
    return result, output


def test_canary_is_metadata_only_bounded_and_required_before_heavy_work(tmp_path):
    result, _ = python_step('Prepare metadata-only retention canary', tmp_path,
        GITHUB_RUN_ID='123', CURRENT_JOB_ID='456', GITHUB_RUN_ATTEMPT='2', GITHUB_SHA='a' * 40, SOURCE_SHA=PIN)
    assert result.returncode == 0, result.stderr
    raw = (tmp_path / 'work/attention_native_admission/retention_canary.json').read_bytes()
    assert len(raw) <= 2048
    assert json.loads(raw) == dict(schema='ATTENTION_NATIVE_RETENTION_CANARY_V1', run_id='123',
        job_id='456', run_attempt='2', trigger_source='a' * 40, production_source=PIN)
    upload = step('retention_canary')
    assert upload['with']['path'] == 'work/attention_native_admission/retention_canary.json'
    assert upload['with']['retention-days'] == 1 and upload['with']['if-no-files-found'] == 'error'
    assert not upload.get('continue-on-error', False)
    assert index('identity') < index('retention_canary') < index('Prepare identical original tools and pinned public sources')
    assert index('retention_canary') < index('Reacquire pinned public model payloads locally') < index('execute')


def test_upload_exact_allowlist_and_quota_failure_is_not_green():
    upload = step('upload')
    paths = upload['with']['path'].splitlines()
    assert set(paths) == {'work/attention_native_result/' + name for name in EVIDENCE}
    assert len(paths) == len(EVIDENCE)
    assert upload['continue-on-error'] is True
    assert "steps.evidence.outcome == 'success'" in upload['if']
    assert "steps.evidence.outputs.file_count != '0'" in upload['if']
    assert index('evidence') < index('upload')
    uploads = [item for item in STEPS if item.get('uses') == 'actions/upload-artifact@v4']
    assert uploads == [step('retention_canary'), upload]
    failure = step('Fail closed when evidence retention fails')
    assert "steps.upload.outcome == 'failure'" in failure['if']
    assert "steps.evidence.outcome == 'failure'" in failure['if']
    assert "steps.retention_canary.outcome == 'failure'" in failure['if']
    assert "steps.upload.outputs.artifact-id == ''" in failure['if']
    assert 'RETENTION_FAILED' in failure['run'] and 'exit 1' in failure['run']
    assert index('upload') < index(failure['name'])


def test_workflow_and_runner_have_the_same_upload_limits():
    tree = ast.parse((ROOT / 'tools/attention_native/run_native_pair.py').read_text())
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and
                      any(isinstance(target, ast.Name) and target.id == 'UPLOAD_LIMITS' for target in node.targets))
    limits = eval(compile(ast.Expression(assignment.value), '<runner upload limits>', 'eval'), {'__builtins__': {}})
    assert limits == EVIDENCE


def test_guard_handles_partial_failure_without_uploading_other_files(tmp_path):
    root = tmp_path / 'work/attention_native_result'
    (root / 'compact').mkdir(parents=True)
    (root / 'compact/summary.json').write_text('{}')
    (root / 'never_upload.npz').write_bytes(b'private')
    result, output = python_step('evidence', tmp_path)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == 'file_count=1\ninput_replay_present=false\nreplay_pack_present=false\n'


def test_guard_accepts_absent_evidence_and_upload_step_skips_it(tmp_path):
    result, output = python_step('evidence', tmp_path)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == 'file_count=0\ninput_replay_present=false\nreplay_pack_present=false\n'


@pytest.mark.parametrize('name,limit', EVIDENCE.items())
def test_guard_rejects_oversized_file_before_upload(tmp_path, name, limit):
    path = tmp_path / 'work/attention_native_result' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as stream:
        stream.truncate(limit + 1)
    result, output = python_step('evidence', tmp_path)
    assert result.returncode != 0 and 'oversized evidence' in result.stderr
    assert not output.exists()


@pytest.mark.parametrize('kind', ['file_symlink', 'directory_symlink', 'directory', 'fifo'])
def test_guard_rejects_nonregular_and_symlink_evidence(tmp_path, kind):
    root = tmp_path / 'work/attention_native_result'
    root.mkdir(parents=True)
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (elsewhere / 'summary.json').write_text('{}')
    if kind == 'directory_symlink':
        (root / 'compact').symlink_to(elsewhere, target_is_directory=True)
    else:
        path = root / 'compact/summary.json'
        path.parent.mkdir()
        if kind == 'file_symlink':
            path.symlink_to(elsewhere / 'summary.json')
        elif kind == 'directory':
            path.mkdir()
        else:
            os.mkfifo(path)
    result, output = python_step('evidence', tmp_path)
    assert result.returncode != 0 and ('symlink evidence' in result.stderr or 'nonregular' in result.stderr)
    assert not output.exists()


def test_guard_rejects_compressed_oversized_internal_metadata(tmp_path):
    root = tmp_path / 'work/attention_native_result'
    root.mkdir(parents=True)
    path = root / 'replay_pack.zip'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('replay_manifest.json', b' ' * (64 * 1024 + 1))
    assert path.stat().st_size < 256 * 1024
    result, output = python_step('evidence', tmp_path)
    assert result.returncode != 0 and 'metadata exceeds' in result.stderr
    assert not output.exists()


def test_budget_and_acceptance_scope_are_explicit():
    plan = step('Record bounded runner plan')['run']
    assert '12,000 s' in plan and '13,200 s' in plan and '10,800 s' in plan
    assert '180 s upload reserve' in plan and '180 s failure reserve' in plan and '9,000 s' in plan
    assert 'cannot guarantee quota' in plan
    boundary = step('State the exact numerical evidence boundary')['run']
    assert 'Native full-block acceptance remains open' in boundary
    assert 'actual internal producer nodes are absent' in boundary
    assert 'Original native full-block producer failures and native counts remain visible' in boundary
    assert 'GitHub API JSON alone supplies no numerical authorization' in boundary
