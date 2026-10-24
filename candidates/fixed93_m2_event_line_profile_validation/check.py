"""Statically check exact source excerpts; never import or execute those sources."""
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
    need(bool(name) and not path.is_absolute() and '..' not in path.parts and
         str(path) == name and '\\' not in name, 'unsafe relative path')
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-source', type=Path,
                        help='Optional original source root for read-only pin checks')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'PORTABLE_MANIFEST.json').read_bytes())
    need(manifest['schema'] == 'single-m2-event-line-profile-public-source-excerpt-v1',
         'manifest schema')
    entries = list(ROOT.rglob('*'))
    need(not any(p.is_symlink() for p in entries), 'package contains symlink')
    found = {p.relative_to(ROOT).as_posix() for p in entries if p.is_file()}
    need(len(manifest['publish_whitelist']) == len(set(manifest['publish_whitelist'])),
         'duplicate whitelist member')
    need(found == set(manifest['publish_whitelist']), 'finite whitelist mismatch')
    need(found == set(manifest['files']) | {'PORTABLE_MANIFEST.json'}, 'file closure')
    private = re.compile(r'(?<![A-Za-z0-9_:])/(?:workspace|home|Users|mnt|tmp|opt|var|root)/[^\s\"\'<>]*')
    windows = re.compile(r'\b[A-Za-z]:[\\/]')
    compiled = []
    for name in sorted(found):
        raw = (ROOT / relative(name)).read_bytes()
        if name != 'PORTABLE_MANIFEST.json':
            need(pin(raw) == manifest['files'][name], 'file pin: ' + name)
        text = raw.decode('utf-8')
        need(private.search(text) is None and windows.search(text) is None,
             'private machine path: ' + name)
        if name.endswith('.py'):
            compile(text, name, 'exec', dont_inherit=True, optimize=0)
            compiled.append(name)
    need(len(manifest['source_files']) == 20, '20 exact source/policy excerpts')
    if args.original_source is not None:
        raw = (args.original_source / 'SOURCE_MANIFEST.json').read_bytes()
        need(pin(raw) == manifest['provenance']['frozen_R2_source_manifest'],
             'original frozen R2 manifest')
    for name, source in manifest['source_files'].items():
        expected = {k: source[k] for k in ('bytes', 'sha256')}
        need(name == 'source/' + relative(source['source_relative_path']),
             'source path correspondence')
        need(manifest['files'][name] == expected, 'exact original bytes: ' + name)
        if args.original_source is not None:
            raw = (args.original_source / source['source_relative_path']).read_bytes()
            need(pin(raw) == expected, 'external source pin: ' + name)
    summary = json.loads((ROOT / 'SUMMARY.json').read_bytes())
    need(summary['provenance'] == manifest['provenance'], 'summary provenance')
    need(summary['status'] ==
         'CONFIRMED_SINGLE_M2_EVENT_LINE_PROFILE_HISTORICAL_EQUIVALENCE_ONLY',
         'limited historical status')
    run = summary['profiled_0557_run']
    need(run['post_exit_inventory'] == {'files': 53, 'bytes': 6603299}, 'profile inventory')
    eq = run['equivalence']
    need(eq['all33_field_presence_output_files_exact_size_SHA_equal'] and
         eq['transport_exact_size_SHA_equal'], 'field and transport equality')
    need(eq['attention_records'] == 8565 and eq['wholeblock_records'] == 2211 and
         eq['decoded_semantic_differences'] == {}, 'decoded semantic comparison')
    need(eq['opaque_ID_difference_rows'] == 11011 and
         sum(eq['opaque_ID_category_counts'].values()) == 11011 and
         eq['long_lived_mapping_count'] == 4, 'bounded ID differences')
    need(eq['short_lived_cross_run_alias_equivalence_proven'] is False and
         eq['raw_stream_bytes_identical'] is False, 'no stronger identity claim')
    sample = run['sampling']
    need(sample['samples'] == 1461 and sample['unique_stacks'] == 925 and
         sample['codes'] == 117 and sample['quality'] == 'COMPLETE_BOUNDED_SAMPLES',
         'reported sample summary')
    need(sample['restored'] is True and sample['active'] is False and
         all(value == 0 for value in sample['reported_loss_counters'].values()),
         'reported sampler state')
    need(sample['physical_timer_coverage_proven'] is False and
         sample['speed_measurement'] is False and sample['diagnostic_only'] is True,
         'sampling limits')
    need(sample['policy_pin'] == manifest['files']['source/SAMPLING_POLICY.json'],
         'sampling policy source pin')
    unsampled = summary['unsampled_0549_run']
    need(unsampled['post_exit_inventory'] == {'files': 51, 'bytes': 6014710} and
         unsampled['sampling_enabled'] is False, 'separate unsampled result')
    for domain in ('cpu', 'wall'):
        old = unsampled['historical_0526_main_loop'][domain + '_seconds']
        new = unsampled['new_main_loop'][domain + '_seconds']
        need(abs(100 * (old - new) / old -
                 unsampled[domain + '_reduction_percent']) < 1e-10,
             'unsampled historical timing arithmetic')
    policy = summary['policy_contract']
    need(policy['event_line_policy_pin'] == manifest['files']['source/EVENT_LINE_POLICY.json']
         and policy['nonconsumer_op_policy_pin'] == manifest['files']['source/POLICY.json'],
         'exact policy pins')
    need(policy['old_per_line_or_every_callback_integrity_equivalent'] is False,
         'explicit weaker integrity contract')
    auxiliary = summary['auxiliary_report_policy']
    need(auxiliary['quality_PARTIAL_alone_blocks_main_evidence'] is False and
         auxiliary['unsafe_or_active_sampler_restore_blocks_main_evidence'] is True and
         auxiliary['malformed_or_unbounded_accounting_blocks_main_evidence'] is True and
         auxiliary['main_seal_and_semantic_comparison_remain_required'] is True and
         auxiliary['sampling_quality_grants_model_or_fullblock_PASS'] is False,
         'auxiliary quality and main-evidence safety separation')
    need(auxiliary['old_0437_actual_FAIL_unchanged'] is True and
         auxiliary['R1_decoder_static_blocker_claim_retracted'] is True and
         auxiliary['R1_actual_executed'] is False and
         auxiliary['R1_runtime_blocker_proven'] is False,
         'no rewrite of historical failures or static correction')
    acceptance = summary['acceptance']
    need(acceptance['wholeblock_scope'] == 'INCOMPLETE_WHOLEBLOCK' and
         all(acceptance[k] is False for k in
             ('numerical_acceptance', 'independent_numeric_oracle', 'M128_acceptance',
              'RTL_pass', 'fullblock_pass', 'fullblock_seal_called')),
         'acceptance limits')
    packaging = summary['packaging']
    need(all(packaging[k] is False for k in
             ('actual_or_source_tests_rerun', 'source_imported_or_executed', 'native_loaded',
              'raw_profile_or_streams_read', 'old_unsealed_stream_read',
              'original_verified_source_bytes_modified', 'standalone_runtime_complete',
              'new_actual_authority')), 'packaging boundary')
    print(json.dumps({
        'status': 'PASS_STATIC_PUBLIC_EXCERPT_CHECK',
        'files': len(found), 'source_files': len(manifest['source_files']),
        'compiled_not_executed': len(compiled),
        'external_original_pins_verified': args.original_source is not None,
        'actual_or_source_tests_executed': False,
        'actual_evidence_independently_reverified': False,
        'standalone_runtime_complete': False}, sort_keys=True))


if __name__ == '__main__':
    main()
