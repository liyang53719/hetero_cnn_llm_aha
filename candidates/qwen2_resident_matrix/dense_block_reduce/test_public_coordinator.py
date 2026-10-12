"""Bounded public coordinator protocol gates; no RTL or full-shape replay.

Injected terminals test controller decisions, separately from the coupled
small physical-bank/DMA transport cases. The latter use opaque Matrix payloads
from the existing protocol harness, real accepted steps, the actual shared Add
loan, and the actual DDR drain. They make no Matrix numerical acceptance claim.
"""
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import re
import unittest

from .public_coordinator import (DenseReductionCoordinator, DenseReductionRequest,
                                 Services, RESET_DOMAIN)
from .dense_drain import DenseReductionOwner, Job, drain
from .k_window_model import KWindowResult
from .sum_tiles import TileSumController, shared_loan_edge
from .vector_add_model import VectorLoanModel
from .test_k_window import Harness as WindowHarness
from ..ffn_drain.test_model import Harness as DrainHarness


def request(n=192, k=192, split=128, rows=16):
    return DenseReductionRequest(Job(m=rows, k=k, n=n, tag=13, a=0x100000,
        b=0x400000, dst=0x4000000, activation_bf16=False, weight_bf16=True,
        write_bytes=rows*n*4), 7, ((0, split), (split, k)), True)


def window_result(q, useful=17, executed=31, **changes):
    r = KWindowResult(q.job.tag, q.identity, q.ng, q.slot, q.job.m, q.cols,
        None, True, q.job.m//16*q.cols, k_begin=q.k_begin, k_end=q.k_end,
        block_id=q.block_id, pair_reverse=q.pair_reverse,
        useful_macs=useful, executed_macs=executed)
    return replace(r, **changes)


