"""Portable stdlib-only adapter: original 66/68 plus 2 separate identity checks.

No model, runtime, original input or reference tensor payload is loaded. The
unaltered original test source is preserved; two historical-source-dependent
checks are explicitly excluded, not silently skipped or called reproduced.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / 'full_reference_gate_r3' / 'test_gate.py'
EXCLUDED = {
    'SourceContractTests.test_frozen_capture_is_unchanged_and_public_disabled':
        'Requires unpublished historical single-arm capture.py; paired public entry is separately tested by the unchanged original suite.',
    'SourceContractTests.test_network_helper_is_exact_frozen_source_region':
        'Requires unpublished historical import_gate_r2/worker.py and private provenance mapping; public helper-region/source identity checks are separate supplemental tests.',
}


def file_id(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def flat(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flat(item)
        else:
            yield item


class PublicIdentityTests(unittest.TestCase):
    def test_published_source_bytes_match_recorded_identities(self):
        pins = json.loads((HERE / 'evidence/SOURCE_INPUT_TOOL_PINS.json').read_text())
        for relative, expected in pins['sources'].items():
            self.assertEqual(file_id(HERE / relative), expected, relative)

    def test_published_network_helper_exact_region_hash(self):
        pins = json.loads((HERE / 'evidence/SOURCE_INPUT_TOOL_PINS.json').read_text())
        source = (HERE / 'full_reference_gate_r3/network_policy.py').read_text()
        region = source[source.index('# Exact trusted stdlib'):]
        self.assertEqual(hashlib.sha256(region.encode()).hexdigest(), pins['network_helper_original_region_sha256'])


def main():
    if set(sys.modules) & {'torch', 'numpy', 'transformers'}:
        raise RuntimeError('Numerical imports forbidden in portable mock reproduction')
    spec = importlib.util.spec_from_file_location('preserved_original_pair_tests', ORIGINAL)
    original = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = original
    spec.loader.exec_module(original)
    all_cases = list(flat(unittest.defaultTestLoader.loadTestsFromModule(original)))
    selected, omitted = [], []
    for case in all_cases:
        short = case.__class__.__name__ + '.' + case._testMethodName
        if short in EXCLUDED:
            omitted.append(short)
        else:
            selected.append(case)
    if len(all_cases) != 68 or len(selected) != 66 or set(omitted) != set(EXCLUDED):
        raise RuntimeError('Explicit original-suite selection contract changed')
    print('ORIGINAL SUITE: 66 of original 68 methods selected unchanged. NOT a full original 68 reproduction.', flush=True)
    for name in sorted(EXCLUDED):
        print('EXCLUDED ORIGINAL TEST: ' + name + ': ' + EXCLUDED[name], flush=True)
    first = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    print('SUPPLEMENTAL PUBLIC IDENTITY CHECKS: 2 new checks, separate from original 68.', flush=True)
    second = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PublicIdentityTests))
    if set(sys.modules) & {'torch', 'numpy', 'transformers'}:
        raise RuntimeError('Forbidden numerical import occurred')
    print(json.dumps({'original_methods_total': 68, 'original_methods_run': first.testsRun,
                      'original_methods_explicitly_excluded': sorted(EXCLUDED),
                      'original_selected_passed': first.wasSuccessful(),
                      'supplemental_identity_checks_run': second.testsRun,
                      'supplemental_identity_checks_passed': second.wasSuccessful(),
                      'original_68_fully_reproduced': False,
                      'ML_imported': False, 'original_tensor_payload_read': False,
                      'reference_forward_executed': False}, sort_keys=True), flush=True)
    return 0 if first.wasSuccessful() and second.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
