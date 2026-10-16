"""Pure observation/preparation tests; no numerical services are imported/run."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace as NS
import unittest

from . import streaming as s


class StreamingTests(unittest.TestCase):
    def test_scalar_canonical_stream_covers_operation_policy_and_all_words(self):
        event = ('mul', 0x80000000, 0x7fc00001, 0xff800000, 'legacy_scalar')
        d = s.ScalarDigest()
        d.append(event)
        expected = (s.VERSION + ':scalar\0').encode() + struct.pack('<BBIII', 1, 1, *event[1:4])
        self.assertEqual(d.report()['sha256'], hashlib.sha256(expected).hexdigest())
        self.assertEqual(d.report()['count'], 1)
        self.assertEqual(d.report()['bytes'], 14)
        for changed in (('add', *event[1:]), (event[0], 0, *event[2:]),
                        (*event[:2], 0, *event[3:]), (*event[:3], 0, event[4]),
                        (*event[:4], 'vector')):
            other = s.ScalarDigest()
            other.append(changed)
            self.assertNotEqual(other.report()['sha256'], d.report()['sha256'])
        for bad in (True, -1, 1 << 32, 1.0):
            with self.assertRaises(ValueError):
                d.append(('bf', bad, 0, 0, 'vector'))
        with self.assertRaises(ValueError):
            d.append(('unknown', 0, 0, 0, 'vector'))
        self.assertEqual(len(d), 1)

    def test_stream_sinks_retain_no_event_lists(self):
        d = s.ScalarDigest()
        for i in range(5000):
            d.append(('bf', i, 0, i, 'vector'))
        self.assertEqual(d.count, 5000)
        self.assertFalse(any(isinstance(v, (list, tuple, bytes, bytearray))
                             for v in vars(d).values()))
        before = d.report()
        self.assertEqual(d.report(), before)  # Reporting does not consume state.
        d.append(('bf', 9, 0, 9, 'vector'))
        self.assertNotEqual(d.report()['sha256'], before['sha256'])

    def test_memory_streams_preserve_full_tags_metadata_and_write_payload(self):
        tag = (1 << 63) + 9
        read = NS(tag=tag, address=0x100000, write=False, data=None, mask=0)
        write = NS(tag=tag + 1, address=0x200000, write=True,
                   data=bytes(range(64)), mask=(1 << 64) - 1)
        callbacks = []
        memory = s.MemoryDigest(write_callback=callbacks.append)
        core = s.CoreDigest()
        for q in (read, write):
            memory.append(q)
            core.append((q.tag, q.address, q.write))
        self.assertEqual(memory.metadata.report(), core.report())
        self.assertEqual((memory.read_count, memory.write_count), (1, 1))
        self.assertEqual(callbacks, [write])
        changed = s.MemoryDigest()
        changed.append(read)
        changed.append(NS(**dict(vars(write), data=write.data[:-1] + b'\xff')))
        self.assertNotEqual(changed.report()['sha256'], memory.report()['sha256'])
        self.assertEqual(changed.metadata.report(), memory.metadata.report())
        with self.assertRaises(ValueError):
            memory.append(NS(**dict(vars(write), data=bytes(63))))
        with self.assertRaises(ValueError):
            core.append((True, 0, False))
        self.assertEqual(memory.count, 2)
        addresses = s.AddressDigest()
        addresses.append((1 << 64) - 1)
        self.assertEqual(addresses.byte_count, 8)
        with self.assertRaises(ValueError):
            addresses.append(1 << 64)

    def test_matrix_stream_hashes_all_16384_bytes_and_step_metadata(self):
        raw = bytes(16384)
        one, two = s.MatrixDigest(), s.MatrixDigest()
        kwargs = dict(opcode=0x23, index=7, context=0, last=True, error=False)
        one.append(raw, **kwargs)
        two.append(raw[:-1] + b'\x01', **kwargs)
        self.assertNotEqual(one.report()['sha256'], two.report()['sha256'])
        self.assertEqual(one.byte_count, 16398)
        with self.assertRaises(ValueError):
            one.append(raw[:-1], **kwargs)
        with self.assertRaises(ValueError):
            one.append(raw, **dict(kwargs, last=1))
        self.assertEqual(one.count, 1)

    def test_observer_factories_forward_exact_original_calls_and_keep_debts(self):
        original_error = RuntimeError('sentinel')
        class FakeScalar:
            def __init__(self, sentinel):
                self.sentinel, self.calls = sentinel, []
            def op(self, client, operation, x, y=0, *, policy='vector'):
                self.calls.append((client, operation, x, y, policy))
                if operation == 'failure':
                    raise original_error
                return self.sentinel
        class FakeMatrix:
            def __init__(self, sentinel):
                self.sentinel, self.calls = sentinel, []
                self.group, self.result, self.done = NS(opcode=0x23), None, object()
            def accept_step(self, owner, step):
                self.calls.append((owner, step))
                if not step.accept:
                    return False
                self.result = self.sentinel
                return True
            def retire_result(self, owner, result):
                self.result = None
        Scalar, Matrix = s.make_observers(FakeScalar, FakeMatrix)
        seen = []
        scalar = Scalar(0x7fc00001, observer_callback=seen.append)
        client = object()
        self.assertEqual(scalar.op(client, 'bf', 0x7fc00001), 0x7fc00001)
        self.assertEqual(scalar.calls, [(client, 'bf', 0x7fc00001, 0, 'vector')])
        self.assertEqual(seen, [('bf', 0x7fc00001, 0, 0x7fc00001, 'vector')])
        self.assertEqual(scalar.stream.count, 1)
        try:
            scalar.op(client, 'failure', 0)
        except RuntimeError as error:
            self.assertIs(error, original_error)
        else:
            self.fail('original exception must propagate')
        self.assertEqual(scalar.observer_failures, 1)
        self.assertEqual(scalar.stream.count, 1)
        result = NS(value=NS(raw=bytes(16384)), context=0, last=True, error=False)
        matrix = Matrix(result)
        done = matrix.done
        rejected = NS(accept=False, index=0)
        accepted = NS(accept=True, index=0)
        self.assertFalse(matrix.accept_step(client, rejected))
        self.assertEqual(matrix.stream.count, 0)
        self.assertTrue(matrix.accept_step(client, accepted))
        self.assertIs(matrix.result, result)
        self.assertIs(matrix.done, done)
        self.assertEqual(matrix.calls, [(client, rejected), (client, accepted)])
        self.assertEqual(matrix.stream.count, 1)
        self.assertIs(Matrix.retire_result, FakeMatrix.retire_result)

    def test_exact_m4_m8_m128_profile_counts_and_budgets(self):
        for tokens, packets, scalar, fmas, cap in (
                (4, 1920, 73152, 983040, 42944),
                (8, 6912, 253440, 3538944, 135552),
                (128, 1585152, 55480320, 811597824, 26483712)):
            with self.subTest(tokens=tokens):
                p = s.profile(tokens)
                self.assertEqual(p['matrix_packets'], packets)
                self.assertEqual(p['scalar_total_no_cutoff'], scalar)
                self.assertEqual(p['native_fmas'], fmas)
                self.assertEqual(p['model_event_cap'], cap)
                self.assertFalse(p['hardware_cycles'])
        p = s.profile(128)
        self.assertEqual(p['causal_pairs'], 99072)
        self.assertEqual(p['matrix_groups'], 111360)
        self.assertEqual(p['core_memory_requests'], 1609728)
        self.assertEqual(p['unique_kv_lines'], 4096)
        self.assertEqual(p['kv_hits'], 1581056)
        self.assertEqual(p['scalar_counts_no_cutoff'],
                         {'bf': 51119616, 'add': 2575872, 'mul': 1783296, 'div': 1536})
        for bad in (0, 129, True, 1.0):
            with self.assertRaises(ValueError):
                s.profile(bad)

    def test_import_never_loads_original_arithmetic_modules(self):
        script = '''import json,sys
from candidates.qwen2_resident_matrix.raw_kv_attention import streaming
print(json.dumps([name for name in sys.modules if name.endswith((
    '.prefix_arithmetic','.matrix_service','.official_bf16.owners'))]))'''
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run([sys.executable, '-c', script], cwd=root,
                                capture_output=True, text=True, timeout=5, check=True)
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == '__main__':
    unittest.main()
