"""Exact bounded arithmetic and bank placement evidence, not RTL evidence."""
import unittest
from .controller import Controller, Timing, NumericalFault
from ..attention_retained_result.controller import Controller as Retained
from ..attention_scheduled_numeric.controller import Controller as Scheduled
from ..attention_matrix_batch.test_model import ExactScalar, OriginalSchedule, exp_negative, fixture, ref_fma


class BankControllerTests(unittest.TestCase):
    def make(self, cls=Controller, **kwargs):
        scalar = ExactScalar(object())
        if cls is Controller: kwargs.setdefault('scratch_enabled',True)
        return cls(scalar,ref_fma,lambda a:exp_negative(scalar,scalar.client,a),timing=Timing(2,3,1,2),**kwargs)

    def test_default_off_allocates_no_scratch(self):
        scalar = ExactScalar(object())
        controller = Controller(scalar,ref_fma,lambda a:exp_negative(scalar,scalar.client,a),timing=Timing(2,3,1,2))
        self.assertIsNone(controller.scratch)
        self.assertTrue(controller.ordinary_owner_ready())
        with self.assertRaisesRegex(ValueError,'disabled'):
            controller.run(1,*fixture(1))
        self.assertFalse(controller.active)
        self.assertEqual(controller.ticks,0)

    def test_m1_m2_oracles_original_counts_and_same_banks(self):
        for tokens, reads, writes in ((1,48,36),(2,156,96)):
            with self.subTest(tokens=tokens):
                data = fixture(tokens)
                original = OriginalSchedule(tokens,*data)
                expected = original.run()
                old = self.make(Retained).run(tokens,*data)
                scheduled = self.make(Scheduled).run(tokens,*data)
                controller = self.make(bank_stalls=2)
                bank = controller.scratch.parent.owner.a_banks
                result = controller.run(tokens,*data)
                self.assertIs(controller.scratch.banks,bank)
                self.assertIs(controller.scratch.parent.raw.banks,bank)
                self.assertEqual(result.output,expected)
                self.assertEqual(result.scores,original.scores()[1])
                self.assertEqual((result.output,result.scores),(old.output,old.scores))
                counts = dict(result.counts)
                for name,value in scheduled.counts:
                    self.assertEqual(counts[name],value,name)
                for name,value in old.counts:
                    if name != 'retained_result_hold_edges': self.assertEqual(counts[name],value,name)
                sc = controller.scratch.counts
                self.assertEqual(sc['read_requests'],reads)
                self.assertEqual(sc['write_requests'],writes)
                self.assertEqual(sc['acks'],reads+writes)
                self.assertEqual(sc['edges'],(reads+writes)*5+2)
                self.assertEqual(sc['bank_reads'],reads*2)
                self.assertEqual(sc['bank_writes'],writes*2)
                self.assertEqual(result.hypothetical_ticks,old.hypothetical_ticks+sc['edges'])
                self.assertEqual(counts['scratch_edges_with_retained_result'],12*tokens*5)
                self.assertEqual(counts['retained_result_hold_edges'],dict(old.counts)['retained_result_hold_edges']+12*tokens*5)
                self.assertEqual((len(controller.cv),len(controller.acc),len(controller.tmp)),(12,6,16))
                self.assertIsNone(controller.scratch.staging)
                self.assertIsNone(controller.scratch.active)
                self.assertTrue(controller.scratch.parent.raw.drained)
                self.assertTrue(controller.ordinary_owner_ready())
                self.assertFalse(any(controller.scratch.parent.debts().values()))
                for _,rd,wr,_,_ in controller.scratch.events:
                    self.assertLessEqual(len(rd)+len(wr),2)
                    self.assertFalse(rd and wr)

    def test_score_write_commits_before_retained_qk_ack(self):
        controller = self.make()
        scratch, observed = controller.scratch, []
        original = scratch.write_scores
        def write(context,head,words):
            slot = controller.slot
            self.assertIsNotNone(slot)
            self.assertEqual(slot['mask'],255)
            port, held = slot['port'],slot['port'].held
            original(context,head,words)
            self.assertIs(controller.slot,slot)
            self.assertIs(port.held,held)
            self.assertFalse(port.retired)
            self.assertIsNone(scratch.active)
            self.assertTrue(scratch.parent.raw.drained)
            observed.append((controller.clock(),port.group))
        scratch.write_scores = write
        controller.run(2,*fixture(2))
        self.assertEqual(len(observed),24)
        ack = {group:edge for edge,group,_ in controller.ack_events}
        for edge,group in observed: self.assertLessEqual(edge,ack[group])

    def test_pv_reads_only_current_key_after_previous_packet_returns(self):
        controller = self.make()
        original, observations = controller.scratch.read_word, []
        def read(context,plane,head,key,**kwargs):
            if kwargs.get('normalized'):
                port = controller.port
                self.assertEqual(port.mask,15)
                self.assertIsNone(port.pending)
                self.assertEqual(port.accepted,key)
                self.assertEqual(port.returned,key)
                observations.append((context.generation,key,head))
            return original(context,plane,head,key,**kwargs)
        controller.scratch.read_word = read
        controller.run(2,*fixture(2))
        self.assertEqual(len(observations),36)

    def test_fold_callback_fault_drains_compute_and_blocks_owner(self):
        scalar = ExactScalar(object())
        def operation(op,a,b):
            if op == 'add': raise ArithmeticError('injected fold callback')
            return scalar(op,a,b)
        controller = Controller(operation,ref_fma,lambda a:exp_negative(scalar,scalar.client,a),timing=Timing(2,3,1,2),scratch_enabled=True)
        with self.assertRaisesRegex(NumericalFault,'scalar failed'):
            controller.run(1,*fixture(1))
        self.assertTrue(controller.failed)
        self.assertFalse(controller.finished)
        self.assertIsNone(controller.port)
        self.assertIsNone(controller.slot)
        self.assertTrue(controller.scratch.parent.raw.drained)
        self.assertFalse(controller.ordinary_owner_ready())
        self.assertTrue(controller.ack_events[-1][2])

    def test_accepted_score_write_abort_drains_bank_and_retained_slot(self):
        controller = self.make()
        scratch, fired = controller.scratch, []
        def edge():
            controller.bank_edge()
            if scratch.active is not None and not fired:
                self.assertIsNotNone(controller.slot)
                fired.append(scratch.active)
                scratch.abort()
        scratch.edge = edge
        with self.assertRaisesRegex(ValueError,'retired poisoned'):
            controller.run(1,*fixture(1))
        self.assertEqual(len(fired),1)
        self.assertTrue(controller.failed)
        self.assertIsNone(controller.port)
        self.assertIsNone(controller.slot)
        self.assertIsNone(scratch.active)
        self.assertIsNone(scratch.staging)
        self.assertTrue(scratch.parent.raw.drained)
        self.assertTrue(scratch.parent.raw.poison)
        self.assertEqual(scratch.counts['acks'],1)
        self.assertEqual(scratch.score_written,[0]*6)
        self.assertTrue(controller.ack_events[-1][2])
        self.assertFalse(controller.ordinary_owner_ready())

    def test_pv_gather_fault_drains_matrix_terminal(self):
        controller = self.make()
        original = controller.scratch.read_word
        def read(context,plane,head,key,**kwargs):
            if context.query == 1 and kwargs.get('normalized') and key == 1:
                raise ValueError('injected second key gather')
            return original(context,plane,head,key,**kwargs)
        controller.scratch.read_word = read
        with self.assertRaisesRegex(ValueError,'second key gather'):
            controller.run(2,*fixture(2))
        self.assertTrue(controller.failed)
        self.assertIsNone(controller.port)
        self.assertIsNone(controller.slot)
        self.assertTrue(controller.ack_events[-1][2])
        self.assertTrue(controller.scratch.parent.raw.drained)
        self.assertFalse(controller.ordinary_owner_ready())


if __name__ == '__main__':
    unittest.main()
