"""Prepare a bounded startup-only source assembly, never execute it.

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
OVERLAY_NAMES = frozenset(('BUDGET_PROPOSAL.json', 'PREFIX_BINDING.json', 'admission.py', 'assembly_preflight.py', 'fullblock_runtime.py', 'integration/attention_route_probe.py', 'integration/interface.py', 'integration/runtime_support/gates.py', 'integration/runtime_support/native_artifact.py', 'integration/startup_probe.py', 'supervision/cold.py', 'supervision/gate.py', 'supervision/launch.py', 'supervision/worker.py'))
PACKAGE_MANIFEST = 'SOURCE_MANIFEST.json'
PACKAGE_CAP = 1024 * 1024
STARTUP_CONTRACT = 'contract/PV_REUSE_STARTUP_SCOPE.json'

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


def prepare_probe(predecessor, package, package_manifest_sha, output):
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
    need(pm['schema'] == 'fixed93-pv-reuse-startup-source-package-v1' and
         pm['actual_authorized'] is False and pm['builder_executed'] is False,
         'source package cannot contain execution authority')
    package_files = pm['files']
    expected_package = {'prepare_probe.py', 'synthetic_cold.py', 'README.md', 'DELTA.diff',
                        'OVERLAY_PINS.json'} | {'overlay/' + name for name in OVERLAY_NAMES}
    need(type(package_files) is dict and set(package_files) == expected_package,
         'exact bounded source package inventory required')
    need(sum(spec(value, MAX_SMALL_FILE)['bytes'] for value in package_files.values()) <= PACKAGE_CAP,
         'source package exceeds 1 MiB')
    package_content = {name: read_small(package, name, value)
                       for name, value in package_files.items()}
    meta = parse(package_content['OVERLAY_PINS.json'])
    need(meta['schema'] == 'fixed93-pv-reuse-startup-overlay-v1' and
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
    need(budget['schema'] == 'fixed93-startup-probe-resource-v1' and
         budget['status'] == 'REVIEWED_FIXED93_STARTUP_PROBE_BUDGET' and
         budget['actual_execution_authorized'] is False and budget['automatic_retry'] is False and
         budget['startup_only_scope_required'] is True and budget['wholeblock_scope_required'] is False and
         budget['inner_wall_seconds'] == 30 and budget['outer_wall_seconds'] == 45 and
         budget['rss_bytes'] == 2147483648 and budget['one_cpu'] is True and budget['sample_rows'] == 46 and
         budget['output_bytes'] == 16777216 and budget['file_bytes'] == 8388608,
         'exact prepared bounded startup-only budget required; enum is not authority')
    need(sum(budget['owned_reservation_components'].values()) == budget['output_bytes'],
         '16 MiB whole-owned reservation must balance')
    startup = dict(startup_only=True, fullblock_authorized=False, M128_authorized=False,
                   entrypoint='integration/startup_probe.py', stop_before='first_x.advance_to_request')
    contract = dict(schema='fixed93-pv-reuse-startup-scope-v1', **startup,
        source_package=pin(package_raw), predecessor_manifest=OLD_TOP_PIN,
        predecessor_receipt=OLD_RECEIPT_PIN, runtime_pin=OLD_RUNTIME_PIN,
        overlay_files=meta['overlay_files'], unchanged_source_objects=321,
        unchanged_recipe_pin=meta['recipe_pin'], external_frozen_files=76,
        prior_qualification_inherited=False, independent_review_pending=True,
        builder_is_metadata_only=True, preflight_executed=False, actual_authorized=False)
    content[STARTUP_CONTRACT] = encoded(contract)
    top = copy.deepcopy(old_top)
    # Keep old fullblock records as clearly historical lineage, not active scope.
    lineage = top.setdefault('historical_parent_lineage', {})
    for name in ('fullblock_return', 'full_return_1559'):
        if name in top:
            need(name not in lineage, 'historical lineage collision')
            lineage[name] = top.pop(name)
    top.update(startup)
    top['startup_probe_preparation'] = dict(contract=STARTUP_CONTRACT,
        scope='PV reuse initializer and empty observer lifecycle only; no first advance or model job',
        independent_review_pending=True, root_admission_required=True,
        historical_pass_inherited=False, fixed_git_runtime_unchanged=True)
    prep_names = (set(old_production['preparation_files']) |
                  (set(meta['overlay_files']) - set(sources)) | {STARTUP_CONTRACT})
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
    need(set(content) == set(old_files) | {'integration/attention_route_probe.py', STARTUP_CONTRACT},
         'unknown output inventory')
    total = sum(map(len, content.values()))
    need(total + MAX_RECEIPT <= MAX_OUTPUT, 'assembly plus receipt reserve exceeds 9 MiB')
    for name, raw in content.items():
        need(len(raw) <= MAX_SMALL_FILE, 'small source/metadata cap exceeded')
        if name.endswith('.py'):
            ast.parse(raw, filename=name)
            compile(raw, name, 'exec', dont_inherit=True, optimize=0)
    new_receipt = dict(schema='fixed93-pv-reuse-startup-source-assembly-v1',
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
        historical_evidence_is_not_current_qualification=True, **startup)
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
    print(json.dumps(prepare_probe(args.predecessor, args.package,
          args.package_manifest_sha, args.output), sort_keys=True))
