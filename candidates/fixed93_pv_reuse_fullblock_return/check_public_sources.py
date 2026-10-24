"""Bounded public byte/AST check only; no production or builder execution."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import time

MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 512 * 1024


def need(ok, message):
    if not ok:
        raise ValueError(message)


def identity(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def parse(raw):
    def unique(items):
        output = {}
        for key, value in items:
            need(key not in output, 'duplicate metadata key')
            output[key] = value
        return output
    return json.loads(raw, object_pairs_hook=unique)


def relative(name):
    need(type(name) is str and name and not Path(name).is_absolute() and
         str(Path(name)) == name and all(p not in ('', '.', '..') for p in name.split('/')),
         'canonical relative inventory required')
    return name


def read(root, name):
    path = root / relative(name)
    need(path.resolve() == path and not any(p.is_symlink() for p in (path, *path.parents)),
         'symlink/alias refused')
    before = path.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= MAX_FILE,
         'bounded ordinary single-link file required')
    raw = path.read_bytes()
    after = path.stat()
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'file changed during read')
    return raw


def private_literal(text):
    # Standard runtime roots and the existing agent authority identifier are
    # preserved in byte-identical production code, not treated as private roots.
    prefixes = tuple('/' + name + '/' for name in ('workspace', 'home', 'Users'))
    return any(prefix in text for prefix in prefixes)


def check(package, manifest_sha):
    started = time.monotonic()
    root = Path(package)
    need(root.is_absolute() and root.resolve() == root and root.is_dir(), 'explicit canonical package root required')
    need(type(manifest_sha) is str and len(manifest_sha) == 64 and
         all(c in '0123456789abcdef' for c in manifest_sha), 'explicit public manifest SHA required')
    raw = read(root, 'MANIFEST.json')
    need(identity(raw)['sha256'] == manifest_sha, 'public manifest identity differs')
    manifest = parse(raw)
    need(manifest['schema'] == 'fixed93-fullblock-return-public-excerpt-manifest-v1' and
         manifest['actual_authorized'] is False, 'public source-only scope required')
    pins = manifest['files']
    expected = {'prepare_fullblock.py', 'overlay/admission.py', 'overlay/integration/interface.py',
        'overlay/integration/runtime_support/native_artifact.py',
        'overlay/contract/PV_REUSE_EXACT_CAPACITY.json', 'PUBLIC_PINS.json',
        'README.md', 'SUMMARY.md', 'check_public_sources.py'}
    need(type(pins) is dict and set(pins) == expected and len(pins) == manifest['file_count'] == 9 and
         sum(value['bytes'] for value in pins.values()) == manifest['total_file_bytes'] <= MAX_TOTAL,
         'exact nine-file public content inventory required')
    actual = set()
    for path in root.rglob('*'):
        need(not path.is_symlink(), 'public symlink refused')
        if path.is_file():
            actual.add(str(path.relative_to(root)))
        else:
            need(path.is_dir(), 'public special file refused')
    need(actual == set(pins) | {'MANIFEST.json'}, 'unmanifested/missing public file')
    content = {name: read(root, name) for name in pins}
    need(all(identity(content[name]) == value for name, value in pins.items()), 'public content pin differs')
    need(not private_literal(raw.decode()) and
         all(not private_literal(value.decode()) for value in content.values()), 'private machine root literal found')
    provenance = parse(content['PUBLIC_PINS.json'])
    need(provenance['schema'] == 'fixed93-pv-reuse-fullblock-public-source-pins-v1' and
         provenance['published_overlay_count'] == 4 and provenance['original_overlay_count'] == 5 and
         provenance['public_is_not_replacement_package'] is True and
         provenance['execution_authorized'] is False and provenance['original_40_case_result_inherited'] is False and
         provenance['startup_pass_inherited_as_fullblock_qualification'] is False,
         'exact fullblock source-excerpt provenance scope required')
    need(provenance['complete_source_package_manifest'] == dict(bytes=3037,
         sha256='aa68227fb8182cc9ae089491cd2e9c288c793c3f68bc3b18d0b4fb6f40f0c0ae'),
         'original complete package identity differs')
    need(identity(content['prepare_fullblock.py']) == provenance['original_builder'], 'unchanged builder bytes differ')
    entries = provenance['published_python_overlays']
    need(set(entries) == {'admission.py', 'integration/interface.py',
                         'integration/runtime_support/native_artifact.py'}, 'exact three original Python overlays required')
    for name, value in entries.items():
        relative(name)
        need(identity(content['overlay/' + name]) == value['after'] ==
             provenance['all_original_overlay_pins'][name]['after'], 'original overlay after pin differs')
    capacity_pin = provenance['published_capacity_contract']
    need(capacity_pin['path'] == 'overlay/contract/PV_REUSE_EXACT_CAPACITY.json' and
         identity(content[capacity_pin['path']]) == {k: capacity_pin[k] for k in ('bytes', 'sha256')} ==
         provenance['all_original_overlay_pins']['contract/PV_REUSE_EXACT_CAPACITY.json']['after'],
         'unchanged exact-capacity contract differs')
    capacity = parse(content[capacity_pin['path']])
    need(capacity['new_max_raw'] == 4281892568 and capacity['new_max_metadata'] == 116 and
         capacity['new_max_records'] == 15165072 and capacity['new_max_output'] == 7375567454 and
         capacity['actual_authorized'] is False and capacity['fullblock_qualified'] is False,
         'capacity-only source scope differs')
    need(set(provenance['omitted_machine_bound_metadata']) == {'overlay/BUDGET_PROPOSAL.json', 'OVERLAY_PINS.json'} and
         not (set(provenance['omitted_machine_bound_metadata']) & set(content)), 'omitted exact metadata included')
    trees = {name: ast.parse(value, filename=name) for name, value in content.items() if name.endswith('.py')}
    for name, function in (
            ('overlay/admission.py', '_load_genuine_git'),
            ('overlay/integration/interface.py', '_load_admission_bridge'),
            ('overlay/integration/runtime_support/native_artifact.py', '_load_parent_adapter')):
        matches = [n for n in trees[name].body if isinstance(n, ast.FunctionDef) and n.name == function]
        need(len(matches) == 1, 'exact source loader helper required')
        node = matches[0]
        calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
        need({'compile', 'exec'} <= {n.func.id for n in calls if isinstance(n.func, ast.Name)} and
             not any(isinstance(n.func, ast.Attribute) and n.func.attr in
                     ('exec_module', 'spec_from_file_location', 'module_from_spec') for n in calls),
             'source-byte loading structure differs')
        compiled = [n for n in calls if isinstance(n.func, ast.Name) and n.func.id == 'compile']
        need(len(compiled) == 1 and isinstance(compiled[0].args[0], ast.Name) and
             compiled[0].args[0].id == 'raw' and
             {k.arg: ast.literal_eval(k.value) for k in compiled[0].keywords} ==
             {'dont_inherit': True, 'optimize': 0}, 'exact raw-byte compile flags required')
        strings = {n.value for n in ast.walk(trees[name]) if isinstance(n, ast.Constant) and type(n.value) is str}
        need('REVIEWED_FIXED93_M128_PUBLIC21_ACTUAL' in strings, 'fullblock authority status missing')
        if name != 'overlay/integration/runtime_support/native_artifact.py':
            need('fixed93-fullblock-admission-v1' in strings, 'fullblock authority schema missing')
        need(not ({'fixed93-startup-probe-admission-v1', 'REVIEWED_FIXED93_STARTUP_PROBE_ACTUAL',
                   'first_x.advance_to_request', 'integration/startup_probe.py'} & strings),
             'startup-only authority or stop boundary transferred')
    builder = trees['prepare_fullblock.py']
    constants = {n.value for n in ast.walk(builder) if isinstance(n, ast.Constant) and type(n.value) is str}
    need('integration/runner.py' in constants and 'integration/startup_probe.py' not in constants and
         provenance['full_entry'] == 'integration/runner.py', 'full runner source assembly contract differs')
    fields = {n.targets[0].id: ast.literal_eval(n.value) for n in builder.body
              if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and
              n.targets[0].id in ('BUDGET_STATUS', 'NUMERIC_DELTA')}
    need(fields['BUDGET_STATUS'] == 'REVIEWED_FIXED93_FULLBLOCK_BUDGET' and len(fields['NUMERIC_DELTA']) == 6,
         'exact fullblock budget declaration and six-leaf delta required')
    return dict(status='PASS_PUBLIC_BYTES_AND_AST_ONLY', public_manifest_sha256=manifest_sha,
        public_content_files=9, total_public_files=10, copied_python_overlays=3,
        copied_capacity_contracts=1, parsed_python_files=len(trees),
        builder_byte_identical=True, original_overlay_after_pins_match=True,
        production_modules_imported=False, production_functions_executed=False,
        builder_executed=False, materialization_executed=False, preflight_executed=False, native_executed=False,
        Git_executed=False, model_executed=False, advance_calls=0,
        internal_40_case_result_inherited=False, independent_review=False, actual_semantic_pass=False,
        one_cpu=len(os.sched_getaffinity(0)) == 1, address_space_limit_bytes=128 * 1024 * 1024,
        elapsed_seconds=time.monotonic()-started, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


if __name__ == '__main__':
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'use python -I -S -B')
    resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (10,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024,) * 2)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('public check deadline')))
    signal.setitimer(signal.ITIMER_REAL, 10)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--manifest-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.package, args.manifest_sha), sort_keys=True))
