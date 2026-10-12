"""Public21 metadata/physical layout checks, not numeric or RTL evidence."""
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import fixture as f
from candidates.qwen2_resident_matrix.ffn_public import model as m
from heteronpu.command import Opcode
from heteronpu.descriptor_chain import validate_descriptor_chain


def original_packer(filename):
    path = ROOT / 'chisel/continuous_prefill/scripts' / filename
    spec = importlib.util.spec_from_file_location('_fixture_test_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FullBlockFixtureTests(unittest.TestCase):
    def test_original_command_bytes_and_only_seven_dense_dtype_edits(self):
        packer = original_packer('pack_owner_block_fixture.py')
        for rows in (16, 128):
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as directory:
                fx = f.make_qwen2_21_fixture(rows, max_tokens=1024)
                source = Path(directory) / 'original'
                original = packer.pack(dict(H=1536, F=8960, HEADS=12, KVHEADS=2,
                                           HD=128, MAX_TOKENS=1024), rows, source)
                cb = (source / 'host_commands.bin').read_bytes()
                db = (source / 'host_descriptors.bin').read_bytes()
                self.assertEqual(bytes(fx.memory.mappings[fx.config.command.base]), cb)
                self.assertEqual(fx.manifest['schedule'], original['schedule'])
                self.assertEqual(fx.config.command.count, 21)
                self.assertEqual(fx.config.descriptor.count, 215)
                self.assertEqual(fx.roots, tuple(tuple(op['roots']) for op in original['schedule']))
                changed = set()
                for i, record in enumerate(fx.records):
                    old = int.from_bytes(db[i * 16:(i + 1) * 16], 'little')
                    if old != record.pack():
                        changed.add(i)
                        self.assertEqual(old ^ record.pack(), 2 << 108)
                expected = {c.src1 for c in fx.commands if c.opcode == Opcode.MATRIX_GEMM}
                self.assertEqual(changed, expected)
                self.assertEqual(len(changed), 7)
                converted = original_packer('pack_owner_bf16_weights.py')
                converted.convert(source, Path(directory) / 'converted')
                self.assertEqual(bytes(fx.memory.mappings[fx.config.descriptor.base]),
                                 (Path(directory) / 'converted/host_descriptors.bin').read_bytes())
                for name, tensor in original['tensors'].items():
                    self.assertEqual(fx.specs[name][:2], (tensor['address'], tuple(tensor['dims'])))

    def test_schedule_keeps_null_softmax_and_full_attention_ffn_suffix(self):
        fx = f.make_qwen2_21_fixture()
        self.assertEqual(fx.commands[11].opcode, Opcode.SFU_SOFTMAX)
        self.assertEqual(fx.commands[11].src1, m.NULL)
        self.assertEqual(fx.manifest['attention_fusion'], [10, 11, 12])
        self.assertEqual([c.opcode for c in fx.commands[10:13]],
                         [Opcode.MATRIX_QK, Opcode.SFU_SOFTMAX, Opcode.MATRIX_PV])
        self.assertEqual([c.opcode for c in fx.commands[16:]],
                         [Opcode.MATRIX_GEMM, Opcode.MATRIX_GEMM, Opcode.SFU_ACTIVATION,
                          Opcode.MATRIX_GEMM, Opcode.SFU_VECTOR])
        self.assertEqual([op['dst'] for op in fx.manifest['schedule'][16:]],
                         ['gate', 'up', 'act', 'down', 'y'])
        self.assertEqual([(c.event_wait, c.event_signal) for c in fx.commands],
                         [(pc, pc + 1) for pc in range(21)])
        self.assertEqual(fx.manifest['schedule'][9]['outputs'], ['cache_k', 'cache_v'])
        self.assertEqual(fx.manifest['schedule'][10]['outputs'], [])
        self.assertEqual(fx.manifest['schedule'][11]['outputs'], [])

    def test_shapes_strides_and_permissions_from_actual_public_roots(self):
        for rows in (16, 128):
            fx = f.make_qwen2_21_fixture(rows)
            reader = m.TypedRootReader(m.RecordPort(fx.memory), fx.config)
            records = dict(enumerate(fx.records))
            for command, op in zip(fx.commands, fx.manifest['schedule']):
                for index, name, write in ((command.src0, op['a'], False),
                                           (command.src1, op['b'], False),
                                           (command.dst, op['dst'], True)):
                    if index == m.NULL:
                        self.assertIsNone(name)
                        continue
                    tensor = reader.read(index, write)
                    self.assertEqual((tensor.address, tensor.dims, tensor.dtype), fx.specs[name])
                    chain = validate_descriptor_chain(index, records)
                    dims = fx.specs[name][1] + (1,) * (4 - len(fx.specs[name][1]))
                    self.assertEqual(chain[1][1].payload,
                                     sum(value << (18 * j) for j, value in enumerate(dims)))
                    strides = (dims[1] * dims[2] * dims[3], dims[2] * dims[3], dims[3])
                    self.assertEqual(chain[2][1].payload,
                                     sum(value << (24 * j) for j, value in enumerate(strides)))
            readonly = {name for name, a in fx.allocations.items() if a.readonly}
            self.assertEqual(readonly, {'wq', 'wk', 'wv', 'wo', 'wg', 'wu', 'wd',
                                        'gamma0', 'gamma1', 'bq', 'bk', 'bv', 'rope', 'x'})
            self.assertEqual(fx.specs['rope'][1], (2, 1024, 64))

    def test_true_reservations_guards_workspace_and_no_view_alias_false_positive(self):
        for rows in (16, 128):
            fx = f.make_qwen2_21_fixture(rows)
            spans = fx.validate_spans()
            self.assertEqual(len(spans), len(fx.allocations) + 3)
            self.assertNotIn('cache_k', dict((name, (a, b)) for name, a, b in spans))
            self.assertNotIn('cache_v', fx.allocations)
            previous = fx.manifest['metadataLimit']
            for a in fx.allocations.values():
                self.assertGreaterEqual(a.address - previous, 64)
                self.assertEqual(a.address % 64, 0)
                self.assertGreaterEqual(a.reserved_bytes, a.storage_bytes)
                previous = a.limit
            workspace = fx.config.regions[3]
            self.assertGreaterEqual(workspace.base - previous, 64)
            self.assertEqual(workspace.limit - workspace.base, 786432)
            self.assertTrue(workspace.read and workspace.write)
            for name in ('wq', 'wk', 'wv', 'wo', 'wg', 'wu', 'wd'):
                a = fx.allocations[name]
                self.assertEqual(a.dtype, 5)
                self.assertEqual(a.reserved_bytes, 2 * a.storage_bytes)
            kv = fx.allocations['kv']
            self.assertEqual(kv.shape, (2, rows, 256))
            self.assertEqual(fx.views['cache_k'], f.AllocationView('kv', 0, (rows, 256), 7))
            self.assertEqual(fx.views['cache_v'],
                             f.AllocationView('kv', rows * 256 * 4, (rows, 256), 7))
            self.assertEqual(fx.specs['cache_v'][0] + fx.views['cache_v'].storage_bytes, kv.limit)

    def test_relocation_preserves_bytes_except_descriptor_addresses(self):
        shift = 0x234560000
        base = f.make_qwen2_21_fixture(128, epoch=19)
        moved = f.make_qwen2_21_fixture(128, epoch=19, relocate=shift)
        self.assertEqual(base.commands, moved.commands)
        self.assertEqual(base.roots, moved.roots)
        self.assertEqual(base.views, moved.views)
        for name, (address, shape, dtype) in base.specs.items():
            self.assertEqual(moved.specs[name], (address + shift, shape, dtype))
        for a, b in zip(base.config.regions, moved.config.regions):
            self.assertEqual((a.base + shift, a.limit + shift, a.read, a.write),
                             (b.base, b.limit, b.read, b.write))
        self.assertEqual(moved.config.epoch, 19)
        self.assertNotEqual(base.provenance['descriptor_sha256'], moved.provenance['descriptor_sha256'])
        self.assertEqual(base.provenance['command_sha256'], moved.provenance['command_sha256'])
        moved.validate_spans()

    def test_metadata_memory_has_no_tensor_payloads_or_materialized_outputs(self):
        for rows in (16, 128):
            fx = f.make_qwen2_21_fixture(rows)
            self.assertEqual(set(fx.memory.mappings), {fx.config.command.base, fx.config.descriptor.base})
            self.assertEqual(sum(map(len, fx.memory.mappings.values())), 3840)
            self.assertEqual(fx.memory.reads, [])
            for _, address, _ in fx.physical_spans():
                if address not in fx.memory.mappings:
                    with self.assertRaises(KeyError):
                        fx.memory.read64(address)
            self.assertFalse(fx.provenance['tensor_payloads_materialized'])
            self.assertFalse(fx.provenance['official_weights'])
            self.assertFalse(fx.provenance['full_block_numeric_proof'])
            self.assertTrue(fx.allocations['scores'].virtual)
            self.assertTrue(fx.allocations['probabilities'].virtual)
            self.assertEqual(fx.scope, 'QWEN2_21_METADATA_ONLY')

    def test_calls_both_retained_packers_without_weight_conversion_payload(self):
        packer = original_packer('pack_owner_block_fixture.py')
        converter = original_packer('pack_owner_bf16_weights.py')
        with mock.patch.object(packer, 'pack', wraps=packer.pack) as pack, \
                mock.patch.object(converter, 'convert', wraps=converter.convert) as convert, \
                mock.patch.object(converter, 'pack_words', side_effect=AssertionError('payload forbidden')), \
                mock.patch.object(f, '_qwen2_21_packers', return_value=(pack, convert)):
            f.make_qwen2_21_fixture(128)
            pack.assert_called_once()
            convert.assert_called_once()
            self.assertFalse(pack.call_args.args[2].exists())
            self.assertFalse(convert.call_args.args[1].exists())

    def test_invalid_profile_types_alignment_epoch_and_max_tokens(self):
        cases = ([dict(rows=value) for value in (0, 1, 15, 17, 127, 129, True, 16.0, '16')]
                 + [dict(relocate=value) for value in (-64, 1, True, 64.0, '64')]
                 + [dict(epoch=value) for value in (-1, 65536, True, 7.0, '7')]
                 + [dict(max_tokens=value) for value in (0, 16, 128, 1025, True, 1024.0, '1024')])
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                f.make_qwen2_21_fixture(**kwargs)

    def test_full_arena_and_workspace_56_bit_boundary(self):
        for rows in (16, 128):
            fx = f.make_qwen2_21_fixture(rows)
            final_legal_shift = m.LIMIT - fx.config.regions[3].limit
            edge = f.make_qwen2_21_fixture(rows, relocate=final_legal_shift)
            self.assertEqual(edge.config.regions[3].limit, m.LIMIT)
            edge.validate_spans()
            for shift in (final_legal_shift + 64, m.LIMIT, 1 << 64):
                with self.subTest(rows=rows, shift=shift), self.assertRaises(ValueError):
                    f.make_qwen2_21_fixture(rows, relocate=shift)

    def test_view_extent_and_true_overlap_rejected(self):
        fx = f.make_qwen2_21_fixture()
        kv = fx.allocations['kv']
        for view in (replace(fx.views['cache_v'], offset_bytes=kv.reserved_bytes),
                     replace(fx.views['cache_v'], allocation='missing'),
                     replace(fx.views['cache_k'], offset_bytes=1)):
            with self.subTest(view=view), self.assertRaises(ValueError):
                replace(fx, views={**fx.views, 'cache_v': view}).validate_spans()
        bad = replace(fx.allocations['up'], address=fx.allocations['gate'].address)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            replace(fx, allocations={**fx.allocations, 'up': bad},
                    specs={**fx.specs, 'up': (bad.address, bad.shape, bad.dtype)}).validate_spans()
        bad = replace(fx.allocations['wq'], reserved_bytes=64)
        with self.assertRaisesRegex(ValueError, 'extent'):
            replace(fx, allocations={**fx.allocations, 'wq': bad}).validate_spans()

    def test_source_provenance_is_pinned_and_readonly(self):
        fx = f.make_qwen2_21_fixture()
        self.assertEqual(fx.provenance['source_commit'], '8212a32f43338163baee4126e522dcacede0fa23')
        self.assertEqual(fx.provenance['source_sha256'], f.QWEN2_21_SOURCE_PINS)
        for path, expected in f.QWEN2_21_SOURCE_PINS:
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected)
        with self.assertRaises(TypeError):
            fx.provenance['official_weights'] = True
        with mock.patch.object(f, 'QWEN2_21_SOURCE_PINS', ((f.QWEN2_21_SOURCE_PINS[0][0], '0' * 64),)):
            with self.assertRaisesRegex(ValueError, 'source pin drift'):
                f.make_qwen2_21_fixture()

    def test_tensor_permissions_and_metadata_workspace_overlap_rejected(self):
        fx = f.make_qwen2_21_fixture()
        writable = replace(fx.allocations['x'], readonly=False)
        with self.assertRaisesRegex(ValueError, 'permission'):
            replace(fx, allocations={**fx.allocations, 'x': writable}).validate_spans()
        for field, tensor in (('command', 'wq'), ('descriptor', 'gamma0')):
            table = getattr(fx.config, field)
            address = fx.allocations[tensor].address
            bad_table = replace(table, base=address, limit=address + table.limit - table.base)
            with self.subTest(table=field), self.assertRaisesRegex(ValueError, 'overlap'):
                replace(fx, config=replace(fx.config, **{field: bad_table})).validate_spans()
        region = fx.config.regions[3]
        address = fx.allocations['y'].address
        bad_workspace = replace(region, base=address, limit=address + region.limit - region.base)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            replace(fx, config=replace(fx.config,
                    regions=fx.config.regions[:3] + (bad_workspace,))).validate_spans()

    def test_ffn4_remains_separate_unchanged_profile(self):
        fx = f.make_ffn4_fixture()
        self.assertEqual(fx.scope, 'FFN4_COMMAND_SUBPROGRAM_ONLY')
        self.assertEqual((len(fx.commands), len(fx.records), len(fx.physical_spans())), (4, 43, 11))
        self.assertEqual(fx.allocations, {})
        self.assertEqual(fx.views, {})
        self.assertEqual([c.opcode for c in fx.commands],
                         [Opcode.MATRIX_GEMM, Opcode.MATRIX_GEMM, Opcode.SFU_ACTIVATION, Opcode.MATRIX_GEMM])


if __name__ == '__main__':
    unittest.main()
