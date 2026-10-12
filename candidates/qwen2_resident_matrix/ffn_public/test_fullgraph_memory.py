"""Small addressed-beat checks for shared public FFN memory; no arithmetic/RTL."""
from dataclasses import replace
import ctypes as C
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import struct
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import execute_numeric as execution
from candidates.qwen2_resident_matrix.ffn_public import fixture, model
from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory
from candidates.qwen2_resident_matrix.ffn_public.fullgraph_memory import FullGraphMemory, SENTINEL, CONTEXT_BYTES

WIRE = execution.numeric.model.down


def setup():
    allocations = {
        'n1': fixture.PhysicalAllocation(0x2000, (1, 16), 7, 64, False),
        'act': fixture.PhysicalAllocation(0x3000, (1, 64), 7, 256, False),
        'gate': fixture.PhysicalAllocation(0x4000, (1, 64), 7, 256, False, True),
        'up': fixture.PhysicalAllocation(0x5000, (1, 64), 7, 256, False, True),
        'wg': fixture.PhysicalAllocation(0x6000, (1, 32), 5, 128, True),
        'wu': fixture.PhysicalAllocation(0x7000, (1, 32), 5, 128, True),
        'wd': fixture.PhysicalAllocation(0x8000, (1, 32), 5, 128, True),
    }
    command, descriptor = model.Table(0x1000, 0x1040, 1), model.Table(0x1100, 0x1140, 1)
    regions = (model.Region(0x2000, 0xa000, True, True),
               model.Region(0xa000, 0xb000, True, False),
               model.Region(0x1000, 0x1200, True, False),
               model.Region(0x100000, 0x100000 + 786432, True, True))
    config = model.LaunchConfig(command, descriptor, regions, 7)
    f = SimpleNamespace(allocations=allocations, config=config, validate_spans=lambda: None,
                        memory=SimpleNamespace(mappings={0x1000: bytes(64), 0x1100: bytes(64)}))
    inputs = {name: lambda offset, value=i: struct.pack('<32H', *([value + offset] * 32))
              for i, name in enumerate(('wg', 'wu', 'wd'), 1)}
    physical = PhysicalMemory(f, inputs)
    return physical, FullGraphMemory(physical)


def job(n=32, k=384):
    return SimpleNamespace(tag=11, m=16, n=n, k=k, a=0x2000, b=0x6000, dst=0x9000,
                           activation_bf16=False, weight_bf16=True, output_bf16=False)


