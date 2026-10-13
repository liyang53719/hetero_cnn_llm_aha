"""Small M1 memory/FP32/transport gates; no full native forward or RTL run."""
from collections import Counter
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import struct
import time
import unittest
from unittest.mock import patch

import numpy as np

from . import owner as r
from .formula import bf16, decode, formula


STAGES = ('squares', 'sum', 'mean', 'mean_eps', 'root', 'inverse',
          'scaled', 'gamma', 'weighted', 'output')


def inputs(seed=71):
    x = np.random.default_rng(seed).uniform(-4, 4, (1, r.WIDTH)).astype('<f4')
    x[0, 0], x[0, 1], x[0, 1024] = np.float32(2**-70), np.float32(-0.0), np.float32(2**-70)
    return bf16(x), bf16(np.linspace(-0.2, 0.2, r.WIDTH, dtype='<f4'))


class TraceScalar(r.SharedScalar):
    def __init__(self):
        super().__init__()
        self.trace = []  # Host-only test observer, never read by owner arithmetic.

    def op(self, client, operation, a, b=0):
        result = super().op(client, operation, a, b)
        self.trace.append((operation, a, b, result))
        return result


class OwnerTests(unittest.TestCase):
    def case(self, *, observer=None, scalar=None, hidden=None, weight=None):
        default_hidden, default_weight = inputs()
        hidden = default_hidden if hidden is None else hidden
        weight = default_weight if weight is None else weight
        memory = r.TypedMemory()
        memory.add_readonly(0x10000, hidden)
        memory.add_readonly(0x60000, weight)
        memory.allocate_output(0x80000, r.ROW_BYTES)
        job = r.RmsJob(71, 0x10000, 0x60000, 0x80000, 1)
        return r.TypedRmsDriver(r.RmsOwner(scalar, observer), memory, job)

    def finish(self, driver, hook=None):
        deadline = time.monotonic() + 15
        events = []
        for tick in range(3000):
            self.assertLess(time.monotonic(), deadline, 'M1 wall budget')
            event = driver.tick(**({} if hook is None else hook(driver, tick)))
            events.append(event)
            if driver.response is not None:
                return events
        self.fail('M1 handshake budget')

    def test_m1_original_inputs_actual_packed_output_counts_and_read_schedule(self):
        driver = self.case()
        hidden, weight = driver.input.raw(), driver.weight.raw()
        events = self.finish(driver, lambda _, i: dict(memory_ready=i % 3 != 0,
                             memory_response_ready=i % 4 != 0, response_ready=i % 5 != 0))
        expected = formula(hidden, weight, 1)
        self.assertEqual(driver.output.raw(), expected['output'])
        self.assertEqual((driver.input.raw(), driver.weight.raw()), (hidden, weight))
        self.assertIsNone(driver.response.status)
        self.assertTrue(driver.output.published)
        self.assertEqual(driver.response.write_bytes, 4096)
        self.assertEqual(driver.counts['read_bytes'], 12288)
        self.assertEqual(driver.counts['write_bytes'], 4096)
        self.assertEqual(driver.owner.scalar_counts, Counter(mul_ieee_rne=6145, add=4265, div=1, sqrt=1))
        self.assertEqual(driver.owner.counts, Counter(read_requests=192, write_requests=64,
                         memory_responses=256, write_acks=64, owner_results=1))
        packets = [event['memory'] for event in events if event['memory_fire']]
        expected_addresses = [(driver.job.input + i, False) for i in range(0, 4096, 64)]
        for chunk in range(2):
            expected_addresses += [(base + chunk * 2048 + i, write)
                                   for base, write in ((driver.job.input, False), (driver.job.weight, False),
                                                       (driver.job.output, True)) for i in range(0, 2048, 64)]
        self.assertEqual([(p.address, p.write) for p in packets], expected_addresses)
        self.assertEqual([p.tag for p in packets], [(71 << 32) | i for i in range(256)])
        self.assertTrue(all(p.data is None or len(p.data) == 64 for p in packets))
        report = driver.owner.report()
        for name in ('row', 'weight', 'output'):
            self.assertEqual(report[f'retained_bf16_{name}_capacity'], 1024)
        self.assertEqual(report['retained_physical_bank_bytes'], 6144)
        self.assertEqual(report['residue_overlay_bf16_entries'], 64)
        self.assertFalse(report['physical_bank_allocation_proven'])
        self.assertFalse(report['control_overhead_proven'])
        self.assertFalse(report['rtl_executed'])
        self.assertFalse(report['native_acceptance'])

    def test_output_bank_really_holds_residues_without_hidden_numeric_array(self):
        driver = self.case()
        accesses = Counter()
        original_partial = driver.owner._partial
        def audited_partial(lane, residue, bits=None):
            accesses['reads' if bits is None else 'writes'] += 1
            return original_partial(lane, residue, bits)
        driver.owner._partial = audited_partial
        bank_ids = tuple(map(id, (driver.owner.row_bank, driver.owner.weight_bank, driver.owner.output_bank)))
        while driver.owner.request.address != driver.job.input + 2048:
            driver.tick()
        self.assertEqual(driver.owner.scratch_phase, 'partials')
        x = decode(driver.input.raw(), (2048,))
        squares = np.multiply(x, x, dtype=np.float32)
        expected = []
        for lane in range(8):
            for residue in range(4):
                subtotal = np.float32(0)
                for block in range(2):
                    part = np.float32(0)
                    for term in range(16):
                        part = np.add(part, squares[block * 512 + term * 32 + residue * 8 + lane], dtype=np.float32)
                    subtotal = np.add(subtotal, part, dtype=np.float32)
                expected.append(r.word(subtotal))
        self.assertEqual(struct.unpack_from('<32I', driver.owner.output_bank), tuple(expected))
        self.assertEqual(driver.owner.output_bank[128:], bytes(1920))
        locals_now = driver.owner.program.gi_frame.f_locals
        self.assertIsNone(locals_now['squares'])
        self.assertFalse(any(isinstance(v, (list, np.ndarray, bytearray)) for v in locals_now.values()))
        self.finish(driver)
        self.assertEqual(accesses, Counter(reads=128, writes=128))  # 512 B each, same output-bank port.
        self.assertEqual(bank_ids, tuple(map(id, (driver.owner.row_bank, driver.owner.weight_bank, driver.owner.output_bank))))
        self.assertEqual(driver.owner.scratch_phase, 'retired')
        with self.assertRaisesRegex(ValueError, 'partial phase'):
            driver.owner._partial(0, 0)

    def test_observer_exact_fp32_nodes_return_values_never_feed_arithmetic(self):
        baseline = self.case(scalar=TraceScalar())
        baseline_events = self.finish(baseline)
        snapshots = {}

        def observer(stage, token, words):
            self.assertEqual(token, 0)
            self.assertIs(type(words), tuple)
            snapshots[stage] = words
            return (0x7fc00000,) * len(words)

        observed = self.case(observer=observer, scalar=TraceScalar())
        events = self.finish(observed)
        self.assertEqual(events, baseline_events)
        self.assertEqual(observed.owner.scalar.trace, baseline.owner.scalar.trace)
        self.assertEqual(observed.report(), baseline.report())
        self.assertEqual(list(snapshots), list(STAGES))
        expected = formula(observed.input.raw(), observed.weight.raw(), 1)
        for stage in STAGES[:-1]:
            self.assertEqual(snapshots[stage], tuple(map(int, expected['trace'][stage].view('<u4').flat)), stage)
        self.assertEqual(snapshots['output'], tuple(int(b) << 16 for b in np.frombuffer(expected['output'], '<u2')))
        self.assertEqual(snapshots['squares'][0], 0x200)
        self.assertEqual(snapshots['scaled'][1], 0x80000000)
        trace = observed.owner.scalar.trace
        split = next(i for i, entry in enumerate(trace) if entry[0] == 'div') + 1
        reduction, post = trace[:split], trace[split:]
        square_calls = [entry for entry in reduction[:-4] if entry[0] == 'mul_ieee_rne']
        order = [chunk * 1024 + block * 512 + term * 32 + residue * 8 + lane
                 for chunk in range(2) for lane in range(8) for residue in range(4)
                 for block in range(2) for term in range(16)]
        hidden = struct.unpack('<2048H', observed.input.raw())
        weights = struct.unpack('<2048H', observed.weight.raw())
        self.assertEqual(len(square_calls), 2048)
        for i, entry in zip(order, square_calls):
            self.assertEqual(entry[1:3], (hidden[i] << 16,) * 2)
        self.assertEqual(len(post), 3 * 2048)
        for i in range(2048):
            self.assertEqual(post[3 * i][1], hidden[i] << 16)
            self.assertEqual(post[3 * i + 1][1:3], (r.word(1), weights[i] << 16))
            self.assertEqual(post[3 * i + 2][1:3], (post[3 * i][3], post[3 * i + 1][3]))

    def test_observer_exception_after_first_chunk_acks_blocks_publication(self):
        for stage, acked in (('squares', 0), ('root', 0), ('scaled', 2048), ('output', 2048)):
            with self.subTest(stage=stage):
                def reject(name, *_):
                    if name == stage:
                        raise RuntimeError('host callback failure')
                driver = self.case(observer=reject)
                self.finish(driver)
                self.assertEqual(driver.response.status, 'Observer')
                self.assertEqual(driver.response.write_bytes, acked)
                self.assertFalse(driver.output.published)
                self.assertIsNone(driver.memory.pending)
                self.assertIsNone(driver.owner.scalar.client)
                self.assertEqual(driver.owner.state, 'locked')
                driver.owner.reset()
                self.assertIs(driver.owner.observer, reject)
                self.assertTrue(driver.owner.ports()['job_ready'])

    def test_immutable_exact_job_shape_dtype_span_and_original_authority(self):
        job = r.RmsJob(1, 0x10000, 0x60000, 0x80000, 1)
        with self.assertRaises(FrozenInstanceError):
            job.width = 1024
        for change in (dict(tag=True), dict(tag=1 << 32), dict(tokens=False), dict(tokens=0), dict(tokens=129),
                       dict(width=1024), dict(width=2048.0), dict(dtype='fp32'), dict(input=True),
                       dict(input=-64), dict(input=1), dict(weight=job.input), dict(output=job.weight),
                       dict(output=(1 << 56) - 64), dict(policy='legacy_ascending'),
                       dict(policy='torch210_cpu_default1024')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(job, **change).validate()
        replace(job, tokens=128, weight=0x100000, output=0x200000).validate()
        owner = r.RmsOwner()
        with self.assertRaisesRegex(ValueError, 'typed immutable RMS job'):
            owner.tick(job=r.base.RmsJob(1, 0x10000, 0x60000, 0x80000, 1))
        self.assertTrue(owner.ports()['job_ready'])
        memory = r.TypedMemory()
        memory.allocate_output(0x10000, 4096)
        memory.add_readonly(0x60000, bytes(4096))
        memory.allocate_output(0x80000, 8192)
        with self.assertRaises(ValueError):
            r.TypedRmsDriver(owner, memory, job)
        self.assertTrue(owner.ports()['job_ready'])
        memory = r.TypedMemory()
        memory.add_readonly(0x10000, bytes(4096))
        memory.add_readonly(0x60000, bytes(2048))
        memory.allocate_output(0x80000, 4096)
        with self.assertRaises(ValueError):
            r.TypedRmsDriver(owner, memory, job)

    def test_final_ack_held_completion_and_actual_producer_reuse(self):
        driver = self.case()
        while driver.pending is None or not driver.owner.request.write or driver.counts['write_bytes'] != 4096:
            driver.tick()
        for _ in range(3):
            driver.tick(memory_response_ready=False)
            self.assertFalse(driver.output.published)
        driver.tick(response_ready=False)
        held = driver.owner.ports()['response']
        self.assertIsNone(held.status)
        for _ in range(3):
            driver.tick(response_ready=False)
            self.assertEqual(driver.owner.ports()['response'], held)
            self.assertFalse(driver.output.published)
            with self.assertRaises(ValueError):
                driver.memory.read64(driver.job.output)
        with self.assertRaisesRegex(ValueError, 'held completion'):
            driver.owner.tick(reset=True)
        driver.tick()
        self.assertTrue(driver.output.published)
        driver.memory.allocate_output(0xa0000, 4096)
        job = replace(driver.job, tag=72, input=driver.job.output, output=0xa0000)
        following = r.TypedRmsDriver(driver.owner, driver.memory, job)
        self.finish(following)
        self.assertEqual(following.output.raw(), formula(driver.output.raw(), driver.weight.raw(), 1)['output'])
        self.assertIs(following.owner.scalar, driver.owner.scalar)
        self.assertIs(following.memory, driver.memory)

    def test_abort_unaccepted_request_read_write_and_held_success(self):
        for phase in ('issue', 'read', 'write', 'finish'):
            with self.subTest(phase=phase):
                driver = self.case()
                if phase in ('read', 'write'):
                    while driver.pending is None or driver.owner.request.write != (phase == 'write'):
                        driver.tick()
                elif phase == 'finish':
                    while driver.owner.state != 'finish':
                        driver.tick(response_ready=False)
                    self.assertIsNone(driver.owner.result.status)
                driver.tick(abort=True, memory_response_ready=False, response_ready=False)
                if phase in ('read', 'write'):
                    self.assertEqual(driver.owner.state, 'drain')
                    self.assertIs(driver.owner.scalar.client, driver.owner)
                    with self.assertRaises(ValueError):
                        driver.owner.reset()
                self.finish(driver)
                self.assertEqual(driver.response.status, 'Aborted')
                self.assertFalse(driver.output.published)
                self.assertIsNone(driver.pending)
                self.assertIsNone(driver.memory.pending)
                self.assertIsNone(driver.owner.scalar.client)
                self.assertEqual(driver.owner.counts['owner_results'], 1)
                self.assertEqual(driver.owner.state, 'locked')
                driver.owner.reset()
                self.assertTrue(driver.owner.ports()['job_ready'])
                self.assertEqual(driver.owner.scratch_phase, 'idle')

    def test_read_and_final_ack_errors_never_publish(self):
        for phase in ('first_read', 'reread', 'weight', 'final_ack'):
            with self.subTest(phase=phase):
                driver = self.case()
                def fault(d, _):
                    q = d.owner.request
                    return dict(read_error=q is not None and not q.write and
                                (phase == 'first_read' or phase == 'reread' and d.owner.scratch_phase == 'output' or
                                 phase == 'weight' and q.address == d.job.weight),
                                ack_error=phase == 'final_ack' and d.counts['write_bytes'] == 4096)
                self.finish(driver, fault)
                self.assertEqual(driver.response.status, 'Memory')
                self.assertEqual(driver.response.write_bytes, 4032 if phase == 'final_ack' else 0)
                self.assertFalse(driver.output.published)
                self.assertIsNone(driver.memory.pending)

    def test_bad_tag_length_type_and_write_ack_retires_once(self):
        for write in (False, True):
            for defect in ('tag', 'bytes', 'error_type', 'data') if not write else ('tag', 'bytes'):
                with self.subTest(write=write, defect=defect):
                    owner = r.RmsOwner()
                    owner.tick(job=r.RmsJob(7, 0x10000, 0x60000, 0x80000, 1))
                    while owner.request.write != write:
                        q = owner.request
                        owner.tick(memory_ready=True)
                        owner.tick(memory_response=r.MemoryResponse(q.tag, bytes(64)))
                    q = owner.request
                    owner.tick(memory_ready=True)
                    response = r.MemoryResponse(q.tag + int(defect == 'tag'),
                                                bytearray(64) if defect == 'data' else bytes(64),
                                                0 if defect == 'error_type' else False,
                                                32 if defect == 'bytes' else 64)
                    owner.tick(memory_response=response)
                    self.assertEqual(owner.result.status, 'Protocol')
                    self.assertEqual(owner.ack_bytes, 0)
                    self.assertIsNone(owner.request)
                    self.assertIsNone(owner.scalar.client)
                    owner.tick(response_ready=True)
                    self.assertEqual(owner.state, 'locked')
                    self.assertEqual(owner.counts['owner_results'], 1)

    def test_active_reset_drains_accepted_read_and_holds_failure(self):
        owner = r.RmsOwner()
        owner.tick(job=r.RmsJob(1, 0x10000, 0x60000, 0x80000, 1))
        q = owner.request
        owner.tick(memory_ready=True)
        owner.tick(reset=True)
        self.assertEqual(owner.state, 'drain')
        self.assertEqual(owner.request, q)
        owner.tick(memory_response=r.MemoryResponse(q.tag, bytes(64)))
        self.assertEqual(owner.result.status, 'Aborted')
        with self.assertRaisesRegex(ValueError, 'held completion'):
            owner.tick(reset=True)
        owner.tick(response_ready=True)
        owner.tick(reset=True)
        self.assertTrue(owner.ports()['job_ready'])

    def test_nonfinite_or_overflow_actual_input_and_weight_never_publish(self):
        for source, index, bits in (('hidden', 0, 0x7f80), ('hidden', 1024, 0x7fc1),
                                    ('hidden', 0, 0x7f7f), ('weight', 0, 0x7f80), ('weight', 1024, 0x7fc1)):
            with self.subTest(source=source, index=index, bits=bits):
                hidden, weight = inputs()
                changed = bytearray(hidden if source == 'hidden' else weight)
                struct.pack_into('<H', changed, index * 2, bits)
                driver = self.case(**{source: bytes(changed)})
                self.finish(driver)
                self.assertEqual(driver.response.status, 'Numerical')
                self.assertFalse(driver.output.published)
                self.assertEqual(driver.response.write_bytes, 2048 if source == 'weight' and index == 1024 else 0)

    def test_source_identity_binds_actual_owner_reference_and_committed_scalar(self):
        self.assertIs(r.RmsOwner.tick, r.base.RmsOwner.tick)
        self.assertIs(r.TypedRmsDriver.tick, r.base.TypedRmsDriver.tick)
        identity = r.source_identity(r.ReductionPolicy.Torch210CpuDefault2048)
        for name in ('candidates/qwen35_35b_rms/owner.py', 'candidates/qwen35_35b_rms/reference.py',
                     'candidates/qwen35_35b_rms/formula.py', 'candidates/qwen35_gdn_prefill/rms_owner.py'):
            self.assertEqual(identity['source_sha256'][name], r.sha((r.ROOT / name).read_bytes()))
        self.assertEqual(identity['source_sha256'][r.base.SCALAR_SOURCE], r.base.SCALAR_SHA)
        self.assertEqual(identity['source_sha256']['HEAD:' + r.base.OWNER_SOURCE], r.base.LEGACY_SHA)
        self.assertEqual(identity['model_revision'], '62704185bd97ad488cfc404e7caea797396b74dc')
        self.assertEqual(identity['transformers_revision'], '42ca97014c85d71a88ad60d55f08cb9fb4d26e2c')
        for name in ('official_component_executed', 'historical_m1_pass_inherited', 'native_acceptance', 'rtl_executed'):
            self.assertFalse(identity[name])
        original = Path.read_bytes
        def changed(path):
            return b'changed source' if path == r.ROOT / r.reference.SOURCE else original(path)
        with patch.object(Path, 'read_bytes', changed), self.assertRaisesRegex(ValueError, 'official source/config drift'):
            r.source_identity(r.ReductionPolicy.Torch210CpuDefault2048)


if __name__ == '__main__':
    unittest.main()
