#!/usr/bin/env python3
"""Current source compatibility only; historical numerical results are never inherited."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

BASE = '55199873c0d5378c53538cc4273b53a3a012915d'
OWNER = 'candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py'
REPLACEMENTS = {
    OWNER: ('8f954329ef7a4ae472b8247e6e34456affee2e946f1fcfb439b19d89d2b786ec',
            '65d823ebebdb50cae98c0ff8c9c1c5631ebc298595cc5c28c71ba7a22890f6d8'),
    'scripts/observe_qwen2_attention_model.py': ('c061da563c079cd3866c661382df5600980ae11e659909a7f0520ce41878ba9f', '18446e01900f81c6bbf9cf211c1df6b9a86b06013e6d7ef8ae8609eea2309a45'),
    'candidates/qwen2_resident_matrix/official_bf16/observation.py': ('bd671f58c73d4a2ab808968c40589f395dc17d25a00b0aa71eb236f5419fb744', '13ec64d2f8985256d4bdf78595a628eb106a79117e62c728ac3e486d09e4f627'),
    'candidates/qwen2_resident_matrix/dense_block_reduce/observation.py': ('90c129e9bf57a234927822439705090d68be2c23b86fd8db61a1ba3a6bafeede', '881c82ae6628b29ea641b639065f6a527a7802f6a134f5d9807421ebb44335c3'),
}
PACKAGES = {
    'qkv16': ('qwen2_live_qkv_model', 136, ('qwen2_live_qkv_model', 'qwen2_live_qkv_inputs')),
    'qkv128': ('qwen2_live_qkv_model_m128', 139, ('qwen2_live_qkv_model_m128', 'qwen2_live_qkv_inputs_m128')),
    'attention128': ('qwen2_live_attention_model_m128', 154, ('qwen2_live_attention_model_m128',)),
    'attention16': ('qwen2_live_attention_model_m16', 177, ('qwen2_live_attention_model_m16', 'qwen2_live_attention_reference_m16', 'qwen2_live_attention_model_m128')),
}
# These event-only sources are not historical numerical source substitutions.
EVENT_FILES = (
    'scripts/check_attention_cold_compatibility.py',
    'scripts/test_attention_cold_compatibility.py',
    'scripts/check_generated_source_consistency.py',
    'candidates/qwen2_resident_matrix/ffn_attention/test_memory_debt.py',
    'candidates/qwen2_attention_resident_candidate/test_scratch_ownership.py',
    'candidates/qwen2_attention_resident_candidate/scratch.py',
    'candidates/qwen2_attention_resident_candidate/owner.py',
    'candidates/qwen2_live_attention_model_m128/pv32_owner.py',
)


PROTOCOL_PINS = {'candidates/qwen2_attention_resident_candidate/scratch.py': 'a0ff924f054bb67cd9c1c1285cc293e17b01e1241aba1d3bcac0062c28b3d4cf', 'candidates/qwen2_attention_resident_candidate/owner.py': '303d21c299d1bc25d2e1cdba0c7aa3def8b444f936682cef21cebc2300261318', 'candidates/qwen2_live_attention_model_m128/pv32_owner.py': '67924e28218c6d423d7a607909984c010f3b09ccac4e2200870f3003b76e747a', 'candidates/qwen2_resident_matrix/ffn_attention/test_memory_debt.py': 'c3e333ec59f501db634600b5b0d23bcf3e4b50f78a848ea93b5a4e28c923e809', 'candidates/qwen2_attention_resident_candidate/test_scratch_ownership.py': 'a1d9ac0cb5a0a06a8349a5e2ebf10f6f460c42d4b0696cadb50b0c150d5c638c'}

def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    # Local Git object inspection only. No fetch, network, or executed source.
    return subprocess.check_output(['git', '-C', str(root), *args],
                                   env={**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0'})


def read_source(root, name):
    p = PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and str(p) == name, 'unsafe source name')
    target = root / name
    require(target.is_file() and not target.is_symlink() and target.resolve() == target,
            'missing or aliased source: ' + name)
    return target.read_bytes()


def verify_files(root, expected):
    for name, digest in expected.items():
        require(sha(read_source(root, name)) == digest, 'source drift: ' + name)


def execution_inventory(historical, replacements):
    require(replacements == REPLACEMENTS, 'reviewed replacement identities changed')
    current = dict(historical)
    for name, pair in replacements.items():
        require(type(pair) is tuple and len(pair) == 2, 'invalid replacement')
        old, new = pair
        require(all(type(x) is str and len(x) == 64 and all(c in '0123456789abcdef' for c in x)
                    for x in pair) and old != new, 'invalid replacement identities')
        require(current.get(name) == old, 'historical replacement identity drift: ' + name)
        current[name] = new
    return current


def package_inventory(root, dirs):
    result = {}
    for directory in dirs:
        base = root / 'candidates' / directory
        require(base.is_dir() and not base.is_symlink(), 'missing package: ' + directory)
        for p in base.rglob('*'):
            # -B is mandatory in CI. An unexpected bytecode file fails closed too.
            require(not p.is_symlink(), 'aliased package source')
            if p.is_file():
                name = p.relative_to(root).as_posix()
                result[name] = sha(read_source(root, name))
    return result


def check(current, historical, kind, event_sha):
    current, historical = current.resolve(), historical.resolve()
    require(current != historical, 'lanes must have separate roots')
    require(git(historical, 'rev-parse', 'HEAD').decode().strip() == BASE, 'wrong historical HEAD')
    require(len(event_sha) == 40 and all(c in '0123456789abcdef' for c in event_sha), 'invalid event SHA')
    require(git(current, 'rev-parse', 'HEAD').decode().strip() == event_sha, 'wrong event HEAD')
    package, count, dirs = PACKAGES[kind]
    manifest = 'candidates/' + package + '/pins.json'
    raw = read_source(historical, manifest)
    require(raw == git(historical, 'show', BASE + ':' + manifest), 'historical manifest modified')
    dependencies = json.loads(raw)['dependency_sha256']
    require(type(dependencies) is dict and len(dependencies) == count, 'dependency cardinality drift')
    verify_files(historical, dependencies)
    frozen_package = package_inventory(historical, dirs)
    tracked = set(git(historical, 'ls-tree', '-r', '--name-only', BASE, '--',
                      *('candidates/' + d for d in dirs)).decode().splitlines())
    require(set(frozen_package) == tracked, 'historical package file set drift')
    for name in frozen_package:
        require(frozen_package[name] == sha(git(historical, 'show', BASE + ':' + name)), 'historical package modified')
    require(package_inventory(current, dirs) == frozen_package, 'current frozen package file set or bytes drift')
    execution = execution_inventory(dependencies, REPLACEMENTS)
    verify_files(current, execution)
    verify_files(current, PROTOCOL_PINS)
    event_sources = {}
    for name in EVENT_FILES:
        data = read_source(current, name)
        require(data == git(current, 'show', event_sha + ':' + name), 'uncommitted event source: ' + name)
        event_sources[name] = sha(data)
    return {
        'schema': 'qwen2_current_cold_compatibility_v1', 'status': 'SOURCE_COMPATIBLE',
        'historical_commit': BASE, 'event_commit': event_sha, 'package': kind,
        'historical_dependency_count': count, 'reviewed_replacements': REPLACEMENTS,
        'unchanged_dependency_count': count - 4, 'package_source_count': len(frozen_package),
        'package_source_sha256': sha(json.dumps(frozen_package, sort_keys=True).encode()),
        'current_dependency_sha256': execution, 'event_source_sha256': event_sources,
        'historical_suite_on_event_commit': False, 'numerical_results_inherited': False,
        'numeric_execution': False, 'fullblock_pass': False, 'rtl_executed': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical', type=Path, required=True)
    parser.add_argument('--current', type=Path, default=Path.cwd())
    parser.add_argument('--package', choices=PACKAGES, required=True)
    parser.add_argument('--event-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.current, args.historical, args.package, args.event_sha), sort_keys=True))


if __name__ == '__main__':
    main()
