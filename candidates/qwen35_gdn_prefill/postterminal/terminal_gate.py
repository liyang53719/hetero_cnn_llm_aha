"""Read-only admission of a root-reviewed, already-terminal execution receipt.

This does not recover Popen authority or prove current namespace absence. It
checks durable evidence from the original retained owner, plus an explicit
retaining-parent handoff. It never signals, waits, imports a model or opens an
actual tensor. A missing/uncertain terminal or cleanup record fails closed.
"""
import hashlib
import json
import math
from pathlib import Path
import copy
import types

# These unchanged implementations are repository-relative, never private roots.
CLEANUP_SHA = '30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047'
SOURCE_FILES = {
    'full_compare': ('candidates/qwen35_gdn_prefill/full_compare.py',
                     'a3de68cba35a649e98fa76ce103731a31c90f79c179d8806232b274c933f3ec1'),
    'strict_cleanup': ('scripts/idma_source_export_20261017/strict_cleanup.py', CLEANUP_SHA),
    'bounded_run': ('scripts/idma_source_export_20261017/bounded_run.py',
                    '26039ae437f9296767ee65cf8303146eadfb61a3116f60e9196a4f68f5b0b380'),
}
SCOPE = 'ANCHORED_ORIGINAL_GROUP_AND_OBSERVED_IDENTITIES_ONLY'
OWNER_KEYS = ('pid', 'ppid', 'group', 'start')
IDENTITY_KEYS = (*OWNER_KEYS, 'session')
PROOF_KEYS = {'schema', 'status', 'scope', 'source_sha256', 'parent_pid', 'boot_id', 'owner_identity',
    'session', 'stop', 'started', 'signal_at', 'barrier_at', 'reap_started_at', 'reaped_at', 'completed_at',
    'empty_complete_scans', 'no_nonleader_identities_at_barrier', 'direct_leader_reaped', 'direct_exit_code',
    'no_post_reap_signals', 'grandchildren_reaped_by_this_helper', 'complete_scan_bounds', 'scan_evidence_sha256'}
STATES = frozenset('RSDZTtXxKWPI')
def original_scan_classifier(repository):
    """Load only hash-pinned source; call its pure scan classifier, not cleanup."""
    path, raw = read_source(repository, 'strict_cleanup')
    module = types.ModuleType('original_readonly_scan_classifier')
    module.__file__ = str(path)
    module._ADMITTED_SOURCE_SHA256 = CLEANUP_SHA
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    need(module._classify_scan.__code__.co_filename == str(path), 'scan classifier origin')
    return module._classify_scan


def need(ok, reason):
    if not ok:
        raise ValueError('terminal gate: ' + reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def valid_digest(value, length=64):
    return type(value) is str and len(value) == length and all(c in '0123456789abcdef' for c in value)


def unaliased_path(value, base=None):
    need(type(value) is str and bool(value) and '\\' not in value, 'path must be a plain nonempty string')
    path = Path(value)
    need(str(path) == value and '..' not in path.parts and '.' not in path.parts,
         'path spelling/parent aliases forbidden')
    if not path.is_absolute():
        need(base is not None, 'absolute unaliased path required')
        path = Path(base) / path
    need(not path.is_symlink() and path.resolve(strict=False) == path, 'path aliases forbidden')
    return path


def read_pinned(path, pin, cap=32 << 20):
    path = unaliased_path(str(path))
    need(type(pin) is dict and valid_digest(pin.get('sha256')), 'invalid receipt hash pin')
    before = path.stat()
    need(path.is_file() and type(pin.get('bytes')) is int and 0 < pin['bytes'] <= cap and
         before.st_size == pin['bytes'], 'receipt byte extent')
    raw = path.read_bytes()
    after = path.stat()
    need(len(raw) == pin['bytes'] and digest(raw) == pin['sha256'], 'receipt hash')
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(all(getattr(before, k) == getattr(after, k) for k in fields), 'receipt changed while reading')
    return raw


def strict_json(raw):
    def object_pairs(pairs):
        out = {}
        for key, value in pairs:
            need(key not in out, 'duplicate JSON key: ' + key)
            out[key] = value
        return out
    def invalid_number(value):
        raise ValueError('terminal gate: nonfinite JSON number: ' + value)
    return json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid_number)


