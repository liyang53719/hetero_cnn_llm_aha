"""Verify the portable M16 excerpt; never import or execute candidate code."""
import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
SOURCE_NAMES = frozenset(('success_driver.py', 'parent/seal_check.py', 'tests.py'))


def need(condition, message):
    if not condition:
        raise ValueError(message)


def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def parse(raw):
    def bad(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)


def identity(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-sha256', help='separately trusted manifest SHA-256')
    args = parser.parse_args()
    path = ROOT / 'MANIFEST.json'
    need(path.is_file() and not path.is_symlink(), 'manifest must be regular, not a symlink')
    raw = path.read_bytes()
    manifest_sha = hashlib.sha256(raw).hexdigest()
    if args.manifest_sha256 is not None:
        need(manifest_sha == args.manifest_sha256, 'external manifest SHA-256 mismatch')
    manifest = parse(raw)
    need(manifest.get('schema') == 'single-m16-scale-portable-excerpt-v1', 'unexpected schema')
    for flag in ('standalone_executable', 'actual_execution_authorized',
                 'prior_execution_authority_inherited', 'M128_authorized',
                 'fullblock_authorized', 'publication_authorized'):
        need(manifest.get(flag) is False, 'excerpt cannot grant authority: ' + flag)
    need(set(manifest['exact_frozen_source_files']) == SOURCE_NAMES, 'source set mismatch')
    files = manifest['files']
    need(type(files) is dict and bool(files), 'missing file inventory')
    allowed_dirs = set()
    for name in files:
        need(type(name) is str, 'file name must be a string')
        p = PurePosixPath(name)
        need(p.parts and not p.is_absolute() and p.as_posix() == name
             and all(part not in ('.', '..') for part in p.parts)
             and '\\' not in name and ':' not in name and name != 'MANIFEST.json',
             'unsafe relative file name')
        allowed_dirs.update(str(p) for p in p.parents if str(p) != '.')
    actual = set()
    for p in ROOT.rglob('*'):
        name = p.relative_to(ROOT).as_posix()
        need(not p.is_symlink(), 'symlink is not portable: ' + name)
        if p.is_dir():
            need(name in allowed_dirs, 'unlisted directory: ' + name)
        else:
            need(p.is_file(), 'non-regular package entry: ' + name)
            actual.add(name)
    need(actual == set(files) | {'MANIFEST.json'}, 'file inventory mismatch')
    contents, compiled, total = {}, [], 0
    for name, expected in sorted(files.items()):
        need(type(expected) is dict and type(expected.get('bytes')) is int
             and 0 <= expected['bytes'] <= 1048576
             and type(expected.get('sha256')) is str, 'invalid pin: ' + name)
        content = (ROOT / name).read_bytes()
        need(identity(content) == expected, 'size/SHA-256 mismatch: ' + name)
        contents[name] = content
        total += len(content)
        if name.endswith('.py'):
            ast.parse(content, filename=name)
            compile(content, name, 'exec', dont_inherit=True)
            compiled.append(name)
    source_pins = parse(contents['SOURCE_PINS.json'])
    need(source_pins['schema'] == 'single-m16-scale-relative-source-pins-v1'
         and source_pins['copied_byte_for_byte'] is True
         and source_pins['original_source_manifest_included'] is False
         and source_pins['machine_paths_included'] is False, 'source provenance boundary')
    need(set(source_pins['files']) == SOURCE_NAMES, 'relative source inventory mismatch')
    for name in SOURCE_NAMES:
        need(source_pins['files'][name] == files[name], 'original source pin mismatch: ' + name)
    need(source_pins['source_manifest'] == manifest['original_provenance']['source_manifest'],
         'source manifest provenance mismatch')
    print(json.dumps(dict(status='PASS_PORTABLE_HASH_AST_COMPILE_ONLY',
        manifest_sha256=manifest_sha, verified_files_excluding_manifest=len(files),
        total_files_including_manifest=len(files)+1,
        total_bytes_including_manifest=total+len(raw), compiled_python_files=compiled,
        candidate_code_executed=False, original_tests_or_actual_rerun=False,
        omitted_evidence_revalidated=False, standalone_executable=False,
        actual_execution_authorized=False), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
