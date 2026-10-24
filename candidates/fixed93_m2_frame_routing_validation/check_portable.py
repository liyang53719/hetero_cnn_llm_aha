"""Hash an exact portable excerpt and compile Python in memory, never execute it."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-sha256', help='separately trusted manifest SHA-256')
    args = parser.parse_args()
    manifest_path = ROOT / 'MANIFEST.json'
    require(not manifest_path.is_symlink(), 'manifest must not be a symlink')
    raw = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(raw).hexdigest()
    if args.manifest_sha256 is not None:
        require(manifest_sha == args.manifest_sha256, 'external manifest SHA-256 mismatch')
    manifest = json.loads(raw)
    require(manifest.get('schema') == 'single-m2-frame-routing-portable-excerpt-v1',
            'unexpected manifest schema')
    require(manifest.get('actual_execution_authorized') is False
            and manifest.get('standalone_executable') is False,
            'excerpt must not claim actual authority or standalone execution')
    files = manifest['files']
    require(type(files) is dict and bool(files), 'missing file inventory')
    allowed_dirs = set()
    for name in files:
        require(type(name) is str, 'file name must be a string')
        p = PurePosixPath(name)
        require(p.parts and not p.is_absolute() and p.as_posix() == name
                and all(part not in ('.', '..') for part in p.parts)
                and '\\' not in name and ':' not in name
                and name != 'MANIFEST.json', 'unsafe relative file name')
        allowed_dirs.update(str(parent) for parent in p.parents if str(parent) != '.')
    actual = set()
    for p in ROOT.rglob('*'):
        name = p.relative_to(ROOT).as_posix()
        require(not p.is_symlink(), 'symlink is not portable: ' + name)
        if p.is_dir():
            require(name in allowed_dirs, 'unlisted directory: ' + name)
        else:
            require(p.is_file(), 'non-regular package entry: ' + name)
            actual.add(name)
    require(actual == set(files) | {'MANIFEST.json'}, 'file inventory mismatch')
    compiled = []
    total = 0
    for name, pin in sorted(files.items()):
        require(type(pin) is dict and type(pin.get('bytes')) is int
                and pin['bytes'] >= 0 and type(pin.get('sha256')) is str,
                'invalid pin: ' + name)
        content = (ROOT / name).read_bytes()
        require(len(content) == pin['bytes']
                and hashlib.sha256(content).hexdigest() == pin['sha256'],
                'size/SHA-256 mismatch: ' + name)
        total += len(content)
        if name.endswith('.py'):
            compile(content, name, 'exec', dont_inherit=True)
            compiled.append(name)
    print(json.dumps({
        'status': 'PASS_PORTABLE_HASH_COMPILE_ONLY',
        'manifest_sha256': manifest_sha,
        'verified_files_excluding_manifest': len(files),
        'total_files_including_manifest': len(files) + 1,
        'total_bytes_including_manifest': total + len(raw),
        'compiled_python_files': compiled,
        'candidate_code_executed': False,
        'tests_or_actual_work_rerun': False,
        'standalone_executable': False,
        'actual_execution_authorized': False,
    }, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
