"""Bounded host-only Matrix arithmetic and transaction regression tests.

Run directly with Python or unittest. MATRIX_SERVICE_LIBRARY reuses a caller's
one combined host build. Otherwise compile matrix_numeric.cpp exactly once in
a fresh /tmp directory. MATRIX_SERVICE_EVIDENCE_DIR selects the parent directory
for a fresh evidence directory; no build or test evidence is written to Git.
The oracle calls the system libm.fmaf, never the candidate's arithmetic helpers.
These tests make no RTL, synthesized-resource, or hardware-cycle claim.
"""
import ctypes as C
import ctypes.util
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import time
from types import SimpleNamespace as NS
import unittest

import matrix_service as m


HERE = Path(__file__).resolve().parent
PINNED_TD_SHA256 = 'bdd7513bd788c03ac92be1d7c2f3553d3d7e0723ce1ac2892e93dcef58782ef1'
ZERO_A, ZERO_B = (0,) * 16, (0,) * 256
FINITE_BF16 = (0x0000, 0x8000, 0x0001, 0x8001, 0x007f, 0x807f,
               0x0080, 0x8080, 0x3f80, 0xbf80, 0x3f81, 0xbf83,
               0x3eab, 0xbeab, 0x3c01, 0xbc01)
LIB = LIBM = EVIDENCE = None
REPORT = {'host_model_only': True, 'hardware_simulation': False,
          'model_ticks_are_hardware_cycles': False, 'tests': []}


class F32Wire(C.c_float):
    """Keep IEEE bits at the libffi boundary, including signaling NaN payloads."""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    paths = [HERE / 'matrix_numeric.cpp', HERE / 'matrix_service.py', Path(__file__),
             *(m.ROOT / p for p in m.SOURCE_HASHES)]
    return {str(p.resolve()): sha(p) for p in paths}


def save_evidence():
    if EVIDENCE is not None:
        (EVIDENCE / 'test_evidence.json').write_text(json.dumps(REPORT, indent=2) + '\n')


def setUpModule():
    global LIB, LIBM, EVIDENCE
    root = Path(os.environ.get('MATRIX_SERVICE_EVIDENCE_DIR', tempfile.gettempdir()))
    root.mkdir(parents=True, exist_ok=True)
    EVIDENCE = Path(tempfile.mkdtemp(prefix='matrix_service_tests_', dir=root))
    REPORT['evidence_directory'] = str(EVIDENCE)
    REPORT['source_sha256_before'] = source_hashes()
    REPORT['started_unix'] = time.time()
    supplied = os.environ.get('MATRIX_SERVICE_LIBRARY')
    library = Path(supplied).resolve() if supplied else EVIDENCE / 'matrix_numeric.so'
    REPORT['library'] = str(library)
    REPORT['compiled_by_this_run'] = not bool(supplied)
    if not supplied:
        command = ['g++', '-shared', '-fPIC', '-O2', '-ffp-contract=off',
                   '-fno-fast-math', str(HERE / 'matrix_numeric.cpp'), '-o', str(library)]
        REPORT['compile_command'] = command
        started = time.monotonic()
        build = subprocess.run(command, cwd=EVIDENCE, capture_output=True, text=True, timeout=15)
        REPORT['compile_seconds'] = time.monotonic() - started
        REPORT['compile_returncode'] = build.returncode
        (EVIDENCE / 'compile.stdout').write_text(build.stdout)
        (EVIDENCE / 'compile.stderr').write_text(build.stderr)
        save_evidence()
        if build.returncode:
            raise RuntimeError('combined host build failed; see ' + str(EVIDENCE))
    REPORT['library_sha256'] = sha(library)
    LIB = m.configure_library(C.CDLL(str(library)))
    libm_name = ctypes.util.find_library('m') or 'libm.so.6'
    LIBM = C.CDLL(libm_name)
    LIBM.fmaf.argtypes = [C.c_float, C.c_float, C.c_float]
    LIBM.fmaf.restype = F32Wire
    REPORT['oracle'] = libm_name + ':fmaf; independent per-cell IEEE FP32 fused operation'
    save_evidence()


def tearDownModule():
    REPORT['source_sha256_after'] = source_hashes()
    REPORT['sources_unchanged'] = REPORT['source_sha256_before'] == REPORT['source_sha256_after']
    REPORT['elapsed_seconds'] = time.time() - REPORT['started_unix']
    save_evidence()
    print('\nMatrix host test evidence: ' + str(EVIDENCE))


