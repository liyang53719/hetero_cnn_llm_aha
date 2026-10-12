"""Actual prefix memory/Host coupling; bounded synthetic values, no RTL."""
from pathlib import Path
from types import SimpleNamespace
import struct
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import fixture, model
from candidates.qwen2_resident_matrix.ffn_public import execute_numeric as e
from candidates.qwen2_resident_matrix.ffn_public import prefix_execution as p
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import PrefixOwner, MemoryResponse
from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import ref_norm


def setup():
    f = fixture.make_qwen2_21_fixture(16)
    inputs = {'x': lambda offset: struct.pack('<16I', *((0x3f000000, 0xbf800000) * 8)),
              'gamma0': lambda offset: struct.pack('<16I', *((0x3f800000,) * 16))}
    memory = p.PhysicalMemory(f, inputs)
    region = f.config.regions[3]
    workspace = e.numeric.model.PrefixWorkspace(region.base, region.limit - region.base,
                                                f.config.epoch + 1, 2560)
    owner = e.numeric.model.FfnDrainOwnerModel(workspace, enable_ffn_window=True,
        enable_ffn_tiles=True, enable_ffn_drain=True)
    x = e.PublicExecution(model.PublicFrontend(memory.metadata_port(), f.config), owner,
        e.numeric.CappedTrace(), time.monotonic() + 60,
        host=model.group.HostControl(enabled=True, legacy_prefix=True), prefix_owner=PrefixOwner())
    return f, memory, x


