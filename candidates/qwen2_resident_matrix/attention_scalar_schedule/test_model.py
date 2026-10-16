"""Short metadata-only schedule tests; no numerical, HDL or synthesis claim.

Scalar spacings here are the source observations encoded by model.py, not
independently measured hardware latency. Vector spacing is a proposed contract.
"""
import unittest
from dataclasses import FrozenInstanceError

from candidates.qwen2_resident_matrix.attention_scalar_schedule.model import (OWNERS, Operation, Offer, Response, Schedule, fold_plan,
                   softmax_plan, silu_plan, workload)


class Plans(unittest.TestCase):
    def test_scalar_observations_and_vector_proposal(self):
        for opcode in ('add', 'mul'):
            self.assertEqual(Operation('sfu16', opcode, 3).spacing, 3)
            self.assertEqual(Operation('vector16', opcode, 2).spacing, 2)
        self.assertEqual(Operation('sfu16', 'exp', 20).spacing, 20)
        self.assertEqual(Operation('sfu16', 'exp', 3).spacing, 3)

    def test_ordered_fold(self):
        plan = fold_plan()
        self.assertEqual(len(plan), 17)
        self.assertEqual([x.opcode for x in plan], ['add'] * 16 + ['mul'])
        self.assertTrue(all(x.pool == 'vector16' and x.spacing == 2 for x in plan))

    def test_ordered_softmax(self):
        plan = softmax_plan(3, 11, (False, True, False))
        self.assertEqual([x.opcode for x in plan],
                         ['add', 'exp', 'add'] * 3 + ['div'] + ['mul'] * 3)
        self.assertEqual([x.spacing for x in plan],
                         [3, 3, 3, 3, 20, 3, 3, 3, 3, 11, 3, 3, 3])
        self.assertTrue(all(x.pool == 'sfu16' for x in plan))

    def test_ordered_silu(self):
        for full in (False, True):
            plan = silu_plan(13, full)
            self.assertEqual([x.opcode for x in plan], ['exp', 'add', 'div', 'mul', 'mul', 'mul'])
            self.assertEqual([x.spacing for x in plan], [20 if full else 3, 3, 13, 3, 3, 3])
            self.assertTrue(all(x.pool == 'sfu16' for x in plan))

    def test_typed_operation_negatives(self):
        for args in [('vector16', 'add', 3), ('vector16', 'exp', 20),
                     ('vector16', 'div', 3), ('sfu16', 'add', 2),
                     ('sfu16', 'mul', 4), ('sfu16', 'exp', 19),
                     ('sfu16', 'div', 2), ('sfu16', 'div', True),
                     ('sfu16', 'div', 3.0), ('sfu16', 'div', 1000001),
                     ('unknown', 'add', 3), ('sfu16', 'sqrt', 3)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                Operation(*args)

    def test_typed_plan_negatives(self):
        for args in [(True, 3, (True,)), (0, 3, ()), (129, 3, (True,) * 129),
                     (1, 3, [True]), (1, 3, (1,)), (2, 3, (True,)),
                     (2, 3, (False, False)), (1, True, (True,))]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                softmax_plan(*args)
        for branch in (0, 1, None, 'full'):
            with self.assertRaises(ValueError):
                silu_plan(3, branch)


class Protocol(unittest.TestCase):
    def make(self, op=None):
        op = op or Operation('vector16', 'add', 2)
        return Schedule({0: (op, op), 1: (op, op)})

    def issue(self, schedule, owner='attention', lanes=(0,)):
        self.assertTrue(schedule.tick(acquire=owner)['acquire_fire'])
        self.assertTrue(schedule.tick(offer=Offer(owner, lanes), feed_ready=True)['offer_fire'])
        return schedule.pending[0]

    def test_vector_capture_then_ack_and_no_same_edge_reissue(self):
        s = self.make()
        r = self.issue(s)
        self.assertEqual(r, Response(1, 'attention', 'vector16', 'add', (0,), (0,)))
        out = s.tick(ack=r.packet, offer=Offer('attention', (1,)), feed_ready=True)
        self.assertTrue(out['ack_fire'])
        self.assertTrue(out['publish'])
        self.assertFalse(out['offer_fire'])
        self.assertEqual(s.indices, {0: 1, 1: 0})
        self.assertTrue(s.tick(offer=Offer('attention', (1,)), feed_ready=True)['offer_fire'])
        self.assertEqual(s.accepted, 2)
        self.assertEqual(s.retired, 1)

    def test_exact_scalar_spacing(self):
        for opcode, spacing in [('add', 3), ('exp', 3), ('exp', 20), ('div', 9)]:
            with self.subTest(opcode=opcode, spacing=spacing):
                s = self.make(Operation('sfu16', opcode, spacing))
                s.tick(acquire='attention')
                acceptance_cycle = s.cycle
                self.assertTrue(s.tick(offer=Offer('attention', (0,)), feed_ready=True)['offer_fire'])
                packet = s.pending[0].packet
                for _ in range(spacing - 2):
                    out = s.tick(ack=packet)
                    self.assertIsNone(out['response'])
                    self.assertFalse(out['ack_fire'])
                self.assertTrue(s.tick(ack=packet)['ack_fire'])
                self.assertEqual(s.cycle - acceptance_cycle, spacing)
                self.assertTrue(s.tick(offer=Offer('attention', (0,)), feed_ready=True)['offer_fire'])

    def test_full_exp_slow_lane_barrier(self):
        s = Schedule({0: (Operation('sfu16', 'exp', 3),),
                      1: (Operation('sfu16', 'exp', 20),)})
        r = self.issue(s, lanes=(0, 1))
        for _ in range(18):
            out = s.tick(ack=r.packet, offer=Offer('attention', (0,)), feed_ready=True)
            self.assertIsNone(out['response'])
            self.assertFalse(out['offer_fire'])
            self.assertFalse(out['ack_fire'])
            self.assertEqual(s.indices, {0: 0, 1: 0})
        out = s.tick(ack=r.packet)
        self.assertEqual(out['response'].lanes, (0, 1))
        self.assertTrue(out['publish'])
        self.assertEqual(s.indices, {0: 1, 1: 1})

    def test_global_owner_exclusive_across_pools(self):
        for owner in OWNERS:
            for rival in OWNERS:
                if owner == rival:
                    continue
                with self.subTest(owner=owner, rival=rival):
                    s = Schedule({0: (Operation('vector16', 'add', 2),),
                                  1: (Operation('sfu16', 'exp', 20),)})
                    s.tick(acquire=owner)
                    out = s.tick(acquire=rival, offer=Offer(rival, (1,)), feed_ready=True)
                    self.assertFalse(out['acquire_fire'])
                    self.assertFalse(out['offer_fire'])
                    self.assertEqual(s.owner, owner)
                    s.tick(offer=Offer(owner, (0,)), feed_ready=True)
                    out = s.tick(offer=Offer(owner, (1,)), feed_ready=True)
                    self.assertFalse(out['offer_fire'])
                    self.assertEqual(s.pending[0].pool, 'vector16')

    def test_release_edge_no_same_edge_reuse(self):
        s = self.make()
        s.tick(acquire='attention')
        out = s.tick(release='attention', acquire='dense',
                     offer=Offer('attention', (0,)), feed_ready=True)
        self.assertTrue(out['release_fire'])
        self.assertFalse(out['acquire_fire'])
        self.assertFalse(out['offer_fire'])
        self.assertIsNone(s.owner)
        out = s.tick(acquire='dense', offer=Offer('dense', (0,)), feed_ready=True)
        self.assertTrue(out['acquire_fire'])
        self.assertFalse(out['offer_fire'])
        self.assertTrue(s.tick(offer=Offer('dense', (0,)), feed_ready=True)['offer_fire'])

    def test_feed_stall_and_wrong_release(self):
        s = self.make()
        s.tick(acquire='attention')
        for _ in range(3):
            out = s.tick(offer=Offer('attention', (0,)), release='dense')
            self.assertFalse(out['offer_fire'])
            self.assertFalse(out['release_fire'])
        out = s.tick(offer=Offer('attention', (0,)), feed_ready=False)
        self.assertFalse(out['offer_fire'])
        self.assertEqual((s.accepted, s.serial, s.indices[0]), (0, 0, 0))
        self.assertTrue(s.tick(offer=Offer('attention', (0,)), feed_ready=True)['offer_fire'])

    def test_response_held_and_matching_ack_only(self):
        s = self.make()
        r = self.issue(s, lanes=(1, 0))
        with self.assertRaises(FrozenInstanceError):
            r.owner = 'dense'
        for ack in (None, 0, r.packet + 1, None):
            out = s.tick(ack=ack, release='attention')
            self.assertIs(out['response'], r)
            self.assertFalse(out['ack_fire'])
            self.assertFalse(out['publish'])
            self.assertFalse(out['release_fire'])
            self.assertEqual(out['debt'], 1)
            self.assertEqual(s.indices, {0: 0, 1: 0})
        out = s.tick(ack=r.packet, release='attention')
        self.assertTrue(out['ack_fire'])
        self.assertFalse(out['release_fire'])
        self.assertTrue(s.tick(release='attention')['release_fire'])
        self.assertFalse(s.tick(ack=r.packet)['publish'])

    def test_fault_preserves_debt_and_suppresses_publish(self):
        for control in ('abort', 'soft_reset'):
            for simultaneous_ack in (False, True):
                with self.subTest(control=control, simultaneous_ack=simultaneous_ack):
                    s = self.make()
                    r = self.issue(s)
                    out = s.tick(**{control: True}, ack=r.packet if simultaneous_ack else None)
                    self.assertTrue(out['reset_required'])
                    self.assertFalse(out['publish'])
                    self.assertEqual(out['debt'], 0 if simultaneous_ack else 1)
                    if not simultaneous_ack:
                        self.assertEqual(s.indices[0], 0)
                        self.assertIs(s.tick()['response'], r)
                        out = s.tick(ack=r.packet)
                        self.assertTrue(out['ack_fire'])
                        self.assertFalse(out['publish'])
                    self.assertEqual(s.indices[0], 1)
                    self.assertEqual((s.accepted, s.retired), (1, 1))
                    self.assertFalse(s.tick(offer=Offer('attention', (0,)), feed_ready=True)['offer_fire'])
                    self.assertTrue(s.tick(release='attention')['release_fire'])
                    self.assertFalse(s.tick(acquire='dense')['acquire_fire'])
                    self.assertTrue(s.poison)

    def test_early_fault_and_ack_cannot_erase_debt(self):
        s = self.make(Operation('sfu16', 'exp', 20))
        r = self.issue(s)
        out = s.tick(abort=True, ack=r.packet, release='attention')
        self.assertFalse(out['ack_fire'])
        self.assertFalse(out['release_fire'])
        self.assertEqual(out['debt'], 1)
        for _ in range(17):
            self.assertFalse(s.tick(ack=r.packet)['ack_fire'])
        out = s.tick(ack=r.packet)
        self.assertTrue(out['ack_fire'])
        self.assertFalse(out['publish'])

    def test_dependency_order_and_completed_chain_rejected(self):
        s = Schedule({0: fold_plan()})
        s.tick(acquire='attention')
        for index, op in enumerate(fold_plan()):
            self.assertTrue(s.tick(offer=Offer('attention', (0,)), feed_ready=True)['offer_fire'])
            r = s.pending[0]
            self.assertEqual((r.indices, r.opcode), ((index,), op.opcode))
            self.assertTrue(s.tick(ack=r.packet)['publish'])
        with self.assertRaises(ValueError):
            s.tick(offer=Offer('attention', (0,)), feed_ready=True)

    def test_six_head_softmax_order_through_causal_boundaries(self):
        # No arithmetic: replay every ordered primitive and delayed ACK.
        for keys in (1, 2, 16, 17, 128):
            plans = {head: softmax_plan(keys, 11, tuple(k == head % keys for k in range(keys))) for head in range(6)}
            schedule = Schedule(plans)
            schedule.tick(acquire='attention')
            expected = len(plans[0])
            for index in range(expected):
                self.assertTrue(schedule.tick(offer=Offer('attention', tuple(range(6))), feed_ready=True)['offer_fire'])
                response, due = schedule.pending
                self.assertEqual(response.indices, (index,) * 6)
                self.assertEqual(response.opcode, plans[0][index].opcode)
                while schedule.cycle < due:
                    self.assertFalse(schedule.tick(ack=response.packet)['ack_fire'])
                # Hold one extra edge, including at each division/normalization.
                self.assertEqual(schedule.tick()['response'], response)
                self.assertTrue(schedule.tick(ack=response.packet)['publish'])
            self.assertEqual(schedule.indices, {head: expected for head in range(6)})
            self.assertEqual((schedule.accepted, schedule.retired), (expected, expected))

    def test_mixed_lockstep_opcode_or_pool_rejected(self):
        for other in (Operation('vector16', 'mul', 2), Operation('sfu16', 'add', 3)):
            s = Schedule({0: (Operation('vector16', 'add', 2),), 1: (other,)})
            s.tick(acquire='attention')
            with self.assertRaises(ValueError):
                s.tick(offer=Offer('attention', (0, 1)), feed_ready=True)
            self.assertEqual(s.accepted, 0)
            self.assertIsNone(s.pending)

    def test_typed_inventory_and_control_negatives(self):
        op = Operation('vector16', 'add', 2)
        for plans in ({}, [], {True: (op,)}, {16: (op,)}, {0: []}, {0: ()},
                      {0: (object(),)}, {0: (op,) * 1025}):
            with self.subTest(plans_type=type(plans).__name__), self.assertRaises(ValueError):
                Schedule(plans)
        bad = [dict(feed_ready=1), dict(abort=0), dict(soft_reset=None),
               dict(ack=True), dict(ack=-1), dict(ack=1.0), dict(acquire='bad'),
               dict(release=1), dict(offer=('attention', (0,))),
               dict(offer=Offer('bad', (0,))), dict(offer=Offer('attention', [0])),
               dict(offer=Offer('attention', ())), dict(offer=Offer('attention', (True,))),
               dict(offer=Offer('attention', (2,))), dict(offer=Offer('attention', (0, 0)))]
        for kwargs in bad:
            s = self.make()
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                s.tick(**kwargs)
            self.assertEqual(s.cycle, 0)
            self.assertIsNone(s.owner)


class Counts(unittest.TestCase):
    def test_frozen_source_resources(self):
        from candidates.qwen2_resident_matrix.attention_scalar_schedule.check_sources import check
        result = check()
        self.assertEqual(result['source_count'], 7)
        self.assertIs(result['rtl_executed'], False)

    def test_m128_exact_counts_and_explicit_nonclaims(self):
        w = workload(128)
        expected = dict(tokens=128, qk_fold_adds=1585152,
                        qk_vector_fold_packets=110592, qk_vector_scale_packets=6912,
                        softmax_subtractions=99072, softmax_ordered_sum_adds=99072,
                        softmax_exp=99072, softmax_divisions=1536,
                        softmax_normalizations=99072, silu_elements=1146880,
                        silu_vectors=71680, silu_lane_operations=6881280,
                        silu_divisions=1146880,
                        silu_service_floor_excluding_division=1075200,
                        silu_all_full_exp_service_excluding_division=2293760)
        for key, value in expected.items():
            self.assertEqual(w[key], value, key)
        self.assertIsNone(w['actual_hardware_cycles'])
        for key in ('accepted_80', 'accepted_90', 'bank_feasibility_proven', 'implemented_borrower'):
            self.assertIs(w[key], False)

    def test_workload_boundary_and_typed_negatives(self):
        self.assertEqual(workload(1)['silu_vectors'], 560)
        self.assertEqual(workload(1)['softmax_exp'], 12)
        for value in (0, 129, True, 1.0, '128', None):
            with self.assertRaises(ValueError):
                workload(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
