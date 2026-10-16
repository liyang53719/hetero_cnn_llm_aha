"""Original-owner arithmetic and real bank transactions, hypothetical routing."""
import unittest
from .controller import Controller
from ..attention_bank_m128.controller import Controller as Baseline
from ..attention_scheduled_numeric.controller import Timing
from ..attention_bank_multirow.oracle import Oracle,ScalarTrace
from ..attention_matrix_batch.test_model import ExactScalar,fixture,ref_fma,exp_negative
class ControllerTests(unittest.TestCase):
    def make(self,**kwargs):
        scalar=ExactScalar(object());scalar.trace=ScalarTrace(capture_scores=False)
        kwargs.setdefault('panel_enabled',True);kwargs.setdefault('timing',Timing(2,3,1,2))
        return Controller(scalar,ref_fma,lambda a:exp_negative(scalar,scalar.client,a),**kwargs)
    def test_existing_qk_method_and_explicit_added_storage(self):
        self.assertIs(Controller.qk_head,Baseline.qk_head)
        c=self.make()
        self.assertEqual(len(c.scratch.panel_words),96)
        ledger=c.scratch.resource_ledger
        self.assertEqual(ledger['panel_payload_bytes'],384)
        self.assertFalse(ledger['legacy_dense_weights_retention_verified'])
        self.assertFalse(ledger['v_placement_verified'])
        with self.assertRaises(ValueError):c.run(128,(),(),())
    def test_default_off(self):
        c=self.make(panel_enabled=False)
        with self.assertRaises(ValueError):c.run(1,*fixture(1))
        self.assertEqual(c.ticks,0)
    def test_m1_m2_original_words_counts_and_same_banks(self):
        for n in (1,2):
            data=fixture(n);oracle=Oracle(n,*data);expected=oracle.run()
            c=self.make(bank_stalls=2);banks=c.scratch.banks;actual=c.run(n,*data);x=dict(actual.counts)
            self.assertEqual(actual.output,expected);self.assertEqual(actual.scores,oracle.scores()[1])
            self.assertIs(c.scratch.parent.owner.a_banks,banks);self.assertIs(c.scratch.parent.raw.banks,banks)
            g=12*n;pairs=6*n*(n+1)
            self.assertEqual(x['scratch_read_requests'],2*g);self.assertEqual(x['scratch_write_requests'],2*g)
            self.assertEqual(x['scratch_edges'],4*g*5+2);self.assertEqual(x['scratch_acks'],4*g)
            self.assertEqual(x['matrix_steps'],96*n+n*(n+1));self.assertEqual(x['matrix_returns'],x['matrix_steps'])
            self.assertEqual(x['matrix_result_acks'],14*n);self.assertEqual(x['selected_fmas'],256*pairs)
            self.assertEqual(x['vector16_add'],16*pairs);self.assertEqual(x['vector16_mul'],pairs)
            self.assertEqual(x['sfu16_add'],2*pairs);self.assertEqual(x['sfu16_exp'],pairs);self.assertEqual(x['sfu16_div'],12*n);self.assertEqual(x['sfu16_mul'],pairs)
            self.assertEqual(x['scalar_packets'],x['scalar_packet_acks']);self.assertTrue(c.ordinary_owner_ready())
            self.assertIsNone(c.pv_context);self.assertIsNone(c.slot)
    def test_stalls_and_divider_assumptions_preserve_words(self):
        data=fixture(2,seed=314159)
        a=self.make(timing=Timing(1,3,0,0)).run(2,*data)
        b=self.make(timing=Timing(6,11,2,3),bank_stalls=2).run(2,*data)
        self.assertEqual((a.output,a.scores),(b.output,b.scores));self.assertLess(a.hypothetical_ticks,b.hypothetical_ticks)
        for key in ('selected_fmas','matrix_steps','matrix_returns','scratch_read_requests','scratch_write_requests','scalar_packets','scheduled_scalar_lane_calls'):
            self.assertEqual(dict(a.counts)[key],dict(b.counts)[key])
    def test_normalization_fault_drains_same_pv_group(self):
        scalar=ExactScalar(object());scalar.trace=ScalarTrace(capture_scores=False);failed=[]
        def operation(op,a,b):
            if op=='mul' and c.pv_context is not None and c.pv_context.returned==1:
                failed.append(c.pv_context.group);raise ArithmeticError('injected normalization fault')
            return scalar(op,a,b)
        c=Controller(operation,ref_fma,lambda a:exp_negative(scalar,scalar.client,a),panel_enabled=True,timing=Timing(2,3,0,1))
        with self.assertRaises((ValueError,ArithmeticError)):c.run(2,*fixture(2))
        self.assertTrue(failed);self.assertTrue(c.failed);self.assertFalse(c.finished);self.assertFalse(c.ordinary_owner_ready())
        self.assertIsNone(c.pv_context);self.assertIsNone(c.slot);self.assertIsNone(c.port)
        self.assertEqual(c.counts['matrix_steps'],c.counts['matrix_returns'])
    def test_suspended_context_cannot_issue_during_scalar(self):
        scalar=ExactScalar(object());scalar.trace=ScalarTrace(capture_scores=False);observed=[]
        def operation(op,a,b):
            if c.pv_context is not None and op=='mul':
                p=c.pv_context
                self.assertEqual(c.pv_state,'suspended');self.assertIsNone(p.pending)
                self.assertEqual(p.accepted,p.returned);self.assertFalse(c.ordinary_owner_ready())
                with self.assertRaises(ValueError):c._pv_tick()
                with self.assertRaises(ValueError):c.scratch.legacy_clear()
                observed.append((p.group,p.accepted))
            return scalar(op,a,b)
        c=Controller(operation,ref_fma,lambda a:exp_negative(scalar,scalar.client,a),panel_enabled=True,timing=Timing(2,3,1,2))
        c.run(2,*fixture(2))
        self.assertEqual(len(observed),36)
        groups={g for g,_ in observed};self.assertEqual(len(groups),4)
        self.assertTrue(any(key==1 for _,key in observed))
    def test_pv_fma_fault_keeps_error_and_debt_fence(self):
        scalar=ExactScalar(object());scalar.trace=ScalarTrace(capture_scores=False)
        def fma(a,b,total):
            if c.pv_context is not None:raise ArithmeticError('injected PV return failure')
            return ref_fma(a,b,total)
        c=Controller(scalar,fma,lambda a:exp_negative(scalar,scalar.client,a),panel_enabled=True,timing=Timing(2,3,0,1))
        with self.assertRaises((ValueError,ArithmeticError)):c.run(1,*fixture(1))
        self.assertTrue(c.failed);self.assertFalse(c.finished);self.assertFalse(c.ordinary_owner_ready())
        self.assertIsNone(c.pv_context);self.assertIsNone(c.slot)
        self.assertEqual(c.counts['matrix_steps'],c.counts['matrix_returns'])
if __name__=='__main__':unittest.main()
