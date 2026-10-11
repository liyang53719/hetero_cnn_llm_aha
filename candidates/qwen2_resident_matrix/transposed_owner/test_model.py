"""Port/control tests only: no substitute arithmetic or numerical FMA claim."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


model = load("transposed_owner_model", HERE / "model.py")
route = load("frozen_transposed_route_model", HERE.parent / "transposed_route/transposed_model.py").route
Job, ReadBeat = model.Job, model.ReadBeat
MatrixResult, MatrixDone, WriteAck = model.MatrixResult, model.MatrixDone, model.WriteAck


def activation(m, k):
    return 0x3000 + (m * 17 + k) % 0x1000


def weight(k, n):
    return 0x3800 + (k * 7 + n) % 0x500


def answer(m, n):
    # Opaque finite FP32 wire token, deliberately not a multiplication oracle.
    return 0x3f000000 + n * 128 + m


def physical(context, n_base=0, padding_nan=False):
    return tuple(tuple(0x7fc00000 if padding_nan and c % 128 >= 16 else
                       answer(c % 128, n_base + context * 32 + (c // 128) * 16 + r)
                       for c in range(256)) for r in range(16))


class Harness:
    """Small external DDR/matrix peer; no access to owner's RAM writes."""
    def __init__(self, job, owner=None):
        self.owner = owner or model.DenseOwnerModel()
        self.job = job
        self.read = None
        self.write = None
        self.ack = None
        self.results = []
        self.steps = []
        self.stores = []
        self.commands = []
        self.response = None
        self.owner.tick(job=job)

    def read_payload(self, cmd):
        if cmd.kind == "a":
            native = self.job.activation_bf16
            first = (cmd.address - self.job.a) // (2 if native else 4)
            values = tuple(activation((first + i) // self.job.k, (first + i) % self.job.k)
                           for i in range(32 if native else 16))
        else:
            native = self.job.weight_bf16
            first = (cmd.address - self.job.b) // (2 if native else 4)
            values = tuple(weight((first + i) // self.job.n, (first + i) % self.job.n)
                           for i in range(32 if native else 16))
        return values if native else tuple(x << 16 for x in values)

    def cycle(self, *, auto_results=True, auto_done=True, auto_ack=True, **overrides):
        o, j = self.owner, self.job
        p = o.ports()
        args = {}
        if self.read is not None:
            args["read_beat"] = ReadBeat(self.read.tag, self.read_payload(self.read), True)
        if self.results and auto_results:
            ctx, base = self.results[0]
            args["result"] = MatrixResult(ctx, physical(ctx, base))
        if auto_done and o.group_started and not o.group_done and not o.error and o.group_accepted_steps == j.k * o.contexts and o.results_received == o.contexts:
            args["matrix_done"] = MatrixDone(j.tag)
        if self.ack is not None and auto_ack:
            args["write_ack"] = self.ack
        args.update(overrides)
        base = getattr(o, "n_base", 0)
        got = o.tick(**args)
        if got["read_fire"]:
            self.read = None
        if got["read_command_fire"]:
            assert self.read is None
            self.read = got["read_command"]
            self.commands.append(self.read)
        if got["step_fire"]:
            step = got["step"]
            self.steps.append((base, step))
            if step.last:
                self.results.append((step.context, base))
        if got["result_fire"] and self.results:
            self.results.pop(0)
        if got["write_command_fire"]:
            self.write = (got["write_command"], 0)
        if got["write_data_fire"]:
            cmd, index = self.write
            self.stores.append((cmd.address + index * 64, got["write_data"]))
            self.write = (cmd, index + 1)
            if got["write_data"].last:
                self.ack = WriteAck(cmd.tag, nbytes=cmd.beats * 64)
        if got["write_ack_fire"]:
            self.ack = None
        if got["response_fire"]:
            self.response = got["response"]
        return got

    def until(self, predicate, limit=200000, **args):
        for _ in range(limit):
            if predicate():
                return
            self.cycle(**args)
        raise AssertionError("bounded test environment did not reach condition: " + self.owner.state)

    def complete(self, **args):
        self.until(lambda: self.response is not None, **args)
        return self.response


class AddressAndRouteTests(unittest.TestCase):
    def test_full_m128_k1536_addresses_unique_and_bounded(self):
        seen = {model.a_address(k, m) for k in range(1536) for m in range(128)}
        self.assertEqual(len(seen), 1536 * 128)
        self.assertEqual(max(word for _, word, _ in seen), 767)
        self.assertEqual(model.a_address(1535, 127), (8, 767, 15))
        bseen = {model.b_address(h, k, c, nh) for h in range(2) for k in range(128) for c in range(5) for nh in range(2)}
        self.assertEqual(len(bseen), 2560)
        self.assertEqual(max(w for _, w in bseen), 159)
        self.assertEqual(model.b_address(1, 1535, 4, 1), (15, 159))

    def test_output_mapping_is_bijection(self):
        coordinates = {model.output_coordinate(m, n) for m in range(128) for n in range(32)}
        self.assertEqual(coordinates, {(r, c) for r in range(16) for c in range(256)})

    def test_rne_finiteness_and_ties(self):
        self.assertEqual(model.bf16_rne(0x3f808000), 0x3f80)
        self.assertEqual(model.bf16_rne(0x3f818000), 0x3f82)
        self.assertEqual(model.bf16_rne(0xbf818000), 0xbf82)
        self.assertEqual(model.bf16_rne(0x7f7fffff), 0x7f80)
        for x in (0x7f800000, 0xff800000, 0x7fc00000):
            with self.assertRaises(ValueError):
                model.bf16_rne(x)

    def test_all_supported_dtype_combinations_and_accepted_route(self):
        for a in (False, True):
            for b in (False, True):
                for out in (False, True):
                    with self.subTest(a=a, b=b, out=out):
                        h = Harness(Job(m=16, k=32, n=32, activation_bf16=a, weight_bf16=b, output_bf16=out))
                        self.assertEqual(h.complete(), (1, None, 16 * 32 * (2 if out else 4)))
                        self.assertEqual(len(h.steps), 32)
                        self.assertEqual(h.owner.rmw_commits, 16 * 32)
                        for base, step in h.steps:
                            self.assertEqual(step.a, tuple(weight(step.k, n) for n in range(16)))
                            self.assertEqual(step.b[:128], tuple(activation(m, step.k) if m < 16 else 0 for m in range(128)))
                            self.assertEqual(step.b[128:144], tuple(weight(step.k, n) for n in range(16, 32)))
                            self.assertEqual(step.b[144:], (0,) * 112)
                            endpoints = route(step.a, step.b, True)
                            for s, (wa, ab) in enumerate(endpoints):
                                self.assertEqual(wa, tuple(weight(step.k, (s // 4) * 16 + n) for n in range(16)))
                                self.assertEqual(ab, tuple(activation(m, step.k) if m < 16 else 0 for m in range((s % 4) * 32, (s % 4 + 1) * 32)))
                        self.check_stores(h)

    def check_stores(self, h):
        per = 32 if h.job.output_bf16 else 16
        width = 2 if h.job.output_bf16 else 4
        seen = set()
        for address, beat in h.stores:
            first = (address - h.job.dst) // width
            expect = tuple(answer((first + i) // h.job.n, (first + i) % h.job.n) for i in range(per))
            if h.job.output_bf16:
                expect = tuple(model.bf16_rne(x) for x in expect)
            self.assertEqual(beat.words, expect)
            for i in range(per):
                self.assertNotIn(first + i, seen)
                seen.add(first + i)
        self.assertEqual(seen, set(range(h.job.m * h.job.n)))

    def test_five_contexts_and_n32_tail_multiple_windows(self):
        h = Harness(Job(m=128, k=16, n=192, activation_bf16=False))
        self.assertEqual(h.complete(), (1, None, 128 * 192 * 4))
        self.assertEqual(len(h.steps), 16 * 6)
        self.assertEqual({base for base, _ in h.steps}, {0, 160})
        for base, step in h.steps:
            self.assertEqual(step.a, tuple(weight(step.k, base + step.context * 32 + n) for n in range(16)))
            self.assertEqual(step.b[:128], tuple(activation(m, step.k) for m in range(128)))
        self.check_stores(h)

    def test_full_a_m128_k1536_and_last_half(self):
        h = Harness(Job(m=128, k=1536, n=32))
        self.assertEqual(h.complete(), (1, None, 128 * 32 * 4))
        self.assertEqual(h.owner.rmw_commits, 128 * 1536)
        self.assertEqual(len(h.steps), 1536)
        for k in (0, 127, 128, 255, 1408, 1535):
            step = h.steps[k][1]
            self.assertEqual(step.b[:128], tuple(activation(m, k) for m in range(128)))
        bank, word, lane = model.a_address(1535, 127)
        self.assertEqual(model.unpack16(h.owner.a_banks.words[bank][word])[lane], activation(127, 1535))


class ClockedPortTests(unittest.TestCase):
    def test_native_two_pass_rmw_reserved_write_edges(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: h.owner.ports()["read_ready"])
        first = h.cycle()
        self.assertTrue(first["read_fire"])
        self.assertEqual(len(first["a_reads"]), 16)
        self.assertEqual(len(first["a_writes"]), 0)
        self.assertFalse(h.owner.ports()["read_ready"])
        lower = h.cycle(read_command_ready=False, step_ready=False)
        self.assertEqual(len(lower["a_writes"]), 16)
        self.assertEqual(len(lower["a_reads"]), 0)
        upper_read = h.cycle(read_command_ready=False, step_ready=False)
        self.assertEqual(len(upper_read["a_reads"]), 16)
        self.assertEqual(len(upper_read["a_writes"]), 0)
        upper = h.cycle(read_command_ready=False, step_ready=False)
        self.assertEqual(len(upper["a_writes"]), 16)
        self.assertEqual(h.owner.rmw_commits, 32)

    def test_fp32_one_pass_preserves_other_rmw_lanes(self):
        h = Harness(Job(m=16, k=16, activation_bf16=False))
        h.until(lambda: h.owner.state == "execute", group_ready=False)
        self.assertEqual(h.owner.rmw_commits, 16 * 16)
        for m in range(16):
            for k in range(16):
                b, w, lane = model.a_address(k, m)
                self.assertEqual(model.unpack16(h.owner.a_banks.words[b][w])[lane], activation(m, k))

    def test_sync_response_has_reserved_fifo_credit_under_stall(self):
        h = Harness(Job(m=16, k=32, n=160))
        h.until(lambda: len(h.owner.fifo) + int(h.owner.pending is not None) == 4, step_ready=False)
        # The fourth reservation may still be a synchronous response. It must
        # enter the FIFO regardless of the downstream stall on this edge.
        h.cycle(step_ready=False)
        self.assertEqual(len(h.owner.fifo), 4)
        self.assertIsNone(h.owner.pending)
        stable = h.owner.ports()["step"]
        for _ in range(25):
            p = h.cycle(step_ready=False)
            self.assertEqual(p["step"], stable)
            self.assertFalse(p["operand_read"])
            self.assertEqual(p["reserved_after"], 4)
        self.assertEqual(h.complete(), (1, None, 16 * 160 * 4))
        self.assertEqual([(s.k, s.context) for _, s in h.steps], [(k, c) for k in range(32) for c in range(5)])
        self.assertLessEqual(h.owner.max_reserved, 4)

    def test_pending_selectors_do_not_follow_live_issue_cursor(self):
        h = Harness(Job(m=16, k=32, n=160))
        h.until(lambda: h.owner.pending is not None, step_ready=False)
        pending_k, pending_ctx = h.owner.pending[:2]
        h.owner.issue_k, h.owner.issue_context = 31, 4
        h.cycle(step_ready=False)
        self.assertEqual((h.owner.fifo[0].k, h.owner.fifo[0].context), (pending_k, pending_ctx))
        self.assertEqual(h.owner.fifo[0].a, tuple(weight(pending_k, pending_ctx * 32 + n) for n in range(16)))

    def test_b_half_not_published_before_final_last(self):
        h = Harness(Job(m=16, k=32, n=32))
        h.until(lambda: h.owner.state == "execute")
        h.until(lambda: h.owner.load_depth == 31 and h.owner.read_active is not None, group_ready=False)
        self.assertEqual(h.owner.ready, [False, False])
        h.cycle(group_ready=False, read_beat=None)
        self.assertEqual(h.owner.ready, [False, False])
        h.cycle(group_ready=False)
        self.assertEqual(h.owner.ready, [True, False])

    def test_m16_padding_cleared_after_previous_m128_job(self):
        owner = model.DenseOwnerModel()
        first = Harness(Job(m=128, k=32), owner)
        first.complete()
        read_sequence = owner.read_sequence
        second = Harness(Job(m=16, k=32, tag=2), owner)
        second.complete()
        self.assertTrue(all(step.b[16:128] == (0,) * 112 for _, step in second.steps))
        self.assertGreater(second.commands[0].tag & 0xffffffff, 0)
        self.assertGreaterEqual(second.commands[0].tag & 0xffffffff, read_sequence)

    def test_unused_b_half_depth_and_context_sentinels_do_not_leak(self):
        for k, n in ((32, 32), (144, 160), (256, 160)):
            with self.subTest(k=k, n=n):
                o = model.DenseOwnerModel()
                for bank in range(16):
                    for word in range(160):
                        # All unloaded halves, depths and N contexts contain
                        # recognizable NaN patterns, never an implicit zero.
                        o.b_banks.words[bank][word] = model.pack16((0x7f81 + (word + bank) % 126,) * 16)
                h = Harness(Job(m=16, k=k, n=n, activation_bf16=False), o)
                self.assertEqual(h.complete()[1], None)
                for base, step in h.steps:
                    first_n = base + step.context * 32
                    self.assertEqual(step.a, tuple(weight(step.k, first_n + i) for i in range(16)))
                    self.assertEqual(step.b[128:144], tuple(weight(step.k, first_n + 16 + i) for i in range(16)))

    def test_backpressure_holds_write_data_and_completion(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: h.owner.write_state == "data", write_data_ready=False)
        stable = h.owner.ports()["write_data"]
        for _ in range(20):
            self.assertEqual(h.cycle(write_data_ready=False)["write_data"], stable)
            self.assertIsNone(h.owner.ports()["response"])
        h.until(lambda: h.owner.state == "finish", response_ready=False)
        response = h.owner.ports()["response"]
        for _ in range(10):
            self.assertEqual(h.cycle(response_ready=False)["response"], response)
        h.cycle()
        self.assertEqual(h.owner.responses, 1)

    def test_write_burst_splits_at_one_kib_boundary(self):
        h = Harness(Job(m=16, k=32, dst=0x8003c0))
        seen = []
        while h.response is None:
            p = h.cycle()
            if p["write_command_fire"]:
                cmd = p["write_command"]
                seen.append(cmd)
                self.assertLessEqual((cmd.address & 1023) + cmd.beats * 64, 1024)
        self.assertEqual(seen[0].beats, 1)
        self.assertEqual(seen[1].beats, 1)
        self.assertEqual(h.response, (1, None, 16 * 32 * 4))


class FailureTests(unittest.TestCase):
    def failed_locked(self, h):
        h.until(lambda: h.response is not None, auto_done=False,
                matrix_done=MatrixDone(h.job.tag) if h.owner.group_started else None)
        self.assertIsNotNone(h.response[1])
        self.assertEqual(h.owner.state, "locked")
        self.assertEqual(h.owner.ready, [False, False])
        for _ in range(5):
            p = h.owner.tick(job=Job(tag=9))
            self.assertFalse(p["job_ready"])
            self.assertIsNone(p["response"])
        self.assertEqual(h.owner.responses, 1)

    def test_invalid_shapes(self):
        for job in (Job(kind="Prefix"), Job(m=32), Job(k=0), Job(k=1552), Job(k=17), Job(k=16), Job(n=16), Job(a=1),
                    Job(dst=0x100000), Job(dst=0x400040), Job(dst=2**56 - 64), Job(write_bytes=64)):
            with self.subTest(job=job):
                h = Harness(job)
                self.failed_locked(h)

    def test_read_bad_tag_and_error_never_commit_or_publish(self):
        for tag_bad, error in ((True, False), (False, True)):
            h = Harness(Job(m=16, k=32))
            h.until(lambda: h.owner.ports()["read_ready"])
            cmd = h.read
            h.cycle(read_beat=ReadBeat(cmd.tag + int(tag_bad), (0x3f80,) * 32, True, error))
            self.assertEqual(h.owner.rmw_commits, 0)
            self.assertIsNone(h.owner.read_active)
            self.failed_locked(h)

    def test_missing_response_waits_and_bad_last_retires_unique_beat(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: h.owner.ports()["read_ready"])
        tag = h.read.tag
        for _ in range(12):
            h.cycle(read_beat=None)
            self.assertIsNotNone(h.owner.read_active)
            self.assertIsNone(h.owner.ports()["response"])
        h.cycle(read_beat=ReadBeat(tag, (0x3f80,) * 32, False))
        self.assertIsNone(h.owner.read_active)
        self.failed_locked(h)

    def test_nonfinite_a_and_b_and_short_beats(self):
        for kind, native, value, short in (("a", True, 0x7f80, False), ("a", False, 0x7fc00000, False),
                                          ("b", True, 0xff80, False), ("b", False, 0x7f800000, False),
                                          ("a", True, 0x3f80, True)):
            with self.subTest(kind=kind, native=native, short=short):
                h = Harness(Job(m=16, k=32, activation_bf16=native, weight_bf16=native))
                h.until(lambda: h.read is not None and h.read.kind == kind and h.owner.ports()["read_ready"])
                count = (32 if native else 16) - int(short)
                h.cycle(read_beat=ReadBeat(h.read.tag, (value,) * count, True))
                self.failed_locked(h)

    def test_bad_final_b_last_cannot_publish_half(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: h.owner.state == "execute" and h.owner.load_depth == 31 and h.owner.read_active is not None)
        cmd = h.read
        h.cycle(read_beat=ReadBeat(cmd.tag, h.read_payload(cmd), False))
        self.assertEqual(h.owner.ready, [False, False])
        h.cycle(matrix_done=MatrixDone(h.job.tag))
        self.failed_locked(h)

    def test_result_order_last_error_and_nonfinite(self):
        for mode in ("context", "last", "error", "nonfinite", "bf16_overflow"):
            h = Harness(Job(m=16, k=32, output_bf16=mode == "bf16_overflow"))
            h.until(lambda: len(h.steps) == 32, auto_results=False)
            values = physical(0)
            if mode in ("nonfinite", "bf16_overflow"):
                rows = [list(r) for r in values]
                rows[0][0] = 0x7f800000 if mode == "nonfinite" else 0x7f7f8000
                values = tuple(tuple(r) for r in rows)
            r = MatrixResult(int(mode == "context"), values, mode != "last", mode == "error")
            h.cycle(auto_results=False, result=r)
            self.failed_locked(h)

    def test_valid_context_returned_out_of_order_is_rejected(self):
        h = Harness(Job(m=16, k=32, n=64))
        h.until(lambda: len(h.steps) == 64, auto_results=False)
        h.cycle(auto_results=False, result=MatrixResult(1, physical(1)))
        self.failed_locked(h)

    def test_fp32_input_rne_finite_threshold_both_signs(self):
        for sign in (0, 0x80000000):
            for kind in ("a", "b"):
                for magnitude, valid in ((0x7f7f7fff, True), (0x7f7f8000, False)):
                    with self.subTest(sign=sign, kind=kind, magnitude=magnitude):
                        h = Harness(Job(m=16, k=32, activation_bf16=False, weight_bf16=False))
                        h.until(lambda: h.read is not None and h.read.kind == kind and h.owner.ports()["read_ready"])
                        h.cycle(read_beat=ReadBeat(h.read.tag, (sign | magnitude,) * 16, True))
                        if valid:
                            self.assertIsNone(h.owner.error)
                            self.assertEqual(h.complete()[1], None)
                        else:
                            self.assertEqual(h.owner.rmw_commits, 0 if kind == "a" else 16 * 32)
                            self.failed_locked(h)

    def test_padded_result_cells_are_ignored_for_m16(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: len(h.steps) == 32, auto_results=False)
        h.cycle(auto_results=False, result=MatrixResult(0, physical(0, padding_nan=True)))
        self.assertEqual(h.complete(), (1, None, 16 * 32 * 4))

    def test_missing_ack_and_matrix_done_cannot_succeed(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: h.owner.write_state == "ack", auto_ack=False, auto_done=False)
        for _ in range(30):
            h.cycle(auto_ack=False, auto_done=False)
            self.assertIsNone(h.owner.ports()["response"])
        h.until(lambda: h.owner.written == 1, auto_done=False)
        for _ in range(30):
            h.cycle(auto_done=False)
            self.assertIsNone(h.owner.ports()["response"])
        self.assertEqual(h.complete(), (1, None, 16 * 32 * 4))

    def test_write_ack_wrong_tag_error_or_byte_count(self):
        for mode in ("tag", "error", "bytes"):
            h = Harness(Job(m=16, k=32))
            h.until(lambda: h.owner.write_state == "ack", auto_ack=False)
            ack = WriteAck(h.ack.tag + int(mode == "tag"), mode == "error", 64 if mode == "bytes" else 128)
            h.cycle(auto_ack=False, write_ack=ack)
            self.assertEqual(h.owner.write_state, "idle")
            self.failed_locked(h)

    def test_failure_drains_accepted_write_then_abort_done(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: h.owner.write_state == "data", auto_done=False, write_data_ready=False)
        h.cycle(auto_done=False, write_data_ready=False, matrix_done=MatrixDone(h.job.tag + 1))
        self.assertTrue(h.owner.group_done)
        h.until(lambda: h.owner.write_state == "idle", auto_done=False)
        self.assertEqual(len(h.stores), 2)
        self.failed_locked(h)

    def test_fifo_drains_one_entry_per_clock_after_failure(self):
        h = Harness(Job(m=16, k=32, n=160))
        h.until(lambda: len(h.owner.fifo) == 4, step_ready=False)
        h.cycle(step_ready=False, matrix_done=MatrixDone(h.job.tag + 1))
        self.assertEqual(len(h.owner.fifo), 4)
        for remaining in (3, 2, 1, 0):
            h.cycle(step_ready=False, auto_done=False)
            self.assertEqual(len(h.owner.fifo), remaining)
            if remaining:
                self.assertIsNone(h.owner.ports()["response"])
        self.failed_locked(h)

    def test_group_handshake_on_bad_b_response_edge_still_needs_abort(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: h.read is not None and h.read.kind == "b", group_ready=False)
        cmd = h.read
        p = h.cycle(group_ready=True, read_beat=ReadBeat(cmd.tag, (), True, True))
        self.assertTrue(p["group_fire"])
        self.assertTrue(h.owner.group_started)
        self.assertTrue(h.owner.ports()["abort"])
        self.assertIsNone(h.owner.ports()["response"])
        h.cycle(matrix_done=MatrixDone(h.job.tag), auto_done=False)
        self.failed_locked(h)

    def test_bad_prefetch_response_does_not_cancel_same_edge_step_fire(self):
        h = Harness(Job(m=16, k=256))
        h.until(lambda: h.owner.ports()["step"] is not None and h.read is not None and
                h.read.kind == "b" and h.owner.load_k == 128, step_ready=False)
        before = h.owner.accepted_steps
        cmd = h.read
        p = h.cycle(step_ready=True, read_beat=ReadBeat(cmd.tag, (), True, True), auto_done=False)
        self.assertTrue(p["step_fire"])
        self.assertEqual(h.owner.accepted_steps, before + 1)
        self.assertTrue(h.owner.ports()["abort"])
        h.cycle(matrix_done=MatrixDone(h.job.tag), auto_done=False)
        self.failed_locked(h)

    def test_read_error_does_not_cancel_accepted_write_request(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: h.owner.write_state == "request", write_command_ready=False, auto_done=False)
        # Fault injection presents two legal port obligations concurrently;
        # this does not claim the conservative scheduler normally overlaps them.
        cmd = model.ReadCommand("b", h.job.b, 1, (h.job.tag << 32) | h.owner.read_sequence)
        h.owner.read_active = (cmd, 0)
        h.read = cmd
        p = h.cycle(write_command_ready=True, read_beat=ReadBeat(cmd.tag, (), True, True), auto_done=False)
        self.assertTrue(p["read_fire"])
        self.assertTrue(p["write_command_fire"])
        self.assertEqual(h.owner.write_state, "data")
        h.until(lambda: h.owner.write_state == "idle", auto_done=False)
        self.assertEqual(len(h.stores), 2)
        self.assertEqual(h.owner.write_bytes, 128)
        self.assertIsNone(h.owner.ports()["response"])
        h.cycle(matrix_done=MatrixDone(h.job.tag), auto_done=False)
        self.failed_locked(h)

    def test_fault_on_ack_edge_preserves_committed_byte_count(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: h.owner.write_state == "ack", auto_ack=False, auto_done=False)
        p = h.cycle(write_ack=h.ack, matrix_done=MatrixDone(h.job.tag, True), auto_done=False)
        self.assertTrue(p["write_ack_fire"])
        self.assertEqual(h.owner.write_bytes, 128)
        self.failed_locked(h)

    def test_result_on_terminal_step_edge_is_rejected(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: len(h.steps) == 31 and h.owner.ports()["step"] is not None, auto_results=False)
        self.assertTrue(h.owner.ports()["step"].last)
        p = h.cycle(result=MatrixResult(0, physical(0)), auto_results=False)
        self.assertTrue(p["step_fire"])
        self.assertTrue(p["result_fire"])
        # The real retained matrix has positive result latency. The owner
        # bitmap deliberately recognizes only an earlier accepted terminal.
        self.assertIn("before final accepted step", h.owner.error)
        self.failed_locked(h)

    def test_pending_sram_response_enqueues_on_same_edge_read_fault(self):
        h = Harness(Job(m=16, k=256))
        h.until(lambda: h.owner.pending is not None and h.read is not None and
                h.read.kind == "b" and h.owner.load_k == 128, step_ready=False)
        before = len(h.owner.fifo)
        pending_k, pending_context = h.owner.pending[:2]
        p = h.cycle(step_ready=False, read_beat=ReadBeat(h.read.tag, (), True, True), auto_done=False)
        self.assertTrue(p["operand_response"])
        self.assertEqual(len(h.owner.fifo), before + 1)
        self.assertEqual((h.owner.fifo[-1].k, h.owner.fifo[-1].context), (pending_k, pending_context))
        self.assertIsNotNone(h.owner.error)
        h.cycle(matrix_done=MatrixDone(h.job.tag), auto_done=False)
        self.failed_locked(h)

    def test_done_cannot_use_result_captured_on_same_edge(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: len(h.steps) == 32, auto_results=False, auto_done=False)
        self.assertEqual(h.owner.results_received, 0)
        p = h.cycle(result=MatrixResult(0, physical(0)), matrix_done=MatrixDone(h.job.tag),
                    auto_results=False, auto_done=False)
        self.assertTrue(p["result_fire"])
        self.assertEqual(h.owner.results_received, 1)
        self.assertIn("matrix done before", h.owner.error)
        self.failed_locked(h)

    def test_done_cannot_use_terminal_step_accepted_on_same_edge(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: len(h.steps) == 31 and h.owner.ports()["step"] is not None,
                auto_results=False, auto_done=False)
        # Forge the independent captured-count register to isolate the old
        # accepted-step/FIFO prerequisites; no real result arrives this early.
        h.owner.results_received = h.owner.contexts
        p = h.cycle(matrix_done=MatrixDone(h.job.tag), auto_results=False, auto_done=False)
        self.assertTrue(p["step_fire"])
        self.assertEqual(h.owner.group_accepted_steps, 32)
        self.assertFalse(h.owner.fifo)
        self.assertIn("matrix done before", h.owner.error)
        self.failed_locked(h)

    def test_enabled_poison_blocks_kernel_admission_for_every_owner(self):
        h = Harness(Job(kind="Unsupported"))
        self.failed_locked(h)
        for selected in ("Dense", "OtherMatrix", "Vector", "Memory"):
            with self.subTest(selected_owner=selected):
                self.assertFalse(model.kernel_can_start(enable_transposed_dense=True,
                                 transposed_reset_required=h.owner.ports()["reset_required"],
                                 selected_owner_ready=True))
        h.owner.tick(local_reset=True)
        self.assertFalse(model.kernel_can_start(enable_transposed_dense=True,
                         transposed_reset_required=h.owner.ports()["reset_required"]))
        h.owner.tick(coordinated_reset=True)
        self.assertTrue(model.kernel_can_start(enable_transposed_dense=True,
                        transposed_reset_required=h.owner.ports()["reset_required"]))

    def test_default_disabled_profile_preserves_legacy_kernel_admission(self):
        self.assertTrue(model.kernel_can_start(transposed_reset_required=True))
        self.assertFalse(model.kernel_can_start(transposed_reset_required=True, selected_owner_ready=False))
        self.assertTrue(model.kernel_can_start(enable_transposed_dense=True, transposed_reset_required=False))

    def test_early_done_and_early_result_are_protocol_failures(self):
        for early_result in (False, True):
            h = Harness(Job(m=16, k=32))
            h.until(lambda: h.owner.group_started, step_ready=False)
            if early_result:
                h.cycle(result=MatrixResult(0, physical(0)), auto_results=False, step_ready=False)
            else:
                h.cycle(matrix_done=MatrixDone(h.job.tag), step_ready=False)
            self.failed_locked(h)

    def test_exact_total_bytes_not_only_ack_count(self):
        h = Harness(Job(m=16, k=32))
        h.until(lambda: h.owner.written == 1, auto_done=False)
        h.owner.write_bytes -= 64  # fault-inject the accounting register
        h.cycle(matrix_done=MatrixDone(h.job.tag))
        self.failed_locked(h)

    def test_local_reset_never_creates_backend_freshness(self):
        o = model.DenseOwnerModel()
        o.tick(local_reset=True)
        o.tick()
        self.assertEqual(o.state, "locked")
        for _ in range(3):
            o.tick(local_reset=True, job=Job())
            self.assertEqual(o.state, "locked")
        o.tick(coordinated_reset=True)
        self.assertTrue(o.ports()["job_ready"])
        h = Harness(Job(m=16, k=32), o)
        self.assertEqual(h.complete(), (1, None, 16 * 32 * 4))


if __name__ == "__main__":
    unittest.main(verbosity=2)
