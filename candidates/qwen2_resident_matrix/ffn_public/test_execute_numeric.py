"""Raw-public control and small real-arithmetic tests; no official inputs.

One real N160 Gate/Up/SiLU/drain window followed by abort is deliberately
incomplete FFN evidence. Ordinary Down uses M16/K256/N32 synthetic metadata
and accepted input writes. Full FFN success requires the separate frozen run.
"""
from array import array
from dataclasses import replace
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import execute_numeric as execution
from candidates.qwen2_resident_matrix.ffn_public import fixture, model

n = execution.numeric
WORK = ROOT / 'work/qwen2_ffn_public_execution_20261012'


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def owner_for(f, *, split=2560):
    region = f.config.regions[3]
    extent = f.specs['dst'][1][1] // 32 * 16384 if split == 128 else region.limit - region.base
    workspace = n.model.PrefixWorkspace(region.base, extent,
                                        f.config.epoch + 1, split)
    return n.model.FfnDrainOwnerModel(workspace, enable_ffn_window=True,
        enable_ffn_tiles=True, enable_ffn_drain=True)


def make_execution(f=None, *, split=2560):
    f = f or fixture.make_ffn4_fixture()
    owner = owner_for(f, split=split)
    x = execution.PublicExecution(model.PublicFrontend(f.memory, f.config), owner,
                                  n.CappedTrace(), time.monotonic() + 90)
    return f, x


