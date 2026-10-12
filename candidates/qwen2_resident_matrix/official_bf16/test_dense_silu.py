"""Bounded synthetic host policy checks; no checkpoint/RTL/full-block run."""
import ctypes as C
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from . import dense_silu as p
from ..ffn_attention.matrix_service import MatrixProtocolError, MatrixValue
from ..ffn_group.model import Job


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def fp(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def job_for(role, tag=71):
    k, n = p.ROLE_SHAPES[role]
    return Job('Dense', tag, 0x100000, 0x10000000, 0x20000000,
               16, n, k, 16 * n * 4, True, False, False)


def packet(output):
    return NS(context=0, last=True, error=False, value=MatrixValue(bytes(output)))


class RoundingPolicyTests(unittest.TestCase):
    def test_ties_sign_zero_subnormal_overflow(self):
        expected = {
            0x3f808000: 0x3f800000, 0x3f818000: 0x3f820000,
            0xbf808000: 0xbf800000, 0xbf818000: 0xbf820000,
            0: 0, 0x80000000: 0x80000000,
            0x00008000: 0, 0x00018000: 0x00020000,
            0x80008000: 0x80000000, 0x007fffff: 0x00800000,
            0x7f7f7fff: 0x7f7f0000, 0x7f7f8000: 0x7f800000,
            0xff7fffff: 0xff800000, 0x7f800000: 0x7f800000,
            0x7fc01234: 0x7fc01234,
        }
        for value, result in expected.items():
            with self.subTest(word=hex(value)):
                self.assertEqual(p.bf16_rne_word(value), result)
        for value in (-1, 1 << 32, True):
            with self.assertRaises(MatrixProtocolError):
                p.bf16_rne_word(value)

    def test_explicit_role_policy_and_storage_are_immutable(self):
        for role in p.ROLE_SHAPES:
            binding = p.DenseBinding.from_job(job_for(role), role)
            self.assertEqual(dict(binding.job_fields)['write_bytes'], 16 * p.ROLE_SHAPES[role][1] * 4)
            with self.assertRaises(FrozenInstanceError):
                binding.role = 'down'
            if role == 'down':
                for start, end in p.DOWN_GROUPS:
                    self.assertEqual(binding.materializes(start, end), end == 8960)
            else:
                self.assertEqual(binding.materializes(0, 1536), role in ('dense_o', 'gate', 'up'))
        for bad in (replace(job_for('gate'), output_bf16=True),
                    replace(job_for('gate'), activation_bf16=True),
                    replace(job_for('gate'), k=32)):
            with self.assertRaises((MatrixProtocolError, ValueError)):
                p.DenseBinding.from_job(bad, 'gate')
        with self.assertRaises(MatrixProtocolError):
            p.DenseBinding.from_job(job_for('down'), 'unknown')
        with self.assertRaises(MatrixProtocolError):
            p.DenseBinding.from_job(job_for('down'), 'gate')
        with self.assertRaises(MatrixProtocolError):
            p.DenseBinding.from_job(job_for('down'), 'down').materializes(0, 1536)


class CompiledPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='qwen2_bf16_dense_silu_')
        cls.path = Path(cls.temp.name)
        cls.lib, cls.receipt = p.build_library(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.assertEqual(self.lib.td_reset(), 0)
        self.assertEqual(self.lib.sf_reset_bf16_v1(), 0)

    def service_for(self, role):
        job = job_for(role)
        service = p.OfficialMatrixService(self.lib)
        owner = NS(job=job)
        service.bind_dense_job(job, role)
        self.assertTrue(service.acquire(owner, 'dense', job.tag))
        return service, owner, service.dense_library(owner)

    def finish(self, service, owner, bridge, result):
        bridge.retire_result(result)
        bridge.retire_done(NS(tag=owner.job.tag, error=False))
        service.retire_owner_response(owner)
        service.release(owner)

    def dense_packet(self, bridge, start=0, end=1536, seed=None):
        self.assertEqual(bridge.td_group(start, end, 1), 0)
        if start:
            self.assertIsNotNone(seed)
            words = (C.c_uint32 * 16)(*[seed] * 16)
            self.assertEqual(bridge.td_seed_begin(0), 0)
            for index in range(256):
                self.assertEqual(bridge.td_seed_beat(0, index, words), 0)
            self.assertEqual(bridge.td_seed_commit(0), 0)
            bridge.retire_seed_ack(NS(request=NS(tag=bridge.owner.job.tag, context=0), error=False))
        a, b, output = (C.c_uint16 * 16)(), (C.c_uint16 * 256)(), (C.c_uint32 * 4096)()
        for k in range(start, end):
            a[0] = b[0] = 0x3f81 if k == 0 else 0
            last = k + 1 == end
            self.assertEqual(bridge.td_step(k, 0, k == 0, last, last, last, a, b, output), int(last))
        return output

    def test_all_raw_projection_outputs_are_unrounded(self):
        for role in ('q_raw', 'k_raw', 'v_raw'):
            with self.subTest(role=role):
                self.assertEqual(self.lib.td_reset(), 0)
                service, owner, bridge = self.service_for(role)
                output = self.dense_packet(bridge)
                self.assertEqual(output[0], 0x3f820200)
                self.assertEqual(service.counts['dense_bf16_packets'], 0)
                self.finish(service, owner, bridge, packet(output))

    def test_dense_o_gate_up_round_packet_but_not_accumulator(self):
        for role in ('dense_o', 'gate', 'up'):
            with self.subTest(role=role):
                self.assertEqual(self.lib.td_reset(), 0)
                service, owner, bridge = self.service_for(role)
                output = self.dense_packet(bridge)
                self.assertEqual(output[0], 0x3f820000)
                accumulator = C.cast(service.resource_address, C.POINTER(C.c_uint32))
                self.assertEqual(accumulator[0], 0x3f820200)
                self.assertEqual(self.lib.matrix_accumulator_bytes(), 81920)
                self.assertEqual(service.counts['dense_bf16_packets'], 1)
                self.assertEqual(service.counts['dense_bf16_words'], 4096)
                self.finish(service, owner, bridge, packet(output))

    def test_down_prefix_and_terminal_use_actual_group_end(self):
        source = 0x3f818000
        for start, end in ((2560, 5120), (5120, 7680), (7680, 8960)):
            with self.subTest(group=(start, end)):
                self.assertEqual(self.lib.td_reset(), 0)
                service, owner, bridge = self.service_for('down')
                output = self.dense_packet(bridge, start, end, seed=source)
                expected = 0x3f820000 if end == 8960 else source
                self.assertEqual(set(output), {expected})
                accumulator = C.cast(service.resource_address, C.POINTER(C.c_uint32))
                self.assertEqual(accumulator[0], source)
                self.finish(service, owner, bridge, packet(output))
        # K2560 is also a prefix even when all contexts finish the group.
        service, owner, bridge = self.service_for('down')
        output = self.dense_packet(bridge, 0, 2560)
        self.assertEqual(output[0], 0x3f820200)
        self.finish(service, owner, bridge, packet(output))

    def test_materialized_digest_is_immutable_through_retirement(self):
        service, owner, bridge = self.service_for('gate')
        output = self.dense_packet(bridge)
        held = packet(output)
        self.assertEqual(bridge.pending[0][3], hashlib.sha256(bytes(output)).digest())
        output[0] = 0x3f820200
        with self.assertRaisesRegex(MatrixProtocolError, 'payload changed'):
            bridge.retire_result(packet(output))
        self.assertEqual(len(bridge.pending), 1)
        with self.assertRaises(MatrixProtocolError):
            bridge.retire_done(NS(tag=owner.job.tag, error=False))
        with self.assertRaises(MatrixProtocolError):
            service.release(owner)
        self.finish(service, owner, bridge, held)
        with self.assertRaises(MatrixProtocolError):
            bridge.retire_result(held)

    def test_dense_bf16_overflow_remains_visible_to_existing_owner(self):
        service, owner, bridge = self.service_for('down')
        output = self.dense_packet(bridge, 7680, 8960, seed=0x7f7fffff)
        self.assertEqual(set(output), {0x7f800000})
        self.assertEqual(service.counts['dense_bf16_overflow_words'], 4096)
        self.assertEqual(C.cast(service.resource_address, C.POINTER(C.c_uint32))[0], 0x7f7fffff)
        # The real existing Dense owner checks finite32 on every result word;
        # conversion must expose the infinity, rather than clamp it silently.
        from ..transposed_down.model import finite32
        self.assertFalse(finite32(output[0]))
        self.finish(service, owner, bridge, packet(output))

    def test_unbound_conflicting_changed_job_and_accumulator_alias_reject(self):
        service = p.OfficialMatrixService(self.lib)
        job = job_for('gate')
        owner = NS(job=job)
        with self.assertRaisesRegex(MatrixProtocolError, 'no explicit'):
            service.acquire(owner, 'dense', job.tag)
        binding = service.bind_dense_job(job, 'gate')
        self.assertEqual(service.bind_dense_job(job, 'gate'), binding)
        with self.assertRaisesRegex(MatrixProtocolError, 'conflicting'):
            service.bind_dense_job(job, 'up')
        with self.assertRaises(TypeError):
            service.bindings[job.tag] = binding
        self.assertTrue(service.acquire(owner, 'dense', job.tag))
        bridge = service.dense_library(owner)
        owner.job = replace(job, a=job.a + 64)
        with self.assertRaisesRegex(MatrixProtocolError, 'admitted Dense owner Job'):
            bridge.td_group(0, 1536, 1)
        owner.job = job
        self.assertEqual(bridge.td_group(0, 1536, 1), 0)
        with self.assertRaisesRegex(MatrixProtocolError, 'aliases the live'):
            bridge.td_step(1535, 0, False, True, True, True,
                (C.c_uint16 * 16)(), (C.c_uint16 * 256)(), C.c_void_p(service.resource_address))

    def vector(self, entrypoint, gates, ups):
        arrays = [(C.c_uint32 * 16)(*values) for values in (gates, ups, [0] * 16)]
        values, flags, errors = (C.c_uint32 * 96)(), (C.c_uint32 * 96)(), (C.c_uint32 * 16)()
        status = entrypoint(*arrays, values, flags, errors)
        return status, list(arrays[2]), list(values), list(flags), list(errors)

    def test_original_entrypoint_and_new_six_phase_boundaries(self):
        gates = [bits(x) for x in (0., -0., 1., -1., 2., -2., 5., -5., 12., -12., 79., -79., 80., -80., 100., -100.)]
        ups = [bits(0.5 + i / 16) for i in range(16)]
        legacy = self.vector(self.lib.sf_vector, gates, ups)
        official = self.vector(self.lib.sf_vector_bf16_v1, gates, ups)
        self.assertEqual(legacy[0], 0)
        self.assertEqual(official[0], 0)
        self.assertEqual(official[2][:64], legacy[2][:64])
        phase4 = [p.bf16_rne_word(x) for x in legacy[2][64:80]]
        phase5 = [p.bf16_rne_word(bits(fp(x) * fp(u))) for x, u in zip(phase4, ups)]
        self.assertEqual(official[2][64:80], phase4)
        self.assertEqual(official[1], phase5)
        self.assertEqual(official[2][80:96], phase5)
        self.assertNotEqual(official[1], legacy[1])
        self.assertNotEqual(phase5, [p.bf16_rne_word(x) for x in legacy[1]])
        reference = (C.c_uint32 * 16)()
        self.assertEqual(self.lib.sf_reference((C.c_uint32 * 16)(*gates),
                         (C.c_uint32 * 16)(*ups), reference, 16), 0)
        self.assertEqual(list(reference), legacy[1])
        self.assertEqual(official[1][1], 0x80000000)

    def test_new_silu_rounding_overflow_and_legacy_faults(self):
        result = self.vector(self.lib.sf_vector_bf16_v1, [0x7f7fffff] * 16, [bits(1)] * 16)
        self.assertEqual(result[0], 5)
        self.assertEqual(result[4], [1 << 4] * 16)
        self.assertEqual(result[2][64:80], [0x7f800000] * 16)
        for name in ('sf_vector', 'sf_vector_bf16_v1'):
            underflow = self.vector(getattr(self.lib, name), [bits(1)] * 16, [1] * 16)
            self.assertEqual(underflow[0], 6)
            self.assertTrue(all(flag & 2 for flag in underflow[3][80:96]))
            nonfinite = self.vector(getattr(self.lib, name), [0x7f800000] * 16, [bits(1)] * 16)
            self.assertEqual(nonfinite[0], -1)
            self.assertEqual(nonfinite[4], [64] * 16)

    def test_selected_facade_uses_separate_call_reset_counters(self):
        facade = p.selected_library(self.lib)
        self.assertIs(facade.sf_vector, self.lib.sf_vector_bf16_v1)
        self.vector(self.lib.sf_vector, [bits(1)] * 16, [bits(1)] * 16)
        self.assertEqual(facade.sf_calls(), 0)
        self.vector(facade.sf_vector, [bits(1)] * 16, [bits(1)] * 16)
        self.vector(facade.sf_vector, [0x7f800000] * 16, [bits(1)] * 16)
        self.assertEqual((facade.sf_calls(), facade.sf_failures()), (2, 1))
        self.assertEqual(facade.sf_reset(), 0)
        self.assertEqual((facade.sf_calls(), facade.sf_failures()), (0, 0))

    def test_new_compile_receipt_requires_actual_source_and_elf_identity(self):
        receipt = p.verify_library(self.path / 'official_bf16_compile.json')
        self.assertEqual(set(receipt['source_sha256']), set(p.SOURCE_CLOSURE))
        self.assertEqual(receipt, self.receipt)
        self.assertFalse(receipt['official_framework_acceptance'])
        self.assertEqual(receipt['status'], 'PASS')
        self.assertEqual(receipt['compiler'], p.compiler_identity())
        self.assertTrue(Path(receipt['compiler']['path']).is_absolute())
        self.assertEqual(receipt['argv'][1:6],
                         ['-shared', '-fPIC', '-O2', '-ffp-contract=off', '-fno-fast-math'])
        for change in ('source', 'elf', 'flags', 'abi', 'compiler', 'compiler_sha', 'compiler_path'):
            corrupted = json.loads(json.dumps(receipt))
            if change == 'source':
                corrupted['source_sha256'].pop(p.SOURCE_CLOSURE[-1])
            elif change == 'elf':
                corrupted['library_sha256'] = '0' * 64
            elif change == 'flags':
                corrupted['argv'][2] = '-ffast-math'
            elif change == 'abi':
                corrupted['selected_silu_entrypoint'] = 'sf_vector'
            elif change == 'compiler_sha':
                corrupted['compiler']['sha256'] = '0' * 64
            elif change == 'compiler_path':
                corrupted['compiler']['path'] += '.unverified'
            else:
                corrupted['compiler'] = 'unverified compiler'
            with self.subTest(change=change), self.assertRaises(MatrixProtocolError):
                p.verify_library(corrupted)

    def test_compile_failure_and_timeout_keep_receipt_and_logs(self):
        actual_run = subprocess.run
        for failure in ('nonzero', 'timeout'):
            def failed_run(argv, **kwargs):
                if argv[-1] == '--version':
                    return actual_run(argv, **kwargs)
                if failure == 'timeout':
                    raise subprocess.TimeoutExpired(argv, 30, output=b'compiler output', stderr=b'timed out')
                return subprocess.CompletedProcess(argv, 2, stdout='compiler output', stderr='compile failed')
            with tempfile.TemporaryDirectory() as directory, patch.object(p.subprocess, 'run', failed_run):
                with self.assertRaises((MatrixProtocolError, subprocess.TimeoutExpired)):
                    p.build_library(directory)
                root = Path(directory)
                receipt = json.loads((root / 'official_bf16_compile.json').read_text())
                self.assertEqual(receipt['status'], 'FAIL')
                self.assertEqual(receipt['stdout'], 'compiler output')
                self.assertEqual((root / 'official_bf16_compile.stdout.log').read_text(), receipt['stdout'])
                self.assertEqual((root / 'official_bf16_compile.stderr.log').read_text(), receipt['stderr'])
                self.assertEqual(receipt['returncode'], None if failure == 'timeout' else 2)
                self.assertIsNone(receipt['library_sha256'])


if __name__ == '__main__':
    unittest.main()