def read_source(repository, name):
    relative, pin = SOURCE_FILES[name]
    path = unaliased_path(str(Path(repository) / relative))
    raw = read_pinned(path, dict(bytes=path.stat().st_size, sha256=pin), 2 << 20)
    return path, raw


def load_reviewed_config(path, reviewed_sha):
    """Admission only: no model/tensor or run evidence is read here.

    A digest supplied independently by the retaining reviewer is the trust root.
    A hash computed from an unreviewed file is not authorization or evidence.
    Relative paths are resolved against this file, without '..' or symlinks.
    """
    path = unaliased_path(str(path), Path.cwd())
    need(valid_digest(reviewed_sha), 'explicit reviewed configuration SHA required')
    pin = dict(bytes=path.stat().st_size, sha256=reviewed_sha)
    data = strict_json(read_pinned(path, pin, 2 << 20))
    need(type(data) is dict and set(data) == {'schema', 'scope', 'source_commit',
         'full_driver_sha256', 'paths', 'files', 'terminal'}, 'exact reviewed configuration fields required')
    need(type(data['schema']) is int and data['schema'] == 1 and
         data['scope'] == 'REVIEWED_POST_TERMINAL_COLD128_CONFIGURATION', 'configuration schema/scope')
    need(valid_digest(data['source_commit'], 40) and valid_digest(data['full_driver_sha256']),
         'configuration source identities')
    paths = data['paths']
    need(type(paths) is dict and set(paths) == {'repository', 'harness', 'run_directory', 'fixture', 'numpy_site'},
         'exact configuration path inventory')
    resolved_paths = {key: unaliased_path(value, path.parent) for key, value in paths.items()}
    need(len(set(resolved_paths.values())) == len(resolved_paths), 'distinct configured roots required')
    need(resolved_paths['run_directory'].is_relative_to(resolved_paths['harness']),
         'run directory must be under frozen harness')
    files = data['files']
    need(type(files) is dict and set(files) == {'plan', 'terminal_manifest', 'reference_freeze', 'native_manifest'},
         'exact configuration file inventory')
    resolved_files = {}
    for key, item in files.items():
        need(type(item) is dict and set(item) == {'path', 'bytes', 'sha256'} and
             type(item['bytes']) is int and 0 < item['bytes'] <= 32 << 20 and valid_digest(item['sha256']),
             'invalid configured file pin: ' + key)
        resolved_files[key] = dict(item, path=str(unaliased_path(item['path'], path.parent)))
    need(len({pin['path'] for pin in resolved_files.values()}) == len(resolved_files),
         'distinct configured files required')
    for key, filename in (('plan', 'PLAN.json'), ('reference_freeze', 'REFERENCE_FREEZE.json')):
        need(resolved_files[key]['path'] == str(resolved_paths['harness'] / filename),
             'exact frozen harness file: ' + key)
    terminal = data['terminal']
    need(type(terminal) is dict and set(terminal) == {'retained_exec_session', 'executor_exit_code',
         'owner_identity', 'boot_id', 'work_start_monotonic'}, 'exact configuration terminal identity')
    owner = terminal['owner_identity']
    need(type(terminal['retained_exec_session']) is int and terminal['retained_exec_session'] > 0 and
         type(terminal['executor_exit_code']) is int and terminal['executor_exit_code'] == 1 and
         type(owner) is dict and set(owner) == set(IDENTITY_KEYS) and
         all(type(owner[key]) is int and owner[key] > 0 for key in IDENTITY_KEYS) and
         owner['pid'] > 1 and owner['pid'] == owner['group'] == owner['session'],
         'strict known-terminal/retained-owner identity required')
    boot = terminal['boot_id']
    need(type(boot) is str and len(boot) == 36 and
         tuple(i for i, char in enumerate(boot) if char == '-') == (8, 13, 18, 23) and
         all(char in '0123456789abcdef-' for char in boot) and _finite(terminal['work_start_monotonic']),
         'terminal boot/work-start identity')
    return dict(data, paths=resolved_paths, files=resolved_files, _path=path, _pin=pin)


