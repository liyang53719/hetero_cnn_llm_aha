"""Host-only coverage seals on real tiny GQA memory transactions.

Uses the same explicitly supplied existing Matrix library as test_gqa. No
compile, full-model fixture, M128 execution, or substitute arithmetic path.
"""
import unittest
from unittest.mock import patch

from . import driver as transport
from . import test_gqa as fixture


class CustomSet(set):
    """Equality-compatible metadata is still not an exact physical set."""


class CustomFrozenSet(frozenset):
    pass


class CoverageSealTests(unittest.TestCase):
    setUp = fixture.GqaModelTests.setUp
    case = fixture.GqaModelTests.case
    until = fixture.GqaModelTests.until
    finish = fixture.GqaModelTests.finish
    cancel = fixture.GqaModelTests.cancel

    @classmethod
    def setUpClass(cls):
        fixture.GqaModelTests.setUpClass.__func__(cls)

    def unadmitted(self):
        job = fixture.o.Bf16CausalGqaJob(71, 0x100000000, 0x200000000,
                                       0x300000000, 1, 0, 1)
        inputs = tuple(fixture.producer(self.memory, base, bytes(extent), index + 1)
                       for index, (base, extent) in enumerate(job.input_spans))
        output = self.memory.allocate_output(job.output, job.write_bytes)
        owner = fixture.o.Bf16CausalGqaOwner(self.matrix, self.scalar)
        return job, inputs, output, owner

    def assert_sealed(self, driver):
        for region in (*driver.inputs, driver.output):
            self.assertIs(type(region.written), frozenset)
            self.assertIs(type(region.acknowledged), frozenset)
        self.assertEqual(driver.output.written, driver._written_offsets)
        self.assertEqual(driver.output.acknowledged, driver._acknowledged_offsets)

    def assert_output_released(self, driver):
        self.assertIsNotNone(driver.response)
        self.assertIs(type(driver.output.written), set)
        self.assertIs(type(driver.output.acknowledged), set)
        self.assertEqual(driver.output.written, driver._written_offsets)
        self.assertEqual(driver.output.acknowledged, driver._acknowledged_offsets)

    def test_admission_rejects_custom_sets_and_bool_integer_aliases(self):
        for field in ('written', 'acknowledged'):
            for kind in (CustomSet, CustomFrozenSet, 'bool'):
                with self.subTest(field=field, kind=kind):
                    self.setUp()
                    job, inputs, _, owner = self.unadmitted()
                    replacement = set(getattr(inputs[0], field))
                    if kind == 'bool':
                        replacement.remove(0)
                        replacement.add(False)
                    else:
                        replacement = kind(replacement)
                    setattr(inputs[0], field, replacement)
                    with self.assertRaisesRegex(ValueError, 'producer data/ACK'):
                        transport.TypedBf16CausalGqaDriver(owner, self.memory, job)
                    self.assertTrue(owner.ports()['job_ready'])
                    self.assertIsNone(self.matrix.owner)
        for kind in (CustomSet, CustomFrozenSet):
            with self.subTest(output_kind=kind):
                self.setUp()
                job, _, output, owner = self.unadmitted()
                output.written = kind()
                with self.assertRaisesRegex(ValueError, 'fresh output'):
                    transport.TypedBf16CausalGqaDriver(owner, self.memory, job)
                self.assertTrue(owner.ports()['job_ready'])

    def test_actual_metadata_is_immutable_and_stale_mutable_aliases_detach(self):
        job, inputs, output, owner = self.unadmitted()
        aliases = tuple((region.written, region.acknowledged) for region in (*inputs, output))
        driver = transport.TypedBf16CausalGqaDriver(owner, self.memory, job)
        self.assert_sealed(driver)
        for region, old in zip((*inputs, output), aliases):
            for field, previous in zip(('written', 'acknowledged'), old):
                sealed = getattr(region, field)
                with self.assertRaises(AttributeError):
                    sealed.add(1)
                with self.assertRaises(TypeError):
                    set.clear(sealed)
                previous.clear()
                previous.add(False)
                self.assertIs(getattr(region, field), sealed)
        driver.tick(memory_ready=False)
        self.assert_sealed(driver)
        self.cancel(driver)

    def test_equal_source_replacement_poisons_and_drains_accepted_read(self):
        for field in ('written', 'acknowledged'):
            for kind in (set, frozenset, CustomSet, 'bool'):
                with self.subTest(field=field, kind=kind):
                    self.setUp()
                    driver, *_ = self.case(tokens=1)
                    self.until(driver, lambda d: d.pending is not None)
                    sealed = getattr(driver.query, field)
                    replacement = set(sealed)
                    if kind == 'bool':
                        replacement.remove(0)
                        replacement.add(False)
                    else:
                        replacement = kind(replacement)
                    self.assertIsNot(replacement, sealed)
                    self.assertEqual(replacement, sealed)
                    setattr(driver.query, field, replacement)
                    with self.assertRaisesRegex(ValueError, 'producer coverage changed'):
                        driver.tick(memory_response_ready=False)
                    self.assertTrue(driver.owner.poison)
                    driver.tick(abort=True, memory_response_ready=False)
                    self.assertIsNotNone(driver.pending)
                    self.finish(driver)
                    self.assertEqual(driver.response.status, 'Aborted')
                    self.assertFalse(driver.output.published)
                    self.assertIsNone(self.memory.pending)
                    self.assertEqual(driver.counts['memory_requests'],
                                     driver.counts['memory_responses'])

    def test_output_replacement_cannot_cross_tick_or_final_ack_fences(self):
        driver, *_ = self.case(tokens=1)
        empty_written = driver.output.written
        self.until(driver, lambda d: d.counts['ack_bytes'] > 0)
        for field in ('written', 'acknowledged'):
            sealed = getattr(driver.output, field)
            for kind in (set, frozenset, CustomSet, 'bool'):
                with self.subTest(field=field, kind=kind):
                    replacement = set(sealed)
                    if kind == 'bool':
                        replacement.remove(0)
                        replacement.add(False)
                    else:
                        replacement = kind(replacement)
                    self.assertIsNot(replacement, sealed)
                    self.assertEqual(replacement, sealed)
                    setattr(driver.output, field, replacement)
                    with self.assertRaisesRegex(ValueError, 'altered write/ACK coverage'):
                        driver.tick()
                    self.assertFalse(driver.output.published)
                    setattr(driver.output, field, sealed)
        current = driver.output.written
        driver.output.written = empty_written
        with self.assertRaisesRegex(ValueError, 'altered write/ACK coverage'):
            driver.tick()
        driver.output.written = current
        self.until(driver, lambda d: d.pending is not None and d.owner.request.write and
                   d.counts['write_bytes'] == d.job.write_bytes)
        self.assert_sealed(driver)
        sealed_ack = driver.output.acknowledged
        driver.output.acknowledged = driver.output.written
        with self.assertRaisesRegex(ValueError, 'altered write/ACK coverage'):
            driver.tick()
        self.assertIsNotNone(self.memory.pending)
        self.assertFalse(driver.output.published)
        driver.output.acknowledged = sealed_ack
        self.finish(driver)
        self.assertIsNone(driver.response.status)
        self.assertTrue(driver.output.published)
        self.assert_output_released(driver)

    def test_tick_identity_checks_do_not_rescan_immutable_coverage(self):
        driver, *_ = self.case(tokens=1)
        seals = tuple((region.written, region.acknowledged) for region in (*driver.inputs, driver.output))
        with patch.object(transport, '_same_coverage', side_effect=AssertionError('coverage rescan')):
            for _ in range(32):
                driver.tick(memory_ready=False)
        for region, (written, acknowledged) in zip((*driver.inputs, driver.output), seals):
            self.assertIs(region.written, written)
            self.assertIs(region.acknowledged, acknowledged)
        # Source byte equality still runs on every tick, even with no metadata scan.
        driver.query.storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'source bytes'):
            driver.tick(memory_ready=False)
        self.cancel(driver)

    def test_actual_write_ack_seals_and_error_ack_drain(self):
        driver, *_ = self.case(tokens=1)
        for _ in range(20000):
            self.assert_sealed(driver)
            if (driver.pending is not None and driver.owner.request.write and
                    driver.counts['write_bytes'] == driver.job.write_bytes):
                break
            driver.tick()
        else:
            self.fail('small GQA transaction exceeded software tick bound')
        written = driver.output.written
        acknowledged = driver.output.acknowledged
        self.assertEqual(len(written), driver.job.write_bytes // 64)
        self.assertEqual(len(acknowledged), len(written) - 1)
        for _ in range(3):
            driver.tick(memory_response_ready=False)
            self.assertIs(driver.output.written, written)
            self.assertIs(driver.output.acknowledged, acknowledged)
            self.assertFalse(driver.output.published)
        driver.tick(ack_error=True)
        self.assert_sealed(driver)
        self.assertEqual(driver.output.acknowledged, acknowledged)
        self.assertEqual(driver.counts['ack_bytes'], driver.job.write_bytes - 64)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Memory')
        self.assertFalse(driver.output.published)
        self.assertIsNone(self.memory.pending)
        self.assertTrue(driver.owner.poison)
        self.assert_output_released(driver)
        with self.assertRaisesRegex(ValueError, 'fresh unpublished staging'):
            self.memory.exact(driver.output.base, driver.output.extent, readable=False)

    def test_source_seal_replacement_drains_final_accepted_write_on_abort(self):
        driver, *_ = self.case(tokens=1)
        self.until(driver, lambda d: d.pending is not None and d.owner.request.write and
                   d.counts['write_bytes'] == d.job.write_bytes)
        driver.key.acknowledged = set(driver.key.acknowledged)
        with self.assertRaisesRegex(ValueError, 'producer coverage changed'):
            driver.tick(memory_response_ready=False)
        driver.tick(abort=True, memory_response_ready=False)
        self.assertIsNotNone(self.memory.pending)
        self.assertFalse(driver.output.published)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Aborted')
        self.assertEqual(driver.response.write_bytes, driver.job.write_bytes)
        self.assertIsNone(self.memory.pending)
        self.assertFalse(driver.output.published)
        self.assertTrue(driver.owner.poison)
        self.assert_output_released(driver)

    def test_early_abort_releases_unwritten_output_for_other_memory_producer(self):
        driver, *_ = self.case(tokens=1)
        driver.tick(abort=True, memory_ready=False, response_ready=False)
        self.until(driver, lambda d: d.owner.state == 'finish',
                   lambda *_: dict(response_ready=False))
        for _ in range(3):
            driver.tick(response_ready=False)
            self.assert_sealed(driver)
            self.assertIsNone(driver.response)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Aborted')
        self.assert_output_released(driver)
        self.assertFalse(driver.output.written)
        self.assertFalse(driver.output.acknowledged)
        self.assertFalse(driver.output.published)
        region = self.memory.exact(driver.output.base, driver.output.extent, readable=False)
        self.assertIs(region, driver.output)
        # A different producer uses the unchanged real memory protocol on
        # the same allocation, with no reset or reallocation of that memory.
        for offset in range(0, region.extent, 64):
            tag = (999 << 32) | (offset // 64)
            self.memory.begin_write(fixture.WriteCommand(region.base + offset, 1, tag))
            self.memory.write_data((0x3f80,) * 32, True)
            self.memory.acknowledge(fixture.WriteAck(tag, False, 64))
        self.memory.publish(region.base, (999, None, region.extent))
        self.assertTrue(region.published)
        self.assertEqual(region.raw(), fixture.pack([0x3f80] * (region.extent // 2)))
        self.assertTrue(driver.owner.poison)
        with self.assertRaisesRegex(ValueError, 'already retired'):
            driver.tick()

    def test_partial_aborted_output_remains_ineligible_for_fresh_reuse(self):
        driver, *_ = self.case(tokens=1)
        self.until(driver, lambda d: d.pending is not None and d.owner.request.write)
        written, acknowledged = driver.output.written, driver.output.acknowledged
        raw = driver.output.raw()
        self.assertEqual(len(written), 1)
        self.assertFalse(acknowledged)
        driver.tick(abort=True, memory_response_ready=False)
        self.assert_sealed(driver)
        self.assertIs(driver.output.written, written)
        self.assertIs(driver.output.acknowledged, acknowledged)
        self.assertIsNotNone(self.memory.pending)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Aborted')
        self.assert_output_released(driver)
        self.assertEqual(driver.output.written, written)
        self.assertEqual(driver.output.acknowledged, written)
        self.assertEqual(driver.output.raw(), raw)
        self.assertFalse(driver.output.published)
        with self.assertRaisesRegex(ValueError, 'fresh unpublished staging'):
            self.memory.exact(driver.output.base, driver.output.extent, readable=False)

    def test_immutable_coverage_does_not_replace_terminal_output_hash(self):
        driver, *_ = self.case(tokens=1)
        self.until(driver, lambda d: d.owner.state == 'finish',
                   lambda *_: dict(response_ready=False))
        self.assert_sealed(driver)
        driver.output.storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'terminal output differs'):
            driver.tick()
        self.assertFalse(driver.output.published)
        self.assertTrue(driver.owner.poison)
        self.cancel(driver)


if __name__ == '__main__':
    unittest.main()
