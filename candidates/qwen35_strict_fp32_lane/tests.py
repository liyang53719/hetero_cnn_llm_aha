#!/usr/bin/env python3
"""Root-only <=10s/1CPU/256MiB source and independent SOFTWARE reference controls.
No Scala/HardFloat/Chisel/native/RTL execution. No real hardware handshakes.
"""
import argparse
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import types
import unittest

HERE = Path(__file__).resolve().parent
M = R = PINS = VECTORS = None
SUMMARY = {}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def audit(event, args):
    if event in ('ctypes.dlopen', 'subprocess.Popen', 'os.system', 'os.posix_spawn',
                 'os.fork', 'os.exec', 'os.remove', 'os.rename', 'os.rmdir',
                 'os.mkdir', 'os.unlink', 'os.symlink', 'os.link', 'os.truncate',
                 'os.chmod', 'os.chown', 'os.utime') or event.startswith('socket.'):
        raise RuntimeError('read-only software controls')
    if event == 'open':
        mode, flags = args[1], args[2]
        if ((isinstance(mode, str) and any(c in mode for c in 'wax+')) or
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise RuntimeError('no file writes')
        if isinstance(args[0], (str, bytes)) and os.fsdecode(args[0]).endswith('.pyc'):
            raise RuntimeError('unpinned bytecode forbidden')


def read(path, spec=None):
    require(path.is_file() and not path.is_symlink(), 'regular input required')
    before = path.stat()
    require(before.st_size < 2 * 1024 * 1024, 'small input cap')
    raw = path.read_bytes()
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(after), 'changed while read')
    got = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    if spec is not None:
        require(got == {k: spec[k] for k in ('bytes', 'sha256')}, str(path))
    return raw, got


def contained(root, name):
    p = Path(name)
    require(not p.is_absolute() and '..' not in p.parts, 'unsafe relative input')
    path = root / p
    require(path.resolve().is_relative_to(root.resolve()), 'escaping input')
    return path


class PinSet:
    def __init__(self, roots):
        manifest_raw, self.manifest = read(HERE / 'SOURCE_MANIFEST.json')
        manifest = json.loads(manifest_raw)
        self.cache, self.entries = {}, []
        for name, spec in manifest['files'].items():
            path = contained(HERE, name)
            raw, got = read(path, spec)
            self.cache[('own', name)] = raw
            self.entries.append((path, got))
        required = {'tests.py', 'lane_model.py', 'fraction_reference.py', 'DIRECTED_VECTORS.json',
                    'source/StrictFp32MatrixLane.scala', 'INPUT_PINS.json', 'SCOPE.json',
                    'README.md', 'TEST_COMMAND.json', 'INTERFACE_PROPOSAL.md',
                    'PROPOSAL_INPUT_PINS.json', 'FLAGS_BOUNDARY_ADDENDUM.md'}
        require(required <= set(manifest['files']), 'omitted own source')
        for label, spec in json.loads(self.cache[('own', 'INPUT_PINS.json')])['files'].items():
            root, name = spec['root'], spec['path']
            path = contained(roots[root], name)
            raw, got = read(path, spec)
            self.cache[(root, name)] = raw
            self.entries.append((path, got))
        self.entries.append((HERE / 'SOURCE_MANIFEST.json', self.manifest))

    def after(self):
        for path, spec in self.entries:
            read(path, spec)


def load(name, filename):
    module = types.ModuleType(name)
    module.__file__ = str(HERE / filename)
    sys.modules[name] = module
    exec(compile(PINS.cache[('own', filename)], module.__file__, 'exec'), module.__dict__)
    return module


def run_request(request, injected=None):
    lane = M.LaneModel(injected)
    before = lane.tick(request=request)
    require(before['request_ready'], 'fresh model admission')
    steps = 0
    while lane.state != 'reply':
        lane.tick()
        steps += 1
        require(steps <= 8, 'finite model stage bound')
    return lane, dict(lane.reply), steps


