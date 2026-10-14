"""Synthetic true64x2 dataflow, independent numeric and transport contracts.

Oracles may retain tensors and use numpy; the candidate never calls them.
No official 16x128 numeric acceptance, native execution, or RTL is claimed.
"""
from collections import Counter
from dataclasses import replace
import math
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from . import model as m
from .vector import Vector16, VectorArithmeticFault, build_library
from ..prep.scalar import PrepScalar
from ..rms_owner import ArithmeticFault, word


def produced(memory, base, raw, tag=10):
    r = memory.allocate_output(base, len(raw))
    for offset in range(0, len(raw), 64):
        memory.begin_write(m.WriteCommand(base + offset, 1, tag))
        memory.write_data(struct.unpack('<32H', raw[offset:offset + 64]), True)
        memory.acknowledge(m.WriteAck(tag, False, 64))
    memory.publish(base, (tag, None, len(raw)))
    return r


def fixture(tokens, seed=81):
    rng = np.random.default_rng(seed)
    raw = np.zeros((tokens, 6400), dtype='<f4')
    q = rng.uniform(-.075, .075, (tokens, 16)).astype(np.float32)
    k = rng.uniform(-.15, .15, (tokens, 16)).astype(np.float32)
    v = rng.uniform(-.8, .8, (tokens, 32)).astype(np.float32)
    raw[:, :16], raw[:, 2048:2064], raw[:, 4096:4128] = q, k, v
    raw[:, 6144] = rng.uniform(-.08, -.01, tokens).astype(np.float32)
    # Beta is BF16-materialized already, exactly as prep's interface requires.
    raw[:, 6145] = .5
    return raw.tobytes()


def recipe_exp(x):
    """Independent scalar FP32 recipe derived from math constants, no service."""
    f = np.float32
    magnitude = abs(f(x))
    z = f(magnitude * f(1 / math.log(2)))
    if magnitude >= 80:
        return f(0)
    exponent = int(z)
    fraction = f(z - f(exponent))
    coefficients = [f((-math.log(2)) ** i / math.factorial(i)) for i in range(8)]
    total = coefficients[-1]
    for c in reversed(coefficients[:-1]):
        total = f(f(total * fraction) + c)
    return f(total * f(2. ** -exponent))


def oracle(raw, state=None, *, fp32=True):
    """Independent formula model; explicit sequential FP32 matrix reductions.

    FP64 uses mathematical exp to diagnose the source exp approximation and
    FP32 roundoff. Neither version supplies candidate inputs or intermediates.
    """
    dtype = np.float32 if fp32 else np.float64
    data = np.frombuffer(raw, dtype='<f4').reshape(-1, 6400)
    tokens = len(data)
    state = np.zeros((16, 32), dtype=dtype) if state is None else np.array(state, dtype=dtype)
    result = []
    exp = recipe_exp if fp32 else math.exp
    def mm(a, b):
        total = np.zeros((a.shape[0], b.shape[1]), dtype=dtype)
        for k in range(a.shape[1]):
            product = np.multiply(a[:, k:k+1], b[k:k+1, :], dtype=dtype)
            total = np.add(total, product, dtype=dtype)
        return total
    def solve(lower, rhs):
        out = np.zeros_like(rhs)
        for i in range(64):
            total = np.zeros(rhs.shape[1], dtype=dtype)
            for k in range(i):
                total = np.add(total, np.multiply(lower[i, k], out[k], dtype=dtype), dtype=dtype)
            out[i] = np.subtract(rhs[i], total, dtype=dtype)
        return out
    for start in range(0, tokens, 64):
        n = min(64, tokens - start)
        q, k, v = (np.zeros((64, d), dtype=dtype) for d in (16, 16, 32))
        q[:n] = data[start:start+n, :16]
        k[:n] = data[start:start+n, 2048:2064]
        v[:n] = data[start:start+n, 4096:4128]
        g, beta = (np.zeros(64, dtype=dtype) for _ in range(2))
        g[:n] = data[start:start+n, 6144]
        beta[:n] = data[start:start+n, 6145]
        cumulative = np.empty(64, dtype=dtype)
        total = dtype(0)
        for i in range(64):
            total = dtype(total + g[i]); cumulative[i] = total
        decay = np.zeros((64, 64), dtype=dtype)
        for i in range(64):
            for j in range(i + 1):
                decay[i, j] = exp(dtype(cumulative[i] - cumulative[j]))
        eg = np.array([exp(x) for x in cumulative], dtype=dtype)
        end = np.array([exp(dtype(cumulative[-1] - x)) for x in cumulative], dtype=dtype)
        kb, vb = np.multiply(k, beta[:, None], dtype=dtype), np.multiply(v, beta[:, None], dtype=dtype)
        ut = np.multiply(mm(kb, k.T), decay, dtype=dtype)
        intra = np.multiply(mm(q, k.T), decay, dtype=dtype)
        solved_v = solve(ut, vb)
        solved_k = solve(ut, np.multiply(kb, eg[:, None], dtype=dtype))
        vnew = np.subtract(solved_v, mm(solved_k, state), dtype=dtype)
        inter = mm(np.multiply(q, eg[:, None], dtype=dtype), state)
        out = np.add(inter, mm(intra, vnew), dtype=dtype)
        update = mm(np.multiply(k, end[:, None], dtype=dtype).T, vnew)
        state = np.add(np.multiply(state, dtype(exp(cumulative[-1])), dtype=dtype), update, dtype=dtype)
        result.append(out[:n])
    return np.concatenate(result), state


