"""Prepare source files and external-frozen routing, never admit or run a DUT.

All six CLI paths are required. Only the 321 pinned source/selected/support
objects and small preparation metadata are written. The frozen roots are
stat-checked as directories, not enumerated, opened, hashed, or copied. A later,
separately authorized preflight must verify the declared external payloads and
runtime. This program does not invoke that preflight or create ADMISSION/work.

The PV metadata generator is executed only after its complete small source
bundle is byte-pinned. Its plan receipt is deliberately not inherited. Top and
production manifests are rebuilt after routing and oracle-binding changes.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import sys
import tempfile

BASE_MANIFEST_SHA = 'e34dbc5b4274399552bfb1d200bca6119ea734030d195201aadfe96b4472acb0'
PV_BUNDLE_SHA = '3b94f42d7612c363d4edd2daee6355e732e70e6f39c671d8bd4ec293b48bea3d'
RESOLVER_BUNDLE_SHA = 'f5a8e2191f2e4b1012b8cb480ec9c94a195a88a36b4b69a3802dd057adeaa580'
BASE_ASSEMBLY_SHA = 'fb45a594e6cf516f9ce722d5db1279950241083206486e164782367b48811423'
LAYOUT_SCHEMA = 'fixed93-readonly-external-frozen-layout-v1'
BINDING = 'source/work/qwen2_fixed93_fullblock_binding/FROZEN_BINDING.json'
COPIES = 'contract/FROZEN_DATA_COPIES.json'
PREFIXES = ('work/qwen2_recovered_inputs', 'work/qwen2_recovered_reference')
ROUTING = frozenset(('admission.py', 'assembly_preflight.py', 'frozen_layout.py',
                    'integration/runner.py', 'integration/runtime_support/gates.py',
                    'integration/runtime_support/recipe.py'))
DELTAS = frozenset(('source/candidates/qwen2_fixed93_attention/owner.py',
                   'selected/chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala'))
DOMAINS = (('source', 'source_sha256', 'source_bytes', 306),
           ('selected', 'selected_source_sha256', 'selected_source_bytes', 9),
           ('support', 'support_sha256', 'support_bytes', 6))
MAX_SMALL_FILE = 2 * 1024 * 1024
MAX_ASSEMBLY_BYTES = 9 * 1024 * 1024
MAX_RECEIPT_BYTES = 256 * 1024


def need(ok, message):
    if not ok:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def parse(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'duplicate JSON key')
            value[key] = item
        return value
    def invalid(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def pin(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def spec(value):
    need(type(value) is dict and set(value) == {'bytes', 'sha256'} and
         type(value['bytes']) is int and 0 <= value['bytes'] <= MAX_SMALL_FILE and
         type(value['sha256']) is str and len(value['sha256']) == 64 and
         all(c in '0123456789abcdef' for c in value['sha256']), 'bounded exact byte/SHA pin')
    return value


def relative(value):
    need(type(value) is str and value and not Path(value).is_absolute() and
         str(Path(value)) == value and all(p not in ('', '.', '..') for p in value.split('/')),
         'canonical relative file name required')
    return value


def local_name(value):
    relative(value)
    need(value not in ('SOURCE_MANIFEST.json', 'ADMISSION.json', 'ASSEMBLY_RECEIPT.json') and
         not value.startswith('work/') and
         (not value.startswith('source/work/') or value == BINDING),
         'payload, run, authority, or self-manifest file is not preparation: ' + value)
    return value


def canonical(value, *, directory=False):
    path = Path(value)
    need(path.is_absolute() and str(path) == str(value) and path.resolve() == path and
         not any(p.is_symlink() for p in (path, *path.parents)), 'canonical absolute path required')
    if directory:
        need(stat.S_ISDIR(path.lstat().st_mode), 'existing directory required: ' + str(path))
    return path


def overlap(a, b):
    return a == b or a in b.parents or b in a.parents


def stamp(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def read_small(root, name, expected=None):
    path = canonical(root / relative(name))
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
         before.st_size <= MAX_SMALL_FILE, 'bounded regular single-link source/metadata file')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        need(stamp(before) == stamp(opened), 'source replaced before open: ' + name)
        raw = stream.read(MAX_SMALL_FILE + 1)
        after = os.fstat(stream.fileno())
    need(len(raw) <= MAX_SMALL_FILE and stamp(before) == stamp(after) == stamp(path.lstat()),
         'source changed during read: ' + name)
    need(expected is None or pin(raw) == spec(expected), 'pinned source drift: ' + name)
    return raw


def bundle(root, expected_sha, expected_schema):
    raw = read_small(root, 'SOURCE_BUNDLE_MANIFEST.json')
    need(pin(raw)['sha256'] == expected_sha, 'wrong source bundle manifest: ' + str(root))
    manifest = parse(raw)
    need(manifest['schema'] == expected_schema and type(manifest['files']) is dict,
         'source bundle schema/files')
    files = {name: read_small(root, name, value) for name, value in manifest['files'].items()}
    return manifest, files


def source_map(manifest):
    result = {}
    for directory, hkey, skey, count in DOMAINS:
        hashes, sizes = manifest[hkey], manifest[skey]
        need(type(hashes) is dict and type(sizes) is dict and
             hashes.keys() == sizes.keys() and len(hashes) == count, 'exact source domain: ' + directory)
        for name, digest in hashes.items():
            logical = local_name(directory + '/' + relative(name))
            need(not logical.startswith('source/work/'), 'no work files among exact321')
            result[logical] = spec(dict(bytes=sizes[name], sha256=digest))
    need(len(result) == 321, 'exact321 unique source objects')
    return result


def write_new(root, name, raw):
    path = root / relative(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    canonical(path.parent, directory=True)
    with path.open('xb') as stream:
        need(stream.write(raw) == len(raw), 'short source write')
    need(read_small(root, name, pin(raw)) == raw, 'written source verification failed')


def prepare_assembly(baseline, pv_bundle, resolver_bundle, output, input_root, reference_root):
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and
         not sys.flags.optimize, 'use python -I -S -B without optimization')
    need(not any(name.split('.')[0] in ('numpy', 'ctypes', 'torch', 'candidates')
                 for name in sys.modules), 'no DUT/native imports before preparation')
    baseline, pv_bundle, resolver_bundle = (
        canonical(Path(value).absolute(), directory=True) for value in (baseline, pv_bundle, resolver_bundle))
    output = canonical(Path(output).absolute())
    need(not output.exists(), 'fresh nonexistent assembly output required')
    canonical(output.parent, directory=True)
    # These two caller-supplied strings must already be exact absolute paths.
    roots = {PREFIXES[0]: canonical(input_root, directory=True),
             PREFIXES[1]: canonical(reference_root, directory=True)}
    need(not overlap(*roots.values()), 'external frozen roots overlap')
    need(all(not overlap(output, path) for path in
             (baseline, pv_bundle, resolver_bundle, *roots.values())), 'assembly overlaps an input root')
    root_stamps = {path: stamp(path.lstat()) for path in roots.values()}
    denied = []
    # Active only for this operation. All mutations stay in the fresh output;
    # its temporary metadata child is removed before the completed receipt.
    active = {'value': True}
    def audit_path(value, dir_fd=None):
        if type(value) is int:
            return Path(os.readlink('/proc/self/fd/' + str(value))).resolve()
        path = Path(os.fsdecode(value))
        if not path.is_absolute():
            base = Path.cwd() if dir_fd in (None, -1) else Path(os.readlink('/proc/self/fd/' + str(dir_fd)))
            path = base / path
        return path.resolve()
    def writable(value, dir_fd=None):
        path = audit_path(value, dir_fd)
        need(path == output or output in path.parents, 'writes are limited to fresh assembly output')
    def audit(event, args):
        if not active['value']:
            return
        if event.startswith(('ctypes.', 'subprocess.', 'socket.')) or event in (
                'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.link', 'os.symlink'):
            denied.append(event)
            raise RuntimeError('source preparation boundary denied: ' + event)
        if event == 'import' and args[0].split('.')[0] in ('numpy', 'ctypes', 'torch', 'candidates'):
            denied.append('import:' + args[0])
            raise RuntimeError('DUT/native import denied')
        if event == 'open':
            path = audit_path(args[0])
            need(not any(path == root or root in path.parents for root in roots.values()),
                 'external frozen files must never be opened during source preparation')
            mode, flags = args[1:]
            if ((type(mode) is str and any(c in mode for c in 'wax+')) or
                    (type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))):
                need(type(args[0]) is int or Path(os.fsdecode(args[0])).is_absolute(),
                     'relative write-open cannot prove its dir_fd target')
                writable(args[0])
        if event in ('os.remove', 'os.rmdir'):
            writable(args[0], args[1])
        elif event in ('os.mkdir', 'os.chmod'):
            writable(args[0], args[2])
        elif event in ('os.chown', 'os.utime'):
            writable(args[0], args[3])
        elif event == 'os.truncate':
            writable(args[0])
        if event == 'os.rename':
            writable(args[0], args[2]); writable(args[1], args[3])
    sys.addaudithook(audit)
    try:
        return _prepare(baseline, pv_bundle, resolver_bundle, output, roots, root_stamps, denied)
    finally:
        active['value'] = False


def _prepare(baseline, pv_bundle, resolver_bundle, output, roots, root_stamps, denied):
    pv_manifest, pv = bundle(pv_bundle, PV_BUNDLE_SHA, 'fixed93-pv-reuse-source-preparation-bundle-v1')
    resolver_manifest, resolver = bundle(resolver_bundle, RESOLVER_BUNDLE_SHA,
                                         'external-frozen-routing-source-bundle-v1')
    need(pv_manifest['baseline_manifest_sha256'] == BASE_MANIFEST_SHA, 'PV predecessor pin')
    inputs = parse(pv['INPUT_PINS.json'])
    need(inputs['schema'] == 'fixed93-pv-reuse-integration-inputs-v1', 'PV input-pin schema')
    base = {name: read_small(baseline, name, value) for name, value in inputs['baseline'].items()}
    need(pin(base['SOURCE_MANIFEST.json'])['sha256'] == BASE_MANIFEST_SHA and
         pin(base['ASSEMBLY_BASE.json'])['sha256'] == BASE_ASSEMBLY_SHA, 'exact baseline metadata')
    old = parse(base['SOURCE_MANIFEST.json'])
    for name, value in inputs['baseline_changed_files'].items():
        read_small(baseline, name, value)
    overlay = {name: pv['overlay/' + name] for name in inputs['overlay']}
    need({name: pin(raw) for name, raw in overlay.items()} == inputs['overlay'], 'PV overlay pins disagree')
    need({name[8:] for name in pv if name.startswith('overlay/')} == set(overlay), 'exact PV overlay inventory')
    routing = {name[8:]: raw for name, raw in resolver.items() if name.startswith('overlay/')}
    need(set(routing) == ROUTING, 'exact six routing/helper sources')
    bases = parse(resolver['SOURCE_BASE_PINS.json'])
    need(bases['schema'] == 'external-frozen-routing-source-bases-v1' and
         bases['baseline_manifest_sha256'] == BASE_MANIFEST_SHA and
         bases['pv_source_bundle_manifest_sha256'] == PV_BUNDLE_SHA and
         set(bases['files']) == ROUTING, 'resolver source-base contract')
    for name, value in bases['files'].items():
        expected = {key: value[key] for key in ('bytes', 'sha256')}
        if value['origin'] == 'current_fullblock_base':
            need(old['preparation_files'].get(name) == expected, 'baseline routing pin not in top manifest')
            read_small(baseline, name, expected)
        elif value['origin'] == 'pv_source_overlay':
            need(name in overlay and pin(overlay[name]) == expected, 'resolver PV base mismatch')
        else:
            need(value['origin'] == 'new_file' and name == 'frozen_layout.py' and
                 expected == pin(b'') and name not in old['preparation_files'], 'exact new resolver file')
    baseline_objects = source_map(old)
    objects = parse(base['ASSEMBLY_BASE.json'])['objects']
    need(len(objects) == 321 and len({item['path'] for item in objects}) == 321 and
         {item['path']: {key: item[key] for key in ('bytes', 'sha256')} for item in objects} == baseline_objects,
         'baseline assembly/domain mismatch')
    expected_objects = dict(baseline_objects)
    for name in DELTAS:
        need(inputs['baseline_changed_files'][name] == baseline_objects[name], 'exact predecessor source delta')
        expected_objects[name] = pin(overlay[name])
    need({name for name in overlay if name.startswith(('source/', 'selected/', 'support/'))} == DELTAS,
         'only two source/selected deltas permitted')

    # This pinned pure metadata generator only imports stdlib and its original
    # source-plan guards. It does not execute DUT, admission, current preflight,
    # resolver load, runtime hashing, or reference/weight loading.
    output.mkdir()
    with tempfile.TemporaryDirectory(prefix='.pv-metadata-', dir=output) as temporary:
        # The original generator rereads INPUT_PINS and CAPACITY without its
        # own bundle guard. Point HERE only at this private verified-byte
        # snapshot, never at the live PV input directory checked earlier.
        snapshot = Path(temporary) / 'pv-source'
        snapshot.mkdir()
        snapshot_files = {name: raw for name, raw in pv.items()
                          if name in ('prepare_metadata.py', 'INPUT_PINS.json', 'CAPACITY_PROPOSAL.json')
                          or name.startswith('overlay/')}
        for name, raw in sorted(snapshot_files.items()):
            write_new(snapshot, name, raw)
        namespace = {'__name__': '_pinned_pv_metadata_generator', '__file__': str(snapshot / 'prepare_metadata.py')}
        exec(compile(pv['prepare_metadata.py'], namespace['__file__'], 'exec', dont_inherit=True, optimize=0), namespace)
        metadata_root = Path(temporary) / 'metadata'
        plan = namespace['build'](baseline, metadata_root)
        need(plan['status'] == 'METADATA_PLAN_ONLY_NO_MATERIALIZED_ASSEMBLY' and
             plan['actual_authorized'] is False and plan['DUT_imported'] is False, 'generator scope changed')
        generated = {name: read_small(metadata_root, name, value) for name, value in plan['output_files'].items()}
        generated_metadata_bytes = sum(map(len, generated.values())) + len(read_small(metadata_root, 'PLAN_RECEIPT.json'))
        generator_snapshot_bytes = sum(map(len, snapshot_files.values()))
        temporary_metadata_bytes = generated_metadata_bytes + generator_snapshot_bytes
        need(temporary_metadata_bytes <= MAX_ASSEMBLY_BYTES, 'temporary source/metadata exceeds source-only cap')
        for name, raw in snapshot_files.items():
            read_small(snapshot, name, pin(raw))
    top = parse(generated.pop('SOURCE_MANIFEST.json'))
    generated_production = parse(generated.pop('PRODUCTION_SOURCE_MANIFEST.json'))
    need(source_map(top) == source_map(generated_production) == expected_objects, 'exact PV successor source inventory')
    need(top['preparation_files'].get('PRODUCTION_SOURCE_MANIFEST.json') == pin(encoded(generated_production)),
         'generated production pin differs')
    need({k: v for k, v in top.items() if k != 'preparation_files'} ==
         {k: v for k, v in generated_production.items() if k != 'preparation_files'} and
         {k: v for k, v in top['preparation_files'].items() if k != 'PRODUCTION_SOURCE_MANIFEST.json'} ==
         generated_production['preparation_files'], 'generator top/production are not the same closure')
    binding = parse(generated[BINDING])
    mapping = {name: dict(bytes=top['source_bytes'][name], sha256=digest)
               for name, digest in top['source_sha256'].items()}
    source_digest = hashlib.sha256(json.dumps(mapping, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    need(binding['source_closure_sha256'] == source_digest and binding['old_pass_inherited'] is False,
         'new noncircular306 binding mismatch')
    binding.update(status='CURRENT_REVIEWED_FROZEN_PAIR_ORACLE_ONLY',
                   scope='Preserve only the unchanged frozen input/reference pair qualification; bind it to the new PV source map. No DUT, PV, source/cold, native, numerical, or fullblock qualification or execution authority is granted.',
                   actual_admission=False, dut_executed=False, numerical_acceptance_claimed=False)
    generated[BINDING] = encoded(binding)
    copies_raw = read_small(baseline, COPIES, old['preparation_files'][COPIES])
    copies = parse(copies_raw)
    need(type(copies['files']) is dict and len(copies['files']) == 76, 'unchanged exact76 frozen inventory')
    for name, value in copies['files'].items():
        relative(name)
        need(sum(name.startswith(prefix + '/') for prefix in PREFIXES) == 1 and
             type(value) is dict and set(value) == {'bytes', 'sha256'}, 'frozen logical pin shape')
    need(sum(name.startswith(PREFIXES[1] + '/first/') and name.endswith(('.f32le', '.bf16le'))
             for name in copies['files']) == 30, 'exact30 reference payload declarations')
    generated['FROZEN_EXTERNAL_LAYOUT.json'] = encoded(dict(
        schema=LAYOUT_SCHEMA, roots={name: str(path) for name, path in roots.items()},
        files=copies['files'], copy_manifest=pin(copies_raw), read_only=True, copy_payloads=False))
    budget = parse(generated['BUDGET_PROPOSAL.json'])
    need(budget['status'] == 'OPEN_PV_REUSE_BUDGET_PENDING_COMBINED_REVIEW' and
         budget['actual_execution_authorized'] is False and budget['automatic_retry'] is False and
         budget['attention_trace_limits']['source_manifest_sha256'] == 'DERIVE_FROM_REVIEWED_SOURCE_MANIFEST',
         'resource proposal must remain OPEN without circular authority')

    content = {}
    for name, value in expected_objects.items():
        content[name] = overlay[name] if name in overlay else read_small(baseline, name, value)
        need(pin(content[name]) == value, 'successor object mismatch: ' + name)
    prep_names = (set(top['preparation_files']) | set(generated) | ROUTING) - {'PRODUCTION_SOURCE_MANIFEST.json'}
    for name in sorted(prep_names):
        local_name(name)
        need(name not in content, 'preparation/source domains overlap')
        if name in routing:
            raw = routing[name]
        elif name in generated:
            raw = generated[name]
        elif name in overlay:
            raw = overlay[name]
        else:
            raw = read_small(baseline, name, old['preparation_files'][name])
        content[name] = raw
    prep = {name: pin(content[name]) for name in sorted(prep_names)}
    need(ROUTING | {'FROZEN_EXTERNAL_LAYOUT.json', BINDING} <= prep.keys(), 'routing/layout/binding must be pinned')
    top.update(status='SOURCE_ASSEMBLY_PREPARED_NOT_ADMITTED', actual_admission=False,
               actual_execution_authorized=False, native_executed=False, M128_executed=False,
               fullblock_acceptance=False, old_pass_inherited=False,
               historical_receipts_are_not_current_qualification=True,
               preparation_scope='Materialized source/metadata only. External frozen files and runtime not verified here; combined source/cold review and separate root authority remain required.',
               external_frozen_preparation=dict(pv_bundle_manifest_sha256=PV_BUNDLE_SHA,
                   resolver_bundle_manifest_sha256=RESOLVER_BUNDLE_SHA,
                   baseline_manifest_sha256=BASE_MANIFEST_SHA, copied_payloads=False,
                   input_reference_payloads_opened=False, external_roots_only_stat_checked=True))
    top['preparation_files'] = prep
    production_raw = encoded(top)
    content['PRODUCTION_SOURCE_MANIFEST.json'] = production_raw
    top['preparation_files'] = dict(prep)
    top['preparation_files']['PRODUCTION_SOURCE_MANIFEST.json'] = pin(production_raw)
    content['SOURCE_MANIFEST.json'] = encoded(top)
    need('SOURCE_MANIFEST.json' not in top['preparation_files'] and
         'PRODUCTION_SOURCE_MANIFEST.json' not in parse(production_raw)['preparation_files'], 'no self-referential manifest pin')
    total_bytes = sum(map(len, content.values()))
    need(total_bytes + MAX_RECEIPT_BYTES <= MAX_ASSEMBLY_BYTES, 'source/metadata plus receipt exceeds 9 MiB cap')
    for name, raw in content.items():
        if name.endswith('.py'):
            ast.parse(raw, filename=name)
            compile(raw, name, 'exec', dont_inherit=True, optimize=0)
    need(not denied, 'preparation attempted a denied native/process operation')
    for root, initial in root_stamps.items():
        need(stamp(root.lstat()) == initial, 'external frozen root changed during preparation')
    for name, raw in sorted(content.items()):
        write_new(output, name, raw)
    need({str(path.relative_to(output)) for path in output.rglob('*') if path.is_file()} == set(content),
         'fresh output contains an undeclared file')
    need(not (output / 'ADMISSION.json').exists() and not (output / 'work').exists(), 'no admission/runtime output')
    need(not any((output / 'source' / prefix).exists() for prefix in PREFIXES), 'no local frozen payload directories')
    manifest_sha = pin(content['SOURCE_MANIFEST.json'])['sha256']
    python = parse(content['RUNTIME_PINS.json'])['python']['path']
    command = [python, '-I', '-S', '-B', str(output / 'assembly_preflight.py'), '--manifest-sha', manifest_sha]
    receipt = dict(schema='fixed93-external-frozen-source-assembly-receipt-v1',
                   status='SOURCE_FILES_PREPARED_PENDING_SEPARATE_PREFLIGHT_AND_REVIEW',
                   source_manifest=pin(content['SOURCE_MANIFEST.json']),
                   production_source_manifest=pin(production_raw), assembly_objects=321,
                   source_files=306, selected_files=9, support_files=6,
                   preparation_files=len(top['preparation_files']),
                   files_excluding_this_receipt=len(content), bytes_excluding_this_receipt=total_bytes,
                   receipt_file_bytes_cap=MAX_RECEIPT_BYTES,
                   logical_output_bytes_upper_bound=total_bytes + MAX_RECEIPT_BYTES,
                   temporary_metadata_bytes=temporary_metadata_bytes,
                   generator_snapshot_bytes=generator_snapshot_bytes,
                   generated_metadata_bytes=generated_metadata_bytes,
                   logical_file_bytes_peak_upper_bound=max(temporary_metadata_bytes, total_bytes + MAX_RECEIPT_BYTES),
                   logical_file_bytes_cap=MAX_ASSEMBLY_BYTES,
                   files={name: pin(raw) for name, raw in sorted(content.items())},
                   count_scope='Receipt excludes itself; production manifest is one preparation file, top manifest is separate.',
                   external_frozen_files_declared=76, external_roots_only_stat_checked=True,
                   input_reference_files_opened=0, payloads_copied=0, runtime_payloads_hashed=0,
                   preflight_executed=False, source_cold_review_qualified=False, actual_admission=False,
                   actual_execution_authorized=False, DUT_imported=False, native_executed=False,
                   fullblock_acceptance=False, budget_status=budget['status'],
                   preflight_requires_separate_authorization=True,
                   preflight_command_argv=command, preflight_command=shlex.join(command))
    receipt_raw = encoded(receipt)
    need(len(receipt_raw) <= MAX_RECEIPT_BYTES, 'receipt exceeds its independent small cap')
    write_new(output, 'ASSEMBLY_RECEIPT.json', receipt_raw)
    # These exact self-file totals are returned to stdout, not stored inside
    # their own hashed receipt, so no fixed-point or self-hash is introduced.
    return dict(receipt, receipt_file=pin(receipt_raw),
                files_including_receipt=len(content) + 1,
                bytes_including_receipt=total_bytes + len(receipt_raw),
                logical_file_bytes_peak=max(temporary_metadata_bytes, total_bytes + len(receipt_raw)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('baseline', 'pv-bundle', 'resolver-bundle', 'output', 'input-root', 'reference-root'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    result = prepare_assembly(args.baseline, args.pv_bundle, args.resolver_bundle,
                              args.output, args.input_root, args.reference_root)
    print(json.dumps({key: value for key, value in result.items() if key != 'files'}, sort_keys=True))
