"""Actual upstream coroutine + strict software arithmetic; no ChunkJob/RTL."""
import struct
import unittest
from dataclasses import replace

import numpy as np

from candidates.qwen35_gdn_prefill.chunk.model import ChunkOwner
from candidates.qwen35_gdn_prefill.rms_owner import ArithmeticFault as UpstreamArithmeticFault
from candidates.qwen35_gdn_prefill.typed_dense import TypedMemory
from candidates.qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from .model import Contraction, ArithmeticFault
from .test_model import Memory, words
from .upstream_coroutine import StrictUpstreamCoroutine, MemoryRequest, MemoryResponse, ResponseFault


class CoroutineTests(unittest.TestCase):
    def fixture(self, seed=100):
        rng = np.random.default_rng(seed)
        memory = Memory()
        a = words(rng.uniform(-.2, .2, (64, 128)).astype(np.float32))
        kt = words(rng.uniform(-.3, .3, (128, 64)).astype(np.float32))
        pair = np.tril(rng.uniform(.3, 1., (64, 64)).astype(np.float32))
        np.fill_diagonal(pair, 1.)
        matrices = tuple(memory.allocate(base, data) for base, data in (
            (0x10000, a), (0x20000, kt), (0x30000, words(pair)),
            (0x40000, np.full((64, 64), 0xdeadbeef, np.uint32))))
        return memory, matrices

    def physical(self, memory, matrices):
        physical = TypedMemory()
        for m in matrices[:-1]:
            # Synthetic phase-boundary operands, NOT actual preceding producers.
            physical.add_readonly(m.base, memory.regions[m.base].astype('<u4').tobytes())
        destination = physical.allocate_output(matrices[-1].base, 64 * 64 * 4)
        return physical, destination

    def accept(self, physical, request):
        self.assertIs(type(request), MemoryRequest)
        if not request.write:
            return MemoryResponse(request.tag, physical.read64(request.address))
        physical.begin_write(WriteCommand(request.address, 1, request.tag))
        physical.write_data(struct.unpack('<32H', request.data), True)
        physical.acknowledge(WriteAck(request.tag, False, 64))
        return MemoryResponse(request.tag)

    def expected_addresses(self, a, kt, pair, dst):
        # Independent row-major derivation, not calling Matrix.address.
        for row in range(64):
            for col in range(0, 64, 16):
                for start in range(0, 128, 16):
                    yield a.base + 4 * (row * 128 + start), False
                    for k in range(start, start + 16):
                        yield kt.base + 4 * (k * 64 + col), False
                yield pair.base + 4 * (row * 64 + col), False
                yield dst.base + 4 * (row * 64 + col), True

    def test_full_ut_qk_upstream_control_all_intermediates_and_typed_writes(self):
        for method in ('_matmul', '_read', '_write', '_mul_add'):
            self.assertIs(getattr(StrictUpstreamCoroutine, method), getattr(ChunkOwner, method))
        replay = StrictUpstreamCoroutine()
        for phase in (5, 6):
            with self.subTest(phase=phase):
                memory, matrices = self.fixture(100 + phase)
                trace = np.empty((2, 128, 64, 64), np.uint32)
                flags = np.empty((2, 128, 64, 64), np.uint8)
                pair_words = np.empty((64, 64), np.uint32)
                pair_flags = np.empty((64, 64), np.uint8)
                def capture(stage, k, values, exception_flags):
                    if stage == 'pair':
                        row, col = divmod(k, 64)
                        pair_words[row, col:col+16] = values
                        pair_flags[row, col:col+16] = exception_flags
                    else:
                        index = stage == 'add'
                        trace[int(index), k] = np.asarray(values).reshape(64, 64)
                        flags[int(index), k] = np.asarray(exception_flags).reshape(64, 64)
                strict = Contraction(memory.read, memory.write, capture)
                strict_counts = strict.run(*matrices, phase=phase)
                checked = 0
                def compare(stage, position, values, exception_flags):
                    nonlocal checked
                    row, col, k = (position[x] for x in ('row', 'column', 'reduction_k'))
                    if stage == 'pair':
                        expected, expected_flags = pair_words[row, col:col+16], pair_flags[row, col:col+16]
                    else:
                        index = int(stage == 'add')
                        expected, expected_flags = trace[index, k, row, col:col+16], flags[index, k, row, col:col+16]
                    self.assertEqual(values, expected.tolist())
                    self.assertEqual(exception_flags, expected_flags.tolist())
                    checked += 16
                replay.observe = compare
                physical, destination = self.physical(memory, matrices)
                program = replay.program(*matrices, phase=phase, tag=phase)
                schedule, response, requests = self.expected_addresses(*matrices), None, 0
                try:
                    while True:
                        try:
                            request = program.send(response)
                        except StopIteration as done:
                            counts = done.value
                            break
                        self.assertEqual((request.address, request.write), next(schedule))
                        self.assertEqual(request.tag, (phase << 32) | requests)
                        response = self.accept(physical, request)
                        requests += 1
                finally:
                    program.close()
                self.assertEqual(list(schedule), [])
                self.assertEqual(checked, 1052672)
                self.assertEqual(counts['read_requests'], 35072)
                self.assertEqual(counts['read_responses'], 35072)
                self.assertEqual(counts['write_requests'], 256)
                self.assertEqual(counts['write_acks'], 256)
                self.assertEqual((counts['mul_lane_ops'], counts['add_lane_ops'], counts['pair_lane_ops']),
                                 (524288, 524288, 4096))
                self.assertEqual(strict_counts['read_beats'], 1280)
                self.assertEqual(destination.raw(), memory.regions[matrices[-1].base].astype('<u4').tobytes())
                self.assertEqual(destination.written, set(range(0, 16384, 64)))
                self.assertEqual(destination.acknowledged, destination.written)
                self.assertFalse(destination.published)
                self.assertIsNone(physical.pending)
                self.assertFalse(replay.busy)

    def test_read_response_faults_stale_tag_and_nonfinite_stop_before_arithmetic(self):
        memory, matrices = self.fixture()
        replay = StrictUpstreamCoroutine()
        for mutant in ('tag', 'nbytes', 'short', 'error', 'type', 'nonfinite'):
            with self.subTest(mutant=mutant):
                program = replay.program(*matrices, phase=5)
                request = next(program)
                response = MemoryResponse(request.tag, bytes(64))
                if mutant == 'tag': response = replace(response, tag=request.tag + 1)
                if mutant == 'nbytes': response = replace(response, nbytes=32)
                if mutant == 'short': response = replace(response, data=bytes(63))
                if mutant == 'error': response = replace(response, error=True)
                if mutant == 'type': response = replace(response, error=1)
                if mutant == 'nonfinite': response = replace(response, data=struct.pack('<16I', 0x7fc00000, *([0] * 15)))
                error = UpstreamArithmeticFault if mutant == 'nonfinite' else ResponseFault
                with self.assertRaises(error): program.send(response)
                self.assertFalse(replay.busy)
                self.assertEqual(replay.counts['mul_lane_ops'], 0)
                self.assertEqual(replay.counts['write_requests'], 0)
        program = replay.program(*matrices, phase=6)
        a_request = next(program)
        b_request = program.send(MemoryResponse(a_request.tag, bytes(64)))
        self.assertNotEqual(a_request.tag, b_request.tag)
        with self.assertRaises(ResponseFault):
            program.send(MemoryResponse(a_request.tag, bytes(64)))
        self.assertFalse(replay.busy)

    def test_suspended_write_ownership_and_bad_second_ack_leave_partial_unpublished(self):
        memory, matrices = self.fixture()
        physical, destination = self.physical(memory, matrices)
        replay = StrictUpstreamCoroutine()
        program = replay.program(*matrices, phase=5, tag=9)
        reply = None
        while True:
            request = program.send(reply)
            if request.write and replay.counts['write_acks'] == 1: break
            reply = self.accept(physical, request)
        physical.begin_write(WriteCommand(request.address, 1, request.tag))
        physical.write_data(struct.unpack('<32H', request.data), True)
        self.assertEqual(destination.written, {0, 64})
        self.assertEqual(destination.acknowledged, {0})
        counts = replay.counts.copy()
        nested = replay.program(*matrices, phase=6)
        with self.assertRaisesRegex(RuntimeError, 'already active'): next(nested)
        self.assertEqual(replay.counts, counts)
        self.assertTrue(replay.busy)
        with self.assertRaisesRegex(ValueError, 'read before producer terminal'):
            physical.read64(matrices[-1].base)
        # Caller retires its actual physical obligation as failed. The adapter
        # only validates the original malformed wire ACK; it does not drain it.
        physical.acknowledge(WriteAck(request.tag, True, 64))
        with self.assertRaises(ResponseFault):
            program.send(MemoryResponse(request.tag + 1))
        self.assertEqual(replay.counts['write_acks'], 1)
        self.assertEqual(destination.acknowledged, {0})
        self.assertFalse(destination.published)
        self.assertFalse(replay.busy)
        self.assertIsNone(physical.pending)

    def test_strict_underflow_boundary_stops_original_coroutine_before_add(self):
        memory, matrices = self.fixture()
        memory.regions[matrices[0].base][:16] = 0x00800000
        memory.regions[matrices[1].base][:16] = 0x3f7fffff
        physical, destination = self.physical(memory, matrices)
        replay = StrictUpstreamCoroutine()
        program = replay.program(*matrices, phase=5)
        request = next(program)
        request = program.send(self.accept(physical, request))
        with self.assertRaises(ArithmeticFault) as caught:
            program.send(self.accept(physical, request))
        self.assertEqual((caught.exception.stage, caught.exception.word, caught.exception.flags),
                         ('mul', 0x00800000, 3))
        self.assertEqual(replay.counts['mul_lane_ops'], 16)
        self.assertEqual(replay.counts['add_lane_ops'], 0)
        self.assertEqual(destination.written, set())
        self.assertFalse(replay.busy)


if __name__ == '__main__':
    unittest.main()
