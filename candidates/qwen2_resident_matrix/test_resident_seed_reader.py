import unittest
from dataclasses import replace

from resident_seed_reader_model import Descriptor, ResidentReaderModel, SyncBankFixture, dense_port_cycle
from seed_protocol_model import Ack, Request, ResidentPrefixOwner, SeedControllerModel


def pattern(i):
    specials = (0x00000000, 0x80000000, 0x00000001, 0x807FFFFF)
    return specials[i] if i < len(specials) else 0x3E000000 + i


def fixture(m=16, n=256, k=1792, slot=0, tile_row=0, n_base=0):
    owner = ResidentPrefixOwner(m, n, k)
    owner.scratch[:] = bytes.fromhex("0100c07f") * (len(owner.scratch) // 4)
    rows, cols = min(16, m - tile_row * 16), min(256, n - n_base)
    owner.store(slot, tile_row, n_base, 256, [pattern(i) for i in range(rows * cols)])
    req = Request(slice_mask=(1 << ((cols + 31) // 32)) - 1)
    desc = Descriptor(req, slot, tile_row, n_base)
    return owner, desc


class Coupled:
    """Cycle source plus existing handshake endpoint/control reference.

    This connects the two software references. It does not execute Chisel and
    makes no numeric/throughput claim for the original Matrix arithmetic.
    """
    def __init__(self, owner, desc):
        self.owner, self.desc = owner, desc
        self.reader = ResidentReaderModel(owner)
        self.mem = SyncBankFixture(owner)
        self.controller = SeedControllerModel(desc.seed.group_tag, desc.seed.group_sequence, desc.seed.slice_mask)
        self.cycles = 0
        self.read_cycles = []
        self.beats = []
        self.state_cycles = {}
        self.offer_stalls = 0
        self.handshakes = dict(start=0, acquire=0, begin=0, beat=0, ack=0,
                               leaf_begin=0, leaf_commit=0, leaf_ack=0)

    def tick(self, start=False, leaf_ready=True, reserve_ready=True,
             commit_ready=True, return_acks=True, terminal_ready=True, abort=False, **kwargs):
        c = self.controller
        source_phase = self.reader.state
        self.state_cycles[source_phase] = self.state_cycles.get(source_phase, 0) + 1
        c.observe(abort=abort or self.reader.poison)
        phase = c.state
        ack = c.response()
        commit = c.req if ack and not c.poison and not ack.error and c.identity_ok() and c.quiescent and terminal_ready else None
        out = self.mem.tick(self.reader, start=self.desc if start else None,
            begin_ready=phase == "idle" and not c.poison,
            beat_ready=phase == "stream" and leaf_ready, ack=ack, committed=commit,
            controller_reset=c.poison, terminal_ready=terminal_ready, abort=abort, **kwargs)
        c.observe(abort=out["abort_controller"])
        if out["begin"] is not None and phase == "idle":
            c.begin(out["begin"])
        if phase == "reserve":
            self.handshakes["leaf_begin"] += int(c.reserve(reserve_ready))
        if out["beat"] is not None and phase == "stream":
            if c.beat(out["beat"], leaf_ready):
                self.beats.append(out["beat"])
        if phase == "commit":
            self.handshakes["leaf_commit"] += int(c.commit(commit_ready))
        if phase == "collect" and return_acks:
            for s in range(8):
                if self.desc.seed.slice_mask & (1 << s):
                    self.handshakes["leaf_ack"] += int(c.leaf_ack(s, Ack.make(self.desc.seed)))
        if out["ack_fire"]:
            before = c.commit_events
            c.take_response(True, abort=abort or out["abort_controller"])
            assert out["completed"] == (c.commit_events == before + 1)
        if out["read"] is not None:
            self.read_cycles.append((self.cycles, out["read"]))
        self.offer_stalls += int(out["beat"] is not None and not (phase == "stream" and leaf_ready))
        self.handshakes["start"] += int(out["start"])
        self.handshakes["acquire"] += int(out["acquired"])
        self.handshakes["begin"] += int(out["begin"] is not None and phase == "idle")
        self.handshakes["beat"] += int(out["beat"] is not None and phase == "stream" and leaf_ready)
        self.handshakes["ack"] += int(out["ack_fire"])
        self.cycles += 1
        return out

    def until(self, predicate, **kwargs):
        for _ in range(10000):
            if predicate():
                return
            self.tick(**kwargs)
        raise AssertionError("source/controller failed to reach expected state")


class ReaderTests(unittest.TestCase):
    def test_no_stall_local_cycle_ledger_is_four_cycles_per_live_beat(self):
        for m, n, live, beats, total in ((16, 256, 256, 256, 1030), (3, 48, 9, 64, 152)):
            with self.subTest(m=m, n=n):
                owner, desc = fixture(m=m, n=n)
                h = Coupled(owner, desc)
                h.tick(start=True)
                h.until(lambda: h.reader.completions == 1)
                self.assertEqual(h.cycles, total)
                self.assertEqual(h.state_cycles, dict(idle=1, acquiring=1, begin=1,
                    read_low=beats, capture_low=live, capture_high=live, offer=beats, wait_ack=3))
                self.assertEqual(h.offer_stalls, 0)
                self.assertEqual(h.handshakes, dict(start=1, acquire=1, begin=1, beat=beats, ack=1,
                    leaf_begin=1, leaf_commit=1, leaf_ack=desc.seed.slice_mask.bit_count()))

    def test_dense_hook_cannot_skip_real_pending_fifo_or_write_drain(self):
        for blocker in (dict(legacy_pending=True), dict(operand_valid=True),
                        dict(a_high_pending=True), dict(a_write=True), dict(state="aWait"), dict(status=1)):
            with self.subTest(blocker=blocker):
                p = dense_port_cycle(pause=True, legacy_request=True, **blocker)
                self.assertFalse(p["grant"])
                self.assertFalse(p["legacy_fire"])
                with self.assertRaises(ValueError):
                    dense_port_cycle(pause=True, seed_enable=True, **blocker)
        p = dense_port_cycle(pause=True, legacy_request=True, seed_enable=True)
        self.assertTrue(p["grant"])
        self.assertTrue(p["seed_fire"])
        self.assertFalse(p["legacy_fire"])
        self.assertFalse(dense_port_cycle(pause=True, state="aReq")["a_request"])
        self.assertFalse(dense_port_cycle(pause=True, state="idle")["job_ready"])
        self.assertTrue(dense_port_cycle(pause=False, state="aReq")["a_request"])
        self.assertTrue(dense_port_cycle(pause=False, legacy_request=True)["legacy_fire"])

    def test_full_context_exact_bits_and_two_synchronous_same_bank_reads(self):
        owner, desc = fixture()
        h = Coupled(owner, desc)
        h.tick(start=True)
        h.until(lambda: h.reader.completions == 1)
        self.assertEqual(h.reader.reads, 512)
        self.assertEqual(len(h.beats), 256)
        self.assertEqual(h.controller.banks[0], [pattern(i) for i in range(4096)])
        expected = []
        for s in range(8):
            for cluster in range(32):
                row, half = divmod(cluster, 2)
                base = owner.c_base + 4 * s + 2 * half
                expected.extend([(row, base), (row, base + 1)])
        self.assertEqual(h.mem.requests, expected)
        for low, high in zip(h.read_cycles[::2], h.read_cycles[1::2]):
            self.assertEqual(high[0], low[0] + 1)
            self.assertEqual(high[1], (low[1][0], low[1][1] + 1))
        self.assertEqual(owner.leases, {})
        self.assertEqual(h.controller.commit_events, 1)

    def test_partial_m_n_padding_reads_no_sentinel(self):
        owner, desc = fixture(m=3, n=48)
        h = Coupled(owner, desc)
        h.tick(start=True)
        h.until(lambda: h.reader.completions == 1)
        self.assertEqual(h.reader.reads, 18)
        self.assertEqual(len(h.beats), 64)
        for row in range(16):
            for col in range(64):
                expected = pattern(row * 48 + col) if row < 3 and col < 48 else 0
                self.assertEqual(h.controller.banks[0][row * 256 + col], expected)

    def test_largest_slot_tile_and_full_a_boundary(self):
        for params, last_address in [(dict(m=128, slot=2, tile_row=7), 895),
                                     (dict(m=128, k=1536, tile_row=7), 1023)]:
            with self.subTest(params=params):
                owner, desc = fixture(**params)
                h = Coupled(owner, desc)
                h.tick(start=True)
                h.until(lambda: h.reader.completions == 1)
                self.assertEqual(h.mem.requests[-1], (15, last_address))
                self.assertTrue(all(owner.c_base <= word < 1024 for _, word in h.mem.requests))

    def test_unsigned_geometry_aliases_rejected_before_lease_or_read(self):
        for changes in (dict(slot=3), dict(tile_row=7), dict(n_base=65280),
                        dict(n_base=65520), dict(prefix_k=65280),
                        dict(prefix_k=257), dict(seed=Request(slice_mask=0x7F)),
                        dict(seed=Request(source_generation=0)), dict(seed=Request(context=5))):
            with self.subTest(changes=changes):
                owner, desc = fixture()
                r, mem = ResidentReaderModel(owner), SyncBankFixture(owner)
                mem.tick(r, start=replace(desc, **changes))
                mem.tick(r)
                self.assertTrue(r.poison)
                self.assertEqual(owner.leases, {})
                self.assertEqual(mem.requests, [])
        owner, desc = fixture(k=1536)
        r = ResidentReaderModel(owner)
        r.tick(start=replace(desc, slot=1)); r.tick()
        self.assertTrue(r.poison)

    def test_large_n_valid_owner_base_does_not_wrap(self):
        owner, desc = fixture(n=65520, n_base=65280)
        h = Coupled(owner, desc)
        h.tick(start=True)
        h.until(lambda: h.reader.completions == 1)
        self.assertEqual(h.reader.reads, 480)
        self.assertEqual(len(h.beats), 256)
        self.assertEqual(h.controller.banks[0][239], pattern(239))
        self.assertEqual(h.controller.banks[0][240:256], [0] * 16)

    def test_actual_owner_prefix_generation_and_failed_store_checked(self):
        for field, value in (("prefix", -1), ("prefix", 512), ("owner_n", 256), ("generation", 2)):
            with self.subTest(field=field):
                owner, desc = fixture()
                getattr(owner, field)[0][0] = value
                r = ResidentReaderModel(owner)
                r.tick(start=desc); r.tick()
                self.assertTrue(r.poison)
                self.assertFalse(r.began)
                self.assertEqual(owner.leases, {})

    def test_grant_waits_for_drain_and_metadata_change_while_waiting_rejects(self):
        owner, desc = fixture()
        h = Coupled(owner, desc)
        out = h.tick(start=True, legacy_drained=False)
        self.assertTrue(out["stop_legacy"])
        for _ in range(10):
            h.tick(legacy_drained=False)
            self.assertEqual(h.reader.state, "acquiring")
            self.assertEqual(owner.leases, {})
        owner.generation[0][0] = 2
        h.tick()
        self.assertTrue(h.reader.poison)
        self.assertEqual(h.mem.requests, [])

    def test_single_buffer_stays_stable_and_stops_reads_under_backpressure(self):
        owner, desc = fixture()
        h = Coupled(owner, desc)
        h.tick(start=True)
        h.until(lambda: h.reader.state == "offer", leaf_ready=False)
        payload, reads, index = h.reader.payload, h.reader.reads, h.reader.index
        for _ in range(40):
            out = h.tick(leaf_ready=False)
            self.assertEqual(out["beat"].words, payload)
            self.assertEqual(h.reader.reads, reads)
            self.assertEqual(h.reader.index, index)
        h.until(lambda: h.reader.completions == 1)
        self.assertEqual(h.controller.banks[0], [pattern(i) for i in range(4096)])

    def test_lease_pinned_during_success_ack_backpressure(self):
        owner, desc = fixture()
        h = Coupled(owner, desc)
        h.tick(start=True)
        h.until(lambda: h.controller.state == "reply", terminal_ready=False)
        held = h.controller.response()
        for _ in range(8):
            h.tick(terminal_ready=False)
            self.assertEqual(h.controller.response(), held)
            self.assertTrue(h.reader.pinned)
            self.assertEqual(h.reader.completions, 0)
            with self.assertRaises(ValueError):
                owner.store(0, 0, 0, 512, [0] * 4096)
        out = h.tick()
        self.assertTrue(out["completed"])
        self.assertFalse(h.reader.pinned)

    def test_abort_in_read_pending_offer_and_terminal_phases_never_completes(self):
        for phase in ("acquiring", "begin", "read_low", "capture_low", "capture_high", "offer", "wait_ack"):
            with self.subTest(phase=phase):
                owner, desc = fixture()
                h = Coupled(owner, desc)
                h.tick(start=True)
                h.until(lambda: h.reader.state == phase, terminal_ready=False)
                payload, writes, reads = h.reader.payload, h.controller.writes, h.reader.reads
                out = h.tick(abort=True)
                self.assertIsNone(out["read"])
                self.assertIsNone(out["beat"])
                self.assertEqual(h.reader.payload, payload)
                self.assertEqual(h.reader.reads, reads)
                self.assertEqual(h.controller.writes, writes)
                self.assertTrue(h.reader.poison)
                for _ in range(3):
                    h.tick()
                self.assertEqual(h.reader.completions, 0)
                if h.reader.pinned:
                    self.assertIn((0, 0), owner.quarantined)

    def test_held_success_ack_abort_and_late_leaf_ack_quarantine(self):
        for reason in ("abort", "late_ack", "owner_generation", "grant", "drain", "shape"):
            with self.subTest(reason=reason):
                owner, desc = fixture()
                h = Coupled(owner, desc)
                h.tick(start=True)
                h.until(lambda: h.controller.state == "reply", terminal_ready=False)
                held = h.controller.response()
                self.assertFalse(held.error)
                kwargs = {}
                if reason == "abort": kwargs["abort"] = True
                if reason == "late_ack": h.controller.leaf_ack(0, Ack.make(desc.seed))
                if reason == "owner_generation": owner.generation[0][0] = 2
                if reason == "grant": kwargs["ports_granted"] = False
                if reason == "drain": kwargs["legacy_drained"] = False
                if reason == "shape": owner.n = 512
                h.tick(terminal_ready=False, **kwargs)
                self.assertEqual(h.controller.response(), held)
                h.tick()
                self.assertEqual(h.reader.completions, 0)
                self.assertEqual(h.controller.commit_events, 0)
                self.assertIn((0, 0), owner.quarantined)

    def test_mid_read_owner_grant_or_metadata_loss_discards_pending_data(self):
        for reason in ("metadata", "grant", "write", "owner_ready"):
            with self.subTest(reason=reason):
                owner, desc = fixture()
                h = Coupled(owner, desc)
                h.tick(start=True)
                h.until(lambda: h.reader.state == "capture_low")
                self.assertIsNotNone(h.mem.pending)
                kwargs = {}
                if reason == "metadata": owner.prefix[0][0] = -1
                if reason == "grant": kwargs["ports_granted"] = False
                if reason == "write": kwargs["legacy_drained"] = False
                if reason == "owner_ready": kwargs["owner_ready"] = False
                held = h.reader.payload
                out = h.tick(**kwargs)
                self.assertIsNone(out["read"])
                self.assertEqual(h.reader.payload, held)
                self.assertTrue(h.reader.poison)
                self.assertIn((0, 0), owner.quarantined)

    def test_nonfinite_rejected_without_leaf_write_or_prefix_release(self):
        for bad in (0x7F800000, 0xFF800000, 0x7FC00001):
            with self.subTest(word=bad):
                owner, desc = fixture()
                address = owner.address(0, 0, 0)
                owner.scratch[address:address + 4] = bad.to_bytes(4, "little")
                h = Coupled(owner, desc)
                h.tick(start=True)
                h.until(lambda: h.reader.poison)
                self.assertEqual(h.controller.writes, 0)
                self.assertEqual(h.reader.completions, 0)
                self.assertIn((0, 0), owner.quarantined)

    def test_ack_error_false_without_committed_is_failure(self):
        owner, desc = fixture(n=32)
        h = Coupled(owner, desc)
        h.tick(start=True)
        h.until(lambda: h.reader.state == "wait_ack", return_acks=False)
        out = h.mem.tick(h.reader, ack=Ack.make(desc.seed), committed=None)
        self.assertFalse(out["completed"])
        self.assertTrue(h.reader.poison)
        self.assertIn((0, 0), owner.quarantined)

    def test_wrong_identity_ack_or_commit_cannot_release(self):
        for which in ("ack", "committed"):
            owner, desc = fixture(n=32)
            h = Coupled(owner, desc)
            h.tick(start=True)
            h.until(lambda: h.reader.state == "wait_ack", return_acks=False)
            ack = Ack.make(desc.seed)
            committed = desc.seed
            if which == "ack": ack = replace(ack, source_generation=2)
            else: committed = replace(committed, group_sequence=2)
            out = h.mem.tick(h.reader, ack=ack, committed=committed)
            self.assertFalse(out["completed"])
            self.assertTrue(h.reader.poison)

    def test_reader_only_reset_does_not_reuse_lease_or_old_sync_data(self):
        owner, desc = fixture()
        h = Coupled(owner, desc)
        h.tick(start=True)
        h.until(lambda: h.reader.state == "capture_low")
        self.assertIsNotNone(h.mem.pending)
        reset_reader = ResidentReaderModel(owner)
        out = h.mem.tick(reset_reader, start=desc)
        self.assertTrue(out["start"])
        self.assertEqual(reset_reader.payload, (0,) * 16)
        h.mem.tick(reset_reader)
        self.assertTrue(reset_reader.poison)
        self.assertEqual(reset_reader.reads, 0)
        self.assertTrue(owner.leases)
        owner2, desc2 = fixture()
        fresh = ResidentReaderModel(owner2)
        out = fresh.tick(start=desc2, owner_ready=False)
        self.assertFalse(out["start"])
        fresh.tick(ack=Ack.make(desc.seed))
        self.assertTrue(fresh.poison)

    def test_new_generation_cannot_resume_old_lease_after_success(self):
        owner, desc = fixture(n=32)
        h = Coupled(owner, desc)
        h.tick(start=True)
        h.until(lambda: h.reader.completions == 1)
        owner.store(0, 0, 0, 512, [0x40000000] * 512)
        h.tick(start=True)
        h.tick()
        self.assertTrue(h.reader.poison)
        self.assertEqual(h.reader.completions, 1)
        self.assertEqual(owner.leases, {})

    def test_duplicate_seed_ack_after_success_or_new_acquisition_is_terminal(self):
        for after_new_start in (False, True):
            with self.subTest(after_new_start=after_new_start):
                owner, desc = fixture(n=32)
                h = Coupled(owner, desc)
                h.tick(start=True)
                h.until(lambda: h.reader.completions == 1)
                if after_new_start:
                    owner.store(0, 0, 0, 512, [0x40000000] * 512)
                    next_desc = replace(desc, seed=replace(desc.seed, source_generation=2, group_sequence=2), prefix_k=512)
                    h.mem.tick(h.reader, start=next_desc)
                    h.mem.tick(h.reader)
                    self.assertTrue(h.reader.pinned)
                out = h.mem.tick(h.reader, ack=Ack.make(desc.seed))
                self.assertFalse(out["completed"])
                self.assertFalse(out["ack_fire"])
                self.assertTrue(h.reader.poison)
                self.assertEqual(h.reader.completions, 1)
                if after_new_start:
                    self.assertIn((0, 0), owner.quarantined)
                else:
                    self.assertEqual(owner.leases, {})

    def test_controller_rejects_begin_and_reader_drains_early_error_ack(self):
        for reason in ("context_live", "group_identity", "inactive_group"):
            with self.subTest(reason=reason):
                owner, desc = fixture(n=32)
                h = Coupled(owner, desc)
                if reason == "context_live": h.controller.seen = 1
                if reason == "group_identity": h.controller.group_sequence = 2
                if reason == "inactive_group": h.controller.group_active = False
                h.tick(start=True)
                h.until(lambda: h.reader.state == "read_low")
                self.assertTrue(h.controller.response().error)
                out = h.tick()
                self.assertTrue(out["ack_fire"])
                self.assertFalse(out["completed"])
                self.assertIsNone(out["read"])
                self.assertIsNone(out["beat"])
                self.assertTrue(h.reader.poison)
                self.assertEqual(h.reader.reads, 0)
                self.assertEqual(h.controller.writes, 0)
                self.assertIn((0, 0), owner.quarantined)


if __name__ == "__main__":
    unittest.main()
