"""Actual bank/control regression. Opaque Matrix words are not numerical proof."""
from collections import deque
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("ffn_window_model", Path(__file__).with_name("model.py"))
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def request(rows=16, cols=32, ng=0, slot=0, reuse=False, k=32, native=True, **kwargs):
    job = m.Job(m=rows, k=k, n=8960, activation_bf16=native, weight_bf16=native,
                b=0x400000 + slot*0x400000, dst=0x2000000, **kwargs)
    return m.FfnWindowRequest(job, 7, ng, cols, slot, reuse)


def owner(**kwargs):
    return m.FfnWindowOwnerModel(m.PrefixWorkspace(0x10000000, 8960//32*16384, 11),
                                 enable_ffn_window=True, enable_ffn_tiles=True, **kwargs)


def physical_result(context, salt=0):
    return tuple(tuple(0x3e000000 + salt*0x100000 + context*0x10000 + bank*256 + i
                       for i in range(256)) for bank in range(16))


class Harness:
    """One controlled DMA and a bounded two-entry Matrix result queue."""
    def __init__(self, q=None, instance=None):
        self.owner = owner() if instance is None else instance
        self.read = None
        self.results = deque()
        self.commands = []
        self.steps = []
        self.events = []
        self.completion = None
        self.max_results = 0
        self.q = None
        if q is not None:
            self.submit(q)

    def submit(self, q, **kwargs):
        self.q = q
        self.completion = None
        e = self.owner.tick(window=q, **kwargs)
        assert e["window_fire"]
        return e

    def source(self, kind, row, column):
        native = self.q.job.activation_bf16 if kind == "a" else self.q.job.weight_bf16
        bf16 = (0x3e00 + (row*131+column*17)%128 if kind == "a"
                else 0x3d00+(row*7+column)%256)
        return bf16 if native else (bf16 << 16) + 0x7fff

    def read_words(self, command):
        j = self.q.job
        native = j.activation_bf16 if command.kind == "a" else j.weight_bf16
        base, stride = (j.a, j.k) if command.kind == "a" else (j.b, j.n)
        first = (command.address-base)//(2 if native else 4)
        return tuple(self.source(command.kind, (first+i)//stride, (first+i)%stride)
                     for i in range(32 if native else 16))

    def expected_operand(self, step):
        j = self.q.job
        act = tuple(self.source("a", row, step.k) if row < j.m else 0 for row in range(128))
        weight = tuple(self.source("b", step.k, self.q.ng+32*step.context+col) for col in range(32))
        if not j.activation_bf16:
            act = tuple(m.down.bf16_rne(x) if x else 0 for x in act)
        if not j.weight_bf16:
            weight = tuple(m.down.bf16_rne(x) for x in weight)
        return weight[:16], act + weight[16:] + (0,)*112

    def cycle(self, *, dma=True, done=True, produce=True, **kwargs):
        o = self.owner
        p = o.ports()
        args = {}
        if dma and self.read is not None:
            args["read_beat"] = m.ReadBeat(self.read.tag, self.read_words(self.read), True)
        if produce and self.results:
            args["result"] = self.results[0]
        if p["step"] is not None and p["step"].last and len(self.results) >= 2:
            args["step_ready"] = False
        if done and o.group_started and not o.group_done and (
            o.error or (o.group_accepted_steps == self.q.job.k*self.q.cols//32 and
                        o.results_received == self.q.cols//32)):
            args["matrix_done"] = m.MatrixDone(self.q.job.tag, bool(o.error))
        args.update(kwargs)
        e = o.tick(**args)
        if e.get("read_fire"):
            self.read = None
        if e.get("read_command_fire"):
            assert self.read is None
            self.read = e["read_command"]
            self.commands.append(self.read)
        if e.get("result_fire") and self.results:
            self.results.popleft()
        if e.get("step_fire"):
            step = e["step"]
            assert (step.a, step.b) == self.expected_operand(step), "actual bank packet mismatch"
            self.steps.append(step)
            if step.last:
                self.results.append(m.MatrixResult(step.context, physical_result(step.context, self.q.slot)))
        self.max_results = max(self.max_results, len(self.results))
        assert self.max_results <= 2
        if e.get("window_result_fire"):
            self.completion = e["window_result"]
        assert e.get("write_command") is None
        assert e.get("write_data") is None
        assert e.get("response") is None
        for key in ("a_reads", "a_writes", "b_reads", "b_writes"):
            assert len(e.get(key, {})) <= 16
        self.events.append(e)
        return e

    def until(self, predicate, limit=100000, **kwargs):
        for _ in range(limit):
            if predicate():
                return
            self.cycle(**kwargs)
        raise AssertionError(("bounded test timeout", self.owner.state, self.owner.error,
                              self.owner.adapter_phase, self.owner.results_received,
                              self.owner.written))

    def finish(self, **kwargs):
        self.until(lambda: self.completion is not None, **kwargs)
        return self.completion


def consume_tile(o, q):
    values = []
    for index in range(q.job.m//16*q.cols):
        e = o.tick(tile_read=m.Read(q.slot, q.identity, q.ng, index))
        assert e["tile"]["read_fire"]
        assert not o.tick()["tile"]["response_fire"]
        e = o.tick()
        assert e["tile"]["response_fire"]
        values.append(e["tile"]["response"].words)
    return values


def release(o, q):
    return o.tick(tile_control=m.Control(2, q.slot, q.identity, q.ng,
                                         q.job.m, q.cols, True))


class WindowModelTests(unittest.TestCase):
    def test_matrix_producer_bijection_all_legal_shapes(self):
        for rows in (16, 128):
            for cols in (32, 64, 96, 128, 160):
                groups = rows//16
                indices = [m.producer_index(q, rows, cols) for q in range(groups*cols)]
                self.assertEqual(sorted(indices), list(range(groups*cols)))
                for q, index in enumerate(indices):
                    context, rest = divmod(q, 32*groups)
                    group, column = divmod(rest, 32)
                    self.assertEqual(index, group*cols + context*32 + column)
        with self.assertRaises(ValueError):
            m.producer_index(256, 128, 32)

    def test_first_load_real_packets_fence_and_exact_typed_completion(self):
        q = request()
        h = Harness(q)
        h.until(lambda: h.owner.a_rmw_pending is not None and h.owner.a_row == 15 and h.owner.a_beat == 1)
        self.assertIsNone(h.owner.lease)
        h.until(lambda: h.owner.state == "a_fence")
        self.assertIsNone(h.owner.lease)
        self.assertEqual(h.owner.rmw_commits, q.job.m*q.job.k)
        self.assertTrue(h.cycle()["a_fence"])
        self.assertEqual(h.owner.lease, m.ALease.for_request(q))
        result = h.finish()
        self.assertEqual(result, m.FfnWindowResult(q.job.tag, 7, 0, 0, 16, 32, None, True, 32, 0))
        self.assertEqual(h.owner.traffic["a_read_bytes"], 16*32*2)
        self.assertEqual(h.owner.traffic["b_read_bytes"], 32*32*2)
        self.assertEqual(len(h.steps), 32)
        self.assertTrue(h.owner.tiles.tags[0].sealed)
        self.assertIs(h.owner.tiles.banks, h.owner.a_banks)
        self.assertEqual(h.owner.a_banks.depth, 1376)
        self.assertEqual(h.owner.b_banks.depth, 160)

    def test_gate_up_reuse_same_physical_a_no_reload_then_next_window(self):
        gate = request(cols=64)
        h = Harness(gate)
        h.finish()
        banks = h.owner.a_banks
        saved_low = tuple(tuple(bank[:768]) for bank in banks.words)
        saved_gate = tuple(tuple(bank[768:928]) for bank in banks.words)
        before = dict(h.owner.traffic)
        start_commands = len(h.commands)
        up = request(cols=64, slot=1, reuse=True)
        h.submit(up)
        h.finish()
        self.assertIs(h.owner.a_banks, banks)
        self.assertEqual(tuple(tuple(bank[:768]) for bank in banks.words), saved_low)
        self.assertEqual(tuple(tuple(bank[768:928]) for bank in banks.words), saved_gate)
        self.assertEqual(h.owner.traffic["a_read_bytes"], before["a_read_bytes"])
        self.assertEqual({c.kind for c in h.commands[start_commands:]}, {"b"})
        self.assertEqual(h.owner.a_fences, 1)
        for q in (gate, up):
            got = consume_tile(h.owner, q)
            for index, words in enumerate(got):
                group, column = divmod(index, q.cols)
                context, local = divmod(column, 32)
                expected = physical_result(context, q.slot)
                self.assertEqual(words, tuple(expected[local%16][128*(local//16)+16*group+l]
                                              for l in range(16)))
            self.assertTrue(release(h.owner, q)["tile"]["ctl_fire"])
        h.submit(request(cols=32, ng=64, reuse=True))
        h.finish()
        self.assertEqual(h.owner.traffic["a_read_bytes"], before["a_read_bytes"])
        self.assertEqual(tuple(tuple(bank[:768]) for bank in banks.words), saved_low)

    def test_tail96_m128_full_global_stride_and_row_group_reads(self):
        q = request(rows=128, cols=96, ng=8864)
        h = Harness(q)
        result = h.finish()
        self.assertEqual((result.produced_beats, result.ddr_write_bytes), (768, 0))
        bcommands = [c.address for c in h.commands if c.kind == "b"]
        self.assertEqual(bcommands[:3], [q.job.b+(q.ng+i*32)*2 for i in range(3)])
        self.assertEqual(bcommands[3], q.job.b+(8960+q.ng)*2)
        self.assertEqual(len(bcommands)*64, 32*96*2)
        got = consume_tile(h.owner, q)
        self.assertEqual(len(got), 768)
        for index, words in enumerate(got):
            group, column = divmod(index, 96)
            context, local = divmod(column, 32)
            value = physical_result(context)
            self.assertEqual(words, tuple(value[local%16][128*(local//16)+16*group+l]
                                          for l in range(16)))

    def test_all_five_contexts_stream_before_done_with_two_result_slots(self):
        h = Harness(request(rows=128, cols=160))
        h.until(lambda: h.owner.results_received == 5, done=False)
        self.assertFalse(h.owner.group_done)
        self.assertIsNone(h.owner.ports()["window_result"])
        self.assertEqual(h.max_results, 2)
        self.assertTrue(any(e["result_fire"] for e in h.events))
        self.assertEqual(h.finish().produced_beats, 1280)

    def test_source_fp32_conversion_and_split_workspace_ignored(self):
        o = owner()
        o.workspace = replace(o.workspace, split_k=128)
        q = request(k=160, native=False, cols=64)
        h = Harness(q, o)
        self.assertIsNone(h.finish().status)
        self.assertEqual(o.traffic["a_read_bytes"], 16*160*4)
        self.assertEqual(o.traffic["b_read_bytes"], 160*64*4)
        self.assertEqual(len(h.steps), 320)
        self.assertEqual(sum(e["group_fire"] for e in h.events), 1)

    def test_full_validation_before_bank_or_dma_access(self):
        good = request()
        bad = [replace(good, identity=0), replace(good, identity=2**32),
               replace(good, ng=1), replace(good, ng=65504, cols=160),
               replace(good, cols=16), replace(good, slot=2), replace(good, reuse_a=1),
               replace(good, job=replace(good.job, k=1568)),
               replace(good, job=replace(good.job, output_bf16=True)),
               replace(good, job=replace(good.job, activation_bf16=1)),
               replace(good, job=replace(good.job, write_bytes=64)),
               replace(good, job=replace(good.job, a=1)),
               replace(good, job=replace(good.job, b=2**56-64)),
               replace(good, job=replace(good.job, dst=good.job.b+100*64)),
               replace(good, reuse_a=True)]
        for q in bad:
            with self.subTest(q=q):
                h = Harness(q)
                completion = h.finish()
                self.assertIsNotNone(completion.status)
                self.assertFalse(completion.committed)
                self.assertEqual(completion.produced_beats, 0)
                self.assertFalse(h.commands)
                self.assertFalse(any(e["a_reads"] or e["a_writes"] or e["b_reads"] or e["b_writes"]
                                     for e in h.events))
        o = owner()
        o.workspace = None
        h = Harness(good, o)
        self.assertIn("workspace", h.finish().status)

    def test_changed_lease_metadata_rejects_before_access(self):
        original = request()
        changes = (dict(a=original.job.a+64), dict(activation_bf16=False), dict(m=128), dict(k=64))
        for changeset in changes + ({},):
            h = Harness(original)
            h.finish()
            candidate = request(slot=1, reuse=True)
            candidate = replace(candidate, job=replace(candidate.job, **changeset))
            if not changeset:
                candidate = replace(candidate, identity=8)
            before = tuple(tuple(b) for b in h.owner.a_banks.words)
            start = len(h.commands)
            h.submit(candidate)
            completion = h.finish()
            self.assertIn("lease", completion.status)
            self.assertEqual(len(h.commands), start)
            self.assertEqual(tuple(tuple(b) for b in h.owner.a_banks.words), before)

    def test_backpressure_no_premature_production_seal_or_completion(self):
        h = Harness(request())
        h.until(lambda: h.owner.final_value is not None)
        before = h.owner.tiles.tags[0].produced
        for _ in range(12):
            e = h.cycle(tile_accept_ready=False, window_result_ready=False)
            self.assertFalse(e["tile"]["write_fire"])
            self.assertFalse(e["window_result_fire"])
            self.assertEqual(h.owner.tiles.tags[0].produced, before)
        h.until(lambda: h.owner.tiles.pending is not None)
        produced = h.owner.tiles.tags[0].produced
        self.assertFalse(h.owner.tiles.tags[0].sealed)
        e = h.cycle(tile_accept_ready=False)
        self.assertTrue(e["tile"]["rmw_commit"])
        self.assertEqual(h.owner.tiles.tags[0].produced, produced+1)
        h.until(lambda: h.owner.state == "seal", window_result_ready=False)
        self.assertIsNone(h.owner.ports()["window_result"])
        h.cycle(window_result_ready=False)
        self.assertEqual(h.owner.state, "check_seal")
        self.assertIsNone(h.owner.ports()["window_result"])
        h.cycle(window_result_ready=False)
        held = h.owner.ports()["window_result"]
        for _ in range(8):
            self.assertEqual(h.cycle(window_result_ready=False)["window_result"], held)
        self.assertEqual(h.finish(), held)

    def test_operand_response_drains_before_rmw_and_fifo_credit_is_reserved(self):
        h = Harness(request(cols=160))
        h.until(lambda: h.owner.pending is not None)
        for _ in range(20):
            h.cycle(step_ready=False)
        self.assertEqual(len(h.owner.fifo), 4)
        self.assertIsNone(h.owner.pending)
        h.finish()
        self.assertEqual(h.owner.max_reserved, 4)
        for e in h.events:
            if e["tile"]["write_fire"]:
                self.assertFalse(e["operand_response"] or e["operand_read"])
                self.assertLessEqual(e["reserved_after"], 4)

    def test_abort_drains_accepted_dma_without_a_lease(self):
        h = Harness(request())
        h.until(lambda: h.read is not None)
        h.cycle(abort=True, dma=False)
        for _ in range(9):
            h.cycle(dma=False)
            self.assertIsNone(h.owner.ports()["window_result"])
            self.assertIsNone(h.owner.lease)
        result = h.finish()
        self.assertFalse(result.committed)
        self.assertIn("abort", result.status)
        self.assertEqual(h.owner.state, "locked")

    def test_abort_drains_accepted_rmw_and_waits_matrix_terminal(self):
        h = Harness(request(cols=64))
        h.until(lambda: h.owner.tiles.pending is not None, done=False)
        produced = h.owner.tiles.tags[0].produced
        e = h.cycle(abort=True, done=False)
        self.assertTrue(e["tile"]["rmw_commit"])
        self.assertEqual(h.owner.tiles.tags[0].produced, produced+1)
        for _ in range(9):
            h.cycle(done=False)
            self.assertIsNone(h.owner.ports()["window_result"])
        result = h.finish()
        self.assertFalse(result.committed)
        self.assertIsNone(h.owner.lease)

    def test_matrix_protocol_failures_and_dma_error_never_commit(self):
        faults = (lambda r: replace(r, context=1), lambda r: replace(r, last=False),
                  lambda r: replace(r, error=True),
                  lambda r: replace(r, value=((0x7fc00000,)*256,)*16))
        for fault in faults:
            h = Harness(request())
            h.until(lambda: bool(h.results))
            h.results[0] = fault(h.results[0])
            self.assertFalse(h.finish().committed)
            self.assertIsNone(h.owner.lease)
        h = Harness(request())
        h.until(lambda: h.read is not None)
        h.cycle(read_beat=m.ReadBeat(h.read.tag, (0x3f80,)*32, True, True))
        self.assertIn("DMA", h.finish().status)

    def test_abort_at_seal_check_cannot_publish_success_but_held_result_is_stable(self):
        h = Harness(request())
        h.until(lambda: h.owner.state == "check_seal", window_result_ready=False)
        h.cycle(abort=True, window_result_ready=False)
        self.assertFalse(h.owner.ports()["window_result"].committed)
        h = Harness(request())
        h.until(lambda: h.owner.ports()["window_result"] is not None, window_result_ready=False)
        held = h.owner.ports()["window_result"]
        h.cycle(abort=True, window_result_ready=False)
        self.assertEqual(h.owner.ports()["window_result"], held)
        self.assertTrue(h.owner.ports()["reset_required"])
        self.assertIsNone(h.owner.lease)

    def test_reset_preserves_cells_but_invalidates_stale_continuation(self):
        h = Harness(request())
        h.finish()
        before = tuple(tuple(b) for b in h.owner.a_banks.words)
        h.owner.tick(coordinated_reset=True)
        self.assertIsNone(h.owner.lease)
        self.assertEqual(tuple(tuple(b) for b in h.owner.a_banks.words), before)
        self.assertFalse(h.owner.tiles.leased)
        h.submit(request(slot=1, reuse=True))
        self.assertIn("lease", h.finish().status)

    def test_low_write_and_kernel_invalidation_revoke_lease(self):
        for mode in ("write", "kernel"):
            h = Harness(request())
            h.finish()
            if mode == "write":
                e = h.owner.tick(dense_writes=[(0, 0, 17)])
                self.assertEqual(e["a_writes"], {0: 0})
            else:
                h.owner.tick(invalidate_lease=True)
            self.assertIsNone(h.owner.lease)
            h.submit(request(slot=1, reuse=True))
            self.assertIn("lease", h.finish().status)

    def test_default_off_and_normal_mode_source_compatibility(self):
        with self.assertRaises(ValueError):
            m.FfnWindowOwnerModel(enable_ffn_window=True)
        self.assertFalse(m.FfnWindowOwnerModel().ports()["window_ready"])
        path = Path(__file__).resolve().parent.parent / "transposed_down/test_model.py"
        spec = importlib.util.spec_from_file_location("ffn_window_ordinary_harness", path)
        previous = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = previous
        spec.loader.exec_module(previous)
        h = previous.Harness(n=32, m_rows=16, k=32, split_k=2560)
        h.owner = m.FfnWindowOwnerModel(h.workspace)
        h.owner.tick(job=h.job)
        h.until(lambda: h.response is not None)
        self.assertIsNone(h.response[1])
        self.assertEqual(h.response[2], 16*32*4)
        self.assertIsNone(h.owner.lease)

    def test_matrix_order_default_old_order_and_slot2_rejected(self):
        b = m.TileBankModel()
        c = m.Control(0, 0, 5, 0, 128, 64)
        b.tick(control=c)
        for index in range(64*8):
            self.assertTrue(b.tick(write=m.Write(0, 5, 0, index, (0x3f000000,)*16))["write_fire"])
            b.tick()
        b.tick(control=replace(c, op=1))
        self.assertFalse(b.poison)
        self.assertFalse(b.tags[0].matrix_producer_order)
        b = m.TileBankModel()
        e = b.tick(control=m.Control(0, 2, 5, 0, 16, 32, True))
        self.assertTrue(b.poison)
        self.assertFalse(e["reads"] or e["writes"])

    def test_window_priority_and_same_edge_invalidation(self):
        h = Harness()
        e = h.submit(request(), job=request().job)
        self.assertTrue(e["window_fire"])
        self.assertIsNone(h.finish().status)
        h.submit(request(slot=1, reuse=True), invalidate_lease=True)
        self.assertIn("lease", h.finish().status)

    def test_a_fence_same_edge_kernel_invalidation_never_regrants_lease(self):
        h = Harness(request())
        h.until(lambda: h.owner.state == "a_fence")
        h.cycle(invalidate_lease=True)
        self.assertIsNone(h.owner.lease)
        self.assertIsNone(h.finish().status)
        h.submit(request(slot=1, reuse=True))
        self.assertIn("lease", h.finish().status)

    def test_rejected_live_target_reports_zero_new_production(self):
        q = request()
        h = Harness(q)
        h.finish()
        self.assertEqual(h.owner.tiles.tags[0].produced, 32)
        h.submit(replace(q, reuse_a=True))
        result = h.finish()
        self.assertFalse(result.committed)
        self.assertEqual(result.produced_beats, 0)
        self.assertEqual(h.owner.tiles.tags[0].produced, 32)

    def test_external_tile_priority_and_sfu_loan_block_new_admission(self):
        o = owner()
        c = m.Control(0, 2, 9, 0, 16, 32)
        e = o.tick(window=request(), job=request().job, tile_control=c)
        self.assertTrue(e["tile"]["ctl_fire"])
        self.assertFalse(e["window_ready"] or e["window_fire"] or e["job_ready"])
        self.assertEqual(o.state, "idle")
        for flags in (dict(loan_busy=True), dict(loan_request=True)):
            e = o.tick(window=request(), job=request().job, **flags)
            self.assertFalse(e["window_ready"] or e["window_fire"] or e["job_ready"])
            self.assertFalse(e["a_reads"] or e["a_writes"])
        self.assertTrue(o.tick(window=request())["window_fire"])

    def test_ordinary_request_held_does_not_stop_accepted_tile_rmw_or_response(self):
        o = owner()
        c = m.Control(0, 2, 9, 0, 16, 32)
        o.tick(tile_control=c)
        o.tick(tile_write=m.Write(2, 9, 0, 0, (0x3f000000,)*16))
        e = o.tick(job=request().job)
        self.assertFalse(e["job_ready"])
        self.assertTrue(e["tile"]["rmw_commit"])
        self.assertEqual(o.tiles.tags[2].produced, 1)
        self.assertEqual(o.state, "idle")
        e = o.tick(job=request().job)
        self.assertTrue(e["job_ready"])
        self.assertEqual(o.state, "clear")

        h = Harness(request())
        h.finish()
        h.owner.tick(tile_read=m.Read(0, 7, 0, 0))
        e = h.owner.tick(job=request().job, tile_response_ready=False)
        self.assertFalse(e["job_ready"])
        self.assertIsNotNone(h.owner.tiles.response)
        e = h.owner.tick(job=request().job, tile_response_ready=True)
        self.assertFalse(e["job_ready"])
        self.assertTrue(e["tile"]["response_fire"])
        e = h.owner.tick(job=request().job)
        self.assertTrue(e["job_ready"])
        self.assertIsNone(h.owner.lease)

    def test_unchanged_consumer_release_ignores_producer_mode(self):
        h = Harness(request())
        h.finish()
        consume_tile(h.owner, h.q)
        c = m.tiles.Control(2, 0, 7, 0, 16, 32)
        e = h.owner.tick(tile_control=c)
        self.assertTrue(e["tile"]["ctl_fire"])
        self.assertFalse(h.owner.tiles.poison or h.owner.tiles.tags[0].live)

    def test_producer_mode_is_begin_only_even_for_slot2(self):
        for slot, begin_mode, later_mode in ((0, True, False), (2, False, True)):
            b = m.TileBankModel()
            c = m.Control(0, slot, 9, 0, 16, 32, begin_mode)
            b.tick(control=c)
            for index in range(32):
                b.tick(write=m.Write(slot, 9, 0, index, (0x3f000000,)*16))
                b.tick()
            b.tick(control=replace(c, op=1, matrix_producer_order=later_mode))
            self.assertFalse(b.poison)
            for index in range(32):
                b.tick(read=m.Read(slot, 9, 0, index))
                b.tick()
                b.tick()
            b.tick(control=replace(c, op=2, matrix_producer_order=later_mode))
            self.assertFalse(b.poison or b.tags[slot].live)

    def test_early_or_wrong_matrix_done_and_local_reset_drain(self):
        for done in (m.MatrixDone(1), m.MatrixDone(99), m.MatrixDone(1, True)):
            h = Harness(request())
            h.until(lambda: h.owner.group_started)
            h.cycle(matrix_done=done)
            result = h.finish()
            self.assertFalse(result.committed)
            self.assertIsNone(h.owner.lease)
        h = Harness(request())
        h.until(lambda: h.owner.a_rmw_pending is not None)
        before = h.owner.rmw_commits
        e = h.cycle(local_reset=True)
        self.assertTrue(e["a_writes"])
        self.assertEqual(h.owner.rmw_commits, before+16)
        self.assertFalse(h.finish().committed)
        self.assertTrue(h.owner.ports()["reset_required"])

    def test_held_future_window_cannot_disrupt_active_ordinary_owner(self):
        path = Path(__file__).resolve().parent.parent / "transposed_down/test_model.py"
        spec = importlib.util.spec_from_file_location("ffn_window_held_ordinary_harness", path)
        previous = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = previous
        spec.loader.exec_module(previous)
        h = previous.Harness(n=32, m_rows=16, k=32, split_k=2560)
        h.owner = m.FfnWindowOwnerModel(h.workspace, enable_ffn_window=True, enable_ffn_tiles=True)
        h.owner.tick(job=h.job)
        next_window = request()
        seen = set()
        for _ in range(10000):
            if h.response is not None:
                break
            e = h.cycle(window=next_window)
            self.assertFalse(e["window_ready"] or e["window_fire"])
            for name in ("read_command_fire", "step_fire", "result_fire",
                         "write_command_fire", "write_data_fire", "write_ack_fire", "response_fire"):
                if e[name]:
                    seen.add(name)
        self.assertEqual(h.response, (1, None, 16*32*4))
        self.assertEqual(len(h.steps), 32)
        self.assertEqual(len(seen), 7)
        self.assertEqual(h.owner.state, "idle")
        self.assertTrue(h.owner.tick(window=next_window)["window_fire"])

    def test_unaccepted_conflicting_ordinary_job_cannot_replace_current_job(self):
        path = Path(__file__).resolve().parent.parent / "transposed_down/test_model.py"
        spec = importlib.util.spec_from_file_location("ffn_window_conflicting_ordinary_harness", path)
        previous = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = previous
        spec.loader.exec_module(previous)
        h = previous.Harness(n=32, m_rows=16, k=32, split_k=2560)
        h.owner = m.FfnWindowOwnerModel(h.workspace, enable_ffn_window=True, enable_ffn_tiles=True)
        h.owner.tick(tile_control=m.Control(0, 2, 9, 0, 16, 32))
        h.owner.tick(job=h.job)
        future_job = replace(h.job, tag=99, k=1568)
        for _ in range(10000):
            if h.response is not None:
                break
            e = h.cycle(job=future_job)
            self.assertFalse(e["job_ready"])
            self.assertIs(h.owner.job, h.job)
        self.assertEqual(h.response, (1, None, 16*32*4))
        self.assertEqual(len(h.steps), 32)
        self.assertEqual(h.owner.state, "idle")
        e = h.owner.tick(job=future_job)
        self.assertFalse(e["a_reads"] or e["a_writes"] or e["b_reads"] or e["b_writes"])
        self.assertFalse(e["read_command_fire"] or e["group_fire"] or e["write_command_fire"])
        self.assertFalse(h.owner.group_started or h.owner.group_done)
        self.assertEqual(h.owner.ports()["response"], (99, "ordinary job intersects live tile allocation", 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
