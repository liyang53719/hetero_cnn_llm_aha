"""Real tiny32/64 terminal acceptance and publication tests, no RTL or Matrix.

Use actual TypedMemory writes/ACKs and one actual ConvScalar. Integrity errors
hold the real terminal; these tests never manufacture a fallback completion.
"""
from copy import deepcopy
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch

from . import model as m


def produced(memory, base, width, bits):
    region = memory.allocate_output(base, width * 2)
    for offset in range(0, region.extent, 64):
        memory.begin_write(m.WriteCommand(base + offset, 1, 7))
        memory.write_data([bits] * 32, True, mask=m.FULL_MASK)
        memory.acknowledge(m.WriteAck(7, False, 64))
    memory.publish(base, (7, None, region.extent))
    return region


class TerminalPreflightTests(unittest.TestCase):
    def driver(self, width=32, *, readonly=False, frozen_sources=False,
               op=m.ElementwiseOp.Add, silu_observer=None, sigmoid_observer=None):
        memory, scalar = m.TypedMemory(), m.ConvScalar()
        owner = m.ElementwiseOwner(scalar, hidden_width=width, ffn_width=width,
                                   attention_width=width, test_geometry=True,
                                   enable_attention_sigmoid_mul=True,
                                   silu_observer=silu_observer, sigmoid_observer=sigmoid_observer)
        if readonly:
            memory.add_readonly(0x1000, struct.pack('<' + 'H' * width, *([0x3f80] * width)))
        else:
            produced(memory, 0x1000, width, 0x3f80)
        produced(memory, 0x2000, width, 0x4000)
        if frozen_sources:
            for region in memory.regions.values():
                region.written = frozenset(region.written)
                region.acknowledged = frozenset(region.acknowledged)
        memory.allocate_output(0x3000, width * 2)
        job = m.ElementwiseJob(93, 0x1000, 0x2000, 0x3000, 1, op, width)
        return m.TypedElementwiseDriver(owner, memory, job)

    def until(self, driver, condition, **tick):
        for _ in range(64):
            if condition():
                return
            driver.tick(**tick)
        self.fail('tiny real owner exceeded bounded handshake budget')

    def held(self, width=32, **options):
        driver = self.driver(width, **options)
        self.until(driver, lambda: driver.owner.state == 'finish', response_ready=False)
        self.assertFalse(driver.output.published)
        return driver

    def assert_blocked(self, driver):
        result = driver.owner.result
        before = (driver.owner.ticks, dict(driver.owner.counts), dict(driver.counts),
                  driver.output.published, dict(driver.owner.scalar.calls))
        with self.assertRaises(ValueError):
            driver.preflight_response()
        with self.assertRaises(ValueError):
            driver.tick(response_ready=True)
        self.assertEqual(before, (driver.owner.ticks, dict(driver.owner.counts), dict(driver.counts),
                                 driver.output.published, dict(driver.owner.scalar.calls)))
        self.assertEqual(driver.owner.state, 'finish')
        self.assertIs(driver.owner.result, result)
        self.assertIsNone(driver.response)
        self.assertEqual(driver.owner.counts['owner_results'], 0)

    def test_public_preflight_is_readonly_under_backpressure_then_one_real_accept(self):
        for width in (32, 64):
            for frozen in (False, True):
                with self.subTest(width=width, frozen_sources=frozen):
                    d = self.held(width, frozen_sources=frozen)
                    result = d.owner.result
                    raw = d.output.raw()
                    before = (d.owner.ticks, dict(d.owner.counts), dict(d.counts),
                              dict(d.owner.scalar.calls), d._output_hash.digest())
                    for _ in range(3):
                        self.assertIs(d.preflight_response(), result)
                    self.assertEqual(before, (d.owner.ticks, dict(d.owner.counts), dict(d.counts),
                                              dict(d.owner.scalar.calls), d._output_hash.digest()))
                    for _ in range(3):
                        self.assertFalse(d.tick(response_ready=False)['response_fire'])
                        self.assertIs(d.preflight_response(), result)
                        self.assertFalse(d.output.published)
                    with self.assertRaises(ValueError):
                        d.memory.read64(d.job.output)
                    event = d.tick(response_ready=True)
                    self.assertTrue(event['response_fire'])
                    self.assertIs(d.response, result)
                    self.assertEqual(d.owner.counts['owner_results'], 1)
                    self.assertTrue(d.output.published)
                    self.assertEqual(raw, struct.pack('<' + 'H' * width, *([0x4040] * width)))
                    self.assertEqual(d.output.raw(), raw)
                    self.assertEqual(d.owner.scalar_counts, dict(add=width))
                    with self.assertRaisesRegex(ValueError, 'retired'):
                        d.preflight_response()

    def test_final_ack_must_really_retire_before_preflight(self):
        d = self.driver(64)
        target = d.job.output + 64
        self.until(d, lambda: d.pending is not None and d.pending_request.address == target)
        self.assertEqual(d.output.written, {0, 64})
        self.assertEqual(d.output.acknowledged, {0})
        obligation = d.memory.pending
        for _ in range(3):
            self.assertFalse(d.tick(memory_response_ready=False)['response_fire'])
            with self.assertRaisesRegex(ValueError, 'held real terminal'):
                d.preflight_response()
            self.assertIs(d.memory.pending, obligation)
            self.assertEqual(d.owner.ack_bytes, 64)
            self.assertFalse(d.output.published)
        event = d.tick(response_ready=True)
        self.assertTrue(event['memory_response_fire'])
        self.assertFalse(event['response_fire'])
        self.assertIsNone(d.memory.pending)
        self.assertEqual(d.preflight_response().write_bytes, 128)
        self.assertTrue(d.tick()['response_fire'])

    def test_ready_high_retains_original_numeric_request_and_tick_schedule(self):
        for width in (32, 64):
            d = self.driver(width)
            requests = []
            for _ in range(64):
                event = d.tick()
                if event['memory_fire']:
                    requests.append(event['memory'].address)
                if event['response_fire']:
                    break
            self.assertIsNotNone(d.response)
            beats = width // 32
            self.assertEqual(requests, [base + offset for offset in range(0, width * 2, 64)
                                        for base in (d.job.a, d.job.b, d.job.output)])
            self.assertEqual(d.counts['ticks'], beats * 6 + 1)
            self.assertEqual(d.response.model_ticks, beats * 6)
            self.assertEqual(d.owner.scalar_counts, dict(add=width))
            self.assertEqual(d.output.raw(), struct.pack('<' + 'H' * width, *([0x4040] * width)))

    def test_successful_preflight_is_rechecked_before_later_acceptance(self):
        for target in ('result', 'source', 'ack'):
            with self.subTest(target=target):
                d = self.held()
                self.assertIs(d.preflight_response(), d.owner.result)
                if target == 'result':
                    d.owner.result = replace(d.owner.result, tag=94)
                elif target == 'source':
                    d.a.storage[64] ^= 1
                else:
                    d.output.acknowledged.clear()
                self.assert_blocked(d)

    def test_result_replacement_or_metadata_corruption_rejected_before_ready_accept(self):
        defects = dict(tag=94, status='Memory', write_bytes=0, model_ticks=float('inf'),
                       staging_complete=False, state_committed=True,
                       history_committed=True, generation_advanced=True)
        for replace_object in (False, True):
            for field, value in defects.items():
                with self.subTest(replace_object=replace_object, field=field):
                    d = self.held()
                    if replace_object:
                        d.owner.result = replace(d.owner.result, **{field: value})
                    else:
                        object.__setattr__(d.owner.result, field, value)
                    self.assert_blocked(d)
        d = self.held()
        d.owner.result = replace(d.owner.result)
        self.assert_blocked(d)

    def test_original_job_identity_and_exact_metadata_are_frozen(self):
        for target in ('driver', 'owner', 'tag', 'tokens', 'op', 'output'):
            with self.subTest(target=target):
                d = self.held()
                if target == 'driver':
                    d.job = replace(d.job)
                elif target == 'owner':
                    d.owner.job = replace(d.job)
                else:
                    object.__setattr__(d.job, target, dict(tag=94, tokens=True,
                                                         op=0, output=0x4000)[target])
                self.assert_blocked(d)

    def test_sources_allocations_and_resources_remain_bound_through_held_terminal(self):
        for target in ('source_bytes', 'source_ack', 'source_write', 'source_published',
                       'source_storage', 'source_region', 'output_region', 'output_storage',
                       'output_base', 'output_extent', 'output_readonly', 'regions',
                       'allocation_alias', 'source_tuple', 'source_hashes', 'owner', 'memory', 'scalar'):
            with self.subTest(target=target):
                d = self.held()
                if target == 'source_bytes':
                    d.a.storage[64] ^= 1
                elif target == 'source_ack':
                    d.a.acknowledged.clear()
                elif target == 'source_write':
                    d.a.written.clear()
                elif target == 'source_published':
                    d.a.published = False
                elif target == 'source_storage':
                    d.a.storage = bytearray(d.a.storage)
                elif target == 'source_region':
                    d.memory.regions[d.job.a] = replace(d.a)
                elif target == 'output_region':
                    d.memory.regions[d.job.output] = replace(d.output)
                elif target == 'output_storage':
                    d.output.storage = bytearray(d.output.storage)
                elif target == 'output_base':
                    d.output.base += 64
                elif target == 'output_extent':
                    d.output.extent += 64
                elif target == 'output_readonly':
                    d.output.readonly = True
                elif target == 'regions':
                    d.memory.regions = dict(d.memory.regions)
                elif target == 'allocation_alias':
                    d.memory.regions[0x4000] = replace(d.output)
                elif target == 'source_tuple':
                    d.sources = tuple(list(d.sources))
                elif target == 'source_hashes':
                    d.source_hashes = tuple(list(d.source_hashes))
                elif target == 'owner':
                    d.owner = deepcopy(d.owner)
                elif target == 'memory':
                    d.memory = deepcopy(d.memory)
                else:
                    d.owner.scalar = m.ConvScalar()
                self.assert_blocked(d)

    def test_real_write_ack_and_finite_output_receipts_are_required(self):
        for target in ('write', 'ack', 'ack_counter', 'owner_ack', 'write_counter',
                       'finite_bytes', 'nonfinite_bytes', 'boolean_offset', 'custom_coverage'):
            with self.subTest(target=target):
                d = self.held(64)
                if target == 'write':
                    d.output.written.remove(64)
                elif target == 'ack':
                    d.output.acknowledged.remove(64)
                elif target == 'ack_counter':
                    d.counts['ack_bytes'] -= 64
                elif target == 'owner_ack':
                    d.owner.ack_bytes -= 64
                elif target == 'write_counter':
                    d.counts['write_bytes'] -= 64
                elif target in ('finite_bytes', 'nonfinite_bytes'):
                    d.output.storage[64:66] = struct.pack('<H', 0x4000 if target == 'finite_bytes' else 0x7f80)
                elif target == 'boolean_offset':
                    d.output.acknowledged = {False, 64}
                else:
                    class EqualCoverage(set):
                        def __eq__(self, other):
                            return True
                    d.output.acknowledged = EqualCoverage()
                self.assert_blocked(d)

    def test_live_source_identity_is_compared_with_original_admission_snapshot(self):
        d = self.held()
        identity = deepcopy(m.source_identity())
        identity['opcodes']['add'] = 99
        with patch.object(m, 'source_identity', return_value=identity):
            self.assert_blocked(d)
        # Mutating the owner's identity cannot rewrite the admission snapshot.
        d.owner.identity['opcodes']['add'] = 99
        self.assert_blocked(d)

    def test_readonly_initial_hidden_retains_empty_real_producer_coverage(self):
        d = self.held(readonly=True)
        self.assertIs(d.preflight_response(), d.owner.result)
        self.assertFalse(d.a.written or d.a.acknowledged)
        d.tick()
        self.assertTrue(d.output.published)
        self.assertFalse(d.a.written or d.a.acknowledged)

    def test_abort_reset_ready_revokes_only_unaccepted_success_using_real_failed_receipt(self):
        for reset in (False, True):
            for corrupt_result in (False, True):
                with self.subTest(reset=reset, corrupt_result=corrupt_result):
                    d = self.held()
                    original = d.preflight_response()
                    if corrupt_result:
                        d.owner.result = replace(original, tag=original.tag + 1)
                    event = d.tick(abort=not reset, reset=reset, response_ready=True)
                    self.assertFalse(event['response_fire'])
                    self.assertIsNone(event['response'])
                    self.assertEqual(d.owner.counts['owner_results'], 0)
                    self.assertFalse(d.output.published)
                    failed = d.preflight_response()
                    self.assertIsNot(failed, original)
                    self.assertEqual(failed.status, 'Aborted')
                    self.assertFalse(failed.staging_complete)
                    self.assertTrue(d.tick()['response_fire'])
                    self.assertIs(d.response, failed)
                    self.assertFalse(d.output.published)

    def test_preflight_failure_does_not_fabricate_or_repair_a_terminal(self):
        d = self.held(64)
        original = d.owner.result
        d.output.acknowledged.remove(64)
        self.assert_blocked(d)
        self.assertIs(d.owner.result, original)
        self.assertIsNone(original.status)
        # A real abort can retire unpublished failure; lost ACK metadata is
        # never restored or credited by preflight and cannot publish success.
        self.assertFalse(d.tick(abort=True)['response_fire'])
        self.assertEqual(d.preflight_response().status, 'Aborted')
        d.tick()
        self.assertFalse(d.output.published)
        self.assertEqual(d.output.acknowledged, {0})
        d.owner.reset()
        self.assertTrue(d.owner.ports()['job_ready'])

    def test_inflight_abort_still_requires_real_drain_before_preflight(self):
        d = self.driver()
        self.until(d, lambda: d.pending is not None and d.pending_request.write)
        physical = d.memory.pending
        d.tick(abort=True, memory_response_ready=False)
        with self.assertRaisesRegex(ValueError, 'held real terminal'):
            d.preflight_response()
        with self.assertRaisesRegex(ValueError, 'drained transport'):
            d.owner.reset()
        self.assertIs(d.memory.pending, physical)
        self.assertEqual(d.owner.state, 'drain')
        d.tick(response_ready=False)
        self.assertIsNone(d.memory.pending)
        self.assertEqual(d.preflight_response().status, 'Aborted')
        d.tick()
        self.assertFalse(d.output.published)

    def test_accepted_success_cannot_be_retroactively_rolled_back(self):
        for reset in (False, True):
            d = self.held()
            accepted = d.preflight_response()
            d.tick()
            raw = d.output.raw()
            d.owner.tick(abort=not reset, reset=reset, response_ready=True)
            self.assertIs(d.response, accepted)
            self.assertIsNone(accepted.status)
            self.assertTrue(d.output.published)
            self.assertEqual(d.memory.read64(d.job.output), raw)
            with self.assertRaisesRegex(ValueError, 'retired'):
                d.preflight_response()

    def test_silu_observer_sees_real_boundary_without_changing_arithmetic_or_schedule(self):
        observations, sigmoid = [], []
        observed = None

        def observe(index, fp32, bf16):
            observations.append((index, fp32, bf16, observed.owner.scalar.calls['mul_ieee_rne']))
            return 0x7fc0  # Deliberately invalid value must never enter arithmetic.

        observed = self.driver(64, op=m.ElementwiseOp.SiluMul, silu_observer=observe,
                               sigmoid_observer=lambda *values: sigmoid.append(values))
        plain = self.driver(64, op=m.ElementwiseOp.SiluMul)
        for driver in (observed, plain):
            self.until(driver, lambda: driver.response is not None)
        self.assertEqual(observed.output.raw(), plain.output.raw())
        self.assertEqual(observed.response, plain.response)
        self.assertEqual(observed.owner.scalar_counts, plain.owner.scalar_counts)
        self.assertEqual(observed.owner.exp_counts, plain.owner.exp_counts)
        self.assertEqual(observed.counts, plain.counts)
        self.assertEqual([item[0] for item in observations], list(range(64)))
        self.assertEqual([item[3] for item in observations], [index * 3 + 2 for index in range(64)])
        self.assertTrue(all(m.ElementwiseOwner._bf16(fp32) == bf16 << 16
                            for _, fp32, bf16, _ in observations))
        self.assertFalse(sigmoid)
        observed.owner.reset()
        self.assertIs(observed.owner.silu_observer, observe)
        self.assertIs(observed.owner._silu_observer_binding, observe)

    def test_silu_observer_has_exact_operation_scope_and_immutable_binding(self):
        for op in (m.ElementwiseOp.Add, m.ElementwiseOp.SigmoidMul):
            observations = []
            d = self.driver(op=op, silu_observer=lambda *values: observations.append(values))
            self.until(d, lambda: d.response is not None)
            self.assertFalse(observations)
        with self.assertRaisesRegex(ValueError, 'callable silu observer'):
            m.ElementwiseOwner(m.ConvScalar(), silu_observer=1)
        d = self.held(op=m.ElementwiseOp.SiluMul)
        d.owner.silu_observer = lambda *values: None
        self.assert_blocked(d)


if __name__ == '__main__':
    unittest.main()
