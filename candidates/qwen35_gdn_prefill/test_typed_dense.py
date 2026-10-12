"""Small actual-C++ Dense tests; no checkpoint, build, Java, or RTL.

Set MATRIX_SERVICE_LIBRARY and MATRIX_SERVICE_COMPILE_RECEIPT explicitly.
Missing evidence is an error, never a skip, cache search, or compilation.
"""
import ctypes as C
import ctypes.util
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest

from . import typed_dense as t

ROOT = Path(__file__).resolve().parents[2]
LIB = LIBM = None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def setUpModule():
    global LIB, LIBM
    from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library
    LIB = configure_library(C.CDLL(str(t.library_from_environment(ROOT))))
    LIBM = C.CDLL(ctypes.util.find_library('m') or 'libm.so.6')
    LIBM.fmaf.argtypes = [C.c_float] * 3
    LIBM.fmaf.restype = C.c_float


def word_float(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def oracle(a_raw, b_raw, m, k, n):
    """Independent logical row-major oracle, called only after actual terminal."""
    a = struct.unpack('<' + 'H' * (m * k), a_raw)
    b = struct.unpack('<' + 'H' * (k * n), b_raw)
    result = []
    for row in range(m):
        for col in range(n):
            value = 0.0
            for depth in range(k):
                value = LIBM.fmaf(word_float(a[row*k + depth] << 16),
                                  word_float(b[depth*n + col] << 16), value)
            bits = struct.unpack('<I', struct.pack('<f', value))[0]
            result.append(((bits + 0x7fff + ((bits >> 16) & 1)) >> 16) & 65535)
    return struct.pack('<' + 'H' * len(result), *result)


def values(count, salt=0):
    basis = (0x3e83, 0xbe47, 0x3f07, 0xbf13, 0x3d8b, 0x0080, 0x0001)
    return struct.pack('<' + 'H' * count, *(basis[(i*3 + i//7 + salt) % len(basis)] for i in range(count)))


class TypedDenseTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(LIB.td_reset(), 0)
        self.matrix = t.MatrixService(LIB)
        self.owner = t.down.DenseOwnerModel(t.down.PrefixWorkspace(0x900000, 64, 1, 2560))
        self.memory = t.TypedMemory()

    def prepare(self, n=64, k=32, m=16, tag=41, a=0x10000, b=0x20000, dst=0x50000):
        if a not in self.memory.regions:
            self.memory.add_readonly(a, values(m*k))
        self.memory.add_readonly(b, values(k*n, 2))
        self.memory.allocate_output(dst, m*n*2)
        return t.down.Job(m=m, k=k, n=n, tag=tag, a=a, b=b, dst=dst,
            activation_bf16=True, weight_bf16=True, output_bf16=True, write_bytes=m*n*2)

    def driver(self, job):
        return t.TypedDenseDriver(self.owner, self.matrix, self.memory, job)

    def finish(self, driver, hook=None):
        deadline = time.monotonic() + 15
        for tick in range(100000):
            self.assertLess(time.monotonic(), deadline, 'small Dense test wall budget')
            args = {} if hook is None else hook(driver, tick)
            driver.tick(**args)
            if driver.response is not None:
                return driver.report()
        self.fail('small Dense tick budget')

    def test_actual_n_larger_than_k_then_published_input_same_resources(self):
        j = self.prepare()
        identity = (id(self.owner), id(self.owner.a_banks), id(self.owner.b_banks), self.matrix.resource_address)
        d = self.driver(j)
        report = self.finish(d, lambda _, i: dict(read_ready=i%3 != 0,
            read_response_ready=i%4 != 0, step_ready=i%5 != 0, result_ready=i%7 != 0,
            done_ready=i%3 != 0, write_ready=i%4 != 0, data_ready=i%5 != 0, ack_ready=i%6 != 0))
        self.assertEqual(d.response, (j.tag, None, 2048))
        self.assertEqual(d.output.raw(), oracle(d.a.raw(), d.b.raw(), 16, 32, 64))
        self.assertEqual(report['executed_fmas'], 32*2*4096)
        self.assertEqual(report['counts']['ack_bytes'], 2048)
        self.assertEqual(self.owner.prefix_bytes, 0)
        # The second command reads the first command's ACTUAL published output.
        second = self.prepare(n=32, k=64, a=j.dst, b=0x30000, dst=0x60000, tag=42)
        e = self.driver(second)
        self.finish(e)
        self.assertEqual(e.output.raw(), oracle(d.output.raw(), e.b.raw(), 16, 64, 32))
        self.assertEqual(identity, (id(self.owner), id(self.owner.a_banks), id(self.owner.b_banks), self.matrix.resource_address))
        self.assertEqual(self.matrix.counts['owner_acquires'], 2)
        self.assertEqual(self.matrix.counts['owner_releases'], 2)
        self.assertEqual(self.matrix.epoch, 0)

    def test_final_ack_and_held_terminal_do_not_publish(self):
        j = self.prepare(n=32)
        d = self.driver(j)
        stalled = 0
        while d.pending_ack is None or d.counts['write_data_bytes'] != j.write_bytes:
            d.tick()
        for _ in range(7):
            d.tick(ack_ready=False)
            stalled += 1
            self.assertFalse(d.output.published)
            self.assertIsNone(d.response)
        while self.owner.ports()['response'] is None:
            d.tick(response_ready=False)
        held = self.owner.ports()['response']
        for _ in range(5):
            d.tick(response_ready=False)
            self.assertEqual(self.owner.ports()['response'], held)
            self.assertFalse(d.output.published)
            with self.assertRaises(ValueError):
                self.memory.read64(j.dst)
        d.tick()
        self.assertTrue(d.output.published)
        self.assertIsNone(self.matrix.owner)

    def test_exact_2byte_spans_alias_and_unpublished_source_rejected(self):
        j = self.prepare()
        for bad in (replace(j, dst=j.a), replace(j, write_bytes=j.write_bytes*2),
                    replace(j, activation_bf16=False), replace(j, output_bf16=False)):
            with self.assertRaises(ValueError):
                self.driver(bad)
        self.assertIsNone(self.matrix.owner)
        self.memory.allocate_output(0x70000, 16*32*2)
        with self.assertRaises(ValueError):
            self.driver(replace(j, a=0x70000))
        with self.assertRaises(ValueError):
            self.memory.allocate_output(j.a+64, 64)

    def test_write_mask_and_explicit_ack_bytes(self):
        self.memory.allocate_output(0x10000, 64)
        self.memory.begin_write(t.down.WriteCommand(0x10000, 1, 5))
        with self.assertRaises(ValueError):
            self.memory.write_data((0,)*32, True, mask=FULL_MASK ^ 1)
        self.memory.write_data((0,)*32, True)
        with self.assertRaises(ValueError):
            self.memory.acknowledge(t.down.WriteAck(5, False, None))
        self.memory.acknowledge(t.down.WriteAck(5, False, 64))
        self.memory.publish(0x10000, (5, None, 64))
        self.assertEqual(self.memory.read64(0x10000), bytes(64))

    def test_abort_drains_accepted_read_result_and_write_obligations(self):
        for phase in ('read', 'step', 'result', 'write'):
            with self.subTest(phase=phase):
                self.setUp()
                j = self.prepare()
                d = self.driver(j)
                while True:
                    if ((phase == 'read' and d.pending_read is not None) or
                        (phase == 'step' and d.counts['steps'] > 0) or
                        (phase == 'result' and d.results) or
                        (phase == 'write' and self.memory.pending is not None)):
                        break
                    d.tick(result_ready=phase != 'result')
                d.tick(abort=True, read_response_ready=False, result_ready=False, ack_ready=False)
                self.assertFalse(d.output.published)
                self.finish(d)
                self.assertIsNotNone(d.response[1])
                self.assertFalse(d.output.published)
                self.assertIsNone(d.pending_read)
                self.assertIsNone(self.memory.pending)
                self.assertFalse(d.results)
                self.assertIsNone(self.matrix.owner)
                self.assertTrue(self.matrix.reset_required)
                self.assertEqual(self.owner.state, 'locked')
                self.assertEqual(self.matrix.counts['aborts'], 1)

    def test_final_ack_error_leaves_staging_unpublished(self):
        j = self.prepare(n=32)
        d = self.driver(j)
        self.finish(d, lambda x, _: dict(ack_error=bool(x.pending_ack and x.counts['write_data_bytes'] == j.write_bytes)))
        self.assertIsNotNone(d.response[1])
        self.assertEqual(d.counts['ack_bytes'], j.write_bytes-64)
        self.assertFalse(d.output.published)
        self.assertIsNone(self.matrix.owner)

    def test_actual_matrix_overflow_drains_without_fabricated_result(self):
        self.memory.add_readonly(0x10000, struct.pack('<512H', *([0x7f7f]*512)))
        self.memory.add_readonly(0x20000, struct.pack('<1024H', *([0x7f7f]*1024)))
        self.memory.allocate_output(0x50000, 1024)
        j = t.down.Job(m=16, k=32, n=32, tag=77, a=0x10000, b=0x20000,
            dst=0x50000, activation_bf16=True, weight_bf16=True, output_bf16=True, write_bytes=1024)
        d = self.driver(j)
        self.finish(d)
        self.assertIsNotNone(d.numeric_fault)
        self.assertIsNotNone(d.response[1])
        self.assertEqual(d.counts['results'], 0)
        self.assertEqual(d.counts['write_data_bytes'], 0)
        self.assertFalse(d.output.published)
        self.assertIsNone(self.matrix.owner)
        self.assertTrue(self.matrix.reset_required)

    def test_explicit_library_receipt_rejects_missing_path_hash_and_source(self):
        with self.assertRaises(ValueError):
            t.library_from_environment(ROOT, {})
        selected = {k: os.environ[k] for k in ('MATRIX_SERVICE_LIBRARY', 'MATRIX_SERVICE_COMPILE_RECEIPT')}
        with self.assertRaises((ValueError, FileNotFoundError)):
            t.library_from_environment(ROOT, dict(selected, MATRIX_SERVICE_LIBRARY='/nonexistent/typed_dense.so'))
        original = json.loads(Path(selected['MATRIX_SERVICE_COMPILE_RECEIPT']).read_text())
        with tempfile.TemporaryDirectory(prefix='typed_dense_receipt_') as directory:
            changed = Path(directory) / 'compile.json'
            for kind in ('library_path', 'library_hash', 'source_hash', 'missing_source', 'compile_flags'):
                with self.subTest(kind=kind):
                    r = json.loads(json.dumps(original))
                    if kind == 'library_path':
                        r['library'] += '.wrong'
                    elif kind == 'library_hash':
                        r['library_sha256'] = '0'*64
                    elif kind in ('source_hash', 'missing_source'):
                        key = 'sources_before' if 'sources_before' in r else 'source_sha256'
                        name = next(iter(r[key]))
                        if kind == 'source_hash':
                            r[key][name] = '0'*64
                        else:
                            del r[key][name]
                    else:
                        r['argv'][r['argv'].index('-fno-fast-math')] = '-ffast-math'
                    changed.write_text(json.dumps(r))
                    with self.assertRaises(ValueError):
                        t.library_from_environment(ROOT, dict(selected, MATRIX_SERVICE_COMPILE_RECEIPT=str(changed)))


FULL_MASK = t.FULL_MASK

if __name__ == '__main__':
    unittest.main()
