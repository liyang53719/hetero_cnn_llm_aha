"""Synthetic host-only telemetry tests. No DUT, build, download or publication."""
import ast
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib
import rss_telemetry as rss

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('RSS_TELEMETRY_BASE', str(HERE)))


def policy(raw=1 << 20):
    return dict(schema=rss.SCHEMA, raw_bytes=raw, compressed_bytes=64 << 20,
                line_bytes=1 << 20, verification_wall_seconds=10, verification_cpu_seconds=10)


def sample(n=0):
    return json.dumps(dict(elapsed=n*.05, aggregate_rss_bytes=1000,
                          processes=[[100, 20, 10, 100, 1000, n, 100000]],
                          MemAvailable_bytes=2 << 30, reserve_below_1GiB_warning=False),
                      separators=(',', ':'))+'\n'


class RSS(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rss-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, count=20, value=None, name='rss.gz'):
        folder = self.root/name
        folder.mkdir()
        p = folder/'rss_samples.jsonl.gz'
        w = rss.Writer(p, value or policy())
        for n in range(count):
            w.write(sample(n))
        w.finish()
        w.close()
        return p, w.receipt()

    def verify(self, p, r):
        return rss.verify(p, r, r['policy'], r['samples'])

    def scan(self, p, raw, packed):
        return rss._scan(p, raw, packed, rss.LINE_BYTES, 10, 10)

    def test_lossless_every_sample_and_receipt(self):
        p, r = self.write(1500)
        raw = ''.join(map(sample, range(1500))).encode()
        self.assertEqual(gzip.decompress(p.read_bytes()), raw)
        v = self.verify(p, r)
        self.assertEqual(v['raw_bytes'], len(raw))
        self.assertEqual(v['raw_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(v['compressed_sha256'], hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(v['samples'], 1500)
        self.assertTrue(v['all_written_bytes_verified'])
        self.assertTrue(v['gzip_crc_eof_verified'])
        self.assertTrue(v['physical_eof_verified'])
        self.assertFalse(r['all_written_bytes_verified'])
        self.assertLess(r['packed_bytes_before_finalization'], r['compressed_bytes'])

    def test_deterministic_single_member(self):
        a, _ = self.write(name='a.gz')
        b, _ = self.write(name='b.gz')
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(a.read_bytes()[:10], rss.HEADER)
        d = zlib.decompressobj(31)
        d.decompress(a.read_bytes())
        self.assertTrue(d.eof)
        self.assertEqual(d.unused_data, b'')

    def test_exact_both_caps_reach_physical_eof(self):
        p, r = self.write()
        v = self.scan(p, r['raw_bytes'], r['compressed_bytes'])
        self.assertEqual(v['samples'], 20)

    def test_raw_cap_plus_one_rejected(self):
        p, r = self.write()
        with self.assertRaisesRegex(ValueError, 'raw cap'):
            self.scan(p, r['raw_bytes']-1, r['compressed_bytes'])

    def test_compressed_cap_plus_one_rejected(self):
        p, r = self.write()
        with self.assertRaisesRegex(ValueError, 'compressed file'):
            self.scan(p, r['raw_bytes'], r['compressed_bytes']-1)

    def test_truncation_every_gzip_trailer_byte(self):
        p, r = self.write()
        original = p.read_bytes()
        for n in range(1, 9):
            p.write_bytes(original[:-n])
            with self.subTest(n=n), self.assertRaises(ValueError):
                self.verify(p, r)

    def test_corrupt_crc_and_payload(self):
        p, r = self.write()
        original = p.read_bytes()
        for i in (15, len(original)-8, len(original)-4):
            value = bytearray(original)
            value[i] ^= 1
            p.write_bytes(value)
            with self.subTest(i=i), self.assertRaises((ValueError, zlib.error, UnicodeError)):
                self.verify(p, r)

    def test_trailing_bytes_or_member_rejected(self):
        p, r = self.write()
        original = p.read_bytes()
        for tail in (b'\0', b'junk', gzip.compress(b''), original):
            p.write_bytes(original+tail)
            with self.subTest(tail=tail[:4]), self.assertRaises(ValueError):
                self.verify(p, r)

    def test_hash_count_and_policy_mutations(self):
        p, r = self.write()
        for key, bad in [('raw_sha256', '0'*64), ('compressed_sha256', '0'*64),
                         ('raw_bytes', r['raw_bytes']+1), ('samples', 19),
                         ('raw_crc32', '0'*8), ('gzip_finalized', False),
                         ('writer_closed', False), ('capture_failed', True)]:
            mutated = copy.deepcopy(r)
            mutated[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                rss.verify(p, mutated, r['policy'], 20)
        with self.assertRaisesRegex(ValueError, 'every supervisor'):
            rss.verify(p, r, r['policy'], 21)
        mutated = copy.deepcopy(r)
        mutated['policy']['raw_bytes'] += 1
        with self.assertRaises(ValueError):
            rss.verify(p, mutated, r['policy'], 20)

    def test_unfinished_writer_cannot_verify(self):
        p = self.root/'rss_samples.jsonl.gz'
        w = rss.Writer(p, policy())
        w.write(sample())
        w.close()
        self.assertFalse(w.receipt()['all_written_bytes_verified'])
        with self.assertRaises(ValueError):
            self.verify(p, w.receipt())

    def test_raw_writer_limit_no_partial_sample(self):
        p = self.root/'rss_samples.jsonl.gz'
        w = rss.Writer(p, policy(len(sample().encode())))
        w.write(sample())
        with self.assertRaisesRegex(ValueError, 'raw telemetry cap'):
            w.write(sample(1))
        self.assertTrue(w.failed)
        self.assertEqual(w.samples, 1)
        with self.assertRaises(ValueError):
            w.finish()
        w.close()
        self.assertFalse(w.receipt()['gzip_finalized'])

    def test_short_write_failure(self):
        p = self.root/'rss_samples.jsonl.gz'
        w = rss.Writer(p, policy())
        w.write(sample())
        real = w.file
        class Short:
            def write(self, data): return real.write(data[:1])
            def close(self): return real.close()
            def flush(self): return real.flush()
        w.file = Short()
        with self.assertRaisesRegex(ValueError, 'complete RSS'):
            w.finish()
        self.assertTrue(w.failed)
        self.assertFalse(w.finalized)
        w.close()

    def test_io_failure(self):
        p = self.root/'rss_samples.jsonl.gz'
        w = rss.Writer(p, policy())
        w.write(sample())
        real = w.file
        class Broken:
            def write(self, data):
                import errno
                raise OSError(errno.ENOSPC, 'synthetic disk failure')
            def close(self): return real.close()
        w.file = Broken()
        with self.assertRaises(OSError):
            w.finish()
        w.close()
        self.assertTrue(w.failed)
        self.assertFalse(w.finalized)

    def test_writer_compressed_cap_never_exceeded(self):
        with patch.object(rss, 'COMPRESSED_BYTES', 16):
            v = policy()
            v['compressed_bytes'] = 16
            p = self.root/'rss_samples.jsonl.gz'
            w = rss.Writer(p, v)
            w.write(sample())
            with self.assertRaisesRegex(ValueError, 'compressed cap'):
                w.finish()
            w.close()
            self.assertLessEqual(p.stat().st_size, 16)
            self.assertFalse(w.finalized)

    def test_line_missing_newline_and_bad_sample(self):
        p = self.root/'rss_samples.jsonl.gz'
        w = rss.Writer(p, policy())
        with self.assertRaises(ValueError):
            w.write(sample().rstrip())
        w.close()
        p, r = self.write(name='valid.gz')
        for raw in (b'{}\n', sample().rstrip().encode(), sample(1).encode()+sample(0).encode()):
            z = zlib.compressobj(6, zlib.DEFLATED, -15)
            import struct
            p.write_bytes(rss.HEADER+z.compress(raw)+z.flush()+struct.pack('<II', zlib.crc32(raw), len(raw)))
            with self.assertRaises(ValueError):
                self.scan(p, 1<<20, 1<<20)

    def test_line_cap(self):
        p, r = self.write()
        with self.assertRaisesRegex(ValueError, 'line cap'):
            rss._scan(p, r['raw_bytes'], r['compressed_bytes'], 20, 10, 10)

    def test_finite_verification_wall_and_cpu(self):
        p, r = self.write()
        for clock, message in [('monotonic', 'wall cap'), ('thread_time', 'CPU cap')]:
            with patch.object(rss.time, clock, side_effect=range(10000)):
                with self.subTest(clock=clock), self.assertRaisesRegex(ValueError, message):
                    self.scan(p, r['raw_bytes'], r['compressed_bytes'])

    def test_reject_symlink(self):
        p, r = self.write()
        q = self.root/'link.gz'
        q.symlink_to(p)
        with self.assertRaises(ValueError):
            self.scan(q, r['raw_bytes'], r['compressed_bytes'])

    def test_exact_policy_and_finite_bounds(self):
        for key, bad in [('schema', 'V1'), ('raw_bytes', 0), ('raw_bytes', True),
                         ('raw_bytes', (16<<30)+1), ('compressed_bytes', (64<<20)+1),
                         ('line_bytes', (1<<20)+1), ('verification_cpu_seconds', 3601),
                         ('verification_wall_seconds', float('inf'))]:
            p = policy()
            p[key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                rss.policy(p)
        p = policy()
        p['extra'] = 1
        with self.assertRaises(ValueError):
            rss.policy(p)

    def test_bounded_expansion_chunk_sizes(self):
        # More than64KiB raw from a small gzip proves the max-length loop,
        # not an unbounded decompress/readtext path, is exercised.
        p, r = self.write(3000)
        self.assertGreater(r['raw_bytes'], rss.CHUNK)
        self.assertLess(r['compressed_bytes'], rss.CHUNK)
        self.assertEqual(self.verify(p, r)['samples'], 3000)

    def test_receipt_unknown_missing_and_boolean_counts(self):
        p, r = self.write()
        mutations = []
        v = copy.deepcopy(r); v['unexpected'] = True; mutations.append(v)
        v = copy.deepcopy(r); del v['raw_sha256']; mutations.append(v)
        v = copy.deepcopy(r); v['samples'] = True; mutations.append(v)
        v = copy.deepcopy(r); v['all_written_bytes_verified'] = 'yes'; mutations.append(v)
        for v in mutations:
            with self.subTest(keys=list(v)), self.assertRaises(ValueError):
                rss.verify(p, v, r['policy'], 20)

    def test_measured_python_memory_bounded_across_many_observations(self):
        import tracemalloc
        tracemalloc.start()
        try:
            p, r = self.write(30000, policy(16 << 20))
            self.assertGreater(r['raw_bytes'], 4 << 20)
            self.verify(p, r)
            current, peak = tracemalloc.get_traced_memory()
            self.assertLess(peak, 2 << 20, (current, peak, r['raw_bytes']))
        finally:
            tracemalloc.stop()

    def test_postphase_receipt_rechecks_physical_identity_without_raw_pass(self):
        p, r = self.write()
        v = self.verify(p, r)
        with patch.object(rss, '_scan', side_effect=AssertionError('no second raw pass')):
            self.assertEqual(rss.check_receipt(p, v, r['policy'], r['samples']), v)
        original = p.read_bytes()
        for modified in (original+b'junk', original+gzip.compress(b''), bytes([original[0]^1])+original[1:]):
            p.write_bytes(modified)
            with self.assertRaises(ValueError):
                rss.check_receipt(p, v, r['policy'], r['samples'])

    def test_postphase_rejects_partial_forged_or_unknown_proof(self):
        p, r = self.write()
        v = self.verify(p, r)
        with self.assertRaises(ValueError):
            rss.check_receipt(p, r, r['policy'], r['samples'])
        for key, bad in [('all_written_bytes_verified', False), ('physical_eof_verified', 1),
                         ('gzip_crc_eof_verified', False), ('verification_cpu_seconds', float('nan')),
                         ('raw_bytes', True), ('compressed_bytes', '20'), ('raw_sha256', 'bad')]:
            modified = copy.deepcopy(v)
            modified[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                rss.check_receipt(p, modified, r['policy'], r['samples'])
        with self.assertRaises(ValueError):
            rss.check_receipt(p, v, policy(r['policy']['raw_bytes']+1), r['samples'])

    def test_nested_policy_numeric_type_aliases_rejected(self):
        value = policy()
        value['verification_cpu_seconds'] = value['verification_wall_seconds'] = 1
        p, r = self.write(value=value)
        v = self.verify(p, r)
        for key, bad in [('raw_bytes', float(value['raw_bytes'])),
                         ('compressed_bytes', float(value['compressed_bytes'])),
                         ('verification_wall_seconds', True),
                         ('verification_cpu_seconds', True)]:
            for original, validator in ((r, rss.verify), (v, rss.check_receipt)):
                modified = copy.deepcopy(original)
                modified['policy'][key] = bad
                with self.subTest(key=key, validator=validator.__name__), self.assertRaises(ValueError):
                    validator(p, modified, value, original['samples'])


class SourceCompatibility(unittest.TestCase):
    def test_original_limits_and_sampling_census_unchanged(self):
        original_function_hashes = {'limits': '961cae7b3322c100314c817bddb44ffed8f45806e3cbc04d697b973557b2a757', 'output_sample': '3f00fc4665849d7d44a7d7b25f9eca3f97ce9895b9821760de43d04c8ae3c782', 'timed_output_sample': '27c8e7c3d630da8a775273638e664f6f8e8df7c200ea6b31631184ff00c4b229'}
        new = ast.parse((HERE/'supervise_multiroot.py').read_text())
        def fn(tree, name):
            return ast.dump(next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), include_attributes=False)
        for name in ('limits', 'output_sample', 'timed_output_sample'):
            self.assertEqual(original_function_hashes[name], hashlib.sha256(fn(new, name).encode()).hexdigest(), name)
        text = (HERE/'supervise_multiroot.py').read_text()
        self.assertEqual(text.count('time.sleep(.05)'), 1)
        self.assertIn("if telemetry_policy is None:telemetry.flush();need(telemetry.tell()<=64*1024*1024", text)
        self.assertIn("(run/'rss_samples.jsonl').open('x')", text)
        self.assertIn("RSS telemetry source pin", text)


class SupervisorHostFixture(unittest.TestCase):
    def run_fixture(self, v2=True, raw=1<<20, pin=True, slow_verify=False):
        import importlib.util
        import shutil
        import sys
        with tempfile.TemporaryDirectory(prefix='rss-supervisor-fixture-') as tmp:
            root = Path(tmp)
            for name in ('strict_cleanup.py', 'lossless_log.py'):
                shutil.copyfile(BASE/name, root/name)
            for name in ('supervise_multiroot.py', 'rss_telemetry.py'):
                shutil.copyfile(HERE/name, root/name)
            if slow_verify:
                with (root/'rss_telemetry.py').open('a') as f:
                    f.write('\ndef verify(*a, **k):\n    time.sleep(2)\n')
            spec = importlib.util.spec_from_file_location('synthetic_supervisor', root/'supervise_multiroot.py')
            module = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(root))
            try:
                spec.loader.exec_module(module)
            finally:
                sys.path.pop(0)
            caps = dict(wall_seconds=3, cleanup_seconds=3, file_bytes=2<<20,
                        tree_bytes=8<<20, log_bytes=1<<20, raw_log_bytes=1<<20,
                        max_entries=1000, per_process_as_bytes=512<<20,
                        per_process_cpu_seconds=3, rss_bytes=256<<20,
                        cpu_seconds=3, min_free_disk_bytes=0)
            pins = {}
            if v2:
                value = policy(raw)
                if slow_verify:
                    value['verification_wall_seconds'] = 1
                    value['verification_cpu_seconds'] = 1
                caps['rss_telemetry_policy'] = value
                if pin:
                    pins[str(root/'rss_telemetry.py')] = ('0'*64 if pin == 'mismatch' else hashlib.sha256((root/'rss_telemetry.py').read_bytes()).hexdigest())
            result = module.execute([sys.executable, '-c', "import time; print('synthetic-host-fixture'); time.sleep(.12)"],
                                    root/'run', root/'lock', caps, dict(os.environ), pins)
            names = sorted(p.name for p in (root/'run').iterdir()) if (root/'run').exists() else []
            return result, names

    def test_v2_real_supervisor_complete_every_observation(self):
        r, names = self.run_fixture()
        self.assertEqual(r['status'], 'PASS_PROCESS_ONLY', r['errors'])
        self.assertIn('rss_samples.jsonl.gz', names)
        self.assertNotIn('rss_samples.jsonl', names)
        self.assertTrue(r['rss_telemetry']['all_written_bytes_verified'])
        self.assertEqual(r['process_sample_count'], r['rss_telemetry']['samples'])
        self.assertGreater(r['process_sample_count'], 1)
        self.assertTrue(r['log_capture']['pipe_eof_observed'])
        self.assertEqual(r['observed_remaining'], [])

    def test_legacy_real_supervisor_keeps_plain_jsonl(self):
        r, names = self.run_fixture(v2=False)
        self.assertEqual(r['status'], 'PASS_PROCESS_ONLY', r['errors'])
        self.assertIn('rss_samples.jsonl', names)
        self.assertNotIn('rss_samples.jsonl.gz', names)
        self.assertNotIn('rss_telemetry', r)

    def test_missing_source_pin_prevents_start(self):
        r, names = self.run_fixture(pin=False)
        self.assertEqual(r['status'], 'FAIL_OR_INCOMPLETE')
        self.assertFalse(r['worker_started'])
        self.assertTrue(any('RSS telemetry source pin' in x for x in r['errors']))

    def test_source_pin_mismatch_prevents_start(self):
        r, names = self.run_fixture(pin='mismatch')
        self.assertEqual(r['status'], 'FAIL_OR_INCOMPLETE')
        self.assertFalse(r['worker_started'])
        self.assertTrue(any('input pin mismatch' in x for x in r['errors']))

    def test_cap_failure_still_proves_group_absence(self):
        r, names = self.run_fixture(raw=1)
        self.assertEqual(r['status'], 'FAIL_OR_INCOMPLETE')
        self.assertTrue(r['worker_started'])
        self.assertTrue(r['cleanup_proof'])
        self.assertEqual(r['observed_remaining'], [])
        self.assertFalse(r['rss_telemetry']['all_written_bytes_verified'])
        self.assertTrue(r['rss_telemetry']['capture_failed'])

    def test_verification_wall_failure_after_cleanup_is_incomplete(self):
        r, names = self.run_fixture(slow_verify=True)
        self.assertEqual(r['status'], 'FAIL_OR_INCOMPLETE')
        self.assertTrue(r['cleanup_proof'])
        self.assertEqual(r['observed_remaining'], [])
        self.assertTrue(r['log_capture']['pipe_eof_observed'])
        self.assertFalse(r['rss_telemetry']['all_written_bytes_verified'])
        self.assertTrue(any('InterruptedError' in x for x in r['errors']), r['errors'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
