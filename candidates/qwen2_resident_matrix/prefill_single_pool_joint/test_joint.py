import unittest
from joint import Joint,Violation
from loan import Request,ContractError

def event(name,*args,**kwargs):return (name,args,kwargs)
def request(tag=1,mode='silu'):
    return dict(request=Request(tag,mode),ordinary_idle=True,vector_request_ready=True)

class Tests(unittest.TestCase):
    def unchanged(self,m,**kw):
        before=m.snapshot()
        with self.assertRaises((Violation,ContractError,TypeError)):m.tick(**kw)
        self.assertEqual(before,m.snapshot())
    def test_loan_valid_bank_invalid_rolls_back_both(self):
        m=Joint();self.unchanged(m,edge=0,loan_signals=request(),events=(event('bank_return',999),))
        self.assertTrue(m.tick(0,loan_signals=request())['loan']['request_fire'])
    def test_bank_valid_loan_invalid_rolls_back_both(self):
        m=Joint();self.unchanged(m,edge=0,loan_signals=dict(vector_result_valid=True,result_token=8),events=(event('begin_scratch',1,0,0),))
        m.tick(0,events=(event('begin_scratch',1,0,0),));self.assertEqual(m.snapshot()['ledger']['context'],(1,0,0))
    def test_late_batch_failure_rolls_back_prior_events(self):
        m=Joint();self.unchanged(m,edge=0,events=(event('begin_scratch',1,0,0),event('bank_return',1)))
    def test_duplicate_tick_atomic(self):
        m=Joint();m.tick(0);self.unchanged(m,edge=0);self.unchanged(m,edge=2)
    def test_legacy_and_alu_and_parent_entrypoints_rejected(self):
        for name in ('sfu_accept','sfu_return','sfu_ack','divider_pulse','alu_accept','alu_return','alu_ack','abort','advance','parent_tick'):
            m=Joint();self.unchanged(m,edge=0,events=(event(name),))
    def test_single_pool_and_no_supply(self):
        m=Joint();m.tick(0,loan_signals=request());out=m.tick(1,loan_signals=request(2))
        self.assertFalse(out['loan']['request_fire']);self.assertEqual(m.report()['debts']['sfu'],1)
        self.assertIsNone(m.snapshot()['ledger']['sfu']);self.assertFalse(m.can_supply('multihead_qk'))
    def test_abort_preserves_internal_division_debt_then_private_drain(self):
        m=Joint();m.tick(0,loan_signals=request());m.tick(1,abort=True)
        m.tick(2,loan_signals=dict(divider_accept_mask=65535));m.tick(3,loan_signals=dict(divider_pulse_mask=65535))
        out=m.tick(4,loan_signals=dict(vector_result_valid=True,result_token=10))
        self.assertTrue(out['loan']['private_drain']);self.assertFalse(out['loan']['publication_allowed'])
        self.assertEqual(m.report()['debts']['sfu'],0);self.assertTrue(m.report()['poisoned'])
    def test_abort_result_same_edge_and_no_reaccept(self):
        m=Joint();m.tick(0,loan_signals=request(mode='binary_add'))
        out=m.tick(1,abort=True,loan_signals=dict(vector_result_valid=True,result_token=10,external_result_ready=True))
        self.assertTrue(out['loan']['private_drain']);self.assertFalse(out['loan']['external_result_valid'])
        self.assertFalse(m.tick(2,loan_signals=request(2))['loan']['request_fire'])
    def test_error_poison_propagates_to_ledger_atomically(self):
        m=Joint();m.tick(0,loan_signals=request(mode='binary_add'))
        sig=dict(vector_result_valid=True,result_token=10,result_error=True,external_result_ready=True)
        self.unchanged(m,edge=1,loan_signals=sig,events=(event('begin_scratch',1,0,0),))
        m.tick(1,loan_signals=sig);self.assertTrue(m.report()['poisoned'])
    def test_identity_collision_rolls_back(self):
        m=Joint();m.tick(0,events=(event('matrix_begin',7),));m.tick(1,events=(event('matrix_command_accepted'),))
        self.unchanged(m,edge=2,loan_signals=request(9),events=(event('matrix_step_accepted',9),))
    def test_abort_input_and_nested_abort_rejected_atomically(self):
        for kw in (dict(abort=1),dict(loan_signals={'abort':False}),dict(events=(event('bank_ack',1,abort=True),)),dict(events=(event('bank_ack',1,True),)),dict(events=(event('bank_ack',1,False),)),dict(events=(event('matrix_result_ack',1,True),))):
            self.unchanged(Joint(),edge=0,**kw)
    def test_noncanonical_return_identities_rejected_atomically(self):
        for name in ('bank_return','bank_ack','matrix_return','matrix_result_ack'):
            for identity in (True,1.0,0,-1):
                self.unchanged(Joint(),edge=0,events=(event(name,identity),))
    def test_report_boundaries_and_snapshot_isolation(self):
        m=Joint();m.tick(0);s=m.snapshot();s['ledger']['poison']=True
        r=m.report();self.assertFalse(r['poisoned']);self.assertEqual(r['physical_sfu_pools'],1)
        for flag in ('attention_primitive_enabled','proposed_alu_enabled','numerical_execution','rtl_measured','accepted_80','accepted_90'):self.assertFalse(r[flag])
        self.assertEqual(r['parent_ticks'],1);self.assertNotIn('wall_cycles',r)

if __name__=='__main__':unittest.main()
