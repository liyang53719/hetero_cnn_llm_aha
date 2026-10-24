"""Read-only replay of a SHA-pinned saved inventory, not live admission.

No saved module/source is imported, executed, opened, or rehashed. All rows and
previous failures are retained. Only the legacy built-in/frozen display-name
conflict can be reclassified using recorded loader/spec/canonical object IDs.
JSON object IDs cannot establish the historical or future live Python object
identity. A fresh collect_modules audit with live-object checks remains required.
"""
import _imp
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import resource
import signal

KINDS = frozenset(('built-in', 'frozen', 'normal_file_module', 'normal_main_script',
                   'normal_namespace_package', 'registered_typing_compat_namespace',
                   'synthetic_namespace_package', 'synthetic_ast_module'))


def replay_inventory(report):
    failures, reclassified, checked = [], [], []
    def fail(name, code):
        failures.append({'name': name, 'code': code})
    rows = report.get('modules') if type(report) is dict else None
    if type(rows) is not list:
        raise ValueError('saved inventory modules must be a list')
    names, groups = {}, {}
    for row in rows:
        if type(row) is not dict or type(row.get('name')) is not str or type(row.get('object_id')) is not str:
            raise ValueError('invalid saved row identity')
        if row['name'] in names:
            fail(row['name'], 'duplicate_module_key')
        names[row['name']] = row
        groups.setdefault(row['object_id'], []).append(row['name'])
    if report.get('schema') != 1 or report.get('entry_count') != len(rows) or report.get('unique_object_count') != len(groups):
        fail(None, 'inventory_counts_or_schema_mismatch')
    original = [{'name': row['name'], **error} for row in rows for error in row.get('errors', [])]
    if report.get('failures') != original:
        fail(None, 'original_failure_ledger_mismatch')
    expected_status = 'FAIL_MODULE_IDENTITY' if original else 'PASS_MODULE_IDENTITY'
    if report.get('status') != expected_status:
        fail(None, 'original_status_mismatch')
    runtime = report.get('runtime_interpreter', {})
    runtime_pin = runtime.get('pin') or {}
    runtime_ok = (runtime.get('match') is True and runtime.get('pinned') is True and
                  runtime.get('errors') == [] and runtime.get('hash_status') == 'computed' and
                  runtime.get('sha256') == runtime_pin.get('sha256') and
                  runtime.get('bytes') == runtime_pin.get('bytes'))
    for row in rows:
        name, kind = row['name'], row.get('kind')
        before = len(failures)
        if kind not in KINDS:
            fail(name, 'unknown_or_unverified_module_kind')
        if row.get('aliases') != groups[row['object_id']]:
            fail(name, 'alias_object_id_ledger_mismatch')
        if type(row.get('errors')) is not list or row.get('match') is not (not row.get('errors')):
            fail(name, 'original_row_status_mismatch')
        recognized = False
        canonical = names.get(row.get('spec_name'))
        if kind in ('built-in', 'frozen'):
            spec = row.get('spec_name')
            recognized = type(spec) is str and bool(_imp.is_builtin(spec) if kind == 'built-in' else _imp.is_frozen(spec))
            loader = '_frozen_importlib.' + ('BuiltinImporter' if kind == 'built-in' else 'FrozenImporter')
            if not recognized or row.get('spec_origin') != kind:
                fail(name, 'unrecognized_saved_builtin_or_frozen_spec')
            if row.get('loader') != loader or row.get('spec_loader') != loader:
                fail(name, 'saved_builtin_or_frozen_loader_conflict')
            if canonical is None or canonical['object_id'] != row['object_id']:
                fail(name, 'saved_canonical_object_id_mismatch')
            if not runtime_ok or row.get('runtime_pin_match') is not True:
                fail(name, 'saved_interpreter_pin_mismatch')
            if kind == 'built-in' and row.get('__file__') is not None:
                fail(name, 'saved_builtin_claims_file')
        # Preserve all previously verified categories. Do not fabricate missing
        # live source/code checks from serialized metadata or object ID strings.
        for error in row.get('errors', []):
            compatible = (kind in ('built-in', 'frozen') and len(failures) == before and
                          error == {'code': 'builtin_or_frozen_object_alias_mismatch', 'detail': row.get('spec_name')} and
                          type(row.get('module_name')) is str and row['module_name'] != row.get('spec_name'))
            if compatible:
                reclassified.append({'name': name, 'original_error': error,
                                     'module_name': row['module_name'], 'spec_name': row['spec_name'],
                                     'basis': 'Recorded spec/loader/canonical object IDs support display-name compatibility only.'})
            else:
                failures.append({'name': name, 'code': 'retained_original_failure', 'original_error': error})
        checked.append({'name': name, 'kind': kind, 'object_id': row['object_id'],
                        'replay_compatible': len(failures) == before})
    return {'schema': 1,
            'status': 'FAIL_OFFLINE_COMPATIBILITY_REPLAY' if failures else 'PASS_OFFLINE_COMPATIBILITY_REPLAY_NOT_LIVE_ADMISSION',
            'entry_count': len(rows), 'unique_object_count': len(groups),
            'kind_counts': dict(sorted(Counter(row.get('kind') for row in rows).items())),
            'checked_rows': checked, 'reclassified_legacy_errors': reclassified, 'failures': failures,
            'historical_result_unchanged': report.get('status'), 'live_admission': False,
            'limitations': 'Pinned JSON replay is not a live module audit. Recorded IDs cannot replace future snapshot/live canonical object equality, file rehashing, source/code checks, or mapping audit. No task, NumPy, DUT, or native attempt is executed.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 ** 2,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    signal.alarm(25)
    raw = args.input.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != args.sha256:
        raise ValueError('exact saved inventory SHA256 mismatch')
    result = replay_inventory(json.loads(raw))
    result['input'] = {'path': str(args.input.resolve()), 'bytes': len(raw), 'sha256': actual}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    print(result['status'], result['entry_count'], 'rows;', len(result['failures']), 'failures; not live admission')
    if result['failures']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
