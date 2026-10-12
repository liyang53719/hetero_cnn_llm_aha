"""Fail-closed small GQA software test receipt. Never compile or fetch data."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest

from scripts.build_shared_matrix_recipe import from_environment
from . import owner


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identities():
    result = owner.source_identity()
    result['gqa_package_sha256'] = {path.name: sha(path) for path in sorted(Path(__file__).parent.iterdir())
                                  if path.is_file() and path.suffix in ('.py', '.md')}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    before = identities()
    started = time.monotonic()
    report = dict(status='FAIL', software_only=True, rtl_executed=False, native_acceptance=False,
                  fullblock_executed=False, hardware_cycles=None, source_before=before,
                  python=sys.executable, compile_performed=False)
    stream = io.StringIO()
    try:
        library = from_environment(owner.ROOT)
        receipt = Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT']).resolve(strict=True)
        report.update(library=str(library), library_sha256=sha(library),
                      compile_receipt=str(receipt), compile_receipt_sha256=sha(receipt),
                      compile_identity_verified=True)
        suite = unittest.defaultTestLoader.loadTestsFromName(
            'candidates.qwen35_attention_prefill.gqa.test_gqa')
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        report.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                      skipped=len(result.skipped), exit_code=0 if result.wasSuccessful() and not result.skipped else 1)
        report['source_after'] = identities()
        report['sources_unchanged'] = report['source_after'] == before
        report['library_unchanged'] = sha(library) == report['library_sha256']
        if report['exit_code'] == 0 and report['sources_unchanged'] and report['library_unchanged']:
            report['status'] = 'PASS_SMALL_GQA_SOFTWARE_ONLY'
        else:
            report['exit_code'] = 1
    except Exception as error:
        report.update(error=type(error).__name__ + ': ' + str(error), exit_code=1)
    report['seconds'] = time.monotonic() - started
    (args.out / 'tests.log').write_text(stream.getvalue())
    (args.out / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(stream.getvalue(), end='')
    print(json.dumps({key: report[key] for key in ('status', 'exit_code', 'seconds')}, sort_keys=True))
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
