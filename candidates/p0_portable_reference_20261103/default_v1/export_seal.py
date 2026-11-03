"""Private terminal seal plus actual workflow outcome; never export a stale PASS."""
import json
from pathlib import Path
from fixture_gate import need, sha, strict_json
from safe_export import FILENAMES, validate_exports


def seal_export(work, identity, status, reason, wall_seconds, cpu_seconds):
    work = Path(work)
    value = dict(schema='P0_DEFAULT_TERMINAL_SEAL_V1', run_id=identity['run_id'],
                 source_commit=identity['source_commit'], launch_commit=identity['launch_commit'],
                 source_manifest_sha256=identity['source_manifest_sha256'], status=status, reason=reason,
                 wall_seconds=wall_seconds, charged_cpu_seconds=cpu_seconds,
                 files={name:sha(work/'export'/name) for name in FILENAMES}, root_retained=True,
                 no_old_owner_resources_touched=True)
    target = work/'TERMINAL.json'
    need(not target.exists() and not target.is_symlink(), 'EXPORT_SCHEMA')
    temp = work/'TERMINAL.pending'
    with temp.open('x') as stream:
        json.dump(value,stream,sort_keys=True,allow_nan=False);stream.write('\n')
        stream.flush()
        import os
        os.fsync(stream.fileno())
    temp.replace(target)


def verify_sealed_export(work, identity, frozen_path, controller_outcome):
    work = Path(work)
    need(controller_outcome in ('success','failure'), 'EXPORT_SCHEMA')
    terminal = strict_json(work/'TERMINAL.json')
    need(set(terminal) == {'schema','run_id','source_commit','launch_commit','source_manifest_sha256','status','reason',
                          'wall_seconds','charged_cpu_seconds','files','root_retained','no_old_owner_resources_touched'}, 'EXPORT_SCHEMA')
    need(terminal['schema']=='P0_DEFAULT_TERMINAL_SEAL_V1', 'EXPORT_SCHEMA')
    for key in ('run_id','source_commit','launch_commit','source_manifest_sha256'):
        need(terminal[key] == identity[key], 'EXPORT_SCHEMA')
    need(terminal['root_retained'] is True and terminal['no_old_owner_resources_touched'] is True, 'EXPORT_SCHEMA')
    need(type(terminal['files']) is dict and set(terminal['files'])==set(FILENAMES), 'EXPORT_SCHEMA')
    before = {name:sha(work/'export'/name) for name in FILENAMES}
    need(before == terminal['files'], 'EXPORT_SCHEMA')
    records = validate_exports(work/'export', frozen_path)
    result=records['RESULT.json']
    need(terminal['status']==result['status'] and terminal['reason']==result['reason'], 'EXPORT_SCHEMA')
    need(result['candidate_source_sha256']==identity['source_manifest_sha256'], 'EXPORT_SCHEMA')
    for key in ('wall_seconds','charged_cpu_seconds'):
        need(type(terminal[key]) in (int,float) and 0 <= terminal[key] <= 3600, 'EXPORT_SCHEMA')
    # This trusted GitHub step result covers failures after any file was written,
    # including alarms between the seal and the controller's final budget check.
    if result['status']=='PASS_EXACT_VISIBLE_FIXTURE':
        need(controller_outcome=='success', 'EXPORT_SCHEMA')
    need({name:sha(work/'export'/name) for name in FILENAMES}==before, 'EXPORT_SCHEMA')
    return records
