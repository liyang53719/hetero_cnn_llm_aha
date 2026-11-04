"""Bounded protocol reference regressions, NOT RTL simulation/elaboration."""
from dataclasses import dataclass
from itertools import product
from pathlib import Path
import unittest

@dataclass
class Model:
    state: str = 'offer'
    visible: bool = False
    debt: bool = False
    aborting: bool = False
    quarantined: bool = False
    accepted: int = 0
    issued: int = 0
    returned: int = 0
    cancelled: int = 0
    terminal_count: int = 0
    terminal: tuple | None = None
    pending: bool = True
    coordinator_done: bool = False
    lease_active: bool = True
    payload: int = 0x1234
    def tick(self, *, abort=False, allow_offer=True, ready=False, poison=False,
             response=False, match=True, error=False, done_ready=True):
        old_visible=self.visible
        old_payload=self.payload
        if self.state in ('finish','locked'):
            # A held terminal cannot be rewritten by an asynchronous late fault.
            if self.terminal is None:
                assert not self.debt and not self.quarantined
                self.terminal=(self.aborting,self.accepted,self.returned)
            if done_ready and self.state=='finish':
                self.pending=False;self.state='locked';self.terminal_count+=1
                self.coordinator_done=True
                assert self.accepted==self.issued==self.returned
                self.lease_active=False
            self.aborting |= abort
            return dict(fire=False,ack=False,visible=False)
        self.aborting |= abort
        offer=self.state=='offer'
        visible=offer and (old_visible or (allow_offer and not self.aborting))
        cancel=self.aborting and offer
        # Explicit receiver ACK, or local ACK only if never published.
        receiver_cancel=cancel and visible
        receiver_ack=receiver_cancel and visible
        ack=cancel and not self.debt and ((not visible and not old_visible) or receiver_ack)
        fire=visible and ready and not poison and not receiver_cancel
        assert not (fire and ack)
        if old_visible and not(fire or ack):
            assert visible and old_payload==self.payload
        self.visible=visible and not(fire or ack)
        if fire:
            self.accepted+=1;self.issued+=1;self.debt=True;self.state='wait'
        if ack:
            self.cancelled+=1;self.state='finish'
        if response and self.state=='wait' and not self.quarantined:
            if not match:
                self.quarantined=True;self.aborting=True
            else:
                self.returned+=1;self.debt=False
                if self.aborting or error:
                    self.aborting=True;self.state='finish'
                else:
                    self.state='offer'
        assert self.returned<=self.issued<=self.accepted
        assert self.accepted-self.returned==int(self.debt)
        return dict(fire=fire,ack=ack,visible=visible)

class AbortContract(unittest.TestCase):
    def test_fresh_suppressed_offer_cancels_locally_without_accept(self):
        m=Model();e=m.tick(abort=True,ready=True)
        self.assertEqual((e['ack'],e['fire'],m.accepted),(True,False,0))
        m.tick();self.assertTrue(m.coordinator_done)
    def test_published_held_offer_cancel_ack_excludes_fire_even_ready(self):
        for ready,poison in product((False,True),repeat=2):
            m=Model();m.tick(ready=False);self.assertTrue(m.visible)
            e=m.tick(abort=True,ready=ready,poison=poison)
            self.assertTrue(e['visible']);self.assertTrue(e['ack']);self.assertFalse(e['fire'])
            self.assertEqual((m.accepted,m.issued,m.returned,m.cancelled),(0,0,0,1))
            m.tick();self.assertTrue(m.coordinator_done)
    def test_held_offer_survives_stall_before_abort(self):
        m=Model()
        for _ in range(32):
            e=m.tick();self.assertTrue(e['visible']);self.assertFalse(e['ack'])
        m.tick(abort=True);m.tick();self.assertTrue(m.coordinator_done)
    def test_accepted_debt_is_never_cancelled(self):
        m=Model();m.tick(ready=True)
        for _ in range(64):
            e=m.tick(abort=True,poison=True)
            self.assertFalse(e['ack']);self.assertTrue(m.debt);self.assertFalse(m.coordinator_done)
        m.tick(response=True);m.tick()
        self.assertEqual((m.accepted,m.issued,m.returned),(1,1,1))
        self.assertTrue(m.coordinator_done)
    def test_matching_return_and_fault_same_cycle(self):
        m=Model();m.tick(ready=True);m.tick(abort=True,response=True);m.tick()
        self.assertTrue(m.coordinator_done);self.assertEqual(m.accepted,1)
    def test_prior_return_then_abort_cancels_next_offer(self):
        m=Model();m.tick(ready=True);m.tick(response=True)
        m.tick(abort=True,poison=True);m.tick()
        self.assertEqual((m.accepted,m.returned,m.cancelled),(1,1,1))
        self.assertTrue(m.coordinator_done)
    def test_mismatched_return_does_not_repay_debt(self):
        m=Model();m.tick(ready=True);m.tick(response=True,match=False)
        for _ in range(64):m.tick(abort=True,response=True,match=True)
        self.assertTrue(m.quarantined);self.assertTrue(m.debt)
        self.assertEqual(m.returned,0);self.assertFalse(m.coordinator_done)
    def test_missing_external_return_is_explicitly_not_bounded(self):
        m=Model();m.tick(ready=True)
        for _ in range(128):m.tick(abort=True)
        self.assertTrue(m.pending and m.lease_active and m.debt)
        self.assertFalse(m.coordinator_done)
    def test_numerical_or_memory_error_return_is_counted_not_discarded(self):
        m=Model();m.tick(ready=True);m.tick(response=True,error=True);m.tick()
        self.assertEqual((m.accepted,m.returned),(1,1));self.assertTrue(m.coordinator_done)
    def test_single_terminal_under_backpressure_and_repeated_abort(self):
        m=Model();m.tick(abort=True);m.tick(done_ready=False)
        terminal=m.terminal
        for _ in range(32):m.tick(abort=True,done_ready=False);self.assertEqual(m.terminal,terminal)
        for _ in range(32):m.tick(abort=True)
        self.assertEqual(m.terminal_count,1)
    def test_no_abort_path_preserves_all_real_operations(self):
        m=Model()
        for _ in range(100):m.tick(ready=True);m.tick(response=True)
        self.assertEqual((m.accepted,m.issued,m.returned,m.cancelled),(100,100,100,0))
    def test_exhaustive_bounded_cancel_and_drain_positions(self):
        for held_stall,return_delay,poison in product(range(5),range(5),(False,True)):
            m=Model()
            for _ in range(held_stall):m.tick()
            m.tick(abort=True,ready=True,poison=poison);m.tick()
            self.assertTrue(m.coordinator_done)
            n=Model();n.tick(ready=True)
            for _ in range(return_delay):n.tick(abort=True,poison=poison)
            n.tick(abort=True,response=True);n.tick()
            self.assertTrue(n.coordinator_done)