def fp32(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def bits32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def oracle_fma(a16, b16, previous32):
    operands = (F32Wire.from_buffer_copy(struct.pack('<I', word))
                for word in (a16 << 16, b16 << 16, previous32))
    result = LIBM.fmaf(*operands)
    return struct.unpack('<I', C.string_at(C.byref(result), 4))[0]


def normal_oracle(previous, a, b):
    # The normal operation owns all 16x32 physical cells in slice zero.
    # Inactive slices are output zeros, irrespective of prior Dense contents.
    return tuple(tuple(oracle_fma(a[r], b[c], previous[r][c]) if c < 32 else 0
                       for c in range(256)) for r in range(16))


def dense_oracle(previous, a, b):
    # Independent statement of the historical transposed packet layout.
    return tuple(tuple(oracle_fma(a[r] if c < 128 else b[128+r],
                                  b[c % 128], previous[r][c])
                       for c in range(256)) for r in range(16))


def dense_result(output, context=0):
    return NS(context=context, value=tuple(tuple(output[r*256+c] for c in range(256))
                                          for r in range(16)), last=True, error=False)


class MatrixServiceTests(unittest.TestCase):
    def setUp(self):
        self.started = time.monotonic()
        self.assertEqual(LIB.td_reset(), 0)
        self.service = m.MatrixService(LIB)
        self.owner = object()

    def tearDown(self):
        outcome = self._outcome.result
        failures = [text for test, text in outcome.failures + outcome.errors
                    if test is self or getattr(test, 'test_case', None) is self]
        REPORT['tests'].append(dict(name=self.id(), seconds=time.monotonic()-self.started,
                                    passed=not failures, failures=failures,
                                    service_report=self.service.report()))
        save_evidence()

    def normal(self, tag=71):
        self.assertTrue(self.service.acquire(self.owner, 'normal', tag))
        return m.LegacyMatrixClient(self.service, self.owner)

    def dense(self, tag=83):
        self.assertTrue(self.service.acquire(self.owner, 'dense', tag))
        return self.service.dense_library(self.owner)

    def until(self, client, predicate, **kwargs):
        for _ in range(16):
            if predicate():
                return
            client.tick(**kwargs)
        self.fail('bounded host handshake did not reach the expected state: ' + client.state)

    def normal_reply(self, client, request):
        self.assertTrue(client.tick(request=request)['request_fire'])
        self.until(client, lambda: client.ports()['result'] is not None)
        return client.ports()['result']

    def finish_owner(self):
        with self.assertRaises(m.MatrixProtocolError):
            self.service.release(self.owner)
        self.service.retire_owner_response(self.owner)
        self.service.release(self.owner)

    def complete_normal(self, opcode, packets):
        client = self.normal()
        expected = tuple((0,) * 256 for _ in range(16))
        for index, (a, b) in enumerate(packets):
            final = index + 1 == len(packets)
            result = self.normal_reply(client, m.LegacyRequest(opcode, a, b, index == 0,
                                                                final, len(packets)))
            expected = normal_oracle(expected, a, b)
            self.assertFalse(result.error)
            self.assertEqual(result.value, expected)
            self.assertTrue(client.tick(result_ready=True)['result_fire'])
        self.assertEqual(LIB.matrix_normal_fmas(), len(packets) * 16 * 32)
        self.assertEqual(LIB.matrix_dense_fmas(), 0)
        self.finish_owner()
        return expected

    def test_source_identity_and_one_inherited_accumulator(self):
        identity = m.source_identity()
        legacy = HERE.parent / 'transposed_down' / 'numeric_smoke.cpp'
        self.assertEqual(sha(legacy), PINNED_TD_SHA256)
        self.assertEqual(m.SOURCE_HASHES[str(legacy.relative_to(m.ROOT))], PINNED_TD_SHA256)
        self.assertFalse(identity['hardware_simulation'])
        self.assertFalse(identity['model_ticks_are_hardware_cycles'])
        cpp = (HERE / 'matrix_numeric.cpp').read_text()
        self.assertIn('#include "../transposed_down/numeric_smoke.cpp"', cpp)
        self.assertFalse(re.search(r'\b(?:float|double)\s+\w+\s*\[', cpp))
        self.assertEqual(len(re.findall(r'\bfloat\s+accum\s*\[', legacy.read_text())), 1)
        self.assertEqual(LIB.matrix_accumulator_bytes(), 5 * 16 * 256 * 4)
        self.assertNotEqual(LIB.matrix_accumulator_address(), 0)

    def test_standalone_td_exports_remain_compatible_before_guard_enable(self):
        # A copied inode gives dlopen a separate instance of the same one build.
        # The primary library's guard was already enabled by setUp.
        copied = EVIDENCE / 'matrix_numeric_standalone.so'
        shutil.copyfile(REPORT['library'], copied)
        standalone = m.configure_library(C.CDLL(str(copied)))
        REPORT['standalone_library_sha256'] = sha(copied)
        self.assertEqual(REPORT['standalone_library_sha256'], REPORT['library_sha256'])
        self.assertEqual(standalone.td_reset(), 0)
        self.assertEqual(standalone.td_group(0, 16, 1), 0)
        a = (C.c_uint16*16)(*([0x3f80]*16))
        b = (C.c_uint16*256)(*([0x3f80]*144 + [0]*112))
        output = (C.c_uint32*4096)()
        expected = 0
        for k in range(16):
            last = k == 15
            self.assertEqual(standalone.td_step(k, 0, k == 0, last, last, last,
                                               a, b, output if last else None), int(last))
            expected = oracle_fma(0x3f80, 0x3f80, expected)
        self.assertEqual(tuple(output), (expected,)*4096)
        self.assertEqual(standalone.matrix_dense_fmas(), 16*4096)
        # Historical callers require no new result/done/owner callbacks.
        self.assertEqual(standalone.td_group(0, 16, 1), 0)
        self.assertEqual(standalone.td_reset(), 0)
        self.assertEqual(standalone.matrix_guard_enable(), 0)
        self.assertEqual(standalone.td_group(0, 16, 1), -4)
        self.assertEqual(standalone.matrix_acquire(1, 55), 0)
        self.assertEqual(standalone.td_group(0, 16, 1), 0)

    def test_qk_eight_step_diagonal_all_active_cells_and_inactive_slices(self):
        packets = []
        for k in range(8):
            a, b = list(ZERO_A), list(ZERO_B)
            a[k] = b[k] = 0x3f80
            packets.append((tuple(a), tuple(b)))
        value = self.complete_normal(0x23, packets)
        self.assertEqual(value, tuple(tuple(0x3f800000 if r == c and r < 8 else 0
                                           for c in range(256)) for r in range(16)))

    def test_qk_finite_bf16_signed_zeros_subnormals_and_rounding(self):
        packets = []
        for k in range(8):
            a = tuple(FINITE_BF16[(r + k*3) % 16] for r in range(16))
            b = tuple(FINITE_BF16[(c*3 + k*5) % 16] for c in range(16)) + (0,) * 240
            packets.append((a, b))
        self.complete_normal(0x23, packets)

    def test_pv_token_plus_one_lengths_and_row_zero_only(self):
        for token in (0, 2, 4, 30, 126, 127, 1023):
            with self.subTest(token=token, length=token+1):
                self.service.reset()
                packets = []
                for k in range(token+1):
                    a = (FINITE_BF16[k % 16],) + (0,) * 15
                    b = tuple(FINITE_BF16[(c+k*3) % 16] for c in range(16)) + (0,) * 240
                    packets.append((a, b))
                value = self.complete_normal(0x24, packets)
                self.assertTrue(all(word == 0 for row in value[1:] for word in row))

    def test_result_done_and_final_owner_reply_are_independent_fences(self):
        client = self.normal()
        request = m.LegacyRequest(0x24, (0x3f80,) + (0,)*15,
                                  (0x3f80,) + (0,)*255, True, True, 1)
        self.assertTrue(client.tick(request=request)['request_fire'])
        client.tick(); client.tick()
        held = self.service.result
        self.assertIsNotNone(held)
        self.assertIsInstance(held.value, m.MatrixValue)
        self.assertEqual(held.value.sha256, hashlib.sha256(held.value.raw).hexdigest())
        for _ in range(7):
            client.tick(service_result_ready=False)
            self.assertIs(self.service.result, held)
            self.assertIsNone(self.service.done)
            self.assertIsNone(client.ports()['result'])
            self.assertFalse(self.service.acquire(object(), 'dense', 2))
        with self.assertRaises(m.MatrixProtocolError):
            self.service.retire_owner_response(self.owner)
        self.assertTrue(client.tick()['service_result_fire'])
        done = self.service.done
        for _ in range(5):
            client.tick(service_done_ready=False)
            self.assertIs(self.service.done, done)
            self.assertIsNone(client.ports()['result'])
        with self.assertRaises(m.MatrixProtocolError):
            self.service.retire_legacy_reply(self.owner, held.ticket, held.epoch)
        self.assertTrue(client.tick()['service_done_fire'])
        response = client.ports()['result']
        for _ in range(5):
            client.tick(result_ready=False)
            self.assertIs(client.ports()['result'], response)
            with self.assertRaises(m.MatrixProtocolError):
                self.service.retire_owner_response(self.owner)
        self.assertTrue(client.tick(result_ready=True)['result_fire'])
        self.assertEqual(self.service.counts['normal_results'], 1)
        self.assertEqual(self.service.counts['normal_done'], 1)
        self.assertEqual(self.service.counts['legacy_replies'], 1)
        self.finish_owner()

    def test_nonfinal_reply_must_retire_before_next_step(self):
        client = self.normal()
        request = m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, False, 3)
        response = self.normal_reply(client, request)
        self.assertFalse(self.service.ports()['step_ready'])
        self.assertIsNone(self.service.done)
        self.assertFalse(client.tick(request=replace(request, clear=False))['request_fire'])
        self.assertIs(client.ports()['result'], response)
        self.assertTrue(client.tick(result_ready=True)['result_fire'])
        self.assertTrue(self.service.ports()['step_ready'])

    def test_modes_share_resource_and_cannot_mix_or_bypass_ownership(self):
        address = self.service.resource_address
        client = self.normal()
        self.assertFalse(self.service.acquire(object(), 'dense', 99))
        with self.assertRaises(m.MatrixProtocolError):
            self.service.dense_library(self.owner)
        self.assertEqual(LIB.td_group(0, 16, 1), -4)
        response = self.normal_reply(client, m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, True, 1))
        self.assertFalse(response.error)
        client.tick(result_ready=True)
        self.finish_owner()
        adapter = self.dense()
        self.assertEqual(adapter.td_group(0, 16, 1), 0)
        self.assertEqual(LIB.matrix_normal_group(0x24, 1, 1, 1), -4)
        self.assertEqual(self.service.resource_address, address)
        self.assertEqual(LIB.matrix_accumulator_address(), address)
        with self.assertRaises(m.MatrixProtocolError):
            adapter.td_reset()

    def test_wrong_done_tag_drains_to_error_and_requires_reset(self):
        client = self.normal()
        client.tick(request=m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, True, 1))
        self.until(client, lambda: client.state == 'wait_done')
        done = self.service.done
        edge = client.tick(done_override=replace(done, tag=done.tag+1))
        self.assertTrue(edge['service_done_fire'])
        self.assertTrue(client.ports()['result'].error)
        client.tick(result_ready=True)
        self.assertEqual(client.state, 'locked')
        self.assertTrue(self.service.reset_required)
        self.finish_owner()
        self.assertFalse(self.service.acquire(object(), 'dense', 99))

    def test_abort_before_arithmetic_drains_error_done_without_result(self):
        client = self.normal()
        client.tick(request=m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, True, 1))
        client.tick()
        self.assertEqual(client.state, 'issue')
        client.tick(abort=True)
        self.until(client, lambda: client.ports()['result'] is not None)
        response = client.ports()['result']
        self.assertTrue(response.error)
        self.assertIsNone(response.value)
        self.assertEqual(LIB.matrix_normal_fmas(), 0)
        client.tick(result_ready=True)
        self.assertEqual(client.state, 'locked')
        self.finish_owner()

    def test_abort_with_held_result_preserves_payload_then_errors(self):
        client = self.normal()
        client.tick(request=m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, False, 3))
        client.tick(); client.tick()
        held = self.service.result
        client.tick(abort=True, service_result_ready=False)
        self.assertIs(self.service.result, held)
        self.until(client, lambda: client.ports()['result'] is not None)
        response = client.ports()['result']
        self.assertEqual(response.value, held.value)
        self.assertTrue(response.error)
        client.tick(result_ready=True)
        self.finish_owner()

    def test_abort_between_packets_drains_without_inventing_an_owner_reply(self):
        client = self.normal()
        self.normal_reply(client, m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, False, 3))
        client.tick(result_ready=True)
        self.assertEqual(client.state, 'idle')
        edge = client.tick(abort=True, service_done_ready=False)
        self.assertFalse(edge['result_fire'])
        self.assertFalse(client.ports()['drained'])
        self.assertIsNone(client.ports()['result'])
        with self.assertRaises(m.MatrixProtocolError):
            self.service.retire_owner_response(self.owner)
        self.until(client, lambda: client.ports()['drained'])
        self.assertIsNone(client.ports()['result'])
        self.assertEqual(self.service.counts['legacy_replies'], 1)
        self.assertEqual(self.service.counts['normal_done'], 1)
        self.finish_owner()

    def test_abort_preserves_already_exposed_owner_reply_under_backpressure(self):
        client = self.normal()
        response = self.normal_reply(client,
            m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, False, 3))
        self.assertFalse(response.error)
        client.tick(abort=True, result_ready=False, service_done_ready=False)
        for _ in range(4):
            client.tick(result_ready=False, service_done_ready=False)
            self.assertIs(client.ports()['result'], response)
        self.assertTrue(client.tick(result_ready=False)['service_done_fire'])
        self.assertIs(client.ports()['result'], response)
        self.assertTrue(self.service.reset_required)
        self.assertFalse(client.ports()['drained'])
        self.assertTrue(client.tick(result_ready=True)['result_fire'])
        self.assertTrue(client.ports()['drained'])
        self.finish_owner()

    def test_invalid_groups_produce_error_done_without_tensor_or_fmas(self):
        for opcode, count, mask in ((0x23, 7, 1), (0x23, 9, 1), (0x24, 0, 1),
                                    (0x24, 1025, 1), (0x22, 1, 1), (0x24, 1, 3)):
            with self.subTest(opcode=opcode, count=count, mask=mask):
                self.service.reset()
                client = self.normal()
                response = self.normal_reply(client, m.LegacyRequest(opcode, ZERO_A, ZERO_B,
                                              True, True, count, mask))
                self.assertTrue(response.error)
                self.assertIsNone(response.value)
                self.assertEqual(LIB.matrix_normal_fmas(), 0)
                self.assertIsNone(self.service.result)
                client.tick(result_ready=True)
                self.finish_owner()

    def test_normal_special_operands_propagate_bits_with_all_512_fmas(self):
        special = (0x7f80, 0xff80, 0x7fc1, 0xffc2, 0x7f81, 0xff81,
                   0, 0x8000, 0x0001, 0x8001, 0x3f80, 0xbf80,
                   0x7f7f, 0xff7f, 0x3eab, 0xbeab)
        a = special
        b = special + tuple(reversed(special)) + (0x7f81,) * 224
        value = self.complete_normal(0x24, [(a, b)])
        self.assertTrue(any((word & 0x7f800000) == 0x7f800000
                            for row in value for word in row[:32]))
        self.assertFalse(self.service.reset_required)

    def test_normal_uses_b_lanes_16_through_31_and_ignores_later_lanes(self):
        a = tuple(0x3f80 if r % 2 == 0 else 0xbf80 for r in range(16))
        b = (0,) * 16 + (0x4000,) * 16 + (0x7f81, 0xff80) * 112
        value = self.complete_normal(0x24, [(a, b)])
        for r, row in enumerate(value):
            self.assertEqual(row[:16], (0,) * 16)
            self.assertEqual(row[16:32], (0x40000000 if r % 2 == 0 else 0xc0000000,) * 16)
            self.assertEqual(row[32:], (0,) * 224)

    def test_normal_selected_inf_and_nan_are_values_not_protocol_failures(self):
        for a0, b0 in ((0x7f7f, 0x7f7f), (0x7f80, 0), (0x7fc1, 0x3f80)):
            with self.subTest(a0=a0, b0=b0):
                self.service.reset()
                value = self.complete_normal(0x24, [((a0,) + (0,)*15,
                                                   (b0,) + (0,)*255)])
                self.assertEqual(value[0][0] & 0x7f800000, 0x7f800000)
                self.assertFalse(self.service.reset_required)

    def test_qk_offdiagonal_overflow_preserves_all_zero_selected_diagonal(self):
        a, b = list(ZERO_A), list(ZERO_B)
        a[0], b[1] = 0x7f7f, 0x7f7f
        value = self.complete_normal(0x23, [(tuple(a), tuple(b))] + [(ZERO_A, ZERO_B)] * 7)
        self.assertEqual(value[0][1], 0x7f800000)
        self.assertEqual(tuple(value[r][r] for r in range(16)), (0,) * 16)
        self.assertFalse(self.service.reset_required)

    def test_matrix_value_preserves_all_4096_word_bits_and_is_immutable(self):
        special = (0, 0x80000000, 1, 0x007fffff, 0x00800000, 0x7f800000,
                   0xff800000, 0x7fc12345, 0xffc12345, 0x7f812345,
                   0xff812345, 0x7f7fffff, 0xff7fffff)
        words = tuple(special[(i // 2) % len(special)] if i % 2 == 0
                      else (i * 0x9e3779b1) & 0xffffffff for i in range(4096))
        raw = struct.pack('<4096I', *words)
        expected = tuple(words[r*256:(r+1)*256] for r in range(16))
        value = m.MatrixValue(raw)
        self.assertEqual(len(value), 16)
        self.assertEqual(value.raw, raw)
        self.assertEqual(bytes(value), raw)
        self.assertEqual(value.sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(tuple(tuple(row) for row in value), expected)
        self.assertEqual(value, expected)
        self.assertEqual(expected, value)
        self.assertEqual(value, m.MatrixValue(raw))
        self.assertEqual(value[-1][-1], expected[-1][-1])
        self.assertEqual(tuple(tuple(row) for row in value[::-1]), expected[::-1])
        self.assertEqual(tuple(tuple(row) for row in value[1:9:2]), expected[1:9:2])
        for r in range(16):
            self.assertEqual(len(value[r]), 256)
            self.assertEqual(value[r][-256], expected[r][0])
            self.assertEqual(tuple(value[r][1:19:3]), expected[r][1:19:3])
            self.assertEqual(tuple(value[r][::-1]), expected[r][::-1])
        changed = bytearray(raw)
        snapshot = m.MatrixValue(changed)
        changed[-1] ^= 1
        self.assertEqual(snapshot.raw, raw)
        self.assertEqual(snapshot, expected)
        self.assertNotEqual(value, m.MatrixValue(bytes(changed)))
        self.assertNotEqual(value, expected[:-1])
        for invalid in (16, -17):
            with self.assertRaises(IndexError):
                value[invalid]
        for invalid in (256, -257):
            with self.assertRaises(IndexError):
                value[0][invalid]
        with self.assertRaises(TypeError):
            value[0] = expected[0]
        with self.assertRaises(TypeError):
            value[0][0] = 1
        with self.assertRaises((AttributeError, TypeError)):
            value.raw = b''
        with self.assertRaises((AttributeError, TypeError)):
            value.sha256 = 'changed'
        self.assertEqual(value.raw, raw)

    def test_invalid_clear_during_active_group_drains_actual_done(self):
        client = self.normal()
        self.normal_reply(client, m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, False, 3))
        client.tick(result_ready=True)
        ticket = self.service.ticket
        edge = client.tick(request=m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, False, 3),
                           service_done_ready=False)
        self.assertTrue(edge['request_fire'])
        self.assertEqual(self.service.ticket, ticket)
        self.assertEqual(LIB.matrix_normal_fmas(), 512)
        for _ in range(4):
            client.tick(service_done_ready=False)
            self.assertFalse(client.ports()['drained'])
            self.assertIsNone(client.ports()['result'])
        with self.assertRaises(m.MatrixProtocolError):
            self.service.retire_owner_response(self.owner)
        self.until(client, lambda: client.ports()['result'] is not None)
        response = client.ports()['result']
        self.assertTrue(response.error)
        self.assertIsNone(response.value)
        self.assertEqual(self.service.counts['normal_done'], 1)
        self.assertTrue(client.tick(result_ready=True)['result_fire'])
        self.assertTrue(client.ports()['drained'])
        self.assertEqual(LIB.matrix_normal_fmas(), 512)
        self.finish_owner()

    def test_bad_step_controls_fault_without_counting_arithmetic(self):
        base = m.NormalStep(0, ZERO_A, ZERO_B, True, True, finish=True)
        for changes in ({'index': 1}, {'context': 1}, {'clear': False},
                        {'last': False}, {'finish': False}, {'emit': False}):
            with self.subTest(changes=changes):
                self.service.reset()
                self.normal()
                self.assertTrue(self.service.accept_group(self.owner, m.NormalGroup(0x24, 1, 14)))
                self.assertTrue(self.service.accept_step(self.owner, replace(base, **changes)))
                self.assertIsNone(self.service.result)
                self.assertTrue(self.service.done.error)
                self.assertEqual(LIB.matrix_normal_fmas(), 0)

    def test_reset_invalidates_old_result_done_and_client(self):
        client = self.normal()
        client.tick(request=m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, True, 1))
        client.tick(); client.tick()
        old_result = self.service.result
        client.tick()
        old_done = self.service.done
        self.service.reset()
        self.assertTrue(self.service.acquire(self.owner, 'normal', 71))
        self.assertTrue(self.service.accept_group(self.owner, m.NormalGroup(0x24, 1, 1)))
        self.assertGreater(self.service.ticket, old_result.ticket)
        for callback in (lambda: self.service.retire_result(self.owner, old_result),
                         lambda: self.service.retire_done(self.owner, old_done),
                         lambda: self.service.retire_legacy_reply(self.owner, old_result.ticket,
                                                                  old_result.epoch),
                         lambda: client.tick()):
            with self.assertRaises(m.MatrixProtocolError):
                callback()
        self.assertEqual(LIB.matrix_normal_fmas(), 0)

    def test_late_done_from_previous_group_is_rejected(self):
        client = self.normal()
        request = m.LegacyRequest(0x24, ZERO_A, ZERO_B, True, True, 1)
        client.tick(request=request)
        self.until(client, lambda: client.state == 'wait_done')
        old_done = self.service.done
        client.tick(); client.tick(result_ready=True)
        client.tick(request=request); client.tick()
        self.assertGreater(self.service.ticket, old_done.ticket)
        with self.assertRaises(m.MatrixProtocolError):
            self.service.retire_done(self.owner, old_done)

    def test_dense_historical_signature_mapping_and_explicit_retirement(self):
        adapter = self.dense()
        self.assertEqual(adapter.td_group(0, 16, 2), 0)
        a = tuple(FINITE_BF16[r] for r in range(16))
        b = tuple(FINITE_BF16[(c*3+5) % 16] for c in range(144)) + (0,)*112
        ca, cb = (C.c_uint16*16)(*a), (C.c_uint16*256)(*b)
        expected = tuple((0,)*256 for _ in range(16))
        for _ in range(16):
            expected = dense_oracle(expected, a, b)
        for context in range(2):
            output = (C.c_uint32*4096)()
            for k in range(16):
                last = k == 15
                self.assertEqual(adapter.td_step(k, context, k == 0, last,
                                  last and context == 1, last, ca, cb, output), int(last))
            result = dense_result(output, context)
            self.assertEqual(result.value, expected)
            self.assertEqual(len(adapter.pending), 1)
            with self.assertRaises(m.MatrixProtocolError):
                adapter.retire_done(NS(tag=self.service.owner_tag, error=False))
            changed = [list(row) for row in result.value]
            changed[0][0] ^= 1
            with self.assertRaises(m.MatrixProtocolError):
                adapter.retire_result(NS(context=context, value=changed, last=True, error=False))
            adapter.retire_result(result, ticket=adapter.ticket, epoch=self.service.epoch)
        self.assertEqual(LIB.matrix_dense_fmas(), 2*16*4096)
        self.assertEqual(LIB.matrix_normal_fmas(), 0)
        with self.assertRaises(m.MatrixProtocolError):
            self.service.retire_owner_response(self.owner)
        adapter.retire_done(NS(tag=self.service.owner_tag, error=False),
                            ticket=adapter.ticket, epoch=self.service.epoch)
        self.assertEqual(self.service.counts['dense_results'], 2)
        self.finish_owner()

    def test_dense_seed_old_256_beat_mapping_and_explicit_seed_ack(self):
        adapter = self.dense()
        self.assertEqual(adapter.td_group(16, 32, 1), 0)
        self.assertEqual(adapter.td_seed_begin(0), 0)
        expected = tuple(tuple(bits32(float(1+r*256+c)) for c in range(256)) for r in range(16))
        for index in range(256):
            row = (index % 32) // 2
            col = (index // 32)*32 + (index % 2)*16
            words = (C.c_uint32*16)(*expected[row][col:col+16])
            self.assertEqual(adapter.td_seed_beat(0, index, words), 0)
        self.assertEqual(adapter.td_seed_commit(0), 0)
        output = (C.c_uint32*4096)()
        a, b = (C.c_uint16*16)(), (C.c_uint16*256)()
        self.assertEqual(adapter.td_step(16, 0, False, False, False, False, a, b, output), -4)
        self.assertEqual(LIB.matrix_dense_fmas(), 0)
        with self.assertRaises(m.MatrixProtocolError):
            self.service.retire_owner_response(self.owner)
        with self.assertRaises(m.MatrixProtocolError):
            adapter.retire_seed_ack(NS(request=NS(tag=999, context=0), error=False))
        ack = NS(request=NS(tag=self.service.owner_tag, context=0), error=False)
        adapter.retire_seed_ack(ack, ticket=adapter.ticket, epoch=self.service.epoch)
        with self.assertRaises(m.MatrixProtocolError):
            adapter.retire_seed_ack(ack)
        for k in range(16, 32):
            last = k == 31
            self.assertEqual(adapter.td_step(k, 0, False, last, last, last, a, b, output), int(last))
        result = dense_result(output)
        self.assertEqual(result.value, expected)
        adapter.retire_result(result, ticket=adapter.ticket, epoch=self.service.epoch)
        adapter.retire_done(NS(tag=self.service.owner_tag, error=False))
        self.assertEqual(self.service.counts['dense_seed_acks'], 1)
        self.assertEqual(LIB.matrix_dense_fmas(), 16*4096)
        self.finish_owner()

    def test_dense_original_group_length_restrictions_remain(self):
        adapter = self.dense()
        invalid = ((0, 0, 1), (16, 16, 1), (16, 0, 1), (0, 15, 1), (1, 16, 1),
                   (0, 2576, 1), (0, 8976, 1), (0, 16, 0), (0, 16, 6))
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                self.assertEqual(adapter.td_group(*arguments), -1)
        self.assertEqual(LIB.matrix_dense_fmas(), 0)
        self.assertFalse(self.service.reset_required)
        self.assertEqual(adapter.td_group(0, 16, 5), 0)

    def test_dense_finish_rejects_an_unfinished_declared_context(self):
        adapter = self.dense()
        self.assertEqual(adapter.td_group(0, 16, 2), 0)
        a, b = (C.c_uint16*16)(), (C.c_uint16*256)()
        # The inherited ABI permits a null terminal pointer until LAST.
        for k in range(15):
            self.assertEqual(adapter.td_step(k, 1, k == 0, False, False, False, a, b, None), 0)
        output = (C.c_uint32*4096)()
        self.assertEqual(adapter.td_step(15, 1, False, True, True, True, a, b, output), -1)
        self.assertEqual(LIB.matrix_dense_fmas(), 15*4096)
        self.assertEqual(len(adapter.pending), 0)
        self.assertTrue(self.service.reset_required)
        adapter.retire_done(NS(tag=self.service.owner_tag, error=True))
        self.finish_owner()

    def test_dense_reference_signature_stays_available_only_when_unowned(self):
        adapter = self.dense()
        activations = (C.c_uint32*(128*8960))()
        weights = (C.c_uint16*8960)()
        output = (C.c_uint32*128)()
        weights[0] = 0x3f80
        for row in range(128):
            activations[row*8960] = 0x3f800000
        self.assertEqual(adapter.td_reference(activations, weights, output, 1), -4)
        self.finish_owner()
        self.assertEqual(LIB.td_reference(activations, weights, output, 1), 0)
        expected = oracle_fma(0x3f80, 0x3f80, 0)
        self.assertEqual(tuple(output), (expected,)*128)
        self.assertEqual(LIB.matrix_dense_fmas(), 0)
        self.assertEqual(LIB.matrix_normal_fmas(), 0)

    def test_dense_error_done_still_waits_for_seed_ack(self):
        adapter = self.dense()
        self.assertEqual(adapter.td_group(16, 32, 1), 0)
        self.assertEqual(adapter.td_seed_begin(0), 0)
        self.service.abort(self.owner)
        adapter.retire_done(NS(tag=self.service.owner_tag, error=True))
        with self.assertRaises(m.MatrixProtocolError):
            self.service.retire_owner_response(self.owner)
        adapter.retire_seed_ack(NS(request=NS(tag=self.service.owner_tag, context=0), error=True))
        self.finish_owner()
        self.assertTrue(self.service.reset_required)

    def test_dense_partial_fault_counter_is_actual_fma_calls(self):
        adapter = self.dense()
        self.assertEqual(adapter.td_group(0, 16, 1), 0)
        a = (C.c_uint16*16)(*([0x7f7f]*16))
        b = (C.c_uint16*256)(*([0x7f7f]*144 + [0]*112))
        output = (C.c_uint32*4096)()
        for k in range(15):
            self.assertEqual(adapter.td_step(k, 0, k == 0, False, False, False, a, b, output), 0)
        self.assertEqual(adapter.td_step(15, 0, False, True, True, True, a, b, output), -3)
        self.assertEqual(LIB.matrix_dense_fmas(), 15*4096 + 1)
        self.assertEqual(len(adapter.pending), 0)
        self.assertTrue(self.service.reset_required)
        adapter.retire_done(NS(tag=self.service.owner_tag, error=True))
        self.finish_owner()

    def test_dense_reset_rejects_old_adapter_and_callbacks(self):
        adapter = self.dense()
        self.assertEqual(adapter.td_group(16, 32, 1), 0)
        old_ticket, old_epoch = adapter.ticket, self.service.epoch
        self.service.reset()
        self.assertTrue(self.service.acquire(self.owner, 'dense', 83))
        fresh = self.service.dense_library(self.owner)
        self.assertEqual(fresh.td_group(16, 32, 1), 0)
        self.assertGreater(fresh.ticket, old_ticket)
        for callback in (lambda: adapter.td_group(0, 16, 1),
                         lambda: adapter.td_seed_begin(0),
                         lambda: fresh.retire_done(NS(tag=83, error=False),
                                                  ticket=old_ticket, epoch=old_epoch),
                         lambda: fresh.retire_seed_ack(NS(request=NS(tag=83, context=0), error=False),
                                                      ticket=old_ticket, epoch=old_epoch)):
            with self.assertRaises(m.MatrixProtocolError):
                callback()

    def test_dense_release_and_reacquire_rejects_previous_adapter(self):
        previous = self.dense()
        self.finish_owner()
        fresh = self.dense()
        self.assertIsNot(fresh, previous)
        with self.assertRaises(m.MatrixProtocolError):
            previous.td_group(0, 16, 1)
        self.assertEqual(fresh.td_group(0, 16, 1), 0)
        with self.assertRaises(m.MatrixProtocolError):
            previous.td_seed_begin(0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
