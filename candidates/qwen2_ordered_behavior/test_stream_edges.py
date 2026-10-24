"""Bounded direct tests of a software Scala-edge translation, NOT DUT tests."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve(strict=True).parent
sys.path.insert(0, str(HERE))
import stream_client
if Path(stream_client.__file__).resolve(strict=True) != HERE / 'stream_client.py':
    raise ImportError('unexpected stream-client model origin')
from stream_client import PackedAttentionStreamEdge, StreamInputs


class StreamEdges(unittest.TestCase):
    def opening(self, *, count=3, pv=False, tag=23):
        c = PackedAttentionStreamEdge(enabled=True)
        p = c.tick(StreamInputs(start_valid=True, start_tag=tag,
                                start_count=count, start_pv=pv))
        self.assertTrue(p['start_fire'])
        self.assertEqual(c.state, 'opening')
        self.assertFalse(p['port_group_valid'])
        return c

    def issuing(self, **kwargs):
        c = self.opening(**kwargs)
        p = c.tick({'port_group_ready': True})
        self.assertTrue(p['port_group_fire'])
        self.assertEqual(c.state, 'issuing')
        return c

    def await_result(self, **kwargs):
        c = self.issuing(**kwargs)
        count = c.count if c.pv else 8
        for index in range(count):
            p = c.tick({'operands_valid': True, 'operands_index': index,
                        'port_step_ready': True})
            self.assertTrue(p['operands_fire'])
            self.assertTrue(p['port_step_fire'])
            self.assertEqual(p['port_step_bits']['clear'], index == 0)
            for key in ('last', 'finish', 'emit'):
                self.assertEqual(p['port_step_bits'][key], index == count - 1)
        self.assertEqual(c.state, 'awaitResult')
        return c

    def await_done(self):
        c = self.await_result()
        p = c.tick({'port_result_valid': True, 'result_ready': True})
        self.assertTrue(p['result_fire'])
        self.assertTrue(p['port_result_fire'])
        self.assertEqual(c.state, 'awaitDone')
        return c

    def reply(self):
        c = self.await_done()
        p = c.tick({'port_done_valid': True, 'port_done_tag': c.tag})
        self.assertTrue(p['port_done_fire'])
        self.assertFalse(p['completion_valid'])
        self.assertEqual(c.state, 'reply')
        return c

    def test_disabled_has_no_handshake_and_keeps_live_wire(self):
        c = PackedAttentionStreamEdge()
        payload = object()
        p = c.tick(dict(start_valid=True, start_tag=1, start_count=1,
                       port_group_ready=True, operands_valid=True,
                       port_step_ready=True, port_result_valid=True,
                       port_result_value=payload, result_ready=True,
                       port_done_valid=True, port_done_tag=1,
                       completion_ready=True, abort=True))
        self.assertEqual(c.state, 'idle')
        self.assertFalse(c.poison)
        self.assertIs(p['result_value'], payload)
        for key, value in p.items():
            if key.endswith('_fire'):
                self.assertFalse(value, key)
        for key in ('port_abort', 'reset_required', 'completion_valid',
                    'start_ready', 'result_valid', 'success_accepted'):
            self.assertFalse(p[key], key)

    def test_descriptor_legality_enters_error_reply_then_locked(self):
        for tag, pv, count in ((0, False, 1), (1, False, 0),
                               (1, False, 17), (1, True, 129)):
            c = PackedAttentionStreamEdge(enabled=True)
            p = c.tick(dict(start_valid=True, start_tag=tag,
                            start_pv=pv, start_count=count))
            self.assertTrue(p['start_fire'])
            self.assertEqual(c.state, 'reply')
            self.assertTrue(c.poison)
            p = c.tick({'completion_ready': True})
            self.assertTrue(p['completion_fire'])
            self.assertTrue(p['completion_error'])
            self.assertFalse(p['success_accepted'])
            self.assertEqual(c.state, 'locked')

    def test_real_eight_qk_steps_and_pv_counted_steps(self):
        for count in (1, 16):
            self.await_result(count=count)
        for count in (1, 3, 128):
            self.await_result(count=count, pv=True)

    def test_operand_backpressure_preserves_index_and_payload_identity(self):
        c = self.issuing()
        a, b = object(), object()
        for _ in range(4):
            p = c.tick(dict(operands_valid=True, operands_a=a, operands_b=b))
            self.assertTrue(p['port_step_valid'])
            self.assertFalse(p['operands_fire'])
            self.assertEqual(c.index, 0)
            self.assertIs(p['port_step_bits']['a'], a)
            self.assertIs(p['port_step_bits']['b'], b)

    def test_pause_grant_requires_drained_and_no_terminal_offer(self):
        c = self.issuing()
        for extra in ({}, {'port_result_valid': True}, {'port_done_valid': True}):
            p = c.peek(dict(pause=True, steps_drained=True,
                            operands_valid=True, operands_index=7, **extra))
            self.assertEqual(p['pause_granted'], not extra)
            self.assertFalse(p['operands_ready'])
            self.assertFalse(p['port_step_valid'])
        self.assertFalse(c.peek({'pause': True})['pause_granted'])

    def test_bad_index_is_consumed_without_issuing_matrix_step(self):
        c = self.issuing()
        p = c.tick(dict(operands_valid=True, operands_index=1,
                        port_step_ready=False))
        self.assertTrue(p['operands_ready'])
        self.assertTrue(p['operands_fire'])
        self.assertFalse(p['port_step_fire'])
        self.assertEqual(c.index, 0)
        self.assertEqual(c.state, 'draining')
        self.assertTrue(c.poison)

    def test_bad_result_is_discarded_even_without_consumer_ack(self):
        for bad in ({'port_result_context': 1}, {'port_result_last': False},
                    {'port_result_error': True}):
            c = self.await_result()
            p = c.tick(dict(port_result_valid=True, result_ready=False, **bad))
            self.assertFalse(p['result_valid'])
            self.assertFalse(p['result_fire'])
            self.assertTrue(p['port_result_fire'])
            self.assertEqual(c.state, 'draining')
            self.assertTrue(c.poison)

    def test_live_result_is_held_until_ack_and_success_waits_completion(self):
        c = self.await_result()
        payload = object()
        for _ in range(4):
            p = c.tick(dict(port_result_valid=True, port_result_value=payload))
            self.assertTrue(p['result_valid'])
            self.assertFalse(p['port_result_fire'])
            self.assertIs(p['result_value'], payload)
            self.assertIs(p['result_bits']['value'], payload)
        p = c.tick(dict(port_result_valid=True, port_result_value=payload,
                        result_ready=True))
        self.assertTrue(p['port_result_fire'])
        self.assertEqual(c.state, 'awaitDone')
        p = c.tick(dict(port_done_valid=True, port_done_tag=c.tag))
        self.assertTrue(p['port_done_fire'])
        self.assertFalse(p['success_accepted'])
        self.assertEqual(c.state, 'reply')
        p = c.tick({'completion_ready': True})
        self.assertTrue(p['success_accepted'])
        self.assertEqual(c.state, 'idle')
        self.assertFalse(c.poison)

    def test_early_done_overrides_result_ack_transition(self):
        for ack in (False, True):
            c = self.await_result()
            p = c.tick(dict(port_result_valid=True, result_ready=ack,
                            port_done_valid=True, port_done_tag=c.tag))
            # The CLIENT does not combinationally mask good result.valid with
            # done.valid. The surrounding ordered core supplies that gate.
            self.assertTrue(p['result_valid'])
            self.assertEqual(p['port_result_fire'], ack)
            self.assertFalse(p['port_done_fire'])
            self.assertFalse(p['reset_required'])
            self.assertEqual(c.state, 'draining')
            self.assertTrue(c.poison)

    def test_foreign_done_never_retires_matching_group(self):
        c = self.await_done()
        p = c.tick(dict(port_done_valid=True, port_done_tag=c.tag + 1))
        self.assertFalse(p['port_done_ready'])
        self.assertFalse(p['port_done_fire'])
        self.assertEqual(c.state, 'draining')
        for _ in range(3):
            p = c.tick(dict(port_done_valid=True, port_done_tag=c.tag + 1))
            self.assertFalse(p['port_done_fire'])
            self.assertEqual(c.state, 'draining')
        p = c.tick(dict(port_done_valid=True, port_done_tag=c.tag))
        self.assertTrue(p['port_done_fire'])
        self.assertEqual(c.state, 'reply')
        p = c.tick({'completion_ready': True})
        self.assertTrue(p['completion_error'])
        self.assertEqual(c.state, 'locked')

    def test_issuing_terminal_prevents_step_and_requests_drain(self):
        for terminal in ({'port_result_valid': True},
                         {'port_done_valid': True, 'port_done_tag': 23}):
            c = self.issuing()
            p = c.tick(dict(operands_valid=True, port_step_ready=True, **terminal))
            self.assertFalse(p['port_step_fire'])
            self.assertFalse(p['operands_fire'])
            self.assertEqual(c.state, 'draining')
            self.assertTrue(c.poison)

    def test_abort_start_opening_and_issuing_priority(self):
        c = PackedAttentionStreamEdge(enabled=True)
        p = c.tick(dict(start_valid=True, start_tag=1, start_count=1, abort=True))
        self.assertFalse(p['start_fire'])
        self.assertEqual(c.state, 'idle')
        self.assertFalse(c.poison)
        c = self.opening()
        p = c.tick(dict(port_group_ready=True, abort=True))
        self.assertFalse(p['port_group_fire'])
        self.assertFalse(p['port_abort'])  # Opening is not Scala's active set.
        self.assertEqual(c.state, 'reply')
        self.assertTrue(c.poison)
        c = self.issuing()
        p = c.tick(dict(operands_valid=True, port_step_ready=True, abort=True))
        self.assertFalse(p['operands_fire'])
        self.assertTrue(p['port_abort'])
        self.assertEqual(c.state, 'draining')

    def test_abort_with_done_fire_replies_instead_of_waiting_again(self):
        c = self.await_done()
        p = c.tick(dict(port_done_valid=True, port_done_tag=c.tag, abort=True))
        self.assertTrue(p['port_done_fire'])
        self.assertTrue(p['port_abort'])
        self.assertEqual(c.state, 'reply')
        self.assertTrue(c.poison)

    def test_completion_stall_and_same_edge_abort_cannot_publish_success(self):
        for ready in (False, True):
            c = self.reply()
            for _ in range(3):
                p = c.tick()
                self.assertTrue(p['completion_valid'])
                self.assertFalse(p['completion_error'])
                self.assertFalse(p['completion_fire'])
            p = c.tick(dict(completion_ready=ready, abort=True))
            self.assertTrue(p['completion_error'])
            self.assertFalse(p['success_accepted'])
            self.assertTrue(c.poison)
            self.assertEqual(c.state, 'locked' if ready else 'reply')
            if not ready:
                p = c.tick({'completion_ready': True})
                self.assertTrue(p['completion_error'])
                self.assertEqual(c.state, 'locked')

    def test_done_error_and_drain_simultaneous_terminal_handshakes(self):
        c = self.await_done()
        c.tick(dict(port_done_valid=True, port_done_tag=c.tag, port_done_error=True))
        self.assertEqual(c.state, 'reply')
        self.assertTrue(c.peek()['completion_error'])
        c = self.await_result()
        c.tick({'abort': True})
        p = c.tick(dict(port_result_valid=True, port_done_valid=True,
                        port_done_tag=c.tag, abort=True))
        self.assertTrue(p['port_result_fire'])
        self.assertTrue(p['port_done_fire'])
        self.assertEqual(c.state, 'reply')
        self.assertTrue(c.poison)


if __name__ == '__main__':
    unittest.main()
