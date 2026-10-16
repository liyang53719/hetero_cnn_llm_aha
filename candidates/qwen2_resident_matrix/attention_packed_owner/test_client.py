"""Cold protocol tests; native ABI execution requires explicit --native arguments."""
from collections import Counter
from dataclasses import replace
import struct
import unittest

from ..ffn_attention.matrix_service import (
    MatrixDone, MatrixProtocolError, MatrixResult, MatrixValue,
    NormalGroup, NormalStep, require,
)
from ..ffn_public.prefix_arithmetic import ArithmeticFault
from .client import (
    PackedClient, PackedConsumerAck, PackedRequest, PackedResult, PackedRetired,
    PackedStepAccepted, PackedTag, PackedWriteAck, PackedWriteTag,
)


class _State:
    def __init__(self, service):
        self.service = service

    def matrix_state(self):
        s = self.service
        return ((4 if s.group is not None else 0) |
                (8 if s.result is not None else 0) |
                (256 if s.reset_required else 0))


class ScriptedService:
    """No arithmetic, native ABI, resource wrapper, or claimed native evidence."""
    def __init__(self):
        self.owner = object()
        self.mode, self.owner_tag = 'normal', 19
        self.epoch, self.ticket = 0, 0
        self.resource_address = 123456
        self.lib, self.counts = _State(self), Counter()
        self.group = self.result = self._done = None
        self.reset_required = self.end = False
        self.words = {0: 0x3f800000, 15 * 256 + 127: 0x7fc12345}
        self.steps = []

    def _check_owner(self, owner, mode):
        require(owner is self.owner and mode == self.mode, 'Matrix owner/resource mismatch')

    def _check_event(self, ticket=None, epoch=None):
        require(ticket is None or ticket == self.ticket, 'late Matrix group event')
        require(epoch is None or epoch == self.epoch, 'late Matrix reset epoch')

    def accept_group(self, owner, group):
        self._check_owner(owner, 'normal')
        require(type(group) is NormalGroup and group.profile == 2, 'exact profile2 group')
        if self.group is not None or self.reset_required:
            return False
        self.group = group
        self.ticket += 1
        self.end = False
        self.counts['normal_groups'] += 1
        return True

    def accept_step(self, owner, step):
        self._check_owner(owner, 'normal')
        require(type(step) is NormalStep, 'exact normal step type')
        if self.result is not None or self.reset_required:
            return False
        require(step.emit == step.last == step.finish, 'packed last-only output')
        self.steps.append(step)
        self.counts['normal_steps'] += 1
        if step.last:
            raw = bytearray(16384)
            for index, word in self.words.items():
                struct.pack_into('<I', raw, index * 4, word)
            self.result = MatrixResult(0, MatrixValue(raw), True, False, self.ticket, self.epoch)
            self.end = True
        return True

    @property
    def done(self):
        if self.group is not None and self.end and self.result is None and self._done is None:
            self._done = MatrixDone(self.group.tag, self.reset_required, self.ticket, self.epoch)
        return self._done

    def retire_result(self, owner, result):
        self._check_owner(owner, 'normal')
        require(result is self.result, 'original service held result required')
        self.result = None
        self.counts['normal_results'] += 1

    def retire_done(self, owner, done):
        self._check_owner(owner, 'normal')
        require(done is self.done and self.result is None, 'actual matching done required')
        self.group = self._done = None
        self.counts['normal_done'] += 1

    def abort(self, owner):
        self._check_owner(owner, 'normal')
        self.reset_required = True
        if self.group is not None:
            self.end = True
        self.counts['aborts'] += 1


def pv(index=0, steps=1, selected=((0, 0),)):
    return PackedRequest(0x24, (0x3f80,) * 16, (0x3f80,) * 256,
                         index == 0, index + 1 == steps, steps, 15,
                         selected if index + 1 == steps else ())


def deliver(client, request):
    require(client.tick(request=request)['request_fire'], 'test request admission')
    for _ in range(10):
        p = client.tick(result_ready=True)
        if p['result_fire']:
            return p['result']
    raise AssertionError('bounded scripted response timeout')


