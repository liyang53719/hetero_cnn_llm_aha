"""Explicit selected dependencies, derived from the unchanged original70 plan.
No filtered caller inventory is accepted. The original range fetch, header and
payload verification functions remain unchanged; this wrapper only selects whole
original profiles. No framework import, reference execution or DUT qualification.
"""
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import pathlib
import shutil
import sys

P = pathlib.Path
D = P(__file__).resolve().parent
RECOVERY = 'candidates/five_profile_input_recovery_20261028'
RESUME = 'candidates/five_profile_acquisition_resume_20261028'
REFERENCE = 'candidates/independent_block_reference_prepare_v3_20261028T2312'
SCHEMA = 'SELECTED_ORIGINAL_WEIGHT_ACQUISITION_V1'
STATUS = 'ACQUIRED_SELECTED_ORIGINAL_TENSORS_ONLY'
COUNTS = (12, 14, 11, 18, 15)
PROFILE_SHA = 'd1c846e7b17fb07fab77643f0470c16660d0b872e9f66354f571e6585b6472b0'
ORIGINAL_ACQUIRE_SHA = '394130861ef0c43c89c78c62312760e62fd30c22e19cf3ef26b13e18e0480b9d'
ORIGINAL_RECONSTRUCT_SHA = '466c267f7a0c6eaaefc41705112196b6c4f29a037da03b692237f89b95b7baee'
ORIGINAL_PREFIX_SHA = 'b1cd8e44bb6a6f3b259f05c78c2a8c6c1297d1c177357ea7abf2548b05886c5d'


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with P(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def same(left, right):
    return canonical(left) == canonical(right)


def domain_sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def pin(path):
    path = P(path)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))


def checked_source(b, relative):
    path = P(b['repo']) / relative
    need(path.is_absolute() and path == path.resolve() and path.is_file()
         and all(not item.is_symlink() for item in (path, *path.parents)),
         'canonical selected dependency source')
    need(b['pins'].get(str(path)) == sha(path), 'explicit selected dependency source pin: ' + relative)
    return path


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def policy(b):
    path = checked_source(b, 'candidates/gdn32_first_model_execution_20261104/profile_policy.py')
    result = module('selected_material_policy', path)
    need(result.is_selected(b), 'explicit selected FULL dependency policy required')
    result.checked(b)
    need(same(b['profiles'], list(range(5))) and type(b['tokens']) is int and b['tokens'] == 128,
         'full registered hardware and original M128 required')
    return result


def profiles(b):
    path = checked_source(b, REFERENCE + '/profiles.json')
    need(sha(path) == PROFILE_SHA, 'unchanged original profile metadata')
    return json.loads(path.read_text())


def source_inputs(b):
    """Pin all original metadata used by verified_plan, including header texts."""
    root = P(b['repo']) / RECOVERY
    names = ['reconstruct_plan.py', 'ACQUISITION_PLAN.json', 'TENSOR_ACQUISITION_PLAN.json',
             'HISTORICAL_SOURCE_HASH_SET.json']
    names += ['pins/' + name for name in ('qwen2_1p5b_manifest.json', 'qwen3_5_0p8b_manifest.json',
               'qwen3_5_35b_a3b_manifest.json', 'layer0_payload_pin.json', 'layer3_payload_pin.json')]
    plan_path = checked_source(b, RECOVERY + '/ACQUISITION_PLAN.json')
    for row in json.loads(plan_path.read_text())['headers']:
        name = row['header']['json_text']
        need(type(name) is str and not P(name).is_absolute() and '..' not in P(name).parts,
             'original relative header path')
        names.append(name)
    for name in names:
        checked_source(b, RECOVERY + '/' + name)
    need(sha(checked_source(b, RESUME + '/acquire_resumable.py')) == ORIGINAL_ACQUIRE_SHA
         and sha(checked_source(b, RESUME + '/prefix.py')) == ORIGINAL_PREFIX_SHA
         and sha(root / 'reconstruct_plan.py') == ORIGINAL_RECONSTRUCT_SHA,
         'byte-unchanged original reconstruction and acquisition algorithms')
    return root


