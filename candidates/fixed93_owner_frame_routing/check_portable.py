"""Verify portable source hashes and compile in memory; never run test code."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent
MANIFEST_NAME = 'MANIFEST.json'
STAGE_FILES = (
    'tests.py',
    'generator_controls.py',
    'overlay/cached_wholeblock.py',
    'overlay/narrow_fullblock_attention.py',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def relative_name(value):
    require(type(value) is str, 'file name must be a string')
    path = PurePosixPath(value)
    require(bool(value) and not path.is_absolute() and path.as_posix() == value
            and all(part not in ('.', '..') for part in path.parts)
            and '\\' not in value and ':' not in value,
            'unsafe or non-canonical relative name: ' + repr(value))
    return value


def verify(expected_manifest_sha=None):
    manifest_path = ROOT / MANIFEST_NAME
    require(not manifest_path.is_symlink(), 'manifest must not be a symlink')
    raw = manifest_path.read_bytes()
    manifest_sha = digest(raw)
    if expected_manifest_sha is not None:
        require(manifest_sha == expected_manifest_sha,
                'external manifest SHA-256 mismatch')
    manifest = json.loads(raw)
    require(manifest.get('schema') == 'attention-frame-routing-portable-v1',
            'unexpected manifest schema')
    require(manifest.get('actual_execution_authorized') is False,
            'manifest must not confer actual authority')
    entries = manifest['files']
    require(type(entries) is dict and entries, 'missing file inventory')
    names = {relative_name(name) for name in entries}
    require(MANIFEST_NAME not in names, 'manifest cannot hash itself')
    actual = set()
    allowed_dirs = set()
    for name in names:
        allowed_dirs.update(str(p) for p in PurePosixPath(name).parents
                            if str(p) != '.')
    for path in ROOT.rglob('*'):
        rel = path.relative_to(ROOT).as_posix()
        require(not path.is_symlink(), 'symlink is not portable: ' + rel)
        if path.is_dir():
            require(rel in allowed_dirs, 'unlisted directory: ' + rel)
        else:
            require(path.is_file(), 'non-regular package entry: ' + rel)
            actual.add(rel)
    require(actual == names | {MANIFEST_NAME}, 'package file inventory mismatch')
    contents = {}
    for name in sorted(names):
        pin = entries[name]
        require(type(pin) is dict and type(pin.get('bytes')) is int
                and pin['bytes'] >= 0 and type(pin.get('sha256')) is str,
                'invalid pin: ' + name)
        content = (ROOT / name).read_bytes()
        require(len(content) == pin['bytes'] and digest(content) == pin['sha256'],
                'size/SHA-256 mismatch: ' + name)
        contents[name] = content
    compiled = []
    for name, content in contents.items():
        if name.endswith('.py'):
            compile(content, name, 'exec', dont_inherit=True)
            compiled.append(name)
    return manifest, contents, manifest_sha, compiled


def prepare_tests(destination, manifest, contents, manifest_sha):
    require(not destination.is_symlink() and not destination.exists(),
            'test stage must be a new, nonexistent directory')
    destination = destination.resolve()
    require(destination != ROOT and ROOT not in destination.parents,
            'test stage must be outside the portable package')
    require(destination.parent.is_dir(), 'test stage parent must already exist')
    for name in STAGE_FILES:
        require(name in contents, 'missing stage source: ' + name)
    stage_manifest = {
        'schema': 'attention-frame-routing-portable-test-stage-v1',
        'scope': 'SOURCE/SYNTHETIC RESTAGING ONLY; not original frozen evidence',
        'actual_execution_authorized': False,
        'policy_id': manifest['policy_id'],
        'portable_manifest_sha256': manifest_sha,
        'original_provenance': manifest['original_provenance'],
        'files': {name: manifest['files'][name] for name in STAGE_FILES},
        'test_inputs': manifest['test_inputs'],
    }
    stage_raw = (json.dumps(stage_manifest, indent=2, sort_keys=True) + '\n').encode()
    destination.mkdir()
    for name in STAGE_FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(contents[name])
    with (destination / 'SOURCE_MANIFEST.json').open('xb') as output:
        output.write(stage_raw)
    return {'status': 'PREPARED_NOT_EXECUTED',
            'source_manifest_sha256': digest(stage_raw),
            'files': [*STAGE_FILES, 'SOURCE_MANIFEST.json'],
            'baseline_copied': False, 'behavioral_tests_run': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-sha256', help='separately trusted package manifest SHA-256')
    parser.add_argument('--prepare-tests', type=Path, metavar='NEW_DIRECTORY',
                        help='prepare a fresh synthetic-only stage without running tests')
    args = parser.parse_args()
    manifest, contents, manifest_sha, compiled = verify(args.manifest_sha256)
    result = {'status': 'PASS_PORTABLE_HASH_COMPILE_ONLY',
              'manifest_sha256': manifest_sha, 'verified_files': len(contents),
              'compiled_python_files': compiled,
              'candidate_code_executed': False, 'behavioral_tests_run': False,
              'actual_execution_authorized': False}
    if args.prepare_tests is not None:
        result['test_preparation'] = prepare_tests(
            args.prepare_tests, manifest, contents, manifest_sha)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
