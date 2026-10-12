"""Small byte-level controls; no opaque successful owner terminal injection."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import model as m
from candidates.qwen2_resident_matrix.ffn_public.fixture import make_ffn4_fixture, tensor_base_record, shape4_record, stride3_record


class RecordTests(unittest.TestCase):
    def test_physical_metadata_map_rejects_duplicate_overlap_and_bad_extent(self):
        bad = [((0x1000, bytes(64)), (0x1000, bytes(64))),
               ((0x1000, bytes(128)), (0x1040, bytes(64))),
               ((0x1001, bytes(64)),), ((0x1000, bytes(16)),),
               ((0x1000, b''),), ((m.LIMIT - 64, bytes(128)),)]
        for mappings in bad:
            with self.subTest(extents=[(a, len(d)) for a, d in mappings]):
                with self.assertRaises(ValueError):
                    m.MetadataMemory(mappings)

    def test_all_four_slots_and_fresh_reads(self):
        table = m.Table(0x1000, 0x1080, 5)
        words = (11, 22, 33, 44, 55)
        memory = m.MetadataMemory(((table.base, b''.join(w.to_bytes(16, 'little') for w in words).ljust(128, b'\0')),))
        port = m.RecordPort(memory)
        self.assertEqual([port.read(table, i, i + 10, purpose='test') for i in range(5)], list(words))
        self.assertEqual(memory.reads, [0x1000] * 4 + [0x1040])
        memory.write_word(table, 0, 999)
        self.assertEqual(port.read(table, 0, 19, purpose='test'), 999)
        self.assertEqual([r['serial'] for r in port.trace], list(range(1, 7)))

    def test_record_admission_no_memory_or_poison(self):
        bad = [(m.Table(0x1001, 0x1080, 4), 0), (m.Table(0x1000, 0x1040, 5), 0),
               (m.Table(0x1000, 0x1040, 0), 0), (m.Table(0x1000, 0x1040, 4), m.NULL),
               (m.Table(0x1000, 0x1040, 4), 4), (m.Table(m.LIMIT - 64, m.LIMIT + 64, 4), 0)]
        for table, index in bad:
            with self.subTest(table=table, index=index):
                port = m.RecordPort(m.MetadataMemory())
                with self.assertRaises(m.Rejected) as caught:
                    port.read(table, index, 1, purpose='test')
                self.assertEqual(caught.exception.status, 'Bounds')
                self.assertFalse(port.machine.poison)
                self.assertEqual(port.memory.reads, [])

    def test_backpressure_busy_and_held_terminal(self):
        r = m.RecordReader()
        q = m.RecordRequest(m.Table(0x1000, 0x1040, 4), 2, 91)
        self.assertTrue(r.tick(request=q)['request_fire'])
        held = r.ports()['memory']
        for _ in range(3):
            self.assertFalse(r.tick(request=q)['request_fire'])
            self.assertEqual(r.ports()['memory'], held)
        self.assertTrue(r.tick(memory_ready=True)['memory_fire'])
        self.assertFalse(r.tick()['response_fire'])
        data = bytes(range(64))
        self.assertTrue(r.tick(response=m.MemoryResponse(data, held.tag))['response_fire'])
        result = r.ports()['result']
        self.assertEqual(result.data, int.from_bytes(data[32:48], 'little'))
        self.assertEqual(result.request_tag, 91)
        for _ in range(3):
            r.tick()
            self.assertEqual(r.ports()['result'], result)
        self.assertTrue(r.tick(result_ready=True)['result_fire'])
        self.assertTrue(r.ports()['request_ready'])

    def test_tag_error_priority_quarantine_reset_and_serial_overflow(self):
        for tag, error, status in ((2, False, 'Protocol'), (1, True, 'Memory'), (2, True, 'Protocol')):
            r = m.RecordReader()
            q = m.RecordRequest(m.Table(0x1000, 0x1040, 1), 0, 1)
            r.tick(request=q); r.tick(memory_ready=True)
            r.tick(response=m.MemoryResponse(bytes(64), tag, error))
            self.assertEqual(r.ports()['result'].status, status)
            r.tick(result_ready=True)
            self.assertEqual(r.state, 'locked')
            self.assertFalse(r.tick(request=q)['request_fire'])
            r.tick(reset=True)
            self.assertTrue(r.ports()['request_ready'])
            self.assertFalse(r.tick(response=m.MemoryResponse(bytes(64), 1))['response_fire'])
            r.serial = m.U64
            r.tick(request=q)
            self.assertEqual(r.result.status, 'Protocol')
            self.assertIsNone(r.ports()['memory'])


class TypedTests(unittest.TestCase):
    def setUp(self):
        self.fx = make_ffn4_fixture()
        self.f = m.PublicFrontend(self.fx.memory, self.fx.config)

    def mutate(self, index, function):
        self.fx.memory.write_word(self.fx.config.descriptor, index, function(self.fx.records[index].pack()))

    def rejected(self, root, status, write=False):
        with self.assertRaises(m.Rejected) as caught:
            self.f.reader.read(root, write)
        self.assertEqual(caught.exception.status, status)

    def test_actual_three_record_prefix_and_one_padding(self):
        for root, spec in ((self.fx.roots[0][0], 'n1'), (self.fx.roots[0][1], 'gate_weight')):
            t = self.f.reader.read(root)
            a, dims, dtype = self.fx.specs[spec]
            self.assertEqual((t.address, t.dims, t.dtype, t.prefix_indices), (a, dims, dtype, (root, root + 1, root + 2)))
        self.assertEqual([r['request_tag'] for r in self.f.port.trace], [0, 1, 2, 0, 1, 2])

    def test_prefix_index_loop_reads_then_fails(self):
        self.mutate(0, lambda w: (w & ~(m.NULL << 32)))
        self.rejected(0, 'Malformed')
        self.assertEqual([r['index'] for r in self.f.port.trace], [0, 0])

    def test_prefix_null_next_is_record_bounds(self):
        self.mutate(0, lambda w: w | m.NULL << 32)
        self.rejected(0, 'Bounds')
        self.assertEqual(len(self.fx.memory.reads), 1)

    def test_wrong_dtype_rank_layout_and_header(self):
        for bit, mask, expected in ((108, 0xf, 'Unsupported'), (116, 0xf, 'Unsupported'),
                                    (112, 0, 'Unsupported'), (104, 0, 'Unsupported'), (8, 0, 'Malformed')):
            with self.subTest(bit=bit):
                self.setUp()
                self.mutate(0, lambda w: (w & ~(mask << bit)) | ((1 if mask == 0 else 0) << bit))
                self.rejected(0, expected)
                self.assertEqual(len(self.fx.memory.reads), 1)

    def test_dims_padding_zero_stride_bytes_negative_and_permission(self):
        mutations = [(1, lambda w: w & ~(((1 << 18) - 1) << 92), 'Bounds'),
                     (2, lambda w: (w & ~(m.NULL << 56)) | (1536 * 4 << 56), 'Unsupported'),
                     (2, lambda w: w | (1 << 79), 'Unsupported'),
                     (0, lambda w: w | (1 << 56), 'Bounds')]
        for index, fn, status in mutations:
            with self.subTest(index=index, status=status):
                self.setUp(); self.mutate(index, fn); self.rejected(0, status)
        self.setUp(); self.rejected(0, 'Permission', True)

    def test_result_tag_and_memory_faults_never_decode(self):
        for step in range(3):
            self.setUp()
            self.f.port.result_filter = lambda req, result: replace(result, request_tag=9) if req.request_tag == step else result
            self.rejected(0, 'Protocol')
            self.assertEqual(len(self.f.port.trace), step + 1)
        self.setUp()
        self.f.port.response_filter = lambda req, response: replace(response, error=True)
        self.rejected(0, 'Memory')
        self.assertTrue(self.f.port.machine.poison)

    def test_policy_is_fetched_only_after_all_three_tensor_prefixes(self):
        c = self.f.fetch_command(0)
        tensors = tuple(self.f.reader.read(root, i == 2) for i, root in enumerate(c.roots))
        p = self.f.read_policy(c, tensors)
        self.assertEqual((p.kind, p.m, p.n, p.k, p.valid), ('matrix', 16, 8960, 1536, True))
        self.assertEqual([e['purpose'] for e in self.f.port.trace], ['command'] + ['tensor_prefix'] * 9 + ['policy'] * 2)

    def test_policy_prefix_revisit_and_reserved_recipe(self):
        c = self.f.fetch_command(0)
        tensors = tuple(self.f.reader.read(root, i == 2) for i, root in enumerate(c.roots))
        t = replace(tensors[0], tail=tensors[1].prefix_indices[1])
        with self.assertRaises(m.Rejected) as caught:
            self.f.read_policy(c, (t,) + tensors[1:])
        self.assertEqual(caught.exception.status, 'Malformed')
        self.mutate(3, lambda w: w | 1 << 112)
        self.assertFalse(self.f.read_policy(c, tensors).valid)

    def test_wrong_record_kind_and_revisit_at_each_later_prefix(self):
        for index in (0, 1, 2):
            self.setUp()
            self.mutate(index, lambda w: (w & ~255) | 0x12)
            self.rejected(0, 'Unsupported')
            self.assertEqual(len(self.f.port.trace), index + 1)
        self.setUp()
        self.mutate(1, lambda w: (w & ~(m.NULL << 32)) | (1 << 32))
        self.rejected(0, 'Malformed')
        self.assertEqual([e['index'] for e in self.f.port.trace], [0, 1, 1])

    def test_dim_product_overflow_and_high_address_padding(self):
        self.mutate(1, lambda w: (w & ((1 << 56) - 1)) | ((1 << 17) | (1 << 17) << 18 | 1 << 36 | 1 << 54) << 56)
        self.rejected(0, 'Bounds')
        self.setUp()
        high = tensor_base_record(m.LIMIT - 64, dtype=7, rank=2, next_index=1)
        self.fx.memory.write_word(self.fx.config.descriptor, 0, high.pack())
        self.rejected(0, 'Bounds')

    def test_policy_loop_tail_and_sfu_reserved_fields(self):
        c = self.f.fetch_command(0)
        tensors = tuple(self.f.reader.read(root, i == 2) for i, root in enumerate(c.roots))
        self.mutate(3, lambda w: (w & ~(m.NULL << 32)) | (3 << 32))
        with self.assertRaises(m.Rejected) as caught:
            self.f.read_policy(c, tensors)
        self.assertEqual(caught.exception.status, 'Malformed')
        self.setUp()
        c = self.f.fetch_command(2)
        tensors = tuple(self.f.reader.read(root, i == 2) for i, root in enumerate(c.roots))
        self.assertTrue(self.f.read_policy(c, tensors).valid)
        index = tensors[0].tail
        self.mutate(index, lambda w: w | (1 << 104))
        self.assertFalse(self.f.read_policy(c, tensors).valid)
        self.mutate(index, lambda w: w & ~(m.NULL << 32))
        self.assertFalse(self.f.read_policy(c, tensors).valid)


class HostTests(unittest.TestCase):
    def setup_host(self, fx=None):
        self.fx = fx or make_ffn4_fixture()
        self.frontend = m.PublicFrontend(self.fx.memory, self.fx.config)
        self.host = m.group.HostControl(enabled=True)
        self.assertTrue(self.frontend.launch(self.host))

    def reach_boundary(self):
        for _ in range(100):
            if self.host.state in ('issue', 'complete', 'finish'):
                return
            self.host.tick(request_ready=False)
        self.fail('frontend did not reach bounded boundary')

    def test_ffn4_scan_real_fetch_order_no_ports_io_no_success(self):
        self.setup_host()
        self.assertEqual(self.fx.memory.reads, [])
        for _ in range(5):
            self.host.ports()
        self.assertEqual(self.fx.memory.reads, [])
        self.reach_boundary()
        self.assertEqual(self.host.state, 'issue')
        self.assertEqual(self.frontend.command_reads, [0, 1, 2, 0, 1, 2, 3])
        self.assertEqual(len(self.frontend.port.trace), 75)
        self.assertEqual(len(self.host.scanner.trace), 12)
        self.assertEqual(self.host.group.gate.tag, 7 << 16)
        self.assertEqual(self.host.group.identity, (7 << 16) + 1)
        self.assertEqual(self.host.completed, 0)
        self.assertEqual(self.host.published, [])
        self.assertEqual(self.host.events, {0})
        self.assertTrue(self.host.group.valid())
        trace_length = len(self.frontend.port.trace)
        for _ in range(5):
            self.host.tick(request_ready=False)
        self.assertEqual(len(self.frontend.port.trace), trace_length)

    def test_bad_primary_root_is_malformed_before_tensor_read(self):
        self.setup_host()
        w = self.fx.commands[0].pack() | m.NULL << 56
        self.fx.memory.write_word(self.fx.config.command, 0, w)
        self.reach_boundary()
        self.assertEqual(self.host.status, 'Malformed')
        self.assertEqual(len(self.frontend.port.trace), 1)
        self.assertEqual(self.host.jobs, 0)

    def test_descriptor_mutation_between_launch_and_fetch_is_visible(self):
        self.setup_host()
        self.fx.memory.write_word(self.fx.config.descriptor, 0, self.fx.records[0].pack() | 1 << 8)
        self.reach_boundary()
        self.assertEqual(self.host.status, 'Malformed')
        self.assertEqual(self.host.jobs, 0)

    def test_group_word_mutation_during_scan_fails_before_issue(self):
        self.setup_host()
        self.host.tick(request_ready=False)
        self.assertEqual(self.host.state, 'scan')
        self.fx.memory.write_word(self.fx.config.command, 0, self.fx.commands[0].pack() | 1 << 11)
        self.reach_boundary()
        self.assertEqual(self.host.status, 'Protocol')
        self.assertEqual(self.host.jobs, 0)
        self.assertEqual(self.host.virtual, [])

    def test_future_unknown_opcode_roots_are_scanned(self):
        self.setup_host()
        word = (self.fx.commands[3].pack() & ~255) | 0xee
        self.fx.memory.write_word(self.fx.config.command, 3, word)
        self.reach_boundary()
        self.assertEqual(self.host.state, 'issue')
        self.assertEqual([x for x in self.host.scanner.trace if x[0] == 3],
                         [(3, i, root) for i, root in enumerate(self.fx.roots[3])])

    def test_future_unknown_opcode_virtual_alias_is_rejected(self):
        self.setup_host()
        c = self.fx.commands[3]
        word = ((c.pack() & ~(255 | (m.NULL << 56))) | 0xee | (self.fx.roots[0][2] << 56))
        self.fx.memory.write_word(self.fx.config.command, 3, word)
        self.reach_boundary()
        self.assertEqual(self.host.status, 'Dependency')
        self.assertEqual(self.host.jobs, 0)
        self.assertEqual(self.host.virtual, [])

    def test_launch_table_alignment_overlap_ro_permissions_and_padding(self):
        fx = make_ffn4_fixture()
        configs = [replace(fx.config, command=replace(fx.config.command, base=fx.config.command.base + 1)),
                   replace(fx.config, descriptor=replace(fx.config.descriptor, base=fx.config.command.base)),
                   replace(fx.config, descriptor=replace(fx.config.descriptor, limit=fx.config.descriptor.limit - 64)),
                   replace(fx.config, regions=fx.config.regions[:2] + (replace(fx.config.regions[2], write=True),) + fx.config.regions[3:])]
        for config in configs:
            self.setup_host(replace(fx, config=config))
            self.assertEqual(self.host.state, 'finish')
            self.assertEqual(self.host.status, 'Bounds')
            self.assertFalse(self.host.poison)
            self.assertEqual(self.fx.memory.reads, [])

    def test_host_quarantine_on_transport_fault(self):
        self.setup_host()
        self.frontend.port.response_filter = lambda req, response: replace(response, tag=response.tag + 1)
        self.reach_boundary()
        self.assertEqual(self.host.status, 'Protocol')
        self.assertTrue(self.host.poison)
        self.assertFalse(self.frontend.launch(self.host))
        self.assertEqual(self.host.jobs, 0)

    def test_global_physical_metadata_spans_and_legal_relocation(self):
        original = make_ffn4_fixture()
        moved = make_ffn4_fixture(relocate=0x100000000)
        self.setup_host(moved)
        self.reach_boundary()
        self.assertEqual(self.host.state, 'issue')
        self.assertEqual(self.host.group.gate.a, original.specs['n1'][0] + 0x100000000)
        self.assertEqual(len(moved.validate_spans()), 11)
        aliased = replace(original, config=replace(original.config,
            command=replace(original.config.command, base=original.specs['n1'][0], limit=original.specs['n1'][0] + 64)))
        with self.assertRaisesRegex(ValueError, 'overlap'):
            aliased.validate_spans()

    def test_launch_config_regions_are_snapshotted(self):
        fx = make_ffn4_fixture()
        regions = list(fx.config.regions)
        self.setup_host(replace(fx, config=replace(fx.config, regions=regions)))
        regions[0] = replace(regions[0], read=False)
        self.reach_boundary()
        self.assertEqual(self.host.state, 'issue')
        self.assertTrue(self.frontend.config.regions[0].read)
        self.assertFalse(self.frontend.launch(self.host))

    def test_event_error_stops_after_only_actual_command_fetch(self):
        self.setup_host()
        w = self.fx.commands[0].pack() | (17 << 24)
        self.fx.memory.write_word(self.fx.config.command, 0, w)
        self.reach_boundary()
        self.assertEqual(self.host.status, 'Dependency')
        self.assertEqual([e['purpose'] for e in self.frontend.port.trace], ['command'])

    def test_gate_permissions_and_up_alias_fail_before_next_command_fetch(self):
        fx = make_ffn4_fixture()
        regions = fx.config.regions
        self.setup_host(replace(fx, config=replace(fx.config,
            regions=regions[:1] + (replace(regions[1], read=False),) + regions[2:])))
        self.reach_boundary()
        self.assertEqual(self.host.status, 'Permission')
        self.assertEqual(self.frontend.command_reads, [0])
        self.setup_host()
        root = self.fx.roots[1][1]
        record = tensor_base_record(self.fx.specs['gate_weight'][0], dtype=5, rank=2, next_index=root + 1)
        self.fx.memory.write_word(self.fx.config.descriptor, root, record.pack())
        self.reach_boundary()
        self.assertEqual(self.host.status, 'Permission')
        self.assertEqual(self.frontend.command_reads, [0, 1])

    def test_policy_recipe_and_non_a_tail_fail_before_issue(self):
        fx = make_ffn4_fixture()
        mutations = [(3, lambda w: w | (1 << 115)), (4, lambda w: w ^ (1 << 82)),
                     (fx.roots[0][1] + 2, lambda w: w & ~(m.NULL << 32))]
        for index, change in mutations:
            self.setup_host()
            self.fx.memory.write_word(self.fx.config.descriptor, index, change(self.fx.records[index].pack()))
            self.reach_boundary()
            self.assertEqual(self.host.status, 'Unsupported')
            self.assertEqual(self.host.jobs, 0)
            self.assertEqual(self.frontend.command_reads, [0])

    def test_softmax_null_b_scan_skip_and_command_hold_between_roots(self):
        self.setup_host()
        c = self.fx.commands[3]
        word = (c.pack() & ~(255 | (7 << 8) | (m.NULL << 80))) | 0x33 | (3 << 8) | (m.NULL << 80)
        self.fx.memory.write_word(self.fx.config.command, 3, word)
        self.host.tick(request_ready=False)
        self.host.tick(request_ready=False)
        before = list(self.frontend.command_reads)
        # Source scanCmd is latched for all roots of this command. Changing
        # memory after slot 0 cannot cause a speculative fetch for slots 1/2.
        self.fx.memory.write_word(self.fx.config.command, 0, self.fx.commands[0].pack() | (1 << 11))
        self.host.tick(request_ready=False)
        self.host.tick(request_ready=False)
        self.assertEqual(self.frontend.command_reads, before)
        self.reach_boundary()
        self.assertEqual(self.host.state, 'issue')
        self.assertEqual([x[1] for x in self.host.scanner.trace if x[0] == 3], [0, 2])
        self.assertEqual(len(self.frontend.port.trace), 72)

    def test_virtual_padding_subrange_alias_from_distinct_prefix(self):
        self.setup_host()
        root = self.fx.roots[3][0]
        # This distinct tiny tensor is only four payload bytes, with a full
        # 64-byte padded extent inside the virtual Gate allocation.
        records = (tensor_base_record(self.fx.specs['gate'][0] + 64, dtype=7, rank=2, next_index=root + 1),
                   shape4_record((1, 1, 1, 1), next_index=root + 2),
                   stride3_record((1, 1, 1)))
        for i, record in enumerate(records):
            self.fx.memory.write_word(self.fx.config.descriptor, root + i, record.pack())
        self.reach_boundary()
        self.assertEqual(self.host.status, 'Dependency')
        self.assertEqual(self.host.jobs, 0)


if __name__ == '__main__':
    unittest.main()
