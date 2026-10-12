"""Bounded public Attention/DDR integration, not complete public21 acceptance.

The M1 three-command fixture has original public QK/Softmax/PV encodings and
synthetic readonly operands. Its real Attention owner and Host execute, with
no opaque success terminals and no populated writable intermediates. Supply
MATRIX_SERVICE_LIBRARY to reuse an existing host library; this suite never
compiles, downloads inputs, or executes a whole numerical block.
"""
import ctypes as C
from dataclasses import replace
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import fixture as f, model
from candidates.qwen2_resident_matrix.ffn_public import execute_numeric as e
from candidates.qwen2_resident_matrix.ffn_public import fullgraph_execution as g
from candidates.qwen2_resident_matrix.ffn_public import prefix_execution as p
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import PrefixOwner
from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService
from candidates.qwen2_resident_matrix.ffn_attention.attention_owner import AttentionOwner
from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import MatrixService, configure_library


def attention_fixture():
    specs = dict(q=(0x1000000, (1, 1536), 7), k=(0x2000000, (1, 256), 7),
                 v=(0x3000000, (1, 256), 7), scores=(0x8000000, (12, 1, 1), 7),
                 probabilities=(0x9000000, (12, 1, 1), 7), att=(0xa000000, (1, 1536), 7))
    records, commands, roots = [], [], []

    def chain(name, extra=()):
        address, shape, dtype = specs[name]
        dims, root = shape + (1,) * (4 - len(shape)), len(records)
        records.extend((f.tensor_base_record(address, dtype=dtype, rank=len(shape), next_index=root + 1),
            f.shape4_record(dims, next_index=root + 2),
            f.stride3_record((dims[1] * dims[2] * dims[3], dims[2] * dims[3], dims[3]),
                            next_index=root + 3 if extra else f.NULL)))
        for index, record in enumerate(extra):
            records.append(f.DescriptorRecord(record.record_type, record.subtype, record.flags,
                root + 4 + index if index + 1 < len(extra) else f.NULL, record.payload))
        return root

    for opcode, a, b, dst, extra in (
        (f.Opcode.MATRIX_QK, 'q', 'k', 'scores',
         (f.matrix_op_record(m=1, n=1, k=128, dataflow=0, transpose_b=True), f.MatrixAux(full_c=True).to_record())),
        (f.Opcode.SFU_SOFTMAX, 'scores', None, 'probabilities',
         (f.SfuProgram(0x33, 1, input_dtype=f.TensorDType.FP32, output_dtype=f.TensorDType.FP32).to_record(),)),
        (f.Opcode.MATRIX_PV, 'probabilities', 'v', 'att',
         (f.matrix_op_record(m=1, n=128, k=1, dataflow=0), f.MatrixAux(full_c=True).to_record()))):
        root = chain(a, extra), chain(b) if b else f.NULL, chain(dst)
        pc = len(commands)
        commands.append(f.Command128(opcode, f.Engine.SFU_CGRA if b is None else f.Engine.MATRIX,
            event_wait=pc, event_signal=pc + 1, src0=root[0], src1=root[1], dst=root[2]))
        roots.append(root)
    cb = b''.join(command.to_bytes() for command in commands)
    db = b''.join(record.pack().to_bytes(16, 'little') for record in records)
    ct = model.Table(0xc000000, 0xc000000 + model.align64(len(cb)), len(commands))
    dt = model.Table(0xc001000, 0xc001000 + model.align64(len(db)), len(records))
    regions = (model.Region(0x1000000, 0x8000000, True, False),
               model.Region(0x8000000, 0xc000000, True, True),
               model.Region(0xc000000, 0xc010000, True, False),
               model.Region(0x10000000, 0x100c0000, True, True))
    config = model.LaunchConfig(ct, dt, regions)
    metadata = model.MetadataMemory(((ct.base, cb.ljust(model.align64(len(cb)), b'\0')),
                                    (dt.base, db.ljust(model.align64(len(db)), b'\0'))))
    allocations = {}
    for name, (address, shape, dtype) in specs.items():
        words = 1
        for dimension in shape:
            words *= dimension
        allocations[name] = f.PhysicalAllocation(address, shape, dtype, model.align64(words * 4),
            name in ('q', 'k', 'v'), name in ('scores', 'probabilities'))
    fixture = f.Fixture(config, metadata, tuple(commands), tuple(records), tuple(roots), specs,
                        scope='SYNTHETIC_M1_PUBLIC_ATTENTION_ONLY', allocations=allocations)
    fixture.validate_spans()
    return fixture


