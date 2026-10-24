"""Prepare a bounded frame-routing fullblock source assembly; never execute it.

Use python -I -S -B. Read only the fixed 549-file source/metadata receipt and
pinned source-package files. All checks finish before fresh output creation.
Never open external runtime, Git packs, frozen payloads, or old run outputs.
This metadata-only builder does not preflight, import, or authorize a DUT.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

OLD_TOP_PIN = {'bytes': 113576, 'sha256': '4e5496a21b3ecd2b99c0022c1e99bb1666eafb284c84e91b525fc0e1c89c2889'}
OLD_RECEIPT_PIN = {'bytes': 97765, 'sha256': '29e1b5c9cde3a6c9d0a66e4752e2ffc2d87e5ad2cf1d1a1f76a239a501f646ef'}
OLD_RUNTIME_PIN = {'bytes': 379561, 'sha256': 'd5ab1421b3f1f5ff3e7e68c7586052ad892cfcc01f607e2be33a1540da905786'}
BINDING = 'source/work/qwen2_fixed93_fullblock_binding/FROZEN_BINDING.json'
TOP = 'SOURCE_MANIFEST.json'
PRODUCTION = 'PRODUCTION_SOURCE_MANIFEST.json'
RUNTIME = 'RUNTIME_PINS.json'
RECEIPT = 'ASSEMBLY_RECEIPT.json'
MAX_SMALL_FILE = 2 * 1024 * 1024
MAX_OUTPUT = 9 * 1024 * 1024
MAX_RECEIPT = 256 * 1024
PACKAGE_CAP = 1024 * 1024
PACKAGE_MANIFEST = 'SOURCE_MANIFEST.json'
PACKAGE_SCHEMA = 'fixed93-fullblock-frame-routing-package-v1'
CURRENT_CONTRACT = 'contract/FRAME_ROUTING_FULLBLOCK.json'
POLICY = 'contract/FRAME_ROUTING_POLICY.json'
POLICY_ID = 'source-attested-owner-frame-routing-v1'
OBSERVATION_MANIFEST = 'observation/SOURCE_MANIFEST.json'
OBSERVATION_FILES = ('__init__.py', 'cold_tests.py', 'event_stream.py', 'fullblock_attention.py', 'source_guard.py')
RECIPE = 'integration/runtime_support/recipe.py'
OLD_CI = 'support/candidates/host93_ci_recovery/ci_support_v3.py'
NEW_CI = 'supervision/ci_support_v3_long.py'
OLD_CI_PINS = 'support/candidates/host93_ci_recovery/SUPPORT_PINS.json'
NEW_CI_PINS = 'supervision/SUPPORT_PINS.json'
FROZEN_LAYOUT = 'FROZEN_EXTERNAL_LAYOUT.json'
FROZEN_COPIES = 'contract/FROZEN_DATA_COPIES.json'
BUDGET_STATUS = 'REVIEWED_FIXED93_FULLBLOCK_BUDGET'
DOMAINS = (('source', 'source_sha256', 'source_bytes', 306),
           ('selected', 'selected_source_sha256', 'selected_source_bytes', 9),
           ('support', 'support_sha256', 'support_bytes', 6))
NUMERIC_DELTA = {
    'inner_wall_seconds': (6585, 43185),
    'outer_wall_seconds': (6600, 43200),
    'sample_rows': (6601, 43201),
    'owned_reservation_components.other_fixed_files_and_samples': (23218176, 98174976),
    'output_bytes': (22103939876, 22178896676),
    'startup_available_bytes_required': (22640810788, 22715767588),
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


def overlay_name(value):
    local_name(value)
    need(not value.startswith(('source/', 'selected/', 'support/', 'work/')) and
         value not in (RUNTIME, TOP, PRODUCTION, RECEIPT, CURRENT_CONTRACT,
                       RECIPE, FROZEN_LAYOUT, FROZEN_COPIES) and
         Path(value).name != 'ADMISSION.json' and
         not Path(value).name.endswith('MANIFEST.json'),
         'overlay may not mutate source/runtime/recipe/layout/authority/generated manifests: ' + value)
    return value


def validate_successor_budget(old, new):
    expected = copy.deepcopy(old)
    for dotted, (before, after) in NUMERIC_DELTA.items():
        keys = dotted.split('.')
        target = expected
        for key in keys[:-1]:
            target = target[key]
        need(type(target[keys[-1]]) is int and target[keys[-1]] == before,
             'old budget numeric leaf mismatch: ' + dotted)
        target[keys[-1]] = after
    need(type(new.get('approval_scope')) is str and new['approval_scope'] and
         'ADMISSION' in new['approval_scope'], 'separate root ADMISSION scope required')
    expected['approval_scope'] = new['approval_scope']
    timing = new.get('timing_basis')
    need(type(timing) is dict and set(timing) == {
             'attention_cpu_seconds_conditional_range', 'independent_compute_vs_postseal_subdeadline',
             'outer_cleanup_seconds', 'outer_postflight_seconds',
             'prefix_tail_unmeasured_for_this_candidate', 'scope', 'work_includes'} and
         timing['independent_compute_vs_postseal_subdeadline'] is False and
         type(timing['outer_cleanup_seconds']) is int and timing['outer_cleanup_seconds'] == 5 and
         type(timing['outer_postflight_seconds']) is int and timing['outer_postflight_seconds'] == 10 and
         timing['prefix_tail_unmeasured_for_this_candidate'] is True and
         timing['scope'] == 'M2/M16 Attention subchain calibration, not fullblock time guarantee' and
         timing['work_includes'] == [
             'source/runtime/input verification', 'pc0..20 original model execution',
             'all source/input/ELF reseals', 'postseal official reference comparison'],
         'explicit whole-work timing scope required, not a completion guarantee')
    estimate = timing['attention_cpu_seconds_conditional_range']
    need(type(estimate) is list and len(estimate) == 2 and
         all(type(value) in (int, float) and 0 < value < 43200 for value in estimate) and
         estimate[0] <= estimate[1], 'bounded conditional calibration annotation required')
    expected['timing_basis'] = timing
    need(encoded(new) == encoded(expected),
         'only six duration/sample/storage leaves plus approval_scope and timing_basis may change')
    need(new['schema'] == 'fixed93-fullblock-resource-proposal-v1' and
         new['status'] == BUDGET_STATUS and new['actual_execution_authorized'] is False and
         new['automatic_retry'] is False and new['wholeblock_scope_required'] is True and
         'startup_only_scope_required' not in new and
         new['rss_bytes'] == 2147483648 and new['one_cpu'] is True and
         new['poll_seconds'] == 1 and new['progress_loop_interval'] == 131072 and
         new['file_bytes'] == 14412800198 and new['guaranteed_time_or_rss_fit'] is False,
         'unchanged fullblock limits and no time/RSS guarantee required')
    need(sum(new['owned_reservation_components'].values()) == new['output_bytes'] == 22178896676 and
         new['free_space_margin_bytes'] == 536870912 and
         new['output_bytes'] + new['free_space_margin_bytes'] ==
         new['startup_available_bytes_required'] == 22715767588 and
         (new['sample_rows'] * 2048 - 6601 * 2048) == 74956800,
         'whole-owned storage, unchanged sampler row cap and separate margin must balance')


def prepare_fullblock(predecessor, package, package_manifest_sha, output):
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and
         not sys.flags.optimize, 'use python -I -S -B without optimization')
    predecessor = canonical(predecessor, directory=True)
    package = canonical(package, directory=True)
    output = canonical(output)
    canonical(output.parent, directory=True)
    need(canonical(Path(__file__)) == package / 'prepare_fullblock.py',
         'the reviewed package builder must be the executing source')
    need(not output.exists() and not os.path.lexists(output), 'fresh nonexistent output required')
    need(not any(overlap(a, b) for a, b in ((predecessor, package),
             (predecessor, output), (package, output))), 'source/package/output roots overlap')
    digest(package_manifest_sha)
    package_raw = read_small(package, PACKAGE_MANIFEST, limit=MAX_RECEIPT)
    need(pin(package_raw)['sha256'] == package_manifest_sha, 'explicit reviewed source package SHA mismatch')
    pm = parse(package_raw)
    need(pm['schema'] == PACKAGE_SCHEMA and pm['actual_authorized'] is False and
         pm.get('builder_executed', False) is False and
         pm.get('materialization_executed', False) is False and
         pm.get('actual_execution_authorized', False) is False,
         'source package cannot contain execution authority')
    need(pm['base'] == {'manifest': OLD_TOP_PIN, 'receipt': OLD_RECEIPT_PIN},
         'exact 0300 source manifest and receipt package binding required')
    package_files = pm['files']
    overlay = pm['overlay_files']
    before_pins = pm['before_pins']
    need(type(overlay) is list and 0 < len(overlay) <= 128 and
         all(type(name) is str for name in overlay) and len(set(overlay)) == len(overlay),
         'bounded unique overlay target list required')
    overlay = set(overlay_name(name) for name in overlay)
    need({'BUDGET_PROPOSAL.json', POLICY, NEW_CI, NEW_CI_PINS} <= overlay and
         type(before_pins) is dict and set(before_pins) == overlay,
         'complete policy/budget overlay and before pin map required')
    need(type(package_files) is dict and 1 <= len(package_files) <= 256 and
         'prepare_fullblock.py' in package_files and PACKAGE_MANIFEST not in package_files and
         {name for name in package_files if name.startswith('overlay/')} ==
         {'overlay/' + name for name in overlay}, 'complete bounded source-package relative inventory required')
    for name, value in package_files.items():
        relative(name)
        spec(value, MAX_SMALL_FILE)
    need(sum(value['bytes'] for value in package_files.values()) <= PACKAGE_CAP,
         'source package exceeds 1 MiB')
    package_content = {name: read_small(package, name, value)
                       for name, value in package_files.items()}
    package_found = set()
    for index, path in enumerate(package.rglob('*')):
        need(index < 1024, 'bounded package filesystem inventory exceeded')
        info = path.lstat()
        need(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), 'package alias/special file')
        if stat.S_ISREG(info.st_mode):
            need(info.st_nlink == 1, 'package hardlink forbidden')
            package_found.add(str(path.relative_to(package)))
    need(package_found == set(package_files) | {PACKAGE_MANIFEST},
         'undeclared or missing source-package file')
    receipt_raw = read_small(predecessor, RECEIPT, OLD_RECEIPT_PIN, MAX_RECEIPT)
    old_receipt = parse(receipt_raw)
    old_files = old_receipt['files']
    need(type(old_files) is dict and len(old_files) == old_receipt['files_excluding_this_receipt'] == 549,
         'exact 549-object predecessor content inventory required')
    need(old_receipt['source_manifest'] == old_files[TOP] == OLD_TOP_PIN and
         old_files[RUNTIME] == OLD_RUNTIME_PIN, 'receipt/top/runtime identity mismatch')
    for name, value in old_files.items():
        local_name(name)
        spec(value, MAX_SMALL_FILE)
    need(sum(value['bytes'] for value in old_files.values()) ==
         old_receipt['bytes_excluding_this_receipt'] == 8729920, 'fixed predecessor total changed')
    content = {name: read_small(predecessor, name, value) for name, value in old_files.items()}
    old_top, old_production = parse(content[TOP]), parse(content[PRODUCTION])
    manifest_pair(old_top, old_production)
    sources = source_map(old_top)
    need(source_map(old_production) == sources and len(old_top['preparation_files']) == 227,
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
    layout = parse(content[FROZEN_LAYOUT])
    need(layout['read_only'] is True and layout['copy_payloads'] is False and len(layout['files']) == 76,
         '76-file readonly external frozen layout required')
    external = [absolute_text(p) for p in layout['roots'].values()]
    external += [absolute_text(runtime['git_environment']['GIT_DIR']),
                 absolute_text(runtime['git_profile_root'])]
    need(all(not overlap(output, p) for p in external), 'output overlaps external runtime/frozen root')
    for name in sorted(overlay):
        previous = before_pins[name]
        need(previous is None or spec(previous, MAX_SMALL_FILE), 'old pin or null required')
        need(previous == old_files.get(name), 'overlay before pin mismatch: ' + name)
        content[name] = package_content['overlay/' + name]
    old_ceiling = b'SHARED_SECONDS = 6600\n'
    new_ceiling = b'SHARED_SECONDS = 43200\n'
    need(content[OLD_CI].count(old_ceiling) == 1 and
         content[NEW_CI] == content[OLD_CI].replace(old_ceiling, new_ceiling, 1) and
         content[NEW_CI].replace(new_ceiling, old_ceiling, 1) == content[OLD_CI] and
         content[NEW_CI_PINS] == content[OLD_CI_PINS],
         'long coordinator must be the exact one-literal derivative with unchanged sibling pins')
    need(content[RUNTIME] == read_small(predecessor, RUNTIME, OLD_RUNTIME_PIN),
         'runtime pins changed during preparation')
    old_budget = parse(read_small(predecessor, 'BUDGET_PROPOSAL.json', old_files['BUDGET_PROPOSAL.json']))
    budget = parse(content['BUDGET_PROPOSAL.json'])
    validate_successor_budget(old_budget, budget)
    policy = parse(content[POLICY])
    need(policy['policy_id'] == POLICY_ID and policy['actual_execution_authorized'] is False and
         policy['entrypoint'] == 'integration/runner.py' and
         policy['execution_scope'] == 'M128_SOFTWARE_PUBLIC21_FULLBLOCK' and
         policy['fullblock_qualification_inherited'] is False,
         'explicit source-attested frame-routing policy scope required')
    policy_files = policy['module_files']
    need(type(policy_files) is dict and set(policy_files) == {
             'capture/CODEC_PINS.json', 'capture/anchors.json',
             'capture/wholeblock.py', 'observation/fullblock_attention.py'},
         'canonical four-file frame-routing policy closure required')
    for name, value in policy_files.items():
        need(spec(value, MAX_SMALL_FILE) == pin(content[name]), 'policy source identity mismatch: ' + name)
    policy_binding = dict(path=POLICY, **pin(content[POLICY]), policy_id=POLICY_ID)
    observation_names = {name for name in content if name.startswith('observation/') and name.endswith('.py')}
    need(observation_names == {'observation/' + name for name in OBSERVATION_FILES},
         'exact five current observation Python sources required')
    observation = copy.deepcopy(parse(content[OBSERVATION_MANIFEST]))
    observation.update(schema='fixed93-fullblock-frame-routing-observation-source-plan-v1',
        source_bytes={name: len(content['observation/' + name]) for name in OBSERVATION_FILES},
        source_sha256={name: pin(content['observation/' + name])['sha256'] for name in OBSERVATION_FILES},
        observation_integrity_policy=policy_binding, actual_authorized=False,
        fullblock_executed=False, native_executed=False, numerical_acceptance=False,
        old_cold_evidence_is_historical=True, old_pass_inherited=False,
        status='SOURCE_PREPARED_REVIEW_SEPARATE')
    content[OBSERVATION_MANIFEST] = encoded(observation)
    need(CURRENT_CONTRACT not in old_files, 'new frame-routing contract namespace collision')
    contract = dict(schema='fixed93-fullblock-frame-routing-contract-v1',
        observation_integrity_policy=policy_binding, source_package=pin(package_raw),
        predecessor_manifest=OLD_TOP_PIN, predecessor_receipt=OLD_RECEIPT_PIN,
        runtime_pin=OLD_RUNTIME_PIN, current_budget=pin(content['BUDGET_PROPOSAL.json']),
        current_budget_status=BUDGET_STATUS, full_entry='integration/runner.py', startup_only=False,
        fullblock_runner=pin(content['integration/runner.py']), full_worker=pin(content['supervision/worker.py']),
        full_authority_schema='fixed93-fullblock-admission-v1',
        full_authority_status='REVIEWED_FIXED93_M128_PUBLIC21_ACTUAL',
        evidence_contract=old_top['evidence_contract'],
        overlay_files={name: dict(before=before_pins[name], after=pin(content[name])) for name in sorted(overlay)},
        numeric_budget_delta={name: dict(before=a, after=b) for name, (a, b) in NUMERIC_DELTA.items()},
        nonnumeric_budget_delta=['approval_scope', 'timing_basis'],
        unchanged_source_objects=321, unchanged_recipe_pin=old_files[RECIPE],
        unchanged_binding_pin=old_files[BINDING], unchanged_runtime_objects=1638,
        external_frozen_files=76, unchanged_external_layout_pin=old_files[FROZEN_LAYOUT],
        capture_nested_manifest_is_historical=True,
        observation_nested_manifest=pin(content[OBSERVATION_MANIFEST]),
        old_pass_inherited=False, prior_qualification_inherited=False,
        independent_combined_review_pending=True, builder_is_metadata_only=True,
        preflight_executed=False, actual_authorized=False, actual_execution_authorized=False,
        root_admission_required=True, budget_enum_is_not_authority=True,
        completion_time_guaranteed=False, fullblock_acceptance=False)
    content[CURRENT_CONTRACT] = encoded(contract)
    top = copy.deepcopy(old_top)
    need('observation_integrity_policy' not in top and 'frame_routing_fullblock_preparation' not in top,
         'successor metadata collision')
    top['observation_integrity_policy'] = policy_binding
    top['frame_routing_fullblock_preparation'] = dict(
        current_successor_contract=CURRENT_CONTRACT, source_package=pin(package_raw),
        predecessor_manifest=OLD_TOP_PIN, current_budget=pin(content['BUDGET_PROPOSAL.json']),
        current_budget_status=BUDGET_STATUS, full_entry='integration/runner.py', startup_only=False,
        independent_combined_review_pending=True, root_admission_required=True,
        historical_pass_inherited=False, fixed_git_runtime_unchanged=True,
        actual_execution_authorized=False)
    prep_names = set(old_production['preparation_files']) | overlay | {CURRENT_CONTRACT, OBSERVATION_MANIFEST}
    need(TOP not in prep_names and PRODUCTION not in prep_names, 'noncircular preparation manifest required')
    prep = {name: pin(content[name]) for name in sorted(prep_names)}
    top['preparation_files'] = prep
    content[PRODUCTION] = encoded(top)
    top['preparation_files'] = dict(prep, **{PRODUCTION: pin(content[PRODUCTION])})
    content[TOP] = encoded(top)
    manifest_pair(top, parse(content[PRODUCTION]))
    need(source_map(top) == sources and all(pin(content[name]) == value for name, value in sources.items()),
         'all 321 current source/selected/support bytes must stay unchanged')
    retained = (RECIPE, BINDING, RUNTIME, FROZEN_LAYOUT, FROZEN_COPIES, 'capture/SOURCE_MANIFEST.json')
    need(all(pin(content[name]) == old_files[name] for name in retained),
         'recipe/binding/runtime/layout or historical capture manifest changed')
    changed = overlay | {OBSERVATION_MANIFEST, TOP, PRODUCTION}
    need(all(pin(content[name]) == value for name, value in old_files.items() if name not in changed),
         'unrelated predecessor metadata changed')
    need(set(content) == set(old_files) | overlay | {CURRENT_CONTRACT}, 'unknown output inventory')
    total = sum(map(len, content.values()))
    need(total + MAX_RECEIPT <= MAX_OUTPUT, 'assembly plus receipt reserve exceeds 9 MiB')
    for name, raw in content.items():
        need(len(raw) <= MAX_SMALL_FILE, 'small source/metadata cap exceeded')
        if name.endswith('.py'):
            ast.parse(raw, filename=name)
            compile(raw, name, 'exec', dont_inherit=True, optimize=0)
    new_receipt = dict(schema='fixed93-fullblock-frame-routing-source-assembly-v1',
        status='SOURCE_FILES_PREPARED_PENDING_SEPARATE_PREFLIGHT_AND_REVIEW',
        predecessor_manifest=OLD_TOP_PIN, predecessor_receipt=OLD_RECEIPT_PIN,
        source_package=pin(package_raw), source_manifest=pin(content[TOP]),
        production_source_manifest=pin(content[PRODUCTION]), runtime_pin=OLD_RUNTIME_PIN,
        observation_integrity_policy=policy_binding,
        assembly_objects=321, source_files=306, selected_files=9, support_files=6,
        preparation_files=len(top['preparation_files']), files_excluding_this_receipt=len(content),
        bytes_excluding_this_receipt=total, logical_file_bytes_cap=MAX_OUTPUT,
        receipt_reserve_bytes=MAX_RECEIPT,
        files={name: pin(raw) for name, raw in sorted(content.items())},
        external_frozen_files_declared=76, payloads_opened=0, payloads_copied=0,
        runtime_payloads_hashed=0, git_commands_executed=0, profile_verifier_executed=False,
        builder_is_metadata_only=True, preflight_executed=False, DUT_imported=False, native_executed=False,
        actual_admission=False, actual_authorized=False, actual_execution_authorized=False,
        fullblock_acceptance=False, independent_source_cold_review_pending=True,
        budget_enum_is_not_authority=True, old_pass_inherited=False,
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
    need(found == set(content) | {RECEIPT} and not (output / 'work').exists() and
         not (output / 'ADMISSION.json').exists(), 'output inventory or no-authority boundary failed')
    return dict(output=str(output), source_manifest=pin(content[TOP]),
        production_source_manifest=pin(content[PRODUCTION]), receipt=pin(new_receipt_raw),
        bytes_including_receipt=total + len(new_receipt_raw), files_including_receipt=len(found),
        preflight_executed=False, actual_authorized=False, status=new_receipt['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('predecessor', 'package', 'package-manifest-sha', 'output'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_fullblock(args.predecessor, args.package,
          args.package_manifest_sha, args.output), sort_keys=True))
