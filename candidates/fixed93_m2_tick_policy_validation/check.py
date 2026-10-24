"""Check a source excerpt using hashes and compilation only, never execution."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parent

def need(condition, message):
    if not condition:
        raise ValueError(message)

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def relative(name):
    path = PurePosixPath(name)
    need(not path.is_absolute() and '..' not in path.parts and str(path) == name, 'unsafe relative path')
    return name

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original-source', type=Path, help='Optional original source root, read-only pin verification')
    args = p.parse_args()
    manifest = json.loads((ROOT / 'PORTABLE_MANIFEST.json').read_bytes())
    need(manifest['schema'] == 'single-m2-tick-policy-public-source-excerpt-v1', 'manifest schema')
    entries = list(ROOT.rglob('*'))
    need(not any(q.is_symlink() for q in entries), 'symlink in package')
    found = {q.relative_to(ROOT).as_posix() for q in entries if q.is_file()}
    need(found == set(manifest['publish_whitelist']), 'finite publication whitelist mismatch')
    need(found == set(manifest['files']) | {'PORTABLE_MANIFEST.json'}, 'manifest file closure')
    private = re.compile(r'(?<![A-Za-z0-9_:])/(?:workspace|home|Users|mnt|tmp|opt|var|root)/[^\s\"\'<>]*')
    windows = re.compile(r'\b[A-Za-z]:[\\/]')
    compiled = []
    for name in sorted(found):
        raw = (ROOT / relative(name)).read_bytes()
        if name != 'PORTABLE_MANIFEST.json':
            need(pin(raw) == manifest['files'][name], 'file pin: ' + name)
        text = raw.decode('utf-8')
        need(private.search(text) is None and windows.search(text) is None, 'private machine path: ' + name)
        if name.endswith('.py'):
            compile(text, name, 'exec', dont_inherit=True, optimize=0)
            compiled.append(name)
    for name, source in manifest['source_files'].items():
        expected = {k: source[k] for k in ('bytes', 'sha256')}
        need(manifest['files'][name] == expected, 'original source bytes: ' + name)
        if args.original_source is not None:
            raw = (args.original_source / relative(source['source_relative_path'])).read_bytes()
            need(pin(raw) == expected, 'external original pin: ' + name)
    summary = json.loads((ROOT / 'SUMMARY.json').read_bytes())
    need(summary['provenance'] == manifest['provenance'], 'summary provenance')
    need(summary['status'] == 'CONFIRMED_SINGLE_M2_TICK_POLICY_HISTORICAL_EQUIVALENCE_ONLY', 'limited status')
    need(summary['post_exit_inventory'] == {'files': 51, 'bytes': 6014897}, 'closed-file inventory')
    equality = summary['equivalence']
    need(equality['all33_field_presence_output_files_exact_size_SHA_equal'] and equality['transport_exact_size_SHA_equal'], 'field/transport comparison')
    need(equality['attention_records'] == 8565 and equality['wholeblock_records'] == 2211 and equality['decoded_semantic_differences'] == {}, 'decoded comparison')
    need(equality['opaque_ID_difference_rows'] == 11011 and sum(equality['opaque_ID_category_counts'].values()) == 11011, 'bounded opaque ID differences')
    need(not equality['short_lived_cross_run_alias_equivalence_proven'], 'no unsupported alias claim')
    timing = summary['main_loop_timing']
    for domain in ('cpu', 'wall'):
        old = timing['historical_0503_cache'][domain + '_seconds']
        new = timing['current_0526_tick_policy'][domain + '_seconds']
        need(abs(100 * (old - new) / old - timing[domain + '_reduction_percent']) < 1e-10, 'timing arithmetic')
    accept = summary['acceptance']
    need(all(accept[k] is False for k in ('numerical_acceptance', 'M128_acceptance', 'RTL_pass', 'fullblock_pass', 'fullblock_seal_called')), 'acceptance overclaim')
    policy = summary['policy_contract']
    need(policy['full_identity_frequency_changed'] is True and policy['old_every_callback_integrity_equivalent'] is False and policy['same_tick_transient_ABI_profile_restore_can_evade_full_check'] is True, 'weaker integrity contract must be explicit')
    need(manifest['files']['source/TICK_POLICY.json'] == policy['policy_pin'], 'exact actual-bound policy pin')
    need(summary['run_boundary']['old_unsealed_stream_read'] is False and summary['packaging']['actual_or_source_tests_rerun'] is False, 'execution boundary')
    print(json.dumps({'status': 'PASS_STATIC_PUBLIC_EXCERPT_CHECK', 'files': len(found),
                      'source_files': len(manifest['source_files']), 'compiled_not_executed': len(compiled),
                      'external_original_pins_verified': args.original_source is not None,
                      'actual_or_source_tests_executed': False,
                      'actual_evidence_independently_reverified': False}, sort_keys=True))

if __name__ == '__main__':
    main()
