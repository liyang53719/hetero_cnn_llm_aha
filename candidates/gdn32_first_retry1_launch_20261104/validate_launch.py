"""Read-only exact second-commit launch gate for the isolated GDN32 full model.

This gate establishes launch identity, not host, plan, budget or numerical
qualification. FULL_PLAN approval and cohort policy belong to launch_entry.py.
No network, native model work, external writes, or payload uploads occur here.
"""
import hashlib
import json
import os
import pathlib
import re
import subprocess

P = pathlib.Path
LAUNCH = 'ci_launch/gdn32_first_meaningful_p1_20261104_retry1.json'
NONCE = 'gdn32-first-meaningful-p1-20261104-retry1'
ROOT = 'candidates/gdn32_first_retry1_launch_20261104'
WORKFLOW = '.github/workflows/gdn32-first-meaningful-p1-retry1.yml'
GUARD = ROOT + '/validate_launch.py'
PLAN = ROOT + '/FULL_PLAN.json'
HARDWARE_GENERATION = '2b2f02d698f16a57ba696c52c4669a1226a68c5378efdc8ebe392cc1b9098f52'
MODEL_GENERATION = '31dc0fabfd5d06d40eccf7194902bee245b8c98e25488b8993b676cae1fd90d3'
SCHEMA = 'GDN32_FULL_MODEL_LAUNCH_V1'
IDENTITY_SCHEMA = 'GDN32_FULL_MODEL_JOB_IDENTITY_V1'
FIELDS = {'schema', 'source_sha', 'nonce', 'hardware_generation_sha256',
          'model_generation_sha256', 'workflow_sha256', 'guard_sha256',
          'plan_sha256', 'selected_profile', 'expected_cohort_sv_sha256'}
PIN_PATHS = {'workflow_sha256': WORKFLOW, 'guard_sha256': GUARD,
             'plan_sha256': PLAN}
PIN_CODES = {'workflow_sha256': 'WORKFLOW_PIN', 'guard_sha256': 'GUARD_PIN',
             'plan_sha256': 'PLAN_PIN'}
REFUSAL_CODES = frozenset({
    'ATTEMPT', 'SCHEMA', 'NONCE', 'HARDWARE_GENERATION', 'MODEL_GENERATION',
    'LAUNCH_FIELDS', 'SOURCE_PIN_FIELDS', 'WORKFLOW_PIN', 'GUARD_PIN', 'PLAN_PIN',
    'GIT_HASH', 'EVENT_SHAPE', 'REF', 'EVENT_TYPE', 'FIRST_PARENT', 'HEAD',
    'ONLY_ADDED', 'SELECTED_PROFILE', 'COHORT_DIGEST', 'COMMITTED_BYTES',
    'LAUNCH_BLOB', 'NONCE_ALREADY_PRESENT', 'PLAN_SHAPE', 'RUN_ID', 'GUARD_PATH',
    'REGULAR_FILE', 'FILE_SIZE', 'EVENT_FILE', 'DUPLICATE_JSON_KEY',
    'NONFINITE_JSON', 'INVALID_JSON', 'INVALID_ENCODING', 'GIT_READ_FAILED',
    'MISSING_INPUT', 'MISSING_ENVIRONMENT', 'IDENTITY_EXISTS', 'FILE_ACCESS_FAILED',
    'FILE_IO_FAILED', 'INTERNAL_FAILURE', 'SOURCE_IDENTITY_UNFINALIZED',
})


