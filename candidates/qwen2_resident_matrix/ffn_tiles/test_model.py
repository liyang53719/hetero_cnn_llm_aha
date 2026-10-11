"""Shared-bank port limits and tile lifetime; no arithmetic or RTL execution."""
from pathlib import Path
import importlib.util
import sys
import unittest
from dataclasses import replace

spec = importlib.util.spec_from_file_location("ffn_tile_model", Path(__file__).with_name("model.py"))
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def ctl(op=0, slot=0, identity=3, ng=0, rows=16, cols=32):
    return m.Control(op, slot, identity, ng, rows, cols)


def values(index=0):
    return tuple(0x3f000000 + index*16 + i for i in range(16))


def fill(b, c):
    assert b.tick(control=c)["ctl_fire"]
    for index in range(c.rows//16*c.cols):
        q = m.Write(c.slot, c.identity, c.ng, index, values(index))
        assert b.tick(write=q)["write_fire"]
        assert b.tick()["rmw_commit"]
    assert b.tick(control=replace(c, op=1))["ctl_fire"]
    assert not b.poison


def read_one(b, c, index):
    assert b.tick(read=m.Read(c.slot, c.identity, c.ng, index))["read_fire"]
    assert not b.tick()["response_fire"]
    e = b.tick()
    assert e["response_fire"]
    return e["response"]


class TileTests(unittest.TestCase):
    def test_actual_dense_port_model_can_run_with_live_high_slots(self):
        # Existing Dense port/control model performs real clears, RMW ingress,
        # gathers and result stores. Its Matrix values remain opaque tokens.
        path = Path(__file__).resolve().parent.parent / "transposed_down/test_model.py"
        spec = importlib.util.spec_from_file_location("ffn_prior_down_harness", path)
        harness = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = harness
        spec.loader.exec_module(harness)
        b = m.TileBankModel()
        fill(b, ctl())
        saved = [list(bank[768:1248]) for bank in b.banks.words]
        self.assertEqual(b.job_admission("Dense", 32), (True, None))
        h = harness.Harness(n=32, m_rows=16, k=32, split_k=2560)
        owner = harness.m.DenseOwnerModel(h.workspace)
        owner.a_banks = b.banks
        owner.tick(job=h.job)
        h.owner = owner
        h.until(lambda: h.response is not None)
        self.assertIsNone(h.response[1])
        self.assertEqual([bank[768:1248] for bank in b.banks.words], saved)
        self.assertTrue(b.tags[0].live)
        self.assertEqual(read_one(b, ctl(), 0).words, values())
        self.assertEqual(b.job_admission("Dense", 8960), (True, "Bounds"))
        self.assertEqual(b.job_admission("Activation", 1536), (True, "Unsupported"))
        self.assertEqual(b.job_admission("Dense", 1536, silu_busy=True), (False, None))

    def test_all_physical_cells_in_reserved_three_slots_and_no_alias(self):
        cells = set()
        for slot in range(3):
            for rg in range(8):
                for n in range(160):
                    word, lane = m.location(slot, rg, n)
                    self.assertTrue(768+slot*160 <= word < 928+slot*160)
                    for bank in range(16):
                        self.assertNotIn((bank, word, lane), cells)
                        cells.add((bank, word, lane))
        self.assertEqual(len(cells)*4, 245760)
        self.assertEqual(393216+len(cells)*4, 638976)
        for bad in ((3, 0, 0), (0, 8, 0), (0, 0, 160)):
            with self.assertRaises(ValueError):
                m.location(*bad)

    def test_one_read_one_write_and_rmw_preserves_other_fp32_lanes(self):
        b = m.TileBankModel()
        sentinel = sum((0x3e000000+i) << (i*32) for i in range(8))
        for bank in range(16):
            b.banks.words[bank][768] = sentinel
        b.tick(control=ctl())
        e = b.tick(write=m.Write(0, 3, 0, 0, values()))
        self.assertEqual(len(e["reads"]), 16)
        self.assertFalse(e["writes"])
        e = b.tick()
        self.assertEqual(len(e["writes"]), 16)
        self.assertFalse(e["reads"])
        for bank in range(16):
            self.assertEqual(b.banks.words[bank][768] >> 32, sentinel >> 32)
            self.assertEqual(b.banks.words[bank][768] & 0xffffffff, values()[bank])
        self.assertEqual(b.counters["physical_read_bytes"], 512)
        self.assertEqual(b.counters["physical_write_bytes"], 512)
        self.assertEqual(b.counters["logical_write_bytes"], 64)

    def test_real_shared_bank_object_and_retained_input_spare_unchanged(self):
        dense = m.down.DenseOwnerModel()
        bank = dense.a_banks
        for i in range(16):
            for word in list(range(768)) + list(range(1248, 1376)):
                bank.words[i][word] = (i+1)*1376+word
        before = [(i, w, bank.words[i][w]) for i in range(16)
                  for w in list(range(768))+list(range(1248, 1376))]
        b = m.TileBankModel(bank)
        self.assertIs(b.banks, dense.a_banks)
        for slot in range(3):
            fill(b, ctl(slot=slot))
        self.assertTrue(all(bank.words[i][w] == value for i, w, value in before))

    def test_ordered_seal_read_release_reuse_for_m128_tail96(self):
        b = m.TileBankModel()
        c = ctl(slot=2, ng=8864, rows=128, cols=96)
        fill(b, c)
        for index in range(768):
            r = read_one(b, c, index)
            self.assertEqual(r.words, values(index))
            self.assertEqual((r.slot, r.identity, r.ng, r.index), (2, 3, 8864, index))
        b.tick(control=replace(c, op=2))
        self.assertFalse(b.leased)
        self.assertFalse(b.tags[2].sealed)
        self.assertFalse(b.poison)
        b.tick(control=replace(c, identity=4))
        self.assertTrue(b.tags[2].live)
        self.assertEqual(b.tags[2].produced, 0)

    def test_write_request_is_not_production_and_read_request_is_not_consumption(self):
        b = m.TileBankModel()
        b.tick(control=ctl())
        b.tick(write=m.Write(0, 3, 0, 0, values()))
        self.assertEqual(b.tags[0].produced, 0)
        b.tick()
        self.assertEqual(b.tags[0].produced, 1)
        for index in range(1, 32):
            b.tick(write=m.Write(0, 3, 0, index, values(index)))
            b.tick()
        b.tick(control=ctl(op=1))
        b.tick(read=m.Read(0, 3, 0, 0))
        b.tick(response_ready=False)
        self.assertEqual(b.tags[0].consumed, 0)
        r = b.response
        for _ in range(9):
            e = b.tick(response_ready=False)
            self.assertEqual(e["response"], r)
            self.assertFalse(e["reads"] or e["writes"])
        self.assertTrue(b.tick()["response_fire"])
        self.assertEqual(b.tags[0].consumed, 1)

    def test_early_seal_release_and_duplicate_begin_poison(self):
        for op in (0, 1, 2):
            b = m.TileBankModel()
            b.tick(control=ctl())
            b.tick(control=ctl(op=op))
            self.assertTrue(b.poison)
            self.assertFalse(b.tick(write=m.Write(0, 3, 0, 0, values()))["write_fire"])

    def test_invalid_metadata_never_reads_or_writes_sram(self):
        bad_controls = (replace(ctl(), slot=3), replace(ctl(), identity=0), replace(ctl(), ng=1),
                        replace(ctl(), rows=32), replace(ctl(), cols=16), replace(ctl(), op=3))
        for q in bad_controls:
            b = m.TileBankModel()
            e = b.tick(control=q)
            self.assertTrue(e["ctl_fire"] and b.poison)
            self.assertFalse(e["reads"] or e["writes"])
        for q in (m.Write(0, 3, 0, 1, values()), m.Write(0, 4, 0, 0, values()),
                  m.Write(0, 3, 32, 0, values()), m.Write(0, 3, 0, 0, (0x7fc00001,)*16)):
            b = m.TileBankModel()
            b.tick(control=ctl())
            e = b.tick(write=q)
            self.assertTrue(e["write_fire"] and b.poison)
            self.assertFalse(e["reads"] or e["writes"])

    def test_single_operation_priority_and_dense_conflict_backpressure(self):
        b = m.TileBankModel()
        e = b.tick(control=ctl(), write=m.Write(0, 3, 0, 0, values()), read=m.Read(0, 3, 0, 0))
        self.assertTrue(e["ctl_fire"])
        self.assertFalse(e["write_fire"] or e["read_fire"])
        e = b.tick(write=m.Write(0, 3, 0, 0, values()), owner_quiescent=False,
                   dense_writes=[(0, 768, 0)])
        self.assertFalse(e["write_fire"] or e["dense_grant"])
        self.assertFalse(e["reads"] or e["writes"])

    def test_live_tiles_allow_dense_low_region_but_never_second_bank_ports(self):
        b = m.TileBankModel()
        fill(b, ctl())
        stored = [b.banks.words[i][768] for i in range(16)]
        e = b.tick(owner_quiescent=False, dense_reads=[(i, 767) for i in range(16)],
                   dense_writes=[(i, 0, i+1) for i in range(16)],
                   read=m.Read(0, 3, 0, 0))
        self.assertTrue(e["dense_grant"])
        self.assertFalse(e["read_fire"])
        self.assertEqual(len(e["reads"]), 16)
        self.assertEqual(len(e["writes"]), 16)
        self.assertEqual([b.banks.words[i][768] for i in range(16)], stored)
        b.tick(read=m.Read(0, 3, 0, 0))
        e = b.tick(owner_quiescent=False, dense_reads=[(0, 0)])
        self.assertFalse(e["dense_grant"])
        self.assertFalse(e["reads"])
        self.assertTrue(b.tick()["response_fire"])
        self.assertFalse(b.poison)

    def test_abort_keeps_accepted_rmw_mandatory_and_rejects_new_work(self):
        b = m.TileBankModel()
        b.tick(control=ctl())
        b.tick(write=m.Write(0, 3, 0, 0, values()))
        e = b.tick(abort=True, owner_quiescent=False, dense_writes=[(0, 768, 0)])
        self.assertTrue(e["rmw_commit"])
        self.assertFalse(e["dense_grant"])
        self.assertTrue(b.poison)
        self.assertEqual(b.tags[0].produced, 1)
        self.assertFalse(b.tick(control=ctl(op=1))["ctl_fire"])

    def test_abort_does_not_retract_or_modify_stalled_response(self):
        b = m.TileBankModel()
        fill(b, ctl())
        b.tick(read=m.Read(0, 3, 0, 0))
        b.tick(response_ready=False)
        held = b.response
        for _ in range(5):
            e = b.tick(abort=True, response_ready=False)
            self.assertEqual(e["response"], held)
        self.assertTrue(b.tick()["response_fire"])
        self.assertTrue(b.idle and b.poison)
        self.assertTrue(b.tags[0].live)

    def test_poisoned_nonfinite_response_is_stable_and_drainable(self):
        b = m.TileBankModel()
        fill(b, ctl())
        b.banks.words[0][768] = (b.banks.words[0][768] & ~0xffffffff) | 0x7f800000
        b.tick(read=m.Read(0, 3, 0, 0))
        b.tick()
        self.assertTrue(b.response.error and b.poison)
        self.assertTrue(b.tick()["response_fire"])

    def test_reset_invalidates_all_tags_without_erasing_sram(self):
        b = m.TileBankModel()
        fill(b, ctl())
        saved = b.banks.words[0][768]
        b.tick(abort=True)
        b.tick(coordinated_reset=True)
        self.assertFalse(b.leased or b.poison)
        self.assertEqual(b.banks.words[0][768], saved)
        e = b.tick(read=m.Read(0, 3, 0, 0))
        self.assertTrue(e["read_fire"] and b.poison)
        self.assertFalse(e["reads"])


if __name__ == "__main__":
    unittest.main()