def bf_bytes(values):
    bits = np.asarray(values, dtype='<f4').view('<u4')
    rounded = ((bits + np.uint32(0x7fff) + ((bits >> 16) & 1)) >> 16).astype('<u2')
    return rounded.tobytes()


class IdentityTests(unittest.TestCase):
    def test_actual_identity_excludes_reference_tests_and_detects_each_implementation_change(self):
        sources = Path(m.__file__).parent
        with tempfile.TemporaryDirectory(prefix='gdn-chunk-identity-') as directory:
            copied = Path(directory)
            for name in m.IMPLEMENTATION_SOURCES:
                (copied / name).write_bytes((sources / name).read_bytes())
            with patch.object(m, '__file__', str(copied / 'model.py')):
                before = m.source_identity()
                self.assertEqual(set(before['implementation_sha256']), {'model.py', 'vector.py', 'vector16.cpp', 'cumsum.py', 'exp_policy.py', 'matmul_reuse.py'})
                for name in ('reference.py', 'test_reference.py', 'test_model.py', 'README.md'):
                    (copied / name).write_text('unrelated initial contents\n')
                    self.assertEqual(before, m.source_identity())
                    (copied / name).write_text('unrelated changed contents\n')
                    self.assertEqual(before, m.source_identity())
                for name in m.IMPLEMENTATION_SOURCES:
                    path = copied / name
                    original = path.read_bytes()
                    path.write_bytes(original + b'\nsource identity drift\n')
                    changed = m.source_identity()
                    self.assertEqual(before['source_sha256'], changed['source_sha256'])
                    self.assertNotEqual(before['implementation_sha256'][name], changed['implementation_sha256'][name])
                    self.assertNotEqual(before, changed)
                    path.write_bytes(original)
                    self.assertEqual(before, m.source_identity())


