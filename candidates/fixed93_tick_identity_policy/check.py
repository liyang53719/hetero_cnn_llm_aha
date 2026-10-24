"""Validate source pins and compile only; optionally stage an unchanged test."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parent

def need(condition, message):
    if not condition:
        raise ValueError(message)

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def relative(name):
    p = PurePosixPath(name)
    need(not p.is_absolute() and '..' not in p.parts and str(p) == name, 'unsafe relative path')
    return name

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, help='Exact external 0503 source root, read-only')
    parser.add_argument('--prepare-synthetic', type=Path, help='New persistent staging directory; never executes tests')
    args = parser.parse_args()
    need(args.prepare_synthetic is None or args.baseline is not None, 'staging requires --baseline')
    baseline = None if args.baseline is None else args.baseline.resolve()
    m = json.loads((ROOT / 'PORTABLE_MANIFEST.json').read_bytes())
    need(m['schema'] == 'tick-boundary-integrity-portable-source-excerpt-v1', 'schema')
    entries = list(ROOT.rglob('*'))
    need(not any(p.is_symlink() for p in entries), 'package symlink')
    actual = {p.relative_to(ROOT).as_posix() for p in entries if p.is_file()}
    need(actual == set(m['publish_whitelist']), 'publication whitelist mismatch')
    need(actual == set(m['files']) | {'PORTABLE_MANIFEST.json'}, 'manifest closure')
    private = re.compile(r'(?<![A-Za-z0-9_:])/(?:workspace|home|Users|mnt|tmp|opt|var|root)/[^\s\"\'<>]*')
    windows = re.compile(r'\b[A-Za-z]:[\\/]')
    compiled = []
    for name in sorted(actual):
        raw = (ROOT / relative(name)).read_bytes()
        if name != 'PORTABLE_MANIFEST.json':
            need(pin(raw) == m['files'][name], 'package pin: ' + name)
        text = raw.decode('utf-8')
        need(private.search(text) is None and windows.search(text) is None, 'private machine path: ' + name)
        if name.endswith('.py'):
            compile(text, name, 'exec', dont_inherit=True, optimize=0)
            compiled.append(name)
    for name, expected in m['unchanged_original_files'].items():
        need(m['files'][name] == expected, 'frozen source bytes: ' + name)
    baseline_raw = {}
    if baseline is not None:
        for name, expected in m['external_baseline_inputs'].items():
            raw = (baseline / relative(name)).read_bytes()
            need(pin(raw) == expected, 'external baseline pin: ' + name)
            baseline_raw[name] = raw
        before = baseline_raw['narrow_fullblock_attention.py'].decode('utf-8')
        after = (ROOT / 'overlay/narrow_fullblock_attention.py').read_text()
        expected_patch = ''.join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile='baseline/narrow_fullblock_attention.py', tofile='overlay/narrow_fullblock_attention.py'))
        need(expected_patch == (ROOT / 'observer.patch').read_text(), 'exact observer patch')
    s = json.loads((ROOT / 'SUMMARY.json').read_bytes())
    need(s['provenance'] == m['provenance'], 'summary provenance')
    need(s['status'] == 'GO_TICK_BOUNDARY_METADATA_INTEGRITY_SOURCE_SYNTHETIC_ONLY', 'source-only status')
    cold = s['author_synthetic_result']
    need(sum(cold['controls'].values()) == cold['control_count'] == 46, 'control count')
    need(cold['scalar_consumers'] == 6 and cold['field_slots'] == 40, 'retained scalar evidence')
    need(cold['full_check_counts'] == {'400_ticks_new_full': 800, '400_ticks_old_full': 8400,
                                     'scalar_new_full': 2, 'scalar_old_full': 46}, 'full-check selection')
    need(s['integrity_limit']['old_every_callback_integrity_equivalent'] is False and
         s['integrity_limit']['same_tick_transient_ABI_profile_restore_can_evade_full_check'] is True, 'policy weakening disclosure')
    need(all(s['qualification'][k] is False for k in ('actual_authorized', 'actual_execution_authorized',
        'M128_authorized', 'numerical_acceptance', 'RTL_pass', 'fullblock_pass')), 'qualification overclaim')
    report = {'status': 'PASS_PORTABLE_STATIC_SOURCE_CHECK', 'files': len(actual),
              'compiled_not_executed': len(compiled), 'external_baseline_pins_verified': baseline is not None,
              'original_tests_modified': False, 'tests_or_actual_executed': False,
              'original_cold_result_independently_reexecuted': False}
    if args.prepare_synthetic is not None:
        stage = args.prepare_synthetic.resolve()
        need(not stage.exists(), 'staging directory must be new and remain available after checker exit')
        need(not stage.is_relative_to(ROOT) and not stage.is_relative_to(baseline), 'staging must be outside package and baseline')
        stage.mkdir()
        (stage / 'overlay').mkdir()
        for name in ('tests.py', 'overlay/narrow_fullblock_attention.py'):
            raw = (ROOT / name).read_bytes()
            need(pin(raw) == m['unchanged_original_files'][name], 'staged source pin: ' + name)
            (stage / name).write_bytes(raw)
        test_inputs = {str(baseline / name): expected['sha256'] for name, expected in m['external_baseline_inputs'].items()}
        test_inputs[str(stage / 'overlay/narrow_fullblock_attention.py')] = m['unchanged_original_files']['overlay/narrow_fullblock_attention.py']['sha256']
        temporary_manifest = {'schema': 'attention-tick-integrity-source-v1',
            'scope': 'Temporary portable source/synthetic layout only; no actual authority.',
            'files': {name: m['unchanged_original_files'][name] for name in ('tests.py', 'overlay/narrow_fullblock_attention.py')},
            'test_inputs': test_inputs}
        (stage / 'SOURCE_MANIFEST.json').write_text(json.dumps(temporary_manifest, indent=2, sort_keys=True) + '\n')
        report['persistent_staging_directory'] = str(stage)
        report['synthetic_command_not_executed'] = shlex.join([sys.executable, '-I', '-B', str(stage / 'tests.py'), '--baseline', str(baseline)])
        report['staging_cleanup'] = 'Not automatically removed; caller may remove this temporary layout after use.'
    print(json.dumps(report, sort_keys=True))

if __name__ == '__main__':
    main()
