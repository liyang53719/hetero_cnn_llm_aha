"""Small synthetic integration and negative controls; no frozen raw captures."""
from array import array
import ctypes as C
from dataclasses import replace
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('fullgroup_tests_check', HERE / 'check_numeric.py')
check = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check
spec.loader.exec_module(check)


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


class LightweightControls(unittest.TestCase):
    def test_decoded_job_all_fields_exact(self):
        request = check.request_for(128)
        self.assertTrue(request.valid())
        for job in (request.gate, request.up, request.act):
            decoded = check.decode_job(job)
            for key, value in check.asdict(job).items():
                self.assertEqual(getattr(decoded, key), value)
        self.assertFalse(replace(request, up=replace(request.up, a=request.up.a + 64)).valid())
        self.assertFalse(replace(request, act=replace(request.act, output_bf16=True)).valid())

    def test_physical_write_guards_ack_mask_boundary(self):
        m = check.FullDestination(16)
        with self.assertRaisesRegex(ValueError, '1KiB'):
            m.accept_command(check.model.WriteCommand(m.base + 960, 2, 0))
        cmd = check.model.WriteCommand(m.base, 1, 7)
        m.accept_command(cmd)
        with self.assertRaisesRegex(ValueError, 'mask'):
            m.accept_data(check.model.WriteBeat((0,) * 16, True, 0))
        m.accept_data(check.model.WriteBeat((0,) * 16, True))
        with self.assertRaisesRegex(ValueError, 'ACK'):
            m.accept_ack(check.model.WriteAck(8, False, 64))
        with self.assertRaisesRegex(ValueError, 'before all'):
            m.read64(m.base)
        m.accept_ack(check.model.WriteAck(7, False, 64))
        with self.assertRaisesRegex(ValueError, 'final ACK'):
            m.validate_full()

    def test_coordinated_reset_includes_all_backends(self):
        c = check.group.ResidentCoordinator()
        with self.assertRaisesRegex(ValueError, 'all retained'):
            c.tick(coordinated_reset={'coordinator'})
        c.tick(coordinated_reset=check.group.RESET_DOMAIN)
        self.assertEqual(c.state, 'idle')

    def test_bounded_trace_hashes_omitted_records(self):
        t = check.CappedTrace(cap=0)
        t.write(b'abc'); t.write(b'def')
        self.assertEqual(t.report()['sha256'], check.sha(b'abcdef'))
        self.assertEqual(t.report()['persisted_prefix_bytes'], 0)


    def test_trace_prefix_truncation_is_sticky(self):
        with tempfile.TemporaryDirectory(dir=check.ROOT / 'work/qwen2_ffn_fullgroup_20261012') as tmp:
            path = Path(tmp) / 'prefix.bin'
            t = check.CappedTrace(path, cap=10)
            for raw in (b'12345678', b'abc', b'x'):
                t.write(raw)
            report = t.report(); t.close()
            self.assertEqual(path.read_bytes(), b'12345678')
            self.assertEqual(report['sha256'], check.sha(b'12345678abcx'))

    def test_coordinator_abort_drains_accepted_read_and_error_terminal(self):
        owner = check.model.FfnDrainOwnerModel(check.model.PrefixWorkspace(check.PREFIX_BASE,
            48 * 16384, check.IDENTITY, 2560), enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
        h = check.Coupled(owner, check.request_for(16), check.CappedTrace(), time.monotonic() + 10)
        h.tick(start=True)
        q = h.next_request('window_request')
        h.tick(window=check.model.FfnWindowRequest(check.decode_job(q.job), q.identity, q.ng, q.cols, q.slot, q.reuse_a))
        accepted = None
        for _ in range(1000):
            edge, _ = h.tick()
            if edge.get('read_command_fire'):
                accepted = edge['read_command']; break
        self.assertIsNotNone(accepted)
        self.assertIsNotNone(owner.read_active)
        # Fault the coordinator alone; the next coupled edge must propagate
        # its sticky backend_abort to the owner while preserving obligations.
        h.c.tick(local_reset=True, services=h.services())
        h.tick(allow_fault=True)
        self.assertIsNotNone(owner.error)
        self.assertIsNotNone(owner.read_active)
        self.assertIsNone(owner.lease)
        edge, _ = h.tick(read_beat=check.model.ReadBeat(accepted.tag, (0,) * 16, True), allow_fault=True)
        self.assertTrue(edge['read_fire'])
        for _ in range(20):
            h.tick(group_result_ready=True, allow_fault=True)
            if h.terminal is not None:
                break
        self.assertIsNotNone(h.terminal)
        self.assertIsNotNone(h.terminal.status)
        self.assertEqual((owner.state, h.c.state), ('locked', 'locked'))
        self.assertFalse(h.services().window_busy)
        self.assertEqual(h.counts['window_result_fire'], 1)
        self.assertEqual(h.terminal.write_bytes, 0)
        self.assertEqual(h.terminal.useful_macs, 0)


class SyntheticIntegration(unittest.TestCase):
    def test_two_real_windows_reuse_and_fault_reset(self):
        # Exact production dimensions/control, only two windows and sparse
        # synthetic inputs. No saved producer output and no altered models.
        with tempfile.TemporaryDirectory(dir=check.ROOT / 'work/qwen2_ffn_fullgroup_20261012', prefix='synthetic_') as tmp:
            out = Path(tmp)
            pins = check.drain_check.load_pins(check_provenance=False)
            lib, _ = check.drain_check.build_library(out, pins)
            inputs = {'n1': array('I', [0]) * (128 * check.K),
                      'gate_weight': array('H', [0]) * (check.K * check.WIDTH),
                      'up_weight': array('H', [0]) * (check.K * check.WIDTH),
                      'down_weight': array('H', [0]) * (check.K * check.WIDTH)}
            for m in range(16):
                inputs['n1'][m * check.K + 17] = bits((m + 1) / 16)
            for n in range(320):
                inputs['gate_weight'][n * check.K + 17] = 0x3f00
                inputs['up_weight'][n * check.K + 17] = 0x3f80
            memory = check.Memory(inputs, 16)
            owner, h, outputs, report = check.execute_group(16, lib, memory, out, time.monotonic() + 90, window_limit=2)
            self.assertEqual(owner.a_fences, 1)
            self.assertEqual(h.c.state, 'gateFlush')
            self.assertIsNotNone(owner.lease)
            self.assertEqual(report['coordinator']['accepted']['window_result_fire'], 4)
            self.assertEqual(report['coordinator']['accepted']['drain_result_fire'], 2)
            self.assertEqual(sum(w[r]['accepted'].get('a_reads', 0) for w in report['windows'] for r in ('gate', 'up')), 16 * check.K // 16)
            for w in report['windows']:
                self.assertEqual(w['drain']['accepted']['held_final_ack_ticks'], 3)
            # Independent reference invoked only after all synthetic writes and
            # ACKs for the selected two windows, never used to populate SRAM.
            gate = (C.c_uint32 * (16 * 320))()
            up = (C.c_uint32 * (16 * 320))()
            ref = (C.c_uint32 * (16 * 320))()
            for m in range(16):
                for n in range(320):
                    gate[m * 320 + n] = bits((m + 1) / 32)
                    up[m * 320 + n] = bits((m + 1) / 16)
                    self.assertEqual(outputs['gate'][m * check.WIDTH + n], gate[m * 320 + n])
                    self.assertEqual(outputs['up'][m * check.WIDTH + n], up[m * 320 + n])
            self.assertEqual(lib.sf_reference(gate, up, ref, len(ref)), 0)
            for m in range(16):
                for n in range(320):
                    offset = 64 + (m * check.WIDTH + n) * 4
                    self.assertEqual(struct.unpack_from('<I', memory.act.data, offset)[0], ref[m * 320 + n])
                first = 64 + (m * check.WIDTH + 320) * 4
                end = 64 + (m + 1) * check.WIDTH * 4
                self.assertEqual(memory.act.data[first:end], memory.act.initial[first:end])
            self.assertTrue(memory.check_virtual()['unchanged'])
            # Third pair reaches an actual held SiLU SRAM response. A
            # coordinator-only fault must drain/discard it before arithmetic.
            check.execute_window(h, lib, memory, 320, 'gate')
            check.execute_window(h, lib, memory, 320, 'up')
            q = h.next_request('silu_request')
            h.tick(silu_accept=True); h.silu_busy = True
            port = check.CoupledTilePort(h)
            read = check.model.Read(0, q.identity, q.ng, 0)
            self.assertTrue(port.tick(read=read, response_ready=False)['read_fire'])
            for _ in range(3):
                port.tick(response_ready=False)
            self.assertIsNotNone(owner.tiles.response)
            h.c.tick(local_reset=True, services=h.services())
            with self.assertRaisesRegex(ValueError, 'coupled backend fault'):
                port.tick(response_ready=True)
            self.assertIsNone(owner.tiles.response)
            self.assertTrue(port.poison)
            self.assertFalse(h.silu_busy)
            for _ in range(20):
                h.tick(group_result_ready=True, allow_fault=True)
                if h.terminal is not None:
                    break
            self.assertIsNotNone(h.terminal)
            self.assertIsNotNone(h.terminal.status)
            h.tick(local_reset=True, allow_fault=True)
            self.assertTrue(owner.ports()['reset_required'])
            self.assertIsNone(owner.lease)
            original_banks = (owner.a_banks, owner.b_banks)
            owner.tick(coordinated_reset=True)
            self.assertEqual(lib.td_reset(), 0)
            self.assertEqual(lib.sf_reset(), 0)
            h.c.tick(coordinated_reset=check.group.RESET_DOMAIN)
            self.assertEqual((owner.a_banks, owner.b_banks), original_banks)
            self.assertFalse(owner.ports()['reset_required'])
            self.assertEqual(h.c.state, 'idle')
            self.assertFalse(owner.tiles.leased)
            self.assertFalse(check.request_for(16).gate.activation_bf16)


if __name__ == '__main__':
    unittest.main()
