#!/usr/bin/env python3
"""Isolate exactly pinned Git/profile dependencies; never run Git or model code.

Production main accepts only the four fixed input pins below. transform() and
stream_checked() are separate so tests need only synthetic JSON and tiny files.
A failed materialization leaves an incomplete fresh directory, without receipt.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import stat

CHUNK = 1024 * 1024
MAX_OUTPUT = 64 * 1024 * 1024
ANCHORS = {
    'runtime': {'bytes': 379526, 'sha256': 'c63292b6cd0be00f15578266f696e7e2b58733d58e1d1ea92fa8bb45e50fc76c'},
    'LINEAGE.json': {'bytes': 5231, 'sha256': '5847cce8b8cf3fa2ec8df675e6c323c16d6850acfc087e6334cc2a1d23165baa'},
    'MANIFEST.json': {'bytes': 1709, 'sha256': '074161fdb0165f1be7ebe20245dfad18ca7228a6b81a5e6a48812e7c7abd8485'},
    'git_profile.py': {'bytes': 3939, 'sha256': 'adb037af47c3894c5f29f310bdb3e03c739e60c3f8cbe58d3794e40a379817b4'},
}


def need(value, message):
    if not value:
        raise ValueError(message)


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def parse(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def canonical(path):
    p = Path(path)
    need(p.is_absolute() and str(p) == str(path) and '..' not in p.parts,
         'absolute normalized path required')
    return p


def path_chain(path):
    """Reject aliases and remember every ancestor's identity, not mutable mtime."""
    p = canonical(path)
    result = []
    for q in reversed(p.parents):
        s = q.lstat()
        need(stat.S_ISDIR(s.st_mode), 'normal source/output ancestors required')
        result.append((str(q), s.st_dev, s.st_ino))
    return tuple(result)


def stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size,
            s.st_mtime_ns, s.st_ctime_ns)


def regular(s):
    need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1,
         'normal non-aliased file with nlink=1 required')