def setup(library):
    fixture = attention_fixture()
    memory = p.PhysicalMemory(fixture, dict(q=lambda _: bytes(64), k=lambda _: bytes(64),
        v=lambda offset: struct.pack('<16I', *((0x3e000000 if offset < 128 * 4 else 0xbe800000,) * 16))))
    scalar = ScalarService()
    lib = configure_library(C.CDLL(library))
    assert lib.td_reset() == 0
    matrix = MatrixService(lib)
    region = fixture.config.regions[3]
    workspace = e.numeric.model.PrefixWorkspace(region.base, region.limit - region.base,
                                                fixture.config.epoch + 1, 2560)
    owner = e.numeric.model.FfnDrainOwnerModel(workspace, enable_ffn_window=True,
        enable_ffn_tiles=True, enable_ffn_drain=True)
    x = e.PublicExecution(model.PublicFrontend(memory.metadata_port(), fixture.config), owner,
        e.numeric.CappedTrace(), time.monotonic() + 30,
        host=model.group.HostControl(enabled=True, legacy_prefix=True, legacy_attention=True),
        prefix_owner=PrefixOwner(scalar), attention_owner=AttentionOwner(matrix, scalar), matrix_service=matrix)
    return memory, x


class FullgraphAdmissionTests(unittest.TestCase):
    def test_synthetic_fixture_is_public_and_has_only_readonly_input_bytes(self):
        fixture = attention_fixture()
        self.assertEqual([int(command.opcode) for command in fixture.commands], [0x23, 0x33, 0x24])
        self.assertEqual(fixture.commands[1].src1, f.NULL)
        memory = p.PhysicalMemory(fixture, {})
        memory.check_coexistence(unpublished_pristine=True)
        self.assertEqual(sum(bool(region['written']) for region in memory.regions.values()
                             if not region['readonly']), 0)