class TransportOnlyTests(unittest.TestCase):
    """Driver/owner handshakes only: no library build or vector arithmetic.

    An explicit three-write request script exercises scratch/output/state
    retirement. It is not a Chunk arithmetic fixture or a numeric receipt.
    """
    def setup_driver(self):
        vector = object.__new__(Vector16)
        vector.client, vector.resource_address = None, id(vector)
        vector.exception_policy, vector.fatal_mask = 'legacy_vector_fatal_underflow', 30
        vector.calls, vector.lane_ops, vector.host_calls, vector.flags = (Counter() for _ in range(4))
        scalar = PrepScalar(enable_softplus=True)
        owner = m.ChunkOwner(scalar, vector, heads=1, key_dim=16, value_dim=32)
        job = m.ChunkJob(19, 0x100000, 0x500000, 0x510000, 0x520000, 0x600000,
                         1, True, 0, 1, 16, 32)
        memory = m.TypedMemory()
        produced(memory, job.input, bytes(job.input_bytes))
        for base, size in ((job.output, job.output_bytes), (job.state_out, job.state_bytes),
                           (job.scratch, job.scratch_bytes)):
            memory.allocate_output(base, size)
        def transport_script(j):
            yield (j.input, None)
            yield (j.scratch, bytes(64))
            yield (j.output, bytes(64))
            yield (j.state_out + j.state_bytes - 64, bytes(64))
        owner._compute = transport_script
        return m.TypedChunkDriver(owner, memory, job)

    def wait_pending(self, driver, target):
        for _ in range(16):
            if driver.pending is not None and driver.pending_request.address == target:
                return
            driver.tick()
        self.fail('bounded scripted transport target')

    def test_malformed_ack_drains_scratch_output_state_without_credit(self):
        for target_name in ('scratch', 'output', 'state_out'):
            for defect in ('tag', 'nbytes', 'error_type'):
                for fault in (None, 'abort', 'reset'):
                    with self.subTest(target=target_name, defect=defect, fault=fault):
                        d = self.setup_driver()
                        target = getattr(d.job, target_name) + (d.job.state_bytes - 64 if target_name == 'state_out' else 0)
                        self.wait_pending(d, target)
                        region = getattr(d, target_name)
                        coverage = region.acknowledged.copy()
                        ack_bytes, ack_count = d.owner.ack_bytes, d.owner.counts['write_acks']
                        scratch_bytes = d.owner.counts['scratch_ack_bytes']
                        wire = dict(ack_tag=d.pending.tag + 1) if defect == 'tag' else dict(ack_nbytes=32)
                        if defect == 'error_type':
                            d.pending = replace(d.pending, error=0)
                            wire = dict(ack_error=True)
                        physical = d.memory.pending
                        d.tick(memory_response_ready=False, **({fault: True} if fault else {}))
                        self.assertIs(d.memory.pending, physical)
                        with self.assertRaises(ValueError):
                            d.owner.reset()
                        event = d.tick(response_ready=False, **wire)
                        self.assertTrue(event['memory_response_fire'])
                        self.assertIsNone(d.pending)
                        self.assertIsNone(d.pending_request)
                        self.assertIsNone(d.pending_write)
                        self.assertIsNone(d.memory.pending)
                        self.assertEqual(d.owner.result.status, 'Protocol')
                        self.assertEqual(d.owner.ack_bytes, ack_bytes)
                        self.assertEqual(d.owner.counts['write_acks'], ack_count)
                        self.assertEqual(d.owner.counts['scratch_ack_bytes'], scratch_bytes)
                        self.assertEqual(region.acknowledged, coverage)
                        self.assertIn(target - region.base, region.written)
                        self.assertNotIn(target - region.base, region.acknowledged)
                        held = d.owner.result
                        d.tick(response_ready=False)
                        self.assertIs(d.owner.result, held)
                        with self.assertRaises(ValueError):
                            d.owner.reset()
                        d.tick()
                        self.assertIs(d.response, held)
                        self.assertFalse(d.response.staging_complete or d.output.published or d.state_out.published)
                        self.assertEqual(d.owner.counts['owner_results'], 1)
                        self.assertEqual(d.owner.state, 'locked')
                        self.assertIsNone(d.owner.scalar.client)
                        self.assertIsNone(d.owner.vector.client)
                        with self.assertRaisesRegex(ValueError, 'retired'):
                            d.tick()
                        d.owner.reset()
                        self.assertTrue(d.owner.ports()['job_ready'])

    def test_read_faults_and_existing_error_survive_abort_reset(self):
        for defect in ('tag', 'nbytes', 'data', 'error_type', 'memory'):
            for fault in (None, 'abort', 'reset'):
                with self.subTest(defect=defect, fault=fault):
                    d = self.setup_driver()
                    d.tick()
                    changes = {'tag': dict(read_tag=d.pending.tag + 1), 'nbytes': dict(read_nbytes=32)}.get(defect, {})
                    if defect in ('data', 'error_type', 'memory'):
                        d.pending = replace(d.pending, **{'data': dict(data=bytes(32)),
                            'error_type': dict(error=0), 'memory': dict(error=True)}[defect])
                    d.tick(memory_response_ready=False, **({fault: True} if fault else {}))
                    with self.assertRaises(ValueError):
                        d.owner.reset()
                    d.tick(response_ready=False, read_error=defect == 'error_type', **changes)
                    status = 'Memory' if defect == 'memory' else 'Protocol'
                    self.assertIsNone(d.pending)
                    self.assertIsNone(d.memory.pending)
                    self.assertEqual(d.owner.result.status, status)
                    d.tick(abort=True, response_ready=False)
                    self.assertEqual(d.owner.result.status, status)
                    d.tick()
                    self.assertFalse(d.output.published or d.state_out.published)
                    self.assertEqual(d.owner.state, 'locked')

    def test_final_state_ack_preserves_memory_error_and_concurrent_protocol(self):
        for fault in ('abort', 'reset'):
            for malformed in (False, True):
                with self.subTest(fault=fault, malformed=malformed):
                    d = self.setup_driver()
                    self.wait_pending(d, d.job.state_out + d.job.state_bytes - 64)
                    d.pending = replace(d.pending, error=True)
                    event = d.tick(**{fault: True}, **(dict(ack_tag=d.pending.tag + 1) if malformed else {}))
                    self.assertTrue(event['memory_response_fire'])
                    self.assertFalse(event['response_fire'])
                    self.assertIsNone(d.memory.pending)
                    self.assertEqual(d.owner.result.status, 'Protocol' if malformed else 'Memory')
                    self.assertEqual(d.owner.ack_bytes, 64)
                    self.assertEqual(d.owner.counts['scratch_ack_bytes'], 64)
                    self.assertFalse(d.state_out.acknowledged)
                    d.tick()
                    self.assertFalse(d.output.published or d.state_out.published)

    def test_unrelated_pending_write_is_never_retired(self):
        for replace_record in (False, True):
            d = self.setup_driver()
            self.wait_pending(d, d.job.scratch)
            physical = d.memory.pending
            command = physical[0]
            if replace_record:
                d.memory.pending = list(physical)
            else:
                physical[0] = replace(command, tag=command.tag + 1)
            unrelated = d.memory.pending
            with self.assertRaisesRegex(ValueError, 'physical write identity changed'):
                d.tick(ack_tag=d.pending.tag + 1)
            self.assertIs(d.memory.pending, unrelated)
            self.assertEqual(d.owner.state, 'wait')
            self.assertFalse(d.scratch.acknowledged)
            physical[0] = command
            d.memory.pending = physical
            d.tick(ack_error=True)
            d.tick()
            self.assertEqual(d.response.status, 'Memory')
            self.assertFalse(d.output.published or d.state_out.published)


class ChunkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='gdn-chunk-test-')
        cls.library = build_library(cls.tmp.name)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def setup_driver(self, tokens=64, raw=None, *, warm=None, host_batch=False):
        memory = m.TypedMemory()
        scalar, vector = PrepScalar(enable_softplus=True), Vector16(self.library)
        owner = m.ChunkOwner(scalar, vector, heads=1, key_dim=16, value_dim=32, host_batch=host_batch)
        job = m.ChunkJob(19, 0x100000, 0x500000, 0x510000, 0x520000, 0x600000,
                         tokens, warm is None, 0 if warm is None else 1, 1, 16, 32)
        raw = fixture(tokens) if raw is None else raw
        produced(memory, job.input, raw)
        if warm is not None: produced(memory, job.state_in, warm)
        memory.allocate_output(job.output, job.output_bytes)
        memory.allocate_output(job.state_out, job.state_bytes)
        memory.allocate_output(job.scratch, job.scratch_bytes)
        driver = m.TypedChunkDriver(owner, memory, job, current_generation=job.expected_generation,
                                    published_state_base=None if warm is None else job.state_in)
        return driver, raw

    def finish(self, driver, hook=None):
        for step in range(1000000):
            driver.tick(**({} if hook is None else hook(driver, step)))
            if driver.response is not None:
                return driver.response
        self.fail('bounded synthetic transport exceeded one million ticks')

    def test_vector_source_policy_and_exclusive_lease(self):
        vector = Vector16(self.library)
        owner, competitor = object(), object()
        self.assertTrue(vector.acquire(owner))
        self.assertFalse(vector.acquire(competitor))
        self.assertEqual(vector.op(owner, 'add', [0x80000000], [0x80000000]), [0x80000000])
        self.assertEqual(vector.op(owner, 'mul', [0x00800000], [0x3f000000]), [0x00400000])
        with self.assertRaises(ArithmeticFault): vector.op(owner, 'mul', [1], [word(.5)])
        with self.assertRaises(ArithmeticFault): vector.op(owner, 'mul', [0x7f7fffff], [word(2)])
        with self.assertRaises(ValueError): vector.op(competitor, 'add', [0], [0])
        vector.release(owner)
        self.assertEqual(vector.flags[2 | 1], 1)

    def test_ftz_daz_rejection_in_isolated_process_keeps_controls_unchanged(self):
        # Only this isolated test helper can change MXCSR. Production adapter
        # has no mode-changing API and must reject both modes before arithmetic.
        helper_source = Path(self.tmp.name) / 'test_mxcsr.cpp'
        helper = Path(self.tmp.name) / 'test_mxcsr.so'
        helper_source.write_text('''#include <xmmintrin.h>
#include <cfenv>
extern "C" unsigned get_csr() { return _mm_getcsr(); }
extern "C" void set_csr(unsigned value) { _mm_setcsr(value); }
extern "C" int get_flags() { return std::fetestexcept(FE_ALL_EXCEPT); }
extern "C" void raise_flags() { std::feraiseexcept(FE_DIVBYZERO); }
''')
        subprocess.run(['g++', '-std=c++17', '-shared', '-fPIC', str(helper_source), '-o', str(helper)],
                       check=True, capture_output=True, timeout=60)
        script = '''import ctypes as C, sys
from candidates.qwen35_gdn_prefill.chunk.vector import Vector16, VectorArithmeticFault
helper = C.CDLL(sys.argv[2])
helper.get_csr.restype = C.c_uint
helper.set_csr.argtypes = (C.c_uint,)
vector = Vector16(sys.argv[1]); owner = object(); assert vector.acquire(owner)
original = helper.get_csr()
assert vector.lib.gdn_vector16_environment() == 0
try:
    for bit, expected in ((1 << 15, -2), (1 << 6, -3), (1 << 13, -1)):
        selected = original | bit
        helper.set_csr(selected)
        assert vector.lib.gdn_vector16_environment() == expected
        for batched in (False, True):
            before = vector.calls.copy()
            try:
                if batched:
                    vector.mul_add(owner, [1], [0x3f000000], [0])
                else:
                    vector.op(owner, 'mul', [1], [0x3f000000])
            except VectorArithmeticFault as error:
                assert error.diagnostic['host_environment_status'] == expected
                assert error.diagnostic['result_words'] is None
                assert error.diagnostic['operation'] == 'mul'
            else:
                raise AssertionError('FTZ/DAZ request was admitted')
            assert vector.calls - before == {'mul': 1}
            assert helper.get_csr() == selected
finally:
    helper.set_csr(original)
assert helper.get_csr() == original
helper.raise_flags()
sticky = helper.get_flags()
vector.mul_add(owner, [0x3f800001], [0x3f7ffffe], [0xbf800000])
assert helper.get_flags() == sticky
'''
        subprocess.run([sys.executable, '-c', script, str(self.library), str(helper)],
                       check=True, capture_output=True, timeout=60)

    def test_host_batch_separate_rounding_special_values_and_fault_stage(self):
        vectors = [Vector16(self.library), Vector16(self.library)]
        clients = [object(), object()]
        for vector, client in zip(vectors, clients): self.assertTrue(vector.acquire(client))
        cases = [
            # Mul rounds to 1 before Add(-1), while a fused FMA would be -2^-46.
            ([0x3f800001], [0x3f7ffffe], [0xbf800000], [0]),
            ([0x80000000, 0, 0x00800000, 1], [word(1), word(-1), word(.5), word(1)],
             [0x80000000, 0, 1, 1], [0x80000000, 0, 0x00400001, 2]),
            # A later Mul-lane UF wins over an earlier would-be Add overflow.
            ([0x7f7fffff, 1], [word(1), word(.5)], [0x7f7fffff, 0], None),
            ([0x7f7fffff], [word(2)], [0], None),
            ([0x7f7fffff], [word(1)], [0x7f7fffff], None),
            ([0x7fc00001], [word(1)], [0], None),
            ([word(1)], [word(1)], [0x7f800000], None),
            ([1], [word(.5)], [0x7fc00000], None),
            ([word(1)], [word(1)], [], None),
            ([-1], [word(1)], [0], None),
        ]
        rng = random.Random(401)
        for lanes in range(1, 17):
            operands = [[word(rng.uniform(-2, 2)) for _ in range(lanes)] for _ in range(3)]
            cases.append((*operands, None))
        for a, b, total, expected in cases:
            outcomes = []
            for batched, vector, client in zip((False, True), vectors, clients):
                try:
                    result = (vector.mul_add(client, a, b, total) if batched else
                              vector.op(client, 'add', total, vector.op(client, 'mul', a, b)))
                    outcomes.append(('ok', result))
                except (ArithmeticFault, ValueError) as error:
                    outcomes.append((type(error), str(error), getattr(error, 'diagnostic', None)))
            self.assertEqual(outcomes[0], outcomes[1], (a, b, total))
            if expected is not None: self.assertEqual(outcomes[0], ('ok', expected))
            for name in ('calls', 'lane_ops', 'flags'):
                self.assertEqual(getattr(vectors[0], name), getattr(vectors[1], name))
        self.assertGreater(vectors[1].host_calls['mul_add'], 0)
        self.assertLess(sum(vectors[1].host_calls.values()), sum(vectors[0].host_calls.values()))
        with self.assertRaises(ValueError): vectors[1].mul_add(object(), [0], [0], [0])
        for vector, client in zip(vectors, clients): vector.release(client)

    def compare_batch_modes(self, *, scenario='success', warm=None, raw=None):
        drivers = [self.setup_driver(tokens=3, raw=raw, warm=warm, host_batch=mode)[0]
                   for mode in (False, True)]
        rng, held_ticks, fired = random.Random(581), 0, dict(request=0, response=0, terminal=0)
        triggered = False
        for step in range(1000000):
            left, right = drivers
            ports = left.owner.ports()
            # Streaming equality of the COMPLETE ordered request, response,
            # terminal and held-port trace. Payload and tag bytes are included.
            self.assertEqual(ports, right.owner.ports())
            self.assertEqual(left.pending, right.pending)
            knobs = dict(memory_ready=rng.random() > .12, memory_response_ready=rng.random() > .1)
            if ports['response'] is not None:
                held_ticks += 1
                knobs['response_ready'] = held_ticks > 3
            if (not triggered and left.owner.context['phase'] == 'ut_matmul' and
                    left.owner.position.get('reduction_k') == 1 and left.pending is not None):
                if scenario in ('abort', 'reset'):
                    knobs.update({scenario: True}, memory_response_ready=False)
                    triggered = True
                elif scenario == 'read_error':
                    knobs.update(read_error=True, memory_response_ready=True)
                    triggered = True
            if scenario == 'ack_error' and left.pending is not None and left.owner.request.write and (
                    left.owner.request.address == left.job.state_out + left.job.state_bytes - 64):
                knobs.update(ack_error=True, memory_response_ready=True)
                triggered = True
            events = [driver.tick(**knobs) for driver in drivers]
            self.assertEqual(events[0], events[1])
            fired['request'] += events[0]['memory_fire']
            fired['response'] += events[0]['memory_response_fire']
            fired['terminal'] += events[0]['response_fire']
            self.assertEqual(left.response, right.response)
            if left.response is not None: break
        else: self.fail('mode-pair trace exceeded bounded synthetic transport')
        self.assertEqual(fired['request'], fired['response'])
        self.assertEqual(fired['terminal'], 1)
        self.assertGreater(fired['request'], 0)
        if scenario not in ('success', 'numerical'): self.assertTrue(triggered)
        for base, region in left.memory.regions.items():
            other = right.memory.regions[base]
            self.assertEqual(region.raw(), other.raw())
            self.assertEqual(region.written, other.written)
            self.assertEqual(region.acknowledged, other.acknowledged)
            self.assertEqual(region.published, other.published)
        self.assertEqual(left.counts, right.counts)
        for name in ('calls', 'lane_ops', 'flags'):
            self.assertEqual(getattr(left.owner.vector, name), getattr(right.owner.vector, name))
        reports = [driver.owner.report() for driver in drivers]
        for report, mode in zip(reports, (False, True)):
            self.assertEqual(report.pop('host_batch'), mode)
            report.pop('host_call_counts')
        self.assertEqual(reports[0], reports[1])
        for driver in drivers:
            self.assertIsNone(driver.memory.pending)
            self.assertIsNone(driver.owner.vector.client)
            self.assertIsNone(driver.owner.scalar.client)
            self.assertFalse(driver.output.published or driver.state_out.published or driver.scratch.published)
        return drivers

    def test_host_batch_complete_success_trace_output_state_and_scratch(self):
        # Both cold and independently published nonzero warm state exercise all
        # matrix and solve stages, including partial final chunk padding.
        warm = np.random.default_rng(91).uniform(-.1, .1, (16, 32)).astype('<f4').tobytes()
        for initial in (None, warm):
            left, right = self.compare_batch_modes(warm=initial)
            self.assertIsNone(left.response.status)
            self.assertTrue(left.response.staging_complete)
            self.assertGreater(right.owner.host_counts['mul_add'], 0)
            self.assertEqual(sum(left.owner.host_counts.values()), sum(left.owner.vector_counts.values()))
            self.assertEqual(sum(right.owner.host_counts.values()) + right.owner.host_counts['mul_add'],
                             sum(right.owner.vector_counts.values()))

    def test_host_batch_complete_fault_abort_reset_traces_and_lifecycle(self):
        raw = bytearray(fixture(3))
        struct.pack_into('<I', raw, 2048 * 4, word(2. ** 70))
        add_raw = bytearray(fixture(3))
        struct.pack_into('<16I', add_raw, 2048 * 4, *([word(2. ** 63)] * 16))
        cases = [('numerical', bytes(raw), 'Numerical', 'mul'),
                 ('numerical', bytes(add_raw), 'Numerical', 'add'),
                 ('read_error', None, 'Memory', None), ('abort', None, 'Aborted', None),
                 ('reset', None, 'Aborted', None), ('ack_error', None, 'Memory', None)]
        for scenario, data, status, operation in cases:
            with self.subTest(scenario=scenario, operation=operation):
                drivers = self.compare_batch_modes(scenario=scenario, raw=data)
                for driver in drivers:
                    self.assertEqual(driver.response.status, status)
                    self.assertFalse(driver.response.staging_complete)
                    self.assertEqual(driver.owner.state, 'locked')
                    if scenario == 'numerical':
                        failure = driver.owner.first_numerical_failure
                        self.assertEqual(failure['phase'], 'ut_matmul')
                        self.assertEqual(failure['diagnostic']['operation'], operation)
                    mode = driver.owner.host_batch
                    driver.owner.reset()
                    self.assertEqual(driver.owner.host_batch, mode)
                    self.assertTrue(driver.owner.ports()['job_ready'])

    def test_host_batch_option_is_explicit_default_off_and_stable_during_job(self):
        driver, _ = self.setup_driver(tokens=1)
        self.assertFalse(driver.owner.host_batch)
        with self.assertRaises(ValueError):
            m.ChunkOwner(driver.owner.scalar, driver.owner.vector, host_batch=1)
        driver.owner.host_batch = True
        with self.assertRaisesRegex(ValueError, 'resources replaced'): driver.tick()
        driver.owner.host_batch = False
        self.finish(driver, lambda *_: dict(abort=True))

    def test_first_underflow_captures_phase_operands_results_and_lane_flags(self):
        raw = bytearray(fixture(1))
        struct.pack_into('<I', raw, 2048 * 4, 1)
        driver, _ = self.setup_driver(tokens=1, raw=bytes(raw))
        self.assertEqual(self.finish(driver).status, 'Numerical')
        report = driver.owner.report()
        failure = report['first_numerical_failure']
        self.assertEqual((failure['phase'], failure['head'], failure['chunk'], failure['row'], failure['column']),
                         ('prepare_key_query_products', 0, 0, 0, 0))
        detail = failure['diagnostic']
        self.assertEqual((detail['operation'], detail['active_lanes']), ('mul', 16))
        self.assertEqual((detail['a_words'][0], detail['b_words'][0], detail['result_words'][0]),
                         (1, word(.5), 0))
        self.assertEqual((detail['exception_flags'], detail['lane_exception_flags'][0]), (3, 3))
        for key in ('a_words', 'b_words', 'result_words', 'lane_exception_flags'):
            self.assertEqual(len(detail[key]), 16)
        driver.owner._remember_failure(ArithmeticFault('later diagnostic must not replace first'))
        self.assertEqual(driver.owner.report()['first_numerical_failure'], failure)
        self.assertNotIn('retained_arithmetic_vectors_max', report)
        self.assertFalse(report['hardware_register_allocation_established'])
        self.assertFalse(driver.output.published or driver.state_out.published)

    def test_true_chunk64x2_stepfp32_fp64_and_held_terminal(self):
        driver, raw = self.setup_driver(tokens=128)
        rng = random.Random(33)
        last_request = None
        for step in range(1000000):
            p = driver.owner.ports()
            if p['response'] is not None: break
            ready = rng.random() > .13
            if last_request is not None:
                self.assertEqual(p['memory'], last_request)
            last_request = p['memory'] if p['memory'] is not None and not ready else None
            driver.tick(memory_ready=ready, memory_response_ready=rng.random() > .1, response_ready=False)
        else: self.fail('chunk64x2 did not reach held terminal')
        held = driver.owner.ports()['response']
        self.assertIsNone(held.status, driver.owner.numerical_detail)
        self.assertEqual(driver.owner.counts['chunks_completed'], 2)
        self.assertEqual(driver.owner.counts['upper_triangle_masked'], 4032)
        self.assertFalse(driver.output.published or driver.state_out.published)
        for _ in range(4):
            driver.tick(response_ready=False)
            self.assertEqual(held, driver.owner.ports()['response'])
        with self.assertRaises(ValueError): driver.tick(reset=True, response_ready=False)
        result = self.finish(driver)
        self.assertTrue(result.staging_complete)
        self.assertFalse(result.state_committed or result.generation_advanced)
        self.assertFalse(driver.output.published or driver.state_out.published or driver.scratch.published)
        expected_out, expected_state = oracle(raw)
        self.assertEqual(driver.output.raw(), bf_bytes(expected_out))
        self.assertEqual(driver.state_out.raw(), expected_state.astype('<f4').tobytes())
        fp64_out, fp64_state = oracle(raw, fp32=False)
        np.testing.assert_allclose(expected_out, fp64_out, rtol=2e-4, atol=2e-7)
        np.testing.assert_allclose(expected_state, fp64_state, rtol=2e-4, atol=3e-7)
        self.assertEqual(result.write_bytes, driver.job.write_bytes)
        self.assertEqual(driver.owner.counts['scratch_ack_bytes'], driver.job.scratch_bytes)

    def test_two_calls_use_actual_published_previous_fp32_state(self):
        # Run a cold real64 chunk, jointly publish actual staging bytes, then
        # reuse the same TypedMemory, arithmetic services and owner for warm64.
        cold, first_raw = self.setup_driver(tokens=64)
        self.assertIsNone(self.finish(cold).status)
        state = np.frombuffer(cold.state_out.raw(), dtype='<f4').reshape(16, 32).copy()
        for r in (cold.output, cold.state_out):
            cold.memory.publish(r.base, (cold.response.tag, None, r.extent))
        second_raw = fixture(64, seed=111)
        job = replace(cold.job, tag=20, input=0x900000, state_in=cold.job.state_out,
                      output=0xc00000, state_out=0xc10000, scratch=0xd00000,
                      cold=False, expected_generation=1)
        produced(cold.memory, job.input, second_raw)
        for base, size in ((job.output, job.output_bytes), (job.state_out, job.state_bytes), (job.scratch, job.scratch_bytes)):
            cold.memory.allocate_output(base, size)
        with self.assertRaises(ValueError):
            m.TypedChunkDriver(cold.owner, cold.memory, job, current_generation=1, published_state_base=0x1234)
        warm = m.TypedChunkDriver(cold.owner, cold.memory, job, current_generation=1,
                                 published_state_base=cold.job.state_out)
        self.assertIsNone(self.finish(warm).status)
        out, next_state = oracle(second_raw, state)
        self.assertEqual(warm.output.raw(), bf_bytes(out))
        self.assertEqual(warm.state_out.raw(), next_state.astype('<f4').tobytes())
        self.assertEqual(warm.sources[1].raw(), state.astype('<f4').tobytes())
        self.assertFalse(warm.state_out.published)

    def test_last_state_ack_error_never_publishes_either_span(self):
        driver, _ = self.setup_driver(tokens=1)
        last = driver.job.state_out + driver.job.state_bytes - 64
        def hook(d, _):
            return dict(ack_error=d.pending is not None and d.owner.request.write and d.owner.request.address == last)
        result = self.finish(driver, hook)
        self.assertEqual(result.status, 'Memory')
        self.assertFalse(result.staging_complete)
        self.assertEqual(result.write_bytes, driver.job.write_bytes - 64)
        self.assertFalse(driver.output.published or driver.state_out.published)
        self.assertEqual(driver.owner.state, 'locked')
        self.assertIsNone(driver.owner.scalar.client)
        self.assertIsNone(driver.owner.vector.client)
        driver.owner.reset()
        self.assertTrue(driver.owner.ports()['job_ready'])

    def test_abort_drain_and_reset_preserve_single_terminal(self):
        driver, _ = self.setup_driver(tokens=1)
        driver.tick()  # first cold-state scratch write accepted
        self.assertIsNotNone(driver.memory.pending)
        driver.tick(abort=True, memory_response_ready=False)
        self.assertEqual(driver.owner.state, 'drain')
        self.assertIsNone(driver.owner.ports()['memory'])
        for _ in range(4): driver.tick(memory_response_ready=False)
        result = self.finish(driver)
        self.assertEqual(result.status, 'Aborted')
        self.assertEqual(driver.owner.counts['owner_results'], 1)
        self.assertIsNone(driver.memory.pending)
        self.assertFalse(driver.state_out.published or driver.output.published)
        driver.owner.reset()
        self.assertTrue(driver.owner.ports()['job_ready'])

    def test_exp_uses_shared_original_saturation_and_masks_upper_first(self):
        driver, _ = self.setup_driver(tokens=1)
        owner = driver.owner
        # Already admitted and holding the same caller-owned scalar lease.
        self.assertEqual(owner._exp(word(-90)), 0)
        self.assertEqual(owner._exp(word(-0.)), word(1))
        self.assertEqual(owner.exp_stats['saturated_abs_ge_80'], 1)
        self.assertEqual(owner.exp_stats['max_abs_input_word'], word(90))
        with self.assertRaises(ArithmeticFault): owner._exp(word(.01))
        self.assertEqual(owner.scalar.calls['exp_negative'], 2)
        self.finish(driver, lambda *_: dict(abort=True))

    def test_full_chunk_large_cumulative_decay_uses_source_saturation(self):
        raw = np.zeros((64, 6400), dtype='<f4')
        raw[:, 6144], raw[:, 6145] = -2., .5
        driver, _ = self.setup_driver(tokens=64, raw=raw.tobytes())
        self.assertIsNone(self.finish(driver).status)
        self.assertGreater(driver.owner.exp_stats['saturated_abs_ge_80'], 0)
        self.assertEqual(driver.owner.exp_stats['max_abs_input_word'], word(128))
        self.assertEqual(driver.owner.counts['upper_triangle_masked'], 2016)
        self.assertEqual(driver.owner.scalar_counts, {'exp_negative': 2209})
        self.assertEqual(driver.output.raw(), bytes(driver.job.output_bytes))
        self.assertEqual(driver.state_out.raw(), bytes(driver.job.state_bytes))

    def test_nonfinite_and_memory_read_faults_release_resources(self):
        raw = bytearray(fixture(1))
        struct.pack_into('<I', raw, 6144 * 4, 0x7fc00000)
        driver, _ = self.setup_driver(tokens=1, raw=bytes(raw))
        self.assertEqual(self.finish(driver).status, 'Numerical')
        self.assertFalse(driver.output.published or driver.state_out.published)
        self.assertIsNone(driver.owner.scalar.client)
        self.assertIsNone(driver.owner.vector.client)
        driver, _ = self.setup_driver(tokens=1)
        self.assertEqual(self.finish(driver, lambda *_: dict(read_error=True)).status, 'Memory')
        self.assertFalse(driver.output.published or driver.state_out.published)

    def test_owner_protocol_bad_tag_or_bytecount_and_active_reset(self):
        for response in (m.MemoryResponse(9, nbytes=64), m.MemoryResponse(0, nbytes=32)):
            driver, _ = self.setup_driver(tokens=1)
            owner = driver.owner
            request = owner.ports()['memory']
            owner.tick(memory_ready=True)
            owner.tick(memory_response=replace(response, tag=request.tag + 1 if response.tag else request.tag))
            self.assertEqual(owner.ports()['response'].status, 'Protocol')
            self.assertTrue(owner.tick(response_ready=True)['response_fire'])
            self.assertFalse(owner.tick(response_ready=True)['response_fire'])
            owner.reset()
            self.assertTrue(owner.ports()['job_ready'])
        driver, _ = self.setup_driver(tokens=1)
        driver.tick()
        driver.tick(reset=True, memory_response_ready=False)
        self.assertEqual(driver.owner.state, 'drain')
        self.assertEqual(self.finish(driver).status, 'Aborted')

    def test_bounds_and_unpublished_readonly_input_admission(self):
        driver, raw = self.setup_driver(tokens=1)
        job = driver.job
        for bad in (replace(job, tokens=129), replace(job, input=1 << 56),
                    replace(job, scratch=job.output), replace(job, state_in=job.state_out),
                    replace(job, expected_generation=(1 << 32) - 1)):
            with self.assertRaises(ValueError): bad.validate()
        full = m.ChunkJob(3, 0x100000, 0x1000000, 0x2000000, 0x3000000, 0x4000000, 128)
        full.validate((16, 128, 128))
        self.assertEqual((full.chunks, full.output_bytes, full.state_bytes), (2, 524288, 1048576))
        self.finish(driver, lambda *_: dict(abort=True))
        memory = m.TypedMemory()
        memory.add_readonly(job.input, raw)
        for base, size in ((job.output, job.output_bytes), (job.state_out, job.state_bytes), (job.scratch, job.scratch_bytes)):
            memory.allocate_output(base, size)
        owner = m.ChunkOwner(PrepScalar(), Vector16(self.library), heads=1, key_dim=16, value_dim=32)
        with self.assertRaises(ValueError): m.TypedChunkDriver(owner, memory, job)
        self.assertTrue(owner.ports()['job_ready'])


if __name__ == '__main__': unittest.main()
