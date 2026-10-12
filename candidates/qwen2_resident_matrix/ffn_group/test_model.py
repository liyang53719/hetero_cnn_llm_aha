"""Adversarial bounded control tests; no hardware/parser/numeric execution claim."""
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ffn_group_control_model", HERE / "model.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def group(rows=16, *, epoch=7, pc=0, offset=0):
    size = rows * m.WIDTH * 4
    g = m.Job("Dense", (epoch << 16) | pc, offset + 0x100000, offset + 0x1000000,
              offset + 0x10000000, rows, m.WIDTH, 1536, size, True)
    u = replace(g, tag=g.tag + 1, b=offset + 0x3000000, dst=offset + 0x11000000)
    a = m.Job("Activation", g.tag + 2, g.dst, u.dst, offset + 0x12000000,
              rows, m.WIDTH, m.WIDTH, size)
    return m.GroupRequest(g, u, a, g.tag + 1)


class ControlHarness:
    """Opaque accepted-terminal ports; no simulated arithmetic or data buffers."""
    def __init__(self, q=None):
        self.q = group() if q is None else q
        self.owner = m.ResidentCoordinator()
        self.services = m.Services()
        self.trace = []
        self.windows, self.drains, self.silu = [], [], []
        self.credits = []
        self.edge(request=self.q)
        assert self.trace[-1]["request_fire"]

    def edge(self, **args):
        args.setdefault("services", self.services)
        e = self.owner.tick(**args)
        self.trace.append(e)
        if e["window_fire"]:
            self.windows.append(e["window_request"])
        if e["drain_fire"]:
            self.drains.append(e["drain_request"])
        if e["silu_fire"]:
            self.silu.append(e["silu_request"])
        for name in ("window", "drain"):
            if e[name + "_result_fire"]:
                self.credits.append(args[name + "_result"])
        return e

    def start_window(self, stalls=0):
        e = self.edge()
        assert e["handoff"] is not None and e["window_request"] is None and e["drain_request"] is None
        held = self.owner.ports(self.services)["window_request"]
        for _ in range(stalls):
            assert self.edge(window_ready=False)["window_request"] == held
        e = self.edge()
        assert e["window_fire"]
        self.services = replace(self.services, window_busy=True)
        return e["window_request"]

    def window_terminal(self, q, useful=7, executed=11, **changes):
        r = m.WindowResult(q.job.tag, q.identity, q.ng, q.job.m, q.cols, q.slot, True,
                           q.job.m // 16 * q.cols, useful_macs=useful, executed_macs=executed)
        return replace(r, **changes)

    def finish_window(self, q, *, delay=0, result=None):
        for _ in range(delay):
            self.edge()
            assert self.owner.state.endswith("Wait")
        self.services = replace(self.services, lease_valid=True, tiles_leased=True)
        e = self.edge(window_result=self.window_terminal(q) if result is None else result)
        self.services = replace(self.services, window_busy=False)
        assert e["window_result_fire"]
        return e

    def reach_drain(self, *, stalls=0):
        for _ in range(2):
            q = self.start_window(stalls)
            # These deliberately arbitrary credits differ on every terminal.
            r = self.window_terminal(q, useful=3 + len(self.windows), executed=17 + 2 * len(self.windows))
            self.finish_window(q, delay=stalls, result=r)
        held = self.owner.ports(self.services)["silu_request"]
        for _ in range(stalls):
            assert self.edge(silu_ready=False)["silu_request"] == held
        assert self.edge()["silu_fire"]
        self.services = replace(self.services, bridge_busy=True, silu_drained=False)
        for _ in range(stalls):
            self.edge()
        self.edge(silu_complete=True)
        self.services = replace(self.services, bridge_busy=False, silu_drained=True)
        e = self.edge()
        assert e["handoff"] == self.q.act and e["drain_request"] is None
        held = self.owner.ports(self.services)["drain_request"]
        for _ in range(stalls):
            assert self.edge(drain_ready=False)["drain_request"] == held
        e = self.edge()
        assert e["drain_fire"]
        self.services = replace(self.services, drain_busy=True)
        return e["drain_request"]

    def drain_terminal(self, q, useful=0, executed=0, **changes):
        r = m.DrainResult(q.job.tag, q.identity, q.ng, q.job.m, q.cols, True,
                          q.job.m // 16 * q.cols, q.job.m * q.cols * 4,
                          useful_macs=useful, executed_macs=executed)
        return replace(r, **changes)

    def finish_drain(self, q, *, ack_delay=0, result=None, release=True):
        # A delayed external ACK/release means no drain terminal exists yet.
        # We do not manufacture data traffic, ACKs, or a DDR memory image here.
        for _ in range(ack_delay):
            assert self.edge()["result"] is None
            assert self.owner.state == "actWait"
        self.services = replace(self.services, tiles_leased=not release, tiles_drained=release)
        e = self.edge(drain_result=self.drain_terminal(q) if result is None else result)
        self.services = replace(self.services, drain_busy=False)
        assert e["drain_result_fire"]
        return e

    def finish(self, *, stalls=0):
        while self.owner.state != "invalidate":
            q = self.reach_drain(stalls=stalls)
            # Drain counters are opaque too; nonzero values catch overwrites.
            r = self.drain_terminal(q, useful=101 + len(self.drains), executed=301 + len(self.drains))
            self.finish_drain(q, ack_delay=stalls, result=r)
        assert self.owner.ng == 8800
        assert self.edge()["invalidate_lease"]
        assert self.owner.state == "retire"
        for _ in range(stalls + 1):
            assert self.edge()["result"] is None
            assert self.owner.state == "retire"
        self.services = replace(self.services, lease_valid=False)
        self.edge()
        assert self.owner.state == "reply"
        return self.owner.result


def fixture(rows=16, *, offset=0, epoch=7):
    q = group(rows, offset=offset, epoch=epoch)
    tensors = {
        0: m.Tensor(q.gate.a, (rows, 1536), tail=100),
        1: m.Tensor(q.gate.b, (1536, 8960), 5),
        2: m.Tensor(q.gate.dst, (rows, 8960)),
        3: m.Tensor(q.up.a, (rows, 1536), tail=101),
        4: m.Tensor(q.up.b, (1536, 8960), 5),
        5: m.Tensor(q.up.dst, (rows, 8960)),
        6: m.Tensor(q.act.a, (rows, 8960), tail=102),
        7: m.Tensor(q.act.b, (rows, 8960)),
        8: m.Tensor(q.act.dst, (rows, 8960)),
    }
    program = [m.Command(0x20, 2, 0, 1, 2, 0, 1), m.Command(0x20, 2, 3, 4, 5, 1, 2),
               m.Command(0x35, 3, 6, 7, 8, 2, 3)]
    policies = {100: m.Policy("matrix", rows, 8960, 1536),
                101: m.Policy("matrix", rows, 8960, 1536), 102: m.Policy("sfu", opcode=0x35)}
    regions = (m.Region(offset + 0x100000, offset + 0x8000000, True, False),
               m.Region(offset + 0x10000000, offset + 0x20000000, True, True))
    return program, tensors, policies, regions


def host_fixture(rows=16, *, enabled=True, offset=0, epoch=7, **kwargs):
    program, tensors, policies, regions = fixture(rows, offset=offset, epoch=epoch)
    host = m.HostControl(enabled=enabled, **kwargs)
    reader = m.TypedRootReader(tensors, regions, 200)
    assert host.launch(program, reader, policies, epoch=epoch)
    return host


def advance_issue(h):
    for _ in range(3 * h.max_commands + 2):
        if h.state in ("issue", "complete", "finish"):
            return
        h.tick()
    raise AssertionError("bounded metadata walk failed to terminate")


def opaque_owner_result(h, *, useful=19, executed=41):
    return m.OwnerResult(h.bound.tag, None, h.bound.write_bytes, 123, useful, executed)


def execute_ordinary(h):
    advance_issue(h)
    assert h.state == "issue" and h.group is None
    assert h.tick()["request_fire"]
    h.tick(owner_result=opaque_owner_result(h))
    assert h.tick(completion_ready=True)["completion_fire"]


class CoordinatorTests(unittest.TestCase):
    def test_m16_and_m128_all_56_windows_and_actual_counter_deltas(self):
        for rows in (16, 128):
            with self.subTest(rows=rows):
                h = ControlHarness(group(rows, epoch=65535, pc=12, offset=0x400000000))
                result = h.finish(stalls=1)
                self.assertEqual(len(h.windows), 112)
                self.assertEqual(len(h.drains), 56)
                self.assertEqual(len(h.silu), 56)
                self.assertEqual([q.ng for q in h.drains], list(range(0, 8960, 160)))
                self.assertEqual([(q.ng, q.slot) for q in h.windows], [(ng, slot) for ng in range(0, 8960, 160) for slot in (0, 1)])
                self.assertEqual([q.reuse_a for q in h.windows], [False] + [True] * 111)
                self.assertTrue(all(q.job.n == 8960 and q.job.k == 1536 for q in h.windows))
                self.assertTrue(all(q.job.k == 8960 for q in h.drains))
                self.assertEqual(result.write_bytes, rows * 8960 * 4)
                self.assertEqual(result.useful_macs, sum(x.useful_macs for x in h.credits))
                self.assertEqual(result.executed_macs, sum(x.executed_macs for x in h.credits))
                self.assertEqual(result.cycles, len(h.trace) - 1)
                self.assertIsNone(result.status)
                self.assertEqual(result.tag, h.q.act.tag)
                self.assertFalse(h.services.lease_valid)

    def test_terminal_backpressure_excluded_from_cycles_and_payload_stable(self):
        h = ControlHarness()
        r = h.finish()
        for _ in range(9):
            e = h.edge(request=group(epoch=9))
            self.assertEqual(e["result"], r)
            self.assertFalse(e["request_fire"])
            self.assertEqual(h.owner.cycles, r.cycles)
        self.assertTrue(h.edge(result_ready=True)["result_fire"])
        self.assertEqual(h.owner.state, "idle")
        self.assertTrue(h.edge(request=group(epoch=9))["request_fire"])
        self.assertEqual(h.owner.cycles, 0)
        self.assertEqual(h.owner.write_bytes, 0)

    def test_window_bad_metadata_and_missing_lease_poison_before_next_issue(self):
        fields = dict(tag=0, identity=0, ng=160, rows=128, cols=32, slot=1,
                      committed=False, produced_beats=159, ddr_write_bytes=64)
        for field, value in fields.items():
            with self.subTest(field=field):
                h = ControlHarness()
                q = h.start_window()
                r = h.window_terminal(q, useful=71, executed=103, **{field: value})
                h.finish_window(q, result=r)
                self.assertEqual(h.owner.state, "draining")
                self.assertTrue(h.owner.poison)
                self.assertEqual((h.owner.useful, h.owner.executed), (71, 103))
                self.assertIsNone(h.owner.ports(h.services)["window_request"])
        h = ControlHarness()
        q = h.start_window()
        h.edge(window_result=h.window_terminal(q), services=m.Services(window_busy=True))
        self.assertEqual(h.owner.state, "draining")

    def test_up_requires_up_tag_slot_and_original_identity(self):
        h = ControlHarness()
        first = h.start_window()
        h.finish_window(first)
        second = h.start_window()
        h.finish_window(second, result=replace(h.window_terminal(second), tag=first.job.tag, slot=0))
        self.assertEqual(h.owner.state, "draining")
        self.assertEqual(h.owner.useful, 14)

    def test_drain_bad_metadata_bytes_and_release_cannot_advance_group(self):
        fields = dict(tag=0, identity=0, ng=160, rows=128, cols=32, committed=False,
                      consumed_beats=159, ddr_write_bytes=16 * 160 * 4 - 64)
        for field, value in fields.items():
            with self.subTest(field=field):
                h = ControlHarness()
                q = h.reach_drain()
                r = h.drain_terminal(q, useful=13, executed=23, **{field: value})
                h.finish_drain(q, result=r)
                self.assertEqual(h.owner.state, "draining")
                self.assertEqual(h.owner.ng, 0)
                self.assertEqual(h.owner.write_bytes, r.ddr_write_bytes)
                self.assertEqual(h.owner.useful, 4 + 5 + 13)
        for leased, drained in ((True, True), (False, False), (True, False)):
            h = ControlHarness()
            q = h.reach_drain()
            h.edge(drain_result=h.drain_terminal(q), services=replace(h.services, tiles_leased=leased, tiles_drained=drained))
            self.assertEqual(h.owner.state, "draining")

    def test_delayed_ack_no_terminal_or_next_window(self):
        h = ControlHarness()
        q = h.reach_drain(stalls=2)
        for _ in range(20):
            e = h.edge()
            self.assertEqual(h.owner.state, "actWait")
            self.assertIsNone(e["result"])
            self.assertIsNone(e["window_request"])
            self.assertEqual(h.owner.write_bytes, 0)
        h.finish_drain(q)
        self.assertEqual(h.owner.state, "gateFlush")
        self.assertEqual(h.owner.ng, 160)

    def test_abort_inflight_window_drains_accepted_counter_terminal(self):
        h = ControlHarness()
        q = h.start_window()
        h.edge(abort=True)
        for _ in range(5):
            self.assertIsNone(h.edge()["result"])
        h.edge(window_result=h.window_terminal(q, useful=113, executed=179, committed=False, status="Backend"))
        self.assertEqual(h.owner.state, "draining")
        h.services = m.Services()
        h.edge()
        self.assertEqual((h.owner.result.useful_macs, h.owner.result.executed_macs), (113, 179))
        self.assertIsNotNone(h.owner.result.status)
        h.edge(result_ready=True)
        self.assertEqual(h.owner.state, "locked")
        self.assertFalse(h.edge(request=h.q)["request_fire"])

    def test_abort_during_drain_retains_actual_partial_ack_byte_credit(self):
        h = ControlHarness()
        q = h.reach_drain()
        h.edge(abort=True)
        partial = h.drain_terminal(q, committed=False, status="Backend", consumed_beats=9,
                                   ddr_write_bytes=192, useful=37, executed=53)
        h.edge(drain_result=partial)
        self.assertIsNone(h.owner.result)
        h.services = m.Services()
        h.edge()
        self.assertEqual(h.owner.result.write_bytes, 192)
        self.assertEqual(h.owner.result.useful_macs, 4 + 5 + 37)
        self.assertEqual(h.owner.result.executed_macs, 19 + 21 + 53)

    def test_explicit_backend_error_survives_same_edge_reset(self):
        for which in ("window", "drain"):
            h = ControlHarness()
            q = h.start_window() if which == "window" else h.reach_drain()
            r = h.window_terminal(q, status="SpecificBackend") if which == "window" else h.drain_terminal(q, status="SpecificBackend")
            h.edge(**{which + "_result": r}, services=replace(h.services, **{which + "_reset": True}))
            self.assertEqual(h.owner.status, "SpecificBackend")
            h.services = m.Services()
            h.edge()
            self.assertEqual(h.owner.result.status, "SpecificBackend")

    def test_draining_waits_all_backend_obligations(self):
        for blocked in (dict(window_busy=True), dict(drain_busy=True), dict(tiles_drained=False),
                        dict(silu_drained=False), dict(bridge_busy=True)):
            with self.subTest(blocked=blocked):
                h = ControlHarness()
                h.edge(abort=True)
                for _ in range(3):
                    h.edge(services=m.Services(**blocked))
                    self.assertEqual(h.owner.state, "draining")
                h.edge(services=m.Services())
                self.assertEqual(h.owner.state, "reply")

    def test_abort_held_terminal_is_sticky_without_payload_mutation(self):
        for fault in ("abort", "window_reset", "drain_reset", "bridge_reset"):
            h = ControlHarness()
            result = h.finish()
            args = dict(abort=True) if fault == "abort" else dict(services=m.Services(**{fault: True}))
            self.assertEqual(h.edge(**args)["result"], result)
            for _ in range(3):
                self.assertEqual(h.edge()["result"], result)
                self.assertTrue(h.owner.ports()["reset_required"])
            h.edge(result_ready=True)
            self.assertEqual(h.owner.state, "locked")

    def test_idle_raw_error_is_sticky_and_blocks_admission(self):
        o = m.ResidentCoordinator()
        self.assertFalse(o.tick(request=group(), abort=True)["request_fire"])
        self.assertTrue(o.ports()["reset_required"])
        self.assertFalse(o.tick(request=group())["request_fire"])

    def test_all_active_phases_abort_suppresses_new_issue(self):
        for state in m.ResidentCoordinator.STATES:
            if state in ("idle", "reply", "locked", "draining"):
                continue
            with self.subTest(state=state):
                h = ControlHarness()
                # State-directed control fault injection, not a legal data path.
                h.owner.state = state
                e = h.edge(abort=True)
                self.assertTrue(e["invalidate_lease"])
                self.assertIsNone(e["window_request"])
                self.assertIsNone(e["drain_request"])
                self.assertIsNone(e["silu_request"])
                self.assertEqual(h.owner.state, "draining")

    def test_invalidate_retire_requires_lease_observation_and_quiescence(self):
        for blocked in (dict(lease_valid=True), dict(window_busy=True), dict(drain_busy=True),
                        dict(tiles_leased=True), dict(tiles_drained=False), dict(silu_drained=False)):
            h = ControlHarness()
            h.owner.state = "invalidate"
            h.edge()
            self.assertEqual(h.owner.state, "retire")
            self.assertTrue(h.edge(services=m.Services(**blocked))["invalidate_lease"])
            self.assertEqual(h.owner.state, "retire")
            h.edge(services=m.Services())
            self.assertEqual(h.owner.state, "reply")

    def test_last_drain_full_total_is_independent_check(self):
        h = ControlHarness()
        h.owner.ng = 8800
        q = h.reach_drain()
        h.owner.write_bytes = h.q.act.write_bytes - h.q.act.m * 160 * 4 - 64
        h.finish_drain(q)
        self.assertEqual(h.owner.state, "draining")

    def test_malformed_group_never_issues_and_remains_reset_required(self):
        q = group()
        bad = [replace(q, identity=0), replace(q, identity=1 << 32), replace(q, gate=replace(q.gate, m=32)),
               replace(q, up=replace(q.up, a=q.up.a + 64)), replace(q, up=replace(q.up, n=8800)),
               replace(q, act=replace(q.act, k=1536)), replace(q, act=replace(q.act, a=q.act.a + 64)),
               replace(q, act=replace(q.act, output_bf16=True)), replace(q, act=replace(q.act, write_bytes=0))]
        for value in bad:
            h = ControlHarness(value)
            self.assertEqual(h.owner.state, "draining")
            h.edge()
            self.assertEqual(h.owner.result.status, "Malformed")
            self.assertEqual(h.windows, [])

    def test_local_reset_is_poison_not_coordinated_recovery(self):
        h = ControlHarness()
        q = h.start_window()
        h.edge(local_reset=True)
        h.edge(window_result=h.window_terminal(q, useful=1, executed=3))
        h.services = m.Services()
        h.edge()
        h.edge(result_ready=True)
        self.assertEqual(h.owner.state, "locked")
        with self.assertRaises(ValueError):
            h.edge(coordinated_reset={"coordinator", "window"})
        h.edge(coordinated_reset=m.RESET_DOMAIN)
        self.assertFalse(h.owner.poison)
        self.assertTrue(h.edge(request=h.q)["request_fire"])

    def test_controlled_terminal_busy_and_single_owner_domain_are_explicit(self):
        h = ControlHarness()
        q = h.start_window()
        with self.assertRaisesRegex(ValueError, "busy"):
            h.edge(window_result=h.window_terminal(q), services=m.Services())
        h.owner.state = "draining"
        with self.assertRaisesRegex(ValueError, "one terminal"):
            h.edge(window_result=h.window_terminal(q), drain_result=h.drain_terminal(m.DrainRequest(h.q.act, h.q.identity, 0, 160)),
                   services=m.Services(window_busy=True, drain_busy=True))


class HostTests(unittest.TestCase):
    def test_all_group_metadata_and_all_public_roots_precede_issue(self):
        for rows in (16, 128):
            h = host_fixture(rows)
            h.tick()
            self.assertEqual(h.state, "scan")
            self.assertEqual(len(h.reader.reads), 9)
            self.assertEqual(h.jobs, 0)
            self.assertEqual(h.virtual, [])
            for _ in range(8):
                self.assertIsNone(h.tick()["group_request"])
                self.assertEqual(h.virtual, [])
                self.assertEqual(h.jobs, 0)
            h.tick()
            self.assertEqual(h.state, "issue")
            self.assertEqual(len(h.reader.reads), 18)
            self.assertEqual(len(h.virtual), 2)
            self.assertEqual(h.scanner.trace, [(pc, slot, h.program[pc].roots[slot]) for pc in range(3) for slot in range(3)])
            self.assertEqual(h.events, {0})
            self.assertEqual(h.published, [])

    def test_group_terminal_then_original_three_completion_edges_publish_only_act(self):
        h = host_fixture(epoch=65535)
        advance_issue(h)
        request = h.ports()["group_request"]
        for _ in range(4):
            self.assertEqual(h.tick(request_ready=False)["group_request"], request)
        self.assertTrue(h.tick()["request_fire"])
        self.assertEqual(h.jobs, 1)
        for _ in range(8):
            self.assertIsNone(h.tick()["completion"])
            self.assertEqual(h.published, [])
        h.tick(owner_result=opaque_owner_result(h, useful=17, executed=91))
        for i in range(3):
            expected = m.Completion(i, (2, 2, 3)[i], i + 1, None)
            for _ in range(4):
                self.assertEqual(h.tick()["completion"], expected)
                self.assertEqual(h.published, [])
                self.assertEqual(h.events, set(range(i + 1)))
            self.assertEqual(h.tick(completion_ready=True)["completion"], expected)
        self.assertEqual(h.state, "finish")
        self.assertEqual(h.published, [(request.act.dst, request.act.dst + request.act.write_bytes)])
        self.assertEqual(h.events, {0, 1, 2, 3})
        self.assertEqual((h.completed, h.useful, h.executed, h.written), (3, 17, 91, request.act.write_bytes))
        for root in (2, 5):
            self.assertFalse(h.live(h.reader.tensors[root]))
        self.assertTrue(h.live(h.reader.tensors[8]))

    def test_default_off_uses_three_ordinary_ddr_jobs_and_all_outputs_visible(self):
        h = host_fixture(enabled=False)
        for i in range(3):
            execute_ordinary(h)
            self.assertEqual(h.jobs, i + 1)
            self.assertEqual(len(h.published), i + 1)
        self.assertEqual(h.virtual, [])
        self.assertEqual(h.written, 3 * 16 * 8960 * 4)
        self.assertTrue(all(h.live(h.reader.tensors[root]) for root in (2, 5, 8)))

    def test_no_eligible_group_falls_back_to_ordinary_driver(self):
        h = host_fixture(rows=32)
        for _ in range(3):
            execute_ordinary(h)
        self.assertEqual(h.jobs, 3)
        self.assertEqual(h.virtual, [])

    def test_bad_up_act_policies_reject_before_gate_issue(self):
        for tail in (100, 101, 102):
            h = host_fixture()
            h.policies[tail] = replace(h.policies[tail], valid=False)
            advance_issue(h)
            self.assertEqual(h.status, "Unsupported")
            self.assertEqual(h.jobs, 0)
            self.assertEqual(h.virtual, [])
        h = host_fixture()
        h.policies[101] = replace(h.policies[101], k=1520)
        advance_issue(h)
        self.assertEqual(h.status, "Unsupported")
        self.assertEqual(h.jobs, 0)

    def test_event_engine_opcode_and_group_order_validation(self):
        for index, changes in ((1, dict(wait=0)), (2, dict(wait=1)), (1, dict(signal=1)),
                               (2, dict(signal=1)), (2, dict(signal=256)), (0, dict(signal=0)),
                               (0, dict(engine=3)), (1, dict(opcode=0x35)), (2, dict(opcode=0x20)),
                               (2, dict(reserved=1))):
            with self.subTest(index=index, changes=changes):
                h = host_fixture()
                h.program[index] = replace(h.program[index], **changes)
                advance_issue(h)
                self.assertIsNotNone(h.status)
                self.assertEqual(h.jobs, 0)
                self.assertEqual(h.virtual, [])

    def test_consumer_policy_tail_is_excluded_from_allocation_identity(self):
        h = host_fixture()
        self.assertNotEqual(h.reader.tensors[0].tail, h.reader.tensors[3].tail)
        self.assertNotEqual(h.reader.tensors[2].tail, h.reader.tensors[6].tail)
        self.assertTrue(h.reader.tensors[0].same_allocation(h.reader.tensors[3]))
        self.assertTrue(h.reader.tensors[2].same_allocation(h.reader.tensors[6]))
        advance_issue(h)
        self.assertIsNone(h.status)
        self.assertEqual(h.state, "issue")

    def test_exact_allocation_rejects_changed_dimensions_dtype_and_address(self):
        for changes in (dict(address=0x100040), dict(dims=(16, 1520)), dict(dtype=5)):
            h = host_fixture()
            h.reader.tensors[3] = replace(h.reader.tensors[3], **changes)
            advance_issue(h)
            self.assertIsNotNone(h.status)
            self.assertEqual(h.jobs, 0)

    def test_permissions_and_padded_full_spans(self):
        for region in (m.Region(0x10000000, 0x20000000, False, True),
                       m.Region(0x10000000, 0x20000000, True, False)):
            h = host_fixture()
            h.reader.regions = (h.reader.regions[0], region)
            advance_issue(h)
            self.assertEqual(h.status, "Permission")
            self.assertEqual(h.jobs, 0)
        # Permission follows the rounded allocation, not its 4-byte payload.
        t = m.Tensor(0x4000, (1,))
        r = m.TypedRootReader({0: t}, (m.Region(0x4000, 0x4004, True, False),))
        with self.assertRaises(m.Rejected) as caught:
            r.read(0)
        self.assertEqual(caught.exception.status, "Permission")
        self.assertEqual(t.padded_end, 0x4040)

    def test_weights_and_all_six_full_allocations_pairwise_disjoint(self):
        for root, address in ((4, 0x1000000), (4, 0x100000), (5, 0x10000000), (8, 0x11000000)):
            h = host_fixture()
            h.reader.tensors[root] = replace(h.reader.tensors[root], address=address)
            if root == 5:
                h.reader.tensors[7] = replace(h.reader.tensors[7], address=address)
            advance_issue(h)
            self.assertIsNotNone(h.status)
            self.assertEqual(h.jobs, 0)

    def test_future_primary_consumers_each_role_reject_before_gate(self):
        for virtual_root in (2, 5):
            for slot in range(3):
                h = host_fixture()
                roots = [0, 1, 8]
                roots[slot] = virtual_root
                h.program.append(m.Command(0xFE, 7, *roots, 3, 4))
                advance_issue(h)
                self.assertEqual(h.status, "Dependency")
                self.assertEqual(h.jobs, 0)
                self.assertEqual(h.virtual, [])

    def test_previous_primary_consumers_each_role_checked_by_scanner(self):
        program, tensors, policies, regions = fixture()
        for root in (2, 5):
            for slot in range(3):
                roots = [0, 1, 8]
                roots[slot] = root
                earlier = m.Command(0xFE, 7, *roots, 0, 4)
                scanner = m.VirtualRootPreflight([earlier] + program, m.TypedRootReader(tensors, regions, 200),
                                                1, program, tensors[2], tensors[5])
                with self.assertRaises(m.Rejected) as caught:
                    while not scanner.done:
                        scanner.step()
                self.assertEqual(caught.exception.status, "Dependency")

    def test_partial_alias_and_forged_designated_allocation_rejected(self):
        h = host_fixture()
        h.reader.tensors[9] = m.Tensor(h.reader.tensors[2].padded_end - 64, (1,))
        h.program.append(m.Command(0xFE, 7, 9, 1, 8, 3, 4))
        advance_issue(h)
        self.assertEqual(h.status, "Dependency")
        h = host_fixture()
        h.tick()
        # Metadata changed after initial group preflight, before scan re-read.
        h.reader.tensors[6] = replace(h.reader.tensors[6], dims=(16, 16))
        advance_issue(h)
        self.assertEqual(h.status, "Dependency")
        self.assertEqual(h.virtual, [])

    def test_unknown_unrelated_opcode_scans_then_normal_decode_rejects_later(self):
        h = host_fixture()
        h.program.append(m.Command(0xFE, 7, 0, 1, 8, 3, 4))
        advance_issue(h)
        self.assertEqual(h.state, "issue")
        h.tick()
        h.tick(owner_result=opaque_owner_result(h))
        for _ in range(3):
            h.tick(completion_ready=True)
        h.tick()
        self.assertEqual(h.status, "Unsupported")
        self.assertEqual(h.completed, 3)

    def test_softmax_null_b_skipped_but_primary_a_and_d_still_scanned(self):
        h = host_fixture()
        h.program.append(m.Command(0x33, 3, 0, m.NULL, 8, 3, 4))
        advance_issue(h)
        self.assertEqual(h.state, "issue")
        self.assertEqual(h.scanner.trace[-2:], [(3, 0, 0), (3, 2, 8)])
        h = host_fixture()
        h.program.append(m.Command(0x33, 3, 0, 1, 8, 3, 4))
        advance_issue(h)
        self.assertEqual(h.status, "Malformed")

    def test_scanner_reads_future_permissions_errors_and_domain_bounds(self):
        for tensor, expected in ((m.Tensor(1 << 56, (1,)), "Bounds"),
                                 (m.Tensor(0x100001, (1,)), "Bounds"),
                                 (m.Tensor(0x100000, (1,), reader_error="Protocol"), "Protocol"),
                                 (m.Tensor(0x30000000, (1,)), "Permission")):
            h = host_fixture()
            h.reader.tensors[9] = tensor
            h.program.append(m.Command(0xFE, 7, 9, 1, 8, 3, 4))
            advance_issue(h)
            self.assertEqual(h.status, expected)
            self.assertEqual(h.jobs, 0)
        for root in (m.NULL, 200, -1, 1 << 24):
            h = host_fixture()
            h.program.append(m.Command(0xFE, 7, root, 1, 8, 3, 4))
            advance_issue(h)
            self.assertEqual(h.status, "Malformed")

    def test_scanner_detects_group_command_mutation_without_reservation(self):
        for pc in range(3):
            h = host_fixture()
            h.tick()
            h.program[pc] = replace(h.program[pc], signal=99)
            advance_issue(h)
            self.assertEqual(h.status, "Protocol")
            self.assertEqual(h.virtual, [])
            self.assertEqual(h.jobs, 0)

    def test_capacity_plus_two_is_widened_and_reserved_only_after_complete_scan(self):
        for max_commands in (21, 255):
            for available in (1, 2):
                h = host_fixture(max_commands=max_commands)
                # Disjoint prior virtual allocations inject only capacity state.
                h.virtual = [(0x30000000 + i * 64, 0x30000040 + i * 64) for i in range(max_commands - available)]
                old = list(h.virtual)
                h.tick()
                if available == 1:
                    self.assertEqual(h.status, "Permission")
                    self.assertEqual(h.virtual, old)
                else:
                    self.assertEqual(h.state, "scan")
                    self.assertEqual(h.virtual, old)
                    advance_issue(h)
                    self.assertEqual(len(h.virtual), max_commands)
                    self.assertEqual(h.state, "issue")

    def test_scanner_exact_maximum_and_overbound_commands(self):
        h = host_fixture(max_commands=21)
        h.program += [m.Command(0xFE, 7, 0, 1, 8, 0, 4)] * 18
        advance_issue(h)
        self.assertEqual(h.state, "issue")
        self.assertEqual(len(h.scanner.trace), 63)
        program, tensors, policies, regions = fixture()
        reader = m.TypedRootReader(tensors, regions, 200)
        over = program + [program[0]] * 19
        h = m.HostControl(enabled=True, max_commands=21)
        self.assertTrue(h.launch(over, reader, policies))
        self.assertEqual(h.state, "finish")
        self.assertEqual(h.status, "Bounds")
        self.assertEqual(reader.reads, [])

    def test_profile_excludes_native_extra_roots(self):
        for profile in ("qwen35_qkv", "qwen35_gdn", "qwen35_attention"):
            with self.assertRaises(ValueError):
                m.HostControl(enabled=True, profile=profile)
        self.assertFalse(m.HostControl().enabled)

    def test_relocated_group_after_prior_a_producer_and_valid_future_a_reuse(self):
        for offset in (0, 0x400000000):
            program, tensors, policies, regions = fixture(offset=offset)
            produced_a = offset + 0x13000000
            tensors[0] = replace(tensors[0], address=produced_a)
            tensors[3] = replace(tensors[3], address=produced_a)
            tensors[9] = m.Tensor(offset + 0x6000000, (16, 16), tail=103)
            tensors[10] = m.Tensor(offset + 0x7000000, (16, 1536), 5)
            tensors[11] = m.Tensor(produced_a, (16, 1536))
            tensors[12] = m.Tensor(produced_a, (16, 1536), tail=104)
            tensors[13] = m.Tensor(offset + 0x7100000, (1536, 32), 5)
            tensors[14] = m.Tensor(offset + 0x14000000, (16, 32))
            policies.update({103: m.Policy("matrix", 16, 1536, 16), 104: m.Policy("matrix", 16, 32, 1536)})
            program = [m.Command(0x20, 2, 9, 10, 11, 0, 10)] + [replace(c, wait=10 + i, signal=11 + i) for i, c in enumerate(program)]
            program += [m.Command(0x20, 2, 12, 13, 14, 13, 14)]
            h = m.HostControl(enabled=True)
            h.launch(program, m.TypedRootReader(tensors, regions, 200), policies, epoch=65535)
            execute_ordinary(h)
            self.assertTrue(h.live(tensors[0]))
            advance_issue(h)
            self.assertEqual(h.state, "issue")
            self.assertEqual(h.group.gate.tag, (65535 << 16) | 1)
            self.assertEqual(h.group.identity, ((65535 << 16) | 1) + 1)
            self.assertEqual(h.scanner.gate_pc, 1)
            h.tick()
            h.tick(owner_result=opaque_owner_result(h))
            for pc, engine, event in ((1, 2, 11), (2, 2, 12), (3, 3, 13)):
                self.assertEqual(h.tick(completion_ready=True)["completion"], m.Completion(pc, engine, event, None))
            execute_ordinary(h)
            self.assertEqual(h.state, "finish")
            self.assertEqual(h.completed, 5)
            self.assertEqual(h.jobs, 3)
            self.assertTrue(h.live(tensors[0]))
            self.assertFalse(h.live(tensors[2]))

    def test_result_tag_bytes_error_and_raw_reset_prevent_publication(self):
        for changes in (dict(tag=0), dict(write_bytes=0), dict(status="Backend")):
            h = host_fixture()
            advance_issue(h)
            h.tick()
            h.tick(owner_result=replace(opaque_owner_result(h), **changes))
            self.assertIsNotNone(h.status)
            self.assertEqual(h.published, [])
            self.assertEqual(h.events, {0})
            self.assertEqual(h.written, 0)
        h = host_fixture()
        advance_issue(h)
        h.tick()
        h.tick(owner_result=opaque_owner_result(h), reset_required=True)
        self.assertEqual(h.status, "Protocol")
        self.assertEqual(h.published, [])

    def test_raw_reset_revokes_each_held_completion_and_never_publishes_act(self):
        for accepted in (0, 1, 2):
            h = host_fixture()
            advance_issue(h)
            h.tick()
            h.tick(owner_result=opaque_owner_result(h))
            for _ in range(accepted):
                h.tick(completion_ready=True)
            e = h.tick(completion_ready=True, reset_required=True)
            self.assertIsNone(e["completion"])
            self.assertFalse(e["completion_fire"])
            self.assertEqual(h.status, "Protocol")
            self.assertEqual(h.published, [])
            self.assertEqual(h.completed, accepted)
            h.tick(completion_ready=True)
            h.tick(result_ready=True)
            self.assertEqual(h.state, "locked")
            self.assertFalse(h.launch([], h.reader, h.policies))

    def test_repeated_successful_launch_clears_events_virtuals_and_counters(self):
        h = host_fixture()
        for _ in range(2):
            advance_issue(h)
            h.tick()
            h.tick(owner_result=opaque_owner_result(h))
            for _ in range(3):
                h.tick(completion_ready=True)
            h.tick(result_ready=True)
            self.assertEqual(h.state, "idle")
            self.assertTrue(h.launch(h.program, h.reader, h.policies, epoch=7))
            self.assertEqual(h.events, {0})
            self.assertEqual(h.virtual, [])
            self.assertEqual((h.jobs, h.completed, h.written), (0, 0, 0))

    def test_host_recovery_requires_full_coordinated_reset(self):
        h = host_fixture()
        h.program[0] = replace(h.program[0], engine=7)
        advance_issue(h)
        h.tick(completion_ready=True)
        h.tick(result_ready=True)
        self.assertEqual(h.state, "locked")
        with self.assertRaises(ValueError):
            h.tick(coordinated_reset={"host"})
        h.tick(coordinated_reset=m.RESET_DOMAIN)
        program, tensors, policies, regions = fixture()
        self.assertTrue(h.launch(program, m.TypedRootReader(tensors, regions, 200), policies))
        advance_issue(h)
        self.assertEqual(h.state, "issue")


if __name__ == "__main__":
    unittest.main()
