"""Synthetic A-scratch ownership regressions; no model/native arithmetic."""
import copy
from types import SimpleNamespace
import unittest
from .scratch import CacheFault, ReadonlyKVIdentity, SharedAScratch


class ScratchOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.s = SharedAScratch()
        self.job = SimpleNamespace(m=1, tag=7, b=0x1000, c=0x2000,
                                   dst=0x3000, write_bytes=6144)
        self.identity = ReadonlyKVIdentity(1, 2, 3, 4)
        self.owner = object()

    def test_null_resident_admission_rejected_before_mutation(self):
        before = copy.deepcopy(self.s.__dict__)
        with self.assertRaises(CacheFault):
            self.s.acquire(None, self.job, self.identity)
        self.assertEqual(self.s.__dict__, before)

    def test_null_external_admission_rejected_before_mutation(self):
        before = copy.deepcopy(self.s.__dict__)
        with self.assertRaises(CacheFault):
            self.s.reserve_external(None)
        self.assertEqual(self.s.__dict__, before)

    def test_resident_blocks_other_clients_and_external_route(self):
        self.s.acquire(self.owner, self.job, self.identity)
        before = {k: copy.deepcopy(v) for k, v in self.s.__dict__.items() if k != 'owner'}
        for other in (None, object()):
            with self.assertRaises(CacheFault):
                self.s.acquire(other, self.job, self.identity)
            with self.assertRaises(CacheFault):
                self.s.reserve_external(other)
            with self.assertRaises(CacheFault):
                self.s.release(other)
        self.assertIs(self.s.owner, self.owner)
        self.assertEqual({k: v for k, v in self.s.__dict__.items() if k != 'owner'}, before)

    def test_external_blocks_resident_until_release(self):
        self.s.reserve_external(self.owner)
        with self.assertRaises(CacheFault):
            self.s.acquire(object(), self.job, self.identity)
        with self.assertRaises(CacheFault):
            self.s.release_external(None)
        self.s.release_external(self.owner)
        self.s.acquire(self.owner, self.job, self.identity)
        self.assertIs(self.s.owner, self.owner)

    def test_fill_ack_held_read_and_reacquire(self):
        self.s.acquire(self.owner, self.job, self.identity)
        raw = bytes(range(64))
        request = self.s.make_request(self.owner, self.job.b, 1, raw)
        self.s.accept(self.owner, request)
        self.assertFalse(self.s.present(request.line))
        self.assertIsNone(self.s.response())
        with self.assertRaises(CacheFault):
            self.s.release(self.owner)
        self.s.clock += 1
        self.s.consume(self.owner)
        self.assertTrue(self.s.present(request.line))
        self.s.accept(self.owner, self.s.make_request(self.owner, self.job.b, 2))
        self.s.clock += 1
        held = self.s.response()
        self.s.clock += 3
        self.assertIs(self.s.response(), held)
        self.assertEqual(self.s.consume(self.owner).data, raw)
        epoch = self.s.epoch
        self.s.release(self.owner)
        self.assertFalse(self.s.present(request.line))
        self.s.acquire(object(), self.job, self.identity)
        self.assertEqual(self.s.epoch, epoch + 1)

    def test_revoked_fill_drains_without_committing(self):
        self.s.acquire(self.owner, self.job, self.identity)
        request = self.s.make_request(self.owner, self.job.b, 1, bytes(64))
        self.s.accept(self.owner, request)
        self.s.revoke()
        with self.assertRaises(CacheFault):
            self.s.release(self.owner)
        self.s.clock += 1
        self.s.consume(self.owner, abort=True)
        self.assertFalse(self.s.present(request.line))
        self.s.release(self.owner)
        self.assertIsNone(self.s.owner)

    def test_falsey_nonnull_owner_is_not_idle_sentinel(self):
        owner = []
        self.s.acquire(owner, self.job, self.identity)
        self.assertIs(self.s.owner, owner)
        with self.assertRaises(CacheFault):
            self.s.reserve_external(object())
        self.s.release(owner)
        self.s.reserve_external(owner)
        self.s.release_external(owner)


if __name__ == '__main__':
    unittest.main()