@unittest.skipUnless(os.environ.get('MATRIX_SERVICE_LIBRARY'), 'provide an existing MATRIX_SERVICE_LIBRARY; no compilation')
class ActualAttentionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.memory, self.x = setup(os.environ['MATRIX_SERVICE_LIBRARY'])

    def test_real_owner_final_ack_then_all_three_completions_publish_output(self):
        memory, x = self.memory, self.x
        job = x.advance_to_request()['ordinary_request']
        self.assertEqual((job.kind, job.tag & 0xffff), ('Attention', 2))
        report = g.execute_attention_owner(x, memory, job, final_ack_stall=7)
        self.assertEqual(report['accepted']['final_ack_stall'], 7)
        self.assertEqual(report['accepted']['requests'], report['accepted']['responses'])
        self.assertEqual(report['accepted']['matrix_requests'], report['accepted']['matrix_results'])
        self.assertEqual(x.counts['request_fire'], 1)
        self.assertEqual(x.counts['owner_result_fire'], 1)
        self.assertEqual(x.host.completed, 0)
        self.assertIsNone(x.matrix_service.owner)
        self.assertTrue(memory.regions['att']['terminal'])
        expected = struct.pack('<1536I', *((0x3e000000,) * 768 + (0xbe800000,) * 768))
        self.assertEqual(memory.raw(job.dst, job.write_bytes), expected)
        for pc in (0, 1):
            x.publish_completions((pc,))
            with self.assertRaisesRegex(ValueError, 'publish before public completion'):
                memory.publish(job, x.host)
            with self.assertRaisesRegex(ValueError, 'read before ACK'):
                memory.read64(job.dst)
        x.publish_completions((2,))
        memory.publish(job, x.host)
        result = x.finish()
        self.assertEqual((result['completed'], result['jobs'], result['write_bytes']), (3, 1, 6144))
        self.assertEqual(memory.read64(job.dst)[1], (0x3e000000,) * 16)
        self.assertEqual(x.attention_jobs, x.attention_results)
        self.assertTrue(report['backend']['synthetic_shape'])
        self.assertFalse(report['backend']['model_ticks_are_hardware_cycles'])
        self.assertEqual([c['pc'] for c in x.completions], [0, 1, 2])
        memory.check_coexistence(unpublished_pristine=True)

    def test_actual_numeric_fault_reaches_host_and_never_publishes(self):
        memory, x = self.memory, self.x
        memory.regions['q']['provider'] = lambda offset: struct.pack('<16I',
            *((0x00010000,) + (0,) * 15 if offset == 0 else (0,) * 16))
        memory.regions['k']['provider'] = lambda _: struct.pack('<16I', *((0x3f800000,) * 16))
        job = x.advance_to_request()['ordinary_request']
        with self.assertRaisesRegex(ValueError, 'Attention owner error'):
            g.execute_attention_owner(x, memory, job)
        self.assertEqual(x.host.status, 'Numerical')
        self.assertEqual(x.host.completed, 0)
        self.assertEqual(x.host.published, [])
        self.assertFalse(memory.regions['att']['terminal'])
        self.assertIsNone(x.matrix_service.owner)
        memory.check_coexistence(unpublished_pristine=True)

    def test_copied_job_and_disconnected_metadata_are_rejected_before_admission(self):
        memory, x = self.memory, self.x
        job = x.advance_to_request()['ordinary_request']
        with self.assertRaisesRegex(ValueError, 'original fused public owner job'):
            g.execute_attention_owner(x, memory, replace(job))
        self.assertEqual(x.host.jobs, 0)
        x.frontend.port.memory = memory.fixture.memory
        with self.assertRaisesRegex(ValueError, 'identical physical map'):
            g.execute_attention_owner(x, memory, job)
        self.assertEqual(x.host.jobs, 0)

    def test_fullgraph_continuation_rejects_partial_fixture_without_memory_mutation(self):
        memory, x = self.memory, self.x
        with self.assertRaisesRegex(ValueError, 'ten actual public prefix completions'):
            g.execute_public_suffix(x, memory, None, ROOT)
        self.assertEqual(x.counts['request_fire'], 0)
        self.assertNotIn('workspace', memory.regions)
        memory.check_coexistence(unpublished_pristine=True)

    def test_dense_helper_uses_actual_shared_service_stores_and_terminal(self):
        fixture = f.make_dense_fixture()
        fixture.allocations = {name: f.PhysicalAllocation(address, shape, dtype,
            model.align64(shape[0] * shape[1] * (2 if dtype == 5 else 4)), name != 'dst')
            for name, (address, shape, dtype) in fixture.specs.items()}
        memory = p.PhysicalMemory(fixture, dict(
            a=lambda _: struct.pack('<16I', *((0x3f800000,) * 16)),
            weight=lambda _: struct.pack('<32H', *((0x3f00,) * 32))))
        lib = configure_library(C.CDLL(os.environ['MATRIX_SERVICE_LIBRARY']))
        self.assertEqual(lib.td_reset(), 0)
        matrix = MatrixService(lib)
        region = fixture.config.regions[3]
        workspace = e.numeric.model.PrefixWorkspace(region.base, region.limit - region.base,
                                                    fixture.config.epoch + 1, 2560)
        owner = e.numeric.model.FfnDrainOwnerModel(workspace, enable_ffn_window=True,
            enable_ffn_tiles=True, enable_ffn_drain=True)
        x = e.PublicExecution(model.PublicFrontend(memory.metadata_port(), fixture.config), owner,
            e.numeric.CappedTrace(), time.monotonic() + 30, matrix_service=matrix)
        job = x.advance_to_request()['ordinary_request']
        with tempfile.TemporaryDirectory(prefix='qwen2_suffix_dense_test_') as temporary:
            report = g._dense(x, memory, memory, lib, job, Path(temporary) / 'dense')
        self.assertTrue(report['completed'])
        self.assertEqual(report['final_ack_fence']['held_ticks'], 5)
        self.assertEqual(matrix.counts['owner_acquires'], 1)
        self.assertEqual(matrix.counts['owner_responses'], 1)
        self.assertEqual(matrix.counts['owner_releases'], 1)
        self.assertIsNone(matrix.owner)
        self.assertTrue(memory.regions['dst']['terminal'])
        self.assertFalse(memory.regions['dst']['published'])
        self.assertEqual(memory.raw(job.dst, job.write_bytes), struct.pack('<512I', *((0x43000000,) * 512)))
        x.publish_completions((0,))
        memory.publish(job, x.host)
        x.retire_ordinary_bookkeeping()
        result = x.finish()
        self.assertEqual((result['completed'], result['jobs']), (1, 1))
        self.assertEqual(len(x.ordinary_history), 1)
        memory.check_coexistence()


if __name__ == '__main__':
    unittest.main()
