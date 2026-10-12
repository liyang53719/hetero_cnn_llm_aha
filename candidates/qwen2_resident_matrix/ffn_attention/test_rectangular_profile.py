"""Bounded host regression for the explicit rectangular NormalGroup profile.

Run with unittest discovery or directly, with MATRIX_SERVICE_LIBRARY pointing
at the caller's already built shared Matrix library. This suite never builds a
library. MATRIX_SERVICE_COMPILE_RECEIPT optionally records and verifies that
build's source and library hashes. The existing fixture is invoked once per
module; its TestCase is not imported/inherited, so discovery cannot duplicate
the legacy tests. The numerical oracle is the independent system libm.fmaf.
These are host arithmetic and handshake tests, not RTL or hardware-cycle tests.
"""
import ctypes as C
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

import matrix_service as m
import test_matrix_service as helpers


ZERO = tuple((0,) * 256 for _ in range(16))
_SETUPS = 0


def setUpModule():
    global _SETUPS
    if not os.environ.get('MATRIX_SERVICE_LIBRARY'):
        raise RuntimeError('MATRIX_SERVICE_LIBRARY must name the caller\'s shared build')
    _SETUPS += 1
    if _SETUPS != 1:
        raise RuntimeError('rectangular test fixture was initialized more than once')
    helpers.setUpModule()
    helpers.REPORT['suite'] = 'explicit_rectangular_normal_profile'
    helpers.REPORT['rectangular_fixture_setups'] = _SETUPS
    helpers.REPORT['rectangular_test_sha256_before'] = helpers.sha(__file__)
    receipt_path = os.environ.get('MATRIX_SERVICE_COMPILE_RECEIPT')
    if receipt_path:
        receipt_path = Path(receipt_path).resolve()
        receipt = json.loads(receipt_path.read_text())
        if receipt['returncode'] != 0:
            raise RuntimeError('shared Matrix build receipt reports a failed build')
        if Path(receipt['library']).resolve() != Path(helpers.REPORT['library']):
            raise RuntimeError('shared Matrix build receipt names a different library')
        if receipt['library_sha256'] != helpers.REPORT['library_sha256']:
            raise RuntimeError('shared Matrix library does not match its build receipt')
        for name, digest in receipt['sources_after'].items():
            if helpers.sha(m.ROOT / name) != digest:
                raise RuntimeError('shared Matrix build source changed: ' + name)
        helpers.REPORT['compile_receipt'] = str(receipt_path)
        helpers.REPORT['compile_receipt_sha256'] = helpers.sha(receipt_path)
        helpers.REPORT['compile_receipt_sources_verified'] = True
    helpers.save_evidence()


def tearDownModule():
    helpers.REPORT['rectangular_test_sha256_after'] = helpers.sha(__file__)
    helpers.REPORT['rectangular_test_unchanged'] = (
        helpers.REPORT['rectangular_test_sha256_before'] == helpers.sha(__file__))
    helpers.tearDownModule()


