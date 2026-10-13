"""Small actual-owner observer gates; no official tensor, M16/M128 or RTL run."""
from itertools import groupby
import struct
import unittest

import numpy as np

from . import rms_owner as r
from .test_rms_owner import bf16, oracle, raw_values


STAGES = ('squares', 'sum', 'mean', 'mean_eps', 'inverse', 'scaled', 'gamma', 'weighted', 'output')


class TracedScalar(r.SharedScalar):
    def __init__(self):
        super().__init__()
        self.trace = []

    def op(self, client, operation, a, b=0):
        result = super().op(client, operation, a, b)
        self.trace.append((client.ticks, operation, a, b, result))
        return result


class RmsObserverTests(unittest.TestCase):
    def case(self, policy, observer=None, tokens=2):
        memory, scalar = r.TypedMemory(), TracedScalar()
        memory.add_readonly(0x10000, raw_values(tokens))
        memory.add_readonly(0x60000, bf16(np.linspace(-0.2, 0.2, r.WIDTH, dtype='<f4')).tobytes())
        memory.allocate_output(0x80000, tokens * r.ROW_BYTES)
        owner = r.RmsOwner(scalar, observer)
        job = r.RmsJob(71, 0x10000, 0x60000, 0x80000, tokens, policy)
        return r.TypedRmsDriver(owner, memory, job)

    def finish(self, driver):
        trace = []
        for tick in range(2000):
            trace.append(driver.tick(memory_ready=tick % 3 != 0,
                                     memory_response_ready=tick % 4 != 0,
                                     response_ready=tick % 5 != 0))
            if driver.response is not None:
                return trace
        self.fail('small RMS observer handshake budget')

    def test_observer_preserves_all_transactions_scalar_nodes_and_output(self):
        for policy in r.ReductionPolicy:
            with self.subTest(policy=policy):
                baseline = self.case(policy)
                expected_transactions = self.finish(baseline)
                events = []

                def observe(stage, token, words):
                    self.assertIs(type(words), tuple)
                    self.assertTrue(all(type(bits) is int and 0 <= bits < 1 << 32 for bits in words))
                    with self.assertRaises(TypeError):
                        words[0] = 0
                    events.append((stage, token, words))
                    return (0x7fc00000,) * len(words)  # Never an arithmetic input or result.

                observed = self.case(policy, observe)
                actual_transactions = self.finish(observed)
                self.assertEqual(actual_transactions, expected_transactions)
                self.assertEqual(observed.owner.scalar.trace, baseline.owner.scalar.trace)
                self.assertEqual(observed.owner.scalar.calls, baseline.owner.scalar.calls)
                self.assertEqual(observed.response, baseline.response)
                self.assertEqual(observed.report(), baseline.report())
                self.assertEqual(observed.output.raw(), baseline.output.raw())
                self.assertEqual(observed.output.raw(),
                                 oracle(observed.input.raw(), observed.weight.raw(), 2, policy)[0])
                self.assertIsNone(observed.owner.scalar.client)
                self.assertIsNone(observed.memory.pending)
                self.assertIsNone(observed.pending)
                self.assertTrue(observed.output.published)
                self.assertEqual([(stage, token) for stage, token, _ in events],
                                 [(stage, token) for token in range(2) for stage in STAGES])

                nodes = {(stage, token): words for stage, token, words in events}
                groups = [list(group) for _, group in groupby(observed.owner.scalar.trace, key=lambda item: item[0])]
                self.assertEqual(len(groups), 2)
                source = struct.unpack('<2048H', observed.input.raw())
                output = struct.unpack('<2048H', observed.output.raw())
                lanes = (list(range(r.WIDTH)) if policy == r.ReductionPolicy.LegacyAscending else
                         [512 * block + 32 * term + 8 * residue + lane
                          for lane in range(8) for residue in range(4)
                          for block in range(2) for term in range(16)])
                self.assertEqual(sorted(lanes), list(range(r.WIDTH)))
                for token, calls in enumerate(groups):
                    split = next(index for index, call in enumerate(calls) if call[1] == 'div') + 1
                    reduction, post = calls[:split], calls[split:]
                    squares = [call for call in reduction[:-4] if call[1] == 'mul_ieee_rne']
                    self.assertEqual(len(squares), r.WIDTH)
                    for lane, call in zip(lanes, squares):
                        self.assertEqual(call[2:4], (source[token * r.WIDTH + lane] << 16,) * 2)
                        self.assertEqual(nodes['squares', token][lane], call[4])
                    mean, mean_eps, root, inverse = reduction[-4:]
                    self.assertEqual([call[1] for call in (mean, mean_eps, root, inverse)],
                                     ['mul_ieee_rne', 'add', 'sqrt', 'div'])
                    self.assertEqual(nodes['sum', token], (mean[2],))
                    for stage, call in (('mean', mean), ('mean_eps', mean_eps), ('inverse', inverse)):
                        self.assertEqual(nodes[stage, token], (call[4],))
                    self.assertEqual(len(post), 3 * r.WIDTH)
                    for offset, stage in enumerate(('scaled', 'gamma', 'weighted')):
                        self.assertEqual(nodes[stage, token], tuple(call[4] for call in post[offset::3]))
                    self.assertEqual(nodes['output', token],
                                     tuple(bits << 16 for bits in output[token * r.WIDTH:(token + 1) * r.WIDTH]))
                self.assertEqual(nodes['squares', 0][0], 0x200)  # Actual gradual FP32 underflow.
                self.assertEqual(nodes['scaled', 0][1], 0x80000000)  # Actual signed zero.

    def test_callback_failure_retires_error_without_publication_or_lost_ack(self):
        for failed_token in (0, 1):
            for failed_stage in STAGES:
                with self.subTest(token=failed_token, stage=failed_stage):
                    events = []

                    def reject(stage, token, words):
                        events.append((stage, token))
                        if (stage, token) == (failed_stage, failed_token):
                            raise RuntimeError('synthetic observer failure')

                    driver = self.case(r.ReductionPolicy.Torch210CpuDefault1024, reject)
                    self.finish(driver)
                    self.assertEqual(events[-1], (failed_stage, failed_token))
                    self.assertEqual(driver.response.status, 'Observer')
                    self.assertEqual(driver.response.write_bytes, failed_token * r.ROW_BYTES)
                    self.assertEqual(driver.counts['write_bytes'], failed_token * r.ROW_BYTES)
                    self.assertEqual(driver.owner.counts['write_acks'], failed_token * 32)
                    self.assertEqual(driver.owner.counts['owner_results'], 1)
                    self.assertFalse(driver.output.published)
                    self.assertIsNone(driver.owner.scalar.client)
                    self.assertIsNone(driver.owner.request)
                    self.assertIsNone(driver.memory.pending)
                    self.assertIsNone(driver.pending)
                    self.assertEqual(driver.owner.state, 'locked')
                    self.assertFalse(driver.owner.ports()['job_ready'])
                    driver.owner.reset()
                    self.assertIs(driver.owner.observer, reject)
                    self.assertTrue(driver.owner.ports()['job_ready'])

    def test_default_validation_reset_and_held_failure_completion(self):
        self.assertIsNone(r.RmsOwner().observer)
        with self.assertRaisesRegex(ValueError, 'observer callback'):
            r.RmsOwner(observer=17)

        def reject(*event):
            raise RuntimeError('synthetic observer failure')

        driver = self.case(r.ReductionPolicy.LegacyAscending, reject, tokens=1)
        for _ in range(200):
            driver.tick(response_ready=False)
            if driver.owner.state == 'finish':
                break
        held = driver.owner.ports()['response']
        self.assertEqual(held.status, 'Observer')
        for _ in range(3):
            driver.tick(response_ready=False)
            self.assertEqual(driver.owner.ports()['response'], held)
            self.assertFalse(driver.output.published)
        with self.assertRaisesRegex(ValueError, 'held completion'):
            driver.owner.reset()
        driver.tick()
        self.assertEqual(driver.owner.state, 'locked')
        driver.owner.reset()
        self.assertIs(driver.owner.observer, reject)
        self.assertTrue(driver.owner.ports()['job_ready'])


if __name__ == '__main__':
    unittest.main()
