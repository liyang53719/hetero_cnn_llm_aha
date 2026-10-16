"""Cold, bounded tests of the single-parent-edge scratch/KV arbiter.

No native library, RTL, arithmetic owner substitute, or numerical PASS claim.
"""
import ast
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from ..attention_packed_owner.protocol import ScratchAction, ScratchResponse
from ..attention_bank_scratch.port import RawKvPort, location
from ..raw_kv.model import RawKvPort as OriginalRawKvPort, Key, Request, Response
from ..raw_kv_parent.model import ParentLoan
from .mux import ScratchMux


class MuxTests(unittest.TestCase):
    def setUp(self):
        self.parent = ParentLoan(enabled=True)
        self.banks = self.parent.owner.a_banks
        self.words = self.banks.words
        self.mux = ScratchMux(self.parent, owner_id=17)
        self.serial = 0

    def action(self, operation, generation=1, query=0, kv_head=0, line=0, words=()):
        self.serial += 1
        return ScratchAction(self.serial, operation, generation, query, kv_head, line, words)

    def edge(self, *, controls=None, state='idle', core_pending=False,
             ddr_pending=False, action=None, response_ready=False,
             abort=False, closing=False, raw_ack_ready=True, replace_ack=None):
        before = self.parent.owner.clock
        counts = dict(self.mux.counts)
        merged = self.mux.prepare(controls={} if controls is None else controls,
            state=state, core_pending=core_pending, ddr_pending=ddr_pending,
            action=action, response_ready=response_ready, abort=abort,
            closing=closing, raw_ack_ready=raw_ack_ready)
        self.assertEqual(self.parent.owner.clock, before)
        if replace_ack is not None:
            merged['ack'] = replace_ack
        actual = self.parent.tick(**merged)
        result = self.mux.observe(actual)
        self.assertEqual(self.parent.owner.clock, before + 1)
        self.assertEqual(result['clock_before'], before)
        self.assertEqual(result['clock_after'], before + 1)
        self.assertEqual(result['counts_before'], counts)
        self.assertEqual(result['counts_after'], self.mux.counts)
        self.assertIs(self.parent.raw.banks, self.banks)
        self.assertIs(self.banks.words, self.words)
        return result, actual, self.mux.supply_raw(actual)

    def consume(self):
        response = self.mux.response
        self.assertIs(type(response), ScratchResponse)
        out, _, _ = self.edge(response_ready=True)
        self.assertIs(out['response'], response)
        self.assertTrue(out['response_fire'])
        self.assertIsNone(self.mux.response)
        return response

    def immediate(self, operation, **kwargs):
        a = self.action(operation, **kwargs)
        out, actual, supply = self.edge(action=a)
        self.assertTrue(out['accepted'])
        response = self.consume()
        self.assertIs(response.action, a)
        return response, actual, supply

    def begin(self):
        self.assertFalse(self.immediate('acquire')[0].error)
        self.assertFalse(self.immediate('begin')[0].error)

    def transfer(self, operation, line, words=(), **kwargs):
        a = self.action(operation, line=line, words=words, **kwargs)
        out, raw, supply = self.edge(action=a)
        self.assertTrue(out['accepted'])
        self.assertTrue(raw['raw']['accepted'])
        self.assertFalse(supply['accepted'])
        self.assertIsNone(self.mux.response)
        self.edge()
        self.edge()
        response = self.consume()
        self.assertIs(response.action, a)
        return response

    def test_exact_parent_original_port_and_same_banks_only(self):
        self.assertIs(type(self.parent.raw), RawKvPort)
        self.assertTrue(self.parent.raw.scratch_enabled)
        self.assertIs(self.mux.parent, self.parent)
        self.assertIs(self.mux.banks, self.banks)
        self.assertIs(self.parent.raw.banks, self.banks)
        with self.assertRaises(ValueError):
            ScratchMux(self.parent, owner_id=17)
        with self.assertRaises(ValueError):
            ScratchMux(object(), owner_id=17)
        class Derived(ParentLoan):
            pass
        with self.assertRaises(ValueError):
            ScratchMux(Derived(enabled=True), owner_id=17)
        for enabled in (False, 1):
            p = ParentLoan(enabled=enabled)
            with self.assertRaises(ValueError):
                ScratchMux(p, owner_id=17)
        for identity in (0, True, 1 << 32, -1, '17'):
            p = ParentLoan(enabled=True)
            original = p.raw
            with self.assertRaises(ValueError):
                ScratchMux(p, owner_id=identity)
            self.assertIs(p.raw, original)

    def test_install_rejects_debt_lease_and_poison_without_replacement(self):
        for setup in ('lease', 'pending', 'response', 'raw_poison', 'parent_poison', 'owner_debt'):
            p = ParentLoan(enabled=True)
            original = p.raw
            if setup == 'lease':
                p.tick(acquire=17)
            elif setup in ('pending', 'response'):
                p.tick(acquire=17)
                p.tick(request=Request(Key(17, 1, 0, False)))
                if setup == 'response':
                    p.tick()
            elif setup == 'raw_poison':
                p.raw.poison = True
            elif setup == 'parent_poison':
                p.poison = True
            else:
                p.owner.state = 'busy'
            with self.assertRaises(ValueError, msg=setup):
                ScratchMux(p, owner_id=17)
            self.assertIs(p.raw, original)
            self.assertIs(type(p.raw), OriginalRawKvPort)

    def test_acquire_mask_and_virtual_release_leave_physical_lease(self):
        response, actual, supply = self.immediate('acquire')
        self.assertFalse(response.error)
        self.assertTrue(actual['raw']['acquired'])
        self.assertFalse(supply['acquired'])
        self.assertEqual(self.parent.raw.owner, 17)
        self.assertTrue(self.mux.leased)
        self.assertTrue(self.mux.idle)
        response, actual, supply = self.immediate('release')
        self.assertFalse(response.error)
        self.assertFalse(actual['raw']['released'])
        self.assertFalse(supply['released'])
        self.assertEqual(self.parent.raw.owner, 17)
        self.assertFalse(self.mux.leased)
        _, actual, supply = self.edge(controls={'release': 17}, closing=True)
        self.assertTrue(actual['raw']['released'])
        self.assertTrue(supply['released'])
        self.assertIsNone(self.parent.raw.owner)
        self.assertEqual(self.mux.counts['physical_acquires'], 1)

    def test_acquire_reuses_suppliers_existing_physical_lease(self):
        _, actual, supply = self.edge(controls={'acquire': 17}, state='acquire')
        self.assertTrue(actual['raw']['acquired'])
        self.assertTrue(supply['acquired'])
        response, actual, supply = self.immediate('acquire')
        self.assertFalse(response.error)
        self.assertFalse(actual['raw']['acquired'])
        self.assertFalse(supply['acquired'])
        self.assertEqual(self.mux.counts['physical_acquires'], 0)
        self.assertEqual(self.parent.raw.owner, 17)

    def test_all_96_lines_exact_bits_valid_only_on_matching_ack(self):
        self.begin()
        covered = set()
        for line in range(4096, 4192):
            words = tuple(((line << 16) ^ (i * 0x9e3779b9)) & 0xffffffff for i in range(16))
            a = self.action('write', line=line, words=words)
            out, actual, supply = self.edge(action=a)
            self.assertTrue(out['accepted'])
            self.assertTrue(actual['raw']['accepted'])
            self.assertFalse(supply['accepted'])
            self.assertNotIn(line, self.mux.valid)
            lo, hi, word = location(line, scratch_enabled=True)
            covered.update(((lo, word), (hi, word)))
            self.assertEqual(set(self.banks.writes), {lo, hi})
            self.assertEqual(self.banks.reads, {})
            self.edge(raw_ack_ready=False)
            self.assertNotIn(line, self.mux.valid)
            held = self.parent.raw.response
            for _ in range(2):
                self.edge(raw_ack_ready=False)
                self.assertIs(self.parent.raw.response, held)
                self.assertNotIn(line, self.mux.valid)
            _, actual, supply = self.edge()
            self.assertTrue(actual['raw']['acked'])
            self.assertFalse(supply['acked'])
            self.assertIn(line, self.mux.valid)
            self.assertFalse(self.consume().error)
            response = self.transfer('read', line)
            self.assertEqual(response.words, words)
            self.assertFalse(response.error)
        self.assertEqual(len(self.mux.valid), 96)
        self.assertEqual(len(covered), 192)
        self.assertEqual({word for _, word in covered}, set(range(512, 524)))
        self.assertEqual(self.mux.counts['writes'], 96)
        self.assertEqual(self.mux.counts['reads'], 96)
        self.assertEqual(self.mux.counts['raw_requests'], 192)
        self.assertEqual(self.mux.counts['raw_acks'], 192)

    def test_kv_payload_survives_scratch_and_kv_events_are_unmasked(self):
        _, _, supply = self.edge(controls={'acquire': 17}, state='acquire')
        self.assertTrue(supply['acquired'])
        for line in (0, 2048, 4095):
            key = Key(17, 99 + line, line, True)
            _, actual, supply = self.edge(controls={'request': Request(key, line + 0x123456)}, state='miss_wait', core_pending=True, ddr_pending=True)
            self.assertTrue(supply['accepted'])
            self.edge(state='fill_wait', core_pending=True)
            _, _, supply = self.edge(controls={'ack': key}, state='fill_wait', core_pending=True)
            self.assertTrue(supply['acked'])
        self.immediate('acquire')
        self.immediate('begin')
        self.transfer('write', 4191, (0xffffffff,) * 16)
        self.immediate('release')
        for line in (0, 2048, 4095):
            key = Key(17, 101 + line, line, False)
            _, _, supply = self.edge(controls={'request': Request(key)}, state='read_issue', core_pending=True)
            self.assertTrue(supply['accepted'])
            self.edge(state='read_wait', core_pending=True)
            self.assertEqual(self.parent.raw.response.data, line + 0x123456)
            _, _, supply = self.edge(controls={'ack': key}, state='ack_wait')
            self.assertTrue(supply['acked'])

    def test_scratch_waits_supply_idle_and_all_accepted_debts(self):
        a = self.action('acquire')
        for values in ({'state': 'lookup'}, {'core_pending': True}, {'ddr_pending': True}):
            out, _, _ = self.edge(action=a, **values)
            self.assertFalse(out['ready'])
            self.assertFalse(out['accepted'])
            self.assertEqual(self.mux.last_serial, 0)
        out, _, _ = self.edge(action=a)
        self.assertTrue(out['accepted'])
        repeated, _, _ = self.edge(action=a, response_ready=True)
        self.assertFalse(repeated['accepted'])
        self.assertTrue(repeated['response_fire'])

    def test_raw_debt_blocks_new_action_without_consuming_serial(self):
        self.edge(controls={'acquire': 17}, state='acquire')
        key = Key(17, 1, 0, False)
        self.edge(controls={'request': Request(key)}, state='read_issue', core_pending=True)
        a = self.action('acquire')
        self.assertFalse(self.edge(action=a)[0]['accepted'])
        self.assertFalse(self.edge(action=a)[0]['accepted'])
        self.assertEqual(self.mux.last_serial, 0)
        self.edge(controls={'ack': key}, state='ack_wait')
        self.assertTrue(self.edge(action=a)[0]['accepted'])

    def test_generation_rejects_stale_context_and_invalidates_all_lines(self):
        self.begin()
        self.transfer('write', 4096, tuple(range(16)))
        for a in (self.action('read', generation=2, line=4096),
                  self.action('read', query=1, line=4096),
                  self.action('read', kv_head=1, line=4096),
                  self.action('read', line=4097), self.action('begin')):
            with self.assertRaises(ValueError):
                self.edge(action=a)
        self.immediate('begin', generation=2, query=1, kv_head=1)
        self.assertEqual(self.mux.context, (2, 1, 1))
        self.assertEqual(self.mux.valid, set())
        with self.assertRaises(ValueError):
            self.edge(action=self.action('read', generation=2, query=1, kv_head=1, line=4096))
        self.immediate('release')
        self.immediate('acquire')
        with self.assertRaises(ValueError):
            self.edge(action=self.action('begin', generation=2))
        self.immediate('begin', generation=3)

    def test_canonical_actions_serials_controls_and_unknown_state(self):
        good = self.action('acquire')
        for bad in (replace(good, serial=True), replace(good, serial=0),
                    replace(good, generation=True), replace(good, line=False),
                    replace(good, query=128), replace(good, kv_head=2),
                    replace(good, operation='erase'), tuple(vars(good).values())):
            with self.assertRaises(ValueError):
                self.edge(action=bad)
            self.assertEqual(self.parent.owner.clock, 0)
        self.edge(action=good)
        self.consume()
        with self.assertRaises(ValueError):
            self.edge(action=replace(good, operation='begin'))
        for kw in ({'response_ready': 1}, {'abort': 1}, {'core_pending': 1},
                   {'ddr_pending': 1}, {'closing': 1}, {'raw_ack_ready': 1},
                   {'state': 'unknown'}, {'state': None},
                   {'controls': {'soft_reset': True}}, {'controls': {'abort': 1}},
                   {'controls': {'acquire': True}}, {'controls': {'release': 18}},
                   {'controls': {'ack': Key(17, True, 0, False)}},
                   {'controls': {'request': Request(Key(17, 1, 4096, True), 0)}}):
            before = self.parent.owner.clock
            with self.assertRaises(ValueError):
                self.edge(**kw)
            self.assertEqual(self.parent.owner.clock, before)

    def test_noncanonical_write_words_and_line_bounds(self):
        self.begin()
        good = self.action('write', line=4096, words=(0,) * 16)
        for a in (replace(good, words=(True,) * 16), replace(good, words=[0] * 16),
                  replace(good, words=(0,) * 15), replace(good, words=(-1,) * 16),
                  replace(good, line=4095), replace(good, line=4192),
                  replace(good, line=True)):
            with self.assertRaises(ValueError):
                self.edge(action=a)
        self.assertEqual(self.mux.counts['raw_requests'], 0)

    def test_foreign_ack_does_not_retire_write_or_publish_validity(self):
        self.begin()
        a = self.action('write', line=4096, words=tuple(range(16)))
        self.edge(action=a)
        self.edge(raw_ack_ready=False)
        key = self.mux.key
        for wrong in (replace(key, owner=18), replace(key, tag=key.tag + 1),
                      replace(key, line=4097), replace(key, write=False),
                      replace(key, tag=True)):
            out, actual, _ = self.edge(replace_ack=wrong)
            self.assertFalse(actual['raw']['acked'])
            self.assertIs(self.mux.active, a)
            self.assertIsNone(self.mux.response)
            self.assertNotIn(4096, self.mux.valid)
        self.edge()
        self.assertIn(4096, self.mux.valid)
        self.assertFalse(self.consume().error)
        self.assertEqual(self.mux.counts['raw_acks'], 1)

    def test_foreign_raw_response_retains_debt_until_matching_ack(self):
        self.begin()
        a = self.action('write', line=4096, words=(7,) * 16)
        self.edge(action=a)
        self.edge(raw_ack_ready=False)
        held = self.parent.raw.response
        foreign = Response(replace(held.key, tag=held.key.tag + 1), held.data)
        self.parent.raw.response = foreign
        _, actual, _ = self.edge()
        self.assertFalse(actual['raw']['acked'])
        self.assertIs(self.parent.raw.response, foreign)
        self.assertIs(self.mux.active, a)
        self.assertTrue(self.mux.reset_required)
        self.assertTrue(self.parent.raw.poison)
        self.assertEqual(self.mux.valid, set())
        self.parent.raw.response = held
        self.edge()
        self.assertTrue(self.consume().error)
        self.assertIsNone(self.mux.active)
        self.assertNotIn(4096, self.mux.valid)
        self.assertFalse(self.immediate('release')[0].error)
        self.assertEqual(self.parent.raw.owner, 17)

    def test_malformed_raw_responses_never_discharge_accepted_debt(self):
        self.begin()
        a = self.action('write', line=4191, words=(0xffffffff,) * 16)
        self.edge(action=a)
        self.edge(raw_ack_ready=False)
        held = self.parent.raw.response
        for malformed in (Response(replace(held.key, tag=True), held.data),
                          Response(held.key, True), Response(held.key, -1),
                          Response(held.key, 1 << 512)):
            self.parent.raw.response = malformed
            _, actual, _ = self.edge()
            self.assertFalse(actual['raw']['acked'])
            self.assertIs(self.parent.raw.response, malformed)
            self.assertIs(self.mux.active, a)
            self.assertIsNone(self.mux.response)
            self.assertEqual(self.mux.valid, set())
        self.parent.raw.response = held
        self.edge()
        self.assertTrue(self.consume().error)
        self.assertTrue(self.parent.raw.drained)

    def test_borrower_soft_reset_cannot_erase_accepted_scratch_debt(self):
        self.begin()
        a = self.action('write', line=4096, words=(0x12345678,) * 16)
        self.edge(action=a)
        merged = self.mux.prepare(controls={}, state='idle', core_pending=False,
                                 ddr_pending=False, raw_ack_ready=False)
        actual = self.parent.tick(**merged, soft_reset=True)
        self.mux.observe(actual)
        self.assertIs(self.mux.active, a)
        self.assertFalse(self.parent.raw.drained)
        self.assertTrue(self.parent.raw.poison)
        self.assertNotIn(4096, self.mux.valid)
        self.edge()
        self.assertTrue(self.consume().error)
        self.assertFalse(self.immediate('release')[0].error)
        self.edge(controls={'release': 17}, closing=True)
        self.assertIsNone(self.parent.raw.owner)
        self.assertTrue(self.mux.poison)
        self.assertTrue(self.parent.raw.poison)

    def test_abort_accepted_write_drains_then_virtual_release(self):
        self.begin()
        a = self.action('write', line=4096, words=(0x7fc12345,) * 16)
        self.edge(action=a)
        self.assertIsNotNone(self.parent.raw.pending)
        self.edge(abort=True, raw_ack_ready=False)
        for _ in range(3):
            out, _, _ = self.edge(raw_ack_ready=False, action=self.action('release'))
            self.assertFalse(out['accepted'])
            self.assertIs(self.mux.active, a)
            self.assertFalse(self.parent.raw.drained)
            self.assertEqual(self.mux.valid, set())
        self.edge()
        response = self.consume()
        self.assertTrue(response.error)
        self.assertIs(response.action, a)
        self.assertTrue(self.parent.raw.drained)
        self.assertFalse(self.immediate('release')[0].error)
        _, _, supply = self.edge(controls={'release': 17}, closing=True)
        self.assertTrue(supply['released'])
        self.assertTrue(self.mux.reset_required)
        self.assertTrue(self.parent.raw.poison)

    def test_abort_read_and_held_response_preserve_exact_payload(self):
        self.begin()
        words = (0x7fc12345, 0x80000000, 0xffffffff) + (0x3f800000,) * 13
        self.transfer('write', 4096, words)
        a = self.action('read', line=4096)
        self.edge(action=a)
        self.edge()
        self.edge()
        response = self.mux.response
        self.assertEqual(response.words, words)
        for _ in range(4):
            out, _, _ = self.edge(abort=True, response_ready=False)
            self.assertIs(out['response'], response)
            self.assertIs(self.mux.response, response)
            self.assertEqual(response.words, words)
        self.assertIs(self.consume(), response)
        self.assertTrue(self.mux.poison)
        self.assertEqual(self.mux.valid, set())

    def test_abort_does_not_admit_new_nonrelease_action(self):
        for operation in ('acquire', 'begin', 'write'):
            a = self.action(operation, line=4096 if operation == 'write' else 0,
                            words=(0,) * 16 if operation == 'write' else ())
            out, _, _ = self.edge(action=a, abort=True)
            self.assertFalse(out['accepted'])
            self.assertFalse(out['ready'])
            self.assertEqual(self.mux.last_serial, 0)
            self.assertIsNone(self.parent.raw.owner)

    def test_no_supplier_action_can_overlap_active_or_held_response(self):
        self.begin()
        self.edge(action=self.action('write', line=4096, words=(0,) * 16))
        for controls in ({'acquire': 17}, {'release': 17},
                         {'request': Request(Key(17, 1, 0, False))},
                         {'ack': Key(17, 1, 0, False)}):
            with self.assertRaises(ValueError):
                self.edge(controls=controls)
        self.edge()
        self.edge()
        with self.assertRaises(ValueError):
            self.edge(controls={'request': Request(Key(17, 1, 0, False))})
        self.consume()
        with self.assertRaises(ValueError):
            self.edge(controls={'release': 17}, closing=True)

    def test_prepare_observe_pair_never_ticks_parent_itself(self):
        before = self.parent.owner.clock
        with patch.object(self.parent, 'tick', wraps=self.parent.tick) as tick:
            merged = self.mux.prepare(controls={}, state='idle', core_pending=False,
                ddr_pending=False, action=self.action('acquire'))
            self.assertEqual(tick.call_count, 0)
            with self.assertRaises(ValueError):
                self.mux.prepare(controls={}, state='idle', core_pending=False, ddr_pending=False)
            with self.assertRaises(ValueError):
                self.mux.observe({'raw': {}})
            actual = self.parent.tick(**merged)
            self.mux.observe(actual)
            self.assertEqual(tick.call_count, 1)
            self.assertEqual(self.parent.owner.clock, before + 1)
            with self.assertRaises(ValueError):
                self.mux.observe(actual)
            with self.assertRaises(ValueError):
                self.mux.supply_raw(dict(actual))
            self.assertFalse(self.mux.supply_raw(actual)['acquired'])

    def test_mux_source_has_no_parent_tick_or_payload_bank_allocation(self):
        source = ast.parse(Path(__file__).with_name('mux.py').read_text())
        calls = [node for node in ast.walk(source) if isinstance(node, ast.Call)]
        self.assertFalse(any(isinstance(node.func, ast.Attribute) and node.func.attr == 'tick' for node in calls))
        self.assertFalse(any(isinstance(node.func, ast.Name) and node.func.id in ('ParentLoan', 'Banks') for node in calls))
        self.assertFalse(any(isinstance(node.func, ast.Name) and node.func.id in ('bytearray', 'bytes', 'list') for node in calls))


if __name__ == '__main__':
    unittest.main()