def begin(memory, n=32, k=384):
    ws = memory.workspace
    task = job(n, k)
    reservation = WIRE.PrefixWorkspace(ws.base, ws.extent, 8, 128)
    view = ws.begin(task, reservation)
    ws.accept_group(0, 0, n // 32, 1)
    return ws, view


def write(ws, address, version, sequence, *, ack=True):
    command = WIRE.WriteCommand(address, 1, (ws.job.tag << 32) | sequence)
    words = (version * 1000 + (address - ws.base) // 64,) * 16
    ws.write_event('command', command)
    ws.write_event('data', WIRE.WriteBeat(words, True))
    response = WIRE.WriteAck(command.tag, nbytes=64)
    if ack:
        ws.write_event('ack', response)
    return command, words, response


def write_sweep(ws, version):
    for index, address in enumerate(ws.versions):
        write(ws, address, version, version * 10000 + index)


def seed_context(ws, local_context):
    chunk, n_base, _, sequence = ws.group
    request = WIRE.SeedRequest(ws.job.tag, sequence, ws.reservation.generation, local_context)
    ws.seed_begin(request)
    start = ws.base + (n_base // 32 + local_context) * CONTEXT_BYTES
    for index, address in enumerate(range(start, start + CONTEXT_BYTES, 64)):
        command = SimpleNamespace(address=address, beats=1, kind='prefix', tag=(ws.job.tag << 32) | index)
        words = ws.accept_read(command)
        ws.retire_read(command, words)
        ws.seed_beat(address, request, words)
    return WIRE.SeedAck(request)


class FullGraphMemoryTests(unittest.TestCase):
    def test_names_only_address_dispatch_and_no_n1_preload(self):
        physical, memory = setup()
        for name, expected, value in (('wg', 'gate_weight', 1), ('wu', 'up_weight', 2), ('wd', 'down_weight', 3)):
            address = physical.regions[name]['base']
            self.assertEqual(memory.read64(address), (expected, (value,) * 32))
            self.assertEqual(physical.read_regions[name], 64)
            with self.assertRaisesRegex(ValueError, 'reservation guard'):
                memory.read64(address + 64)
        with self.assertRaisesRegex(ValueError, 'read before ACK'):
            memory.read64(physical.regions['n1']['base'])
        self.assertIs(physical.metadata_port().physical_memory, physical)
        self.assertIs(memory.physical_memory, physical)
        self.assertIs(memory.act.data, physical.regions['act']['data'])
        self.assertEqual(physical.raw(0x2000, 64), SENTINEL * 16)
        self.assertTrue(memory.check_virtual()['unchanged'])
        with self.assertRaisesRegex(ValueError, 'virtual allocation'):
            memory.read64(physical.regions['gate']['base'])

    def test_shared_act_actual_events_ack_and_publication_are_distinct(self):
        physical, memory = setup()
        act = memory.act
        command = WIRE.WriteCommand(act.base, 4, 31)
        act.accept_command(command)
        self.assertEqual(physical.pending, ['act', command, 0])
        for i in range(4):
            self.assertEqual(act.accept_data(SimpleNamespace(words=(i + 1,) * 16,
                                mask=(1 << 64) - 1, last=i == 3)), act.base + i * 64)
        self.assertTrue(act.awaiting_ack)
        with self.assertRaisesRegex(ValueError, 'ACK tag/status'):
            act.accept_ack(WIRE.WriteAck(32, nbytes=256))
        self.assertEqual(act.ack_bytes, 0)
        act.accept_ack(WIRE.WriteAck(31, nbytes=256))
        raw, report = act.validate_full()
        self.assertEqual(raw, b''.join(struct.pack('<16I', *((i + 1,) * 16)) for i in range(4)))
        self.assertEqual(report['ack_bytes'], 256)
        self.assertEqual(physical.regions['act']['records'], [(command, WIRE.WriteAck(31, nbytes=256))])
        with self.assertRaisesRegex(ValueError, 'read before ACK'):
            act.read64(act.base)
        task = SimpleNamespace(dst=act.base, write_bytes=act.extent, tag=31)
        physical.terminal(task, (31, None, act.extent))
        physical.publish(task, SimpleNamespace(published=[(act.base, act.base + act.extent)], status=None))
        self.assertEqual(memory.read64(act.base), ('act', (1,) * 16))
        self.assertEqual(physical.counts['write_data_bytes'], 256)

    def test_workspace_same_index_full_reservation_and_audit_is_not_transport(self):
        physical, memory = setup()
        ws, view = begin(memory)
        self.assertEqual(ws.extent, 786432)
        self.assertEqual(view.extent, CONTEXT_BYTES)
        self.assertIs(view.data, physical.regions['workspace']['data'])
        self.assertIs(view.data, ws.data)
        command, words, ack = write(ws, ws.base, 1, 1, ack=False)
        self.assertEqual(view.read64(ws.base), words)
        self.assertEqual(ws.versions[ws.base], 0)
        with self.assertRaisesRegex(ValueError, 'read before ACK|workspace reads require'):
            physical.read64(ws.base)
        with self.assertRaisesRegex(ValueError, 'accepted command/data/ACK'):
            view.write64(ws.base, words)
        with self.assertRaisesRegex(ValueError, 'prior group ACK|outstanding'):
            ws.accept_group(1, 0, 1, 2)
        ws.write_event('ack', ack)
        self.assertEqual(ws.versions[ws.base], 1)
        self.assertEqual(physical.regions['workspace']['records'], [(command, ack)])
        view.check_guards()
        self.assertEqual(len(view.raw()), CONTEXT_BYTES)
        view.data[64 + view.extent] ^= 1
        with self.assertRaisesRegex(ValueError, 'inactive public workspace tail'):
            view.check_guards()
        view.data[64 + view.extent] ^= 1
        view.data[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'guard corruption'):
            view.check_guards()

    def test_workspace_two_versions_actual_read_seed_ack_before_overwrite(self):
        physical, memory = setup()
        ws, view = begin(memory)
        write_sweep(ws, 1)
        ws.accept_group(1, 0, 1, 2)
        ack = seed_context(ws, 0)
        with self.assertRaisesRegex(ValueError, 'all group seed ACKs'):
            write(ws, ws.base, 2, 20000)
        ws.seed_ack(ack)
        with self.assertRaisesRegex(ValueError, 'unsolicited or duplicate'):
            ws.seed_ack(ack)
        write_sweep(ws, 2)
        ws.accept_group(2, 0, 1, 3)
        ws.seed_ack(seed_context(ws, 0))
        ws.finish()
        self.assertTrue(ws.finished)
        self.assertTrue(ws.drained)
        self.assertEqual(set(ws.versions.values()), {2})
        self.assertEqual(len(ws.read_versions), 512)
        self.assertEqual(len(ws.seed_versions), 512)
        self.assertEqual(physical.counts['write_ack_bytes'], CONTEXT_BYTES * 2)
        self.assertEqual(physical.read_regions['workspace'], CONTEXT_BYTES * 2)
        with self.assertRaisesRegex(ValueError, 'inactive, finished or invalidated'):
            ws.accept_read(SimpleNamespace(address=ws.base, beats=1, kind='prefix', tag=11 << 32))
        with self.assertRaisesRegex(ValueError, 'read before ACK|workspace reads require'):
            physical.read64(ws.base)
        self.assertEqual(view.read64(ws.base), (2000,) * 16)

    def test_all_group_seed_acks_required_not_just_address_context(self):
        _, memory = setup()
        ws, _ = begin(memory, n=64)
        write_sweep(ws, 1)
        ws.accept_group(1, 0, 2, 2)
        ws.seed_ack(seed_context(ws, 0))
        with self.assertRaisesRegex(ValueError, 'all group seed ACKs'):
            write(ws, ws.base, 2, 20000)
        ws.seed_ack(seed_context(ws, 1))
        write(ws, ws.base, 2, 20000)
        self.assertEqual(ws.versions[ws.base], 2)

    def test_seed_and_read_identity_payload_and_coverage(self):
        _, memory = setup()
        ws, _ = begin(memory)
        write_sweep(ws, 1)
        ws.accept_group(1, 0, 1, 2)
        request = WIRE.SeedRequest(11, 2, 8, 0)
        ws.seed_begin(request)
        with self.assertRaisesRegex(ValueError, 'all actual read/seed beats'):
            ws.seed_ack(WIRE.SeedAck(request))
        with self.assertRaisesRegex(ValueError, 'exact actual read'):
            ws.seed_beat(ws.base, request, (1000,) * 16)
        command = SimpleNamespace(address=ws.base, beats=1, kind='prefix', tag=11 << 32)
        words = ws.accept_read(command)
        with self.assertRaisesRegex(ValueError, 'duplicate accepted read'):
            ws.accept_read(command)
        with self.assertRaisesRegex(ValueError, 'identity/payload'):
            ws.retire_read(command, (9,) * 16)
        ws.retire_read(command, words)
        with self.assertRaisesRegex(ValueError, 'identity/generation/context'):
            ws.seed_beat(ws.base, replace(request, generation=9), words)
        ws.seed_beat(ws.base, request, words)
        with self.assertRaisesRegex(ValueError, 'exact actual read'):
            ws.seed_beat(ws.base, request, words)
        with self.assertRaisesRegex(ValueError, 'duplicate accepted read'):
            ws.accept_read(command)

    def test_ordinary_physical_events_cannot_bypass_workspace_lifecycle(self):
        physical, memory = setup()
        ws, _ = begin(memory)
        command = WIRE.WriteCommand(ws.base, 1, 11 << 32)
        beat = WIRE.WriteBeat((7,) * 16, True)
        ack = WIRE.WriteAck(command.tag, nbytes=64)
        with self.assertRaisesRegex(ValueError, 'workspace'):
            physical.write_event('command', command)
        self.assertIsNone(physical.pending)
        ws.write_event('command', command)
        with self.assertRaisesRegex(ValueError, 'workspace'):
            physical.write_event('data', beat)
        self.assertEqual(physical.pending, ['workspace', command, 0])
        self.assertEqual(ws.data_versions[ws.base], 0)
        ws.write_event('data', beat)
        with self.assertRaisesRegex(ValueError, 'workspace'):
            physical.write_event('ack', ack)
        self.assertEqual(physical.pending, ['workspace', command, 1])
        self.assertEqual(ws.versions[ws.base], 0)
        self.assertEqual(ws.region['acked'], set())
        ws.write_event('ack', ack)
        self.assertIsNone(physical.pending)
        self.assertEqual(ws.versions[ws.base], 1)
        self.assertEqual(physical.counts['write_acks'], 1)

    def test_shared_transaction_slot_and_fault_drain_invalidate(self):
        physical, memory = setup()
        ws, _ = begin(memory)
        command = WIRE.WriteCommand(ws.base, 1, 11 << 32)
        ws.write_event('command', command)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            memory.act.accept_command(WIRE.WriteCommand(memory.act.base, 1, 22))
        ws.invalidate('owner reset with accepted workspace descriptor')
        self.assertFalse(ws.drained)
        with self.assertRaisesRegex(ValueError, 'invalidated'):
            ws.accept_group(0, 0, 1, 1)
        ws.write_event('data', WIRE.WriteBeat((5,) * 16, True))
        ws.write_event('ack', WIRE.WriteAck(command.tag, error=True, nbytes=64))
        self.assertTrue(ws.drained)
        self.assertEqual(ws.versions[ws.base], 0)
        self.assertEqual(physical.regions['workspace']['acked'], set())
        self.assertFalse(physical.regions['workspace']['published'])
        with self.assertRaisesRegex(ValueError, 'invalidated'):
            ws.finish()
        with self.assertRaisesRegex(ValueError, 'already used'):
            ws.begin(job(), ws.reservation)

    def test_invalidated_accepted_read_drains_without_publication(self):
        _, memory = setup()
        ws, _ = begin(memory)
        write_sweep(ws, 1)
        ws.accept_group(1, 0, 1, 2)
        request = WIRE.SeedRequest(11, 2, 8, 0)
        ws.seed_begin(request)
        command = SimpleNamespace(address=ws.base, beats=1, kind='prefix', tag=11 << 32)
        words = ws.accept_read(command)
        ws.invalidate('owner abort after read acceptance')
        self.assertFalse(ws.drained)
        ws.retire_read(command, words)
        ws.seed_ack(WIRE.SeedAck(request, error=True))
        self.assertTrue(ws.drained)
        self.assertEqual(ws.read_versions, set())
        self.assertEqual(ws.seed_commits, set())

    def test_epoch_generation_and_overlap_are_bound_to_public_configuration(self):
        physical, memory = setup()
        ws = memory.workspace
        with self.assertRaisesRegex(ValueError, 'epoch generation'):
            ws.begin(job(), WIRE.PrefixWorkspace(ws.base, ws.extent, 9, 128))
        ws, _ = begin(memory)
        physical.fixture.config = replace(physical.fixture.config, epoch=8)
        with self.assertRaisesRegex(ValueError, 'epoch/reservation changed'):
            write(ws, ws.base, 1, 1)
        physical, memory = setup()
        del physical.regions['workspace']
        physical.regions['overlap'] = dict(base=memory.workspace.base + 64, reserved=64)
        from candidates.qwen2_resident_matrix.ffn_public.fullgraph_memory import SharedWorkspace
        with self.assertRaisesRegex(ValueError, 'overlaps physical allocation'):
            SharedWorkspace(physical)


class SharedWorkspaceDriverTests(unittest.TestCase):
    """Reuse only the verified existing strict binary; never compile a test."""
    @classmethod
    def setUpClass(cls):
        cached = ROOT / 'work/qwen2_ffn_fullgroup_20261012/actual_m128_01'
        source = Path('candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp')
        binary, receipt = cached / 'numeric_recipe.so', cached / 'summary.json'
        frozen = cached / 'frozen_sources' / source
        if not all(p.is_file() for p in (binary, receipt, frozen)):
            raise unittest.SkipTest('verified existing arithmetic binary unavailable; no compilation allowed')
        compiled = json.loads(receipt.read_text())['compile']
        if (frozen.read_bytes() != (ROOT / source).read_bytes() or
                hashlib.sha256(binary.read_bytes()).hexdigest() != compiled['binary_sha256'] or
                not {'-O2', '-fno-fast-math', '-ffp-contract=off', '-frounding-math'} <= set(compiled['argv'])):
            raise unittest.SkipTest('existing arithmetic source/binary verification failed')
        cls.lib = C.CDLL(str(binary))
        u16, u32 = C.POINTER(C.c_uint16), C.POINTER(C.c_uint32)
        for name, args in (('td_reset', []), ('td_group', [C.c_uint] * 3),
                ('td_seed_begin', [C.c_uint]), ('td_seed_beat', [C.c_uint, C.c_uint, u32]),
                ('td_seed_commit', [C.c_uint]), ('td_step', [C.c_uint] * 6 + [u16, u16, u32])):
            getattr(cls.lib, name).argtypes, getattr(cls.lib, name).restype = args, C.c_int

    def memory(self, k):
        physical, _ = setup()
        f = physical.fixture
        f.allocations = dict(f.allocations)
        f.allocations['act'] = fixture.PhysicalAllocation(0xa000000, (16, k), 7, 16 * k * 4, False)
        f.allocations['wd'] = fixture.PhysicalAllocation(0x6000000, (k, 32), 5, k * 32 * 2, True)
        f.allocations['down'] = fixture.PhysicalAllocation(0xb000000, (16, 32), 7, 16 * 32 * 4, False)
        f.config = replace(f.config, regions=(model.Region(0x2000, 0x10000000, True, True),
            model.Region(0, 0, False, False), model.Region(0x1000, 0x1200, True, False),
            model.Region(0x10000000, 0x10000000 + 786432, True, True)))
        physical = PhysicalMemory(f, {'wd': lambda offset: struct.pack('<32H', *((0x3f00,) * 32))})
        memory = FullGraphMemory(physical)
        act = memory.act
        for sequence, address in enumerate(range(act.base, act.base + act.extent, 1024)):
            command = WIRE.WriteCommand(address, 16, (99 << 32) | sequence)
            act.accept_command(command)
            for index in range(16):
                act.accept_data(SimpleNamespace(words=(0x3f800000,) * 16, mask=(1 << 64) - 1, last=index == 15))
            act.accept_ack(WIRE.WriteAck(command.tag, nbytes=1024))
        task = SimpleNamespace(dst=act.base, write_bytes=act.extent, tag=99)
        physical.terminal(task, (99, None, act.extent))
        physical.publish(task, SimpleNamespace(published=[(act.base, act.base + act.extent)], status=None))
        reservation = WIRE.PrefixWorkspace(memory.workspace.base, memory.workspace.extent, 8, 128)
        owner = execution.numeric.model.FfnDrainOwnerModel(reservation, enable_ffn_window=True,
            enable_ffn_tiles=True, enable_ffn_drain=True)
        task = execution.numeric.model.Job(m=16, k=k, n=32, tag=11, a=act.base, b=0x6000000,
            dst=0xb000000, activation_bf16=False, weight_bf16=True, output_bf16=False, write_bytes=2048)
        return physical, memory, owner, task

    def test_existing_driver_two_and_four_chunks_share_public_prefix_and_output(self):
        for k in (256, 512):
            with self.subTest(k=k), tempfile.TemporaryDirectory(prefix='shared_workspace_driver_') as out:
                physical, memory, owner, task = self.memory(k)
                self.assertEqual(self.lib.td_reset(), 0)
                report, actual = execution.down_driver.execute_down(execution.numeric.model, owner,
                    self.lib, memory, task, out, time.monotonic() + 30, execution.numeric.CappedTrace(),
                    synthetic_geometry=True, workspace_transport=memory.workspace,
                    output_event=physical.dense_sink(task))
                self.assertTrue(report['prefix']['shared_public_allocation'])
                self.assertEqual(report['prefix']['active_extent'], CONTEXT_BYTES)
                self.assertEqual(report['prefix']['reserved_extent'], 786432)
                self.assertEqual(report['prefix']['ack_bytes'], (k // 128 - 1) * CONTEXT_BYTES)
                self.assertEqual(physical.raw(task.dst, task.write_bytes), actual.tobytes())
                self.assertTrue(physical.regions['down']['terminal'])
                self.assertFalse(physical.regions['down']['published'])
                with self.assertRaisesRegex(ValueError, 'read before ACK'):
                    physical.read64(task.dst)
                self.assertTrue(memory.workspace.finished)
                self.assertTrue(memory.workspace.drained)
                memory.workspace.check_guards()
                # Independent expectation is only inspected after actual final ACK/terminal.
                expected = struct.unpack('<I', struct.pack('<f', k * 0.5))[0]
                self.assertEqual(tuple(actual), (expected,) * (16 * 32))

    def test_single_chunk_shared_lease_keeps_entire_workspace_pristine(self):
        physical, memory, owner, task = self.memory(128)
        self.assertEqual(self.lib.td_reset(), 0)
        with tempfile.TemporaryDirectory(prefix='shared_workspace_single_') as out:
            report, destination = execution.down_driver.execute_dense(execution.numeric.model, owner,
                self.lib, physical, task, out, time.monotonic() + 30, execution.numeric.CappedTrace(),
                a_source=physical.dense_source(task), output_event=physical.dense_sink(task),
                workspace_transport=memory.workspace)
        self.assertEqual(report['prefix']['active_extent'], 0)
        self.assertEqual(physical.raw(memory.workspace.base, memory.workspace.extent),
                         SENTINEL * (memory.workspace.extent // 4))
        self.assertEqual(physical.raw(task.dst, task.write_bytes), destination.raw())
        self.assertTrue(memory.workspace.finished)

    def test_driver_fault_invalidates_workspace_and_never_publishes_output(self):
        physical, memory, owner, task = self.memory(256)
        self.assertEqual(self.lib.td_reset(), 0)
        original = memory.workspace.write_event
        def fail_after_data(kind, value):
            original(kind, value)
            if kind == 'data':
                raise ValueError('injected actual workspace data fault')
        memory.workspace.write_event = fail_after_data
        with tempfile.TemporaryDirectory(prefix='shared_workspace_fault_') as out:
            with self.assertRaisesRegex(ValueError, 'actual workspace data fault'):
                execution.down_driver.execute_down(execution.numeric.model, owner, self.lib, memory,
                    task, out, time.monotonic() + 30, execution.numeric.CappedTrace(),
                    synthetic_geometry=True, workspace_transport=memory.workspace,
                    output_event=physical.dense_sink(task))
        self.assertIn('actual workspace data fault', memory.workspace.invalidated)
        self.assertFalse(memory.workspace.drained)
        self.assertEqual(len(physical.regions['workspace']['written']), 1)
        self.assertEqual(physical.regions['workspace']['acked'], set())
        self.assertFalse(physical.regions['down']['terminal'])
        self.assertFalse(physical.regions['down']['published'])


if __name__ == '__main__':
    unittest.main()
