"""Small source-FSM/ledger tests only; no numeric workload, RTL, or EDA run."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from .model import (
    CAPACITIES, COMPLETE_BLOCK_BLOCKERS, SOURCE_PINS, Event, Interval, Ledger,
    Operation, Phase, ScalarRequest, Signal, TimingError, UnboundTimingError,
    exclusive_cycle_buckets, replay_scalar_primitives, verify_sources,
)

REPO = Path(__file__).resolve().parents[2]
ONE, TWO = 0x3f800000, 0x40000000


def request(identity="s0", offered=0, operation="add", a=ONE, b=TWO):
    return ScalarRequest(identity, offered, operation, a, b)


def ledger(end=20, scope="primitive_subset", phases=None, **kwargs):
    return Ledger(repo=REPO, window=Interval(0, end), scope=scope,
                  phases=phases or (Phase("test", Interval(0, end)),), **kwargs)


def scalar(identity="s0", phase="test"):
    return Operation(identity, phase, "scalar", "add", operands=(ONE, TWO))


def matrix(identity="m0", phase="test", context=0, lanes=512, useful=32):
    return Operation(identity, phase, "matrix", "retained_leaf_step",
                     active_lanes=lanes, useful_macs=useful, executed_macs=lanes, context=context)


def add_events(target, op, *, offer=None, start=0, done=2, ack=2, **extra):
    target.register(op)
    edges = dict(request=start if offer is None else offer, start=start, done=done, ack=ack)
    if op.resource == "scalar":
        edges["normal"] = start + 1
    edges.update(extra)
    for kind, cycle in edges.items():
        target.record(Event(cycle, kind, op.identity))


class ScalarReplayTests(unittest.TestCase):
    def test_exact_E0_E1_E2_E3_semantics_for_all_supported_ops(self):
        for operation in ("add", "mul", "mul_ieee_rne"):
            with self.subTest(operation=operation):
                result = replay_scalar_primitives(
                    [request(operation=operation), request("s1", 1, operation)], repo=REPO)
                first = {e.kind: e.cycle for e in result.events if e.transaction == "s0"}
                second = {e.kind: e.cycle for e in result.events if e.transaction == "s1"}
                self.assertEqual(first, dict(request=0, start=0, normal=1, done=2, ack=2))
                self.assertEqual(second, dict(request=1, start=3, normal=4, done=5, ack=5))
                report = result.report()
                self.assertEqual(report["wall_cycles"], 6)
                self.assertEqual(report["scalar_requests"], 2)
                self.assertEqual(report["resource_peak_occupancy"]["scalar_units"], 1)
                self.assertEqual(report["useful_matrix_macs"], 0)
                self.assertEqual(report["executed_matrix_macs"], 0)
                self.assertFalse(report["scalar_ops_are_matrix_macs"])

    def test_held_result_does_not_repeat_operation_and_blocks_reuse(self):
        result = replay_scalar_primitives(
            [request(), request("s1", 1)], repo=REPO,
            result_ready_low=[Interval(2, 7)])
        self.assertEqual([(e.kind, e.cycle) for e in result.events if e.transaction == "s0"],
                         [("request", 0), ("start", 0), ("normal", 1), ("done", 2), ("ack", 7)])
        self.assertEqual(next(e.cycle for e in result.events if e.transaction == "s1" and e.kind == "start"), 8)
        self.assertEqual(result.report()["exclusive_cycle_buckets"]["result_backpressure"], 5)
        self.assertEqual(result.report()["event_count"], 10)

    def test_ready_low_that_ends_at_done_does_not_delay_result(self):
        result = replay_scalar_primitives([request()], repo=REPO, result_ready_low=[Interval(0, 2)])
        self.assertEqual(result.events[-1].cycle, 2)

    def test_adjacent_low_intervals_are_continuous(self):
        result = replay_scalar_primitives([request()], repo=REPO,
                                          result_ready_low=[Interval(2, 4), Interval(4, 7)])
        self.assertEqual(result.events[-1].cycle, 7)

    def test_huge_hold_uses_constant_number_of_records(self):
        duration = 10**12
        result = replay_scalar_primitives([request()], repo=REPO,
                                          result_ready_low=[Interval(2, duration)])
        report = result.report()
        self.assertEqual(report["event_count"], 5)
        self.assertEqual(report["wall_cycles"], duration + 1)
        self.assertEqual(sum(report["exclusive_cycle_buckets"].values()), duration + 1)

    def test_missing_ack_does_not_turn_timeout_into_completion(self):
        with self.assertRaisesRegex(TimingError, "missing result ACK"):
            replay_scalar_primitives([request()], repo=REPO,
                                     result_ready_low=[Interval(2, 100)], stop_cycle=20)

    def test_exp_softplus_div_sqrt_and_unknown_paths_fail_closed(self):
        for operation in ("exp_negative", "exp_negative_ieee_rne",
                          "softplus", "softplus_ieee_decay_candidate", "div", "sqrt", "op5"):
            with self.subTest(operation=operation), self.assertRaises(UnboundTimingError):
                replay_scalar_primitives([request(operation=operation)], repo=REPO)

    def test_nonfinite_inputs_do_not_take_normal_timing(self):
        for bits in (0x7f800000, 0xff800000, 0x7fc00000):
            with self.subTest(bits=bits), self.assertRaises(UnboundTimingError):
                replay_scalar_primitives([request(a=bits)], repo=REPO)

    def test_finite_zero_subnormal_and_possible_overflow_use_normal_path(self):
        # Timing only: neither success nor flags are inferred from these inputs.
        for a, b in ((0, 0x80000000), (1, ONE), (0x7f7fffff, 0x7f7fffff)):
            result = replay_scalar_primitives([request(a=a, b=b)], repo=REPO)
            self.assertEqual(result.events[-1].cycle, 2)

    def test_request_port_is_not_an_unbounded_software_queue(self):
        for requests in ([request(), request("s1", 0)],
                         [request(), request("s1", 1), request("s2", 2)]):
            with self.assertRaisesRegex(TimingError, "single request port"):
                replay_scalar_primitives(requests, repo=REPO)

    def test_record_and_waveform_bounds_fail_before_growth(self):
        with self.assertRaisesRegex(TimingError, "record limit"):
            replay_scalar_primitives([request(), request("s1", 3)], repo=REPO, max_records=6)
        with self.assertRaisesRegex(TimingError, "waveform limit"):
            replay_scalar_primitives([request()], repo=REPO,
                                     result_ready_low=[Interval(3, 4)] * 7, max_records=6)

    def test_overlapping_ready_low_intervals_are_invalid(self):
        with self.assertRaisesRegex(TimingError, "must not overlap"):
            replay_scalar_primitives([request()], repo=REPO,
                                     result_ready_low=[Interval(1, 4), Interval(3, 6)])


class LedgerTests(unittest.TestCase):
    def test_missing_ack_and_duplicate_events_fail_closed(self):
        missing = ledger()
        missing.register(scalar())
        for kind, cycle in (("request", 0), ("start", 0), ("normal", 1), ("done", 2)):
            missing.record(Event(cycle, kind, "s0"))
        with self.assertRaisesRegex(TimingError, "missing/unexpected"):
            missing.report()
        valid = ledger()
        add_events(valid, scalar())
        valid.record(Event(2, "ack", "s0"))
        with self.assertRaisesRegex(TimingError, "duplicate ack"):
            valid.report()

    def test_scalar_ack_edge_is_not_next_accept_edge(self):
        target = ledger()
        add_events(target, scalar())
        add_events(target, scalar("s1"), start=2, done=4, ack=4)
        with self.assertRaisesRegex(TimingError, "scalar_units capacity conflict"):
            target.report()

    def test_wrong_scalar_off_by_one_rejected(self):
        target = ledger()
        add_events(target, scalar(), done=1, ack=1)
        with self.assertRaisesRegex(TimingError, "E0/E1/E2"):
            target.report()

    def test_independent_resources_may_overlap_without_adding_wall_cycles(self):
        target = ledger(10)
        add_events(target, scalar(), start=0, done=2, ack=2)
        add_events(target, matrix(), start=0, done=5, ack=5)
        report = target.report()
        self.assertEqual(report["wall_cycles"], 10)
        self.assertEqual(sum(report["exclusive_cycle_buckets"].values()), 10)
        self.assertEqual(report["exclusive_cycle_buckets"]["matrix_issue"], 1)
        self.assertEqual(report["exclusive_cycle_buckets"]["scalar_issue"], 0)

    def test_five_matrix_contexts_are_reused_without_multiplying_mac_capacity(self):
        target = ledger(20)
        for context in range(5):
            add_events(target, matrix(f"m{context}", context=context, lanes=4096),
                       start=context, done=context + 5, ack=context + 5)
        add_events(target, matrix("reuse", context=0, lanes=4096), start=5, done=10, ack=10)
        report = target.report()
        self.assertEqual(report["resource_peak_occupancy"]["matrix_contexts"], 5)
        self.assertEqual(report["resource_peak_occupancy"]["matrix_lanes"], 4096)
        self.assertEqual(report["executed_matrix_macs"], 6 * 4096)
        self.assertEqual(report["matrix_lane_cycle_denominator"], 20 * 4096)

    def test_matrix_context_waits_for_actual_ack_not_a_fixed_five_cycle_timer(self):
        target = ledger()
        add_events(target, matrix(), start=0, done=5, ack=9)
        add_events(target, matrix("m1"), start=5, done=10, ack=10)
        with self.assertRaisesRegex(TimingError, "context_0 capacity conflict"):
            target.report()

    def test_matrix_pipeline_occupancy_is_not_mislabeled_idle_or_mac_work(self):
        target = ledger(10)
        add_events(target, matrix(), start=0, done=5, ack=7)
        report = target.report()
        self.assertEqual(report["exclusive_cycle_buckets"]["matrix_in_flight"], 4)
        self.assertEqual(report["exclusive_cycle_buckets"]["result_backpressure"], 2)
        self.assertEqual(report["exclusive_cycle_buckets"]["idle"], 2)
        self.assertEqual(report["executed_matrix_macs"], 512)

    def test_matrix_too_early_done_and_sixth_context_rejected(self):
        target = ledger()
        add_events(target, matrix(), done=4, ack=4)
        with self.assertRaisesRegex(TimingError, "before E5"):
            target.report()
        with self.assertRaisesRegex(TimingError, "0..4"):
            ledger().register(matrix(context=5))

    def test_matrix_lane_conflict_is_not_hidden_by_different_contexts(self):
        target = ledger()
        add_events(target, matrix("m0", context=0, lanes=4096), done=5, ack=5)
        add_events(target, matrix("m1", context=1, lanes=512), done=5, ack=5)
        with self.assertRaisesRegex(TimingError, "matrix_lanes capacity conflict"):
            target.report()

    def test_matrix_disjoint_slices_do_not_create_a_second_wide_issue_port(self):
        target = ledger()
        add_events(target, matrix("m0", context=0, lanes=512), done=5, ack=5)
        add_events(target, matrix("m1", context=1, lanes=512), done=5, ack=5)
        with self.assertRaisesRegex(TimingError, "matrix_issue_slots capacity conflict"):
            target.report()

    def test_explicit_events_cannot_queue_two_offers_on_the_same_scalar_port(self):
        target = ledger()
        add_events(target, scalar("s0"), offer=0, start=0, done=2, ack=2)
        add_events(target, scalar("s1"), offer=1, start=3, done=5, ack=5)
        add_events(target, scalar("s2"), offer=2, start=6, done=8, ack=8)
        with self.assertRaisesRegex(TimingError, "scalar_request_port capacity conflict"):
            target.report()

    def test_registered_dependency_requires_next_edge(self):
        target = ledger()
        add_events(target, scalar())
        add_events(target, replace(matrix(), dependencies=("s0",)), start=2, done=7, ack=7)
        with self.assertRaisesRegex(TimingError, "producer ACK edge"):
            target.report()

    def test_missing_dependency_ack_is_not_ignored(self):
        target = ledger()
        add_events(target, replace(matrix(), dependencies=("not_recorded",)), done=5, ack=5)
        with self.assertRaisesRegex(TimingError, "missing dependency ACK"):
            target.report()

    def test_stage_denominators_include_all_idle_and_stall_cycles(self):
        target = ledger(20, phases=(Phase("dense", Interval(0, 8)), Phase("scalar_tail", Interval(8, 20))))
        add_events(target, matrix(phase="dense", lanes=512, useful=32), done=5, ack=5)
        add_events(target, scalar(phase="scalar_tail"), start=8, done=10, ack=15)
        report = target.report()
        self.assertEqual([p["wall_cycles"] for p in report["phases"]], [8, 12])
        self.assertEqual([p["matrix_lane_cycle_denominator"] for p in report["phases"]], [8 * 4096, 12 * 4096])
        self.assertEqual(report["matrix_lane_cycle_denominator"], 20 * 4096)
        self.assertEqual(report["padding_matrix_macs"], 480)
        self.assertEqual(report["conditional_useful_matrix_fraction"], 32 / (20 * 4096))
        for phase in report["phases"]:
            self.assertEqual(sum(phase["exclusive_cycle_buckets"].values()), phase["wall_cycles"])

    def test_phase_gaps_overlap_and_cross_phase_ack_are_rejected(self):
        for phases in ((Phase("a", Interval(0, 5)), Phase("b", Interval(6, 10))),
                       (Phase("a", Interval(0, 6)), Phase("b", Interval(5, 10)))):
            with self.assertRaisesRegex(TimingError, "phase boundaries"):
                ledger(10, phases=phases)
        target = ledger(10, phases=(Phase("a", Interval(0, 3)), Phase("b", Interval(3, 10))))
        add_events(target, scalar(phase="a"), done=2, ack=3)
        with self.assertRaisesRegex(TimingError, "phase terminal"):
            target.report()

    def test_exclusive_stall_partition_with_overlapping_signals(self):
        buckets = exclusive_cycle_buckets(Interval(0, 10), [
            Signal(Interval(0, 4), "input_wait"), Signal(Interval(2, 6), "result_backpressure"),
            Signal(Interval(3, 4), "matrix_issue"), Signal(Interval(6, 8), "dependency_wait")])
        self.assertEqual(sum(buckets.values()), 10)
        self.assertEqual(buckets["input_wait"], 2)
        self.assertEqual(buckets["result_backpressure"], 3)
        self.assertEqual(buckets["matrix_issue"], 1)
        self.assertEqual(buckets["dependency_wait"], 2)
        self.assertEqual(buckets["idle"], 2)

    def test_clock_and_handshake_tick_units_cannot_be_mixed(self):
        target = ledger()
        target.register(scalar())
        for event in (Event(0, "request", "s0", clock="other"),
                      Event(0, "request", "s0", unit="driver_tick")):
            with self.assertRaisesRegex(TimingError, "mixed clocks"):
                target.record(event)

    def test_vector_and_scalar_ops_cannot_be_reclassified_as_matrix_macs(self):
        with self.assertRaisesRegex(TimingError, "only Matrix"):
            ledger().register(replace(scalar(), useful_macs=1, executed_macs=1))
        with self.assertRaisesRegex(UnboundTimingError, "Vector timing is unbound"):
            ledger().register(Operation("v", "test", "vector", "mul", active_lanes=16))

    def test_ddr_write_requires_data_external_ack_and_final_ack(self):
        op = Operation("d", "test", "ddr", "external_write64", external_trace_sha256="a" * 64)
        target = ledger()
        add_events(target, op, done=8, ack=9, write_data=2)
        with self.assertRaisesRegex(TimingError, "missing/unexpected"):
            target.report()
        target.record(Event(7, "write_ack", "d"))
        report = target.report()
        self.assertEqual(report["resource_peak_occupancy"]["ddr_transfers"], 1)
        self.assertIsNone(report["full_block_cycles"])
        self.assertTrue(any("physical DDR" in reason for reason in report["completeness_blockers"]))

    def test_ddr_response_hold_keeps_single_mailbox_occupied(self):
        target = ledger()
        for identity, start, done, ack in (("d0", 0, 3, 7), ("d1", 7, 10, 11)):
            add_events(target, Operation(identity, "test", "ddr", "external_read64",
                                         external_trace_sha256="a" * 64),
                       start=start, done=done, ack=ack, read_data=done - 1)
        with self.assertRaisesRegex(TimingError, "ddr_transfers capacity conflict"):
            target.report()

    def test_ddr_physical_latency_cannot_be_invented_without_external_trace(self):
        with self.assertRaises(UnboundTimingError):
            ledger().register(Operation("d", "test", "ddr", "external_read64"))

    def test_prefix_and_relabelled_full_block_always_fail_completeness(self):
        for scope in ("prefix", "full_block"):
            with self.subTest(scope=scope):
                target = ledger(scope=scope)
                add_events(target, scalar())
                report = target.report()
                self.assertFalse(report["complete_block"])
                self.assertFalse(report["rtl_executed"])
                self.assertIsNone(report["full_block_utilization"])
                self.assertIsNone(report["rtl_measured_cycles"])
                self.assertGreaterEqual(len(report["completeness_blockers"]), len(COMPLETE_BLOCK_BLOCKERS))
                with self.assertRaisesRegex(UnboundTimingError, "complete-block utilization unavailable"):
                    target.require_full_block_utilization()

    def test_source_hash_and_line_attribution_are_verified(self):
        pins = verify_sources(REPO)
        self.assertEqual(len(pins), len(SOURCE_PINS))
        self.assertTrue(all(pin["lines"] for pin in pins))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for pin in SOURCE_PINS:
                destination = root / pin.path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((REPO / pin.path).read_bytes())
            (root / SOURCE_PINS[0].path).write_text("changed\n")
            with self.assertRaisesRegex(TimingError, "source pin changed"):
                verify_sources(root)

    def test_fixed_capacity_dictionary_cannot_be_resized(self):
        self.assertEqual(CAPACITIES["matrix_lanes"], 4096)
        self.assertEqual(CAPACITIES["matrix_contexts"], 5)
        self.assertEqual(CAPACITIES["vector_lanes"], 16)
        self.assertEqual(CAPACITIES["scalar_units"], 1)
        self.assertEqual(CAPACITIES["ddr_beat_bits"], 512)
        with self.assertRaises(TypeError):
            CAPACITIES["matrix_lanes"] = 512


if __name__ == "__main__":
    unittest.main()