def finish(client, result):
    retired = deliver(client, PackedConsumerAck(result.tag))
    require(type(retired) is PackedRetired and not retired.error, 'retirement response')
    require(client.drained, 'retired client drain')
    return retired


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.service = ScriptedService()
        self.client = PackedClient(self.service, self.service.owner)

    def test_nonfinal_metadata_has_no_payload_or_service_retirement(self):
        first = deliver(self.client, pv(0, 3))
        self.assertIs(type(first), PackedStepAccepted)
        self.assertIsNone(first.value)
        self.assertEqual(first.index, 0)
        self.assertIsNone(self.service.result)
        self.assertEqual(self.service.counts['normal_results'], 0)
        second = deliver(self.client, pv(1, 3))
        self.assertEqual(first.tag, second.tag)
        result = deliver(self.client, pv(2, 3))
        self.assertIs(type(result), PackedResult)
        self.assertIs(self.service.result, result.service_result)
        self.assertEqual([(x.clear, x.last, x.emit) for x in self.service.steps],
                         [(True, False, False), (False, False, False), (False, True, True)])
        finish(self.client, result)

    def test_qk_eight_steps_enable_all_slices_and_select_wide_columns(self):
        for index in range(8):
            request = PackedRequest(0x23, (0x3f80,) * 16, (0x3f80,) * 256,
                index == 0, index == 7, 8, 255, ((0, 255),) if index == 7 else ())
            result = deliver(self.client, request)
            if index < 7:
                self.assertIs(type(result), PackedStepAccepted)
                self.assertIsNone(self.service.result)
        self.assertEqual(result.selected_words(), (0,))
        self.assertEqual(self.service.group.profile, 2)
        self.assertEqual(self.service.group.slice_mask, 255)
        self.assertEqual(self.service.counts['normal_steps'], 8)
        finish(self.client, result)

    def test_final_delivery_keeps_exact_service_payload_until_ack(self):
        result = deliver(self.client, pv())
        held = self.service.result
        self.assertIs(result.value, held.value)
        for _ in range(4):
            p = self.client.tick(result_ready=True)
            self.assertFalse(p['service_result_fire'])
            self.assertFalse(self.client.drained)
            self.assertIs(self.service.result, held)
        with self.assertRaisesRegex(MatrixProtocolError, 'before consumer ACK'):
            self.client.tick(request=pv())
        self.assertEqual(result.selected_words(), (0x3f800000,))
        self.assertFalse(result.error)
        finish(self.client, result)
        self.assertEqual(self.service.counts['normal_results'], 1)
        self.assertEqual(self.service.counts['normal_done'], 1)

    def test_consumer_ack_waits_both_ready_edges_and_returns_metadata(self):
        result = deliver(self.client, pv())
        self.assertTrue(self.client.tick(request=PackedConsumerAck(result.tag))['request_fire'])
        for _ in range(3):
            self.assertFalse(self.client.tick(service_result_ready=False)['service_result_fire'])
            self.assertIs(self.service.result, result.service_result)
        p = self.client.tick(service_done_ready=False)
        self.assertTrue(p['service_result_fire'])
        self.assertFalse(p['service_done_fire'])
        self.assertIsNone(self.service.result)
        self.assertFalse(self.client.tick(service_done_ready=False)['service_done_fire'])
        self.assertTrue(self.client.tick()['service_done_fire'])
        self.assertIs(type(self.client.ports()['result']), PackedRetired)
        self.assertFalse(self.client.drained)
        self.assertTrue(self.client.tick(result_ready=True)['result_fire'])
        self.assertTrue(self.client.drained)
        again = deliver(self.client, pv())
        self.assertNotEqual(result.tag, again.tag)
        finish(self.client, again)

    def test_selected_finite_only_and_exact_special_bits(self):
        result = deliver(self.client, pv())
        self.assertEqual(result.value[15][127], 0x7fc12345)
        self.assertEqual(result.selected_words(), (0x3f800000,))
        self.assertFalse(self.service.reset_required)
        finish(self.client, result)
        result = deliver(self.client, pv(selected=((15, 127),)))
        with self.assertRaises(ArithmeticFault):
            result.selected_words()
        self.assertFalse(result.error)
        self.assertIs(self.service.result, result.service_result)
        self.client.tick(abort=True, result_ready=True)
        self.client.tick(result_ready=True)
        self.assertTrue(self.client.drained)

    def test_tagged_write_debts_gate_retirement_and_reject_wrong_acks(self):
        result = deliver(self.client, pv())
        tag = PackedWriteTag(result.tag, 'scratch', 4096, 5, 9)
        self.client.register_write(tag)
        with self.assertRaises(MatrixProtocolError):
            self.client.register_write(tag)
        for bad in (replace(tag, address=4097), replace(tag, generation=6),
                    replace(tag, bank='foreign'), replace(tag, serial=10)):
            with self.assertRaises(MatrixProtocolError):
                self.client.commit_write(PackedWriteAck(bad))
            self.assertEqual(self.client.write_debts, 1)
        self.assertFalse(self.client.tick(request=PackedConsumerAck(result.tag))['request_fire'])
        self.assertIs(self.service.result, result.service_result)
        self.assertTrue(self.client.commit_write(PackedWriteAck(tag)))
        with self.assertRaises(MatrixProtocolError):
            self.client.commit_write(PackedWriteAck(tag))
        with self.assertRaises(MatrixProtocolError):
            self.client.register_write(tag)
        finish(self.client, result)

    def test_write_debts_are_bounded_metadata(self):
        result = deliver(self.client, pv())
        tags = [PackedWriteTag(result.tag, 'scratch', 4096 + i, 1, i)
                for i in range(self.client.MAX_WRITE_DEBTS)]
        for tag in tags:
            self.client.register_write(tag)
        with self.assertRaises(MatrixProtocolError):
            self.client.register_write(PackedWriteTag(result.tag, 'scratch', 4190, 1, 100))
        self.assertEqual(self.client.write_debts, 64)
        self.assertTrue(all(type(tag) is PackedWriteTag for tag in self.client._write_debts))
        for tag in reversed(tags):
            self.assertTrue(self.client.commit_write(PackedWriteAck(tag)))
        finish(self.client, result)

    def test_stale_foreign_and_noncanonical_tags_never_discharge(self):
        result = deliver(self.client, pv())
        for name in ('owner_tag', 'group', 'ticket', 'epoch'):
            foreign = replace(result.tag, **{name: getattr(result.tag, name) + 1})
            with self.assertRaisesRegex(MatrixProtocolError, 'stale or foreign'):
                self.client.tick(request=PackedConsumerAck(foreign))
            self.assertIs(self.service.result, result.service_result)
        for name in ('owner_tag', 'group', 'ticket', 'epoch'):
            with self.assertRaises(MatrixProtocolError):
                replace(result.tag, **{name: True})
        with self.assertRaises(MatrixProtocolError):
            PackedConsumerAck(tuple(result.tag.__dict__.values()))
        finish(self.client, result)
        fresh = deliver(self.client, pv())
        with self.assertRaises(MatrixProtocolError):
            self.client.tick(request=PackedConsumerAck(result.tag))
        finish(self.client, fresh)

    def test_foreign_done_rejected_without_retiring_group(self):
        result = deliver(self.client, pv())
        self.client.tick(request=PackedConsumerAck(result.tag))
        self.client.tick()
        done = self.service.done
        for name in ('tag', 'ticket', 'epoch'):
            with self.assertRaises(MatrixProtocolError):
                self.client.tick(done_override=replace(done, **{name: getattr(done, name) + 1}))
            self.assertIs(self.service.done, done)
            self.assertEqual(self.service.counts['normal_done'], 0)
        for noncanonical in (replace(done, tag=True), replace(done, error=0),
                             replace(done, ticket=True), replace(done, epoch=False)):
            with self.assertRaises(MatrixProtocolError):
                self.client.tick(done_override=noncanonical)
        self.assertTrue(self.client.tick()['service_done_fire'])
        self.client.tick(result_ready=True)
        self.assertTrue(self.client.drained)

    def test_abort_exposed_result_is_byte_stable_through_backpressure(self):
        self.client.tick(request=pv())
        while self.client.ports()['result'] is None:
            self.client.tick()
        visible = self.client.ports()['result']
        raw = visible.value.raw
        self.client.tick(abort=True, result_ready=False)
        for _ in range(3):
            self.assertIs(self.client.ports()['result'], visible)
            self.assertIs(self.service.result, visible.service_result)
            self.assertEqual(visible.value.raw, raw)
            self.assertFalse(visible.error)
            self.assertFalse(self.client.tick()['service_result_fire'])
        p = self.client.tick(result_ready=True, service_result_ready=False)
        self.assertTrue(p['result_fire'])
        self.assertIs(p['result'], visible)
        self.assertIs(self.service.result, visible.service_result)
        self.assertTrue(self.client.tick(result_ready=True)['service_result_fire'])
        self.assertTrue(self.client.tick(result_ready=True)['service_done_fire'])
        self.assertTrue(self.client.drained)
        self.assertTrue(self.client.poison)
        self.assertFalse(self.client.ports()['request_ready'])

    def test_abort_held_result_waits_accepted_write_and_never_publishes(self):
        result = deliver(self.client, pv())
        tag = PackedWriteTag(result.tag, 'scratch', 4096, 1, 1)
        self.client.register_write(tag)
        self.client.tick(abort=True, result_ready=True)
        for _ in range(3):
            self.assertFalse(self.client.tick(result_ready=True)['service_result_fire'])
            self.assertIs(self.service.result, result.service_result)
        self.assertFalse(self.client.commit_write(PackedWriteAck(tag)))
        self.assertTrue(self.client.tick(result_ready=True)['service_result_fire'])
        self.assertTrue(self.client.tick(result_ready=True)['service_done_fire'])
        self.assertTrue(self.client.drained)
        self.assertIsNone(self.client.ports()['result'])
        self.assertEqual(self.service.counts['aborts'], 1)

    def test_write_error_aborts_and_retains_other_debts(self):
        result = deliver(self.client, pv())
        one = PackedWriteTag(result.tag, 'scratch', 4096, 1, 1)
        two = replace(one, address=4097, serial=2)
        self.client.register_write(one)
        self.client.register_write(two)
        self.assertFalse(self.client.commit_write(PackedWriteAck(one, True)))
        self.assertEqual(self.client.write_debts, 1)
        self.assertFalse(self.client.tick(result_ready=True)['service_result_fire'])
        self.assertFalse(self.client.commit_write(PackedWriteAck(two)))
        self.client.tick(result_ready=True)
        self.client.tick(result_ready=True)
        self.assertTrue(self.client.drained)

    def test_abort_before_issue_and_between_steps_does_not_invent_payload(self):
        self.client.tick(request=pv())
        self.client.tick(abort=True, result_ready=True)
        self.assertTrue(self.client.drained)
        self.assertEqual(self.service.counts['normal_steps'], 0)
        self.setUp()
        deliver(self.client, pv(0, 2))
        p = self.client.tick(abort=True, result_ready=True)
        self.assertTrue(p['service_done_fire'])
        self.assertFalse(p['result_fire'])
        self.assertTrue(self.client.drained)
        self.assertEqual(self.service.counts['normal_results'], 0)

    def test_reset_epoch_and_resource_mismatch_reject_without_mutation(self):
        result = deliver(self.client, pv())
        self.service.epoch += 1
        with self.assertRaises(MatrixProtocolError):
            self.client.tick(result_ready=True)
        self.assertIs(self.service.result, result.service_result)
        self.service.epoch -= 1
        self.service.resource_address += 1
        with self.assertRaises(MatrixProtocolError):
            self.client.tick(result_ready=True)

    def test_old_client_cannot_drive_a_later_identical_owner_acquisition(self):
        result = deliver(self.client, pv())
        finish(self.client, result)
        self.service.counts['owner_acquires'] += 1
        with self.assertRaisesRegex(MatrixProtocolError, 'acquisition changed'):
            self.client.tick(request=pv())
        self.assertIsNone(self.service.group)

    def test_malformed_packets_rejected_before_admission(self):
        request = pv()
        for bad in (replace(request, clear=1), replace(request, slice_mask=True),
                    replace(request, steps=129), replace(request, a=(0,) * 15),
                    replace(request, b=(0,) * 255), replace(request, a=(True,) * 16),
                    replace(request, selected=((0, 128),)), replace(request, selected=([0, 0],)),
                    replace(request, selected=((False, 0),)), replace(request, last=False)):
            with self.assertRaises(MatrixProtocolError):
                self.client.tick(request=bad)
            self.assertEqual(self.service.counts['normal_groups'], 0)
            self.assertTrue(self.client.drained)
        with self.assertRaises(MatrixProtocolError):
            self.client.tick(result_ready=1)