class PrefixMemoryTests(unittest.TestCase):
    def test_raw_public_norm_requires_actual_ack_and_public_completion(self):
        f, mem, x = setup()
        job = x.advance_to_request()['ordinary_request']
        self.assertEqual(job.kind, 'Norm')
        with self.assertRaisesRegex(ValueError, 'read before ACK'):
            mem.read64(job.dst)
        report = p.execute_prefix_owner(x, mem, job)
        self.assertEqual(report['accepted']['final_ack_stall'], 5)
        self.assertEqual(x.host.completed, 0)
        self.assertEqual(x.host.state, 'complete')
        self.assertEqual(x.prefix_jobs, 1)
        self.assertEqual(x.prefix_results, 1)
        self.assertIsNone(x.host.result)
        self.assertTrue(mem.regions['n0']['terminal'])
        self.assertFalse(mem.regions['n0']['published'])
        with self.assertRaisesRegex(ValueError, 'read before ACK'):
            mem.read64(job.dst)
        with self.assertRaisesRegex(ValueError, 'publish before public completion'):
            mem.publish(job, x.host)
        x.publish_completions((0,), stall_edges=4)
        mem.publish(job, x.host)
        expected = ref_norm((0x3f000000, 0xbf800000) * 768, (0x3f800000,) * 1536)
        self.assertEqual(mem.raw(job.dst, job.write_bytes), struct.pack('<1536I', *expected) * 16)
        self.assertEqual(mem.read64(job.dst)[1], expected[:16])
        dense = x.advance_to_request()['ordinary_request']
        self.assertEqual((dense.kind, dense.a), ('Dense', job.dst))
        source = mem.dense_source(dense)
        self.assertTrue(source.ready())
        self.assertEqual(source.raw(), mem.raw(job.dst, job.write_bytes))
        self.assertEqual(sum(ack.nbytes for _, ack in source.write_acks()), job.write_bytes)
        self.assertEqual(mem.report()['reads_by_allocation']['x'], 16 * 1536 * 4)
        self.assertIsNone(x.host.result)
        mem.check_coexistence(unpublished_pristine=True)
        mem.regions['n0']['data'][64] ^= 1
        with self.assertRaisesRegex(ValueError, 'prior published output changed'):
            mem.check_coexistence()

    def test_only_known_implicit_dense_wire_can_omit_full_mask(self):
        for beat, accepted in ((e.numeric.model.down.WriteBeat((1,) * 16, True), True),
                               (SimpleNamespace(words=(1,) * 16, last=True), False),
                               (SimpleNamespace(words=(1,) * 16, last=True, mask=(1 << 32) - 1), False)):
            f, mem, _ = setup()
            address = f.specs['n0'][0]
            command = e.numeric.model.WriteCommand(address, 1, 12)
            mem.write_event('command', command)
            if accepted:
                mem.write_event('data', beat)
                with self.assertRaisesRegex(ValueError, 'read before ACK'):
                    mem.read64(address)
                mem.write_event('ack', e.numeric.model.WriteAck(12, nbytes=64))
                self.assertEqual(mem.regions['n0']['acked'], {address})
            else:
                with self.assertRaisesRegex(ValueError, 'mask/last/extent'):
                    mem.write_event('data', beat)
                self.assertEqual(mem.regions['n0']['written'], set())

    def test_ack_identity_extent_and_coverage_are_not_command_buckets(self):
        for ack in (e.numeric.model.WriteAck(13, nbytes=64),
                    e.numeric.model.WriteAck(12, error=True, nbytes=64),
                    e.numeric.model.WriteAck(12, nbytes=128)):
            f, mem, _ = setup()
            address = f.specs['n0'][0]
            mem.write_event('command', e.numeric.model.WriteCommand(address, 1, 12))
            mem.write_event('data', e.numeric.model.down.WriteBeat((1,) * 16, True))
            with self.assertRaisesRegex(ValueError, 'ACK tag/status/byte fence'):
                mem.write_event('ack', ack)
            self.assertEqual(mem.regions['n0']['acked'], set())
            self.assertFalse(mem.regions['n0']['published'])
            self.assertIsNotNone(mem.pending)

    def test_address_reservation_virtual_and_readonly_boundaries(self):
        f, mem, _ = setup()
        with self.assertRaisesRegex(ValueError, 'readonly input provider'):
            p.PhysicalMemory(f, {'n0': lambda _: bytes(64)})
        with self.assertRaisesRegex(ValueError, 'immutable/published'):
            mem.write_event('command', e.numeric.model.WriteCommand(f.specs['x'][0], 1, 1))
        w = f.allocations['wq']
        with self.assertRaisesRegex(ValueError, 'reservation guard'):
            mem.read64(w.address + w.storage_bytes)
        with self.assertRaisesRegex(ValueError, 'virtual allocation'):
            mem.read64(f.specs['scores'][0])
        with self.assertRaisesRegex(ValueError, 'unaligned'):
            mem.read64(f.specs['x'][0] + 4)
        self.assertEqual(mem.region(f.specs['cache_k'][0])[0], 'kv')
        self.assertEqual(mem.region(f.specs['cache_v'][0])[0], 'kv')

    def test_prefix_does_not_accept_copied_job_or_busy_matrix(self):
        from dataclasses import replace
        _, _, x = setup()
        job = x.advance_to_request()['ordinary_request']
        with self.assertRaisesRegex(ValueError, 'original public job object'):
            x.prefix_edge(job=replace(job))
        self.assertEqual(x.host.jobs, 0)
        x.owner.state = 'wait'
        with self.assertRaisesRegex(ValueError, 'Matrix obligations'):
            x.prefix_edge(job=job)
        self.assertEqual(x.prefix_jobs, 0)

    def test_prefix_rejects_disconnected_metadata_map_before_owner(self):
        f, memory, x = setup()
        x.frontend.port.memory = f.memory
        with self.assertRaisesRegex(ValueError, 'identical physical map'):
            p.execute_public_prefix(x, memory, None, ROOT / 'work/unused_prefix_path')
        self.assertEqual(x.host.jobs, 0)
        self.assertEqual(x.prefix_jobs, 0)

    def test_public_prefix_abort_waits_for_accepted_read_and_never_publishes(self):
        _, memory, x = setup()
        job = x.advance_to_request()['ordinary_request']
        self.assertTrue(x.prefix_edge(job=job)['job_fire'])
        edge = x.prefix_edge(memory_ready=True)
        self.assertTrue(edge['memory_fire'])
        request = edge['memory']
        x.prefix_edge(local_reset=True)
        for _ in range(4):
            self.assertFalse(x.prefix_edge()['response_fire'])
            self.assertEqual(x.host.state, 'waitDone')
            self.assertIsNone(x.ports()['completion'])
        response = MemoryResponse(request.tag, memory.read_bytes64(request.address))
        self.assertTrue(x.prefix_edge(memory_response=response)['memory_response_fire'])
        edge = x.prefix_edge()
        self.assertTrue(edge['response_fire'])
        self.assertIsNotNone(edge['response'].status)
        self.assertEqual(x.host.published, [])
        self.assertEqual(x.host.completed, 0)
        self.assertTrue(x.reset_required())
        self.assertEqual(x.prefix_results, 1)
        memory.check_coexistence(unpublished_pristine=True)


if __name__ == '__main__':
    unittest.main()