def normalized(reply):
    return dict(product=reply['product'], mul_flags=reply['mulFlags'],
                value=reply['value'], add_flags=reply['addFlags'],
                attempted=reply['passesCompleted'], status=reply['status'])


class SourceControls(unittest.TestCase):
    def test_single_original_arithmetic_chain_and_raw_widths(self):
        s = PINS.cache[('own', 'source/StrictFp32MatrixLane.scala')].decode()
        for name in ('HeteroFullFp32FmaPre', 'HeteroBF16FmaMul', 'HeteroBF16FmaPost', 'HeteroBF16FmaRound'):
            self.assertEqual(s.count('Module(new ' + name + ')'), 1)
        self.assertEqual(s.count('Module(new MulAddRecFNToRaw_preMul(8, 24))'), 1)
        self.assertNotRegex(s, r'Module\(new (?:MulRecFN|AddRecFN|MulAddRecFN)\(')
        self.assertNotIn('BlackBox', s)
        self.assertIn('round.io.exceptionFlags(4, 1).orR || !finite(round.io.out)', s)
        self.assertIn('Cat(job.a(31) ^ job.b(31), 0.U(31.W))', s)
        self.assertIn('Mux(addPass, reply.product, job.a)', s)
        self.assertIn('"h3f800000".U(32.W)', s)
        self.assertIn('state === idle && !reset.asBool', s)
        self.assertIn('state === replyStep && !reset.asBool', s)
        self.assertIn('reply := 0.U.asTypeOf(new StrictFp32LaneResponse)', s)
        self.assertEqual(s.count('when(state === preStep)'), 1)
        self.assertEqual(s.count('when(state === mulStep)'), 1)
        self.assertEqual(s.count('when(state === postStep)'), 1)
        self.assertEqual(s.count('when(state === roundStep)'), 1)
        request = s.split('class StrictFp32LaneRequest extends Bundle {', 1)[1].split('\n}', 1)[0]
        response = s.split('class StrictFp32LaneResponse extends Bundle {', 1)[1].split('\n}', 1)[0]
        width = lambda q: sum(map(int, re.findall(r'UInt\((\d+)\.W\)', q))) + q.count('Bool()')
        self.assertEqual(width(request), 130)
        self.assertEqual(width(response), 124)

    def test_reference_independence_and_flag_boundary_sources(self):
        ref = PINS.cache[('own', 'fraction_reference.py')].decode()
        integer = PINS.cache[('own', 'lane_model.py')].decode()
        self.assertIn('Fraction', ref)
        self.assertNotRegex(ref, r'(?:from|import)\s+lane_model')
        self.assertNotRegex(integer, r'(?:from|import)\s+(?:fractions|fraction_reference)')
        hf = PINS.cache[('hardfloat', 'RoundAnyRawFNToRecFN.scala')].decode()
        cpp = PINS.cache[('base', 'candidates/qwen35_gdn_prefill/chunk/vector16.cpp')].decode()
        self.assertIn('unboundedRange_roundIncr', hf)
        self.assertIn('std::fabs(r) < 0x1p-126f', cpp)
        self.assertIn('tininess_afterRounding', PINS.cache[('base', 'integration/gemmini/EmitHeteroBF16Fma.scala')].decode())


