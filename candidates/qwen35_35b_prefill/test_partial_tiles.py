"""Synthetic physical port/control checks; no numerical owner or DDR-ACK claim."""
from dataclasses import replace
import hashlib
import unittest

from . import partial_tiles as m


def values(index=0, source=0):
    # Finite opaque encodings, distinct at every lane/beat/source. These are
    # transport sentinels, explicitly NOT the numerical sum of lhs and rhs.
    return tuple(0x3D000000 + source * 0x100000 + index * 16 + bank for bank in range(16))


def ctl(op=0, slot=0, identity=11, rows=16, cols=32, **kwargs):
    return m.Control(op, slot, identity, 0, rows, cols, **kwargs)


def fill(bank, control, *, legacy=False):
    wire = m.window.Write if legacy else m.Write
    assert bank.tick(control=control)["ctl_fire"]
    count = control.rows // 16 * control.cols
    for produced in range(count):
        index = (m.producer_index(produced, control.rows, control.cols)
                 if control.matrix_producer_order else produced)
        edge = bank.tick(write=wire(control.slot, control.identity, control.ng,
                                    index, values(index, control.slot)))
        assert edge["write_fire"] and not bank.poison
        assert len(edge["reads"]) == 16 and not edge["writes"]
        assert bank.tags[control.slot].produced == produced
        edge = bank.tick()
        assert edge["rmw_commit"] and len(edge["writes"]) == 16 and not edge["reads"]
    assert bank.tick(control=replace(control, op=1))["ctl_fire"]
    assert not bank.poison


def stage(*, rows=16, cols=32, matrix=False, legacy=False, banks=None):
    bank = m.TileBankModel(banks)
    wire = m.window.Control if legacy else m.Control
    for slot in range(2):
        fill(bank, wire(0, slot, 11 + slot, 0, rows, cols,
                        matrix_producer_order=matrix), legacy=legacy)
    call = m.BeginOverwrite(21, 0, rows, cols, 11, 12)
    return bank, call


def begin(bank, call):
    assert bank.tick(control=call)["ctl_fire"]
    assert bank.overwrite is not None and not bank.poison


def consume(bank, query, stall=0):
    edge = bank.tick(read=query)
    assert edge["read_fire"] and not edge["response_fire"] and not bank.poison
    assert len(edge["reads"]) == 16 and not edge["writes"]
    edge = bank.tick(response_ready=False)
    assert not edge["response_fire"] and not edge["reads"] and not edge["writes"]
    held = bank.response
    assert held is not None
    for _ in range(stall):
        edge = bank.tick(response_ready=False)
        assert edge["response"] == held and not edge["response_fire"]
        assert not edge["reads"] and not edge["writes"]
    edge = bank.tick()
    assert edge["response_fire"] and edge["response"] == held
    return held


def operands(bank, call, index):
    lhs = consume(bank, m.Read(call.lhs_slot, call.lhs_identity, call.ng, index, phase="lhs"))
    rhs = consume(bank, m.Read(call.rhs_slot, call.rhs_identity, call.ng, index, phase="rhs"))
    assert lhs.words == values(index, call.lhs_slot)
    assert rhs.words == values(index, call.rhs_slot)


def add_result(call, index):
    return m.Write(call.lhs_slot, call.identity, call.ng, index, values(index, 2), phase="sum")


def seal(call):
    return m.Control(1, call.lhs_slot, call.identity, call.ng, call.rows, call.cols, phase="sum")


def reduce(bank, call):
    begin(bank, call)
    for index in range(call.beats):
        operands(bank, call, index)
        assert bank.tick(write=add_result(call, index))["write_fire"]
        assert not bank.sum_ready
        assert bank.tick()["rmw_commit"]
        assert not bank.sum_ready
    assert bank.tick(control=seal(call))["ctl_fire"]
    assert bank.sum_ready and not bank.poison


def footprint(bank, ranges):
    digest = hashlib.sha256()
    for cells in bank.banks.words:
        for begin_, end in ranges:
            for word in cells[begin_:end]:
                digest.update(word.to_bytes(32, "little"))
    return digest.hexdigest()


