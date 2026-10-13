"""Small actual KV -> real scalar Add -> final-fence acceptance gates.

Upstream bytes are synthetic real TypedMemory producers. No complete L3,
checkpoint numerical acceptance, Matrix build or RTL is claimed here.
"""
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch

from ...qwen35_gdn_prefill.typed_dense import TypedMemory
from ...qwen35_gdn_prefill.elementwise.model import ElementwiseOwner, ElementwiseJob, TypedElementwiseDriver
from ...qwen35_gdn_prefill.conv.scalar import ConvScalar
from .driver import TypedKvCacheDriver
from .fence import KvBlockFence
from .owner import KvCacheOwner, KvCacheJob
from .test_kv_cache import producer


class RealFinalOwnerTests(unittest.TestCase):
    def setUp(self):
        self.memory = TypedMemory()
        self.fence = KvBlockFence(self.memory)
        self.kv_owner = KvCacheOwner()
        self.scalar = ConvScalar()
        self.final_owner = ElementwiseOwner(self.scalar, hidden_width=32, ffn_width=32, test_geometry=True)
        self.ordinal = 0

    def until(self, driver, predicate, **controls):
        for _ in range(10000):
            if predicate():
                return
            driver.tick(**controls)
        self.fail('bounded real small owner did not finish')

    def new_kv(self, *, staging=None):
        self.ordinal += 1
        base = 0x10000000 + self.ordinal * 0x100000
        a = producer(self.memory, base, struct.pack('<512H', *([0x3f80 + self.ordinal] * 512)), self.ordinal * 10)
        b = producer(self.memory, base + 0x1000, bytes(1024), self.ordinal * 10 + 1)
        old = self.fence.state
        job = KvCacheJob(self.ordinal, old.k_root, old.v_root, old.valid_tokens, a.base, b.base,
                         base + 0x40000 if staging is None else staging, 1, old.generation, old.generation)
        for root, extent in job.output_spans:
            self.memory.allocate_output(root, extent)
        return TypedKvCacheDriver(self.kv_owner, self.memory, job, self.fence)

    def finish_kv(self):
        kv = self.new_kv()
        self.until(kv, lambda: kv.response is not None)
        return kv

    def new_final(self, *, output=None):
        base = 0x20000000 + self.ordinal * 0x10000
        a = producer(self.memory, base, struct.pack('<32H', *([0x3f80] * 32)), 100 + self.ordinal)
        b = producer(self.memory, base + 0x100, struct.pack('<32H', *([0x4000] * 32)), 200 + self.ordinal)
        out = base + 0x200 if output is None else output
        self.memory.allocate_output(out, 64)
        job = ElementwiseJob(1000 + self.ordinal, a.base, b.base, out, 1, row_width=32)
        return TypedElementwiseDriver(self.final_owner, self.memory, job)

    def held(self, driver):
        self.until(driver, lambda: driver.owner.ports()['response'] is not None, response_ready=False)
        return driver.preflight_response()

    def commit(self, kv, final):
        prepared = self.fence.prepare_final_owner(kv.receipt, final, expected_job=final.job)
        event = self.fence.accept_final_owner(prepared)
        self.assertTrue(event['response_fire'])
        return prepared

    def test_real_final_ack_hold_held_success_and_atomic_acceptance(self):
        kv = self.finish_kv()
        before = self.fence.state
        final = self.new_final()
        self.until(final, lambda: final.pending_write is not None)
        for _ in range(3):
            final.tick(memory_response_ready=False)
            self.assertIsNone(final.owner.ports()['response'])
            self.assertFalse(final.output.published)
            self.assertIs(self.fence.state, before)
        self.held(final)
        prepared = self.fence.prepare_final_owner(kv.receipt, final, expected_job=final.job)
        for _ in range(3):
            final.tick(response_ready=False)
            self.assertFalse(final.output.published)
            self.assertIs(self.fence.state, before)
        with patch.object(self.memory, 'publish', wraps=self.memory.publish) as publish:
            self.assertTrue(self.fence.accept_final_owner(prepared)['response_fire'])
            self.assertEqual(publish.call_count, 1)
        self.assertEqual(struct.unpack('<32H', final.output.raw()), (0x4040,) * 32)
        self.assertTrue(final.output.published)
        self.assertEqual((self.fence.state.k_root, self.fence.state.valid_tokens, self.fence.state.generation),
                         (kv.job.staging_k, 1, 1))
        self.assertIsNone(self.fence.pending_receipt)
        with self.assertRaises(ValueError):
            self.fence.accept_final_owner(prepared)
        with self.assertRaises(ValueError):
            final.tick(abort=True)
        self.assertTrue(final.output.published)
        self.assertEqual(self.fence.state.generation, 1)

    def test_rejects_wrong_final_job_tag_receipt_ack_and_source_before_acceptance(self):
        kv = self.finish_kv()
        final = self.new_final()
        real = self.held(final)
        before = self.fence.state
        with self.assertRaises(ValueError):
            self.fence.prepare_final_owner(kv.receipt, final, expected_job=replace(final.job, tag=9))
        with self.assertRaises(ValueError):
            self.fence.prepare_final_owner(replace(kv.receipt), final, expected_job=final.job)
        for obj, name, changed in ((final.owner, 'result', replace(real, tag=real.tag + 1)),
                (final.output, 'acknowledged', set()), (final.a, 'written', set()),
                (self.fence, '_state', replace(before, generation=1))):
            with self.subTest(field=name):
                old = getattr(obj, name)
                setattr(obj, name, changed)
                with self.assertRaises(ValueError):
                    self.fence.prepare_final_owner(kv.receipt, final, expected_job=final.job)
                setattr(obj, name, old)
                self.assertIsNone(final.response)
                self.assertFalse(final.output.published)
        final.a.storage[64] ^= 1
        with self.assertRaises(ValueError):
            self.fence.prepare_final_owner(kv.receipt, final, expected_job=final.job)
        final.a.storage[64] ^= 1
        self.assertIs(self.fence.state, before)
        self.commit(kv, final)

    def test_prepared_revalidates_changed_staging_source_ack_and_generation(self):
        kv = self.finish_kv()
        final = self.new_final()
        self.held(final)
        prepared = self.fence.prepare_final_owner(kv.receipt, final, expected_job=final.job)
        for region in (kv.outputs[0], final.a):
            region.storage[64] ^= 1
            with self.assertRaises(ValueError):
                self.fence.accept_final_owner(prepared)
            region.storage[64] ^= 1
        coverage = final.output.acknowledged
        final.output.acknowledged = set()
        with self.assertRaises(ValueError):
            self.fence.accept_final_owner(prepared)
        final.output.acknowledged = coverage
        before = self.fence.state
        object.__setattr__(before, 'generation', 9)
        with self.assertRaises(ValueError):
            self.fence.accept_final_owner(prepared)
        object.__setattr__(before, 'generation', 0)
        self.assertIsNone(final.response)
        self.assertFalse(final.output.published)
        self.fence.accept_final_owner(prepared)
        self.assertEqual(self.fence.state.generation, 1)

    def test_final_output_in_unused_kv_capacity_is_rejected(self):
        kv = self.finish_kv()
        final = self.new_final(output=kv.job.staging_k + 2048)
        self.held(final)
        with self.assertRaisesRegex(ValueError, 'reservation'):
            self.fence.prepare_final_owner(kv.receipt, final, expected_job=final.job)
        self.assertFalse(final.output.published)
        self.assertEqual(self.fence.state.generation, 0)
        final.tick(abort=True, response_ready=True)
        self.until(final, lambda: final.response is not None)
        self.fence.discard_pending(kv.receipt)

    def test_held_success_abort_and_reset_win_over_ready(self):
        for control in ('abort', 'reset'):
            with self.subTest(control=control):
                self.setUp()
                kv = self.finish_kv()
                final = self.new_final()
                self.held(final)
                prepared = self.fence.prepare_final_owner(kv.receipt, final, expected_job=final.job)
                before = self.fence.state
                event = final.tick(**{control: True, 'response_ready': True})
                self.assertFalse(event['response_fire'])
                self.assertFalse(final.output.published)
                with self.assertRaises(ValueError):
                    self.fence.accept_final_owner(prepared)
                self.until(final, lambda: final.response is not None)
                self.assertEqual(final.response.status, 'Aborted')
                self.fence.discard_pending(kv.receipt)
                self.assertIs(self.fence.state, before)
                self.assertIsNone(self.fence.pending_receipt)

    def test_post_kv_failure_discard_retry_fresh_staging_and_actual_carried_roots(self):
        cold = self.finish_kv()
        final = self.new_final()
        self.held(final)
        self.commit(cold, final)
        roots = self.fence.state
        cold_raw = tuple(r.raw() for r in cold.outputs)
        failed = self.finish_kv()
        self.assertIs(failed.inputs[0], cold.outputs[0])
        bad_final = self.new_final()
        self.until(bad_final, lambda: bad_final.response is not None, read_error=True)
        self.assertEqual(bad_final.response.status, 'Memory')
        self.assertFalse(bad_final.output.published)
        self.fence.discard_pending(failed.receipt)
        self.assertIs(self.fence.state, roots)
        with self.assertRaisesRegex(ValueError, 'fresh staging'):
            self.fence.validate_job(failed.job)
        self.final_owner.reset()
        retry = self.finish_kv()
        self.assertIs(retry.inputs[0], cold.outputs[0])
        self.assertEqual(tuple(r.raw()[:1024] for r in retry.outputs), cold_raw)
        good_final = self.new_final()
        self.held(good_final)
        self.commit(retry, good_final)
        self.assertEqual((self.fence.state.valid_tokens, self.fence.state.generation), (2, 2))
        self.assertEqual(tuple(r.raw() for r in cold.outputs), cold_raw)

    def test_changed_old_root_rejected_before_final_acceptance(self):
        cold = self.finish_kv()
        final = self.new_final()
        self.held(final)
        self.commit(cold, final)
        carried = self.finish_kv()
        final = self.new_final()
        self.held(final)
        prepared = self.fence.prepare_final_owner(carried.receipt, final, expected_job=final.job)
        cold.outputs[0].storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'committed prefix changed'):
            self.fence.accept_final_owner(prepared)
        self.assertIsNone(final.response)
        self.assertFalse(final.output.published)
        cold.outputs[0].storage[64] ^= 1
        self.fence.accept_final_owner(prepared)


if __name__ == '__main__':
    unittest.main()