class SyntheticDownMemory:
    """Known input words, stored by original physical write/ACK primitives."""
    def __init__(self, job):
        self.job = job
        self.act = n.drain_check.DestinationMemory(job.m, base=job.a, width=job.k)
        for index, address in enumerate(range(job.a, job.a + self.act.extent, 1024)):
            beats = min(16, (job.a + self.act.extent - address) // 64)
            command = n.model.WriteCommand(address, beats, index)
            self.act.accept_command(command)
            for beat in range(beats):
                self.act.accept_data(n.model.WriteBeat((bits(1.0),) * 16, beat + 1 == beats))
            self.act.accept_ack(n.model.WriteAck(command.tag, nbytes=beats * 64))

    def read64(self, address):
        j = self.job
        if j.a <= address and address + 64 <= j.a + self.act.extent:
            assert self.act.pending is None and self.act.ack_bytes == self.act.extent
            assert address in self.act.write_addresses
            return 'act', struct.unpack_from('<16I', self.act.data, 64 + address - j.a)
        if j.b <= address and address + 64 <= j.b + j.k * j.n * 2:
            return 'down_weight', (0x3f00,) * 32
        raise ValueError('unexpected synthetic physical input address')


class PublicControlTests(unittest.TestCase):
    def test_ordinary_outstanding_read_fault_reaches_host_without_counter_injection(self):
        _, x = make_execution(fixture.make_dense_fixture(), split=128)
        job = n.decode_job(x.advance_to_request()['ordinary_request'])
        x.ordinary_edge(job=job)
        accepted = None
        for _ in range(1000):
            edge = x.ordinary_edge()
            if edge.get('read_command_fire'):
                accepted = edge['read_command']
                break
        self.assertIsNotNone(accepted)
        x.ordinary_edge(local_reset=True)
        self.assertTrue(x.ports()['reset_required'])
        self.assertIsNotNone(x.owner.read_active)
        self.assertIsNone(x.ports()['completion'])
        for _ in range(3):
            x.ordinary_edge()
            self.assertIsNone(x.ports()['completion'])
        edge = x.ordinary_edge(read_beat=n.model.ReadBeat(accepted.tag, (0,) * 16, True))
        self.assertTrue(edge['read_fire'])
        for _ in range(30):
            if x.down_terminal is not None:
                break
            x.ordinary_edge()
        self.assertIsNotNone(x.down_terminal)
        self.assertEqual(x.host.status, x.down_terminal[1])
        self.assertTrue(x.host.poison)
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.host.published, [])
        self.assertEqual((x.host.useful, x.host.executed, x.host.written), (0, 0, 0))
        self.assertEqual(x.counts['owner_result_fire'], 1)

    def test_ordinary_job_mutation_rejected_before_owner_edge(self):
        _, x = make_execution(fixture.make_dense_fixture(), split=128)
        job = n.decode_job(x.advance_to_request()['ordinary_request'])
        clock = x.owner.clock
        with self.assertRaisesRegex(ValueError, 'differs from public decoded'):
            x.ordinary_edge(job=replace(job, tag=job.tag + 1))
        self.assertEqual(x.owner.clock, clock)
        self.assertEqual(x.counts['request_fire'], 0)
        self.assertEqual(x.host.state, 'issue')

    def test_same_edge_reset_does_not_invent_ordinary_admission(self):
        _, x = make_execution(fixture.make_dense_fixture(), split=128)
        job = n.decode_job(x.advance_to_request()['ordinary_request'])
        clock = x.owner.clock
        edge = x.ordinary_edge(job=job, local_reset=True)
        self.assertFalse(edge['job_ready'])
        self.assertEqual(x.owner.clock, clock + 1)
        self.assertEqual(x.counts['request_fire'], 0)
        self.assertEqual(x.host.jobs, 0)
        self.assertIsNone(x.down_job)
        self.assertTrue(x.ports()['reset_required'])

    def test_raw_public_group_is_original_request_and_ports_are_read_free(self):
        f, x = make_execution(fixture.make_ffn4_fixture(epoch=39))
        h = x.start_group()
        self.assertIs(h.call, x.host.group)
        self.assertIs(execution.public_group, model.group)
        self.assertIs(type(x.host), model.group.HostControl)
        self.assertIs(type(h.call), model.group.GroupRequest)
        self.assertIs(type(h.c), n.group.ResidentCoordinator)
        self.assertIsNot(n.group, model.group)
        # The coordinator constructs downstream dataclasses in the module
        # used by every unchanged numeric helper's equality checks. Frontend
        # Rejected exceptions stay in the public Host module exclusively.
        self.assertIs(n.execute_silu.__globals__['group'], n.group)
        self.assertIs(n.execute_window.__globals__['group'], n.group)
        self.assertIs(n.execute_drain.__globals__['group'], n.group)
        self.assertEqual([h.call.gate.tag, h.call.up.tag, h.call.act.tag],
                         [(39 << 16) + i for i in range(3)])
        self.assertNotEqual(h.call.identity, n.IDENTITY)
        self.assertEqual(h.call.gate.a, f.specs['n1'][0])
        self.assertEqual(x.host.state, 'waitDone')
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.counts['request_fire'], 1)
        reads = tuple(f.memory.reads)
        for _ in range(10):
            self.assertIsNone(x.ports()['completion'])
        self.assertEqual(tuple(f.memory.reads), reads)

    def test_accepted_read_fault_drains_before_real_host_error(self):
        _, x = make_execution()
        h = x.start_group()
        q = h.next_request('window_request')
        h.tick(window=n.model.FfnWindowRequest(n.decode_job(q.job), q.identity,
                                             q.ng, q.cols, q.slot, q.reuse_a))
        accepted = None
        for _ in range(1000):
            edge, _ = h.tick()
            if edge.get('read_command_fire'):
                accepted = edge['read_command']
                break
        self.assertIsNotNone(accepted)
        x.completion_ready = True
        h.tick(local_reset=True, allow_fault=True)
        self.assertTrue(x.ports()['reset_required'])
        self.assertIsNotNone(x.owner.read_active)
        self.assertIsNone(x.ports()['completion'])
        self.assertEqual(x.host.events, {0})
        for _ in range(3):
            h.tick(allow_fault=True)
            self.assertIsNone(x.ports()['completion'])
        edge, _ = h.tick(read_beat=n.model.ReadBeat(accepted.tag, (0,) * 16, True), allow_fault=True)
        self.assertTrue(edge['read_fire'])
        x.completion_ready = False
        for _ in range(30):
            h.tick(allow_fault=True)
            if h.terminal is not None:
                break
        self.assertIsNotNone(h.terminal)
        self.assertIsNotNone(h.terminal.status)
        self.assertEqual(x.host.status, 'Protocol')
        self.assertTrue(x.host.poison)
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.host.published, [])
        self.assertEqual(x.host.completed, 0)
        self.assertEqual(x.counts['owner_result_fire'], 1)
        self.assertEqual(x.counts['completion_fire'], 0)
        self.assertFalse(x.frontend.launch(x.host))


class SyntheticPublicArithmeticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WORK.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix='public_numeric_', dir=WORK)
        cls.out = Path(cls.temp.name)
        pins = n.drain_check.load_pins(check_provenance=False)
        cls.lib, cls.compile = n.drain_check.build_library(cls.out, pins)
        n.configure_down_library(cls.lib)
        cls.arithmetic_hashes = {str(path): n.file_sha(path) for path in (
            n.TASK.parent / 'transposed_down/numeric_smoke.cpp',
            n.TASK.parent / 'ffn_window/numeric_recipe.cpp',
            n.TASK.parent / 'ffn_tiles/silu_recipe.cpp')}

    @classmethod
    def tearDownClass(cls):
        try:
            for path, digest in cls.arithmetic_hashes.items():
                assert n.file_sha(Path(path)) == digest
        finally:
            cls.temp.cleanup()

    def setUp(self):
        self.assertEqual(self.lib.td_reset(), 0)
        self.assertEqual(self.lib.sf_reset(), 0)

    def case_dir(self, name):
        out = self.out / name
        out.mkdir()
        return out

    def test_one_real_public_window_then_abort_never_publishes_success(self):
        _, x = make_execution()
        h = x.start_group()
        inputs = {'n1': array('I', [0]) * (128 * n.K),
                  'gate_weight': array('H', [0]) * (n.K * n.WIDTH),
                  'up_weight': array('H', [0]) * (n.K * n.WIDTH),
                  'down_weight': array('H', [0]) * (n.K * n.WIDTH)}
        for row in range(16):
            inputs['n1'][row * n.K + 17] = bits((row + 1) / 16)
        for col in range(160):
            inputs['gate_weight'][col * n.K + 17] = 0x3f00
            inputs['up_weight'][col * n.K + 17] = 0x3f80
        memory = n.Memory(inputs, 16)
        outputs = {role: array('I', [n.drain_check.SENTINEL_WORD]) * (16 * n.WIDTH)
                   for role in ('gate', 'up')}
        x.completion_ready = x.result_ready = True
        report = execution.execute_windows(x, self.lib, memory, outputs,
                                            self.case_dir('one_window_abort'), window_limit=1)
        self.assertEqual(report['partial_synthetic_windows'], 1)
        self.assertEqual(memory.act.ack_bytes, 16 * 160 * 4)
        self.assertEqual(report['windows'][0]['drain']['accepted']['held_final_ack_ticks'], 3)
        self.assertEqual(x.owner.a_fences, 1)
        self.assertEqual(x.counts['completion_fire'], 0)
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.host.state, 'waitDone')
        self.assertEqual(h.c.state, 'gateFlush')
        self.assertIsNotNone(x.owner.lease)
        x.completion_ready = x.result_ready = False
        h.tick(local_reset=True, allow_fault=True)
        for _ in range(30):
            h.tick(allow_fault=True)
            if h.terminal is not None:
                break
        self.assertIsNotNone(h.terminal)
        self.assertEqual(h.terminal.write_bytes, memory.act.ack_bytes)
        self.assertEqual(h.terminal.useful_macs,
                         sum(r['useful_macs'] for r in h.window_reports))
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.host.published, [])
        self.assertTrue(x.host.poison)
        self.assertEqual(x.host.completed, 0)
        self.assertTrue(memory.check_virtual()['unchanged'])
        # Inspect synthetic results only after the actual partial run's error
        # terminal. There is no fabricated success for the other 55 windows.
        for row in range(16):
            for col in range(160):
                self.assertEqual(outputs['gate'][row * n.WIDTH + col], bits((row + 1) / 32))
                self.assertEqual(outputs['up'][row * n.WIDTH + col], bits((row + 1) / 16))

    def run_tiny_down(self, name, *, accept_terminal=True):
        f, x = make_execution(fixture.make_dense_fixture(rows=16, k=256, n=32), split=128)
        ports = x.advance_to_request()
        self.assertIsNone(ports['group_request'])
        job = n.decode_job(ports['ordinary_request'])
        memory = SyntheticDownMemory(job)
        clock_before = x.owner.clock
        x.completion_ready = x.result_ready = True
        acks, held_final_ack_edges = [], []

        def actual_owner_edge(**inputs):
            command = x.owner.accepted_write
            final_ack_pending = (x.owner.write_state == 'ack' and command is not None and
                job.dst <= command.address < job.dst + job.write_bytes and
                x.owner.write_bytes + command.beats * 64 == job.write_bytes)
            if final_ack_pending:
                self.assertEqual(x.host.state, 'waitDone')
                self.assertIsNone(x.ports()['completion'])
                self.assertEqual(x.counts['owner_result_fire'], 0)
                if 'write_ack' not in inputs:
                    held_final_ack_edges.append(x.owner.clock)
            edge = x.ordinary_edge(**inputs)
            if edge.get('write_ack_fire'):
                acks.append(inputs['write_ack'])
            if final_ack_pending:
                self.assertEqual(x.host.state, 'waitDone')
                self.assertIsNone(x.ports()['completion'])
            return edge

        report, actual = execution.down_driver.execute_down(n.model, x.owner, self.lib,
            memory, job, self.case_dir(name), x.deadline, n.CappedTrace(),
            synthetic_geometry=True, owner_tick=actual_owner_edge)
        self.assertEqual(x.owner.clock - clock_before, x.counts['ordinary_owner_edges'])
        self.assertEqual(x.counts['ordinary_owner_edges'], report['protocol_model_ticks'])
        self.assertEqual(x.counts['request_fire'], 1)
        self.assertEqual(x.counts['owner_result_fire'], 0)
        self.assertEqual(x.counts['completion_fire'], 0)
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.host.state, 'waitDone')
        self.assertEqual(report['final_ack_fence']['held_ticks'], 5)
        self.assertEqual(len(held_final_ack_edges), 5)
        self.assertEqual(x.down_terminal_tick, report['owner_completion_tick'])
        self.assertEqual(tuple(actual), (bits(128.0),) * (16 * 32))
        x.completion_ready = x.result_ready = False
        if accept_terminal:
            x.accept_down_terminal(report)
            self.assertEqual(x.counts['owner_result_fire'], 1)
            self.assertEqual(x.host.events, {0})
            self.assertEqual(x.host.written, report['physical_traffic']['down_ack_bytes'])
            self.assertEqual(x.host.useful, report['useful_macs'])
            self.assertEqual(x.host.executed, report['executed_macs'])
        return x, report, acks[-1]

    def test_real_tiny_down_one_callback_per_edge_and_held_host_completion(self):
        x, report, _ = self.run_tiny_down('tiny_down_success')
        x.publish_completions((0,), stall_edges=4)
        result = x.finish(stall_edges=4)
        self.assertEqual(x.host.events, {0, 1})
        self.assertEqual(result['completed'], 1)
        self.assertEqual(result['jobs'], 1)
        self.assertEqual(result['write_bytes'], report['ddr']['ack_bytes'])
        self.assertEqual(x.counts['completion_backpressure_edges'], 4)
        self.assertEqual(x.counts['result_backpressure_edges'], 4)

    def test_host_raw_reset_revokes_held_ordinary_success_on_ready_edge(self):
        x, _, _ = self.run_tiny_down('tiny_down_held_reset')
        self.assertIsNotNone(x.ports()['completion'])
        x.completion_ready = True
        x.idle_edge(local_reset=True)
        self.assertTrue(x.ports()['reset_required'])
        self.assertEqual(x.counts['completion_fire'], 0)
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.host.published, [])
        self.assertEqual(x.host.completed, 0)
        self.assertEqual(x.host.status, 'Protocol')
        self.assertTrue(x.host.poison)
        self.assertEqual(x.ports()['completion'].status, 'Protocol')
        self.assertTrue(x.completion_ready)
        x.idle_edge()
        self.assertTrue(x.last_host_edge['completion_fire'])
        self.assertEqual(x.last_host_edge['completion'].status, 'Protocol')
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.host.completed, 0)

    def test_duplicate_ack_revokes_only_unaccepted_ordinary_success(self):
        x, _, ack = self.run_tiny_down('tiny_down_held_duplicate_ack')
        x.completion_ready = True
        x.idle_edge(write_ack=ack)
        self.assertTrue(x.ports()['reset_required'])
        self.assertFalse(x.last_host_edge['completion_fire'])
        self.assertEqual(x.host.status, 'Protocol')
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.host.published, [])
        self.assertEqual(x.host.completed, 0)

    def test_wrong_terminal_tag_still_faults_after_real_down_ack(self):
        x, report, _ = self.run_tiny_down('tiny_down_wrong_terminal_tag', accept_terminal=False)
        tag, status, written = x.down_terminal
        corrupted = n.group.OwnerResult(tag + 1, status, written,
            report['protocol_model_ticks'], report['useful_macs'], report['executed_macs'])
        x.idle_edge(owner_result=corrupted)
        self.assertTrue(x.last_host_edge['owner_result_fire'])
        self.assertEqual(x.host.status, 'Protocol')
        self.assertTrue(x.host.poison)
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.host.published, [])
        self.assertEqual(x.host.completed, 0)

    def test_raw_reset_on_actual_ordinary_terminal_edge_becomes_protocol(self):
        x, report, _ = self.run_tiny_down('tiny_down_terminal_reset', accept_terminal=False)
        terminal = n.group.OwnerResult(*x.down_terminal, report['protocol_model_ticks'],
                                       report['useful_macs'], report['executed_macs'])
        x.idle_edge(owner_result=terminal, local_reset=True)
        self.assertTrue(x.last_host_edge['owner_result_fire'])
        self.assertEqual(x.host.status, 'Protocol')
        self.assertTrue(x.host.poison)
        self.assertEqual(x.host.events, {0})
        self.assertEqual(x.host.published, [])
        self.assertEqual(x.host.completed, 0)

    def test_late_duplicate_ack_preserves_accepted_completion_and_result(self):
        x, _, ack = self.run_tiny_down('tiny_down_after_completion_duplicate_ack')
        x.publish_completions((0,), stall_edges=0)
        self.assertEqual(x.counts['completion_fire'], 1)
        held = dict(x.ports()['launch_result'])
        published = list(x.host.published)
        self.assertIsNone(held['status'])
        self.assertEqual(held['completed'], 1)
        x.idle_edge(write_ack=ack)
        self.assertTrue(x.ports()['reset_required'])
        self.assertEqual(x.ports()['launch_result'], held)
        self.assertEqual(x.host.events, {0, 1})
        self.assertEqual(x.host.published, published)
        self.assertEqual(x.host.completed, 1)
        x.result_ready = True
        x.idle_edge()
        self.assertTrue(x.last_host_edge['result_fire'])
        self.assertEqual(x.launch_result, held)
        self.assertFalse(x.host.launch(range(x.frontend.config.command.count),
            x.frontend.reader, {}, epoch=x.frontend.config.epoch,
            reset_required=x.reset_required(), frontend=x.frontend))
        # This is global quarantine of a late response. It does not establish
        # that an untagged external epoch can be identified after reset.


if __name__ == '__main__':
    unittest.main()