class ArithmeticControls(unittest.TestCase):
    def compare(self, a, b, acc, expected=None):
        oracle = R.strict(a, b, acc)
        lane, reply, steps = run_request(M.Request(19, 1, a, b, acc))
        self.assertEqual(normalized(reply), oracle)
        if expected is not None:
            self.assertEqual(oracle, expected)
        self.assertEqual(reply['accCommit'], oracle['status'] == 0)
        self.assertEqual(steps, 4 * oracle['attempted'])
        self.assertEqual(lane.stage_enables, dict.fromkeys(('pre', 'mul', 'post', 'round'), oracle['attempted']))
        self.assertEqual(reply['mulFlags'] & 24, 0)
        self.assertEqual(reply['addFlags'] & 26, 0)  # finite Add: no NV/DZ/natural inexact-tiny UF
        return lane, reply

    def test_directed_independent_reference_vectors(self):
        for row in VECTORS['vectors']:
            with self.subTest(name=row['id']):
                self.compare(int(row['a'], 16), int(row['b'], 16), int(row['acc'], 16),
                             {k: int(row['expected'][k], 16) if k in ('product', 'value') else row['expected'][k]
                              for k in ('product', 'mul_flags', 'value', 'add_flags', 'attempted', 'status')})
        SUMMARY['directed_vectors'] = len(VECTORS['vectors'])

    def test_fixed_seed_finite_bit_patterns(self):
        state = 0x1a2b3c4d
        for i in range(256):
            words = []
            for _ in range(3):
                state = (1664525 * state + 1013904223) & 0xffffffff
                u = state
                if (u & 0x7f800000) == 0x7f800000:
                    u ^= 0x00800000
                words.append(u)
            self.compare(*words)
        SUMMARY['fixed_seed_triples'] = 256

    def test_all_signed_zero_combinations(self):
        for a in (0, 0x80000000):
            for b in (0, 0x80000000, 0x3f800000, 0xbf800000):
                for c in (0, 0x80000000):
                    lane, reply = self.compare(a, b, c)
                    self.assertEqual(lane.round_inputs[0][2], (a ^ b) & 0x80000000)

    def test_no_single_fma_substitution_or_overflow_cancellation(self):
        a, b, c = 0x3f800001, 0x3f7ffffe, 0xbf800000
        _, reply = self.compare(a, b, c)
        self.assertEqual(reply['value'], 0)
        self.assertEqual(R.fma(a, b, c), (0xa8800000, 0))
        self.assertNotEqual(reply['value'], R.fma(a, b, c)[0])
        lane, reply = self.compare(0x7f7fffff, 0x40000000, 0xff7fffff)
        self.assertEqual((reply['status'], len(lane.round_inputs)), (4, 1))
        self.assertEqual(R.fma(0x7f7fffff, 0x40000000, 0xff7fffff), (0x7f7fffff, 0))

    def test_unbounded_tininess_is_not_delivered_exponent(self):
        _, reply = self.compare(0x00800000, 0x3f7fffff, 0)
        self.assertEqual((reply['product'], reply['mulFlags'], reply['status']), (0x00800000, 3, 4))
        cpp_delivered_exponent_flags = 1 | (2 if reply['product'] & 0x7fffffff < 0x00800000 else 0)
        self.assertEqual(cpp_delivered_exponent_flags, 1)
        _, threshold = self.compare(0x00f80000, 0x3f042108, 0)
        self.assertEqual((threshold['product'], threshold['mulFlags'], threshold['status']), (0x00800000, 1, 0))
        SUMMARY['known_cpp_flags_integration_blocker'] = dict(a='00800000', b='3f7fffff', product='00800000',
            hardfloat_source_expected_flags=3, old_cpp_predicate_flags=1, hardware_measured=False)

    def test_subnormal_exact_and_inexact_zero(self):
        for a, b, flags in ((0x00800000, 0x3f000000, 0), (1, 0x3f000000, 3),
                            (0x80000001, 0x3f000000, 3)):
            _, reply = self.compare(a, b, 0)
            self.assertEqual(reply['mulFlags'], flags)

    def test_legacy_finite_single_fused_mode(self):
        for a, b, c in ((0x3f80, 0x4000, 0xbf800000), (0x8000, 0x3f80, 0x80000000),
                        (0x3f81, 0x3f7e, 0xbf800000), (0x0080, 0x3f00, 1)):
            lane, reply, steps = run_request(M.Request(77, 0, a, b, c))
            expected = R.fma(a << 16, b << 16, c)
            self.assertEqual((reply['value'], reply['fmaFlags']), expected)
            self.assertEqual(steps, 4)
            self.assertTrue(reply['fmaFlagsValid'] and reply['valueValid'] and reply['accCommit'])
            self.assertFalse(reply['mulFlagsValid'] or reply['addFlagsValid'] or reply['productValid'])

    def test_short_dot_ascending_k_explicit_accumulator(self):
        acc = 0
        for a, b in ((0x3f800001, 0x3f7ffffe), (0xbf800000, 0x3f800000), (1, 0x3f800000)):
            _, reply = self.compare(a, b, acc)
            self.assertEqual(reply['status'], 0)
            acc = reply['value']
        self.assertEqual(acc, 1)


