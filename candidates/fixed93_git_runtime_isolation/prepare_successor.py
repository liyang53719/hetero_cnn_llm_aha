"""Prepare one bounded source-only successor with isolated Git runtime pins.

This program is inert until separately authorized and invoked. It never runs
Git, a profile verifier, preflight, imported candidate code, native code or a
DUT. It opens only bounded, pinned metadata/source files, never a Git pack or
frozen payload. The old 0150 assembly and all historical evidence stay intact.
Run with python -I -S -B. Every CLI option is required; output must not exist.
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


OLD_TOP_PIN = {'bytes': 112347, 'sha256': '39ae180ce12df8f22c085b8b2ca507fbceb2aa29e47c2b04edd77786eebc2142'}
OLD_RECEIPT_PIN = {'bytes': 97372, 'sha256': 'df42d5523b7e62bf48a0484cbab8d73fadf394e9de398d91bd4515abe04db0f2'}
OLD_RUNTIME_PIN = {'bytes': 379526, 'sha256': 'c63292b6cd0be00f15578266f696e7e2b58733d58e1d1ea92fa8bb45e50fc76c'}
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
GIT_NAMES = frozenset(('HEAD', 'config', 'shallow',
    'objects/pack/pack-99eb2d31e43dac84c4651d133b1bc52fa822b513.idx',
    'objects/pack/pack-99eb2d31e43dac84c4651d133b1bc52fa822b513.pack',
    'objects/pack/pack-99eb2d31e43dac84c4651d133b1bc52fa822b513.rev'))
PROFILE_NAMES = frozenset(('339b21863d1bf21cac842ad7395b4570802bca14.tree',
    '4f92a2fa92a3c3c39dcda90ce62806486a723059.tree',
    '91169f015489c3f6637752ed1fb24959ffcf160c.tree', 'LINEAGE.json',
    'MANIFEST.json', 'README.md', 'a05d76302a6eb76f4742cb6d19d793af5089456e.tree',
    'adefaa78c2d313d9927b4e87550dddc926b3c605.commit',
    'committed_qwen2_block.cpp', 'e40538df77611f10e39e70d5520397886a5607c8.blob',
    'git_profile.py', 'test_cold.py'))


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


def validate_runtime(old, new, receipt, snapshot):
    """Pure metadata comparison; no runtime path is opened or hashed here."""
    # The caller has already established OLD_RUNTIME_PIN. Derive identities
    # from those exact bytes, never from a separate CLI root override.
    old_git = str(absolute_text(old['git_environment']['GIT_DIR']))
    old_profile = str(absolute_text(old['git_profile_root']))
    mapping = {old_git + '/' + name: str(snapshot / 'git' / name) for name in GIT_NAMES}
    mapping.update({old_profile + '/' + name: str(snapshot / 'profile' / name)
                    for name in PROFILE_NAMES})
    need(receipt['old_to_new_path'] == mapping and len(mapping) == 18 and
         len(set(mapping.values())) == 18, 'exact 6 Git + 12 profile migration required')
    need(receipt['unchanged_count'] == 1620 and receipt['runtime_count'] == 1638,
         'snapshot count identity changed')
    expected_names = {'git/' + n for n in GIT_NAMES} | {'profile/' + n for n in PROFILE_NAMES} | {RUNTIME}
    snapshot_files = receipt['snapshot_files']
    need(type(snapshot_files) is dict and set(snapshot_files) == expected_names,
         'unknown, omitted or extra snapshot file')
    for name, value in snapshot_files.items():
        relative(name)
        spec(value)
    need(receipt['profile_files'] == {n: snapshot_files['profile/' + n] for n in PROFILE_NAMES},
         'profile/snapshot pin sets disagree')
    before, after = old['files'], new['files']
    need(type(before) is dict and type(after) is dict and len(before) == len(after) == 1638,
         'exact runtime count required')
    for paths in (before, after):
        for name, value in paths.items():
            absolute_text(name)
            spec(value)
    need(set(mapping) <= set(before) and not set(mapping.values()) & set(before),
         'missing old pin or colliding snapshot target')
    need({p for p in before if p.startswith((old_git + '/', old_profile + '/'))} == set(mapping),
         'unknown old Git/profile pin')
    generated_profile = {old_profile + '/' + n for n in ('LINEAGE.json', 'git_profile.py', 'MANIFEST.json')}
    need(all(snapshot_files[str(Path(target).relative_to(snapshot))] == before[source]
             for source, target in mapping.items() if source not in generated_profile),
         '15 nongenerated Git/profile dependency pins must stay byte-identical')
    expected = {name: value for name, value in before.items() if name not in mapping}
    need(len(expected) == 1620, 'unchanged runtime set must contain 1620 entries')
    expected.update({target: snapshot_files[str(Path(target).relative_to(snapshot))]
                     for target in mapping.values()})
    need(after == expected and not set(mapping) & set(after),
         'runtime mixed old/new paths, extra/missing pins, or unrelated pin drift')
    need(old['total_file_bytes'] == sum(s['bytes'] for s in before.values()) and
         new['total_file_bytes'] == sum(s['bytes'] for s in after.values()), 'runtime byte total mismatch')
    expected_runtime = copy.deepcopy(old)
    expected_runtime['files'] = expected
    expected_runtime['total_file_bytes'] = sum(s['bytes'] for s in expected.values())
    expected_runtime['git_environment']['GIT_DIR'] = str(snapshot / 'git')
    expected_runtime['git_profile_root'] = str(snapshot / 'profile')
    expected_runtime['git_profile_manifest_sha256'] = snapshot_files['profile/MANIFEST.json']['sha256']
    need(encoded(new) == encoded(expected_runtime),
         'unrelated runtime field, type or Git environment changed')
    return mapping


def validate_profile_manifest(raw, receipt, runtime):
    manifest = parse(raw)
    need(type(manifest['schema']) is int and manifest['schema'] == 1 and
         manifest['files'] == {n: s for n, s in receipt['profile_files'].items()
                               if n != 'MANIFEST.json'},
         'profile manifest and exact profile pins disagree')
    need(pin(raw) == receipt['profile_files']['MANIFEST.json'] and
         runtime['git_profile_manifest_sha256'] == pin(raw)['sha256'],
         'new runtime profile-manifest SHA association failed')


def prepare_successor(predecessor, snapshot, snapshot_receipt_sha, output):
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and
         not sys.flags.optimize, 'use python -I -S -B without optimization')
    predecessor = canonical(predecessor, directory=True)
    snapshot = canonical(snapshot, directory=True)
    output = canonical(output)
    need(not output.exists(), 'fresh nonexistent successor output required')
    canonical(output.parent, directory=True)
    need(not any(overlap(a, b) for a, b in ((predecessor, snapshot), (predecessor, output),
                                           (snapshot, output))), 'source/output roots overlap')
    digest(snapshot_receipt_sha)
    old_receipt_raw = read_small(predecessor, RECEIPT, OLD_RECEIPT_PIN, MAX_RECEIPT)
    old_receipt = parse(old_receipt_raw)
    old_top_raw = read_small(predecessor, TOP, OLD_TOP_PIN)
    old_top = parse(old_top_raw)
    need(old_receipt['source_manifest'] == OLD_TOP_PIN and
         old_receipt['files'][TOP] == OLD_TOP_PIN and
         old_receipt['files'][RUNTIME] == OLD_RUNTIME_PIN,
         'fixed predecessor receipt/top/runtime binding disagreement')
    old_files = old_receipt['files']
    need(type(old_files) is dict and len(old_files) == old_receipt['files_excluding_this_receipt'] == 546,
         'exact old 546-object content inventory required')
    for name, value in old_files.items():
        local_name(name)
        spec(value, MAX_SMALL_FILE)
    need(CONTRACT not in old_files and sum(s['bytes'] for s in old_files.values()) ==
         old_receipt['bytes_excluding_this_receipt'] == 8709510, 'old receipt inventory/bytes changed')
    need(old_top['preparation_files'].get(RUNTIME) == OLD_RUNTIME_PIN,
         'old runtime not pinned by predecessor manifest')
    old_production_raw = read_small(predecessor, PRODUCTION, old_files[PRODUCTION])
    old_production = parse(old_production_raw)
    manifest_pair(old_top, old_production)
    need(old_receipt['production_source_manifest'] == pin(old_production_raw) ==
         old_top['preparation_files'][PRODUCTION], 'old production binding mismatch')
    sources = source_map(old_top)
    need(source_map(old_production) == sources and len(old_top['preparation_files']) == 224,
         'old source/preparation count mismatch')
    expected_old = dict(sources)
    for name, value in old_top['preparation_files'].items():
        local_name(name)
        need(name not in expected_old, 'preparation/source domains overlap')
        expected_old[name] = spec(value, MAX_SMALL_FILE)
    expected_old[TOP] = OLD_TOP_PIN
    need(expected_old == old_files, 'receipt contains unmanifested or missing content')
    old_runtime_raw = read_small(predecessor, RUNTIME, OLD_RUNTIME_PIN)
    old_runtime = parse(old_runtime_raw)
    old_git = absolute_text(old_runtime['git_environment']['GIT_DIR'])
    old_profile = absolute_text(old_runtime['git_profile_root'])
    need(not overlap(old_git, old_profile) and
         all(not overlap(target, original) for target in (snapshot, output)
             for original in (old_git, old_profile)), 'original and isolated runtime roots overlap')

    snapshot_receipt_raw = read_small(snapshot, SNAPSHOT_RECEIPT, limit=MAX_RECEIPT)
    snapshot_receipt_pin = pin(snapshot_receipt_raw)
    need(snapshot_receipt_pin['sha256'] == snapshot_receipt_sha, 'snapshot receipt SHA mismatch')
    sr = parse(snapshot_receipt_raw)
    need(type(sr['schema']) is int and sr['schema'] == 1 and
         sr['status'] == 'SOURCE_DEPENDENCY_ISOLATION_ONLY_NOT_DUT_ADMISSION' and
         sr['old_runtime_pin'] == OLD_RUNTIME_PIN, 'wrong snapshot scope or predecessor pin')
    need(sr['snapshot_root'] == str(snapshot) and sr['profile_root'] == str(snapshot / 'profile') and
         sr['git_dir'] == str(snapshot / 'git') and sr['source_git_dir'] == str(old_git) and
         sr['source_profile_root'] == str(old_profile) and
         sr['source_runtime_path'] == str(predecessor / RUNTIME),
         'snapshot source/root identity changed')
    need(sr['source_profile_pins'] == {n: old_runtime['files'][str(old_profile / n)]
         for n in ('LINEAGE.json', 'MANIFEST.json', 'git_profile.py')},
         'snapshot source profile pins do not match fixed predecessor')
    need(all(sr[k] is True for k in ('head_reconstructed_from_pinned_lineage', 'no_git_command',
                                     'no_profile_verify', 'no_native', 'no_model')),
         'snapshot preparation boundary not established')
    digest(sr['source_builder_sha256'])
    spec(sr['new_runtime_pin'], MAX_SMALL_FILE)
    need(sr['snapshot_files'][RUNTIME] == sr['new_runtime_pin'], 'snapshot runtime pin is ambiguous')
    new_runtime_raw = read_small(snapshot, RUNTIME, sr['new_runtime_pin'])
    new_runtime = parse(new_runtime_raw)
    mapping = validate_runtime(old_runtime, new_runtime, sr, snapshot)
    profile_manifest_raw = read_small(snapshot, 'profile/MANIFEST.json', sr['profile_files']['MANIFEST.json'])
    validate_profile_manifest(profile_manifest_raw, sr, new_runtime)

    # Only this fixed old receipt chooses source files. Snapshot dependencies
    # stay external; no runtime file map entry is used as a read/copy request.
    content = {name: read_small(predecessor, name, value) for name, value in old_files.items()}
    need(content[TOP] == old_top_raw and content[PRODUCTION] == old_production_raw and
         content[RUNTIME] == old_runtime_raw, 'predecessor changed between reads')
    layout = parse(content['FROZEN_EXTERNAL_LAYOUT.json'])
    need(layout['read_only'] is True and layout['copy_payloads'] is False and len(layout['files']) == 76,
         'external frozen layout changed')
    frozen_roots = tuple(absolute_text(p) for p in layout['roots'].values())
    need(all(not overlap(output, p) and not overlap(snapshot, p) for p in frozen_roots),
         'output or snapshot overlaps external frozen payloads')
    budget = parse(content['BUDGET_PROPOSAL.json'])
    need(budget['status'] == 'OPEN_PV_REUSE_BUDGET_PENDING_COMBINED_REVIEW' and
         budget['actual_execution_authorized'] is False and budget['automatic_retry'] is False,
         'budget must stay OPEN without execution authority')
    for key in ('actual_admission', 'actual_execution_authorized', 'native_executed',
                'M128_executed', 'fullblock_acceptance', 'old_pass_inherited'):
        need(old_top[key] is False, 'predecessor contains current execution authority')
    content[RUNTIME] = new_runtime_raw
    contract = dict(schema='fixed93-fixed-git-runtime-isolation-v1',
        status='FIXED_GIT_RUNTIME_DEPENDENCY_ISOLATION_ONLY_NOT_ADMISSION',
        predecessor_root=str(predecessor), predecessor_manifest=OLD_TOP_PIN,
        predecessor_receipt=OLD_RECEIPT_PIN, old_runtime_pin=OLD_RUNTIME_PIN,
        new_runtime_pin=pin(new_runtime_raw), snapshot_root=str(snapshot),
        snapshot_receipt_name=SNAPSHOT_RECEIPT, snapshot_receipt=snapshot_receipt_pin,
        source_git_dir=str(old_git), source_profile_root=str(old_profile), old_to_new_path=mapping,
        runtime_count=1638, changed_runtime_paths=18, unchanged_runtime_pins=1620,
        source_selected_support_unchanged=True, other_preparation_bytes_unchanged=True,
        original_frozen_binding=old_files[BINDING], external_frozen_layout=old_files['FROZEN_EXTERNAL_LAYOUT.json'],
        provenance_preserved=True, historical_evidence_is_not_current_qualification=True,
        snapshot_payloads_opened=False, snapshot_payloads_copied=False,
        frozen_payloads_opened=False, frozen_payloads_copied=False,
        preflight_executed=False, source_cold_review_qualified=False, actual_admission=False,
        actual_execution_authorized=False, native_executed=False, DUT_imported=False,
        fullblock_acceptance=False, budget_status=budget['status'],
        scope='Only isolate fixed Git/profile runtime dependencies. Preserve all provenance and the original frozen binding. This is not preflight permission, cold qualification, execution admission, or fullblock PASS.')
    content[CONTRACT] = encoded(contract)
    top = copy.deepcopy(old_top)
    prep = {n: pin(content[n]) for n in old_production['preparation_files']}
    prep[CONTRACT] = pin(content[CONTRACT])
    top['preparation_files'] = prep
    production_raw = encoded(top)
    content[PRODUCTION] = production_raw
    top['preparation_files'] = dict(prep, **{PRODUCTION: pin(production_raw)})
    content[TOP] = encoded(top)
    manifest_pair(top, parse(production_raw))
    need(source_map(top) == sources and len(top['preparation_files']) == 225,
         'successor source inventory or preparation count changed')
    need({n: pin(content[n]) for n in old_files if n not in (TOP, PRODUCTION, RUNTIME)} ==
         {n: s for n, s in old_files.items() if n not in (TOP, PRODUCTION, RUNTIME)},
         'non-runtime source or preparation bytes changed')
    need(set(content) == set(old_files) | {CONTRACT} and len(content) == 547,
         'successor contains undeclared or missing content')
    total = sum(map(len, content.values()))
    need(total + MAX_RECEIPT <= MAX_OUTPUT, 'successor plus receipt reserve exceeds 9 MiB')
    for name, raw in content.items():
        need(len(raw) <= MAX_SMALL_FILE, 'oversize output metadata/source')
        if name.endswith('.py'):
            ast.parse(raw, filename=name)
            compile(raw, name, 'exec', dont_inherit=True, optimize=0)
    command = [new_runtime['python']['path'], '-I', '-S', '-B',
               str(output / 'assembly_preflight.py'), '--manifest-sha', pin(content[TOP])['sha256']]
    receipt = dict(schema='fixed93-isolated-git-source-assembly-receipt-v1',
        status='SOURCE_FILES_PREPARED_PENDING_SEPARATE_PREFLIGHT_AND_REVIEW',
        predecessor_root=str(predecessor), predecessor_manifest=OLD_TOP_PIN,
        predecessor_receipt=OLD_RECEIPT_PIN, snapshot_root=str(snapshot),
        snapshot_receipt=snapshot_receipt_pin, runtime_isolation=pin(content[CONTRACT]),
        old_runtime_pin=OLD_RUNTIME_PIN, new_runtime_pin=pin(new_runtime_raw),
        source_manifest=pin(content[TOP]), production_source_manifest=pin(production_raw),
        assembly_objects=321, source_files=306, selected_files=9, support_files=6,
        preparation_files=225, files_excluding_this_receipt=len(content),
        bytes_excluding_this_receipt=total, receipt_file_bytes_cap=MAX_RECEIPT,
        logical_file_bytes_cap=MAX_OUTPUT, logical_output_bytes_upper_bound=total + MAX_RECEIPT,
        files={n: pin(raw) for n, raw in sorted(content.items())},
        count_scope='This new receipt excludes itself; old assembly receipt is a pin only, never current qualification.',
        runtime_count=1638, changed_runtime_paths=18, unchanged_runtime_pins=1620,
        provenance_preserved=True, original_frozen_binding_unchanged=True,
        external_frozen_layout_unchanged=True, external_frozen_files_declared=76,
        input_reference_files_opened=0, payloads_copied=0, runtime_payloads_hashed=0,
        git_commands_executed=0, profile_verifier_executed=False,
        preflight_executed=False, source_cold_review_qualified=False, actual_admission=False,
        actual_execution_authorized=False, DUT_imported=False, native_executed=False,
        fullblock_acceptance=False, historical_evidence_is_not_current_qualification=True,
        budget_status=budget['status'], preflight_requires_separate_authorization=True,
        preflight_command_argv=command, preflight_command=shlex.join(command),
        scope='Fixed Git runtime dependency isolation only. No provenance is removed and no preflight or fullblock PASS is granted.')
    receipt_raw = encoded(receipt)
    need(len(receipt_raw) <= MAX_RECEIPT and total + len(receipt_raw) <= MAX_OUTPUT,
         'final receipt or total byte cap exceeded')
    # All validation and bounded reads complete before any output is created.
    output.mkdir()
    for name, raw in sorted(content.items()):
        write_new(output, name, raw)
    write_new(output, RECEIPT, receipt_raw)
    actual = set()
    for path in output.rglob('*'):
        value = path.lstat()
        need(stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode), 'output alias or special file')
        if stat.S_ISREG(value.st_mode):
            need(value.st_nlink == 1, 'hard-linked output forbidden')
            actual.add(str(path.relative_to(output)))
    need(actual == set(content) | {RECEIPT} and not (output / 'work').exists() and
         not (output / 'ADMISSION.json').exists(), 'output inventory or execution boundary failed')
    # Self-file pin/totals exist only in stdout, not inside the receipt.
    return dict(output=str(output), receipt_file=pin(receipt_raw),
                source_manifest=pin(content[TOP]), production_source_manifest=pin(production_raw),
                runtime_pin=pin(new_runtime_raw), files_including_receipt=len(content) + 1,
                bytes_including_receipt=total + len(receipt_raw),
                status=receipt['status'], preflight_executed=False, actual_admission=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('predecessor', 'snapshot', 'snapshot-receipt-sha', 'output'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_successor(args.predecessor, args.snapshot,
                                      args.snapshot_receipt_sha, args.output), sort_keys=True))
