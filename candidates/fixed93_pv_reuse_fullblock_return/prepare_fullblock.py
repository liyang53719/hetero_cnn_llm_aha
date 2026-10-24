"""Prepare a bounded fullblock source assembly; never execute or preflight it.

Use python -I -S -B. All source/budget/manifest checks finish before creating
fresh output. Read only the fixed 547-file predecessor receipt inventory and
the independently pinned tiny overlay package. Do not open external runtime,
Git packs, frozen payloads, old runs, or execute any imported candidate code.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import sys


OLD_TOP_PIN = {'bytes': 112503, 'sha256': 'cc82716a4801c111225c1dc6cb4435ca3120482f4e21ebd01fd1d3a6f1e7b90b'}
OLD_RECEIPT_PIN = {'bytes': 98784, 'sha256': '9254099e334902bf01f173f978ef244d5c574a219d023060bc0fe6794110cf42'}
OLD_RUNTIME_PIN = {'bytes': 379561, 'sha256': 'd5ab1421b3f1f5ff3e7e68c7586052ad892cfcc01f607e2be33a1540da905786'}
SNAPSHOT_RECEIPT = 'SNAPSHOT_RECEIPT.json'
CONTRACT = 'contract/GIT_RUNTIME_ISOLATION.json'
BINDING = 'source/work/qwen2_fixed93_fullblock_binding/FROZEN_BINDING.json'
TOP = 'SOURCE_MANIFEST.json'
PRODUCTION = 'PRODUCTION_SOURCE_MANIFEST.json'
RUNTIME = 'RUNTIME_PINS.json'
RECEIPT = 'ASSEMBLY_RECEIPT.json'
MAX_SMALL_FILE = 2 * 1024 * 1024
MAX_OUTPUT = 9 * 1024 * 1024
MAX_RECEIPT = 256 * 1024
DOMAINS = (('source', 'source_sha256', 'source_bytes', 306),
           ('selected', 'selected_source_sha256', 'selected_source_bytes', 9),
           ('support', 'support_sha256', 'support_bytes', 6))
OVERLAY_NAMES = frozenset(('BUDGET_PROPOSAL.json', 'admission.py', 'integration/interface.py', 'integration/runtime_support/native_artifact.py', 'contract/PV_REUSE_EXACT_CAPACITY.json'))
PACKAGE_MANIFEST = 'SOURCE_MANIFEST.json'
PACKAGE_CAP = 1024 * 1024
CURRENT_CONTRACT = 'contract/FULLBLOCK_RETURN_LOADER_CAPACITY.json'
CAPACITY_CONTRACT = 'contract/PV_REUSE_EXACT_CAPACITY.json'
BUDGET_STATUS = 'REVIEWED_FIXED93_FULLBLOCK_BUDGET'
CAPACITY_RECEIPT_PIN = {'bytes': 1861, 'sha256': '954d13dc365bbb42507673f31cd608f866ee96f401031d1b4775a9ab124ccf71'}
LOADER_ACTUAL_PIN = {'bytes': 7120, 'sha256': '69ef9b3f2955cba917dab9db71a3bf0f6883ba55c81adba56d66d9686f3592dc'}
NUMERIC_DELTA = {
    'attention_trace_limits.codec_limits.max_raw': (4913071232, 4281892568),
    'attention_trace_limits.codec_limits.max_metadata': (128, 116),
    'attention_trace_limits.codec_limits.max_output': (8188726982, 7375567454),
    'owned_reservation_components.attention_stream': (8188726982, 7375567454),
    'output_bytes': (22917099404, 22103939876),
    'startup_available_bytes_required': (23453970316, 22640810788),
}

def need(ok, message):
    if not ok:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def digest(value):
    need(type(value) is str and len(value) == 64 and
         all(c in '0123456789abcdef' for c in value), 'canonical SHA256 required')
    return value


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def spec(value, limit=None):
    need(type(value) is dict and set(value) == {'bytes', 'sha256'} and
         type(value['bytes']) is int and value['bytes'] >= 0, 'exact byte/SHA pin required')
    digest(value['sha256'])
    need(limit is None or value['bytes'] <= limit, 'pin exceeds byte cap')
    return value


def relative(value):
    need(type(value) is str and value and not Path(value).is_absolute() and
         str(Path(value)) == value and '\\' not in value and
         all(p not in ('', '.', '..') for p in value.split('/')), 'canonical relative path required')
    return value


def local_name(value):
    relative(value)
    need(value not in (RECEIPT, 'ADMISSION.json') and
         not value.startswith(('work/', '.git/', 'git/', 'profile/')) and
         (not value.startswith('source/work/') or value == BINDING),
         'run, payload, receipt or Git dependency cannot be copied: ' + value)
    return value


def absolute_text(value):
    need(type(value) is str and Path(value).is_absolute() and str(Path(value)) == value and
         '..' not in Path(value).parts and '\\' not in value, 'canonical absolute spelling required')
    return Path(value)


def canonical(value, directory=False):
    path = absolute_text(str(value))
    need(path.resolve() == path and not any(p.is_symlink() for p in (path, *path.parents)),
         'symlink or alias forbidden: ' + str(path))
    if directory:
        need(stat.S_ISDIR(path.lstat().st_mode), 'existing ordinary directory required: ' + str(path))
    return path


def overlap(a, b):
    return a == b or a in b.parents or b in a.parents


def stamp(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def chain(path):
    """Parent identities, not directory mtimes changed by our own fresh writes."""
    result = []
    for parent in reversed(path.parents):
        value = parent.lstat()
        need(stat.S_ISDIR(value.st_mode), 'non-directory or symlink parent')
        result.append((str(parent), value.st_dev, value.st_ino, value.st_mode))
    return tuple(result)


def read_small(root, name, expected=None, limit=MAX_SMALL_FILE):
    need(0 <= limit <= MAX_SMALL_FILE, 'small-read cap cannot be enlarged')
    path = canonical(root / relative(name))
    parents, before = chain(path), path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit,
         'bounded single-link regular file required: ' + str(path))
    if expected is not None:
        spec(expected, limit)
        need(before.st_size == expected['bytes'], 'source size mismatch: ' + name)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        need(stamp(before) == stamp(os.fstat(stream.fileno())), 'source changed before open')
        raw = stream.read(limit + 1)
        observed = pin(raw)
        after = os.fstat(stream.fileno())
    need(len(raw) <= limit and stamp(before) == stamp(after) == stamp(path.lstat()) and
         parents == chain(path), 'source changed during same-FD read: ' + name)
    need(expected is None or observed == expected, 'source byte/SHA mismatch: ' + name)
    return raw


def write_new(root, name, raw):
    need(len(raw) <= MAX_SMALL_FILE, 'output file exceeds small-file cap')
    path = root / relative(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    canonical(path.parent, directory=True)
    parents = chain(path)
    with path.open('xb') as stream:
        need(stream.write(raw) == len(raw), 'short fresh-output write')
        stream.flush()
        current = os.fstat(stream.fileno())
        need(stat.S_ISREG(current.st_mode) and current.st_nlink == 1 and
             current.st_size == len(raw) and stamp(current) == stamp(path.lstat()) and
             parents == chain(path), 'fresh output alias or unstable write')
    read_small(root, name, pin(raw))


def source_map(manifest):
    result = {}
    for directory, hkey, skey, count in DOMAINS:
        hashes, sizes = manifest[hkey], manifest[skey]
        need(type(hashes) is dict and type(sizes) is dict and
             hashes.keys() == sizes.keys() and len(hashes) == count and
             manifest[directory + '_count'] == count, 'exact source-domain count required')
        for name, value in hashes.items():
            logical = local_name(directory + '/' + relative(name))
            need(not logical.startswith('source/work/'), 'payload is not source')
            result[logical] = spec({'bytes': sizes[name], 'sha256': value}, MAX_SMALL_FILE)
    need(len(result) == 321, '321 distinct source/selected/support objects required')
    return result


def manifest_pair(top, production):
    need(type(top['preparation_files']) is dict and type(production['preparation_files']) is dict,
         'preparation maps required')
    need(TOP not in top['preparation_files'] and TOP not in production['preparation_files'] and
         PRODUCTION not in production['preparation_files'], 'self-referential manifest forbidden')
    need({k: v for k, v in top.items() if k != 'preparation_files'} ==
         {k: v for k, v in production.items() if k != 'preparation_files'} and
         {k: v for k, v in top['preparation_files'].items() if k != PRODUCTION} ==
         production['preparation_files'], 'top/production closure disagreement')


def validate_successor_budget(old, new, meta, content):
    expected = copy.deepcopy(old)
    for dotted, (before, after) in NUMERIC_DELTA.items():
        keys = dotted.split('.')
        target = expected
        for key in keys[:-1]:
            target = target[key]
        need(type(target[keys[-1]]) is int and target[keys[-1]] == before,
             'old budget numeric leaf mismatch: ' + dotted)
        target[keys[-1]] = after
    expected['status'] = BUDGET_STATUS
    need(type(new.get('approval_scope')) is str and new['approval_scope'] and
         'ADMISSION' in new['approval_scope'], 'explicit pending separate authority scope required')
    expected['approval_scope'] = new['approval_scope']
    expected['capacity_source_binding'] = dict(path=CAPACITY_CONTRACT, **pin(content[CAPACITY_CONTRACT]))
    need(new == expected, 'only six exact numeric leaves and three declared provenance/interface fields may change')
    need(meta['numeric_budget_delta'] == {k: dict(before=a, after=b) for k, (a, b) in NUMERIC_DELTA.items()} and
         meta['nonnumeric_budget_delta'] == ['status', 'approval_scope', 'capacity_source_binding'],
         'budget delta declaration differs')
    need(new['schema'] == 'fixed93-fullblock-resource-proposal-v1' and
         new['status'] == BUDGET_STATUS and new['actual_execution_authorized'] is False and
         new['automatic_retry'] is False and new['wholeblock_scope_required'] is True and
         'startup_only_scope_required' not in new and
         new['inner_wall_seconds'] == 6585 and new['outer_wall_seconds'] == 6600 and
         new['rss_bytes'] == 2147483648 and new['one_cpu'] is True and
         new['sample_rows'] == 6601 and new['file_bytes'] == 14412800198,
         'unchanged fullblock budget interface and limits required; status is not authority')
    need(sum(new['owned_reservation_components'].values()) == new['output_bytes'] == 22103939876 and
         new['free_space_margin_bytes'] == 536870912 and
         new['output_bytes'] + new['free_space_margin_bytes'] == new['startup_available_bytes_required'] == 22640810788,
         'whole-owned fullblock storage and separate margin must balance')
    cap = parse(content[CAPACITY_CONTRACT])
    need(cap['schema'] == 'fixed93-pv-reuse-exact-capacity-source-v1' and
         cap['actual_authorized'] is False and cap['fullblock_qualified'] is False and
         cap['new_max_raw'] == 4281892568 and cap['new_max_records'] == 15165072 and
         cap['new_max_metadata'] == 116 and cap['new_max_output'] == 7375567454 and
         cap['preserved_raw_slack'] == 946430 and cap['preserved_record_slack'] == 135 and
         cap['metadata_cap_headroom'] == 14,
         'exact bounded source-success capacity qualification required')


def prepare_fullblock(predecessor, package, package_manifest_sha, output):
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and
         not sys.flags.optimize, 'use python -I -S -B without optimization')
    predecessor = canonical(predecessor, directory=True)
    package = canonical(package, directory=True)
    output = canonical(output)
    canonical(output.parent, directory=True)
    need(not output.exists() and not os.path.lexists(output), 'fresh nonexistent output required')
    need(not any(overlap(a, b) for a, b in ((predecessor, package),
             (predecessor, output), (package, output))), 'source/package/output roots overlap')
    digest(package_manifest_sha)
    package_raw = read_small(package, PACKAGE_MANIFEST, limit=MAX_RECEIPT)
    need(pin(package_raw)['sha256'] == package_manifest_sha, 'explicit reviewed source package SHA mismatch')
    pm = parse(package_raw)
    need(pm['schema'] == 'fixed93-pv-reuse-fullblock-return-source-package-v1' and
         pm['actual_authorized'] is False and pm['builder_executed'] is False,
         'source package cannot contain execution authority')
    package_files = pm['files']
    expected_package = {'prepare_fullblock.py', 'synthetic_cold.py', 'README.md', 'DELTA.diff',
                        'OVERLAY_PINS.json', 'COLD_RESULT.json'} | {'overlay/' + name for name in OVERLAY_NAMES}
    need(type(package_files) is dict and set(package_files) == expected_package,
         'exact bounded source package inventory required')
    need(sum(spec(value, MAX_SMALL_FILE)['bytes'] for value in package_files.values()) <= PACKAGE_CAP,
         'source package exceeds 1 MiB')
    package_content = {name: read_small(package, name, value)
                       for name, value in package_files.items()}
    meta = parse(package_content['OVERLAY_PINS.json'])
    need(meta['schema'] == 'fixed93-pv-reuse-fullblock-return-overlay-v1' and
         meta['base_manifest'] == OLD_TOP_PIN and meta['base_receipt'] == OLD_RECEIPT_PIN and
         meta['base_runtime'] == OLD_RUNTIME_PIN and set(meta['overlay_files']) == OVERLAY_NAMES,
         'overlay/base immutable binding mismatch')
    receipt_raw = read_small(predecessor, RECEIPT, OLD_RECEIPT_PIN, MAX_RECEIPT)
    old_receipt = parse(receipt_raw)
    old_files = old_receipt['files']
    need(type(old_files) is dict and len(old_files) == old_receipt['files_excluding_this_receipt'] == 547,
         'exact 547-object predecessor content inventory required')
    need(old_receipt['source_manifest'] == old_files[TOP] == OLD_TOP_PIN and
         old_files[RUNTIME] == OLD_RUNTIME_PIN, 'receipt/top/runtime identity mismatch')
    for name, value in old_files.items():
        local_name(name)
        spec(value, MAX_SMALL_FILE)
    need(sum(value['bytes'] for value in old_files.values()) ==
         old_receipt['bytes_excluding_this_receipt'] == 8716507,
         'fixed predecessor total changed')
    content = {name: read_small(predecessor, name, value) for name, value in old_files.items()}
    old_top, old_production = parse(content[TOP]), parse(content[PRODUCTION])
    manifest_pair(old_top, old_production)
    sources = source_map(old_top)
    need(source_map(old_production) == sources and len(old_top['preparation_files']) == 225,
         'fixed source/preparation inventories required')
    expected = dict(sources)
    for name, value in old_top['preparation_files'].items():
        local_name(name)
        need(name not in expected, 'preparation/source overlap')
        expected[name] = value
    expected[TOP] = OLD_TOP_PIN
    need(expected == old_files and old_receipt['production_source_manifest'] == pin(content[PRODUCTION]),
         'receipt must exactly close predecessor manifests')
    runtime = parse(content[RUNTIME])
    need(len(runtime['files']) == 1638, 'fixed 1638-object runtime metadata inventory required')
    need(old_top.get('startup_only') is False and
         old_top.get('candidate_identity') == 'fixed93-pv-normalization-reuse-source-candidate-v1',
         'fullblock PV-reuse source identity required')
    need(meta['current_full_entry'] == 'integration/runner.py' and
         meta['recipe_pin'] == old_files['integration/runtime_support/recipe.py'],
         'unchanged full runner and frozen-pair recipe required')
    for name, expected_pin in meta['retained_files'].items():
        need(old_files.get(name) == expected_pin and pin(content[name]) == expected_pin,
             'retained fullblock source pin mismatch: ' + name)
    layout = parse(content['FROZEN_EXTERNAL_LAYOUT.json'])
    need(layout['read_only'] is True and layout['copy_payloads'] is False and len(layout['files']) == 76,
         '76-file readonly external frozen layout required')
    external = [absolute_text(p) for p in layout['roots'].values()]
    external += [absolute_text(runtime['git_environment']['GIT_DIR']),
                 absolute_text(runtime['git_profile_root'])]
    need(all(not overlap(output, p) for p in external), 'output overlaps external runtime/frozen root')
    for name, change in meta['overlay_files'].items():
        need(not name.startswith(('source/', 'selected/', 'support/', 'work/')) and
             name not in (RUNTIME, TOP, PRODUCTION, RECEIPT, 'ADMISSION.json'),
             'overlay may not mutate frozen source/runtime/authority')
        need(change['before'] == old_files.get(name), 'overlay before pin mismatch: ' + name)
        raw = package_content['overlay/' + name]
        need(pin(raw) == change['after'], 'overlay after pin mismatch: ' + name)
        content[name] = raw
    need(content[RUNTIME] == read_small(predecessor, RUNTIME, OLD_RUNTIME_PIN),
         'runtime pins changed during preparation')
    budget = parse(content['BUDGET_PROPOSAL.json'])
    old_budget = parse(read_small(predecessor, 'BUDGET_PROPOSAL.json', old_files['BUDGET_PROPOSAL.json']))
    validate_successor_budget(old_budget, budget, meta, content)
    cap = parse(content[CAPACITY_CONTRACT])
    need({k: meta['loader_actual_review'][k] for k in ('bytes', 'sha256')} == LOADER_ACTUAL_PIN,
         'limited loader actual evidence pin changed')
    need(cap['review']['DECISION.json'] == CAPACITY_RECEIPT_PIN,
         'exact capacity delta review pin changed')
    cold = parse(package_content['COLD_RESULT.json'])
    need(cold.get('status') == 'PASS_SYNTHETIC_FULLBLOCK_SOURCE_ONLY' and
         cold.get('builder_executed') is False and cold.get('preflight_executed') is False and
         cold.get('native_executed') is False and cold.get('actual_authorized') is False,
         'new synthetic source-only cold report required')
    contract = dict(schema='fixed93-pv-reuse-fullblock-return-loader-capacity-v1',
        source_package=pin(package_raw), predecessor_manifest=OLD_TOP_PIN,
        predecessor_receipt=OLD_RECEIPT_PIN, runtime_pin=OLD_RUNTIME_PIN,
        full_entry='integration/runner.py', startup_only=False,
        fullblock_runner=pin(content['integration/runner.py']),
        full_worker=pin(content['supervision/worker.py']),
        full_authority_schema='fixed93-fullblock-admission-v1',
        full_authority_status='REVIEWED_FIXED93_M128_PUBLIC21_ACTUAL',
        evidence_contract=old_top['evidence_contract'],
        current_budget=pin(content['BUDGET_PROPOSAL.json']), current_budget_status=BUDGET_STATUS,
        current_capacity_contract=dict(path=CAPACITY_CONTRACT, **pin(content[CAPACITY_CONTRACT])),
        loader_source_manifest=meta['loader_source_manifest'],
        limited_loader_actual_evidence=meta['loader_actual_review'],
        limited_loader_pass_is_not_fullblock_qualification=True,
        capacity_evidence=meta['capacity_evidence'],
        synthetic_cold=dict(package_path='COLD_RESULT.json', **pin(package_content['COLD_RESULT.json'])),
        numeric_budget_delta=meta['numeric_budget_delta'],
        nonnumeric_budget_delta=meta['nonnumeric_budget_delta'],
        overlay_files=meta['overlay_files'], unchanged_source_objects=321,
        unchanged_recipe_pin=meta['recipe_pin'], unchanged_runtime_objects=1638,
        external_frozen_files=76, current_runner=meta['current_runner'],
        current_runner_prefix=meta['current_runner_prefix'], current_runner_cleanup=meta['current_runner_cleanup'],
        historical_records_not_current_qualification=[
            'fullblock_return', 'full_return_1559', 'contract/GIT_RUNTIME_ISOLATION.json',
            'contract/PV_REUSE_CAPACITY.json', 'PREFIX_BINDING.json'],
        prior_qualification_inherited=False, independent_combined_review_pending=True,
        builder_is_metadata_only=True, preflight_executed=False, actual_authorized=False,
        actual_execution_authorized=False, root_admission_required=True,
        budget_enum_is_not_authority=True, fullblock_acceptance=False)
    content[CURRENT_CONTRACT] = encoded(contract)
    top = copy.deepcopy(old_top)
    # Prior lineage records are byte-equivalent JSON values, not current qualification.
    need('pv_reuse_fullblock_return_preparation' not in top, 'successor metadata collision')
    top['pv_reuse_fullblock_return_preparation'] = dict(
        current_successor_contract=CURRENT_CONTRACT,
        current_budget=pin(content['BUDGET_PROPOSAL.json']), current_budget_status=BUDGET_STATUS,
        full_entry='integration/runner.py', startup_only=False,
        independent_combined_review_pending=True, root_admission_required=True,
        historical_pass_inherited=False, fixed_git_runtime_unchanged=True,
        source_package=pin(package_raw), actual_execution_authorized=False)
    prep_names = (set(old_production['preparation_files']) |
                  (set(meta['overlay_files']) - set(sources)) | {CURRENT_CONTRACT})
    need(TOP not in prep_names and PRODUCTION not in prep_names, 'noncircular preparation manifest required')
    prep = {name: pin(content[name]) for name in sorted(prep_names)}
    top['preparation_files'] = prep
    content[PRODUCTION] = encoded(top)
    top['preparation_files'] = dict(prep, **{PRODUCTION: pin(content[PRODUCTION])})
    content[TOP] = encoded(top)
    manifest_pair(top, parse(content[PRODUCTION]))
    need(source_map(top) == sources and
         all(pin(content[name]) == value for name, value in sources.items()),
         'all 321 current PV reuse source/selected/support bytes must stay unchanged')
    changed = set(meta['overlay_files']) | {TOP, PRODUCTION}
    need(all(pin(content[name]) == value for name, value in old_files.items() if name not in changed),
         'unrelated predecessor metadata changed')
    need(set(content) == set(old_files) | {CAPACITY_CONTRACT, CURRENT_CONTRACT},
         'unknown output inventory')
    total = sum(map(len, content.values()))
    need(total + MAX_RECEIPT <= MAX_OUTPUT, 'assembly plus receipt reserve exceeds 9 MiB')
    for name, raw in content.items():
        need(len(raw) <= MAX_SMALL_FILE, 'small source/metadata cap exceeded')
        if name.endswith('.py'):
            ast.parse(raw, filename=name)
            compile(raw, name, 'exec', dont_inherit=True, optimize=0)
    new_receipt = dict(schema='fixed93-pv-reuse-fullblock-return-source-assembly-v1',
        status='SOURCE_FILES_PREPARED_PENDING_SEPARATE_PREFLIGHT_AND_REVIEW',
        predecessor_manifest=OLD_TOP_PIN, predecessor_receipt=OLD_RECEIPT_PIN,
        source_package=pin(package_raw), source_manifest=pin(content[TOP]),
        production_source_manifest=pin(content[PRODUCTION]), runtime_pin=OLD_RUNTIME_PIN,
        assembly_objects=321, source_files=306, selected_files=9, support_files=6,
        preparation_files=len(top['preparation_files']), files_excluding_this_receipt=len(content),
        bytes_excluding_this_receipt=total, logical_file_bytes_cap=MAX_OUTPUT,
        files={name: pin(raw) for name, raw in sorted(content.items())},
        external_frozen_files_declared=76, payloads_opened=0, payloads_copied=0,
        runtime_payloads_hashed=0, git_commands_executed=0, profile_verifier_executed=False,
        preflight_executed=False, DUT_imported=False, native_executed=False,
        actual_admission=False, actual_execution_authorized=False, fullblock_acceptance=False,
        independent_source_cold_review_pending=True, budget_enum_is_not_authority=True,
        historical_evidence_is_not_current_qualification=True, startup_only=False,
        full_entry='integration/runner.py', current_budget=pin(content['BUDGET_PROPOSAL.json']),
        current_budget_status=BUDGET_STATUS, current_successor_contract=CURRENT_CONTRACT,
        runtime_count=1638, source_cold_review_qualified=False)
    new_receipt_raw = encoded(new_receipt)
    need(len(new_receipt_raw) <= MAX_RECEIPT and total + len(new_receipt_raw) <= MAX_OUTPUT,
         'receipt/assembly output cap exceeded')
    output.mkdir()
    for name, raw in sorted(content.items()):
        write_new(output, name, raw)
    write_new(output, RECEIPT, new_receipt_raw)
    found = set()
    for path in output.rglob('*'):
        value = path.lstat()
        need(stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode), 'output alias/special file')
        if stat.S_ISREG(value.st_mode):
            need(value.st_nlink == 1, 'output hardlink forbidden')
            found.add(str(path.relative_to(output)))
    need(found == set(content) | {RECEIPT} and not (output/'work').exists() and
         not (output/'ADMISSION.json').exists(), 'output inventory or no-authority boundary failed')
    return dict(output=str(output), source_manifest=pin(content[TOP]),
        production_source_manifest=pin(content[PRODUCTION]), receipt=pin(new_receipt_raw),
        bytes_including_receipt=total+len(new_receipt_raw), files_including_receipt=len(found),
        preflight_executed=False, actual_authorized=False, status=new_receipt['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('predecessor', 'package', 'package-manifest-sha', 'output'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_fullblock(args.predecessor, args.package,
          args.package_manifest_sha, args.output), sort_keys=True))
