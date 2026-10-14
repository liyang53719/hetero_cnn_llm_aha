"""Local H2048 postnorm gates using actual producer bytes and original RMS.

These are software transport/integrity tests, not native forward or RTL proof.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import inspect
import struct
import unittest
from unittest.mock import patch

from ..qwen35_35b_rms import owner as rms
from ..qwen35_35b_rms.formula import formula
from ..qwen35_35b_rms.test_owner import inputs
from ..qwen35_gdn_prefill.typed_dense import FULL_MASK
from ..qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from .strict_rms import StrictPostNormDriver


def produced(memory, address, raw):
    region = memory.allocate_output(address, len(raw))
    for offset in range(0, len(raw), rms.BEAT_BYTES):
        memory.begin_write(WriteCommand(address + offset, 1, 7))
        memory.write_data(struct.unpack('<32H', raw[offset:offset + 64]), True, mask=FULL_MASK)
        memory.acknowledge(WriteAck(7, False, 64))
    memory.publish(address, (7, None, len(raw)))
    return region


class StrictPostNormTests(unittest.TestCase):
    def resources(self, tokens=1, *, readonly_input=False, produced_weight=False, observer=None):
        hidden, weight = inputs()
        memory, owner = rms.TypedMemory(), rms.RmsOwner(observer=observer)
        if readonly_input:
            memory.add_readonly(0x10000, hidden * tokens)
        else:
            produced(memory, 0x10000, hidden * tokens)
        if produced_weight:
            produced(memory, 0x60000, weight)
        else:
            memory.add_readonly(0x60000, weight)
        memory.allocate_output(0x80000, rms.ROW_BYTES * tokens)
        return owner, memory, rms.RmsJob(71, 0x10000, 0x60000, 0x80000, tokens)

    def driver(self, tokens=1, **options):
        return StrictPostNormDriver(*self.resources(tokens, **options))

    def until(self, driver, condition, **kwargs):
        events = []
        for _ in range(2200 * driver.job.tokens):
            if condition():
                return events
            events.append(driver.tick(**kwargs))
        self.fail('original RMS exceeded bounded local handshake budget')

    def held(self, **options):
        driver = self.driver(**options)
        self.until(driver, lambda: driver.owner.state == 'finish', response_ready=False)
        self.assertFalse(driver.output.published)
        return driver

    def assert_blocked(self, driver, *, tick_options=None):
        before = (driver.owner.ticks, dict(driver.owner.counts), dict(driver.counts),
                  driver.owner.state, driver.owner.result, driver.pending, driver.memory.pending)
        with self.assertRaises(ValueError):
            driver.preflight_response()
        with self.assertRaises(ValueError):
            driver.tick(**({} if tick_options is None else tick_options))
        after = (driver.owner.ticks, dict(driver.owner.counts), dict(driver.counts),
                 driver.owner.state, driver.owner.result, driver.pending, driver.memory.pending)
        self.assertEqual(before, after)
        self.assertIsNone(driver.response)
        self.assertFalse(driver._output.published)
        self.assertEqual(driver.owner.counts['owner_results'], 0)

    def test_h2048_original_arithmetic_wire_schedule_and_streamed_data_hash(self):
        for tokens in (1, 2):
            with self.subTest(tokens=tokens):
                driver = self.driver(tokens)
                original = rms.TypedRmsDriver(*self.resources(tokens))
                banks = (driver.owner.row_bank, driver.owner.weight_bank, driver.owner.output_bank)
                expected_hash = hashlib.sha256()
                for tick in range(2200 * tokens):
                    options = dict(memory_ready=tick % 3 != 0, memory_response_ready=tick % 4 != 0,
                                   response_ready=tick % 5 != 0)
                    event, baseline = driver.tick(**options), original.tick(**options)
                    self.assertEqual(event, baseline)
                    if event['memory_fire'] and event['memory'].write:
                        expected_hash.update(event['memory'].data)
                    self.assertEqual(driver._output_hash.digest(), expected_hash.digest())
                    if driver.response is not None:
                        break
                self.assertIsNotNone(driver.response)
                self.assertEqual(driver.output.raw(), formula(driver.input.raw(), driver.weight.raw(), tokens)['output'])
                self.assertEqual(driver.output.raw(), original.output.raw())
                self.assertEqual(driver.response, original.response)
                self.assertEqual(driver.owner.scalar_counts, original.owner.scalar_counts)
                self.assertEqual(driver.owner.scalar_counts,
                                 Counter(mul_ieee_rne=6145 * tokens, add=4265 * tokens, div=tokens, sqrt=tokens))
                self.assertEqual(driver.owner.counts, original.owner.counts)
                self.assertEqual(driver.counts['ack_bytes'], driver.job.write_bytes)
                self.assertEqual(driver.counts['read_bytes'], 3 * driver.job.write_bytes)
                self.assertEqual(driver.owner.report()['retained_physical_bank_bytes'], 6144)
                self.assertTrue(all(a is b for a, b in zip(banks,
                    (driver.owner.row_bank, driver.owner.weight_bank, driver.owner.output_bank))))
                self.assertTrue(driver.output.published)
                self.assertFalse(driver.owner.report()['rtl_executed'])

    def test_same_owner_memory_scalar_and_banks_reuse_real_previous_output(self):
        first = self.driver()
        self.until(first, lambda: first.response is not None)
        first.memory.allocate_output(0xa0000, rms.ROW_BYTES)
        second = StrictPostNormDriver(first.owner, first.memory,
                                      replace(first.job, tag=72, input=first.job.output, output=0xa0000))
        self.until(second, lambda: second.response is not None)
        self.assertIs(second.input, first.output)
        self.assertIs(second.owner, first.owner)
        self.assertIs(second.memory, first.memory)
        self.assertIs(second._scalar, first._scalar)
        self.assertTrue(all(a is b for a, b in zip(first._banks, second._banks)))
        self.assertEqual(second.output.raw(), formula(first.output.raw(), first.weight.raw(), 1)['output'])
        self.assertEqual(second.owner.counts['owner_results'], 1)
        self.assertTrue(second.output.published)

    def test_admission_requires_real_producer_immutable_weight_and_sentinel(self):
        cases = ('readonly_input', 'produced_weight', 'source_write', 'source_ack', 'source_published',
                 'source_boolean_offset', 'source_fake_coverage', 'weight_coverage', 'output_sentinel',
                 'bank_alias', 'bank_size', 'storage_size', 'output_geometry')
        for defect in cases:
            with self.subTest(defect=defect):
                owner, memory, job = self.resources(readonly_input=defect == 'readonly_input',
                                                     produced_weight=defect == 'produced_weight')
                source, weight, output = (memory.regions[address] for address in
                                          (job.input, job.weight, job.output))
                if defect == 'source_write':
                    source.written.remove(0)
                elif defect == 'source_ack':
                    source.acknowledged.remove(0)
                elif defect == 'source_published':
                    source.published = False
                elif defect == 'source_boolean_offset':
                    source.written.remove(0)
                    source.written.add(False)
                elif defect == 'source_fake_coverage':
                    class AlwaysEqual(set):
                        def __eq__(self, other):
                            return True
                    source.written = AlwaysEqual()
                elif defect == 'weight_coverage':
                    weight.written.add(0)
                elif defect == 'output_sentinel':
                    output.storage[64] ^= 1
                elif defect == 'bank_alias':
                    owner.weight_bank = owner.row_bank
                elif defect == 'bank_size':
                    owner.output_bank.extend(b'xx')
                elif defect == 'storage_size':
                    output.storage[64:64] = bytes(64)
                elif defect == 'output_geometry':
                    output.base += 64
                with self.assertRaises(ValueError):
                    StrictPostNormDriver(owner, memory, job)
                self.assertTrue(owner.ports()['job_ready'])
                self.assertIsNone(owner.scalar.client)
                self.assertFalse(output.published)

    def test_final_ack_stall_and_held_preflight_are_readonly_until_real_accept(self):
        driver = self.driver()
        self.until(driver, lambda: driver.pending is not None and driver.owner.request.write and
                   driver.counts['write_bytes'] == driver.job.write_bytes)
        obligation = driver.memory.pending
        for _ in range(3):
            self.assertFalse(driver.tick(memory_response_ready=False)['response_fire'])
            with self.assertRaisesRegex(ValueError, 'held real terminal'):
                driver.preflight_response()
            self.assertIs(driver.memory.pending, obligation)
            self.assertEqual(driver.owner.ack_bytes, rms.ROW_BYTES - 64)
            self.assertFalse(driver.output.published)
        event = driver.tick()
        self.assertTrue(event['memory_response_fire'])
        self.assertFalse(event['response_fire'])
        result = driver.owner.result
        self.assertIs(driver.preflight_response(), result)
        for _ in range(3):
            before = (driver.owner.ticks, dict(driver.counts), dict(driver.owner.counts),
                      driver._output_hash.digest(), dict(driver.owner.scalar.calls))
            self.assertIs(driver.preflight_response(), result)
            self.assertEqual(before, (driver.owner.ticks, dict(driver.counts), dict(driver.owner.counts),
                                     driver._output_hash.digest(), dict(driver.owner.scalar.calls)))
            self.assertFalse(driver.tick(response_ready=False)['response_fire'])
            self.assertIs(driver.owner.result, result)
            with self.assertRaises(ValueError):
                driver.memory.read64(driver.job.output)
        self.assertTrue(driver.tick()['response_fire'])
        self.assertIs(driver.response, result)
        self.assertTrue(driver.output.published)
        with self.assertRaisesRegex(ValueError, 'retired'):
            driver.preflight_response()

    def test_terminal_identity_and_every_field_rechecked_before_accept(self):
        defects = dict(tag=72, status='Memory', write_bytes=0, model_ticks=float('inf'))
        for replace_object in (False, True):
            for field, value in defects.items():
                with self.subTest(replace_object=replace_object, field=field):
                    driver = self.held()
                    self.assertIs(driver.preflight_response(), driver.owner.result)
                    if replace_object:
                        driver.owner.result = replace(driver.owner.result, **{field: value})
                    else:
                        object.__setattr__(driver.owner.result, field, value)
                    self.assert_blocked(driver)
        driver = self.held()
        driver.owner.result = replace(driver.owner.result)
        self.assert_blocked(driver)

    def test_original_job_and_all_regions_sources_scalars_banks_remain_bound(self):
        defects = ('job', 'owner_job', 'job_tag', 'job_input', 'job_weight', 'job_output', 'job_tokens',
                   'job_policy', 'job_width', 'job_dtype', 'owner', 'memory', 'scalar', 'scalar_owned',
                   'observer', 'source_region', 'weight_region', 'output_region', 'source_storage',
                   'weight_storage', 'output_storage', 'output_base', 'output_extent', 'output_readonly',
                   'regions', 'partial_alias', 'source_readonly', 'weight_readonly', 'source_bytes',
                   'weight_bytes', 'source_written', 'source_acknowledged', 'source_published',
                   'weight_published', 'source_hashes', 'row_bank', 'weight_bank', 'output_bank', 'bank_size')
        for defect in defects:
            with self.subTest(defect=defect):
                driver = self.held()
                if defect in ('job', 'owner_job'):
                    if defect == 'job':
                        driver.job = replace(driver.job)
                    else:
                        driver.owner.job = replace(driver.job)
                elif defect.startswith('job_'):
                    field = defect[4:]
                    value = dict(tag=True, input=0x20000, weight=0x70000, output=0xa0000,
                                 tokens=True, policy=driver.job.policy.value, width=2048.0, dtype=b'bf16')[field]
                    object.__setattr__(driver.job, field, value)
                elif defect in ('owner', 'memory'):
                    setattr(driver, defect, deepcopy(getattr(driver, defect)))
                elif defect == 'scalar':
                    driver.owner.scalar = rms.SharedScalar()
                elif defect == 'scalar_owned':
                    driver.owner.scalar.client = driver.owner
                elif defect == 'observer':
                    driver.owner.observer = lambda *_: None
                elif defect in ('source_region', 'weight_region', 'output_region'):
                    region = dict(source_region=driver.input, weight_region=driver.weight,
                                  output_region=driver.output)[defect]
                    driver.memory.regions[region.base] = replace(region)
                elif defect in ('source_storage', 'weight_storage', 'output_storage'):
                    region = dict(source_storage=driver.input, weight_storage=driver.weight,
                                  output_storage=driver.output)[defect]
                    region.storage = bytearray(region.storage)
                elif defect == 'output_base':
                    driver.output.base += 64
                elif defect == 'output_extent':
                    driver.output.extent += 64
                elif defect == 'output_readonly':
                    driver.output.readonly = True
                elif defect == 'regions':
                    driver.memory.regions = dict(driver.memory.regions)
                elif defect == 'partial_alias':
                    driver.memory.regions[0xa0000] = replace(driver.input, base=driver.input.base + 64, extent=64)
                elif defect == 'source_readonly':
                    driver.input.readonly = True
                elif defect == 'weight_readonly':
                    driver.weight.readonly = False
                elif defect in ('source_bytes', 'weight_bytes'):
                    region = driver.input if defect == 'source_bytes' else driver.weight
                    region.storage[64] ^= 1
                elif defect == 'source_written':
                    driver.input.written.clear()
                elif defect == 'source_acknowledged':
                    driver.input.acknowledged.clear()
                elif defect == 'source_published':
                    driver.input.published = False
                elif defect == 'weight_published':
                    driver.weight.published = False
                elif defect == 'source_hashes':
                    driver.source_hashes = tuple(list(driver.source_hashes))
                elif defect == 'bank_size':
                    driver.owner.output_bank.extend(b'xx')
                else:
                    setattr(driver.owner, defect, bytearray(getattr(driver.owner, defect)))
                self.assert_blocked(driver)

    def test_output_hash_finite_bytes_real_coverage_and_ack_counters_are_fenced(self):
        for defect in ('written', 'acknowledged', 'owner_ack', 'owner_ack_count', 'float_ack_count', 'write_count',
                       'ack_count', 'finite_bytes', 'nonfinite_bytes', 'guard', 'bool_coverage', 'fake_coverage'):
            with self.subTest(defect=defect):
                driver = self.held()
                if defect in ('written', 'acknowledged'):
                    getattr(driver.output, defect).remove(64)
                elif defect == 'owner_ack':
                    driver.owner.ack_bytes -= 64
                elif defect == 'owner_ack_count':
                    driver.owner.counts['write_acks'] -= 1
                elif defect == 'float_ack_count':
                    driver.owner.counts['write_acks'] = float(driver.owner.counts['write_acks'])
                elif defect in ('write_count', 'ack_count'):
                    driver.counts['write_bytes' if defect == 'write_count' else 'ack_bytes'] -= 64
                elif defect in ('finite_bytes', 'nonfinite_bytes'):
                    digest = driver._output_hash.digest()
                    driver.output.storage[64:66] = struct.pack('<H', 0x4000 if defect == 'finite_bytes' else 0x7f80)
                    self.assertEqual(driver._output_hash.digest(), digest)
                elif defect == 'guard':
                    driver.output.storage[0] ^= 1
                elif defect == 'bool_coverage':
                    driver.output.acknowledged.remove(0)
                    driver.output.acknowledged.add(False)
                else:
                    class AlwaysEqual(set):
                        def __eq__(self, other):
                            return True
                    driver.output.acknowledged = AlwaysEqual()
                self.assert_blocked(driver)

    def test_source_identity_is_frozen_at_admission_and_rechecked_live(self):
        driver = self.held()
        changed = deepcopy(driver.owner.identity)
        changed['implementation_sha256'] = 'changed'
        with patch.object(rms.RmsOwner, 'source_identity', staticmethod(lambda _: changed)):
            self.assert_blocked(driver)
        driver.owner.identity['implementation_sha256'] = 'changed'
        self.assert_blocked(driver)

    def test_held_success_abort_creates_real_failure_and_held_high_does_not_bypass_fence(self):
        for corrupt_success in (False, True):
            with self.subTest(corrupt_success=corrupt_success):
                driver = self.held()
                success = driver.owner.result
                if corrupt_success:
                    driver.owner.result = replace(success, tag=72)
                event = driver.tick(abort=True)
                self.assertFalse(event['response_fire'])
                failed = driver.preflight_response()
                self.assertIsNot(success, failed)
                self.assertEqual(failed.status, 'Aborted')
                driver.owner.result = replace(failed)
                self.assert_blocked(driver, tick_options=dict(abort=True))
                driver.owner.result = failed
                self.assertTrue(driver.tick(abort=True)['response_fire'])
                self.assertIs(driver.response, failed)
                self.assertFalse(driver.output.published)
                self.assertEqual(driver.owner.counts['owner_results'], 1)
                self.assertEqual(driver.owner.state, 'locked')

    def test_abort_inflight_preserves_real_obligation_until_drain(self):
        for write in (False, True):
            driver = self.driver()
            self.until(driver, lambda: driver.pending is not None and driver.owner.request.write == write)
            pending, physical = driver.pending, driver.memory.pending
            driver.tick(abort=True, memory_response_ready=False)
            self.assertEqual(driver.owner.state, 'drain')
            self.assertIs(driver.pending, pending)
            self.assertIs(driver.memory.pending, physical)
            self.assertIs(driver.owner.scalar.client, driver.owner)
            with self.assertRaises(ValueError):
                driver.owner.reset()
            driver.tick(abort=True)
            self.assertEqual(driver.preflight_response().status, 'Aborted')
            driver.tick(abort=True)
            self.assertFalse(driver.output.published)
            self.assertIsNone(driver.memory.pending)
            self.assertIsNone(driver.owner.scalar.client)

    def test_read_ack_and_observer_errors_return_real_unpublished_failure(self):
        for phase in ('read', 'ack', 'observer'):
            with self.subTest(phase=phase):
                def reject(stage, *_):
                    if stage == 'output':
                        raise RuntimeError('intentional host observer failure')
                driver = self.driver(observer=reject if phase == 'observer' else None)
                if phase == 'read':
                    self.until(driver, lambda: driver.pending is not None)
                    driver.tick(read_error=True)
                elif phase == 'ack':
                    self.until(driver, lambda: driver.pending is not None and driver.owner.request.write and
                               driver.counts['write_bytes'] == driver.job.write_bytes)
                    driver.tick(ack_error=True)
                else:
                    self.until(driver, lambda: driver.owner.state == 'finish', response_ready=False)
                failed = driver.preflight_response()
                self.assertEqual(failed.status, 'Observer' if phase == 'observer' else 'Memory')
                self.assertEqual(failed.write_bytes, dict(read=0, ack=4032, observer=2048)[phase])
                self.assertTrue(driver.tick()['response_fire'])
                self.assertFalse(driver.output.published)
                self.assertIsNone(driver.memory.pending)
                self.assertIsNone(driver.owner.scalar.client)

    def test_pending_and_physical_obligation_tampering_fails_closed_without_repair(self):
        for defect in ('pending_replace', 'pending_tag', 'pending_size', 'request_replace',
                       'physical_replace', 'physical_tag', 'physical_count', 'physical_region', 'physical_offsets'):
            with self.subTest(defect=defect):
                driver = self.driver()
                self.until(driver, lambda: driver.pending is not None and driver.owner.request.write)
                if defect == 'pending_replace':
                    driver.pending = replace(driver.pending)
                elif defect == 'pending_tag':
                    object.__setattr__(driver.pending, 'tag', driver.pending.tag + 1)
                elif defect == 'pending_size':
                    object.__setattr__(driver.pending, 'nbytes', 32)
                elif defect == 'request_replace':
                    driver.owner.request = replace(driver.owner.request)
                elif defect == 'physical_replace':
                    driver.memory.pending = list(driver.memory.pending)
                elif defect == 'physical_tag':
                    command = driver.memory.pending[0]
                    object.__setattr__(command, 'tag', command.tag + 1)
                elif defect == 'physical_count':
                    driver.memory.pending[3] = 0
                elif defect == 'physical_region':
                    driver.memory.pending[1] = driver.input
                else:
                    driver.memory.pending[2] = (64,)
                obligation = driver.memory.pending
                self.assert_blocked(driver)
                self.assertIs(driver.memory.pending, obligation)
                self.assertEqual(driver.owner.state, 'wait')
                self.assertIs(driver.owner.scalar.client, driver.owner)

    def test_frozen_producer_coverage_and_unchanged_original_tick_interface(self):
        owner, memory, job = self.resources()
        for address in (job.input, job.weight):
            region = memory.regions[address]
            region.written, region.acknowledged = frozenset(region.written), frozenset(region.acknowledged)
        driver = StrictPostNormDriver(owner, memory, job)
        self.until(driver, lambda: driver.response is not None)
        self.assertTrue(driver.output.published)
        self.assertEqual(inspect.signature(StrictPostNormDriver.tick), inspect.signature(rms.TypedRmsDriver.tick))
        self.assertTrue(issubclass(StrictPostNormDriver, rms.TypedRmsDriver))
        self.assertNotIn('_compute', StrictPostNormDriver.__dict__)
        self.assertNotIn('ack_tag', inspect.signature(StrictPostNormDriver.tick).parameters)
        self.assertNotIn('ack_nbytes', inspect.signature(StrictPostNormDriver.tick).parameters)


if __name__ == '__main__':
    unittest.main()