class ProtocolControls(unittest.TestCase):
    def test_reject_mode_encoding_nan_inf_without_pass_or_fake_flags(self):
        requests = [M.Request(1, m, 0, 0, 0) for m in (2, 3)]
        requests += [M.Request(2, 0, 0x10000, 0, 0), M.Request(3, 0, 0, 0xffff0000, 0)]
        for u in (0x7f800000, 0xff800000, 0x7fc00001, 0x7f800001, 0xffc12345):
            for field in range(3):
                v = [0x3f800000] * 3
                v[field] = u
                requests.append(M.Request(4, 1, *v))
        for request in requests:
            lane, reply, steps = run_request(request)
            self.assertEqual(steps, 0)
            self.assertEqual(reply['passesCompleted'], 0)
            self.assertFalse(reply['accCommit'] or reply['productValid'] or reply['valueValid'])
            self.assertFalse(reply['mulFlagsValid'] or reply['addFlagsValid'] or reply['fmaFlagsValid'])
            self.assertEqual(sum(lane.stage_enables.values()), 0)
            self.assertEqual((reply['tag'], reply['mode']), (request.tag, request.mode))

    def test_injected_mul_fatal_flags_never_start_add(self):
        for flags in (2, 4, 8, 16, 31):
            lane, reply, steps = run_request(M.Request(9, 1, 0x3f800000, 0x3f800000, 0),
                                            lambda operands, add_pass, mode: (0x3f800000, flags))
            self.assertEqual((reply['status'], steps), (4, 4))
            self.assertTrue(reply['productValid'] and reply['mulFlagsValid'])
            self.assertEqual(reply['mulFlags'], flags)
            self.assertFalse(reply['addFlagsValid'] or reply['valueValid'] or reply['accCommit'])
        # Injected finite arithmetic cannot naturally raise NV/DZ; this is a protocol guard test.

    def test_injected_add_fatal_preserves_both_attempts(self):
        def service(operands, add_pass, mode):
            return (0x7f800000, 5) if add_pass else (0x3f800000, 0)
        lane, reply, steps = run_request(M.Request(11, 1, 0x3f800000, 0x3f800000, 0), service)
        self.assertEqual((reply['status'], steps, reply['passesCompleted']), (5, 8, 2))
        self.assertTrue(reply['mulFlagsValid'] and reply['addFlagsValid'] and reply['valueValid'])
        self.assertFalse(reply['accCommit'])
        self.assertEqual(reply['value'], 0x7f800000)

    def test_injected_legacy_nonfinite_raw_result_is_not_strict_rejection(self):
        lane, reply, steps = run_request(M.Request(12, 0, 0x7f80, 0, 0),
                                        lambda operands, add_pass, mode: (0x7fc00000, 16))
        self.assertEqual((reply['status'], reply['value'], reply['fmaFlags']), (0, 0x7fc00000, 16))
        self.assertTrue(reply['accCommit'] and reply['fmaFlagsValid'])
        self.assertEqual(steps, 4)
        SUMMARY['legacy_nonfinite_case'] = 'INJECTED_RAW_ROUND_RESPONSE_PROTOCOL_ONLY_NOT_NAN_PAYLOAD_EQUIVALENCE'

    def test_held_reply_second_offer_and_no_same_edge_refill(self):
        lane, reply, _ = run_request(M.Request(13, 1, 0x3f800000, 0x40000000, 0))
        stages = dict(lane.stage_enables)
        offer = M.Request(14, 1, 0x3f800000, 0x3f800000, 0)
        for _ in range(8):
            pre = lane.tick(request=offer, result_ready=False)
            self.assertFalse(pre['request_ready'])
            self.assertEqual(lane.reply, reply)
            self.assertEqual(lane.stage_enables, stages)
        pre = lane.tick(request=offer, result_ready=True)
        self.assertTrue(pre['result_valid'])
        self.assertFalse(pre['request_ready'])
        self.assertEqual(lane.state, 'idle')
        lane.tick(request=offer)
        self.assertEqual(lane.job.tag, 14)

    def test_reset_at_every_stage_masks_handshakes_and_discards(self):
        request = M.Request(15, 1, 0x3f800000, 0x3f800000, 0)
        for advance in range(9):
            lane = M.LaneModel()
            lane.tick(request=request)
            for _ in range(advance):
                lane.tick()
            pre = lane.tick(request=request, result_ready=True, resetting=True)
            self.assertFalse(pre['request_ready'] or pre['result_valid'] or pre['busy'])
            self.assertEqual(lane.state, 'idle')
            self.assertEqual(lane.reply, M.blank_response())
            self.assertEqual(sum(lane.stage_enables.values()), 0)

    def test_reply_reentry_clears_prior_flags_and_diagnostics(self):
        lane, reply, _ = run_request(M.Request(16, 1, 1, 0x3f000000, 0))
        self.assertEqual(reply['mulFlags'], 3)
        lane.tick(result_ready=True)
        lane.tick(request=M.Request(17, 2, 0, 0, 0))
        self.assertEqual(lane.reply['tag'], 17)
        self.assertFalse(lane.reply['mulFlagsValid'] or lane.reply['productValid'])
        self.assertEqual(lane.reply['mulFlags'], 0)

    def test_four_registered_stages_each_pass_and_held_availability(self):
        for mode, expected in ((0, ['pre', 'mul', 'post', 'round', 'reply']),
                               (1, ['pre', 'mul', 'post', 'round', 'pre', 'mul', 'post', 'round', 'reply'])):
            request = M.Request(18, mode, 0x3f80 if mode == 0 else 0x3f800000,
                                0x3f80 if mode == 0 else 0x3f800000, 0)
            lane = M.LaneModel()
            lane.tick(request=request)
            seen = [lane.state]
            while lane.state != 'reply':
                lane.tick()
                seen.append(lane.state)
            self.assertEqual(seen, expected)
            self.assertTrue(lane.signals()['result_valid'])


