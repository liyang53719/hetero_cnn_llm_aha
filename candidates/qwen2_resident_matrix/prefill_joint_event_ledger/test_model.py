import unittest
from model import Ledger, Violation, INTERFACES

class Tests(unittest.TestCase):
    def make(self):
        m=Ledger();m.advance(0);return m
    def tick(self,m):m.advance(m.edge+1)
    def scratch(self):
        m=self.make();m.begin_scratch(1,0,0);self.tick(m);return m
    def matrix(self):
        m=self.make();m.matrix_begin(1);self.tick(m);m.matrix_command_accepted();self.tick(m);return m
    def resolve(self,m,ticket,expected):
        self.tick(m);self.assertEqual(m.resolve_publication(ticket),expected)
    def test_raw_write_not_rmw_and_clean_ack_publication(self):
        m=self.scratch();c=m.context;m.raw_accept(1,4096,True,c)
        self.assertFalse(m.reads);self.assertEqual(m.writes,{0:512,1:512});self.assertFalse(m.reserved)
        self.tick(m);m.bank_return(1)
        with self.assertRaises(Violation):m.bank_ack(1)
        self.tick(m);ticket=m.bank_ack(1)
        self.assertNotIn(4096,m.written)
        with self.assertRaises(Violation):m.resolve_publication(ticket)
        with self.assertRaises(Violation):bool(ticket)
        self.resolve(m,ticket,True);self.assertIn(4096,m.written)
        m.raw_accept(2,4096,False,c);self.assertEqual(m.reads,{0:512,1:512})
    def test_rmw_next_write_no_fictitious_response_ack(self):
        m=self.make();m.rmw_accept(1,768)
        self.assertEqual(len(m.reads),16);self.assertEqual(len(m.reserved[1]),16)
        self.tick(m);self.assertEqual(len(m.writes),16);self.assertFalse(m.bank_debts)
        with self.assertRaises(Violation):m.external_bank_access(0,900,True)
        with self.assertRaises(Violation):m.bank_return(1)
        with self.assertRaises(Violation):m.bank_ack(1)
    def test_bank_conflicts_and_distinct_ports(self):
        m=self.make();m.external_bank_access(0,20,False)
        with self.assertRaises(Violation):m.external_bank_access(0,21,False)
        with self.assertRaises(Violation):m.external_bank_access(0,20,True)
        m.external_bank_access(1,20,False)
        with self.assertRaises(Violation):m.external_bank_access(0,21,True)
    def test_raw_lease_blocks_dense_tile_and_same_edge_begin(self):
        m=self.make();m.begin_scratch(1,16,1)
        with self.assertRaises(Violation):m.raw_accept(1,4096,True,m.context)
        self.tick(m)
        with self.assertRaises(Violation):m.rmw_accept(1,768)
        with self.assertRaises(Violation):m.external_bank_access(15,800,True)
        with self.assertRaises(Violation):m.raw_accept(1,4096,False,m.context)
        with self.assertRaises(Violation):m.raw_accept(1,4096,True,(2,16,1))
        m.raw_accept(1,4191,True,m.context)
        with self.assertRaises(Violation):m.raw_accept(2,4097,True,m.context)
        with self.assertRaises(Violation):m.release_scratch()
    def test_parent_tick_once_and_monotonic_edges(self):
        m=self.make();m.parent_tick()
        with self.assertRaises(Violation):m.parent_tick()
        with self.assertRaises(Violation):m.advance(0)
        with self.assertRaises(Violation):m.advance(2)
        self.tick(m);m.parent_tick();self.assertEqual(m.parent_ticks,2)
    def test_abort_ack_both_orders_never_publish(self):
        for abort_first in (False,True):
            m=self.scratch();m.raw_accept(1,4096,True,m.context)
            self.tick(m);m.bank_return(1);self.tick(m)
            if abort_first:m.abort()
            ticket=m.bank_ack(1)
            if not abort_first:m.abort()
            self.resolve(m,ticket,False);self.assertNotIn(4096,m.written)
    def test_abort_does_not_cancel_physical_rmw(self):
        m=self.make();m.rmw_accept(1,768);m.advance(1,abort=True)
        self.assertFalse(m.bank_debts);self.assertTrue(m.history[-1]['physical_commit'])
    def test_matrix_eight_metadata_credits(self):
        m=self.matrix()
        for i in range(2,10):m.matrix_step_accepted(i);self.tick(m)
        with self.assertRaises(Violation):m.matrix_step_accepted(10)
        with self.assertRaises(Violation):m.matrix_return(3)
        m.matrix_return(2);self.assertEqual(len(m.matrix_steps),7)
    def test_matrix_single_port_fires(self):
        m=self.matrix();m.matrix_step_accepted(2,emit=True)
        with self.assertRaises(Violation):m.matrix_step_accepted(3,emit=True)
        self.tick(m);m.matrix_step_accepted(3,last=True,emit=True)
        self.tick(m);m.matrix_return(2)
        with self.assertRaises(Violation):m.matrix_return(3)
        self.tick(m);m.matrix_return(3);self.tick(m);m.matrix_result_ack(2)
        with self.assertRaises(Violation):m.matrix_result_ack(3)
    def test_matrix_two_result_slots_completion_and_hold(self):
        m=self.matrix()
        for i in (2,3,4):m.matrix_step_accepted(i,last=i==4,emit=True);self.tick(m)
        m.matrix_return(2);self.tick(m);m.matrix_return(3);self.tick(m)
        with self.assertRaises(Violation):m.matrix_return(4)
        m.matrix_result_ack(2);m.matrix_return(4);self.tick(m)
        m.matrix_result_ack(3);self.tick(m);m.matrix_result_ack(4);self.tick(m)
        with self.assertRaises(Violation):m.matrix_done_ack()
        m.matrix_completion_accepted()
        with self.assertRaises(Violation):m.matrix_done_ack()
        self.tick(m);ticket=m.matrix_done_ack()
        with self.assertRaises(Violation):m.matrix_begin(5)
        self.resolve(m,ticket,True)
    def test_matrix_group_command_not_free(self):
        m=self.make();m.matrix_begin(1)
        with self.assertRaises(Violation):m.matrix_command_accepted()
        self.tick(m)
        with self.assertRaises(Violation):m.matrix_step_accepted(2)
        m.matrix_command_accepted()
        with self.assertRaises(Violation):m.matrix_step_accepted(2)
    def test_matrix_abort_before_last_discards_new_returns(self):
        m=self.matrix();m.matrix_step_accepted(2,emit=True);m.advance(m.edge+1,abort=True);self.tick(m)
        m.matrix_return(2);self.assertFalse(m.matrix_results);self.tick(m)
        with self.assertRaises(Violation):m.matrix_done_ack()
        self.tick(m);ticket=m.matrix_done_ack();self.resolve(m,ticket,False)
    def test_matrix_abort_retains_preexisting_result_debt(self):
        m=self.matrix();m.matrix_step_accepted(2,last=True,emit=True);self.tick(m);m.matrix_return(2)
        m.abort();self.tick(m)
        with self.assertRaises(Violation):m.matrix_done_ack()
        ticket=m.matrix_result_ack(2);self.resolve(m,ticket,False)
        done=m.matrix_done_ack();self.resolve(m,done,False)
    def test_sfu_shared_pool_and_pulse_reservation(self):
        m=self.make();m.sfu_accept(1,'attention',3,division=True)
        with self.assertRaises(Violation):m.sfu_accept(2,'silu',65535)
        self.tick(m);m.divider_pulse(1,0)
        with self.assertRaises(Violation):m.divider_pulse(1,0)
        with self.assertRaises(Violation):m.divider_pulse(1,2)
        with self.assertRaises(Violation):m.sfu_return(1)
        m.divider_pulse(1,1)
        with self.assertRaises(Violation):m.sfu_return(1)
        self.tick(m);m.sfu_return(1);self.tick(m);ticket=m.sfu_ack(1)
        with self.assertRaises(Violation):m.sfu_accept(2,'silu',65535)
        self.resolve(m,ticket,True)
    def test_sfu_abort_drains_and_primitive_label_is_proposed(self):
        m=self.make();m.sfu_accept(1,'silu',1,division=True)
        self.assertEqual(m.history[-1]['interface'],'proposed');m.advance(m.edge+1,abort=True)
        m.divider_pulse(1,0);self.tick(m);m.sfu_return(1);self.tick(m)
        ticket=m.sfu_ack(1);self.resolve(m,ticket,False)
        n=self.make();n.sfu_accept(1,'silu',65535)
        self.assertEqual(n.history[-1]['interface'],'actual-Chisel')
    def test_alu_held_and_abort_after_ack_same_edge(self):
        m=self.make();m.alu_accept(1,'add',65535)
        with self.assertRaises(Violation):m.alu_accept(2,'mul',1)
        self.tick(m);m.alu_return(1);self.tick(m);ticket=m.alu_ack(1);m.abort()
        self.resolve(m,ticket,False)
    def test_no_ack_edge_bank_or_lease_reuse(self):
        m=self.scratch();m.raw_accept(1,4096,True,m.context)
        self.tick(m);m.bank_return(1);self.tick(m);m.bank_ack(1)
        with self.assertRaises(Violation):m.raw_accept(2,4096,False,m.context)
        with self.assertRaises(Violation):m.release_scratch()
        self.tick(m);m.release_scratch()
        with self.assertRaises(Violation):m.begin_scratch(2,0,0)
    def test_abort_and_new_accept_are_rejected_in_both_orders(self):
        for first in (True,False):
            m=self.make()
            if first:
                m.abort()
                with self.assertRaises(Violation):m.sfu_accept(1,'silu',65535)
            else:
                m.sfu_accept(1,'silu',65535)
                with self.assertRaises(Violation):m.abort()
    def test_lease_release_edge_and_acquire_after_dense_forbidden(self):
        m=self.scratch();m.release_scratch()
        with self.assertRaises(Violation):m.rmw_accept(1,768)
        with self.assertRaises(Violation):m.external_bank_access(0,20,False)
        n=self.make();n.external_bank_access(0,20,False)
        with self.assertRaises(Violation):n.begin_scratch(1,0,0)
    def test_abort_clears_scratch_written_and_active(self):
        m=self.scratch();m.raw_accept(1,4096,True,m.context)
        self.tick(m);m.bank_return(1);self.tick(m);m.bank_ack(1);self.tick(m)
        self.assertIn(4096,m.written);m.abort()
        self.assertFalse(m.written);self.assertFalse(m.scratch_active)
        self.assertIsNotNone(m.context) # lease retained for explicit drain/release
    def test_empty_matrix_abort_does_not_finish_same_edge(self):
        m=self.matrix();m.abort()
        with self.assertRaises(Violation):m.matrix_done_ack()
        self.tick(m)
        with self.assertRaises(Violation):m.matrix_done_ack()
        self.tick(m);ticket=m.matrix_done_ack();self.resolve(m,ticket,False)
    def test_matrix_first_abort_edge_uses_preedge_credit_and_enqueues(self):
        for abort_first in (True,False):
            m=self.matrix();m.matrix_step_accepted(2,emit=True);self.tick(m)
            if abort_first:m.abort()
            m.matrix_return(2)
            if not abort_first:m.abort()
            self.assertIn(2,m.matrix_results)
        m=self.matrix()
        for i in (2,3,4):m.matrix_step_accepted(i,emit=True);self.tick(m)
        m.matrix_return(2);self.tick(m);m.matrix_return(3)
        m.advance(m.edge+1,abort=True)
        with self.assertRaises(Violation):m.matrix_return(4)
        self.tick(m);m.matrix_return(4)
        self.assertEqual(len(m.matrix_results),2)
    def test_tile_service_blocks_dense_even_on_other_port_address(self):
        m=self.make();m.rmw_accept(1,768)
        with self.assertRaises(Violation):m.external_bank_access(0,900,True)
        self.tick(m)
        with self.assertRaises(Violation):m.external_bank_access(0,900,False)
        n=self.make();n.external_bank_access(0,900,True)
        with self.assertRaises(Violation):n.rmw_accept(1,768)
    def test_unmapped_staging_never_supplies_and_no_cycle_claim(self):
        m=self.make();self.assertFalse(m.can_supply('Q128'));r=m.report()
        self.assertTrue(r['unresolved_prerequisites']);self.assertFalse(r['rtl_measured'])
        self.assertFalse(r['accepted_80']);self.assertFalse(r['accepted_90']);self.assertNotIn('wall_cycles',r)
        self.assertEqual(r['event_provenance'],'synthetic_external')
        self.assertEqual(set(INTERFACES.values()),{'actual-Chisel','source-candidate-not-wired','proposed'})

if __name__=='__main__':unittest.main()