def drain_result(q, **changes):
    return replace(drain.FfnDrainResult(q.job.tag, q.identity, q.ng, q.job.m, q.cols,
        None, True, q.job.m//16*q.cols, q.job.m*q.cols*4, 19), **changes)


class PublicCoordinatorTests(unittest.TestCase):
    def start(self, q=None):
        c = DenseReductionCoordinator()
        self.assertTrue(c.tick(request=q or request())["request_fire"])
        self.assertEqual(c.state, "partialFlush")
        c.tick()
        return c

    def partial(self, c, **changes):
        q = c.ports()["window_request"]
        self.assertIsNotNone(q)
        self.assertTrue(c.tick()["window_fire"])
        r = window_result(q, **changes)
        e = c.tick(window_result=r, services=Services(window_busy=True, lease_valid=True, tiles_leased=True))
        self.assertTrue(e["window_result_fire"])
        return q, r

    def full_window(self, c):
        a, _ = self.partial(c)
        c.tick()
        b, _ = self.partial(c)
        self.assertEqual((a.slot, b.slot, a.job.n, b.job.k), (0, 1, c.call.job.n, c.call.job.k))
        self.assertTrue(c.tick(services=Services(lease_valid=True, tiles_leased=True))["sum_fire"])
        c.tick(sum_complete=True, services=Services(sum_busy=True, lease_valid=True, tiles_leased=True))
        self.assertEqual(c.state, "drainFlush")
        c.tick()
        q = c.ports()["drain_request"]
        self.assertTrue(c.tick()["drain_fire"])
        c.tick(drain_result=drain_result(q), services=Services(drain_busy=True, lease_valid=True))
        return q

    def success(self):
        c = self.start(request(n=32, k=32, split=16))
        self.full_window(c)
        c.tick(services=Services(lease_valid=True))
        self.assertEqual(c.state, "retire")
        c.tick()
        self.assertEqual(c.state, "reply")
        return c

    def test_full_job_snapshot_variable_tail_and_terminal_credit_only(self):
        q = request()
        c = self.start(q)
        self.assertEqual(c.call, q)
        self.assertIsNot(c.call, q)
        self.assertIsNot(c.call.job, q.job)
        first = self.full_window(c)
        self.assertEqual((first.ng, first.cols, c.ng), (0, 160, 160))
        self.assertEqual(c.write_bytes, 16*160*4)
        c.tick()
        tail = self.full_window(c)
        self.assertEqual((tail.ng, tail.cols), (160, 32))
        self.assertEqual(c.useful, 4*17)  # deliberately not a shape-derived count
        self.assertEqual(c.executed, 4*31)
        self.assertIsNone(c.ports()["result"])
        self.assertTrue(c.ports()["invalidate_lease"])
        c.tick(services=Services(lease_valid=True))
        for fence in (Services(lease_valid=True), Services(matrix_drained=False),
                      Services(dma_drained=False), Services(tiles_leased=True),
                      Services(tiles_drained=False), Services(vector_drained=False),
                      Services(sum_busy=True)):
            c.tick(services=fence)
            self.assertIsNone(c.ports()["result"])
        c.tick()
        r = c.ports()["result"]
        self.assertEqual((r.tag, r.status, r.write_bytes), (q.job.tag, None, q.job.write_bytes))
        self.assertEqual((r.useful_macs, r.executed_macs), (68, 124))
        self.assertIsNone(r.cycles)
        self.assertGreater(r.model_ticks, 0)
        for _ in range(9):
            e = c.tick(request=q)
            self.assertEqual(e["result"], r)
            self.assertFalse(e["request_fire"])
        self.assertTrue(c.tick(result_ready=True)["result_fire"])
        self.assertTrue(c.ports()["request_ready"])

    def test_bad_full_job_profile_rejected_before_any_backend_issue(self):
        good = request()
        bad = [replace(good, identity=0), replace(good, pair_reverse=1),
               replace(good, k_ranges=((0, 64), (66, 192))),
               replace(good, k_ranges=((0, 96), (96, 190))),
               replace(good, k_ranges=((0, 95), (95, 192))),
               replace(good, k_ranges=((0, 64), (64, 128), (128, 192))),
               replace(good, k_ranges=[(0, 128), (128, 192)]),
               replace(good, job=replace(good.job, write_bytes=64)),
               replace(good, job=replace(good.job, materialize_dense_output=True)),
               replace(good, job=replace(good.job, dst=good.job.b+64))]
        for q in bad:
            c = DenseReductionCoordinator()
            self.assertTrue(c.tick(request=q)["request_fire"])
            self.assertEqual(c.state, "draining")
            c.tick()
            r = c.ports()["result"]
            self.assertEqual((r.status, r.write_bytes, r.useful_macs), ("Malformed", 0, 0))
            c.tick(result_ready=True)
            self.assertFalse(c.tick(request=good)["request_fire"])

    def test_parameterized_even_ranges_not_fixed_1024_policy(self):
        for k, split in ((32, 2), (128, 126), (1536, 512), (1536, 1024)):
            c = self.start(request(n=32, k=k, split=split))
            q, _ = self.partial(c)
            self.assertEqual((q.k_begin, q.k_end), (0, split))
            c.tick()
            q, _ = self.partial(c)
            self.assertEqual((q.k_begin, q.k_end), (split, k))

    def test_request_backpressure_holds_and_sum_waits_for_physical_grant(self):
        c = self.start()
        q = c.ports()["window_request"]
        for _ in range(8):
            self.assertFalse(c.tick(window_ready=False)["window_fire"])
            self.assertEqual(c.ports()["window_request"], q)
        self.partial(c)
        c.tick()
        self.partial(c)
        for fence in (Services(window_busy=True), Services(drain_busy=True),
                      Services(matrix_drained=False), Services(dma_drained=False)):
            e = c.tick(services=fence)
            self.assertFalse(e["sum_fire"])
            self.assertFalse(e["sum_bank_granted"])
        call = c.ports()["sum_request"]
        for _ in range(6):
            self.assertFalse(c.tick(sum_ready=False)["sum_fire"])
            self.assertEqual(c.ports()["sum_request"], call)
        self.assertTrue(c.tick()["sum_fire"])

    def test_fault_waits_for_terminal_and_each_accepted_backend_obligation(self):
        c = self.start(request(n=32, k=32, split=16))
        q = c.ports()["window_request"]
        c.tick()
        busy = Services(window_busy=True, matrix_drained=False, dma_drained=False)
        c.tick(abort=True, services=busy)
        for _ in range(7):
            c.tick(services=busy)
            self.assertIsNone(c.ports()["result"])
        c.tick(window_result=window_result(q, committed=False, status="DMA failure", produced_beats=0),
               services=busy)
        self.assertFalse(c.window_pending)
        for fence in (Services(matrix_drained=False), Services(dma_drained=False),
                      Services(tiles_drained=False), Services(vector_drained=False), Services(sum_busy=True)):
            c.tick(services=fence)
            self.assertIsNone(c.ports()["result"])
        c.tick(services=Services(tiles_leased=True))  # poisoned lease stays quarantined
        self.assertIsNotNone(c.ports()["result"].status)
        self.assertEqual(c.ports()["result"].write_bytes, 0)
        c.tick(result_ready=True)
        self.assertEqual(c.state, "locked")

    def test_metadata_or_counter_mismatch_poison_cannot_publish_success(self):
        for changes in ({"block_id": 2}, {"k_end": 30}, {"pair_reverse": False},
                        {"ng": 32}, {"ddr_write_bytes": 64}, {"useful_macs": -1}):
            c = self.start(request(n=32, k=32, split=16))
            self.partial(c, **changes)
            c.tick()
            self.assertEqual(c.ports()["result"].status, "Protocol")
            self.assertEqual(c.write_bytes, 0)

    def test_abort_held_success_fences_current_acceptance_without_payload_mutation(self):
        c = self.success()
        held = c.ports()["result"]
        e = c.tick(abort=True, result_ready=True)
        self.assertEqual(e["result"], held)
        self.assertTrue(e["reset_required"])
        self.assertTrue(e["result_fire"])
        self.assertEqual(c.state, "locked")
        self.assertFalse(c.ports()["request_ready"])

    def test_current_service_fault_fences_then_registered_poison_cancels(self):
        c = self.start()
        fault = Services(drain_reset=True)
        p = c.ports(fault)
        self.assertTrue(p["reset_required"])
        self.assertIsNone(p["window_request"])
        self.assertFalse(p["backend_abort"])
        e = c.tick(services=fault)
        self.assertFalse(e["window_fire"])
        self.assertFalse(e["backend_abort"])
        self.assertTrue(c.poison)
        self.assertTrue(c.ports()["backend_abort"])
        # Independent external abort remains immediate, before a clock edge.
        self.assertTrue(DenseReductionCoordinator().ports(abort=True)["backend_abort"])

    def test_service_fault_fences_held_success_before_cancel_registers(self):
        c = self.success()
        held = c.ports()["result"]
        e = c.tick(services=Services(drain_reset=True), result_ready=True)
        self.assertEqual(e["result"], held)
        self.assertTrue(e["reset_required"])
        self.assertFalse(e["backend_abort"])
        self.assertEqual(c.state, "locked")
        self.assertTrue(c.ports()["backend_abort"])

    def test_abort_wiring_static_feedback_audit_rejects_old_equation(self):
        here = Path(__file__).resolve().parent
        source = (here / "DenseBlockReductionCoordinator.scala").read_text()
        retained = (here.parent / "ffn_drain" / "drain.patch").read_text()
        # Bind the hazard to the retained owner, not an invented backend model.
        self.assertIn("d.resetRequired:=io.resetRequired", retained)
        owner_reset = next(line for line in retained.splitlines()
                           if "io.resetRequired:=" in line and "d.abort" in line)
        self.assertIn("io.tiles.get.abort", owner_reset)
        nodes = ("cancel", "bad", "serviceError", "io.backendAbort", "io.drain.abort",
                 "bridge.io.abort", "io.drain.resetRequired", "owner.resetRequired",
                 "owner.tiles.abort")
        graph = {}
        for name in ("cancel", "bad", "serviceError"):
            expr = re.search(r"val " + name + r"=(.*?)(?=\n\s*(?:val|io\.|//))", source, re.S)
            self.assertIsNotNone(expr, name)
            graph[name] = {n for n in nodes if re.search(r"(?<![\w.])" + re.escape(n) + r"(?![\w.])", expr[1])}
        for name in ("io.backendAbort", "io.drain.abort", "bridge.io.abort"):
            expr = re.search(re.escape(name) + r":=([^;\n]+)", source)
            self.assertIsNotNone(expr, name)
            graph[name] = {n for n in nodes if re.search(r"(?<![\w.])" + re.escape(n) + r"(?![\w.])", expr[1])}
        graph["io.drain.resetRequired"] = {"owner.resetRequired"}
        graph["owner.resetRequired"] = {"io.drain.abort", "owner.tiles.abort"}
        graph["owner.tiles.abort"] = {"bridge.io.abort"}
        def cyclic(edges):
            def visit(node, active, done):
                if node in active:
                    return True
                if node in done:
                    return False
                active.add(node)
                if any(visit(n, active, done) for n in edges.get(node, ())):
                    return True
                active.remove(node)
                done.add(node)
                return False
            done = set()
            return any(visit(n, set(), done) for n in edges)
        self.assertFalse(cyclic(graph), graph)
        self.assertEqual(graph["cancel"], set())  # only external input / register
        for endpoint in ("io.backendAbort", "io.drain.abort", "bridge.io.abort"):
            self.assertEqual(graph[endpoint], {"cancel"})
        old = {n: set(edges) for n, edges in graph.items()}
        old["io.drain.abort"] = {"bad"}
        old["bridge.io.abort"] = {"bad"}
        self.assertTrue(cyclic(old), "audit must reject the original combinational feedback")

    def test_unsolicited_terminal_fences_held_success_on_same_edge(self):
        c = self.success()
        held = c.ports()["result"]
        e = c.tick(window_result=SimpleNamespace(), result_ready=True)
        self.assertEqual(e["result"], held)
        self.assertTrue(e["reset_required"])
        self.assertEqual(c.state, "locked")

    def test_abort_after_success_accepted_never_retracts_prior_completion(self):
        c = self.success()
        accepted = c.tick(result_ready=True)
        self.assertTrue(accepted["result_fire"])
        self.assertFalse(accepted["reset_required"])
        c.tick(abort=True)
        self.assertIsNone(c.ports()["result"])
        self.assertIsNone(accepted["result"].status)

    def test_reset_requires_entire_backend_domain_and_local_reset_only_poisons(self):
        c = self.start()
        with self.assertRaises(ValueError):
            c.tick(coordinated_reset={"coordinator"})
        c.tick(local_reset=True)
        self.assertTrue(c.poison)
        c.tick()
        c.tick(result_ready=True)
        self.assertFalse(c.ports()["request_ready"])
        c.tick(coordinated_reset=RESET_DOMAIN)
        self.assertTrue(c.ports()["request_ready"])
        self.assertEqual((c.write_bytes, c.useful, c.executed), (0, 0, 0))


class Coupled:
    """One bank edge per call, including the exclusive shared-vector interval."""
    def __init__(self, q):
        self.call = q
        self.c = DenseReductionCoordinator()
        self.owner = DenseReductionOwner(drain.PrefixWorkspace(0x10000000, 786432, 11),
            enable_dense_drain=True, enable_k_window=True, enable_ffn_drain=True,
            enable_ffn_window=True, enable_ffn_tiles=True)
        self.window = WindowHarness(instance=self.owner)
        self.sum = TileSumController(self.owner.tiles)
        self.loan = VectorLoanModel(lane_latency=2)
        self.output = None
        self.outputs, self.partials, self.drains, self.memory = [], [], [], {}
        self.started = False
        self.edge = None

    def services(self):
        o = self.owner
        return Services(window_busy=o.window_request is not None and o.state not in ("idle", "locked"),
            drain_busy=o.drain_request is not None and o.state not in ("idle", "locked"),
            tiles_drained=o.tiles.idle, tiles_leased=o.tiles.leased,
            vector_drained=self.loan.ports()["drained"], sum_busy=self.sum.busy,
            lease_valid=o.lease is not None,
            matrix_drained=not o.group_started or o.group_done,
            dma_drained=o.read_active is None and o.accepted_write is None,
            window_reset=bool(o.ports()["reset_required"]),
            tiles_reset=o.tiles.poison, sum_reset=self.sum.poison,
            vector_reset=self.loan.ports()["reset_required"])

    def tick(self, *, hold_ack=False, hold_read=False, ack_error=False, abort=False, result_ready=False, stall=False):
        services = self.services()
        cp = self.c.ports(services, abort=abort)
        op = self.owner.ports()
        args = dict(abort=cp["backend_abort"], invalidate_lease=cp["invalidate_lease"])
        sum_edge = {}
        if self.c.state in ("sumIssue", "sumWait") or self.sum.busy:
            sum_edge = shared_loan_edge(self.sum, self.loan, start=cp["sum_request"],
                abort=cp["backend_abort"], bank_ready=cp["sum_bank_granted"] and not stall)
            oe = {}
        elif cp["window_request"] is not None and op["window_ready"]:
            oe = self.window.submit(cp["window_request"], **args)
        elif self.owner.window_request is not None and self.owner.state != "locked":
            oe = self.window.cycle(dma=not hold_read, window_result_ready=cp["window_result_ready"],
                read_command_ready=not stall, **({"step_ready": False} if stall else {}), **args)
        elif cp["drain_request"] is not None and op["drain_ready"]:
            self.output = DrainHarness(cp["drain_request"], self.owner, seed=False)
            self.outputs.append(self.output)
            oe = self.output.submit(**args)
        elif self.owner.drain_request is not None and self.owner.state != "locked":
            if ack_error and self.output.ack is not None:
                args["write_ack"] = replace(self.output.ack, error=True)
            oe = self.output.cycle(ack=not hold_ack, drain_result_ready=cp["drain_result_ready"],
                write_command_ready=not stall, write_data_ready=not stall, **args)
        else:
            oe = self.owner.tick(**args)
        ce = self.c.tick(request=self.call if not self.started else None,
            services=services, abort=abort, window_ready=bool(oe.get("window_fire")),
            drain_ready=bool(oe.get("drain_fire")), sum_ready=bool(sum_edge.get("start_fire")),
            window_result=op.get("window_result"), drain_result=op.get("drain_result"),
            sum_complete=bool(sum_edge.get("complete")), result_ready=result_ready)
        self.started |= ce["request_fire"]
        assert ce["window_fire"] == bool(oe.get("window_fire"))
        assert ce["window_result_fire"] == bool(oe.get("window_result_fire"))
        assert ce["drain_fire"] == bool(oe.get("drain_fire"))
        assert ce["drain_result_fire"] == bool(oe.get("drain_result_fire"))
        assert ce["sum_fire"] == bool(sum_edge.get("start_fire"))
        if ce["window_result_fire"]:
            self.partials.append(op["window_result"])
        if ce["drain_result_fire"]:
            self.drains.append(op["drain_result"])
            self.memory.update(self.output.memory)
        self.edge = oe
        return ce

    def until(self, predicate, **kwargs):
        for i in range(30000):
            if predicate():
                return
            self.tick(stall=i % 17 == 0, **kwargs)
        raise AssertionError(("bounded protocol watchdog", self.c.state, self.owner.state, self.owner.error))


class CoupledPhysicalTests(unittest.TestCase):
    def test_real_banks_two_n_windows_last_ack_then_lease_invalidate(self):
        h = Coupled(request())
        physical = h.owner.a_banks
        h.until(lambda: h.output is not None and h.output.q.ng == 160 and
            h.output.ack is not None and len(h.output.memory)*4 == 16*32*4)
        before = h.c.write_bytes
        self.assertEqual(before, 16*160*4)
        for _ in range(13):
            self.assertFalse(h.tick(hold_ack=True)["result_fire"])
            self.assertIsNone(h.c.ports()["result"])
            self.assertEqual(h.c.write_bytes, before)
            self.assertTrue(h.owner.tiles.tags[2].live)
        h.until(lambda: h.c.state == "reply")
        r = h.c.ports()["result"]
        self.assertIsNone(r.status)
        self.assertEqual(r.write_bytes, h.call.job.write_bytes)
        self.assertEqual(r.useful_macs, sum(r.useful_macs for r in h.partials))
        self.assertEqual(r.executed_macs, sum(r.executed_macs for r in h.partials))
        self.assertEqual(r.useful_macs, len(h.window.steps)*16*32)
        self.assertEqual(r.executed_macs, len(h.window.steps)*4096)
        self.assertEqual(h.owner.k_a_fences, 1)
        self.assertIsNone(h.owner.lease)
        self.assertFalse(h.owner.tiles.leased)
        self.assertIs(physical, h.owner.a_banks)
        self.assertIs(physical, h.owner.tiles.banks)
        self.assertEqual(set(h.memory), {h.call.job.dst+4*i for i in range(16*192)})
        self.assertEqual(len(h.partials), 4)
        self.assertEqual(len(h.drains), 2)
        self.assertTrue(h.tick(result_ready=True)["result_fire"])
        self.assertTrue(h.c.ports(h.services())["request_ready"])

    def test_abort_cannot_discard_accepted_dma_read(self):
        h = Coupled(request(n=32, k=32, split=16))
        h.until(lambda: h.window.read is not None)
        pending = h.window.read
        h.tick(abort=True, hold_read=True)
        for _ in range(7):
            h.tick(hold_read=True)
            self.assertEqual(h.window.read, pending)
            self.assertIsNone(h.c.ports()["result"])
            self.assertTrue(h.c.window_pending)
        h.until(lambda: h.c.state == "reply")
        self.assertIsNone(h.window.read)
        self.assertFalse(h.c.window_pending)
        self.assertIsNotNone(h.c.ports()["result"].status)
        self.assertEqual(h.c.ports()["result"].write_bytes, 0)

    def test_abort_drains_actual_accepted_vector_lanes_before_failed_terminal(self):
        h = Coupled(request(n=32, k=32, split=16))
        h.until(lambda: h.loan.active and h.loan.state == "wait")
        h.tick(abort=True)
        self.assertFalse(h.loan.ports()["drained"])
        self.assertIsNone(h.c.ports()["result"])
        h.until(lambda: h.c.state == "reply")
        self.assertTrue(h.loan.ports()["drained"])
        self.assertFalse(h.sum.busy)
        self.assertEqual(h.loan.published, [])
        self.assertIsNotNone(h.c.ports()["result"].status)
        self.assertEqual(h.c.ports()["result"].write_bytes, 0)

    def test_abort_waits_for_real_last_ack_and_counts_it_without_committing(self):
        h = Coupled(request(n=32, k=32, split=16))
        h.until(lambda: h.output is not None and h.output.ack is not None and
                        len(h.output.memory)*4 == h.call.job.write_bytes)
        h.tick(abort=True, hold_ack=True)
        for _ in range(7):
            h.tick(hold_ack=True)
            self.assertIsNone(h.c.ports()["result"])
            self.assertIsNotNone(h.owner.accepted_write)
        h.until(lambda: h.c.state == "reply")
        self.assertIsNone(h.owner.accepted_write)
        self.assertIsNotNone(h.c.ports()["result"].status)
        self.assertEqual(h.c.ports()["result"].write_bytes, h.call.job.write_bytes)
        self.assertFalse(h.drains[-1].committed)

    def test_real_final_ack_error_counts_prior_acks_and_poison_blocks_next_job(self):
        h = Coupled(request(n=32, k=32, split=16))
        h.until(lambda: h.output is not None and h.output.ack is not None and
                        len(h.output.memory)*4 == h.call.job.write_bytes)
        before = h.owner.write_bytes
        self.assertLess(before, h.call.job.write_bytes)
        h.tick(ack_error=True)
        h.until(lambda: h.c.state == "reply")
        r = h.c.ports()["result"]
        self.assertIsNotNone(r.status)
        self.assertEqual(r.write_bytes, before)
        self.assertTrue(h.owner.tiles.tags[2].live)
        h.tick(result_ready=True)
        self.assertFalse(h.c.ports(h.services())["request_ready"])


if __name__ == "__main__":
    unittest.main()