class LaunchRefusal(ValueError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in REFUSAL_CODES else 'INTERNAL_FAILURE'
        super().__init__(self.code)


def safe_refusal(exc):
    """Finite public reason only; never echo exceptions, paths, data or tokens."""
    if isinstance(exc, LaunchRefusal):
        code = exc.code if type(exc.code) is str and exc.code in REFUSAL_CODES else 'INTERNAL_FAILURE'
    elif isinstance(exc, json.JSONDecodeError):
        code = 'INVALID_JSON'
    elif isinstance(exc, UnicodeError):
        code = 'INVALID_ENCODING'
    elif isinstance(exc, subprocess.CalledProcessError):
        code = 'GIT_READ_FAILED'
    elif isinstance(exc, FileExistsError):
        code = 'IDENTITY_EXISTS'
    elif isinstance(exc, FileNotFoundError):
        code = 'MISSING_INPUT'
    elif isinstance(exc, PermissionError):
        code = 'FILE_ACCESS_FAILED'
    elif isinstance(exc, KeyError):
        code = 'MISSING_ENVIRONMENT'
    elif isinstance(exc, OSError):
        code = 'FILE_IO_FAILED'
    else:
        code = 'INTERNAL_FAILURE'
    return dict(schema='GDN32_FULL_MODEL_LAUNCH_REFUSAL_V1', status='FAIL_LAUNCH', reason=code)


def need(value, code):
    if not value:
        raise LaunchRefusal(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def exact_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def read_json(raw):
    return json.loads(raw, object_pairs_hook=exact_object,
                      parse_constant=lambda _: need(False, 'NONFINITE_JSON'))


def is_sha(value, size=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(size) + '}', value) is not None


def checked_bytes(repo, relative, cap):
    root = P(repo).resolve()
    path = root / relative
    need(path.is_file() and all(not item.is_symlink() for item in (path, *path.parents)),
         'REGULAR_FILE')
    need(0 < path.stat().st_size <= cap, 'FILE_SIZE')
    raw = path.read_bytes()
    need(0 < len(raw) <= cap, 'FILE_SIZE')
    return raw


def git_read(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)


def validate(event, manifest, attempt, head, parent, diff, source_pins):
    need(attempt == '1', 'ATTEMPT')
    need(is_sha(MODEL_GENERATION), 'SOURCE_IDENTITY_UNFINALIZED')
    need(type(manifest) is dict and set(manifest) == FIELDS, 'LAUNCH_FIELDS')
    need(manifest['schema'] == SCHEMA, 'SCHEMA')
    need(manifest['nonce'] == NONCE, 'NONCE')
    need(manifest['hardware_generation_sha256'] == HARDWARE_GENERATION, 'HARDWARE_GENERATION')
    need(manifest['model_generation_sha256'] == MODEL_GENERATION, 'MODEL_GENERATION')
    need(type(source_pins) is dict and set(source_pins) == set(PIN_PATHS),
         'SOURCE_PIN_FIELDS')
    for key, actual in source_pins.items():
        need(is_sha(actual) and manifest[key] == actual, PIN_CODES[key])
    source = manifest['source_sha']
    need(is_sha(source, 40) and is_sha(head, 40) and is_sha(parent, 40),
         'GIT_HASH')
    need(type(event) is dict, 'EVENT_SHAPE')
    need(event.get('ref') == 'refs/heads/main', 'REF')
    need(event.get('before') == source == parent and source != head, 'FIRST_PARENT')
    need(event.get('after') == head, 'HEAD')
    need(diff == 'A\t' + LAUNCH + '\n', 'ONLY_ADDED')
    profile = manifest['selected_profile']
    need(type(profile) is int and 0 <= profile < 5, 'SELECTED_PROFILE')
    cohort = manifest['expected_cohort_sv_sha256']
    need(cohort is None or is_sha(cohort), 'COHORT_DIGEST')
    return source


def build_identity(repo, environ, git=git_read):
    need(environ.get('GITHUB_EVENT_NAME') == 'push', 'EVENT_TYPE')
    need(environ.get('GITHUB_REF') == 'refs/heads/main', 'REF')
    need(environ.get('GITHUB_RUN_ATTEMPT') == '1', 'ATTEMPT')
    event_path = P(environ['GITHUB_EVENT_PATH'])
    need(event_path.is_file() and not event_path.is_symlink() and
         0 < event_path.stat().st_size <= 1 << 20, 'EVENT_FILE')
    event = read_json(event_path.read_bytes())
    launch_bytes = checked_bytes(repo, LAUNCH, 4096)
    manifest = read_json(launch_bytes)
    parents = git(repo, 'rev-list', '--parents', '-n', '1', 'HEAD').decode('ascii').split()
    need(len(parents) == 2, 'FIRST_PARENT')
    head, parent = parents
    need(head == environ['GITHUB_SHA'], 'HEAD')
    diff = git(repo, 'diff-tree', '--no-commit-id', '--name-status', '-r', 'HEAD').decode('utf-8')
    local_bytes = {key: checked_bytes(repo, relative, 1 << 20)
                   for key, relative in PIN_PATHS.items()}
    source_pins = {key: digest(raw) for key, raw in local_bytes.items()}
    source = validate(event, manifest, environ['GITHUB_RUN_ATTEMPT'],
                      head, parent, diff, source_pins)
    need(git(repo, 'show', head + ':' + LAUNCH) == launch_bytes,
         'COMMITTED_BYTES')
    launch_blob = git(repo, 'rev-parse', head + ':' + LAUNCH).decode('ascii').strip()
    expected_blob = hashlib.sha1(b'blob ' + str(len(launch_bytes)).encode('ascii') +
                                 b'\0' + launch_bytes).hexdigest()
    need(is_sha(launch_blob, 40) and launch_blob == expected_blob, 'LAUNCH_BLOB')
    need(git(repo, 'ls-tree', source, '--', LAUNCH) == b'',
         'NONCE_ALREADY_PRESENT')
    for key, relative in PIN_PATHS.items():
        source_bytes = git(repo, 'show', source + ':' + relative)
        need(source_bytes == local_bytes[key], PIN_CODES[key])
    plan = read_json(local_bytes['plan_sha256'])
    need(type(plan) is dict, 'PLAN_SHAPE')
    need(is_sha(plan.get('source_catalog_sha256')) and plan.get('model_generation_sha256') == MODEL_GENERATION,
         'SOURCE_IDENTITY_UNFINALIZED')
    # Plan approval is intentionally not asserted here. The immutable source
    # entry checks the real reviewed plan, resources and original job clock.
    run_id = environ['GITHUB_RUN_ID']
    need(type(run_id) is str and re.fullmatch('[1-9][0-9]{0,19}', run_id) is not None,
         'RUN_ID')
    return dict(schema=IDENTITY_SCHEMA, run_id=int(run_id), run_attempt=1,
                source_commit=source, launch_commit=head, nonce=NONCE,
                artifact_name='gdn32-first-meaningful-p1-retry1-' + run_id,
                launch_manifest_path=LAUNCH, launch_manifest_blob_sha=launch_blob,
                hardware_generation_sha256=HARDWARE_GENERATION,
                model_generation_sha256=MODEL_GENERATION,
                **source_pins, plan_path=PLAN,
                selected_profile=manifest['selected_profile'],
                expected_cohort_sv_sha256=manifest['expected_cohort_sv_sha256'],
                launch_manifest_sha256=digest(launch_bytes))


def main():
    repo = P(os.environ['GITHUB_WORKSPACE']).resolve()
    need(P(__file__).resolve() == repo / GUARD, 'GUARD_PATH')
    identity = build_identity(repo, os.environ)
    target = P(os.environ['RUNNER_TEMP']) / 'gdn32-full-identity.json'
    with target.open('x') as stream:
        json.dump(identity, stream, sort_keys=True)
        stream.write('\n')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write('source_sha=' + identity['source_commit'] + '\n')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps(safe_refusal(exc), sort_keys=True))
        raise SystemExit(1)