def recheck_config(config):
    read_pinned(config['_path'], config['_pin'], 2 << 20)
    for name in SOURCE_FILES:
        read_source(config['paths']['repository'], name)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _row(row):
    return (type(row) is dict and set(row) == {*IDENTITY_KEYS, 'state'} and
            all(type(row[k]) is int and row[k] >= 0 for k in IDENTITY_KEYS) and
            row['pid'] > 0 and row['start'] > 0 and type(row['state']) is str and row['state'] in STATES)


def validate_durable_cleanup(start, launch, cleanup, work_start, *, repository):
    """Validate serialized evidence, never impersonate a retained parent handle."""
    need(launch.get('status') == 'FAILED' and launch.get('actual_complete_uncompared') is False and
         launch.get('cleanup_confirmed') is True and type(launch.get('returncode')) is int,
         'known incomplete terminal with confirmed cleanup required')
    need(launch.get('all_frozen_actual_inputs_unchanged') is not False,
         'explicit final identity failure cannot be ignored')
    proof = launch.get('cleanup_proof')
    need(type(proof) is dict and set(proof) == PROOF_KEYS and cleanup.get('proof') == proof and
         all(cleanup.get(k) is True for k in ('cleanup_complete', 'leader_reaped', 'authority_released')),
         'original complete cleanup receipt required')
    need(not any(k in cleanup for k in ('error', 'evidence_budget_exhausted', 'omitted_scan',
         'direct_reap_incomplete', 'alarm_finalization_error', 'containment_signal_error', 'containment_reap_error')),
         'cleanup error evidence cannot be ignored')
    need(type(proof.get('schema')) is int and proof['schema'] == 1 and proof.get('status') == 'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and
         proof.get('scope') == cleanup.get('scope') == SCOPE and
         proof.get('source_sha256') == cleanup.get('source_sha256') == CLEANUP_SHA,
         'unchanged cleanup source/schema/scope')
    owner = proof.get('owner_identity')
    need(type(owner) is dict and set(owner) == set(OWNER_KEYS) and
         all(type(owner[k]) is int and owner[k] > 0 for k in OWNER_KEYS) and
         owner['pid'] > 1 and type(proof.get('session')) is int and type(proof.get('parent_pid')) is int and
         owner['pid'] == owner['group'] == proof.get('session') and
         owner['ppid'] == proof.get('parent_pid') == launch.get('supervisor_pid'), 'retained owner identity')
    for row in (start, launch.get('child_identity', {}), cleanup.get('leader', {})):
        need(all(row.get(k) == (proof['session'] if k == 'session' else owner[k]) for k in IDENTITY_KEYS),
             'START/launch/cleanup identity disagreement')
    need(_row(launch.get('child_identity')) and _row(cleanup.get('leader')), 'original complete leader rows')
    need(type(proof.get('boot_id')) is str and len(proof['boot_id']) == 36 and
         tuple(i for i,c in enumerate(proof['boot_id']) if c == '-') == (8,13,18,23) and
         all(c in '0123456789abcdef-' for c in proof['boot_id']) and
         start.get('boot_id') == launch.get('boot_id') == proof['boot_id'], 'boot identity')
    need(_finite(work_start) and proof.get('stop') == work_start + 10830 and
         cleanup.get('stop') == proof['stop'], 'original absolute cleanup deadline')
    times = [proof.get(k) for k in ('started', 'signal_at', 'barrier_at', 'reap_started_at', 'reaped_at', 'completed_at')]
    need(all(_finite(v) for v in times) and times == sorted(times) and times[-1] < proof['stop'] and
         times[2] < times[3] and cleanup.get('started') == times[0], 'barrier must precede reap before original stop')
    need(type(proof.get('empty_complete_scans')) is int and proof['empty_complete_scans'] == 2 and
         all(proof.get(k) is True for k in ('no_nonleader_identities_at_barrier', 'direct_leader_reaped', 'no_post_reap_signals')) and
         proof.get('grandchildren_reaped_by_this_helper') is False and
         type(proof.get('direct_exit_code')) is int and proof.get('direct_exit_code') == launch['returncode'], 'strict absence/reap claims')
    scans = cleanup.get('scans')
    need(type(scans) is list and 2 <= len(scans) <= 4096, 'bounded retained-leader scans required')
    classify = original_scan_classifier(repository)
    first_identity = next((item.get('original') for item in scans[0].get('identities', [])
                           if item.get('original', {}).get('pid') == owner['pid']), None)
    need(_row(first_identity) and all(first_identity[k] == start[k] for k in IDENTITY_KEYS),
         'original tracked leader identity required')
    tracked_all = {owner['pid']: copy.deepcopy(first_identity)}
    previous_finish = times[1]
    for observed_scan in scans:
        need(observed_scan.get('complete') is True and 'error' not in observed_scan and
             _finite(observed_scan.get('started')) and _finite(observed_scan.get('finished')) and
             previous_finish <= observed_scan['started'] <= observed_scan['finished'] < proof['stop'],
             'no incomplete/error/reordered original scan may be ignored')
        previous_finish = observed_scan['finished']
        reproduced = copy.deepcopy(observed_scan)
        try:
            classify(reproduced, tracked_all, cleanup['leader'])
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            raise ValueError('terminal gate: original scan history rejected: ' + str(error)) from error
        need(all(reproduced[k] == observed_scan.get(k) for k in
             ('identities', 'nonleader_present', 'live_nonleader_present')),
             'exact original chronological scan history required')
    scans = scans[-2:]
    need(digest(canonical(scans)) == proof.get('scan_evidence_sha256'), 'scan evidence hash')
    bounds = [[s.get('started'), s.get('finished')] for s in scans]
    need(proof.get('complete_scan_bounds') == bounds and all(_finite(v) for pair in bounds for v in pair) and
         times[1] <= bounds[0][0] <= bounds[0][1] <= bounds[1][0] <= bounds[1][1] == times[2],
         'ordered original scan bounds')
    for scan in scans:
        need('error' not in scan, 'scan error evidence cannot be ignored')
        need(all(scan.get(k) is True for k in ('complete', 'leader_exited_retained')) and
             scan.get('nonleader_present') is False and scan.get('live_nonleader_present') is False,
             'complete anchored absence scan required')
        captured, members = scan.get('captured'), scan.get('members')
        need(type(captured) is dict and type(members) is list and members, 'complete scan inventory')
        anchor = captured.get(str(owner['pid']))
        need(_row(anchor) and all(anchor.get(k) == start[k] for k in IDENTITY_KEYS), 'retained scan anchor')
        need(any(all(row.get(k) == start[k] for k in IDENTITY_KEYS) for row in members), 'enumerated retained leader')
        for row in [*captured.values(), *members]:
            if row is None:
                continue
            need(_row(row), 'scan identity types')
            need(row['group'] != owner['group'] or all(row[k] == start[k] for k in IDENTITY_KEYS),
                 'nonleader identity still present in original group')
        identities = scan.get('identities')
        need(type(identities) is list and identities, 'tracked-identity scan evidence')
        tracked = set()
        for item in identities:
            original, observed = item.get('original', {}), item.get('observed')
            pid = original.get('pid'); tracked.add(str(pid))
            need(_row(original) and (observed is None or _row(observed)), 'tracked identity')
            classification = ('identity_disappeared' if observed is None else
                'identity_reused_unrelated' if observed['start'] != original['start'] else
                'defunct_present_unreaped' if observed['state'] == 'Z' else
                'dead_transient_present' if observed['state'] in ('X', 'x') else 'live_or_not_proven_dead')
            need(item.get('classification') == classification and
                 (observed is None or observed['pid'] == pid), 'tracked classification/identity consistency')
            if pid != owner['pid']:
                need(observed is None or (type(observed) is dict and observed.get('start') != original['start'] and
                     observed.get('group') != owner['group']), 'tracked nonleader has not disappeared')
        need(set(captured) == tracked, 'all tracked identities enumerated')
        original_tracked = {item['original']['pid']: copy.deepcopy(item['original']) for item in identities}
        replay = copy.deepcopy(scan)
        try:
            absent = classify(replay, original_tracked, cleanup['leader'])
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            raise ValueError('terminal gate: original scan classifier rejected evidence: ' + str(error)) from error
        need(absent is True and
             replay['identities'] == scan['identities'] and replay['nonleader_present'] is False and
             replay['live_nonleader_present'] is False, 'original pure classifier must reproduce complete absence evidence')
    signals = cleanup.get('signals')
    need(type(signals) is list and signals and signals[0].get('at') == times[1] and all(s.get('pid') == owner['pid'] and
         s.get('kind') == 'SIGKILL' and s.get('leader_retained') is True and _finite(s.get('at')) and
         times[0] <= s['at'] < times[3] for s in signals), 'all original signals before reap')
    return proof


