"""Cold structural/integer checks only; never invoke native or oracle kernels."""
import unittest
from dataclasses import replace
from . import screen as s


class ScreenTests(unittest.TestCase):
    def test_sources_and_fixed_resources(self):
        self.assertEqual(s.source_check(), 10)
        pins = s.json.loads((s.HERE / 'sources.json').read_text())
        self.assertIn('candidates/qwen2_official_platform_fullblock/runner.py', pins)
        self.assertNotIn('candidates/qwen2_fullblock_recovery/runner.py', pins)
        r = s.screen()
        self.assertEqual((r['physical_macs'], r['physical_contexts']), (4096, 5))
        self.assertEqual(r['accumulator_bytes'], 81920)
        self.assertEqual(r['additional_mac_lanes'], 0)
        self.assertEqual(r['additional_accumulator_words'], 0)
        self.assertEqual(r['borrowed_shared_fp32_add_lanes'], 16)

    def test_ordered_tree_matches_original_offset_loops(self):
        # Symbolic nodes preserve both children: reassociation/swap changes equality.
        original = [[r * 8 + lane for lane in range(8)] for r in range(8)]
        for offset in (4, 2, 1):
            for r in range(offset):
                for lane in range(8):
                    original[r][lane] = (original[r][lane], original[r + offset][lane])
        for offset in (4, 2, 1):
            for lane in range(offset):
                original[0][lane] = (original[0][lane], original[0][lane + offset])
        self.assertEqual(s.full_tree(), original[0][0])
        self.assertEqual(len(s.postorder(s.full_tree())), 63)
        self.assertEqual(s.leaves(s.full_tree())[:8], [0, 32, 16, 48, 8, 40, 24, 56])
        self.assertEqual(sorted(s.leaves(s.full_tree())), list(range(64)))

    def test_partial_updates_have_exact_k_coverage_and_contexts(self):
        schedule = s.schedule()
        partials = [x for x in schedule['trace'] if x['op'] == 'partial']
        self.assertEqual(len(partials), 64)
        self.assertEqual(sorted(k for x in partials for k in x['k']), list(range(1536)))
        self.assertTrue(all(x['k'] == list(range(x['p'], 1536, 64)) for x in partials))
        self.assertTrue(all(0 <= x['context'] < 5 for x in partials))
        self.assertEqual(sum(x['finish'] for x in partials), 13)
        # t-major round robin of real contexts; explicit tail recurrence gap.
        for count in (1, 2, 3, 4, 5):
            last = {}
            for t in range(24):
                for c in range(count):
                    tick = t * max(count, 5) + c
                    if c in last:
                        self.assertGreaterEqual(tick - last[c], 5)
                    last[c] = tick

    def test_slot_lifetimes_and_inplace_order(self):
        for size in range(1, 6):
            schedule = s.schedule(size)
            self.assertLessEqual(schedule['peak_partial_slots'], 10)
            slot_nodes = {}
            for event in schedule['trace']:
                if event['op'] == 'partial':
                    self.assertNotIn(event['slot'], slot_nodes)
                    slot_nodes[event['slot']] = event['p']
                elif event['op'] == 'add':
                    lhs, rhs, dst = (event[k] for k in ('lhs_slot', 'rhs_slot', 'dst_slot'))
                    self.assertNotEqual(lhs, rhs)
                    self.assertEqual(dst, lhs)
                    self.assertEqual(slot_nodes[lhs], event['left'])
                    self.assertEqual(slot_nodes[rhs], event['right'])
                    self.assertTrue(event['release_rhs_after_last_write_ack'])
                    self.assertEqual(event['packets'], 256)
                    # This test accepts the declared ACK fence, never predicts
                    # elapsed clocks or pretends to exercise an RTL write port.
                    slot_nodes[dst] = (slot_nodes[lhs], slot_nodes.pop(rhs))
            self.assertEqual(slot_nodes, {schedule['root_slot']: s.full_tree()})
        self.assertEqual(s.schedule()['peak_partial_slots'], 10)

    def test_banked_addresses_disjoint_and_ports_serialized(self):
        addresses = set()
        for slot in range(11):
            for packet in range(256):
                pair = [s.partial_address(slot, packet, half) for half in (0, 1)]
                self.assertNotEqual(pair[0][0], pair[1][0])
                for address in pair:
                    self.assertNotIn(address, addresses)
                    self.assertTrue(0 <= address[0] < 16 and 768 <= address[1] < 1376)
                    addresses.add(address)
        self.assertEqual(len(addresses), 11 * 512)
        # LHS and RHS have SAME banks at a given packet, hence need distinct
        # read phases. No two-read-port or zero-cost crossbar assumption.
        self.assertEqual([s.partial_address(0, 31, h)[0] for h in (0, 1)],
                         [s.partial_address(1, 31, h)[0] for h in (0, 1)])

    def test_complete_live_set_not_free_a_memory(self):
        r = s.screen()
        self.assertEqual(r['peak_partial_bytes'], 163840)
        self.assertEqual(r['a_total_reserved_bytes'], 573440)
        self.assertEqual(r['a_spare_bytes'], 131072)
        self.assertEqual(r['b_group_payload_bytes'], 61440)
        self.assertLessEqual(r['a_total_reserved_bytes'], r['a_capacity_bytes'])
        self.assertLessEqual(r['b_group_payload_bytes'], r['b_capacity_bytes'])
        self.assertGreater(2 * r['b_group_payload_bytes'], r['b_capacity_bytes'])
        self.assertFalse(r['b_prefetch_double_buffer_credited'])

    def test_qk_and_fullblock_accounting_are_distinct(self):
        r = s.screen()
        self.assertEqual(r['output_tiles'], 56)
        self.assertEqual(r['useful_qk_macs'], 352321536)
        self.assertEqual(r['physical_issue_slots'], r['useful_qk_macs'])
        self.assertEqual(r['partial_snapshot_bytes'], 58720256)
        self.assertEqual(r['partial_snapshot_selected_bank_writes'], 1835008)
        self.assertEqual(r['tree_selected_bank_writes'], 1806336)
        self.assertEqual(r['tree_read_bank_phases'], 1806336)
        self.assertEqual(r['weight_read_bytes'], 44040192)
        self.assertEqual(r['full_block_useful_macs'], 6014828544)
        self.assertGreater(r['full_block_useful_macs'], r['useful_qk_macs'])
        self.assertLess(r['conditional_projection_mac_ratio'], r['issue_geometry_fill'])
        self.assertEqual(r['conditional_serial_projection_total'],
                         sum(r['conditional_serial_projection_cost_units'].values()))
        self.assertTrue(all(x > 0 for x in r['conditional_serial_projection_cost_units'].values()))

    def test_hardware_and_unknown_conversion_fields_remain_null(self):
        r = s.screen()
        for key in ('hardware_cycles', 'measured_utilization', 'cycle_prediction',
                    'full_block_cost', 'conversion_service_cost'):
            self.assertIsNone(r[key])
        for key in ('hardware_implemented', 'rtl_executed', 'numeric_executed'):
            self.assertFalse(r[key])
        for key in ('unchanged_bias', 'unchanged_rope'):
            self.assertIsNone(r[key]['conversion_count'])
            self.assertTrue(r[key]['follow_existing_owner'])

    def test_cost_monotonicity_and_reject_invented_contexts(self):
        base = s.screen()['conditional_serial_projection_total']
        for field in s.asdict(s.Costs()):
            value = getattr(s.Costs(), field)
            self.assertGreater(s.screen(replace(s.Costs(), **{field: value + 1}))[
                'conditional_serial_projection_total'], base)
            with self.assertRaises(ValueError):
                s.screen(replace(s.Costs(), **{field: 0}))
        for contexts in (0, 6, 64, True):
            with self.assertRaises(ValueError):
                s.schedule(contexts)
        with self.assertRaises(ValueError):
            s.screen(replace(s.Costs(), recurrence=4))


if __name__ == '__main__':
    unittest.main()
