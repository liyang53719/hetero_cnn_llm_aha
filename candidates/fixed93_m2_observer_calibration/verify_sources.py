"""Inert stdlib-only integrity/compile checker. Never imports captured sources."""
import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

SOURCE_NAMES = (
    'decode_diff.py', 'git_read_preflight.py', 'import_closure_preflight.py',
    'm2_authority.py', 'm2_context.py', 'm2_entry.py', 'm2_io.py',
    'm2_runtime.py', 'm2_supervision_gate.py', 'narrow_fullblock_attention.py',
    'native_adapter.py', 'run_pair.py', 'success_driver.py', 'tests.py',
)
EXPECTED = {'source/' + name for name in SOURCE_NAMES} | {
    'README.md', 'SUMMARY.md', 'SCOPE.json', 'verify_sources.py',
}
# Directory-name patterns are generic. No original machine path is embedded.
PRIVATE_ROOTS = ('workspace', 'home', 'Users', 'mnt', 'media', 'Volumes',
                 'tmp', 'root', 'opt', 'private/var', 'var/folders')
PRIVATE_PATH = re.compile(r'(?<![A-Za-z0-9_])/(?:' + '|'.join(PRIVATE_ROOTS) + r')/[^\s\"\']+')
WINDOWS_PATH = re.compile(r'(?<![A-Za-z0-9_])[A-Za-z]:[\\/]')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def relative_name(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name,
            'invalid relative name')
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and
            str(path) == name and name not in ('.', ''), 'unsafe relative name')
    return name


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def validate_pin(raw, expected):
    require(expected == pin(raw), 'length/hash mismatch')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def private_path_scan(raw):
    text = raw.decode('utf-8')
    require(not PRIVATE_PATH.search(text) and not WINDOWS_PATH.search(text),
            'potential private absolute path in source text')
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            require(not PRIVATE_PATH.search(node.value) and not WINDOWS_PATH.search(node.value),
                    'potential private absolute path in source literal')


def self_test():
    cases = 0
    def reject(function):
        nonlocal cases
        try:
            function()
        except (ValueError, SyntaxError):
            cases += 1
            return
        raise ValueError('negative self-test failed')
    require(relative_name('source/example.py') == 'source/example.py', 'relative path test')
    cases += 1
    for bad in ('../escape.py', '/absolute.py', 'a/../b', 'a//b', 'C:\\example.py'):
        reject(lambda value=bad: relative_name(value))
    validate_pin(b'abc', pin(b'abc')); cases += 1
    reject(lambda: validate_pin(b'changed', pin(b'abc')))
    reject(lambda: parse(b'{"same":1,"same":2}'))
    reject(lambda: compile('def broken(:', '<synthetic>', 'exec'))
    reject(lambda: private_path_scan(('x = ' + repr('/' + 'home' + '/synthetic/file')).encode()))
    private_path_scan(b'x = "relative/file"\n'); cases += 1
    compile(b'x = 1\n', '<synthetic>', 'exec', dont_inherit=True); cases += 1
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    # Read only this small, exact inventory, refusing symlinks and oversized files.
    inventory = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'symlink in bundle')
        if path.is_file():
            require(path.stat().st_size <= 2 * 1024 * 1024, 'unexpected large file')
            inventory.add(path.relative_to(root).as_posix())
        else:
            require(path.is_dir(), 'special file in bundle')
    require(inventory == EXPECTED | {'MANIFEST.json', 'SHA256SUMS'}, 'unexpected file inventory')
    manifest = parse((root / 'MANIFEST.json').read_bytes())
    require(manifest['schema'] == 'portable-m2-source-review-v1', 'manifest schema')
    require(set(manifest['files']) == EXPECTED, 'manifest file inventory')
    count = 0
    total = 0
    for name in sorted(EXPECTED):
        relative_name(name)
        raw = (root / name).read_bytes()
        validate_pin(raw, manifest['files'][name])
        total += len(raw)
        if name.endswith('.py'):
            if name.startswith('source/'):
                private_path_scan(raw)
            compile(raw, name, 'exec', dont_inherit=True, optimize=0)
            count += 1
    expected_sums = ''.join(
        hashlib.sha256((root / name).read_bytes()).hexdigest() + '  ' + name + '\n'
        for name in sorted(EXPECTED | {'MANIFEST.json'})
    )
    require((root / 'SHA256SUMS').read_text() == expected_sums, 'SHA256SUMS mismatch')
    cases = self_test() if args.self_test else 0
    print(json.dumps({'status': 'PASS_SOURCE_COMPILE_HASH_ONLY',
        'original_sources': len(SOURCE_NAMES), 'python_files_compiled': count,
        'pinned_files': len(EXPECTED), 'pinned_bytes': total,
        'self_tests': cases, 'captured_source_execution': False,
        'native_or_model_execution': False, 'authority_created': False}, sort_keys=True))


if __name__ == '__main__':
    main()