class PartialTileTests(unittest.TestCase):
    def test_complete_physical_layout_and_five_contexts(self):
        ledger = m.resource_ledger()
        self.assertEqual(ledger["total_bytes"], 704512)
        self.assertEqual(ledger["matrix_contexts"], 5)
        self.assertEqual(ledger["additional_tensor_storage_bytes"], 0)
        ranges = [ledger[key] for key in ("a_words", "lhs_words", "rhs_words", "spare_words")]
        self.assertEqual(ranges, [(0, 1024), (1024, 1184), (1184, 1344), (1344, 1376)])
        self.assertEqual(sum(end - start for start, end in ranges), 1376)
        cells = set()
        for slot in range(2):
            words = set()
            for group in range(8):
                for column in range(160):
                    word, lane = m.location(slot, group, column)
                    words.add(word)
                    for bank in range(16):
                        self.assertNotIn((bank, word, lane), cells)
                        cells.add((bank, word, lane))
            self.assertEqual(words, set(range(1024 + slot * 160, 1184 + slot * 160)))
        self.assertEqual(len(cells) * 4, 2 * 81920)
        for bad in ((2, 0, 0), (-1, 0, 0), (0, 8, 0), (0, 0, 160), (False, 0, 0)):
            with self.assertRaises(ValueError):
                m.location(*bad)

    def test_full_k2048_a_and_both_partials_coexist_in_actual_shared_banks(self):
        owner = m.down.DenseOwnerModel()
        banks = owner.a_banks
        # Cover every physical cell of full BF16 M128 K2048 A through the
        # original real A mapping, not just a command-index capacity formula.
        seen = set()
        for k in range(2048):
            for row in range(128):
                bank, word, lane = m.down.a_address(k, row)
                key = (bank, word, lane)
                self.assertNotIn(key, seen)
                seen.add(key)
                banks.words[bank][word] |= ((k * 131 + row) & 0xFFFF) << (16 * lane)
        self.assertEqual(len(seen), 16 * 1024 * 16)
        for bank in range(16):
            for word in range(1344, 1376):
                banks.words[bank][word] = (bank + 1) * 1376 + word
        b = m.TileBankModel(banks)
        self.assertIs(b.banks, owner.a_banks)
        a_spare_before = footprint(b, ((0, 1024), (1344, 1376)))
        for slot in range(2):
            fill(b, ctl(slot=slot, identity=11 + slot, rows=128, cols=160,
                        matrix_producer_order=True))
        rhs_before = footprint(b, ((1184, 1344),))
        call = m.BeginOverwrite(21, 0, 128, 160, 11, 12)
        reduce(b, call)
        self.assertEqual(footprint(b, ((0, 1024), (1344, 1376))), a_spare_before)
        self.assertEqual(footprint(b, ((1184, 1344),)), rhs_before)
        self.assertEqual(b.counters["operand_responses"], 2 * 1280)
        self.assertEqual(b.tags[0].produced, 1280)
        self.assertEqual((b.tags[0].identity, b.tags[0].phase, b.tags[0].consumed), (21, "sum", 0))
        self.assertFalse(b.tags[1].live)
        for index in range(1280):
            response = consume(b, m.Read(0, 21, 0, index, phase="sum"))
            self.assertEqual(response.words, values(index, 2))
        b.tick(control=replace(seal(call), op=2))
        self.assertFalse(b.leased or b.sum_ready or b.poison)

    def test_original_phase_less_wires_keep_exact_authority_and_context_order(self):
        b, call = stage(rows=128, cols=160, matrix=True, legacy=True)
        self.assertIsInstance(b, m.window.TileBankModel)
        self.assertIsInstance(m.Control(0, 0, 1, 0, 128, 160), m.window.Control)
        self.assertIsInstance(m.Write(0, 1, 0, 0, values()), m.window.Write)
        order = [m.producer_index(index, 128, 160) for index in range(1280)]
        self.assertEqual(order[:33], list(range(32)) + [160])
        self.assertEqual(order[256], 32)
        self.assertEqual(set(order), set(range(1280)))
        self.assertEqual(consume(b, m.window.Read(0, 11, 0, 0)).words, values())
        self.assertEqual(b.job_admission("Dense", 2048), (True, None))
        self.assertEqual(b.job_admission("Dense", 2080), (True, "Bounds"))
        self.assertEqual(b.job_admission("Activation", 2048), (True, "Unsupported"))
        # A partial that has already been consumed cannot enter overwrite.
        b.tick(control=call)
        self.assertTrue(b.poison)

    def test_wrong_row_major_producer_order_rejected(self):
        b = m.TileBankModel()
        b.tick(control=ctl(rows=128, cols=160, matrix_producer_order=True))
        for index in range(32):
            b.tick(write=m.Write(0, 11, 0, index, values(index)))
            b.tick()
        edge = b.tick(write=m.Write(0, 11, 0, 32, values(32)))
        self.assertTrue(edge["write_fire"] and b.poison)
        self.assertFalse(edge["reads"] or edge["writes"])

    def test_begin_overwrite_revokes_old_tags_and_does_not_allocate_slot_two(self):
        b, call = stage()
        begin(b, call)
        self.assertEqual(len(b.tags), 2)
        self.assertTrue(b.leased)
        self.assertTrue(all(not tag.live and not tag.sealed for tag in b.tags))
        self.assertFalse(b.sum_ready)
        self.assertEqual(b.job_admission("Dense", 2048), (False, None))
        edge = b.tick(owner_quiescent=False, dense_reads=[(0, 0)])
        self.assertFalse(edge["dense_grant"] or edge["reads"] or edge["writes"])

    def test_rmw_consumes_both_real_responses_and_preserves_other_lanes(self):
        b, call = stage()
        begin(b, call)
        word, lane = m.location(0, 0, 0)
        before = tuple(bank[word] for bank in b.banks.words)
        operands(b, call, 0)
        self.assertEqual((b.overwrite.lhs_consumed, b.overwrite.rhs_consumed), (1, 1))
        edge = b.tick(write=add_result(call, 0))
        self.assertTrue(edge["write_fire"])
        self.assertEqual(tuple(bank[word] for bank in b.banks.words), before)
        self.assertEqual(b.tags[0].produced, 0)
        self.assertEqual(b.overwrite.stage, "rmw")
        edge = b.tick(owner_quiescent=False, dense_writes=[(0, word, 0)])
        self.assertTrue(edge["rmw_commit"])
        self.assertFalse(edge["dense_grant"] or edge["reads"])
        self.assertEqual(len(edge["writes"]), 16)
        for bank in range(16):
            actual = b.banks.words[bank][word]
            self.assertEqual(actual >> 32, before[bank] >> 32)
            self.assertEqual(actual & 0xFFFFFFFF, values(0, 2)[bank])
        self.assertEqual(b.overwrite.index, 1)
        self.assertEqual(b.tags[0].produced, 1)

    def test_early_write_before_operands_or_after_only_lhs_faults_without_sram(self):
        for consume_lhs in (False, True):
            b, call = stage()
            begin(b, call)
            if consume_lhs:
                consume(b, m.Read(0, 11, 0, 0, phase="lhs"))
            before = footprint(b, ((1024, 1344),))
            edge = b.tick(write=add_result(call, 0))
            self.assertTrue(edge["write_fire"] and b.poison)
            self.assertFalse(edge["reads"] or edge["writes"] or b.sum_ready)
            self.assertEqual(footprint(b, ((1024, 1344),)), before)

    def test_response_backpressure_is_consumption_fence_and_preserves_payload(self):
        b, call = stage()
        begin(b, call)
        b.tick(read=m.Read(0, 11, 0, 0, phase="lhs"))
        b.tick(response_ready=False)
        held = b.response
        for _ in range(7):
            edge = b.tick(response_ready=False, write=add_result(call, 0),
                          read=m.Read(1, 12, 0, 0, phase="rhs"))
            self.assertEqual(edge["response"], held)
            self.assertFalse(edge["write_fire"] or edge["read_fire"] or edge["response_fire"])
            self.assertEqual(b.overwrite.lhs_consumed, 0)
            self.assertFalse(edge["reads"] or edge["writes"])
        self.assertTrue(b.tick()["response_fire"])
        self.assertEqual(b.overwrite.lhs_consumed, 1)
        self.assertEqual(b.overwrite.stage, "rhs")
        consume(b, m.Read(1, 12, 0, 0, phase="rhs"), stall=7)
        self.assertEqual(b.overwrite.rhs_consumed, 1)

    def test_bad_phase_identity_index_and_legacy_access_are_rejected(self):
        bad_reads = [m.Read(0, 11, 0, 0), m.window.Read(0, 11, 0, 0),
                     m.Read(0, 21, 0, 0, phase="lhs"),
                     m.Read(1, 12, 0, 0, phase="rhs"),
                     m.Read(0, 11, 0, 1, phase="lhs"),
                     m.Read(0, 11, 32, 0, phase="lhs"),
                     m.Read(2, 11, 0, 0, phase="lhs"),
                     m.Read(0, True, 0, 0, phase="lhs"),
                     m.Read(0, 11, 0, False, phase="lhs"),
                     m.Read(0, 11, 0, 0, phase="sum")]
        for query in bad_reads:
            with self.subTest(query=query):
                b, call = stage()
                begin(b, call)
                edge = b.tick(read=query)
                self.assertTrue(edge["read_fire"] and b.poison)
                self.assertFalse(edge["reads"] or edge["writes"])
        for query in (m.window.Write(0, 21, 0, 0, values()),
                      m.Write(0, 11, 0, 0, values(), phase="sum"),
                      m.Write(1, 21, 0, 0, values(), phase="sum"),
                      m.Write(0, 21, 0, 1, values(), phase="sum")):
            b, call = stage()
            begin(b, call)
            operands(b, call, 0)
            edge = b.tick(write=query)
            self.assertTrue(edge["write_fire"] and b.poison)
            self.assertFalse(edge["reads"] or edge["writes"])

    def test_duplicate_operand_and_old_overwritten_beat_cannot_be_reread(self):
        for after_write in (False, True):
            b, call = stage()
            begin(b, call)
            consume(b, m.Read(0, 11, 0, 0, phase="lhs"))
            if after_write:
                consume(b, m.Read(1, 12, 0, 0, phase="rhs"))
                b.tick(write=add_result(call, 0))
                b.tick()
            edge = b.tick(read=m.Read(0, 11, 0, 0, phase="lhs"))
            self.assertTrue(b.poison)
            self.assertFalse(edge["reads"] or edge["writes"])

    def test_sum_only_seals_after_final_rmw_and_explicit_control(self):
        b, call = stage()
        begin(b, call)
        for index in range(call.beats):
            operands(b, call, index)
            b.tick(write=add_result(call, index))
            if index == call.beats - 1:
                # A seal held valid on final RMW edge is backpressured; the
                # physically accepted write still retires on that edge.
                edge = b.tick(control=seal(call))
                self.assertTrue(edge["rmw_commit"])
                self.assertFalse(edge["ctl_fire"] or b.sum_ready)
            else:
                b.tick()
        self.assertFalse(b.tags[0].live or b.tags[0].sealed)
        self.assertTrue(b.tick(control=seal(call))["ctl_fire"])
        self.assertTrue(b.sum_ready)
        self.assertEqual(b.counters["sum_seals"], 1)
        self.assertFalse(b.tags[1].live)

    def test_early_seal_and_release_never_publish(self):
        for operation in (1, 2):
            b, call = stage()
            begin(b, call)
            edge = b.tick(control=replace(seal(call), op=operation))
            self.assertTrue(edge["ctl_fire"] and b.poison)
            self.assertFalse(b.sum_ready or edge["reads"] or edge["writes"])

    def test_stale_identity_or_phase_after_publication_cannot_read_sum(self):
        bad = [m.window.Read(0, 11, 0, 0), m.Read(0, 11, 0, 0, phase="sum"),
               m.Read(0, 21, 0, 0), m.Read(0, 11, 0, 0, phase="lhs"),
               m.Read(1, 12, 0, 0, phase="rhs")]
        for query in bad:
            b, call = stage()
            reduce(b, call)
            edge = b.tick(read=query)
            self.assertTrue(b.poison)
            self.assertFalse(edge["reads"] or edge["writes"] or b.sum_ready)

    def test_final_sum_response_hold_blocks_release_until_consumed(self):
        b, call = stage()
        reduce(b, call)
        for index in range(call.beats - 1):
            consume(b, m.Read(0, 21, 0, index, phase="sum"))
        b.tick(read=m.Read(0, 21, 0, call.beats - 1, phase="sum"))
        b.tick(response_ready=False)
        held = b.response
        for _ in range(5):
            edge = b.tick(control=replace(seal(call), op=2), response_ready=False)
            self.assertEqual(edge["response"], held)
            self.assertFalse(edge["ctl_fire"] or edge["reads"] or edge["writes"])
            self.assertTrue(b.tags[0].live)
            self.assertEqual(b.tags[0].consumed, call.beats - 1)
        self.assertTrue(b.tick()["response_fire"])
        self.assertTrue(b.tick(control=replace(seal(call), op=2))["ctl_fire"])
        self.assertFalse(b.leased or b.poison)
        self.assertEqual((b.tags[0].identity, b.tags[0].ng, b.tags[0].rows,
                          b.tags[0].cols, b.tags[0].phase, b.tags[0].consumed),
                         (call.identity, call.ng, call.rows, call.cols, "sum", call.beats))
        self.assertFalse(b.tags[0].live or b.tags[0].sealed)

    def test_control_write_read_priority_and_pending_edge_exclusion(self):
        b = m.TileBankModel()
        edge = b.tick(control=ctl(), write=m.Write(0, 11, 0, 0, values()), read=m.Read(0, 11, 0, 0))
        self.assertTrue(edge["ctl_fire"])
        self.assertFalse(edge["write_fire"] or edge["read_fire"])
        edge = b.tick(write=m.Write(0, 11, 0, 0, values()), read=m.Read(0, 11, 0, 0))
        self.assertTrue(edge["write_fire"])
        self.assertFalse(edge["read_fire"])
        edge = b.tick(write=m.Write(0, 11, 0, 1, values(1)))
        self.assertTrue(edge["rmw_commit"])
        self.assertFalse(edge["write_fire"] or edge["reads"])

    def test_dense_low_region_1r1w_and_conflicts_fail_before_access(self):
        b, _ = stage()
        edge = b.tick(owner_quiescent=False, dense_reads=[(i, 1023) for i in range(16)],
                      dense_writes=[(i, 0, i + 1) for i in range(16)])
        self.assertTrue(edge["dense_grant"])
        self.assertEqual((len(edge["reads"]), len(edge["writes"])), (16, 16))
        bad = [([(0, 1024)], []), ([], [(0, 1184, 0)]),
               ([(0, 0), (0, 1)], []), ([], [(0, 0, 1), (0, 1, 2)]),
               ([(0, 0)], [(0, 0, 1)]), ([(16, 0)], [])]
        for reads, writes in bad:
            b, _ = stage()
            edge = b.tick(owner_quiescent=False, dense_reads=reads, dense_writes=writes)
            self.assertTrue(b.poison)
            self.assertFalse(edge["dense_grant"] or edge["reads"] or edge["writes"])

    def test_abort_after_accepted_sum_write_retires_edge_then_poison_until_reset(self):
        b, call = stage()
        begin(b, call)
        operands(b, call, 0)
        b.tick(write=add_result(call, 0))
        edge = b.tick(abort=True, control=seal(call), owner_quiescent=False,
                      dense_writes=[(0, 1024, 0)])
        self.assertTrue(edge["rmw_commit"] and b.poison)
        self.assertFalse(edge["ctl_fire"] or edge["dense_grant"] or b.sum_ready)
        self.assertEqual(b.banks.words[0][1024] & 0xFFFFFFFF, values(0, 2)[0])
        self.assertEqual(b.tags[0].produced, 1)
        self.assertTrue(all(tag.poisoned and not tag.live for tag in b.tags))
        for _ in range(3):
            edge = b.tick(read=m.Read(0, 11, 0, 0, phase="lhs"), control=ctl())
            self.assertFalse(edge["ctl_fire"] or edge["read_fire"] or edge["reads"] or edge["writes"])
        retained = footprint(b, ((0, 1376),))
        self.assertTrue(b.tick(coordinated_reset=True)["reset"])
        self.assertFalse(b.poison or b.leased)
        self.assertEqual(footprint(b, ((0, 1376),)), retained)
        # Reset leaves physical stale bytes, but they have no readable tag.
        edge = b.tick(read=m.Read(0, 21, 0, 0, phase="sum"))
        self.assertTrue(b.poison)
        self.assertFalse(edge["reads"])
        b.tick(coordinated_reset=True)
        for slot in range(2):
            fill(b, ctl(slot=slot, identity=11 + slot))
        reduce(b, call)
        self.assertTrue(b.sum_ready)

    def test_reset_cannot_drop_accepted_rmw_or_held_read_response(self):
        b = m.TileBankModel()
        b.tick(control=ctl())
        b.tick(write=m.Write(0, 11, 0, 0, values()))
        edge = b.tick(coordinated_reset=True)
        self.assertTrue(edge["rmw_commit"] and b.poison)
        self.assertFalse(edge["reset"])
        self.assertEqual(b.banks.words[0][1024] & 0xFFFFFFFF, values()[0])
        self.assertTrue(b.tick(coordinated_reset=True)["reset"])
        b, call = stage()
        begin(b, call)
        b.tick(read=m.Read(0, 11, 0, 0, phase="lhs"))
        b.tick(response_ready=False)
        held = b.response
        edge = b.tick(coordinated_reset=True, response_ready=False)
        self.assertEqual(edge["response"], held)
        self.assertFalse(edge["reset"])
        self.assertTrue(b.poison)
        self.assertTrue(b.tick()["response_fire"])
        self.assertTrue(b.tick(coordinated_reset=True)["reset"])

    def test_abort_preserves_stalled_response_and_marks_pending_read_error(self):
        for abort_before_response in (False, True):
            b, call = stage()
            begin(b, call)
            b.tick(read=m.Read(0, 11, 0, 0, phase="lhs"))
            b.tick(response_ready=False, abort=abort_before_response)
            held = b.response
            self.assertEqual(held.error, abort_before_response)
            for _ in range(4):
                edge = b.tick(abort=True, response_ready=False)
                self.assertEqual(edge["response"], held)
                self.assertFalse(edge["response_fire"])
            self.assertTrue(b.tick()["response_fire"])
            self.assertTrue(b.idle and b.poison)
            self.assertFalse(b.sum_ready)

    def test_invalid_overwrite_metadata_cannot_relabel_or_read_storage(self):
        base = m.BeginOverwrite(21, 0, 16, 32, 11, 12)
        bad = [replace(base, identity=11), replace(base, identity=12),
               replace(base, identity=0), replace(base, identity=2**32),
               replace(base, identity=True), replace(base, lhs_identity=10),
               replace(base, rhs_identity=2**32), replace(base, rhs_slot=0),
               replace(base, lhs_slot=2), replace(base, rows=32),
               replace(base, cols=192), replace(base, ng=1), replace(base, ng=2**16)]
        for query in bad:
            b, _ = stage()
            edge = b.tick(control=query)
            self.assertTrue(edge["ctl_fire"] and b.poison)
            self.assertFalse(edge["reads"] or edge["writes"] or b.sum_ready)

    def test_nonfinite_write_and_actual_sram_response_poison(self):
        b, call = stage()
        begin(b, call)
        operands(b, call, 0)
        edge = b.tick(write=replace(add_result(call, 0), words=(0x7FC00001,) * 16))
        self.assertTrue(b.poison)
        self.assertFalse(edge["reads"] or edge["writes"])
        b, call = stage()
        begin(b, call)
        b.banks.words[0][1024] = (b.banks.words[0][1024] & ~0xFFFFFFFF) | 0x7F800000
        b.tick(read=m.Read(0, 11, 0, 0, phase="lhs"))
        b.tick()
        self.assertTrue(b.response.error and b.poison)
        self.assertTrue(b.tick()["response_fire"])
        self.assertFalse(b.sum_ready)

    def test_legacy_layout_is_unchanged_and_old_third_slot_remains_real(self):
        old = m.window.TileBankModel()
        self.assertEqual(len(old.tags), 3)
        self.assertEqual(m.window.tiles.location(0, 0, 0), (768, 0))
        self.assertEqual(m.window.tiles.location(2, 7, 159), (1247, 7))
        old.tick(control=m.window.Control(0, 2, 11, 0, 16, 32))
        old.tick(write=m.window.Write(2, 11, 0, 0, values()))
        self.assertTrue(old.tick()["rmw_commit"])
        self.assertEqual(old.banks.words[0][1088] & 0xFFFFFFFF, values()[0])


if __name__ == "__main__":
    unittest.main()