def admit_terminal_manifest(path, reviewed_sha, *, config_path, reviewed_config_sha):
    config = load_reviewed_config(config_path, reviewed_config_sha)
    path = unaliased_path(str(path), Path.cwd())
    mpin = config['files']['terminal_manifest']
    need(valid_digest(reviewed_sha) and reviewed_sha == mpin['sha256'] and str(path) == mpin['path'],
         'exact reviewed terminal manifest binding required')
    manifest = strict_json(read_pinned(path, mpin, 2 << 20))
    expected_plan_path = Path(config['files']['plan']['path'])
    expected_plan_sha = config['files']['plan']['sha256']
    source_commit = config['source_commit']
    terminal = config['terminal']
    need(type(manifest.get('schema')) is int and manifest['schema'] == 1 and manifest.get('scope') == 'ROOT_REVIEWED_TERMINAL_COLD_DIAGNOSTIC_HANDOFF' and
         type(manifest.get('retained_exec_session')) is int and manifest['retained_exec_session'] == terminal['retained_exec_session'] and manifest.get('retained_handle_terminal_observed') is True and
         type(manifest.get('executor_exit_code')) is int and manifest['executor_exit_code'] == terminal['executor_exit_code'] == 1 and manifest.get('overall_status') == 'INCOMPLETE' and
         manifest.get('combined_full_run_acceptance') is False, 'explicit known-terminal parent handoff')
    pinfo = manifest['plan']; expected_plan_path = Path(expected_plan_path)
    need(pinfo == config['files']['plan'], 'exact frozen plan')
    plan = strict_json(read_pinned(expected_plan_path, pinfo, 4 << 20))
    need(plan['source_commit'] == manifest.get('source_commit') == source_commit, 'frozen source commit')
    run = Path(plan['run_directory'])
    need(manifest.get('run_directory') == str(run) == str(config['paths']['run_directory']),
         'exact original run directory')
    need(plan.get('repository') == str(config['paths']['repository']) and
         plan.get('numpy_site') == str(config['paths']['numpy_site']) and
         plan['driver_api']['fixture'] == str(config['paths']['fixture']) and
         plan['comparison']['native_manifest'] == config['files']['native_manifest']['path'],
         'exact frozen source/reference/fixture paths')
    reference_pin = config['files']['reference_freeze']
    frozen_reference = plan.get('inputs', {}).get(reference_pin['path'])
    need(type(frozen_reference) is dict and
         frozen_reference.get('sha256') == reference_pin['sha256'] and
         frozen_reference.get('bytes') == reference_pin['bytes'] and
         frozen_reference.get('resolved') == reference_pin['path'], 'exact frozen reference inventory pin')
    paths = manifest['metadata']; pins = manifest['inputs']
    expected = dict(start=run/'START.json', launch=run/'LAUNCH.json', cleanup=run/'CLEANUP.json', identity=run/'actual/identity.json')
    evidence_key = Path(paths['evidence']).stem
    if evidence_key == 'progress':
        expected['summary'] = run/'actual/summary.json'
    need(set(paths) == {*expected, 'evidence'} and all(paths[k] == str(v) for k, v in expected.items()) and
         paths['evidence'] in (str(run/'actual/summary.json'), str(run/'actual/progress.json')) and
         set(pins) == set(paths.values()), 'only explicitly admitted terminal metadata paths')
    # Identity/evidence/tensors are intentionally NOT read until cleanup passes.
    start, launch, cleanup = [strict_json(read_pinned(paths[k], pins[paths[k]])) for k in ('start', 'launch', 'cleanup')]
    need(start.get('plan_sha256') == launch.get('plan_sha256') == expected_plan_sha and
         launch.get('source_commit') == source_commit, 'original plan/source receipt binding')
    work_start = terminal['work_start_monotonic']
    need(start.get('work_stop_monotonic') == work_start + 10800 and
         all(type(start.get(key)) is int and start[key] == terminal['owner_identity'][key] for key in IDENTITY_KEYS) and
         start.get('boot_id') == terminal['boot_id'], 'frozen retained-owner/start/deadline identity')
    need(launch.get('original_stop_monotonic') == work_start + 11400, 'original work/outer deadline binding')
    validate_durable_cleanup(start, launch, cleanup, work_start, repository=config['paths']['repository'])
    recheck_config(config)
    metadata_files = {k: dict(path=paths[v], **pins[paths[v]]) for k, v in (('identity', 'identity'), (evidence_key, 'evidence'))}
    if evidence_key == 'progress':
        metadata_files['summary'] = dict(path=paths['summary'], **pins[paths['summary']])
    return dict(config=config, plan=plan, run=run, manifest=manifest, metadata_paths=paths, metadata_pins=pins,
        actual_directory=run/'actual', metadata_files=metadata_files, evidence_kind=evidence_key,
        start=start, launch=launch, cleanup=cleanup,
        whole_run_status='INCOMPLETE', recorded_launch_status=launch['status'], source_commit=source_commit,
        plan_sha256=expected_plan_sha, terminal_manifest_sha256=reviewed_sha,
        native_manifest=plan['comparison']['native_manifest'], fixture=plan['driver_api']['fixture'],
        include_conv_reference_arithmetic=manifest.get('include_conv_reference_arithmetic') is True,
        _manifest_path=path, _manifest_pin=mpin, _plan_path=expected_plan_path, _plan_pin=pinfo)


def recheck_terminal_manifest(gate):
    recheck_config(gate['config'])
    read_pinned(gate['_manifest_path'], gate['_manifest_pin'], 2 << 20)
    read_pinned(gate['_plan_path'], gate['_plan_pin'], 4 << 20)
    for key in ('start', 'launch', 'cleanup'):
        path = gate['metadata_paths'][key]
        read_pinned(path, gate['metadata_pins'][path])


def admit_terminal(path, reviewed_sha, config_path, reviewed_config_sha):
    return admit_terminal_manifest(path, reviewed_sha, config_path=config_path,
                                   reviewed_config_sha=reviewed_config_sha)
