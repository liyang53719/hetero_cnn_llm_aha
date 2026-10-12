"""Original FP32 Elementwise Add ordering and failure-boundary model tests."""
from dataclasses import replace
import struct
import unittest

from candidates.qwen2_resident_matrix.ffn_public import prefix_owners as p
from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import Harness, ref_add


def make(left=None, right=None):
    j = p.Job('Add', (7 << 16) | 14, 0x100000, 0x200000, 0x300000,
              1, 1536, 1536, 6144)
    left = list(left if left is not None else [0x3f800000] * 1536)
    right = list(right if right is not None else [0x3e800000] * 1536)
    h = Harness()
    h.bus.input(j.a, left); h.bus.input(j.b, right); h.bus.output(j.dst, j.write_bytes)
    return h, j, left, right


class ResidualTests(unittest.TestCase):
    def test_two_tiles_signed_zero_and_rounding_against_exact_rational(self):
        patterns = [(0x80000000, 0x80000000), (0x3f800000, 0x33800000),
                    (0x00800000, 0x807fffff), (0x3f800001, 0xbf800000)]
        left, right = zip(*(patterns[i % len(patterns)] for i in range(1536)))
        h, j, left, right = make(left, right)
        result = h.run(j)
        self.assertIsNone(result.status)
        self.assertEqual(struct.unpack('<1536I', h.bus.raw(j.dst)),
                         tuple(ref_add(a, b) for a, b in zip(left, right)))
        expected = []
        for start, count in ((0, 1024), (1024, 512)):
            for base, write in ((j.a, False), (j.b, False), (j.dst, True)):
                expected += [(base + 4 * i, write) for i in range(start, start + count, 16)]
        self.assertEqual([(q.address, q.write) for q in h.bus.trace], expected)
        self.assertTrue(all(q.tag >> 32 == (7 << 16) | 8 for q in h.bus.trace))
        self.assertEqual(h.owner.report()['peak_add_tile_words'], 3072)

    def test_late_lane_nonfinite_and_overflow_no_same_tile_store(self):
        for lane in (1023, 1535):
            for a, b in ((0x7fc00000, 0), (0x7f7fffff, 0x7f7fffff)):
                left, right = [0x3f800000] * 1536, [0] * 1536
                left[lane], right[lane] = a, b
                h, j, _, _ = make(left, right)
                result = h.run(j, publish=False)
                self.assertEqual(result.status, 'Numerical')
                self.assertEqual(result.write_bytes, 0 if lane == 1023 else 4096)
                self.assertEqual(len(h.bus.writes) * 64, result.write_bytes)
                self.assertFalse(h.bus.outputs[j.dst].intersection(h.bus.readable))
                self.assertEqual(h.owner.state, 'locked')

    def test_final_ack_and_completion_backpressure(self):
        h, j, _, _ = make()
        h.tick(job=j)
        h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                and h.bus.pending.address + 64 == j.dst + j.write_bytes)
        for _ in range(7):
            h.tick(respond=False, response_ready=True)
            self.assertIsNone(h.owner.ports()['response'])
            self.assertEqual(h.owner.ack_bytes, j.write_bytes - 64)
        self.assertTrue(h.tick()['memory_response_fire'])
        result = h.owner.ports()['response']
        self.assertEqual(result.write_bytes, j.write_bytes)
        for _ in range(3):
            h.tick()
            self.assertEqual(h.owner.ports()['response'], result)
        self.assertTrue(h.tick(response_ready=True)['response_fire'])

    def test_final_ack_fault_retains_unpublished_output(self):
        h, j, _, _ = make()
        h.tick(job=j)
        h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                and h.bus.pending.address + 64 == j.dst + j.write_bytes)
        q = h.bus.pending
        h.tick(response=p.MemoryResponse(q.tag, error=True))
        result = h.owner.ports()['response']
        self.assertEqual((result.status, result.write_bytes), ('Memory', j.write_bytes - 64))
        self.assertFalse(h.bus.outputs[j.dst].intersection(h.bus.readable))

    def test_reset_drains_read_and_requires_coordinated_recovery(self):
        h, j, _, _ = make()
        h.tick(job=j); h.tick()
        self.assertIsNotNone(h.bus.pending)
        h.tick(local_reset=True, respond=False)
        self.assertEqual(h.owner.state, 'drain')
        self.assertIsNone(h.owner.ports()['response'])
        h.tick()
        self.assertEqual(h.owner.ports()['response'].status, 'Protocol')
        h.tick(response_ready=True)
        self.assertEqual(h.owner.state, 'locked')
        h.tick(reset=True)
        self.assertEqual(h.owner.state, 'idle')

    def test_invalid_typed_shape_and_alias_rejected_before_dma(self):
        for changes in ({'output_bf16': True}, {'n': 1024, 'k': 1024},
                        {'dst': 0x100000}, {'b': 0x200001}, {'write_bytes': 64}):
            h, j, _, _ = make()
            result = h.run(replace(j, **changes), publish=False)
            self.assertIsNotNone(result.status)
            self.assertEqual((h.bus.reads, h.bus.writes), ([], []))


if __name__ == '__main__':
    unittest.main()
