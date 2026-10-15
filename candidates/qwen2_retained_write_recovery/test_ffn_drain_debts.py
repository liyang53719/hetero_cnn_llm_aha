"""Actual FfnDrain owner/writer protocol at an initialized final-ACK boundary.

The real owner, ordinary Down wire, and PhysicalMemory process synthetic zero
payloads (2048 B, 16 bursts). Matrix execution, job launch, the full M128/K8960
schedule, public Host retirement, and RTL are deliberately outside this test.
"""
import copy
from dataclasses import replace
from types import SimpleNamespace as NS
import unittest

from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory, execution
from .debts import corrected_debts, retained_write_evidence


# Use the exact dynamically loaded owner/wire family used by public execution.
model = execution.numeric.model
wire = model.down


def final_ack_fixture():
    allocation = NS(address=4096, storage_bytes=2048, reserved_bytes=2048,
                    dtype=7, readonly=False, virtual=False)
    fixture = NS(validate_spans=lambda: None, allocations={'down': allocation},
                 config=NS(command=NS(base=8192), descriptor=NS(base=8256)),
                 memory=NS(mappings={8192: bytes(64), 8256: bytes(64)}))
    physical = PhysicalMemory(fixture, {})
    owner = model.FfnDrainOwnerModel(enable_ffn_drain=True,
                                    enable_ffn_window=True, enable_ffn_tiles=True)
    for index in range(16):
        command = wire.WriteCommand(4096 + 128 * index, 2, (123 << 32) | index)
        physical.write_event('command', command)
        physical.write_event('data', wire.WriteBeat((0,) * 16, False))
        physical.write_event('data', wire.WriteBeat((0,) * 16, True))
        if index < 15:
            physical.write_event('ack', wire.WriteAck(command.tag, nbytes=128))

    # Initialize a consistent final-row boundary; no numerical job is executed.
    owner.state, owner.write_state = 'execute', 'ack'
    owner.job = wire.Job(m=16, k=32, n=32, tag=123, dst=4096, write_bytes=2048)
    owner.accepted_write = command
    owner.write_index, owner.write_row_beat, owner.write_row = 2, 0, 15
    owner.write_sequence, owner.write_bytes = 15, 1920
    owner.n_base, owner.contexts = 0, 1
    owner.issue_k = owner.load_k = 32
    owner.group_started = owner.group_done = True
    owner.group_accepted_steps = owner.accepted_steps = 32
    owner.results_received, owner.terminal_issued = 1, {0}
    owner.final_value = [[0] * 256 for _ in range(16)]
    return owner, physical, wire.WriteAck(command.tag, nbytes=128)


def retire_final_ack(owner, physical, ack):
    physical.write_event('ack', ack)
    edge = owner.tick(write_ack=ack, response_ready=False)
    assert edge['write_ack_fire'] and owner.state == 'finish'
    assert owner.tick(response_ready=True)['response_fire']
    assert owner.state == 'idle'


class FfnDrainRetainedWriteTests(unittest.TestCase):
    def test_real_owner_final_ack_held_response_then_idle(self):
        owner, physical, ack = final_ack_fixture()
        descriptor = owner.accepted_write
        self.assertIsInstance(owner, model.FfnDrainOwnerModel)
        self.assertIsInstance(owner, wire.DenseOwnerModel)
        self.assertIsNotNone(physical.pending)
        self.assertFalse(retained_write_evidence(owner, physical)['retired'])

        physical.write_event('ack', ack)
        # Physical acceptance alone cannot retire an owner's pending ACK.
        self.assertFalse(retained_write_evidence(owner, physical)['retired'])
        edge = owner.tick(write_ack=ack, response_ready=False)
        self.assertTrue(edge['write_ack_fire'])
        self.assertFalse(edge['response_fire'])
        self.assertEqual((owner.state, owner.write_state), ('finish', 'idle'))
        self.assertFalse(owner.drain_poison)
        self.assertEqual(owner.write_bytes, 2048)
        self.assertEqual(len(physical.regions['down']['records']), 16)
        for _ in range(3):
            self.assertFalse(retained_write_evidence(owner, physical)['retired'])
            self.assertFalse(owner.tick(response_ready=False)['response_fire'])

        self.assertTrue(owner.tick(response_ready=True)['response_fire'])
        self.assertEqual(owner.state, 'idle')
        before = copy.deepcopy(physical.regions)
        ports = owner.ports()
        corrected, evidence = corrected_debts({'accepted_write': True}, owner, physical)
        self.assertTrue(evidence['retired'])
        self.assertFalse(corrected['accepted_write'])
        self.assertIs(owner.accepted_write, descriptor)
        self.assertEqual(physical.regions, before)
        self.assertEqual(owner.ports(), ports)

    def test_missing_final_ack_keeps_both_obligations_live(self):
        owner, physical, _ = final_ack_fixture()
        for _ in range(3):
            edge = owner.tick(response_ready=True)
            self.assertFalse(edge['write_ack_fire'])
            self.assertFalse(edge['response_fire'])
            self.assertEqual((owner.state, owner.write_state), ('execute', 'ack'))
            self.assertIsNotNone(physical.pending)
            self.assertFalse(retained_write_evidence(owner, physical)['retired'])

    def test_real_physical_writer_rejects_invalid_ack(self):
        for changes in ({'tag': 0}, {'error': True}, {'nbytes': 64}, {'nbytes': None}):
            with self.subTest(changes=changes):
                owner, physical, ack = final_ack_fixture()
                before = copy.deepcopy(physical.regions)
                with self.assertRaises(ValueError):
                    physical.write_event('ack', replace(ack, **changes))
                self.assertIsNotNone(physical.pending)
                self.assertEqual(physical.regions, before)
                self.assertFalse(retained_write_evidence(owner, physical)['retired'])

    def test_prior_burst_coverage_is_required(self):
        for field in ('written', 'acked'):
            with self.subTest(field=field):
                owner, physical, ack = final_ack_fixture()
                retire_final_ack(owner, physical, ack)
                self.assertTrue(retained_write_evidence(owner, physical)['retired'])
                # The retained descriptor covers the last burst, not this one.
                physical.regions['down'][field].remove(4096)
                self.assertFalse(retained_write_evidence(owner, physical)['retired'])

    def test_every_other_debt_is_preserved(self):
        owner, physical, ack = final_ack_fixture()
        retire_final_ack(owner, physical, ack)
        original = {'accepted_write': True, 'owner_fifo': 3, 'owner_read': True,
                    'reset_required': True, 'unknown_future_debt': object()}
        corrected, evidence = corrected_debts(original, owner, physical)
        self.assertTrue(evidence['retired'])
        self.assertFalse(corrected['accepted_write'])
        self.assertTrue(original['accepted_write'])
        self.assertEqual(corrected.keys(), original.keys())
        for name, value in original.items():
            if name != 'accepted_write':
                self.assertIs(corrected[name], value)


if __name__ == '__main__':
    unittest.main()
