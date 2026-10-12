"""Independent act-drain controls and actual address/word transport, not numerics."""
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ffn_drain_model", HERE / "model.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def request(rows=16, cols=32, ng=0, **kwargs):
    j = m.ActivationJob(m=rows, a=0x1000000, b=0x2000000, dst=0x3000000,
                        write_bytes=rows * 8960 * 4, **kwargs)
    return m.FfnDrainRequest(j, 7, ng, cols)


def owner(**kwargs):
    return m.FfnDrainOwnerModel(m.PrefixWorkspace(0x10000000, 8960 // 32 * 16384, 11),
        enable_ffn_drain=True, enable_ffn_window=True, enable_ffn_tiles=True, **kwargs)


def token(row, column):
    # Unique, finite opaque FP32 encodings distinguish every row and column.
    return 0x3E000000 + row * 16384 + column


def produce_act(o, q, *, slot=2):
    """Real ordered begin, per-column physical RMW, then seal; no bank injection."""
    c = m.Control(0, slot, q.identity, q.ng, q.job.m, q.cols)
    assert o.tick(tile_control=c)["tile"]["ctl_fire"]
    for index in range(q.job.m // 16 * q.cols):
        group, column = divmod(index, q.cols)
        words = tuple(token(group * 16 + lane, q.ng + column) for lane in range(16))
        e = o.tick(tile_write=m.Write(slot, q.identity, q.ng, index, words))
        assert e["tile"]["write_fire"]
        assert o.tick()["tile"]["rmw_commit"]
    assert o.tick(tile_control=replace(c, op=1))["tile"]["ctl_fire"]
    assert not o.tiles.poison


class Harness:
    """One actual-address DDR map and one accepted write obligation.

    Data mutates physical DDR on data.fire; ACK makes no bytes appear. The map
    is intentionally visible even on failures, where output is uncommitted.
    No role, command tag, row, or expected-output bucket chooses a memory bank.
    """
    def __init__(self, q=None, instance=None, seed=True):
        self.owner = owner() if instance is None else instance
        self.q = request() if q is None else q
        self.memory = {}
        self.command = self.ack = self.completion = None
        self.index = 0
        self.commands, self.events, self.acks = [], [], []
        if seed:
            produce_act(self.owner, self.q)
        self.before = dict(self.owner.tiles.counters)

    def submit(self, q=None, **kwargs):
        if q is not None:
            self.q = q
        e = self.owner.tick(drain=self.q, **kwargs)
        assert e["drain_fire"]
        self.events.append(e)
        return e

    def cycle(self, ack=True, **kwargs):
        args = {}
        if ack and self.ack is not None:
            args["write_ack"] = self.ack
        args.update(kwargs)
        e = self.owner.tick(**args)
        if e["write_command_fire"]:
            assert self.command is None
            self.command, self.index = e["write_command"], 0
            self.commands.append(self.command)
            assert 1 <= self.command.beats <= 16
            assert self.command.address % 64 == 0
            assert (self.command.address & 1023) + self.command.beats * 64 <= 1024
        if e["write_data_fire"]:
            assert self.command is not None
            beat = e["write_data"]
            assert len(beat.words) == 16 and beat.mask == (1 << 64) - 1
            assert beat.last == (self.index + 1 == self.command.beats)
            address = self.command.address + self.index * 64
            for lane, word in enumerate(beat.words):
                assert address + lane * 4 not in self.memory, "duplicate physical write"
                self.memory[address + lane * 4] = word
            self.index += 1
            if beat.last:
                self.ack = m.WriteAck(self.command.tag, nbytes=self.command.beats * 64)
        if e["write_ack_fire"]:
            assert self.command is not None and self.index == self.command.beats
            self.acks.append(args["write_ack"])
            self.command = self.ack = None
        if e["drain_result_fire"]:
            assert self.completion is None, "duplicate terminal result"
            self.completion = e["drain_result"]
        assert e.get("response") is None and e.get("window_result") is None
        assert not e.get("read_command") and not e.get("group") and not e.get("step")
        for name in ("a_reads", "a_writes", "b_reads", "b_writes"):
            assert len(e.get(name, {})) <= 16
        assert not e.get("a_writes") and not e.get("b_reads") and not e.get("b_writes")
        self.events.append(e)
        return e

    def until(self, predicate, limit=50000, **kwargs):
        for _ in range(limit):
            if predicate():
                return
            self.cycle(**kwargs)
        raise AssertionError(("finite control timeout", self.owner.state, self.owner.error,
                              self.owner.drain_phase, self.owner.write_state))

    def finish(self, **kwargs):
        self.until(lambda: self.completion is not None, **kwargs)
        return self.completion

    def assert_data(self, case):
        expected = {self.q.job.dst + (row * 8960 + self.q.ng + column) * 4:
                    token(row, self.q.ng + column)
                    for row in range(self.q.job.m) for column in range(self.q.cols)}
        case.assertEqual(self.memory, expected)


class DrainModelTests(unittest.TestCase):
    def test_all_shapes_actual_values_addresses_and_separate_traffic(self):
        for rows in (16, 128):
            for cols in (32, 64, 96, 128, 160):
                with self.subTest(rows=rows, cols=cols):
                    q = request(rows, cols, 8960 - cols)
                    h = Harness(q)
                    banks = h.owner.a_banks
                    h.submit()
                    result = h.finish()
                    self.assertTrue(result.committed)
                    self.assertEqual(result.ddr_write_bytes, rows * cols * 4)
                    self.assertEqual(result.consumed_beats, rows // 16 * cols)
                    self.assertEqual((result.tag, result.identity, result.ng, result.rows, result.cols),
                                     (q.job.tag, q.identity, q.ng, rows, cols))
                    self.assertEqual((result.useful_macs, result.executed_macs), (0, 0))
                    h.assert_data(self)
                    self.assertIs(h.owner.a_banks, banks)
                    self.assertIs(h.owner.tiles.banks, banks)
                    self.assertEqual((banks.depth, h.owner.b_banks.depth), (1376, 160))
                    counters = h.owner.tiles.counters
                    self.assertEqual(counters["logical_read_bytes"] - h.before["logical_read_bytes"], rows * cols * 4)
                    self.assertEqual(counters["physical_read_bytes"] - h.before["physical_read_bytes"], rows * cols * 32)
                    self.assertEqual(counters["physical_write_bytes"], h.before["physical_write_bytes"])
                    self.assertFalse(h.owner.tiles.tags[2].live)
                    self.assertEqual(sum(e.get("release_fire", False) for e in h.events), 1)
                    self.assertEqual(sum(e.get("release_verified", False) for e in h.events), 1)

    def test_nonzero_ng_one_kib_boundary_and_final_row_tail(self):
        q = request(rows=128, cols=160, ng=8800)
        q = replace(q, job=replace(q.job, dst=q.job.dst + 448))
        h = Harness(q)
        h.submit()
        h.finish()
        h.assert_data(self)
        first = q.job.dst + q.ng * 4
        self.assertEqual(first % 1024, 832)
        self.assertEqual([(c.address, c.beats) for c in h.commands[:2]], [(first, 3), (first + 192, 7)])
        self.assertEqual(h.commands[-1].address + h.commands[-1].beats * 64,
                         q.job.dst + (127 * 8960 + 8960) * 4)
        self.assertEqual([c.tag for c in h.commands], [(q.job.tag << 32) + i for i in range(len(h.commands))])

    def test_each_rowgroup_reads_only_after_previous_group_ack(self):
        h = Harness(request(rows=128, cols=64))
        h.submit()
        h.until(lambda: h.owner.write_row == 15 and h.owner.write_state == "ack")
        read_count = h.owner.tiles.counters["read_requests"]
        self.assertEqual(read_count - h.before["read_requests"], 64)
        for _ in range(7):
            e = h.cycle(ack=False)
            self.assertFalse(e["tile"]["read_fire"])
            self.assertEqual(h.owner.write_row, 15)
        h.cycle()
        self.assertEqual(h.owner.write_row, 16)
        self.assertEqual(h.owner.drain_phase, "read")
        self.assertEqual(h.cycle()["tile"]["read_fire"], True)
        h.finish()
        h.assert_data(self)

    def test_tile_read_response_backpressure_holds_and_no_early_ddr(self):
        h = Harness()
        h.submit()
        h.until(lambda: h.owner.tiles.response is not None, tile_response_ready=False)
        held = h.owner.tiles.response
        hold = h.owner.final_value
        for _ in range(11):
            e = h.cycle(tile_response_ready=False)
            self.assertEqual(e["tile"]["response"], held)
            self.assertFalse(e["tile"]["response_fire"])
            self.assertFalse(h.commands)
            self.assertEqual(h.owner.drain_consumed, 0)
            self.assertIs(h.owner.final_value, hold)
        self.assertTrue(h.cycle()["tile"]["response_fire"])
        h.finish()
        h.assert_data(self)

    def test_final_ack_stall_no_completion_release_or_bytes_claim(self):
        h = Harness(request(cols=160, ng=160))
        h.submit()
        h.until(lambda: h.owner.write_row == 15 and h.owner.write_state == "ack" and
                h.owner.write_row_beat + h.command.beats == 10)
        pending = h.command.beats * 64
        for _ in range(13):
            e = h.cycle(ack=False)
            self.assertIsNone(e["drain_result"])
            self.assertFalse(e["release_fire"])
            self.assertTrue(h.owner.tiles.tags[2].live)
            self.assertEqual(h.owner.write_bytes, 16 * 160 * 4 - pending)
        self.assertTrue(h.cycle()["write_ack_fire"])
        self.assertIsNone(h.owner.ports()["drain_result"])
        self.assertTrue(h.owner.tiles.tags[2].live)
        self.assertTrue(h.cycle()["release_fire"])
        self.assertFalse(h.owner.tiles.tags[2].live)
        self.assertIsNone(h.owner.ports()["drain_result"])
        self.assertTrue(h.cycle()["release_verified"])
        self.assertTrue(h.finish().committed)

    def test_write_command_and_data_hold_stable_under_stalls(self):
        h = Harness(request(cols=160))
        h.submit()
        h.until(lambda: h.owner.ports()["write_command"] is not None)
        held = h.owner.ports()["write_command"]
        for _ in range(7):
            self.assertEqual(h.cycle(write_command_ready=False)["write_command"], held)
        h.cycle()
        data = h.owner.ports()["write_data"]
        for _ in range(7):
            self.assertEqual(h.cycle(write_data_ready=False)["write_data"], data)
        h.finish()
        h.assert_data(self)

    def test_ack_fault_mismatch_and_byte_count_never_release_or_commit(self):
        for change in (dict(error=True), dict(tag=0xBAD), dict(nbytes=64)):
            h = Harness(request(cols=160))
            h.submit()
            h.until(lambda: h.owner.write_row == 15 and h.owner.write_state == "ack")
            ack = replace(h.ack, **change)
            before = h.owner.write_bytes
            h.cycle(write_ack=ack)
            result = h.finish()
            self.assertFalse(result.committed)
            self.assertEqual(result.ddr_write_bytes, before)
            self.assertTrue(h.owner.tiles.tags[2].live)
            self.assertFalse(any(e.get("release_fire") for e in h.events))
            self.assertEqual(h.owner.state, "locked")

    def test_complete_activation_job_validation_before_reads_or_dma(self):
        good = request()
        invalid_jobs = [dict(kind="Dense"), dict(m=32), dict(n=160), dict(k=1536),
            dict(a=1), dict(b=(1 << 56) - 64), dict(dst=(1 << 56) - 64),
            dict(activation_bf16=True), dict(weight_bf16=True), dict(output_bf16=True),
            dict(write_bytes=64), dict(write_bytes=None), dict(tag=-1), dict(tag=1 << 32),
            dict(m=True), dict(weight_bf16=0), dict(c=-1), dict(gdn_elementwise_op=4),
            dict(a=good.job.b + 64), dict(dst=good.job.a + 64), dict(dst=good.job.b + 64)]
        bad = [replace(good, job=replace(good.job, **change)) for change in invalid_jobs]
        bad += [replace(good, **change) for change in (dict(identity=0), dict(identity=1 << 32),
            dict(ng=1), dict(ng=65504, cols=160), dict(ng=8960), dict(cols=16), dict(cols=True))]
        for q in bad:
            with self.subTest(q=q):
                h = Harness(good)
                before = tuple(tuple(bank) for bank in h.owner.a_banks.words)
                h.submit(q)
                self.assertFalse(h.finish().committed)
                self.assertFalse(h.commands or h.memory)
                self.assertFalse(any(e["a_reads"] or e["a_writes"] for e in h.events))
                self.assertEqual(tuple(tuple(bank) for bank in h.owner.a_banks.words), before)

    def test_workspace_overlap_and_missing_workspace_reject_preaccess(self):
        for w in (None, m.PrefixWorkspace(request().job.a + 64, 16384, 1)):
            h = Harness()
            h.owner.workspace = w
            h.submit()
            self.assertFalse(h.finish().committed)
            self.assertFalse(h.commands)
            self.assertFalse(any(e["a_reads"] for e in h.events))

    def test_slot_missing_unsealed_wrong_identity_shape_and_consumed_reject(self):
        changes = (dict(live=False), dict(sealed=False), dict(identity=8), dict(ng=32),
                   dict(rows=128), dict(cols=64), dict(produced=31), dict(consumed=1),
                   dict(matrix_producer_order=True))
        for change in changes:
            h = Harness()
            for name, value in change.items():
                setattr(h.owner.tiles.tags[2], name, value)
            h.submit()
            result = h.finish()
            self.assertFalse(result.committed)
            self.assertEqual(result.consumed_beats, 0)
            self.assertFalse(h.commands)
        h = Harness(seed=False)
        produce_act(h.owner, h.q, slot=1)
        h.submit()
        self.assertFalse(h.finish().committed)
        self.assertTrue(h.owner.tiles.tags[1].live)

    def test_bad_read_response_identity_and_nonfinite_actual_bank_word(self):
        for change in (dict(identity=8), dict(index=1), dict(error=True)):
            h = Harness()
            h.submit()
            h.until(lambda: h.owner.tiles.response is not None, tile_response_ready=False)
            h.owner.tiles.response = replace(h.owner.tiles.response, **change)
            result = h.finish()
            self.assertFalse(result.committed)
            self.assertEqual(result.consumed_beats, 1 if change == dict(error=True) else 0)
            self.assertFalse(h.commands)
        h = Harness()
        word, lane = m.tiles.location(2, 0, 0)
        h.owner.a_banks.words[0][word] |= 0x7FC00000 << (32 * lane)
        h.submit()
        self.assertFalse(h.finish().committed)
        self.assertFalse(h.commands)

    def test_abort_during_pending_read_drains_real_response(self):
        h = Harness()
        h.submit()
        h.cycle()
        self.assertIsNotNone(h.owner.tiles.pending)
        h.cycle(abort=True, tile_response_ready=False)
        for _ in range(9):
            h.cycle(tile_response_ready=False)
            self.assertIsNone(h.owner.ports()["drain_result"])
        result = h.finish()
        self.assertFalse(result.committed)
        self.assertEqual(result.consumed_beats, 1)
        self.assertFalse(h.commands)

    def test_unsolicited_response_on_read_or_write_offer_creates_no_new_obligation(self):
        # Input faults are sampled on the same modeled edge as an otherwise
        # ready downstream. Only actual fires/obligations are asserted; ports()
        # is a pre-input proposal and is not a combinational RTL waveform.
        for phase in ("read", "write"):
            for bad in (dict(write_ack=m.WriteAck(991)),
                        dict(result=object()), dict(read_beat=object())):
                with self.subTest(phase=phase, source=next(iter(bad))):
                    h=Harness();h.submit()
                    if phase=="write":
                        h.until(lambda:h.owner.ports()["write_command"] is not None)
                    self.assertIsNone(h.owner.drain_expected)
                    before=len(h.commands)
                    e=h.cycle(**bad)
                    self.assertFalse(e["write_command_fire"])
                    self.assertFalse(e["tile"]["read_fire"] or e["tile"]["ctl_fire"])
                    self.assertEqual(len(h.commands),before)
                    self.assertIsNone(h.owner.drain_expected)
                    self.assertFalse(h.finish().committed)
                    self.assertFalse(h.memory)
                    self.assertTrue(h.owner.tiles.tags[2].live)

    def test_abort_before_write_accept_has_no_ddr_obligation(self):
        h = Harness()
        h.submit()
        h.until(lambda: h.owner.ports()["write_command"] is not None)
        h.cycle(abort=True)
        self.assertFalse(h.finish().committed)
        self.assertFalse(h.commands or h.memory)

    def test_abort_accepted_descriptor_drains_all_data_then_actual_ack(self):
        for accepted_beats in (0, 1, 9):
            h = Harness(request(cols=160))
            h.submit()
            h.until(lambda: h.command is not None)
            for _ in range(accepted_beats):
                h.cycle(ack=False)
            data = h.owner.ports()["write_data"]
            h.cycle(abort=True, write_data_ready=False, ack=False)
            for _ in range(7):
                e = h.cycle(write_data_ready=False, ack=False)
                self.assertEqual(e["write_data"], data)
                self.assertIsNone(e["drain_result"])
            h.until(lambda: h.owner.write_state == "ack", ack=False)
            self.assertEqual(h.index, 10)
            for _ in range(7):
                self.assertIsNone(h.cycle(ack=False)["drain_result"])
            result = h.finish()
            self.assertFalse(result.committed)
            self.assertEqual(result.ddr_write_bytes, 640)
            self.assertEqual(len(h.memory), 160)
            self.assertEqual(len(h.commands), 1)
            self.assertTrue(h.owner.tiles.tags[2].live)

    def test_abort_same_edge_final_ack_credits_bytes_without_release(self):
        h = Harness()
        h.submit()
        h.until(lambda: h.owner.write_row == 15 and h.owner.write_state == "ack")
        self.assertTrue(h.cycle(abort=True)["write_ack_fire"])
        result = h.finish()
        self.assertFalse(result.committed)
        self.assertEqual(result.ddr_write_bytes, 16 * 32 * 4)
        self.assertTrue(h.owner.tiles.tags[2].live)
        self.assertFalse(any(e.get("release_fire") for e in h.events))

    def test_abort_at_release_request_and_release_verify_never_publish_success(self):
        for phase in ("release", "verify"):
            h = Harness()
            h.submit()
            h.until(lambda: h.owner.drain_phase == phase)
            h.cycle(abort=True)
            self.assertFalse(h.finish().committed)
            self.assertEqual(h.owner.tiles.tags[2].live, phase == "release")

    def test_held_result_stable_abort_locks_without_duplicate_terminal(self):
        h = Harness()
        h.submit()
        h.until(lambda: h.owner.ports()["drain_result"] is not None, drain_result_ready=False)
        held = h.owner.ports()["drain_result"]
        for _ in range(8):
            self.assertEqual(h.cycle(drain_result_ready=False)["drain_result"], held)
        h.cycle(abort=True, drain_result_ready=False)
        self.assertEqual(h.owner.ports()["drain_result"], held)
        self.assertTrue(h.owner.ports()["reset_required"])
        self.assertEqual(h.finish(), held)
        self.assertEqual(h.owner.state, "locked")
        for _ in range(5):
            self.assertIsNone(h.cycle()["drain_result"])

    def test_release_observation_fault_cannot_claim_success(self):
        for phase in ("read", "release", "verify"):
            for change in (dict(live=False), dict(identity=99), dict(ng=32),
                           dict(cols=64), dict(sealed=True), dict(consumed=1)):
                if phase == "verify" and change == dict(live=False):
                    continue
                if phase != "verify" and change == dict(sealed=True):
                    continue
                h = Harness()
                h.submit()
                h.until(lambda: h.owner.drain_phase == phase)
                for name, value in change.items():
                    setattr(h.owner.tiles.tags[2], name, value)
                self.assertFalse(h.finish().committed)

    def test_unsolicited_matrix_or_dma_response_poison_and_drain(self):
        for arg in (dict(result=m.MatrixResult(0, ())),
                    dict(read_beat=m.ReadBeat(1, (0,) * 16, True))):
            h = Harness()
            h.submit()
            h.cycle(**arg)
            self.assertFalse(h.finish().committed)
            self.assertFalse(h.commands)

    def test_unsolicited_tile_response_waits_for_coordinated_reset(self):
        h = Harness()
        h.submit()
        h.owner.tiles.response = m.Response(2, 7, 0, 0, (0x3F000000,) * 16)
        for _ in range(8):
            e = h.cycle()
            self.assertFalse(e["tile"]["response_fire"])
            self.assertIsNone(e["drain_result"])
        self.assertTrue(h.owner.ports()["reset_required"])
        h.owner.tick(coordinated_reset=True)
        self.assertTrue(h.owner.ports()["drain_ready"])

    def test_local_reset_drains_and_coordinated_reset_preserves_cells(self):
        h = Harness(request(cols=160))
        h.submit()
        h.until(lambda: h.command is not None)
        h.cycle(local_reset=True, write_data_ready=False, ack=False)
        self.assertFalse(h.finish().committed)
        before = tuple(tuple(bank) for bank in h.owner.a_banks.words)
        h.owner.tick(coordinated_reset=True)
        self.assertEqual(tuple(tuple(bank) for bank in h.owner.a_banks.words), before)
        self.assertFalse(h.owner.tiles.leased)
        self.assertIsNone(h.owner.lease)
        self.assertTrue(h.owner.ports()["drain_ready"])

    def test_late_ack_after_reset_or_completion_poison_before_relaunch(self):
        for reset in (False, True):
            h = Harness()
            h.submit()
            h.finish()
            ack = h.acks[-1]
            if reset:
                h.owner.tick(coordinated_reset=True)
            e = h.owner.tick(write_ack=ack, drain=h.q)
            self.assertFalse(e["drain_fire"])
            self.assertTrue(h.owner.ports()["reset_required"])
            self.assertFalse(h.owner.ports()["drain_ready"])

    def test_idle_unexpected_dma_matrix_blocks_same_edge_window_and_job(self):
        for extra in (dict(write_ack=m.WriteAck(0)), dict(read_beat=m.ReadBeat(0, (), True)),
                      dict(result=m.MatrixResult(0, ()))):
            h = Harness()
            j = m.Job(m=16, n=8960)
            w = m.FfnWindowRequest(j, 9, 0, 32, 0)
            e = h.owner.tick(drain=h.q, window=w, job=j, **extra)
            self.assertFalse(e["drain_fire"] or e["window_fire"] or e["job_ready"])
            self.assertTrue(h.owner.ports()["reset_required"])

    def test_idle_external_tile_response_is_legitimate_and_blocks_admission(self):
        h = Harness()
        e = h.owner.tick(tile_read=m.Read(2, 7, 0, 0))
        self.assertTrue(e["tile"]["read_fire"])
        h.owner.tick(tile_response_ready=False)
        response = h.owner.tiles.response
        self.assertIsNotNone(response)
        for _ in range(7):
            e = h.owner.tick(drain=h.q, job=m.Job(m=16), tile_response_ready=False)
            self.assertEqual(e["tile"]["response"], response)
            self.assertFalse(e["drain_fire"] or e["job_ready"])
            self.assertFalse(h.owner.ports()["reset_required"])
        self.assertTrue(h.owner.tick()["tile"]["response_fire"])
        self.assertFalse(h.owner.ports()["reset_required"])
        self.assertEqual(h.owner.tiles.tags[2].consumed, 1)

    def test_ack_offered_before_last_data_is_backpressured(self):
        h = Harness(request(cols=160))
        h.submit()
        h.until(lambda: h.command is not None)
        early = m.WriteAck(h.command.tag, nbytes=640)
        for _ in range(10):
            e = h.cycle(write_ack=early)
            self.assertFalse(e["write_ack_fire"])
            self.assertFalse(h.owner.error)
        self.assertTrue(h.cycle()["write_ack_fire"])
        h.finish()

    def test_external_tile_priority_and_loan_guard(self):
        h = Harness()
        control = m.Control(0, 0, 9, 32, 16, 32)
        e = h.owner.tick(drain=h.q, tile_control=control)
        self.assertTrue(e["tile"]["ctl_fire"])
        self.assertFalse(e["drain_fire"])
        for flags in (dict(loan_busy=True), dict(loan_request=True)):
            e = h.owner.tick(drain=h.q, **flags)
            self.assertFalse(e["drain_fire"])
        h.submit()
        h.finish()

    def test_drain_over_ordinary_and_held_window_cannot_interrupt(self):
        h = Harness()
        job = m.Job(m=16)
        window = m.FfnWindowRequest(job, 9, 32, 32, 0)
        e = h.submit(job=job)
        self.assertFalse(e["window_fire"] or e["job_ready"])
        result = h.finish(window=window, job=job)
        self.assertTrue(result.committed)
        self.assertTrue(all(not e.get("window_fire") and not e.get("response_fire") for e in h.events))

    def test_window_priority_over_simultaneous_drain_and_job(self):
        h = Harness()
        j = m.Job(m=16, n=8960, dst=0x4000000)
        w = m.FfnWindowRequest(j, 9, 32, 32, 0)
        e = h.owner.tick(window=w, drain=h.q, job=j)
        self.assertTrue(e["window_fire"])
        self.assertFalse(e["drain_fire"] or e["job_ready"])
        self.assertIsNone(h.owner.drain_request)
        self.assertEqual(h.owner.window_request, w)

    def test_success_preserves_real_a_lease_for_next_window(self):
        path = HERE.parent / "ffn_window/test_model.py"
        spec = importlib.util.spec_from_file_location("ffn_drain_window_harness", path)
        old = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = old
        spec.loader.exec_module(old)
        q = old.request()
        w = old.Harness(q, owner())
        w.finish()
        old.consume_tile(w.owner, q)
        old.release(w.owner, q)
        lease = w.owner.lease
        low = tuple(tuple(bank[:768]) for bank in w.owner.a_banks.words)
        h = Harness(instance=w.owner)
        h.submit()
        h.finish()
        self.assertEqual(w.owner.lease, lease)
        self.assertEqual(tuple(tuple(bank[:768]) for bank in w.owner.a_banks.words), low)
        before = w.owner.traffic["a_read_bytes"]
        w.submit(old.request(ng=32, reuse=True))
        w.finish()
        self.assertEqual(w.owner.traffic["a_read_bytes"], before)

    def test_default_off_and_ordinary_owner_with_held_future_drain(self):
        with self.assertRaises(ValueError):
            m.FfnDrainOwnerModel(enable_ffn_drain=True)
        self.assertFalse(m.FfnDrainOwnerModel().ports()["drain_ready"])
        path = HERE.parent / "transposed_down/test_model.py"
        spec = importlib.util.spec_from_file_location("ffn_drain_ordinary_harness", path)
        old = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = old
        spec.loader.exec_module(old)
        for enabled in (False, True):
            h = old.Harness(n=32, m_rows=16, k=32, split_k=2560)
            h.owner = owner() if enabled else m.FfnDrainOwnerModel(h.workspace)
            h.owner.tick(job=h.job)
            h.until(lambda: h.response is not None, drain=request())
            self.assertEqual(h.response, (1, None, 16 * 32 * 4))
            self.assertIsNone(h.owner.drain_request)

    def test_independent_drain_on_window_off_profile(self):
        o = m.FfnDrainOwnerModel(m.PrefixWorkspace(0x10000000, 16384, 1),
                                 enable_ffn_drain=True, enable_ffn_tiles=True)
        self.assertFalse(o.ports()["window_ready"])
        h = Harness(instance=o)
        h.submit()
        self.assertTrue(h.finish().committed)


if __name__ == "__main__":
    unittest.main()
