"""Actual word hold/drain tests of proposed ports, not physical or RTL evidence."""
import unittest
from .ports import ScalarPort, MatrixPort
from ..attention_scalar_schedule.model import Operation, Offer
from ..attention_matrix_batch.test_model import ExactScalar, ref_bf, ref_fma

ONE = 0x3f800000
TWO = 0x40000000
ADD = Operation('vector16', 'add', 2)
PAYLOAD = ((ONE,)*16, (TWO,)*256)


class ScalarPortTests(unittest.TestCase):
    def make_port(self, plans=None, operation=None, exponential=None):
        port = ScalarPort(plans or {0:(ADD,), 1:(ADD,)},
                          operation or ExactScalar(object()), exponential or (lambda x: ONE))
        self.assertTrue(port.tick(acquire='attention')['acquire_fire'])
        return port

    def offer(self, port, **kwargs):
        return port.tick(offer=Offer('attention',(0,1)), operands=((ONE,ONE),(ONE,TWO)), **kwargs)

    def capture(self, port):
        for _ in range(100):
            if port.held is not None:
                return port.held
            port.tick()
        self.fail('scalar failed to produce bounded response')

    def test_accepted_only_arithmetic_early_foreign_ack_and_stable_words(self):
        port = self.make_port()
        for _ in range(3):
            self.assertFalse(self.offer(port)['offer_fire'])
        self.assertEqual(port.calls, 0)
        self.assertTrue(self.offer(port, feed_ready=True, ack=1)['offer_fire'])
        self.assertEqual(port.calls, 0)
        capture = port.tick(ack=1)
        self.assertFalse(capture['ack_fire'])
        held = self.capture(port)
        self.assertEqual(held.words, (TWO, 0x40400000))
        self.assertEqual(port.schedule.indices, {0:0,1:0})
        for ack in (None,0,99,None):
            out = port.tick(ack=ack)
            self.assertEqual(out['response'], held)
            self.assertFalse(out['ack_fire'])
            self.assertEqual(port.calls, 2)
        out = port.tick(ack=held.packet)
        self.assertTrue(out['publish'])
        self.assertEqual(port.schedule.indices, {0:1,1:1})
        self.assertEqual(port.schedule.accepted, port.schedule.retired)
        self.assertIsNone(port.held)

    def test_abort_and_ack_suppresses_publication(self):
        port = self.make_port()
        self.offer(port, feed_ready=True)
        held = self.capture(port)
        out = port.tick(ack=held.packet, abort=True)
        self.assertTrue(out['ack_fire'])
        self.assertFalse(out['publish'])
        self.assertTrue(out['reset_required'])
        self.assertEqual(out['debt'], 0)
        self.assertEqual(port.calls, 2)

    def test_abort_on_scalar_capture_edge_still_drains_without_publish(self):
        port = self.make_port()
        self.offer(port, feed_ready=True)
        self.assertIsNone(port.held)
        out = port.tick(abort=True, ack=1)
        self.assertIsNone(out['response'])
        self.assertFalse(out['ack_fire'])
        self.assertEqual(port.calls, 2)
        self.assertIsNotNone(port.held)
        self.assertTrue(out['reset_required'])
        out = port.tick(ack=port.held.packet)
        self.assertTrue(out['ack_fire'])
        self.assertFalse(out['publish'])
        self.assertEqual(out['debt'], 0)

    def test_pending_abort_drains_accepted_packet_once(self):
        plans = {0:(Operation('sfu16','div',8),),1:(Operation('sfu16','div',8),)}
        port = self.make_port(plans)
        self.offer(port, feed_ready=True)
        self.assertEqual(port.calls, 0)
        self.assertEqual(port.tick(abort=True)['debt'], 1)
        held = self.capture(port)
        self.assertEqual(port.calls, 2)
        out = port.tick(ack=held.packet)
        self.assertTrue(out['ack_fire'])
        self.assertFalse(out['publish'])
        self.assertEqual(out['debt'], 0)

    def test_error_result_zeroes_all_lanes_and_never_publishes(self):
        def bad(op,a,b):
            return TWO if b == ONE else 0x7f800000
        port = self.make_port(operation=bad)
        self.offer(port, feed_ready=True)
        held = self.capture(port)
        self.assertTrue(held.error)
        self.assertEqual(held.words, (0,0))
        for _ in range(4):
            self.assertEqual(port.tick()['response'], held)
        self.assertEqual(port.calls, 2)
        out = port.tick(ack=held.packet)
        self.assertTrue(out['ack_fire'])
        self.assertFalse(out['publish'])
        self.assertTrue(out['reset_required'])

    def test_lockstep_waits_for_slowest_lane_and_blocks_reissue(self):
        plans = {0:(Operation('sfu16','exp',3),),1:(Operation('sfu16','exp',20),)}
        port = self.make_port(plans)
        self.offer(port, feed_ready=True)
        for _ in range(18):
            self.assertFalse(self.offer(port, feed_ready=True)['offer_fire'])
            self.assertEqual(port.calls, 0)
            self.assertIsNone(port.held)
        held = self.capture(port)
        self.assertEqual(held.words,(ONE,ONE))
        self.assertEqual(port.calls, 2)
        self.assertEqual(port.schedule.accepted, 1)
        self.assertTrue(port.tick(ack=held.packet)['publish'])
        self.assertEqual(port.schedule.indices,{0:1,1:1})