def stream_checked(path, expected, destination=None, seen=None):
    """Hash and optionally copy from the same FD, with bounded memory and checks."""
    need(destination is not None or expected['bytes'] <= CHUNK, 'retained metadata limited to 1 MiB')
    p = canonical(path)
    chain = path_chain(p)
    before_path = p.lstat()
    regular(before_path)
    need(before_path.st_size == expected['bytes'], 'source size pin mismatch')
    identity = (before_path.st_dev, before_path.st_ino)
    if seen is not None:
        need(identity not in seen, 'duplicate source inode')
    out = None
    chunks = []
    digest = hashlib.sha256()
    count = 0
    try:
        with os.fdopen(os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
            opened = os.fstat(source.fileno())
            regular(opened)
            need(stamp(opened) == stamp(before_path), 'source replaced before open')
            if destination is not None:
                target = canonical(destination)
                target_chain = path_chain(target)
                out = target.open('xb')
                regular(os.fstat(out.fileno()))
            while True:
                block = source.read(CHUNK)
                if not block:
                    break
                count += len(block)
                need(count <= expected['bytes'], 'source grew during read')
                digest.update(block)
                if out is None:
                    chunks.append(block)
                else:
                    out.write(block)
            after = os.fstat(source.fileno())
            regular(after)
            after_path = p.lstat()
            regular(after_path)
            need(stamp(before_path) == stamp(opened) == stamp(after) == stamp(after_path)
                 and path_chain(p) == chain, 'source changed during read')
            need({'bytes': count, 'sha256': digest.hexdigest()} == expected,
                 'source content pin mismatch')
            if out is not None:
                out.flush()
                final = os.fstat(out.fileno())
                regular(final)
                regular(target.lstat())
                need(stamp(final) == stamp(target.lstat()) and final.st_size == count
                     and path_chain(target) == target_chain,
                     'output changed during write')
                need((final.st_dev, final.st_ino) != identity, 'source/output alias')
    finally:
        if out is not None:
            out.close()
    if seen is not None:
        seen.add(identity)
    return b''.join(chunks) if destination is None else None


def patch_profile(source, old_lineage_pin, new_lineage):
    """Preserve every AST node except the two exact LINEAGE binding literals."""
    old_sha = old_lineage_pin['sha256']
    new_pin = pin(new_lineage)
    old_text = source.decode()
    a = "LINEAGE_SHA='" + old_sha + "'"
    b = 'bytes=' + str(old_lineage_pin['bytes']) + ',sha256=LINEAGE_SHA'
    need(old_text.count(a) == old_text.count(b) == 1, 'exact profile binding literals')
    new_text = old_text.replace(a, "LINEAGE_SHA='" + new_pin['sha256'] + "'", 1)
    new_text = new_text.replace(b, 'bytes=' + str(new_pin['bytes']) + ',sha256=LINEAGE_SHA', 1)
    old_ast, new_ast = ast.parse(old_text), ast.parse(new_text)
    old_nodes, new_nodes = list(ast.walk(old_ast)), list(ast.walk(new_ast))
    need(len(old_nodes) == len(new_nodes), 'profile AST shape unchanged')
    changes = []
    for old, new in zip(old_nodes, new_nodes):
        if isinstance(old, ast.Constant) and isinstance(new, ast.Constant) and old.value != new.value:
            changes.append((old.value, new.value))
            new.value = old.value
    need(changes.count((old_sha, new_pin['sha256'])) == 1,
         'one SHA binding change required')
    expected = [(old_sha, new_pin['sha256'])]
    if old_lineage_pin['bytes'] != new_pin['bytes']:
        expected.append((old_lineage_pin['bytes'], new_pin['bytes']))
    need(sorted(map(repr, changes)) == sorted(map(repr, expected))
         and ast.dump(old_ast) == ast.dump(new_ast), 'only two binding literals may change')
    return new_text.encode()


def validate_runtime_delta(old, new, mapping, replacement_pins):
    need(len(old['files']) == len(new['files']) == 1638 and len(mapping) == 18,
         'exact 1638 runtime / 18 relocated inventory')
    need(len(set(mapping.values())) == 18, 'unique relocated paths')
    expected_files = {}
    for path, spec in old['files'].items():
        target = mapping.get(path, path)
        need(target not in expected_files, 'runtime destination collision')
        expected_files[target] = replacement_pins.get(path, spec)
    need(new['files'] == expected_files, 'no removed, mixed, extra or altered runtime pins')
    untouched = set(old['files']) - set(mapping)
    need(len(untouched) == 1620 and all(old['files'][p] == new['files'][p] for p in untouched),
         'exactly 1620 byte-identical remaining runtime pins')
    expected = copy.deepcopy(old)
    expected['files'] = expected_files
    old_head = str(Path(old['git_environment']['GIT_DIR']) / 'HEAD')
    old_manifest = str(Path(old['git_profile_root']) / 'MANIFEST.json')
    expected['git_environment']['GIT_DIR'] = str(Path(mapping[old_head]).parent)
    expected['git_profile_root'] = str(Path(mapping[old_manifest]).parent)
    expected['git_profile_manifest_sha256'] = replacement_pins[old_manifest]['sha256']
    expected['total_file_bytes'] = sum(x['bytes'] for x in expected_files.values())
    need(new == expected, 'runtime metadata delta outside allowed fields')


def transform(runtime, lineage_bytes, manifest_bytes, profile_source, output):
    """Pure metadata transform; no file reads, commands, imports or hash of packs."""
    output = canonical(output)
    lineage, manifest = parse(lineage_bytes), parse(manifest_bytes)
    old_profile = canonical(runtime['git_profile_root'])
    old_git = canonical(runtime['git_environment']['GIT_DIR'])
    need(not any(output == p or output.is_relative_to(p) or p.is_relative_to(output)
                 for p in (old_profile, old_git)), 'output/source roots must be disjoint')
    need(runtime['git_profile_manifest_sha256'] == pin(manifest_bytes)['sha256'], 'manifest binding')
    need(lineage['git_dir'] == str(old_git)
         and lineage['proposed_environment'] == runtime['git_environment'], 'Git environment binding')
    need(len(runtime['files']) == 1638
         and runtime['total_file_bytes'] == sum(s['bytes'] for s in runtime['files'].values()),
         'original runtime count/total')
    manifest_files = manifest['files']
    need(len(manifest_files) == 11 and all(Path(n).name == n and n not in ('.', '..', 'MANIFEST.json')
         for n in manifest_files), 'exact flat 11-file profile manifest')
    profile_pins = {**manifest_files, 'MANIFEST.json': pin(manifest_bytes)}
    need(profile_pins['LINEAGE.json'] == pin(lineage_bytes)
         and profile_pins['git_profile.py'] == pin(profile_source), 'profile binding pins')
    metadata = lineage['git_metadata']
    need(len(metadata) == 6 and len({s['path'] for s in metadata}) == 6, 'six distinct Git files')
    git_names = {str(canonical(s['path']).relative_to(old_git)) for s in metadata}
    packs = sorted(n for n in git_names if n.startswith('objects/pack/'))
    need(len(packs) == 3 and {Path(n).suffix for n in packs} == {'.idx', '.pack', '.rev'}
         and len({str(Path(n).with_suffix('')) for n in packs}) == 1
         and git_names == {'HEAD', 'config', 'shallow', *packs}, 'exact Git metadata inventory')
    old_pins = {str(old_profile / n): s for n, s in profile_pins.items()}
    old_pins.update({s['path']: {k: s[k] for k in ('bytes', 'sha256')} for s in metadata})
    related = {p for p in runtime['files'] if Path(p).is_relative_to(old_profile)
               or Path(p).is_relative_to(old_git)}
    need(len(old_pins) == 18 and related == set(old_pins), 'no missing or extra Git/profile runtime entries')
    need(all(runtime['files'][p] == s for p, s in old_pins.items()), 'all 18 old pins must match')
    head = (lineage['head'] + '\n').encode('ascii')
    need(pin(head) == old_pins[str(old_git / 'HEAD')]
         == old_pins[str(old_git / 'shallow')], 'fixed HEAD/shallow content pins')
    mapping = {str(old_profile / n): str(output / 'profile' / n) for n in profile_pins}
    mapping.update({s['path']: str(output / 'git' / Path(s['path']).relative_to(old_git)) for s in metadata})
    new_lineage = copy.deepcopy(lineage)
    new_lineage['git_dir'] = str(output / 'git')
    new_lineage['proposed_environment']['GIT_DIR'] = str(output / 'git')
    for spec in [new_lineage['committed_cpp'], *(x['artifact'] for x in new_lineage['object_lineage'])]:
        need(spec['path'] in mapping and Path(spec['path']).is_relative_to(old_profile), 'profile artifact path')
        need({k: spec[k] for k in ('bytes', 'sha256')} == old_pins[spec['path']], 'profile artifact binding')
        spec['path'] = mapping[spec['path']]
    for spec in new_lineage['git_metadata']:
        spec['path'] = mapping[spec['path']]
    new_lineage_bytes = encode(new_lineage)
    new_source = patch_profile(profile_source, pin(lineage_bytes), new_lineage_bytes)
    new_manifest = copy.deepcopy(manifest)
    new_manifest['files']['LINEAGE.json'] = pin(new_lineage_bytes)
    new_manifest['files']['git_profile.py'] = pin(new_source)
    generated = {'LINEAGE.json': new_lineage_bytes, 'git_profile.py': new_source,
                 'MANIFEST.json': encode(new_manifest)}
    replacements = {str(old_profile / n): pin(data) for n, data in generated.items()}
    new_runtime = copy.deepcopy(runtime)
    new_runtime['files'] = {mapping.get(p, p): replacements.get(p, s) for p, s in runtime['files'].items()}
    new_runtime['git_environment']['GIT_DIR'] = str(output / 'git')
    new_runtime['git_profile_root'] = str(output / 'profile')
    new_runtime['git_profile_manifest_sha256'] = pin(generated['MANIFEST.json'])['sha256']
    new_runtime['total_file_bytes'] = sum(s['bytes'] for s in new_runtime['files'].values())
    validate_runtime_delta(runtime, new_runtime, mapping, replacements)
    return new_runtime, mapping, old_pins, generated, head


def write_new(path, data):
    p = canonical(path)
    chain = path_chain(p)
    with p.open('xb') as f:
        f.write(data)
        f.flush()
        s = os.fstat(f.fileno())
        regular(s)
        need(stamp(s) == stamp(p.lstat()) and s.st_size == len(data)
             and path_chain(p) == chain, 'stable fresh output file')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-pins', required=True)
    parser.add_argument('--profile-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    profile_root, output = canonical(args.profile_root), canonical(args.output)
    seen = set()
    raw_runtime = stream_checked(args.runtime_pins, ANCHORS['runtime'], seen=seen)
    runtime = parse(raw_runtime)
    need(str(profile_root) == runtime['git_profile_root'], 'profile root must match pinned logical root')
    raw = {n: stream_checked(profile_root / n, ANCHORS[n], seen=seen)
           for n in ('LINEAGE.json', 'MANIFEST.json', 'git_profile.py')}
    updated, mapping, old_pins, generated, head = transform(
        runtime, raw['LINEAGE.json'], raw['MANIFEST.json'], raw['git_profile.py'], output)
    runtime_bytes = encode(updated)
    files = {str(Path(target).relative_to(output)): updated['files'][target] for target in mapping.values()}
    files['RUNTIME_PINS.json'] = pin(runtime_bytes)
    receipt = {
        'schema': 1, 'status': 'SOURCE_DEPENDENCY_ISOLATION_ONLY_NOT_DUT_ADMISSION',
        'snapshot_root': str(output), 'git_dir': str(output / 'git'),
        'profile_root': str(output / 'profile'),
        'source_runtime_path': str(canonical(args.runtime_pins)),
        'source_profile_root': str(profile_root),
        'source_git_dir': runtime['git_environment']['GIT_DIR'],
        'source_profile_pins': {n: ANCHORS[n] for n in raw},
        'old_runtime_pin': ANCHORS['runtime'], 'new_runtime_pin': pin(runtime_bytes),
        'old_to_new_path': mapping, 'unchanged_count': 1620, 'runtime_count': 1638,
        'snapshot_files': files, 'profile_files': {n: files['profile/' + n] for n in (*parse(raw['MANIFEST.json'])['files'], 'MANIFEST.json')},
        'head_reconstructed_from_pinned_lineage': True,
        'no_git_command': True, 'no_profile_verify': True, 'no_native': True, 'no_model': True,
        'source_builder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'output_limit_bytes': MAX_OUTPUT,
    }
    receipt_bytes = encode(receipt)
    total = sum(s['bytes'] for s in files.values()) + len(receipt_bytes)
    need(total <= MAX_OUTPUT, 'snapshot exceeds 64 MiB including runtime and receipt')
    path_chain(output)
    output.mkdir(mode=0o700)  # Must be fresh, never merge/overwrite an existing tree.
    for name in ('git', 'git/objects', 'git/objects/info', 'git/objects/pack', 'git/refs', 'profile'):
        (output / name).mkdir(mode=0o700)
    old_git = Path(runtime['git_environment']['GIT_DIR'])
    for source, target in mapping.items():
        p = Path(source)
        if p == old_git / 'HEAD':
            write_new(target, head)  # Deliberately never open the mutable old HEAD.
        elif p.parent == profile_root and p.name in generated:
            write_new(target, generated[p.name])
        else:
            stream_checked(p, old_pins[source], target, seen)
    write_new(output / 'RUNTIME_PINS.json', runtime_bytes)
    # Receipt is the last write and never purports to hash itself.
    write_new(output / 'SNAPSHOT_RECEIPT.json', receipt_bytes)
    print(json.dumps({'output': str(output), 'file_bytes': total,
                      'runtime_pin': pin(runtime_bytes), 'receipt_pin': pin(receipt_bytes)}, sort_keys=True))


if __name__ == '__main__':
    main()
