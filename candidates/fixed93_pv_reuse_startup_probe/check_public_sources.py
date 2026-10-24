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
    need(manifest['schema'] == 'fixed93-startup-public-excerpt-manifest-v1' and
         manifest['actual_authorized'] is False, 'public source-only scope required')
    pins = manifest['files']
    need(type(pins) is dict and len(pins) == manifest['file_count'] == 17 and
         sum(value['bytes'] for value in pins.values()) == manifest['total_file_bytes'] <= MAX_TOTAL,
         'exact small public inventory required')
    actual = set()
    for path in root.rglob('*'):
        need(not path.is_symlink(), 'public symlink refused')
        if path.is_file():
            actual.add(str(path.relative_to(root)))
        else:
            need(path.is_dir(), 'public special file refused')
    need(actual == set(pins) | {'MANIFEST.json'}, 'unmanifested/missing public file')
    content = {name: read(root, name) for name in pins}
    need(all(identity(content[name]) == pin for name, pin in pins.items()), 'public content pin differs')
    need(not private_literal(raw.decode()) and
         all(not private_literal(value.decode()) for value in content.values()), 'private machine root literal found')
    provenance = parse(content['PUBLIC_PINS.json'])
    need(provenance['published_overlay_count'] == 12 and provenance['original_overlay_count'] == 14 and
         provenance['public_is_not_replacement_package'] is True and
         provenance['execution_authorized'] is False and provenance['original_38_case_result_inherited'] is False,
         'exact source-excerpt provenance scope required')
    need(identity(content['prepare_probe.py']) == provenance['original_builder'], 'unchanged builder bytes differ')
    entries = provenance['published_python_overlays']
    need(len(entries) == 12 and all(name.endswith('.py') for name in entries), 'twelve original Python overlays required')
    for name, value in entries.items():
        relative(name)
        need(identity(content['overlay/' + name]) == value['after'] ==
             provenance['all_original_overlay_pins'][name]['after'], 'original overlay after pin differs')
    trees = {name: ast.parse(raw, filename=name) for name, raw in content.items() if name.endswith('.py')}
    worker = trees['overlay/supervision/worker.py']
    imported = [node.module for node in ast.walk(worker) if isinstance(node, ast.ImportFrom) and
                (node.module or '').startswith('integration.')]
    need(imported == ['integration.startup_probe'], 'worker entry differs')
    probe = trees['overlay/integration/startup_probe.py']
    need(not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and
                 node.func.attr == 'advance_to_request' for node in ast.walk(probe)), 'first advance call in probe')
    for name, function in (
            ('overlay/admission.py', '_load_genuine_git'),
            ('overlay/integration/interface.py', '_load_admission_bridge'),
            ('overlay/integration/runtime_support/native_artifact.py', '_load_parent_adapter')):
        node = next(n for n in trees[name].body if isinstance(n, ast.FunctionDef) and n.name == function)
        calls = [n.func for n in ast.walk(node) if isinstance(n, ast.Call)]
        need({'compile', 'exec'} <= {n.id for n in calls if isinstance(n, ast.Name)} and
             not any(isinstance(n, ast.Attribute) and n.attr == 'exec_module' for n in calls),
             'source-byte loading structure differs')
    guard = trees['overlay/supervision/gate.py']
    values = {n.targets[0].id: ast.literal_eval(n.value) for n in guard.body
              if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and
              n.targets[0].id in ('PUBLIC_TOTAL_CEILING_SECONDS', 'CLEANUP_SECONDS', 'POST_SECONDS')}
    need(values == dict(PUBLIC_TOTAL_CEILING_SECONDS=45, CLEANUP_SECONDS=5, POST_SECONDS=10), 'timing constants differ')
    return dict(status='PASS_PUBLIC_BYTES_AND_AST_ONLY', public_manifest_sha256=manifest_sha,
        public_content_files=17, copied_python_overlays=12, parsed_python_files=len(trees),
        builder_byte_identical=True, original_overlay_after_pins_match=True,
        production_modules_imported=False, production_functions_executed=False,
        builder_executed=False, preflight_executed=False, native_executed=False,
        Git_executed=False, model_executed=False, advance_calls=0,
        internal_38_case_result_inherited=False, independent_review=False, actual_semantic_pass=False,
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