def selected_plan(b):
    p = policy(b)
    checked_source(b, 'candidates/gdn32_first_model_execution_20261104/runtime/selected_acquisition.py')
    root = source_inputs(b)
    original = module('selected_original_reconstruction', root / 'reconstruct_plan.py').verified_plan(root)
    registered = profiles(b)
    chosen = p.eligible(b)
    specs = []
    counts = {}
    for i in chosen:
        profile = registered[i]
        config = checked_source(b, 'config/upstream/weight_headers/' + profile['model'] + '/config.json')
        need(sha(config) == profile['config_sha256'], 'original selected config hash')
        prefix = ('model.layers.' if i == 0 else 'model.language_model.layers.') + str(profile['layer']) + '.'
        group = [row for row in original['specs'] if row['model'] == profile['model'] and row['name'].startswith(prefix)]
        need(len(group) == COUNTS[i] and all(row['revision'] == profile['checkpoint_revision'] for row in group),
             'complete original selected layer tensor inventory')
        specs.extend(group)
        counts[str(i)] = len(group)
    specs.sort(key=lambda row: (row['model'], row['name']))
    need(len({(row['model'], row['name']) for row in specs}) == len(specs), 'unique complete selected tensors')
    urls = {row['url'] for row in specs}
    headers = [row for row in original['headers'] if row['url'] in urls]
    need({row['url'] for row in headers} == urls, 'all and only selected original shard headers')
    total = sum(row['bytes'] for row in specs)
    return dict(schema=SCHEMA, execution_policy=p.checked(b), profiles=chosen, tokens=128,
                profile_tensor_counts=counts, specs=specs, headers=headers, tensor_bytes=total,
                body_cap=total + sum(row['header']['bytes'] for row in headers),
                max_response_bytes=original['max_response_bytes'], workers=original['workers'],
                original_plan_sha256=sha(root / 'ACQUISITION_PLAN.json'),
                original_verified_plan_sha256=domain_sha(original),
                source_plan_sha256=original['source_plan_sha256'])


def validate_summary(summary, plan):
    need(summary['status'] == STATUS and same(summary['execution_policy'], plan['execution_policy'])
         and same(summary['profiles'], plan['profiles']) and same(summary['profile_tensor_counts'], plan['profile_tensor_counts'])
         and type(summary['tensors']) is int and summary['tensors'] == len(plan['specs'])
         and type(summary['tensor_bytes']) is int and summary['tensor_bytes'] == plan['tensor_bytes']
         and summary['selected_plan_sha256'] == domain_sha(plan)
         and summary['reference_executed'] is False and summary['dut_executed'] is False,
         'complete selected original acquisition only')
    totals = summary['totals']
    need(set(totals) == {'requested', 'received', 'requests'} and all(type(value) is int for value in totals.values())
         and totals['requested'] == totals['received'] == plan['body_cap'] and totals['requests'] > 0,
         'exact selected original range budget accounted')


def validate_inventory(b, rows):
    """Cheap exact selected union check; does not hash or qualify tensor bytes."""
    plan = selected_plan(b)
    need(type(rows) is list and len(rows) == len(plan['specs']), 'exact selected original tensor count')
    actual = {}
    for row in rows:
        need(type(row) is dict and set(row) == {'model', 'name', 'pin'}, 'exact selected weight row')
        key = (row['model'], row['name'])
        need(key not in actual, 'no duplicate selected weight')
        actual[key] = row
    expected = {(row['model'], row['name']): row for row in plan['specs']}
    need(set(actual) == set(expected), 'exact selected original semantic weight inventory')
    for key, spec in expected.items():
        value = actual[key]['pin']
        need(type(value) is dict and set(value) == {'path', 'bytes', 'sha256'}
             and type(value['bytes']) is int and value['bytes'] == spec['bytes'], 'original selected tensor byte geometry')
        path = P(value['path'])
        need(path.name == spec['name'] + '.bin' and path.parent.name == spec['model'], 'original selected tensor path roles')
        if 'payload' in b:
            need(path == P(b['payload']) / spec['model'] / (spec['name'] + '.bin'), 'exact selected payload path')
        if spec['verification'] == 'EXACT_NAME_SHA256':
            need(value['sha256'] == spec['expected_sha256'], 'original exact tensor SHA pin')
        elif spec['verification'] == 'PUBLISHED_RAW_SOURCE_SET_MEMBERSHIP':
            need(value['sha256'] in spec['allowed_sha256'], 'original raw-source membership pin')
    return [actual[key] for key in sorted(expected)]


