"""Pure synthetic schema tests. No frameworks, downloads, or reference execution."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

import safe_export as se


def fixture():
    pin = {'bytes': 4, 'sha256': 'a' * 64}
    frozen = {'frozen_fixture': {
        'tensor_records': {name: dict(pin) for name in sorted(se.TENSOR_NAMES)},
        'rope1024': dict(pin)}}
    sha = se.frozen_digest(frozen)
    result = dict(schema='P0_PORTABLE_REFERENCE_RESULT_V1', candidate_id=se.CANDIDATE_ID,
        status='NOT_STARTED', reason=None, candidate_source_sha256='b' * 64,
        frozen_manifest_sha256=sha, runtime_receipt_sha256=None,
        weight_expected=12, weight_checked=0, tensor_expected=25, tensor_checked=0,
        first_mismatch_name=None, all_visible_exact=False, hardware_executed=False,
        dut_numerical_pass=False, raw_payloads_uploaded=False, internal_op_order_proven=False)
    checks = dict(schema='P0_PORTABLE_REFERENCE_CHECKS_V1', frozen_manifest_sha256=sha,
        weight_checked=0, weight_mismatch_count=0, checks=[])
    for name in (*frozen['frozen_fixture']['tensor_records'], 'rope1024'):
        checks['checks'].append(dict(name=name, status='NOT_REACHED', expected_bytes=4,
            observed_bytes=None, expected_sha256='a' * 64, observed_sha256=None,
            shape_equal=None, dtype_equal=None))
    host = dict(schema='P0_PORTABLE_REFERENCE_HOST_V1', architecture=None,
        python_implementation=None, python_version=None, python_sha256=None,
        cpu_affinity_count=None, cpu_evidence_sha256=None,
        isa={key: None for key in ('sse2', 'avx', 'avx2', 'avx512f')},
        requested_capability='default', observed_capability=None, requested_threads=4,
        observed_threads=None, requested_interop=1, observed_interop=None,
        initial_free_bytes=None, minimum_free_bytes=None, mem_available_bytes=None, stages=[],
        job_wall_seconds=None, job_cpu_seconds=None, job_wall_budget_seconds=3600, job_cpu_budget_seconds=3600)
    for name, budgets in se.STAGE_BUDGETS.items():
        stage = dict(name=name, status='NOT_REACHED', wall_seconds=None, cpu_seconds=None,
            peak_rss_bytes=None, disk_bytes=None, native_exit=None, cleanup='NOT_REACHED',
            pipe_eof='NOT_REACHED', gzip_finalized='NOT_REACHED')
        stage.update(zip(('wall_budget_seconds', 'cpu_budget_seconds', 'rss_budget_bytes', 'disk_budget_bytes'), budgets))
        host['stages'].append(stage)
    return result, checks, host, frozen


def passed_fixture():
    result, checks, host, frozen = fixture()
    result.update(status='PASS_EXACT_VISIBLE_FIXTURE', runtime_receipt_sha256='c' * 64,
                  weight_checked=12, tensor_checked=25, all_visible_exact=True)
    checks['weight_checked'] = 12
    for row in checks['checks']:
        row.update(status='PASS', observed_bytes=4, observed_sha256='a' * 64,
                   shape_equal=True, dtype_equal=True)
    host.update(architecture='x86_64', python_implementation='CPython', python_version='3.12.9',
        python_sha256='d' * 64, cpu_affinity_count=4, cpu_evidence_sha256='e' * 64,
        isa={key: False for key in host['isa']}, observed_capability='DEFAULT',
        observed_threads=4, observed_interop=1, initial_free_bytes=10 * se.GIB,
        minimum_free_bytes=9 * se.GIB, mem_available_bytes=8 * se.GIB,
        job_wall_seconds=10, job_cpu_seconds=6)
    for stage in host['stages']:
        stage.update(status='PASS', wall_seconds=1.5, cpu_seconds=1, peak_rss_bytes=100,
                     disk_bytes=100, native_exit=0, cleanup=se.COMPLETE_CLEANUP,
                     pipe_eof='COMPLETE', gzip_finalized='COMPLETE')
    return result, checks, host, frozen


class ExportTests(unittest.TestCase):
    def test_not_started_and_pass(self):
        for make in (fixture, passed_fixture):
            with self.subTest(make=make.__name__), tempfile.TemporaryDirectory() as tmp:
                args = make()
                out = Path(tmp) / 'export'
                result = se.write_exports(out, *args)
                self.assertEqual(set(result), set(se.FILENAMES))
                self.assertEqual(set(p.name for p in out.iterdir()), set(se.FILENAMES))
                self.assertEqual(se.validate_exports(out, args[-1]), result)
                with self.assertRaises(FileExistsError):
                    se.write_exports(out, *args)

    def test_failure_missing_measurements(self):
        result, checks, host, frozen = fixture()
        result.update(status='FAIL', reason='INSTALL')
        host['stages'][0].update(status='FAIL', wall_seconds=0.1)
        self.assertTrue(se.validate_records(result, checks, host, frozen))

    def test_geometry_failure_without_digest(self):
        result, checks, host, frozen = fixture()
        row = next(r for r in checks['checks'] if r['name'] == 'hidden_native')
        row.update(status='MISMATCH', shape_equal=False)
        result.update(status='FAIL', reason='REFERENCE_GEOMETRY', tensor_checked=1,
                      first_mismatch_name=row['name'])
        self.assertTrue(se.validate_records(result, checks, host, frozen))

    def test_reject_mutations(self):
        mutations = [
            lambda r,c,h,f: r.update(path='/secret'),
            lambda r,c,h,f: r.update(weight_checked=True),
            lambda r,c,h,f: r.update(hardware_executed=True),
            lambda r,c,h,f: r.update(candidate_source_sha256='https://example.com'),
            lambda r,c,h,f: r.update(status='PASS_EXACT_VISIBLE_FIXTURE'),
            lambda r,c,h,f: r.update(first_mismatch_name='unknown'),
            lambda r,c,h,f: c['checks'][0].update(expected_sha256='b'*64),
            lambda r,c,h,f: c['checks'][0].update(observed_bytes=4),
            lambda r,c,h,f: c['checks'][0].update(values=[0]),
            lambda r,c,h,f: c['checks'].append(copy.deepcopy(c['checks'][0])),
            lambda r,c,h,f: c['checks'][1].update(name=c['checks'][0]['name']),
            lambda r,c,h,f: h.update(python_version='/usr/bin/python'),
            lambda r,c,h,f: h.update(cpu_affinity_count=True),
            lambda r,c,h,f: h['isa'].update(secret=True),
            lambda r,c,h,f: h['stages'][0].update(wall_seconds=float('nan')),
            lambda r,c,h,f: h['stages'][0].update(cpu_seconds=float('inf')),
            lambda r,c,h,f: h['stages'][0].update(peak_rss_bytes=2**100),
            lambda r,c,h,f: h['stages'][0].update(wall_budget_seconds=9999),
            lambda r,c,h,f: h['stages'][0].update(native_exit=False),
            lambda r,c,h,f: h.update(stages=[]),
            lambda r,c,h,f: h.update(job_wall_seconds=float('nan')),
            lambda r,c,h,f: h.update(job_cpu_seconds=float('inf')),
            lambda r,c,h,f: h.update(job_wall_seconds=True),
            lambda r,c,h,f: h.update(job_cpu_seconds=86401),
            lambda r,c,h,f: h.update(job_wall_budget_seconds=3601),
            lambda r,c,h,f: h.update(job_cpu_budget_seconds=False),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                args = fixture()
                mutation(*args)
                with self.assertRaises(se.ExportError):
                    se.validate_records(*args)

    def test_pass_requires_terminal_and_runtime_proof(self):
        for mutate in (
            lambda r,c,h,f: h['stages'][0].update(cleanup='INCOMPLETE'),
            lambda r,c,h,f: h.update(observed_capability='AVX512'),
            lambda r,c,h,f: h.update(observed_threads=8),
            lambda r,c,h,f: h['stages'][0].update(wall_seconds=1801),
            lambda r,c,h,f: r.update(runtime_receipt_sha256=None),
            lambda r,c,h,f: h.update(minimum_free_bytes=0),
            lambda r,c,h,f: h.update(job_wall_seconds=None),
            lambda r,c,h,f: h.update(job_cpu_seconds=None),
            lambda r,c,h,f: h.update(job_wall_seconds=3600.1),
            lambda r,c,h,f: h.update(job_cpu_seconds=3600.1),
        ):
            args = passed_fixture()
            mutate(*args)
            with self.assertRaises(se.ExportError):
                se.validate_records(*args)

    def test_disk_attacks(self):
        attacks = ('extra', 'duplicate', 'nan', 'oversize', 'symlink', 'hardlink')
        for attack in attacks:
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as tmp:
                args = fixture()
                out = Path(tmp) / 'export'
                se.write_exports(out, *args)
                path = out / 'RESULT.json'
                if attack == 'extra':
                    (out / 'raw.bin').write_bytes(b'no')
                elif attack == 'duplicate':
                    path.write_text('{"schema":"x","schema":"y"}', encoding='utf-8')
                elif attack == 'nan':
                    path.write_text('{"x":NaN}', encoding='utf-8')
                elif attack == 'oversize':
                    path.write_bytes(b' ' * (se.MAX_FILE_BYTES + 1))
                else:
                    saved = Path(tmp) / 'saved'
                    path.rename(saved)
                    if attack == 'symlink':
                        path.symlink_to(saved)
                    else:
                        os.link(saved, path)
                with self.assertRaises((se.ExportError, OSError)):
                    se.validate_exports(out, args[-1])

    def test_directory_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = fixture()
            out = Path(tmp) / 'export'
            se.write_exports(out, *args)
            alias = Path(tmp) / 'alias'
            alias.symlink_to(out, target_is_directory=True)
            with self.assertRaises(se.ExportError):
                se.validate_exports(alias, args[-1])


if __name__ == '__main__':
    unittest.main()
