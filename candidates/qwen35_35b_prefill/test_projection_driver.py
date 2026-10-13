"""Actual shared Matrix/Vector/DDR transactions for the explicit K2048 lease.

Synthetic arithmetic profiles only. No official 35B input, policy or block
acceptance is implied. Existing receipt-bound libraries are required.
"""
import time
import json
import unittest
from dataclasses import replace

from ..qwen35_gdn_prefill import test_projection_driver as old
from ..qwen35_gdn_prefill import typed_dense as t
from ..qwen35_gdn_prefill.dense_prefix import TypedSeededDenseDriver
from ..qwen35_gdn_prefill.chunk.vector import Vector16, IEEE_POLICY
from . import projection_owner as p
from .projection_driver import TypedLargeKProjectionDriver
from .partial_tiles import resource_ledger
from .sum_tiles import shared_loan_edge


def setUpModule():
    old.setUpModule()


class LargeKProjectionTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(old.LIB.td_reset(), 0)
        self.matrix = t.MatrixService(old.LIB)
        self.vector = Vector16(old.VECTOR_PATH, exception_policy=IEEE_POLICY)
        self.owner = p.LargeKProjectionOwner(p.PrefixWorkspace(0x9000000, 16384, 1, 128))
        self.memory = t.TypedMemory()

    def prepare(self, n=32, k=32, m=16, tag=41,
                a=0x100000, b=0x400000, dst=0x2000000):
        if a not in self.memory.regions:
            self.memory.add_readonly(a, old.values(m*k))
        self.memory.add_readonly(b, old.values(k*n, 2))
        self.memory.allocate_output(dst, m*n*2)
        return t.down.Job(m=m, k=k, n=n, tag=tag, a=a, b=b, dst=dst,
            activation_bf16=True, weight_bf16=True, output_bf16=True,
            write_bytes=m*n*2)

    def driver(self, job):
        profile = replace(old.PROFILE, identity='synthetic_large_k_two_partials',
                          ranges=((0, job.k//2), (job.k//2, job.k)))
        return TypedLargeKProjectionDriver(self.owner, self.matrix, self.memory,
            job, vector=self.vector, profile=profile, sum_identity=job.tag+1000)

    until = old.ProjectionTests.until
    identity = old.ProjectionTests.identity

    def finish(self, driver, hook=None):
        deadline = time.monotonic()+90
        for tick in range(1000000):
            self.assertLess(time.monotonic(), deadline, 'bounded K2048 transaction')
            driver.tick(**({} if hook is None else hook(driver, tick)))
            if driver.response is not None:
                return driver.report()
        self.fail('projection did not retire')

    def check_actual(self, k, n):
        d = self.driver(self.prepare(k=k, n=n))
        identity = self.identity()
        report = self.finish(d, lambda _, i: dict(read_ready=i%3!=0,
            read_response_ready=i%4!=0, step_ready=i%5!=0,
            result_ready=i%7!=0, done_ready=i%3!=0,
            write_ready=i%4!=0, data_ready=i%5!=0, ack_ready=i%6!=0))
        self.assertEqual(d.response, (d.job.tag, None, 16*n*2))
        self.assertEqual(d.output.raw(), old.oracle(d.a.raw(), d.b.raw(),
            16, k, n, d.profile.ranges, True))
        self.assertEqual(report['executed_fmas'], k*(n//32)*4096)
        self.assertEqual(report['vector_add_calls'], n)
        self.assertEqual(report['counts']['ack_bytes'], 16*n*2)
        self.assertEqual(report['a_load_fences'], 1)
        self.assertEqual(report['counts']['a_read_beats'], 16*k//32)
        self.assertEqual(report['resource_ledger'], resource_ledger())
        useful = sum(partial['useful_macs'] for partial in report['partials'])
        self.assertEqual(useful, 16*k*n)
        self.assertEqual(self.identity(), identity)
        self.assertTrue(d.output.published)
        self.assertFalse(self.owner.tiles.leased)
        self.assertIsNone(self.matrix.owner)
        self.assertIsNone(self.vector.client)
        print('K2048_CASE ' + json.dumps(dict(scope='SYNTHETIC_PROJECTION_ONLY',
            shape=dict(m=16,k=k,n=n), numerical_status='PASS_FIXED_RECIPE_BIT_EXACT',
            official_model_acceptance=False, matrix_macs=4096, vector_lanes=16,
            matrix_contexts=5, useful_macs=useful, executed_macs=report['executed_fmas'],
            vector_add_requests=report['vector_add_calls'],
            vector_active_lane_operations=report['vector_add_lanes'],
            software_ticks=report['counts']['ticks'], counts=report['counts'],
            hardware_full_cycles=None, hardware_utilization=None, busy_duty=None,
            active_lane_duty=None, stall_breakdown=None, overlap_timeline=None,
            input_sha256=report['input_sha256'], output_sha256=report['output_sha256'],
            missing_measurement='source-bound full-cycle/timeline or later RTL replay'),sort_keys=True),flush=True)
        return d, report

    def test_tiny_actual_two_partials(self):
        self.check_actual(32, 32)

    def test_actual_n160_five_contexts(self):
        self.check_actual(64, 160)

    def test_actual_full_k2048(self):
        self.check_actual(2048, 32)

    def test_actual_multigroup_n192(self):
        self.check_actual(32, 192)

    test_actual_projection_then_ordinary_then_seeded_down_without_reset = old.ProjectionTests.test_actual_projection_then_ordinary_then_seeded_down_without_reset
    test_abort_held_success_is_failed_once_and_requires_reset = old.ProjectionTests.test_abort_held_success_is_failed_once_and_requires_reset

    def test_abort_after_accepted_sum_rmw_commits_then_poisons(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: self.owner.tiles.pending is not None and
                   self.owner.tiles.pending[0] == 'write' and
                   getattr(self.owner.tiles.pending[1], 'phase', 'partial') == 'sum')
        banks = self.owner.tiles
        _, accepted, word, lane, captured = banks.pending
        commits = banks.counters['rmw_commits']
        d.tick(abort=True)
        self.assertEqual(banks.counters['rmw_commits'], commits+1)
        mask = 0xffffffff << (lane*32)
        for bank in range(16):
            self.assertEqual(banks.banks.words[bank][word],
                (captured[bank] & ~mask) | (accepted.words[bank] << (lane*32)))
        self.finish(d, lambda *_: dict(abort=True))
        self.assertIsNotNone(d.response[1])
        self.assertFalse(d.output.published)
        self.assertTrue(banks.poison)
        self.assertFalse(banks.sum_ready)
        self.assertTrue(banks.idle)
        self.assertIsNone(self.matrix.owner)
        self.assertIsNone(self.vector.client)

    def test_sum_reset_waits_for_accepted_rmw(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: self.owner.tiles.pending is not None and
                   self.owner.tiles.pending[0] == 'write' and
                   getattr(self.owner.tiles.pending[1], 'phase', 'partial') == 'sum')
        banks = self.owner.tiles
        commits = banks.counters['rmw_commits']
        edge = d.sum.tick(coordinated_reset=True, loan_drained=True)
        self.assertFalse(edge['reset'])
        self.assertTrue(edge['reset_rejected'])
        self.assertEqual(banks.counters['rmw_commits'], commits+1)
        self.assertTrue(banks.poison and d.sum.poison)
        self.assertFalse(d.output.published or banks.sum_ready)
        self.finish(d, lambda *_: dict(abort=True))
        self.assertIsNotNone(d.response[1])
        self.owner.tick(coordinated_reset=True)
        self.matrix.reset()
        self.assertTrue(d.sum.tick(coordinated_reset=True, loan_drained=True)['reset'])
        self.assertFalse(banks.poison or d.sum.poison)

    def test_owner_reset_waits_for_accepted_sum_rmw(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: self.owner.tiles.pending is not None and
                   self.owner.tiles.pending[0] == 'write' and
                   getattr(self.owner.tiles.pending[1], 'phase', 'partial') == 'sum')
        banks = self.owner.tiles
        commits = banks.counters['rmw_commits']
        edge = self.owner.tick(coordinated_reset=True)
        self.assertFalse(edge['coordinated_reset'])
        self.assertTrue(edge['reset_rejected'])
        self.assertEqual(banks.counters['rmw_commits'], commits+1)
        self.assertTrue(banks.poison)
        self.assertFalse(banks.sum_ready or d.output.published)
        self.finish(d, lambda *_: dict(abort=True))
        self.assertIsNotNone(d.response[1])
        self.owner.tick(coordinated_reset=True)
        self.matrix.reset()
        self.assertFalse(banks.poison)

    def test_connected_reset_drains_real_vector_held_result_first(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: d.loan.result is not None)
        self.assertTrue(d.sum.inflight)
        self.assertFalse(d.loan.ports()['drained'])
        calls = self.vector.calls['add']
        edge = shared_loan_edge(d.sum, d.loan, coordinated_reset=True)
        self.assertTrue(edge['reset_rejected'])
        self.assertFalse(edge['reset'] or edge['request_fire'] or edge['result_fire'])
        self.assertEqual(self.vector.calls['add'], calls)
        self.assertTrue(d.loan.ports()['drained'])
        self.assertTrue(d.sum.poison and d.loan.poison)
        self.assertFalse(d.output.published)
        self.finish(d, lambda *_: dict(abort=True))
        self.assertIsNotNone(d.response[1])
        self.owner.tick(coordinated_reset=True)
        self.matrix.reset()
        edge = shared_loan_edge(d.sum, d.loan, coordinated_reset=True)
        self.assertTrue(edge['reset'])
        self.assertFalse(d.sum.poison or d.loan.poison)

    def test_old_owner_and_profile_cannot_authorize_new_layout(self):
        j = self.prepare()
        with self.assertRaisesRegex(ValueError, 'exact selected'):
            TypedLargeKProjectionDriver(old.p.GdnProjectionOwner(self.owner.workspace),
                self.matrix, self.memory, j, vector=self.vector,
                profile=old.PROFILE, sum_identity=1041)
        for changed in (replace(j, k=2050), replace(j, output_bf16=False),
                        replace(j, b=j.a)):
            with self.assertRaises(ValueError):
                self.driver(changed)
        self.assertIsNone(self.memory.pending)
        self.assertIsNone(self.matrix.owner)
        self.assertIsNone(self.vector.client)

    def test_malformed_slot_or_job_retires_failure_without_dma(self):
        j = p.Job(**vars(self.prepare()))
        for job, slot in ((j, 2), (replace(j, m=None), 0)):
            with self.subTest(slot=slot, rows=job.m):
                self.owner.tick(coordinated_reset=True)
                q = p.LargeKWindowRequest(job, 41, 0, 32, slot, False,
                    k_begin=0, k_end=16, block_id=1, pair_reverse=True)
                self.owner.tick(window=q)
                r = self.owner.ports()['window_result']
                self.assertIsNotNone(r)
                self.assertIsNotNone(r.status)
                self.assertFalse(r.committed)
                self.assertEqual((r.produced_beats, r.executed_macs, r.ddr_write_bytes), (0,0,0))
                self.assertTrue(self.owner.tick()['window_result_fire'])
                self.assertIsNone(self.matrix.owner)
                self.assertIsNone(self.memory.pending)

    # The same negative driver harness now exercises the selected two-slot
    # owner through real public ACK/result paths, rather than a fake sink.
    test_final_ack_and_held_success_do_not_publish = old.ProjectionTests.test_final_ack_and_held_success_do_not_publish
    test_abort_during_read_matrix_result_sum_and_final_ack_drains = old.ProjectionTests.test_abort_during_read_matrix_result_sum_and_final_ack_drains
    test_failed_real_ack_credits_no_bytes_and_does_not_publish = old.ProjectionTests.test_failed_real_ack_credits_no_bytes_and_does_not_publish
    test_unsolicited_late_result_poison_cannot_accept_held_success = old.ProjectionTests.test_unsolicited_late_result_poison_cannot_accept_held_success


if __name__ == '__main__':
    unittest.main()