def verify_weights(b, rows, payload, summary=None, allow_unselected=False):
    """Independently reconstruct selected semantics, then hash actual payloads.
    rows use the existing tail model/name/pin schema. allow_unselected is only
    for independently approved retained producer roots, never an acquisition.
    """
    plan = selected_plan(b)
    if summary is not None:
        validate_summary(summary, plan)
    payload = P(payload)
    need(payload.is_absolute() and payload == payload.resolve() and payload.is_dir()
         and all(not item.is_symlink() for item in (payload, *payload.parents)), 'canonical selected payload root')
    need(type(rows) is list and len(rows) == len(plan['specs']), 'exact selected original tensor count')
    actual = {}
    for row in rows:
        need(type(row) is dict and set(row) == {'model', 'name', 'pin'}, 'exact selected weight row')
        key = (row['model'], row['name'])
        need(key not in actual, 'no duplicate selected weight')
        actual[key] = row
    expected = {(row['model'], row['name']): row for row in plan['specs']}
    need(set(actual) == set(expected), 'exact selected original semantic weight inventory')
    receipts = set()
    files = set()
    result = []
    for key in sorted(expected):
        spec = expected[key]
        row = actual[key]
        path = payload / spec['model'] / (spec['name'] + '.bin')
        receipt_path = path.with_name(spec['name'] + '.receipt.json')
        for item in (path, receipt_path):
            need(item.is_file() and item == item.resolve() and all(not part.is_symlink() for part in (item, *item.parents)),
                 'canonical original selected tensor and receipt')
        need(receipt_path.stat().st_size <= 65536, 'bounded original tensor receipt')
        receipt = json.loads(receipt_path.read_text())
        need(all(same(receipt.get(name), value) for name, value in spec.items()), 'original selected weight semantic/range/hash policy')
        need(receipt['status'] == 'ACQUIRED_ORIGINAL_TENSOR_BYTES_ONLY_NOT_REFERENCE_OR_DUT'
             and receipt['file'] == str(path.relative_to(payload)) and type(receipt['actual_bytes']) is int
             and receipt['actual_bytes'] == spec['bytes'], 'original completed selected tensor receipt')
        actual_pin = pin(path)
        need(same(row['pin'], actual_pin) and actual_pin['bytes'] == spec['bytes']
             and actual_pin['sha256'] == receipt['actual_sha256'], 'actual selected tensor bytes hash')
        if spec['verification'] == 'EXACT_NAME_SHA256':
            need(actual_pin['sha256'] == spec['expected_sha256'], 'exact original tensor hash')
        elif spec['verification'] == 'PUBLISHED_RAW_SOURCE_SET_MEMBERSHIP':
            need(actual_pin['sha256'] in spec['allowed_sha256'], 'original raw-source hash set')
        else:
            need(spec['verification'] == 'FRESH_PINNED_REVISION_HTTPS_DIGEST_NO_HISTORICAL_PAYLOAD_HASH', 'unchanged original hash policy')
        receipts.add(receipt_path)
        files.add(path)
        result.append(dict(model=key[0], name=key[1], pin=actual_pin))
    if not allow_unselected:
        need(receipts == set(payload.glob('*/*.receipt.json'))
             and files == {item for item in payload.glob('*/*.bin') if item.parent.name != 'headers'},
             'only selected weight payload and receipts')
    need(sum(row['pin']['bytes'] for row in result) == plan['tensor_bytes'], 'exact selected complete layer bytes')
    return result


def run(b):
    plan = selected_plan(b)
    out = P(b['output'])
    need(out.is_absolute() and out == out.resolve() and not out.exists()
         and all(not item.is_symlink() for item in out.parents), 'fresh canonical selected acquisition output')
    need(shutil.disk_usage(out.parent).free >= 8 * 1024**3, 'original 8 GiB free acquisition gate')
    original_path = checked_source(b, RESUME + '/acquire_resumable.py')
    # The original importer resolves prefix from its script directory when run as
    # a program. Supply that same directory for this reviewed module invocation.
    sys.path.insert(0, str(original_path.parent))
    try:
        original = module('selected_original_acquire', original_path)
    finally:
        sys.path.remove(str(original_path.parent))
    original.OUT = out
    original.PREVIOUS = None
    original.BODY_CAP = plan['body_cap']
    need(original.MAX == plan['max_response_bytes'], 'unchanged original maximum response')
    out.mkdir()
    original.write_json(out / 'ACQUISITION_PLAN.json', plan)
    try:
        for header in plan['headers']:
            data = original.fetch(header['url'], 0, header['header']['bytes'] - 1, header['file_bytes'], 'shard-header')
            need(original.digest(data) == header['header']['sha256'], 'downloaded original header SHA mismatch')
            folder = out / 'headers'
            folder.mkdir(exist_ok=True)
            (folder / (original.digest(data) + '.bin')).write_bytes(data)
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=plan['workers']) as pool:
            pending = [pool.submit(original.acquire, row) for row in sorted(plan['specs'], key=lambda row: (row['bytes'], row['model'], row['name']))]
            for future in concurrent.futures.as_completed(pending):
                results.append(future.result())
        summary = dict(status=STATUS, execution_policy=plan['execution_policy'], profiles=plan['profiles'],
                       profile_tensor_counts=plan['profile_tensor_counts'], tensors=len(results),
                       tensor_bytes=sum(row['actual_bytes'] for row in results), totals=original.totals,
                       selected_plan_sha256=domain_sha(plan), reference_executed=False, dut_executed=False)
        validate_summary(summary, plan)
        original.write_json(out / 'SUMMARY.json', summary)
        return summary
    except BaseException as error:
        original.stop.set()
        original.write_json(out / 'FAILURE.json', dict(status='FAIL_ACQUISITION_PRESERVE_PARTIALS_NO_RETRY',
                            error=type(error).__name__ + ': ' + str(error), totals=original.totals))
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binding', type=P, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    need(args.execute and args.binding.is_absolute() and args.binding == args.binding.resolve()
         and not args.binding.is_symlink() and sha(args.binding) == args.sha256,
         'explicit independently pinned selected acquisition binding')
    run(json.loads(args.binding.read_text()))


if __name__ == '__main__':
    main()