def native_smoke(root, library):
    """Small opt-in ABI smoke, no compiler and no full-public or RTL execution."""
    import ctypes
    import importlib.util
    from pathlib import Path
    import sys
    path = Path(root) / 'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py'
    spec = importlib.util.spec_from_file_location('packed_client_native_service', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    lib = module.configure_library(ctypes.CDLL(str(Path(library).resolve())))
    require(lib.td_reset() == 0, 'native reset')
    service = module.MatrixService(lib)
    owner = object()
    require(service.acquire(owner, 'normal', 29), 'native owner acquisition')
    resource = service.resource_address
    client = PackedClient(service, owner)
    for index in range(3):
        result = deliver(client, pv(index, 3))
        require(service.resource_address == resource, 'native resource changed')
        if index < 2:
            require(type(result) is PackedStepAccepted and result.value is None,
                    'native nonfinal metadata')
    require(result.value is service.result.value, 'native result copied')
    require(result.selected_words() == (0x40400000,), 'native three-step value')
    tag = PackedWriteTag(result.tag, 'scratch', 4096, 1, 1)
    client.register_write(tag)
    require(not client.tick(request=PackedConsumerAck(result.tag))['request_fire'], 'native write fence')
    require(client.commit_write(PackedWriteAck(tag)), 'native matching write')
    finish(client, result)
    require(lib.matrix_normal_fmas() == 3 * 16 * 128, 'native enabled-cell FMA count')
    service.retire_owner_response(owner)
    service.release(owner)
    return dict(status='PASS_TINY_PACKED_CLIENT_NATIVE', native_steps=3,
                full_public_admission=False, rtl_execution=False,
                same_service_type=type(service) is module.MatrixService,
                same_accumulator_resource=service.resource_address == resource)


if __name__ == '__main__':
    import sys
    if '--native-service-root' in sys.argv:
        import argparse
        import json
        parser = argparse.ArgumentParser()
        parser.add_argument('--native-service-root', required=True)
        parser.add_argument('--native-library', required=True)
        args = parser.parse_args()
        print(json.dumps(native_smoke(args.native_service_root, args.native_library), sort_keys=True))
    else:
        unittest.main()
