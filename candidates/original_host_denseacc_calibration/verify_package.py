#!/usr/bin/env python3
"""Verify public text identities and finite evidence boundaries, never native code."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json
HERE = Path(__file__).resolve().parent

def require(value, message):
    if not value:
        raise ValueError(message)

def load(name):
    return json.loads((HERE / name).read_text())

def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def verify(repo=None):
    manifest = load('MANIFEST.json')
    expected = manifest['files']
    actual = {str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file()}
    require(actual == set(expected) | {'MANIFEST.json'}, 'exact small file allowlist')
    total = 0
    for name, row in expected.items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts, 'safe relative path')
        path = HERE / name
        require(not path.is_symlink() and path.is_file(), 'regular public text')
        data = path.read_bytes()
        require(identity(data) == row, 'identity: ' + name)
        data.decode('utf-8')
        require(b'\0' not in data and not data.startswith(b'\x7fELF'), 'not binary')
        require(b'/work' + b'space/' not in data and b'/home/' + b'agent/' not in data, 'no private paths')
        require(len(data) <= 64 * 1024, 'small per-file cap')
        require(path.suffix in {'.json', '.md', '.py', '.scala', '.cpp', '.in'}, 'source-only extensions')
        require(path.suffix != '.cpp' or name == 'source/denseacc_calibration_driver.cpp', 'no generated C++')
        total += len(data)
    require(total < 256 * 1024, 'small package cap')
    source = load('SOURCE_PINS.json')
    for row in source['sources']:
        require(identity((HERE / row['path']).read_bytes()) == row['published'], 'source pin')
        if not row['path_only_portability_changes']:
            require(row['original'] == row['published'], 'unchanged actual source')
    facts = load('ACTUAL_FACTS.json')
    observed = facts['observed']
    require(observed == dict(alias_checks=200704, beat_domain=16, clocked_cycles=17,
                            full_word_capacity=4096, pair_checks=401408, row_domain=32,
                            scans=49, witness_checks=401408, words_per_read=16, write_masks=8), 'exact actual counters')
    require(observed['scans'] * 32 * 16 * 16 == observed['pair_checks'] == observed['witness_checks'], 'comparison arithmetic')
    require(observed['scans'] * 16 * 16 * 16 == observed['alias_checks'], 'alias arithmetic')
    require(facts['five_block_M128_Chisel_RTL'] == '0/5 unchanged' and facts['packager_native_tests'] == 0, 'qualification scope')
    warnings = load('WARNING_CLASSIFICATION.json')
    require(sum(r['count'] for r in warnings['classes']) == 65520, 'all warning classes')
    require(warnings['counts'] == dict(ADD_8_RHS=16, EQ_4_LHS=32752, EQ_8_LHS=32752, WIDTHEXPAND=65520), 'warning totals')
    history = load('FAILURE_HISTORY.json')['entries']
    build = next(r for r in history if r['stage'] == '2141')
    require(build['status'] == 'FAIL_PRESERVED' and build['native_exit'] == 0 and build['outer_exit'] == 1, 'preserve original build failure')
    classes = load('CLASS_RECOVERY.json')
    require(len(classes['exclude_diagnostic_main3']) == 3 and len(classes['add_exact_support16']) == 16 and len(classes['add_fifo3']) == 3 and len(classes['actual_new37']) == 37, 'class stages')
    require(883 - 3 + 16 + 3 + 37 == classes['emission_class_count'] == 936, '936 class reconstruction')
    dependencies = load('DEPENDENCY_PINS.json')['ordered_maven_classpath']
    require(len(dependencies) == 106 and len({(r['root_role'], r['path']) for r in dependencies}) == 106, '106 exact ordered dependencies')
    recipe = load('REPRODUCTION.json')
    argv = recipe['commands']['diagnostic1335']['recorded_role_command']['argv']
    require('-Wno-fatal' in argv and not any(a.startswith('-Wno-') and a != '-Wno-fatal' for a in argv), 'warnings retained, not suppressed')
    require(recipe['build_translation_units'] == 28 and recipe['generated_units'] == 25 and recipe['unknown_role_count'] == 0, 'complete recipe roles')
    refs = load('PUBLIC_REFERENCES.json')
    if repo is not None:
        for row in refs['references']:
            path = Path(repo) / row['path']
            require(path.is_file() and not path.is_symlink(), 'source reference exists: ' + row['path'])
            data = path.read_bytes()
            require(identity(data) == {k: row[k] for k in ('bytes', 'sha256')}, 'exact pinned source reference: ' + row['path'])
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            require(blob == row['git_blob_sha'], 'Git blob identity')
    return dict(status='PASS_PUBLIC_SOURCE_AND_METADATA_ONLY', files=len(actual),
                bytes=total + (HERE / 'MANIFEST.json').stat().st_size,
                source_references=len(refs['references']), repository_refs_verified=repo is not None,
                native_tests=0, five_block_M128_Chisel_RTL='0/5 unchanged')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.repo), sort_keys=True))

if __name__ == '__main__':
    main()