class MatrixPortTests(unittest.TestCase):
    def make_port(self, steps=1, fma=ref_fma, round_bf=ref_bf):
        return MatrixPort(steps,15,((0,0),(5,127)),fma,round_bf,latency=3,group=7)

    def capture(self, port):
        for _ in range(100):
            if port.held is not None:
                return port.held
            port.tick()
        self.fail('matrix failed to produce bounded response')

    def test_accepted_only_computation_early_foreign_ack_and_hold(self):
        port = self.make_port()
        for _ in range(4):
            self.assertFalse(port.tick(payload=PAYLOAD)['accepted'])
        self.assertEqual((port.calls,port.conversions),(0,0))
        self.assertTrue(port.tick(payload=PAYLOAD,feed_ready=True,ack=7)['accepted'])
        for _ in range(2):
            out = port.tick(payload=PAYLOAD,feed_ready=True,ack=7)
            self.assertFalse(out['accepted'])
            self.assertFalse(out['ack_fire'])
            self.assertEqual(port.calls,0)
        out = port.tick(ack=7)
        self.assertFalse(out['ack_fire'])
        held = self.capture(port)
        self.assertEqual(held.words[0],TWO)
        self.assertEqual(held.words[5*256+127],TWO)
        self.assertEqual(sum(word != 0 for word in held.words),2)
        for ack in (None,0,1,None):
            out = port.tick(ack=ack,payload=PAYLOAD,feed_ready=True)
            self.assertEqual(out['response'],held)
            self.assertFalse(out['ack_fire'])
            self.assertFalse(out['accepted'])
            self.assertEqual((port.calls,port.conversions),(2,272))
        self.assertTrue(port.tick(ack=7)['publish'])
        self.assertTrue(port.retired)
        self.assertFalse(port.tick(payload=PAYLOAD,feed_ready=True,ack=7)['accepted'])

    def test_multistep_selected_cells_accumulate_once_in_order(self):
        port = self.make_port(2)
        port.tick(payload=PAYLOAD,feed_ready=True)
        while port.pending is not None:
            port.tick()
        self.assertIsNone(port.held)
        self.assertEqual(port.cells[0],TWO)
        port.tick(payload=PAYLOAD,feed_ready=True)
        held = self.capture(port)
        self.assertEqual(held.words[0],0x40800000)
        self.assertEqual(held.words[5*256+127],0x40800000)
        self.assertEqual((port.accepted,port.returned,port.calls,port.conversions),(2,2,4,544))
        self.assertTrue(port.tick(ack=7)['publish'])

    def test_abort_with_ack_suppresses_publication(self):
        port = self.make_port()
        port.tick(payload=PAYLOAD,feed_ready=True)
        self.capture(port)
        out = port.tick(ack=7,abort=True)
        self.assertTrue(out['ack_fire'])
        self.assertFalse(out['publish'])
        self.assertTrue(out['reset_required'])
        self.assertEqual((out['pending_debt'],out['terminal_debt']),(0,0))

    def test_abort_pending_drains_and_cancels_unaccepted_steps(self):
        port = self.make_port(2)
        port.tick(payload=PAYLOAD,feed_ready=True)
        out = port.tick(abort=True,payload=PAYLOAD,feed_ready=True)
        self.assertFalse(out['accepted'])
        self.assertEqual(out['pending_debt'],1)
        held = self.capture(port)
        self.assertTrue(held.error)
        self.assertFalse(any(held.words))
        self.assertEqual((port.accepted,port.returned,port.calls),(1,1,2))
        out = port.tick(ack=7)
        self.assertTrue(out['ack_fire'])
        self.assertFalse(out['publish'])
        self.assertEqual(out['terminal_debt'],0)

    def test_abort_on_exact_matrix_return_edge_requires_terminal_ack(self):
        port = self.make_port(2)
        port.tick(payload=PAYLOAD, feed_ready=True)
        port.tick()
        port.tick()
        self.assertIsNotNone(port.pending)
        self.assertEqual(port.returned, 0)
        out = port.tick(abort=True, ack=7)
        self.assertFalse(out['ack_fire'])
        self.assertEqual((port.accepted, port.returned, port.calls), (1, 1, 2))
        self.assertEqual((out['pending_debt'], out['terminal_debt']), (0, 1))
        self.assertTrue(port.held.error)
        self.assertFalse(any(port.held.words))
        out = port.tick(ack=7)
        self.assertTrue(out['ack_fire'])
        self.assertFalse(out['publish'])
        self.assertEqual(out['terminal_debt'], 0)

    def test_error_after_successful_cell_zeroes_entire_result(self):
        calls = []
        def late_error(a, b, c):
            calls.append((a,b,c))
            return ref_fma(a,b,c) if len(calls) == 1 else 0x7f800000
        port = self.make_port(fma=late_error)
        port.tick(payload=PAYLOAD, feed_ready=True)
        held = self.capture(port)
        self.assertEqual(port.cells[0], TWO)
        self.assertTrue(held.error)
        self.assertFalse(any(held.words))
        self.assertEqual(len(calls), 2)
        self.assertFalse(port.tick(ack=7)['publish'])
        self.assertEqual(len(calls), 2)

    def test_arithmetic_and_conversion_errors_hold_without_reexecution(self):
        for kwargs in ({'fma':lambda a,b,c:0x7f800000},
                       {'round_bf':lambda a:0x7f800000}):
            with self.subTest(failure=list(kwargs)):
                port = self.make_port(2,**kwargs)
                port.tick(payload=PAYLOAD,feed_ready=True)
                held = self.capture(port)
                self.assertTrue(held.error)
                self.assertFalse(any(held.words))
                for _ in range(4):
                    self.assertEqual(port.tick()['response'],held)
                self.assertEqual((port.accepted,port.returned,port.calls,port.conversions),(1,1,2,272))
                out = port.tick(ack=7)
                self.assertTrue(out['ack_fire'])
                self.assertFalse(out['publish'])
                self.assertTrue(out['reset_required'])


if __name__ == '__main__':
    unittest.main()