class SourceBindings(unittest.TestCase):
    def text(self,n):return (Path(__file__).parent/'source'/n).read_text()
    def test_opt_in_receiver_ports_and_actual_mapping(self):
        top=self.text('HostBlockTopV4.scala');w=self.text('HostRuntimeChunkWiringV9.scala')
        self.assertIn('new SharedMemoryArbiter(17,if(enableChunk32)16 else -1)',top)
        self.assertIn('new UnifiedMoeSharedArithmeticAdapterV5(enableChunk32)',top)
        self.assertIn('hub.io.requests(i+12)',w)
        self.assertIn('val State=0; val Load=1; val Derived=2; val Transpose=3; val Execute=4',self.text('GdnRuntimeChunkLeafCollection.scala'))
    def test_leaf_wrapper_collection_kernel_abort_wires(self):
        for n,needle in [('GdnRuntimeChunkSelectedExecuteV1.scala','execute.io.abort32<>io.abort32'),('GdnRuntimeChunkLeafCollection.scala','execute.io.abort32<>io.abort32'),('QwenOwnerProtocol.scala','c.io.abort32<>port.abort32')]:self.assertIn(needle,self.text(n))
    def test_receiver_cancel_masks_acceptance_not_accepted_state(self):
        a=self.text('UnifiedMoeSharedArithmeticAdapterV5.scala');h=self.text('SharedMemoryArbiter.scala')
        self.assertIn('clientMayAccept(client) && !chunk32Cancel',a)
        self.assertIn('!chunk32ShapeBad && !chunk32Cancel',a)
        self.assertIn('io.requests(i).ready:=arb.io.in(i).ready && !io.cancel.get',h)
        self.assertIn('assert(!(io.cancelled.get && io.requests(i).fire))',h)
        self.assertEqual(a.count('new UnifiedVectorElement32BankV4'),1)
    def test_whole_abort_reflection_is_registered(self):
        w=self.text('HostRuntimeChunkWiringV9.scala')
        self.assertIn('p.abort32.abort:=RegNext(enableChunk32.B &&',w)
    def test_wrong_transport_tag_is_not_retagged_and_delivered_in_opt_in_mode(self):
        h=self.text('SharedMemoryArbiter.scala')
        self.assertIn('when(!tagMatches){quarantine:=true.B}.otherwise{',h)
        self.assertIn('state === awaitResponse && (if(cancellationClient>=0) !quarantine else true.B)',h)
    def test_leaf_never_reports_live_debt_as_drained_terminal(self):
        l=self.text('GdnRuntimeChunkExecuteOwner32V1.scala')
        self.assertIn('io.done.valid:=state===finish && drained && !quarantine',l)
        self.assertIn('quarantine:=true.B;status:=Status.Protocol.U',l)
        self.assertIn('assert(!(io.abort32.memoryCancelled && io.memory.fire))',l)
        self.assertIn('assert(!(io.abort32.vectorCancelled && io.vectorRequest.fire))',l)
        self.assertEqual(l.count('Reg(UInt(1024.W))'),3)
    def test_coordinator_counts_matched_partial_execution_once(self):
        c=self.text('GdnRuntimeChunkCoordinator.scala')
        start=c.index('  when(io.executeDone.fire)');end=c.index('  val expectedHeadChunks',start)
        self.assertEqual(c[start:end].count('account(r.receipt)'),2)
        self.assertIn('when(exact){retire(r.receipt.drained);if(enableExecute32Abort){account(r.receipt)}}',c[start:end])
        self.assertIn('if(!enableExecute32Abort){account(r.receipt)}',c[start:end])

if __name__=='__main__':unittest.main(verbosity=2)
