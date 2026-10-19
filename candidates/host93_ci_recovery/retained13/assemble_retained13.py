#!/usr/bin/env python3
"""Portable, offline retained13 projection. No --out means static pins only."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('use python -I -S -B run_retained13.py')
if globals().get('__verified_entry__') != 'ci-retained13-v1':
    raise SystemExit('fixed same-buffer entry required')

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import resource
import signal
import stat
import time
import types

HERE = Path(__file__).absolute().parent
PLAN_PIN = {'bytes': 26494, 'sha256': 'f4418409f1a460428926529df23f2a6c48b1e3af5d8d7818604264d2e98ed89e'}
HELPER_PIN = {'bytes': 15592, 'sha256': '75a2145eea0de83ad1bbe3a7a64e1a5f14f20f9f1381f65e619fb5bd3d427641'}
ORIGINAL_PIN = {'bytes': 118060, 'sha256': '963b338d5ba80aaf6e16f05c697fd62a448ab2a9dbcc96d36d49c4b83b26c2e2'}
FILE_CAP, TREE_CAP, REPORT_CAP = 2*1024*1024, 8*1024*1024, 512*1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def verify(raw, pin, label):
    require(identity(raw) == pin, 'fixed size/SHA256 mismatch: ' + label)


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate JSON key')
        value[key] = item
    return value


def clean(path):
    path = Path(path).absolute()
    require('..' not in path.parts and all(not p.is_symlink() for p in (path, *path.parents)), 'unsafe path')
    return path


def read(root, name, cap=FILE_CAP):
    rel = PurePosixPath(name)
    require(rel.parts and not rel.is_absolute() and str(rel) == name and
            all(p not in ('.', '..') for p in rel.parts), 'unsafe relative source')
    path = clean(root/name)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= cap, 'input type/size cap')
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            raw = handle.read(cap + 1)
        after = os.fstat(fd)
        require(len(raw) <= cap and (before.st_size, before.st_mtime_ns) ==
                (after.st_size, after.st_mtime_ns), 'input changed during read')
        return raw
    finally:
        os.close(fd)


def limits():
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, set()), 'inherited SIGALRM blocked')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'inherited ITIMER_REAL occupied')
    os.umask(0o077)
    def expired(signum, frame):
        raise RuntimeError('60-second total wall limit')
    remaining = 60.0 - (time.monotonic() - __entry_started__)
    require(remaining > 0, 'entry exhausted wall budget')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    for kind, amount in ((resource.RLIMIT_CPU, 40), (resource.RLIMIT_AS, 512*1024*1024),
                         (resource.RLIMIT_FSIZE, 4*1024*1024), (resource.RLIMIT_NOFILE, 64),
                         (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(kind, (amount, amount))
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})


def preflight(repo):
    raw = read(HERE, 'SOURCE_PLAN.json')
    verify(raw, PLAN_PIN, 'source plan')
    plan = json.loads(raw, object_pairs_hook=unique)
    require(plan['schema'] == 'ci-retained13-source-v1' and plan['old_candidate_review_inherited'] is False,
            'new CI candidate identity required')
    frozen = {name: read(repo, name) for name in plan['input_pins']}
    require(len(frozen) == 96 and sum(map(len, frozen.values())) <= TREE_CAP, 'input inventory/total cap')
    for name, raw in frozen.items():
        verify(raw, plan['input_pins'][name], name)
    verify(frozen[plan['helper']], HELPER_PIN, 'published patch helper')
    verify(frozen[plan['original_plan']], ORIGINAL_PIN, 'published production plan')
    original = json.loads(frozen[plan['original_plan']], object_pairs_hook=unique)
    stages, seed = original['production_stages'], original['production_seed']
    require(len(seed) == 76 and sum(n.endswith('.scala') for n in seed) == 70 and
            sum(n.endswith('.sv') for n in seed) == 6, '76 seed identity')
    require([s['patch'] for s in stages] == plan['production_stages'] and
            [len(s['expected']) for s in stages] == plan['production_stage_counts'] == [76, 76, 76, 77] and
            all(set(s) == {'patch', 'expected'} for s in stages), 'unknown production stage')
    required = set(seed) | set(plan['production_stages']) | set(plan['unchanged_seven']) | {
        plan['original_plan'], plan['helper'], plan['lint_plan'], plan['retained_list'], plan['front_baseline']
    } | {fix[k] for fix in plan['front_fixes'] for k in ('patch', 'reference')}
    require(required == set(frozen), 'unknown or unconsumed input')
    for name, expected in seed.items():
        require(plan['input_pins'][name]['sha256'] == expected, 'seed identity drift')
    for name in plan['production_stages']:
        require(plan['input_pins'][name]['sha256'] == original['input_sha256'][name], 'patch identity drift')
    six = {n: h for n, h in stages[-1]['expected'].items() if n.endswith('.sv')}
    expected = {**six, plan['front']: plan['input_pins'][plan['front_fixes'][-1]['reference']]['sha256'],
                **plan['unchanged_seven']}
    require(six == plan['production_six'] and len(six) == 6 and len(plan['unchanged_seven']) == 7 and
            len(expected) == 13 and expected == plan['expected13'] and
            len(plan['source_order']) == 13 and set(plan['source_order']) == set(expected), 'exact final13 identity')
    lint = json.loads(frozen[plan['lint_plan']], object_pairs_hook=unique)
    for name, expected_hash in expected.items():
        require(any(e['path'].endswith('/'+name) and e['sha256'] == expected_hash
                    for e in lint['source_order']), 'historical lint source pin mismatch')
    return plan, original, frozen


def helper_module(raw, path):
    verify(raw, HELPER_PIN, 'helper before compile')
    module = types.ModuleType('_ci_retained13_fixed_patch')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def unchanged(repo, plan, frozen):
    for name, expected in frozen.items():
        require(read(repo, name) == expected, 'source changed: ' + name)
    verify(read(HERE, 'SOURCE_PLAN.json'), PLAN_PIN, 'plan after')
    verify(read(HERE, Path(__file__).name), __runner_pin__, 'runner after')


def project(plan, original, frozen, helper):
    production = {n: frozen[n] for n in original['production_seed']}
    helper.verify_map(production, original['production_seed'], 'production76')
    chains = {n: [{'stage': 'seed', 'path': n, **identity(production[n])}] for n in plan['production_six']}
    for stage in original['production_stages']:
        production = helper.patch_sources(production, frozen[stage['patch']])
        helper.verify_map(production, stage['expected'], 'complete production postimage')
        for n in chains:
            chains[n].append({'patch': stage['patch'], 'patch_pin': identity(frozen[stage['patch']]),
                              **identity(production[n])})
    selected = {n: production[n] for n in plan['production_six']}
    helper.verify_map(selected, plan['production_six'], 'six production SV postimages')
    front = plan['front']
    require(selected[front] == frozen[plan['front_baseline']], 'front baseline mismatch')
    for fix in plan['front_fixes']:
        new = helper.patch_sources({front: selected[front]}, frozen[fix['patch']])
        helper.verify_map(new, {front: plan['input_pins'][fix['reference']]['sha256']}, fix['name'])
        require(new[front] == frozen[fix['reference']] and
                helper.patch_sources(new, frozen[fix['patch']], reverse=True) == {front: selected[front]},
                'front reference/reverse mismatch')
        selected[front] = new[front]
        chains[front].append({'stage': fix['name'], 'patch': fix['patch'],
                              'patch_pin': identity(frozen[fix['patch']]),
                              'reference': fix['reference'], **identity(new[front])})
    for name in plan['unchanged_seven']:
        selected[name] = frozen[name]
        chains[name] = [{'stage': 'unchanged_main_tree', 'path': name, **identity(frozen[name])}]
    helper.verify_map(selected, plan['expected13'], 'exact retained13')
    return selected, chains


def cold(helper):
    old, new = {'tiny.sv': b'a\nb\n'}, {'tiny.sv': b'a\nc\n'}
    patch = b'--- a/tiny.sv\n+++ b/tiny.sv\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n'
    require(helper.patch_sources(old, patch) == new and helper.patch_sources(new, patch, reverse=True) == old,
            'tiny exact projection failed')
    helper.verify_map(new, {'tiny.sv': identity(new['tiny.sv'])['sha256']}, 'tiny positive hash')
    rejected = 0
    for action in (lambda: helper.verify_map(new, {'tiny.sv': '0'*64}, 'bad postimage'),
                   lambda: helper.patch_sources({'tiny.sv': b'x\nb\n'}, patch),
                   lambda: helper.verify_map(new, {}, 'bad inventory'),
                   lambda: verify(b'x', {'bytes': 2, 'sha256': identity(b'x')['sha256']}, 'bad size'),
                   lambda: helper_module(b'raise RuntimeError("must not execute")\n', Path('tiny.py'))):
        try:
            action()
        except ValueError:
            rejected += 1
    require(rejected == 5, 'tiny negative case accepted')
    return {'status': 'PASS_TINY_COLD_ONLY', 'positive_cases': 3, 'negative_cases': rejected,
            'optimize': sys.flags.optimize, 'real_production_replayed': False, 'source_assembled': False}


def publish(repo, out, plan, original, frozen, helper):
    out = clean(out)
    require(out.parent.is_dir() and not out.exists(), 'fresh output with existing parent required')
    require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (repo, HERE)), 'overlapping output')
    selected, chains = project(plan, original, frozen, helper)
    unchanged(repo, plan, frozen)
    report = {'schema': 'ci-retained13-receipt-v1', 'status': 'PASS_RETAINED13_SOURCE_ONLY',
              'source_commit_basis': plan['source_commit'], 'source_count': 13, 'source_order': plan['source_order'],
              'source_pins': {n: identity(selected[n]) for n in plan['source_order']}, 'source_chains': chains,
              'input_pins_before': plan['input_pins'], 'input_pins_after': plan['input_pins'],
              'all_inputs_unchanged': True, 'plan_pin': PLAN_PIN, 'runner_pin': __runner_pin__,
              'production_stage_counts': [76, 76, 76, 77], 'native_started': False, 'downloaded': False,
              'scala_compiled': False, 'rebase_helper_executed': False, 'hardfloat_loaded': False,
              'idma_package_included': False, 'clock_included': False, 'simulation_started': False,
              'old_candidate_review_inherited': False}
    receipt = (json.dumps(report, indent=2, sort_keys=True)+'\n').encode()
    require(len(receipt) <= REPORT_CAP and sum(map(len, selected.values())) + len(receipt) <= TREE_CAP and
            all(len(data) <= 4*1024*1024 for data in selected.values()), 'output/report cap')
    out.mkdir(mode=0o700)
    source = out/'source'
    source.mkdir(mode=0o700)
    for name, raw in selected.items():
        path = source/name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open('xb') as handle:
            handle.write(raw)
    actual = set()
    for path in out.rglob('*'):
        require(not path.is_symlink(), 'output symlink')
        require(stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600), 'output mode')
        if path.is_file():
            actual.add(path.relative_to(source).as_posix())
    require(actual == set(selected), 'output inventory')
    for name, raw in selected.items():
        require(read(source, name) == raw, 'output bytes')
    unchanged(repo, plan, frozen)
    with (out/'SOURCE_RECEIPT.json').open('xb') as handle:
        handle.write(receipt)
    require(read(out, 'SOURCE_RECEIPT.json', REPORT_CAP) == receipt and
            stat.S_IMODE((out/'SOURCE_RECEIPT.json').stat().st_mode) == 0o600, 'receipt readback/mode')
    return {'status': report['status'], 'source_count': 13, 'output': str(out), 'receipt_pin': identity(receipt)}


def main():
    limits()
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--cold-test', action='store_true')
    args = parser.parse_args()
    require(not (args.out is not None and args.cold_test), 'cold test cannot publish')
    repo = clean(args.repo)
    plan, original, frozen = preflight(repo)
    if args.out is None and not args.cold_test:
        result = {'status': 'PASS_STATIC_PLAN_ONLY', 'input_count': 96, 'project_helper_executed': False,
                  'real_production_replayed': False, 'source_assembled': False}
    else:
        helper = helper_module(frozen[plan['helper']], repo/plan['helper'])
        result = cold(helper) if args.cold_test else publish(repo, args.out, plan, original, frozen, helper)
    unchanged(repo, plan, frozen)
    print(json.dumps(result, sort_keys=True))
    signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == '__main__':
    main()
