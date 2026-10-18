#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline source-only candidate. Default preflight does not assemble/import a recipe.

The explicit assembly mode, for a later separately approved action, replays fixed
project text and one pinned, source-only Python rebase helper. It never downloads,
spawns a subprocess, compiles Scala, elaborates hardware, or executes a model.
"""
import argparse
import difflib
import hashlib
import json
import re
import sys
import tempfile
import types
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
HF_PREFIX = 'hardfloat_snapshot/hardfloat/src/main/scala/'
CANDIDATE_PREFIX = 'candidates/qwen2_resident_matrix/host93_source_recovery/'
PLAN_SHA256 = '963b338d5ba80aaf6e16f05c697fd62a448ab2a9dbcc96d36d49c4b83b26c2e2'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode_json(data):
    return json.loads(data, object_pairs_hook=unique_object)


def relative(name):
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_./+-]+', name), 'unsafe path')
    path = PurePosixPath(name)
    require(path.parts and not path.is_absolute() and str(path) == name and
            all(x not in ('.', '..') for x in path.parts), 'unsafe relative path: ' + name)
    return path


def clean_path(path):
    path = Path(path).absolute()
    require('..' not in path.parts, 'path traversal')
    require(all(not item.is_symlink() for item in (path, *path.parents)), 'symlink path')
    return path


def read_regular(root, name, cap=2*1024*1024):
    relative(name)
    path = clean_path(root / name)
    require(path.is_file() and path.is_relative_to(root.absolute()), 'missing regular input: ' + name)
    require(path.stat().st_size <= cap, 'input byte cap: ' + name)
    with path.open('rb') as handle:
        data = handle.read(cap + 1)
    require(len(data) <= cap, 'input grew past cap: ' + name)
    return data


def verify_map(sources, pins, label):
    require(set(sources) == set(pins), label + ' inventory drift')
    for name, expected in pins.items():
        relative(name)
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'bad digest')
        require(digest(sources[name]) == expected, label + ' hash drift: ' + name)


def patch_entries(patch):
    """Parse a constrained unified diff. No offsets, fuzz, rename, deletion or binary patch."""
    lines = patch.splitlines(keepends=True)
    require(lines and all(x.endswith(b'\n') for x in lines), 'complete newline-terminated patch required')
    i, entries, seen = 0, [], set()
    while i < len(lines):
        old_header = lines[i]
        require(old_header.startswith(b'--- a/') or old_header == b'--- /dev/null\n', 'old patch path')
        create = old_header == b'--- /dev/null\n'
        i += 1
        require(i < len(lines) and lines[i].startswith(b'+++ b/'), 'new patch path')
        name = lines[i][6:-1].decode('utf-8'); relative(name)
        require(create or old_header == b'--- a/' + name.encode() + b'\n', 'no renames')
        require(name not in seen, 'duplicate patch target'); seen.add(name); i += 1
        hunks = []
        while i < len(lines) and not lines[i].startswith(b'--- '):
            match = re.fullmatch(rb'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[i])
            require(match is not None, 'exact unified hunk required')
            a, ac, b, bc = (int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1))
            require((a > 0 or ac == 0) and (b > 0 or bc == 0), 'valid hunk position')
            i += 1; old, new = [], []
            while i < len(lines) and not lines[i].startswith((b'@@ ', b'--- ')):
                line = lines[i]; require(line[:1] in (b' ', b'+', b'-'), 'patch body')
                if line[:1] != b'+': old.append(line[1:])
                if line[:1] != b'-': new.append(line[1:])
                i += 1
            require((len(old), len(new)) == (ac, bc), 'hunk line counts')
            hunks.append((a-1 if ac else a, b-1 if bc else b, old, new))
        require(hunks, 'empty patch entry')
        entries.append((name, create, hunks))
    return entries


def patch_sources(sources, patch, *, reverse=False, insertion_only=False):
    result = dict(sources)
    for name, create, hunks in patch_entries(patch):
        require(not (reverse and create), 'reverse creation unsupported')
        require((name not in sources) if create else (name in sources), 'patch target existence')
        original = (b'' if create else sources[name]).splitlines(keepends=True)
        cursor, output = 0, []
        for a, b, old, new in hunks:
            if insertion_only:
                require(not create, 'tap must change an existing file')
                changes = difflib.SequenceMatcher(None, b''.join(old), b''.join(new), autojunk=False)
                require(all(tag in ('equal', 'insert') for tag, *_ in changes.get_opcodes()),
                        'tap changes existing bytes')
            pos, target, before, after = (b, a, new, old) if reverse else (a, b, old, new)
            require(cursor <= pos <= len(original), 'ordered exact hunk position')
            output.extend(original[cursor:pos])
            require(len(output) == target, 'new hunk position drift')
            require(original[pos:pos+len(before)] == before, 'exact hunk context drift')
            output.extend(after); cursor = pos + len(before)
        output.extend(original[cursor:]); result[name] = b''.join(output)
    return result


def preflight(repo, plan_path=HERE/'SOURCE_REPLAY_PLAN.json'):
    """Static byte/manifest checks only; do not replay production or import its helper."""
    repo = clean_path(repo)
    require(repo.is_dir(), 'repository directory missing')
    plan_raw = read_regular(clean_path(plan_path.parent), plan_path.name)
    require(digest(plan_raw) == PLAN_SHA256, 'fixed source replay plan drift')
    plan = decode_json(plan_raw)
    require(plan['schema'] == 'host93-source-replay-v1' and plan['source_count'] == 93 and
            plan['production_source_count'] == 92 and plan['bench_sources'] == [] and
            plan['old_95_identity_inherited'] is False, 'new Host-only93 scope required')
    frozen = {}
    for name, expected in plan['input_sha256'].items():
        if name.startswith(CANDIDATE_PREFIX):
            require(name == plan['emitter']['source'], 'only the new emitter comes from this candidate')
            data = read_regular(HERE, name[len(CANDIDATE_PREFIX):], plan['source_file_bytes_cap'])
        else:
            data = read_regular(repo, name, plan['source_file_bytes_cap'])
        require(digest(data) == expected, 'project input drift: ' + name)
        frozen[name] = data
    require(sum(map(len, frozen.values())) <= plan['consumed_project_bytes_cap'], 'total project input cap')
    base = plan['rebase']['expected92']
    require(len(base) == 92 and sum(x.startswith(HF_PREFIX) for x in base) == 20, '72 project + 20 HardFloat')
    require(all(x.endswith('.scala') and not re.search(r'(Bench|Spec)\.scala$', x) for x in base),
            'production source set must exclude Bench/Spec')
    for source_set in (plan['production_seed'], plan['donor']['seed'], plan['donor']['owner_seed']):
        verify_map({name: frozen[name] for name in source_set}, source_set, 'source seed')
    fix = plan['silu_fix']; fixed = frozen[fix['replacement']]
    before, after = fix['old_expression'].encode(), fix['new_expression'].encode()
    require(fixed.count(after) == 1 and before not in fixed, 'fixed SiLU source expression')
    reconstructed = fixed.replace(after, before)
    require(digest(reconstructed) == base[fix['logical']], 'exact SiLU single-expression backprojection')
    expected = dict(base); expected[fix['logical']] = digest(fixed)
    for tap in plan['taps']:
        name = tap['logical']; old, new, patch = (frozen[tap[k]] for k in ('baseline','candidate','patch'))
        require(digest(old) == expected[name], 'tap baseline differs from repaired92: ' + name)
        forward = patch_sources({name:old}, patch, insertion_only=True)
        backward = patch_sources({name:new}, patch, reverse=True, insertion_only=True)
        require(forward == {name:new} and backward == {name:old}, 'exact tap projection')
        expected[name] = digest(new)
    emitter = plan['emitter']
    require(emitter['target'] not in expected and emitter['emission_top'] == 'HostBlockCollection' and
            emitter['execution_top'] == 'HostBlockTop' and emitter['single_common_namespace'] is True,
            'same-namespace original Host required')
    expected[emitter['target']] = digest(frozen[emitter['source']])
    require(expected == plan['expected93'] and len(expected) == 93, 'derived93 manifest drift')
    return plan, frozen, digest(plan_raw)


def write_tree(root, sources):
    root.mkdir(parents=True, exist_ok=False)
    for name, data in sorted(sources.items()):
        relative(name); path = root/name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as handle: handle.write(data)


def inventory(root):
    result = {}
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'output symlink')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def source_module(name, path, raw, expected_sha256):
    # Same fixed-buffer pattern as the published source-recovery cold loader.
    # Hash and execute the identical supplied bytes; never ask a project pyc loader.
    require(digest(raw) == expected_sha256, 'project source bytes differ before execution')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def assemble(repo, hardfloat_scala, output):
    """Future explicit source-only action. Not called by cold tests or default preflight."""
    plan, frozen, plan_sha = preflight(repo)
    repo, hf, output = clean_path(repo), clean_path(hardfloat_scala), clean_path(output)
    require(hf.is_dir() and output.parent.is_dir() and not output.exists(), 'fresh output and existing roots')
    require(not any(output.is_relative_to(x) or x.is_relative_to(output) for x in (repo,hf,HERE)),
            'output must be disjoint from repository, candidate and HardFloat input trees')
    base92 = plan['rebase']['expected92']
    hf_files = {name: read_regular(hf, name[len(HF_PREFIX):])
                for name in base92 if name.startswith(HF_PREFIX)}
    verify_map(hf_files, {k:v for k,v in base92.items() if k.startswith(HF_PREFIX)}, 'HardFloat20')
    require({p.name for p in hf.iterdir() if p.is_file()} == {x[len(HF_PREFIX):] for x in hf_files} and
            all(p.is_file() and not p.is_symlink() for p in hf.iterdir()), 'exact flat HardFloat20 directory')
    production = {name:frozen[name] for name in plan['production_seed']}
    for stage in plan['production_stages']:
        production = patch_sources(production, frozen[stage['patch']])
        verify_map(production, stage['expected'], 'production stage')
    d = plan['donor']; donor = {name:frozen[name] for name in d['seed']}
    for patch in d['base_patches']: donor = patch_sources(donor, frozen[patch])
    donor[d['client_target']] = frozen[d['client_source']]
    verify_map(donor, d['stream_expected'], 'stream donor')
    donor.update({name:frozen[name] for name in d['owner_seed']})
    donor = patch_sources(donor, frozen[d['owner_patch']]); verify_map(donor, d['owner_expected'], 'owner donor')
    donor = patch_sources(donor, frozen[d['qk16_patch']]); verify_map(donor, d['qk16_expected'], 'qk16 donor')
    # The only project Python recipe executed is this fixed source-only rebase helper.
    # Freeze its bytes and its own SOURCE_PINS.json together, so later repo edits cannot change it.
    with tempfile.TemporaryDirectory(prefix='.host93-source-', dir=output.parent) as temporary:
        work = Path(temporary); write_tree(work/'production', production); write_tree(work/'donor', donor)
        helper = work/'helper'; helper.mkdir()
        (helper/'build_source.py').write_bytes(frozen[plan['rebase']['helper']])
        (helper/'SOURCE_PINS.json').write_bytes(frozen[plan['rebase']['helper_pins']])
        module = source_module('_fixed_host93_rebase', helper/'build_source.py',
                               frozen[plan['rebase']['helper']],
                               plan['input_sha256'][plan['rebase']['helper']])
        module.compose(work/'production', work/'donor', work/'overlay')
        overlay = inventory(work/'overlay')
        selected = {name: (hf_files[name] if name in hf_files else
                           overlay[name] if name in overlay else production[name]) for name in base92}
        verify_map(selected, base92, 'reconstructed production92')
        fix = plan['silu_fix']; selected[fix['logical']] = frozen[fix['replacement']]
        for tap in plan['taps']: selected[tap['logical']] = frozen[tap['candidate']]
        selected[plan['emitter']['target']] = frozen[plan['emitter']['source']]
        verify_map(selected, plan['expected93'], 'new derived93')
        # Publish only after all stage pins pass. No prior output can be reused.
        output.mkdir(exist_ok=False); write_tree(output/'scala', selected)
        verify_map(inventory(output/'scala'), plan['expected93'], 'published93')
        receipt = {'status':'PASS_NEW_DERIVED_HOST93_SOURCE_ONLY', 'source_count':93,
                   'source_sha256':plan['expected93'], 'recipe_sha256':plan_sha,
                   'historical95_identity_inherited':False, 'compiler_started':False,
                   'elaboration_started':False, 'rtl_generated':False, 'hardware_executed':False}
        with (output/'SOURCE_RECEIPT.json').open('x') as handle:
            handle.write(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--assemble-reviewed-source', action='store_true')
    parser.add_argument('--hardfloat-scala', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.assemble_reviewed_source:
        require(args.hardfloat_scala is not None and args.output is not None, 'assembly roots required')
        report = assemble(args.repo, args.hardfloat_scala, args.output)
        print(json.dumps({k:v for k,v in report.items() if k != 'source_sha256'}, sort_keys=True))
    else:
        require(args.hardfloat_scala is None and args.output is None, 'preflight accepts no output or external source')
        plan, frozen, identity = preflight(args.repo)
        print(json.dumps({'status':'PASS_STATIC_HOST93_PLAN_ONLY', 'source_count_planned':93,
                          'recipe_sha256':identity, 'source_inputs_checked':len(frozen),
                          'source_assembled':False, 'external_recipe_loaded':False,
                          'compiler_started':False, 'elaborated':False, 'rtl_generated':False}, sort_keys=True))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'use python -I -S -B')
    main()
