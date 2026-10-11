"""Source-bound proposal/control tests, explicitly NOT hardware acceptance."""
import unittest
from dataclasses import replace

from seed_protocol_model import Ack, Beat, Request, ResidentPrefixOwner, SeedControllerModel, route


def pattern(i):
    special = (0, 0x80000000, 1, 0x80000001, 0x007FFFFF, 0x807FFFFF,
               0x00800000, 0x80800000, 0x3F800001, 0xBF800001,
               0x7F7FFFFF, 0xFF7FFFFF)
    return special[i % len(special)]


def advance_to_collect(c, req=None):
    req = Request(slice_mask=c.slice_mask) if req is None else req
    assert c.begin(req) and c.reserve()
    for i, _ in enumerate(route(req.slice_mask)):
        assert c.beat(Beat.make(req, i, [pattern(i * 16 + j) for j in range(16)], i + 1 == len(route(req.slice_mask))))
    assert c.commit()
    return req


def advance_to_reply(c, req=None):
    req = advance_to_collect(c, req)
    for s in range(8):
        if req.slice_mask & (1 << s):
            assert c.leaf_ack(s, Ack.make(req))
    assert c.state == 'reply'
    return req


class ControllerTests(unittest.TestCase):
    def test_each_of_five_destination_contexts(self):
        for context in range(5):
            with self.subTest(context=context):
                c = SeedControllerModel(slice_mask=1)
                advance_to_reply(c, Request(context=context, slice_mask=1))
                c.take_response()
                self.assertEqual(c.seeded, 1 << context)
                self.assertTrue(c.first_step(context, False))

    def test_full_context_exact_bits_no_publish_before_every_ack(self):
        owner = ResidentPrefixOwner()
        words = [pattern(i) for i in range(4096)]
        owner.store(0, 0, 0, 256, words)
        req = Request()
        lease = owner.open_restore(req, 0, 0, 0, 256, 16, 256)
        c = SeedControllerModel()
        self.assertTrue(c.begin(req))
        self.assertTrue(c.reserve())
        for b in owner.beats(req, lease):
            self.assertTrue(c.beat(b))
            self.assertEqual(c.seeded, 0)
            self.assertFalse(any(c.leaf_valid[0]))
        self.assertEqual(c.writes, 256)
        self.assertEqual(owner.read_words, 512)
        self.assertEqual(len(owner.scratch), 768 * 1024)
        self.assertEqual(c.banks[0], words)
        self.assertTrue(c.commit())
        for s in range(7):
            self.assertTrue(c.leaf_ack(s, Ack.make(req)))
            self.assertEqual(c.seeded, 0)
            self.assertIsNone(c.response())
        self.assertFalse(c.first_step(0, False))
        self.assertTrue(c.leaf_ack(7, Ack.make(req)))
        self.assertEqual(c.seeded, 0)
        self.assertTrue(c.take_response())
        self.assertEqual(c.seeded, 1)
        self.assertEqual(c.commit_events, 1)
        owner.release(lease, True)

    def test_sparse_slices_map_without_alias(self):
        c = SeedControllerModel(slice_mask=0b01001010)
        req = advance_to_reply(c, Request(context=4, slice_mask=c.slice_mask))
        c.take_response()
        self.assertEqual(c.writes, 96)
        self.assertEqual(c.seeded, 16)
        for row in range(16):
            for col in range(256):
                if not c.slice_mask & (1 << (col // 32)):
                    self.assertEqual(c.banks[4][row * 256 + col], 0x3F000000)
        self.assertEqual(req.context, 4)

    def test_begin_shape_identity_and_live_context_rejected_before_mutation(self):
        variations = [dict(context=5), dict(group_tag=7), dict(group_sequence=2), dict(slice_mask=0), dict(slice_mask=3)]
        for fields in variations:
            with self.subTest(fields=fields):
                c = SeedControllerModel()
                before = tuple(map(tuple, c.banks))
                c.begin(replace(Request(), **fields))
                self.assertTrue(c.poison)
                self.assertEqual(tuple(map(tuple, c.banks)), before)
                self.assertFalse(c.reserved)
        for field in ('seen', 'closed', 'seeded'):
            c = SeedControllerModel()
            setattr(c, field, 1)
            c.begin(Request())
            self.assertTrue(c.poison)
            self.assertEqual(c.writes, 0)
        for field in ('quiescent', 'group_active'):
            c = SeedControllerModel()
            setattr(c, field, False)
            c.begin(Request())
            self.assertTrue(c.poison)
            self.assertEqual(c.writes, 0)

    def test_bad_beat_cannot_mutate_its_target(self):
        changes = [dict(index=0), dict(index=2), dict(last=True), dict(context=1),
                   dict(group_tag=0), dict(group_sequence=0), dict(source_generation=2),
                   dict(error=True)]
        for special in (0x7F800000, 0xFF800000, 0x7FC12345, 0x7F800001, 0xFFC12345):
            changes.append(dict(words=(special,) + (0,) * 15))
        for change in changes:
            with self.subTest(change=change):
                c = SeedControllerModel()
                req = Request()
                c.begin(req)
                c.reserve()
                c.beat(Beat.make(req, 0, [pattern(i) for i in range(16)]))
                before = tuple(c.banks[0])
                c.beat(replace(Beat.make(req, 1, [0] * 16), **change))
                self.assertTrue(c.poison)
                self.assertEqual(tuple(c.banks[0]), before)
                self.assertEqual(c.writes, 1)
                self.assertEqual(c.seeded, 0)
                self.assertFalse(any(c.leaf_valid[0]))
                self.assertFalse(c.first_step(0, False))
                c.take_response()
                self.assertEqual(c.state, 'locked')
                self.assertFalse(c.begin(req))

    def test_missing_last_rejected_before_last_write(self):
        c = SeedControllerModel(slice_mask=1)
        req = Request(slice_mask=1)
        c.begin(req)
        c.reserve()
        for i in range(31):
            c.beat(Beat.make(req, i, [0] * 16))
        before = tuple(c.banks[0])
        c.beat(Beat.make(req, 31, [1] * 16, last=False))
        self.assertTrue(c.poison)
        self.assertEqual(tuple(c.banks[0]), before)

    def test_missing_beat_or_ack_does_not_publish_or_timeout_to_success(self):
        c = SeedControllerModel()
        c.begin(Request())
        c.reserve()
        for _ in range(100):
            c.observe()
        self.assertEqual(c.state, 'stream')
        self.assertEqual(c.commit_events, 0)
        c = SeedControllerModel()
        req = advance_to_collect(c)
        for s in range(7):
            c.leaf_ack(s, Ack.make(req))
        for _ in range(100):
            c.observe()
        self.assertEqual(c.state, 'collect')
        self.assertEqual(c.seeded, 0)
        self.assertFalse(c.take_response())

    def test_backpressure_no_extra_write_and_stable_terminal_ack(self):
        c = SeedControllerModel(slice_mask=1)
        req = Request(slice_mask=1)
        c.begin(req)
        self.assertFalse(c.reserve(False))
        self.assertFalse(c.reserved)
        c.reserve()
        beat = Beat.make(req, 0, [pattern(i) for i in range(16)])
        for _ in range(10):
            self.assertFalse(c.beat(beat, False))
            self.assertEqual(c.next_beat, 0)
            self.assertEqual(c.writes, 0)
        self.assertTrue(c.beat(beat))
        self.assertEqual(c.writes, 1)
        c = SeedControllerModel(slice_mask=1)
        advance_to_reply(c)
        response = c.response()
        for _ in range(10):
            self.assertFalse(c.take_response(False))
            self.assertEqual(c.response(), response)
        self.assertEqual(c.commit_events, 0)
        c.take_response()
        self.assertEqual(c.commit_events, 1)
        self.assertFalse(c.take_response())
        self.assertEqual(c.responses, 1)

    def test_wrong_duplicate_unselected_ack_and_commit_error(self):
        for mutation in ('identity', 'generation', 'error', 'duplicate', 'unselected'):
            with self.subTest(mutation=mutation):
                c = SeedControllerModel(slice_mask=3)
                req = advance_to_collect(c)
                ack = Ack.make(req)
                if mutation == 'identity':
                    c.leaf_ack(0, replace(ack, context=1))
                elif mutation == 'generation':
                    c.leaf_ack(0, replace(ack, source_generation=2))
                elif mutation == 'error':
                    c.leaf_ack(0, replace(ack, error=True))
                elif mutation == 'duplicate':
                    c.leaf_ack(0, ack)
                    c.leaf_ack(0, ack)
                else:
                    c.leaf_ack(2, ack)
                self.assertTrue(c.poison)
                self.assertFalse(any(c.leaf_valid[0]))
                self.assertEqual(c.seeded, 0)
                self.assertTrue(c.response().error)

    def test_early_ack_is_not_replayed_as_fresh_commit_ack(self):
        for phase in ('idle', 'reserve', 'stream', 'commit'):
            with self.subTest(phase=phase):
                c = SeedControllerModel(slice_mask=1)
                req = Request(slice_mask=1)
                if phase != 'idle':
                    c.begin(req)
                if phase in ('stream', 'commit'):
                    c.reserve()
                if phase == 'commit':
                    for i in range(32):
                        c.beat(Beat.make(req, i, [0] * 16, i == 31))
                c.leaf_ack(0, Ack.make(req))
                self.assertTrue(c.poison)
                self.assertEqual(c.seeded, 0)
                if phase == 'idle':
                    self.assertEqual(c.state, 'locked')
                    self.assertIsNone(c.response())

    def test_late_ack_cannot_publish_held_success(self):
        c = SeedControllerModel(slice_mask=1)
        req = advance_to_reply(c)
        held = c.response()
        c.leaf_ack(0, Ack.make(req))
        self.assertTrue(c.poison)
        self.assertEqual(c.response(), held)
        c.take_response()
        self.assertEqual(c.state, 'locked')
        self.assertEqual(c.commit_events, 0)

    def test_abort_in_all_active_phases_latches_and_invalidates(self):
        for phase in ('reserve', 'stream', 'commit', 'collect', 'reply'):
            with self.subTest(phase=phase):
                c = SeedControllerModel(slice_mask=1)
                req = Request(slice_mask=1)
                c.begin(req)
                if phase != 'reserve':
                    c.reserve()
                if phase in ('commit', 'collect', 'reply'):
                    for i in range(32):
                        c.beat(Beat.make(req, i, [pattern(i)] * 16, i == 31))
                if phase in ('collect', 'reply'):
                    c.commit()
                if phase == 'reply':
                    c.leaf_ack(0, Ack.make(req))
                c.observe(abort=True)
                self.assertTrue(c.poison)
                self.assertFalse(any(c.leaf_valid[0]))
                c.observe(abort=False)
                self.assertTrue(c.poison)
                c.take_response(abort=True)
                self.assertEqual(c.state, 'locked')
                self.assertEqual(c.seeded, 0)
                self.assertEqual(c.responses, 1)

    def test_reply_pulse_abort_preserves_ack_bits_but_never_recommits(self):
        c = SeedControllerModel(slice_mask=1)
        advance_to_reply(c)
        held = c.response()
        self.assertFalse(held.error)
        c.take_response(ready=False, abort=True)
        c.observe(abort=False)
        self.assertEqual(c.response(), held)
        self.assertTrue(c.poison)
        self.assertFalse(any(c.leaf_valid[0]))
        c.take_response()
        self.assertEqual(c.seeded, 0)
        self.assertEqual(c.commit_events, 0)
        self.assertEqual(c.state, 'locked')

    def test_reply_identity_and_resource_loss_is_sticky(self):
        for field, changed in [('group_tag', 9), ('group_sequence', 2), ('slice_mask', 3), ('group_active', False), ('quiescent', False)]:
            with self.subTest(field=field):
                c = SeedControllerModel(slice_mask=1)
                advance_to_reply(c)
                original = getattr(c, field)
                held = c.response()
                setattr(c, field, changed)
                c.take_response(ready=False)
                setattr(c, field, original)
                self.assertTrue(c.poison)
                self.assertEqual(c.response(), held)
                c.take_response()
                self.assertEqual(c.commit_events, 0)

    def test_error_ack_stays_stable_under_backpressure(self):
        c = SeedControllerModel()
        c.begin(Request(context=5))
        held = c.response()
        self.assertTrue(held.error)
        for _ in range(5):
            c.take_response(False, abort=True)
            self.assertEqual(c.response(), held)
        c.take_response()
        self.assertEqual(c.state, 'locked')

    def test_first_step_clear_policy(self):
        c = SeedControllerModel(slice_mask=1)
        self.assertFalse(c.first_step(0, False))
        self.assertTrue(c.first_step(0, True))
        self.assertTrue(c.first_step(0, False))
        self.assertFalse(c.first_step(0, True))
        c = SeedControllerModel(slice_mask=1)
        advance_to_reply(c)
        c.take_response()
        self.assertFalse(c.first_step(0, True))
        self.assertTrue(c.first_step(0, False))
        self.assertTrue(c.first_step(0, False))
        self.assertFalse(c.first_step(0, True))
        c.begin(Request(slice_mask=1))
        self.assertTrue(c.poison)


class ResidentOwnerTests(unittest.TestCase):
    def make(self, m=16, n=256, k=1792):
        o = ResidentPrefixOwner(m, n, k)
        o.store(0, 0, 0, 256, [pattern(i) for i in range(min(m, 16) * min(n, 256))])
        return o

    def test_partial_shape_uses_zero_not_uninitialized_padding(self):
        o = self.make(m=3, n=48)
        req = Request(slice_mask=3)
        lease = o.open_restore(req, 0, 0, 0, 256, 3, 48)
        c = SeedControllerModel(slice_mask=3)
        c.begin(req)
        c.reserve()
        for b in o.beats(req, lease):
            c.beat(b)
        self.assertEqual(c.writes, 64)
        self.assertEqual(o.read_words, 18)
        for row in range(16):
            for col in range(64):
                expected = pattern(row * 48 + col) if row < 3 and col < 48 else 0
                self.assertEqual(c.banks[0][row * 256 + col], expected)

    def test_alias_shape_slot_generation_and_prefix_checks(self):
        mutations = [dict(slot=3), dict(tile_row=1), dict(n_base=256), dict(prefix_k=512),
                     dict(rows=15), dict(cols=240), dict(c_base=0), dict(c_base=129)]
        for change in mutations:
            with self.subTest(change=change):
                o = self.make()
                args = dict(slot=0, tile_row=0, n_base=0, prefix_k=256, rows=16, cols=256)
                args.update(change)
                before = bytes(o.scratch)
                with self.assertRaises(ValueError):
                    o.open_restore(Request(), **args)
                self.assertEqual(bytes(o.scratch), before)
                self.assertEqual(o.leases, {})
        o = self.make()
        with self.assertRaises(ValueError):
            o.open_restore(Request(source_generation=2), 0, 0, 0, 256, 16, 256)

    def test_failed_store_never_publishes_prefix(self):
        o = ResidentPrefixOwner(m=16)
        o.store(0, 0, 0, 256, [0] * 4096, acknowledged=False)
        with self.assertRaises(ValueError):
            o.open_restore(Request(), 0, 0, 0, 256, 16, 256)

    def test_generation_pinned_through_ack_and_quarantined_on_failure(self):
        o = self.make()
        lease = o.open_restore(Request(), 0, 0, 0, 256, 16, 256)
        with self.assertRaises(ValueError):
            o.store(0, 0, 0, 512, [0] * 4096)
        o.release(lease, False)
        with self.assertRaises(ValueError):
            o.store(0, 0, 0, 512, [0] * 4096)
        with self.assertRaises(ValueError):
            o.release(lease, True)
        with self.assertRaises(ValueError):
            next(o.beats(Request(), lease))

    def test_successful_lease_release_permits_next_generation(self):
        o = self.make()
        lease = o.open_restore(Request(), 0, 0, 0, 256, 16, 256)
        o.release(lease, True)
        o.store(0, 0, 0, 512, [0] * 4096)
        self.assertEqual(o.generation[0][0], 2)

    def test_old_lease_cannot_read_new_generation_under_old_tag(self):
        o = self.make()
        req = Request()
        lease = o.open_restore(req, 0, 0, 0, 256, 16, 256)
        old_generator = o.beats(req, lease)
        next(old_generator)
        o.release(lease, True)
        o.store(0, 0, 0, 512, [0x40000000] * 4096)
        with self.assertRaises(ValueError):
            next(o.beats(req, lease))
        with self.assertRaises(ValueError):
            next(old_generator)

    def test_lease_requires_exact_request_and_stable_source_metadata(self):
        o = self.make()
        req = Request()
        lease = o.open_restore(req, 0, 0, 0, 256, 16, 256)
        for field, value in [('context', 1), ('group_tag', 2), ('group_sequence', 2),
                             ('source_generation', 2), ('slice_mask', 3)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                next(o.beats(replace(req, **{field: value}), lease))
        o.generation[0][0] = 2
        with self.assertRaises(ValueError):
            next(o.beats(req, lease))

    def test_generation_wrap_requires_coordinated_reset(self):
        o = self.make()
        o.generation[0][0] = 0xFFFFFFFF
        with self.assertRaises(ValueError):
            o.store(0, 0, 0, 512, [0] * 4096)

    def test_full_a_uses_actual_disjoint_single_c_slot(self):
        o = self.make(k=1536)
        self.assertEqual(o.c_base, 768)
        self.assertEqual(o.slots, 1)
        self.assertEqual(o.address(0, 0, 0), 768 * 32)
        with self.assertRaises(ValueError):
            o.address(1, 0, 0)


if __name__ == '__main__':
    unittest.main()