def packet(index):
    # Distinct rows, columns and steps; includes rounding, signed zero and
    # subnormal operands. Nonzero upper columns expose accidental slice-zero PV.
    finite = helpers.FINITE_BF16
    a = tuple(finite[(row + 3 * index) % 16] for row in range(16))
    b = tuple(finite[(5 * col + 7 * index + col // 16) % 16]
              for col in range(256))
    return a, b


def rectangular_oracle(previous, a, b, columns):
    # Independent recurrence over every active physical cell. No candidate
    # helper, selected-cell shortcut, host matrix multiply or unfused +=.
    return tuple(tuple(helpers.oracle_fma(a[row], b[col], previous[row][col])
                       if col < columns else 0 for col in range(256))
                 for row in range(16))


class RectangularProfileTests(unittest.TestCase):
    setUp = helpers.MatrixServiceTests.setUp
    tearDown = helpers.MatrixServiceTests.tearDown
    normal = helpers.MatrixServiceTests.normal
    dense = helpers.MatrixServiceTests.dense
    until = helpers.MatrixServiceTests.until
    normal_reply = helpers.MatrixServiceTests.normal_reply
    finish_owner = helpers.MatrixServiceTests.finish_owner

    def acquire_rectangular(self, opcode=0x24, steps=1, tag=97):
        self.assertTrue(self.service.acquire(self.owner, 'normal', 91))
        group = m.NormalGroup(opcode, steps, tag, 1 if opcode == 0x23 else 255, 1)
        self.assertTrue(self.service.accept_group(self.owner, group))
        self.assertFalse(self.service.reset_required)
        return group

    def step(self, index, count, operands=None):
        a, b = packet(index) if operands is None else operands
        last = index + 1 == count
        return m.NormalStep(index, a, b, index == 0, last, finish=last, emit=last)

    def assert_no_legacy_reply(self):
        self.assertEqual(helpers.LIB.matrix_state() & 32, 0)
        with self.assertRaises(m.MatrixProtocolError):
            self.service.retire_legacy_reply(self.owner, self.service.ticket,
                                             self.service.epoch)

    def assert_owner_blocked(self):
        self.assertFalse(self.service.acquire(object(), 'dense', 101))
        for callback in (lambda: self.service.retire_owner_response(self.owner),
                         lambda: self.service.release(self.owner)):
            with self.assertRaises(m.MatrixProtocolError):
                callback()

    def drain_error(self, expected_fmas):
        self.assertTrue(self.service.reset_required)
        self.assertIsNone(self.service.result)
        self.assertFalse(self.service.ports()['step_ready'])
        self.assertFalse(self.service.ports()['group_ready'])
        self.assert_no_legacy_reply()
        self.assert_owner_blocked()
        done = self.service.done
        self.assertIsNotNone(done)
        self.assertTrue(done.error)
        self.service.retire_done(self.owner, done)
        self.finish_owner()
        self.assertFalse(self.service.acquire(self.owner, 'normal', 91))
        self.assertFalse(self.service.acquire(object(), 'dense', 101))
        self.assertEqual(helpers.LIB.matrix_normal_fmas(), expected_fmas)
        self.assertEqual(helpers.LIB.matrix_dense_fmas(), 0)

    def complete_rectangular(self, opcode, count):
        group = self.acquire_rectangular(opcode, count)
        columns = 32 if opcode == 0x23 else 256
        before = helpers.LIB.matrix_normal_fmas()
        replies = self.service.counts['legacy_replies']
        results = self.service.counts['normal_results']
        expected = ZERO
        for index in range(count):
            a, b = packet(index)
            self.assertTrue(self.service.accept_step(self.owner,
                self.step(index, count, (a, b))))
            expected = rectangular_oracle(expected, a, b, columns)
            self.assert_no_legacy_reply()
            if index + 1 < count:
                self.assertIsNone(self.service.result)
                self.assertIsNone(self.service.done)
                self.assertTrue(self.service.ports()['step_ready'])
                self.assert_owner_blocked()
        held = self.service.result
        self.assertIsNotNone(held)
        self.assertTrue(held.last)
        self.assertFalse(held.error)
        self.assertEqual(held.context, 0)
        self.assertEqual(held.value, expected)
        self.assertIsNone(self.service.done)
        fake_done = m.MatrixDone(group.tag, False, held.ticket, held.epoch)
        with self.assertRaises(m.MatrixProtocolError):
            self.service.retire_done(self.owner, fake_done)
        for _ in range(4):
            self.assertIs(self.service.ports()['result'], held)
            self.assertIsNone(self.service.ports()['done'])
            self.assertFalse(self.service.accept_step(self.owner, self.step(0, count)))
            self.assertFalse(self.service.accept_group(self.owner, group))
            self.assert_owner_blocked()
        self.service.retire_result(self.owner, held)
        done = self.service.done
        self.assertIsNotNone(done)
        self.assertFalse(done.error)
        self.assertEqual((done.tag, done.ticket, done.epoch),
                         (group.tag, held.ticket, held.epoch))
        for _ in range(4):
            self.assertIs(self.service.ports()['done'], done)
            self.assert_owner_blocked()
        self.service.retire_done(self.owner, done)
        self.assert_no_legacy_reply()
        self.assertEqual(self.service.counts['legacy_replies'], replies)
        self.assertEqual(self.service.counts['normal_results'], results + 1)
        # A new mode remains unavailable until the separately accepted owner
        # response and explicit release, even after the REAL done is retired.
        self.assertFalse(self.service.acquire(object(), 'dense', 101))
        self.finish_owner()
        self.assertEqual(helpers.LIB.matrix_normal_fmas() - before,
                         count * 16 * columns)
        return held, done

    def complete_dense(self):
        adapter = self.dense()
        self.assertEqual(adapter.td_group(0, 16, 1), 0)
        expected = ZERO
        for index in range(16):
            a, b = packet(index)
            b = b[:144] + (0,) * 112  # Historical transposed Dense wire padding.
            expected = helpers.dense_oracle(expected, a, b)
            output = (C.c_uint32 * 4096)()
            last = index == 15
            self.assertEqual(adapter.td_step(index, 0, index == 0, last, last, last,
                (C.c_uint16 * 16)(*a), (C.c_uint16 * 256)(*b), output), int(last))
        result = helpers.dense_result(output)
        self.assertEqual(result.value, expected)
        self.assert_owner_blocked()
        with self.assertRaises(m.MatrixProtocolError):
            adapter.retire_done(NS(tag=self.service.owner_tag, error=False))
        adapter.retire_result(result)
        self.assert_owner_blocked()
        adapter.retire_done(NS(tag=self.service.owner_tag, error=False))
        self.finish_owner()

    def complete_legacy(self, opcode, count):
        # Retain cumulative counters and never reset between mixed-mode jobs.
        client = self.normal()
        expected = ZERO
        for index in range(count):
            a, b = packet(index)
            result = self.normal_reply(client, m.LegacyRequest(
                opcode, a, b, index == 0, index + 1 == count, count))
            expected = helpers.normal_oracle(expected, a, b)
            self.assertEqual(result.value, expected)
            self.assertFalse(result.error)
            self.assertTrue(client.tick(result_ready=True)['result_fire'])
        self.finish_owner()

    def test_mixed_legacy_rectangular_dense_and_back_use_one_resource(self):
        address = self.service.resource_address
        self.assertEqual(helpers.LIB.matrix_accumulator_bytes(), 5 * 16 * 256 * 4)
        sequence = (
            lambda: self.complete_legacy(0x23, 8),
            lambda: self.complete_legacy(0x24, 3),
            lambda: self.complete_rectangular(0x23, 256),
            lambda: self.complete_rectangular(0x24, 256),
            self.complete_dense,
            lambda: self.complete_legacy(0x23, 8),
            lambda: self.complete_legacy(0x24, 1),
            lambda: self.complete_rectangular(0x24, 1),
        )
        for operation in sequence:
            operation()
            self.assertEqual(self.service.resource_address, address)
            self.assertEqual(helpers.LIB.matrix_accumulator_address(), address)
            self.assertFalse(self.service.reset_required)
        self.assertEqual(helpers.LIB.matrix_normal_fmas(),
                         (8 + 3 + 8 + 1 + 256) * 512 + (256 + 1) * 4096)
        self.assertEqual(helpers.LIB.matrix_dense_fmas(), 16 * 4096)
        self.assertEqual(self.service.counts['legacy_replies'], 20)
        self.assertEqual(self.service.counts['normal_results'], 23)
        self.assertEqual(self.service.counts['normal_done'], 7)
        self.assertEqual(self.service.counts['owner_acquires'], 8)
        self.assertEqual(self.service.counts['owner_releases'], 8)

    def test_pv_short_and_non_power_of_two_lengths_compute_every_cell(self):
        for count in (2, 17):
            with self.subTest(count=count):
                held, _ = self.complete_rectangular(0x24, count)
                self.assertTrue(any(word for row in held.value[1:] for word in row[32:]))

    def test_special_operands_preserve_all_payloads_without_protocol_fault(self):
        special = (0x7f80, 0xff80, 0x7fc1, 0xffc2, 0x7f81, 0xff81,
                   0, 0x8000, 0x0001, 0x8001, 0x3f80, 0xbf80,
                   0x7f7f, 0xff7f, 0x3eab, 0xbeab)
        b = tuple(special[(col + col // 16) % 16] for col in range(256))
        self.acquire_rectangular()
        self.assertTrue(self.service.accept_step(self.owner,
            self.step(0, 1, (special, b))))
        result = self.service.result
        self.assertEqual(result.value, rectangular_oracle(ZERO, special, b, 256))
        self.assertFalse(self.service.reset_required)
        self.assertEqual(helpers.LIB.matrix_normal_fmas(), 4096)
        self.service.retire_result(self.owner, result)
        self.assertFalse(self.service.done.error)
        self.service.retire_done(self.owner, self.service.done)
        self.assert_no_legacy_reply()
        self.finish_owner()

    def test_malformed_packet_widths_reject_without_advancing_or_arithmetic(self):
        self.acquire_rectangular()
        step = self.step(0, 1)
        for changes in ({'a': step.a[:-1]}, {'b': step.b[:-1]},
                        {'a': (65536,) + step.a[1:]}, {'b': (-1,) + step.b[1:]},
                        {'index': True}, {'context': -1}):
            with self.subTest(changes=changes):
                with self.assertRaises(m.MatrixProtocolError):
                    self.service.accept_step(self.owner, replace(step, **changes))
                self.assertTrue(self.service.ports()['step_ready'])
                self.assertIsNone(self.service.result)
                self.assertIsNone(self.service.done)
                self.assertEqual(helpers.LIB.matrix_normal_fmas(), 0)
        self.assertTrue(self.service.accept_step(self.owner, step))
        self.service.retire_result(self.owner, self.service.result)
        self.service.retire_done(self.owner, self.service.done)
        self.finish_owner()

    def test_unknown_profile_opcode_shapes_and_masks_fault_before_arithmetic(self):
        invalid = (
            m.NormalGroup(0x24, 1, 2, 255, 2),
            m.NormalGroup(0x24, 1, 2, 255, 0xffffffff),
            m.NormalGroup(0x22, 1, 2, 255, 1),
            *(m.NormalGroup(0x23, count, 2, 1, 1) for count in (0, 8, 255, 257)),
            *(m.NormalGroup(0x23, 256, 2, mask, 1) for mask in (0, 2, 255, 256)),
            *(m.NormalGroup(0x24, count, 2, 255, 1) for count in (0, 257, 1024)),
            *(m.NormalGroup(0x24, 1, 2, mask, 1) for mask in (0, 1, 127, 256)),
            m.NormalGroup(0x23, 256, 2),  # Default still means legacy Qwen2.
            m.NormalGroup(0x24, 256, 2, 255),
        )
        for group in invalid:
            with self.subTest(group=group):
                self.service.reset()
                self.assertTrue(self.service.acquire(self.owner, 'normal', 91))
                self.assertTrue(self.service.accept_group(self.owner, group))
                self.drain_error(0)

    def test_group_python_field_types_reject_without_consuming_the_group(self):
        self.assertTrue(self.service.acquire(self.owner, 'normal', 91))
        group = m.NormalGroup(0x24, 1, 2, 255, 1)
        for changes in ({'profile': True}, {'profile': -1}, {'profile': 1 << 32},
                        {'profile': 1.0}, {'steps': True}, {'slice_mask': -1}):
            with self.subTest(changes=changes):
                with self.assertRaises(m.MatrixProtocolError):
                    self.service.accept_group(self.owner, replace(group, **changes))
                self.assertTrue(self.service.ports()['group_ready'])
                self.assertIsNone(self.service.done)
                self.assertEqual(helpers.LIB.matrix_normal_fmas(), 0)
        self.finish_owner()

    def test_intermediate_and_final_controls_fault_without_extra_fmas(self):
        initial_changes = ({'index': 1}, {'context': 1}, {'clear': False},
                           {'clear': 2}, {'last': True}, {'finish': True},
                           {'emit': True}, {'emit': 2})
        final_changes = ({'index': 0}, {'context': 1}, {'clear': True},
                         {'last': False}, {'last': 2}, {'finish': False},
                         {'finish': 2}, {'emit': False}, {'emit': 2})
        for final, changes_set in ((False, initial_changes), (True, final_changes)):
            for changes in changes_set:
                with self.subTest(final=final, changes=changes):
                    self.service.reset()
                    self.acquire_rectangular(steps=2)
                    if final:
                        self.assertTrue(self.service.accept_step(self.owner, self.step(0, 2)))
                    self.assertTrue(self.service.accept_step(self.owner,
                        replace(self.step(int(final), 2), **changes)))
                    self.drain_error(4096 if final else 0)

    def test_abort_before_after_partial_and_held_terminal_drains_then_reset(self):
        for accepted in (0, 1, 3):
            with self.subTest(accepted_steps=accepted):
                self.service.reset()
                address = self.service.resource_address
                self.acquire_rectangular(steps=3)
                for index in range(accepted):
                    self.assertTrue(self.service.accept_step(self.owner, self.step(index, 3)))
                held = self.service.result
                self.service.abort(self.owner)
                self.assertFalse(self.service.accept_step(self.owner, self.step(accepted, 3)))
                if held is not None:
                    snapshot = held.value.raw
                    for _ in range(4):
                        self.assertIs(self.service.result, held)
                        self.assertEqual(held.value.raw, snapshot)
                        self.assertIsNone(self.service.done)
                        self.assert_owner_blocked()
                    self.service.retire_result(self.owner, held)
                self.drain_error(accepted * 4096)
                self.service.reset()
                self.assertEqual(self.service.resource_address, address)
                self.complete_rectangular(0x24, 1)

    def test_wrong_done_tag_errors_and_prevents_reacquisition_until_reset(self):
        self.acquire_rectangular()
        self.assertTrue(self.service.accept_step(self.owner, self.step(0, 1)))
        self.service.retire_result(self.owner, self.service.result)
        done = self.service.done
        self.service.retire_done(self.owner, replace(done, tag=done.tag + 1))
        self.assertTrue(self.service.reset_required)
        self.assert_no_legacy_reply()
        self.finish_owner()
        self.assertFalse(self.service.acquire(self.owner, 'normal', 91))
        self.service.reset()
        self.complete_rectangular(0x24, 1)

    def test_previous_group_and_reset_epoch_reject_late_result_done_and_reply(self):
        old_result, old_done = self.complete_rectangular(0x24, 1)
        for reset in (False, True):
            with self.subTest(reset=reset):
                if reset:
                    self.service.reset()
                self.acquire_rectangular()
                self.assertGreater(self.service.ticket, old_result.ticket)
                callbacks = [
                    lambda: self.service.retire_result(self.owner, old_result),
                    lambda: self.service.retire_done(self.owner, old_done),
                    lambda: self.service.retire_legacy_reply(self.owner,
                        old_result.ticket, old_result.epoch),
                ]
                if reset:
                    # Matching the new ticket must not bypass the reset epoch.
                    callbacks.extend((
                        lambda: self.service.retire_result(self.owner,
                            replace(old_result, ticket=self.service.ticket)),
                        lambda: self.service.retire_done(self.owner,
                            replace(old_done, ticket=self.service.ticket)),
                    ))
                before = helpers.LIB.matrix_normal_fmas()
                for callback in callbacks:
                    with self.assertRaises(m.MatrixProtocolError):
                        callback()
                    self.assertTrue(self.service.ports()['step_ready'])
                    self.assertFalse(self.service.reset_required)
                self.assertEqual(helpers.LIB.matrix_normal_fmas(), before)
                self.assertTrue(self.service.accept_step(self.owner, self.step(0, 1)))
                self.service.retire_result(self.owner, self.service.result)
                self.service.retire_done(self.owner, self.service.done)
                self.finish_owner()


if __name__ == '__main__':
    unittest.main()