def main():
    global M, R, PINS, VECTORS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--hardfloat', type=Path, required=True)
    args = parser.parse_args()
    require(sys.version_info[:2] == (3, 12), 'target CPython3.12 only')
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, '-I -S -B required')
    sys.addaudithook(audit)
    started = time.monotonic()
    PINS = PinSet(dict(base=args.base.resolve(), hardfloat=args.hardfloat.resolve()))
    result, error, after = None, None, False
    try:
        M = load('pinned_strict_lane_model', 'lane_model.py')
        R = load('pinned_fraction_reference', 'fraction_reference.py')
        VECTORS = json.loads(PINS.cache[('own', 'DIRECTED_VECTORS.json')])
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c)
                                   for c in (SourceControls, ArithmeticControls, ProtocolControls))
        result = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(suite)
    except Exception as exc:
        error = str(exc)
    finally:
        try:
            PINS.after()
            after = True
        except Exception as exc:
            error = 'AFTER_PIN_FAILURE: ' + str(exc)
    success = error is None and result is not None and result.wasSuccessful()
    print(json.dumps(dict(status='PASS_SOURCE_AND_INDEPENDENT_SOFTWARE_REFERENCE_ONLY' if success else 'FAIL',
        tests=0 if result is None else result.testsRun, pinned_files=len(PINS.entries), pins_before_after=after,
        source_manifest_sha256=PINS.manifest['sha256'], elapsed_seconds=round(time.monotonic()-started, 6),
        hardware_execution=False, scala_execution=False, numerical_hardware_equivalence=False,
        real_handshake_validation=False, fullblock_utilization_validation=False, scope=SUMMARY, error=error),
        sort_keys=True), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
