"""Real shared-bank and vector-loan composition; no Matrix/Host/RTL claim."""
from dataclasses import replace
import unittest
from .sum_tiles import SumInvocation, TileSumController, shared_loan_edge, owner_tile_edge
from . import vector_add_model as vector
from .sum_tiles import TileBankModel, Control, Read, Write
from ..ffn_public.test_prefix_owners import ref_add


def load(banks, call, slot, packets):
    assert banks.tick(control=Control(0,slot,call.identity,call.ng,call.rows,call.cols))["ctl_fire"]
    for index, words in enumerate(packets):
        assert banks.tick(write=Write(slot,call.identity,call.ng,index,words))["write_fire"]
        assert banks.tick()["rmw_commit"]
    assert banks.tick(control=Control(1,slot,call.identity,call.ng,call.rows,call.cols))["ctl_fire"]


def packets(call, base):
    # Finite, non-BF16 FP32 values exercise preservation of low fraction bits.
    return [tuple(base + (i*16+n) % 4096 for n in range(16)) for i in range(call.beats)]


class Harness:
    def __init__(self, call=SumInvocation(3,32,16,32), lane_latency=2, overflow=False):
        self.call=call
        self.banks=TileBankModel()
        self.lhs=packets(call,0x3f801234);self.rhs=packets(call,0x33012345)
        if overflow:
            self.lhs[0] = self.rhs[0] = (0x7f7fffff,) * 16
        load(self.banks,call,call.lhs_slot,self.lhs);load(self.banks,call,call.rhs_slot,self.rhs)
        self.controller=TileSumController(self.banks)
        self.loan=vector.VectorLoanModel(lane_latency=lane_latency)
        self.initial_counters=dict(self.banks.counters)
        self.edges=[]

    def tick(self, **kwargs):
        edge=shared_loan_edge(self.controller,self.loan,**kwargs)
        self.edges.append(edge)
        return edge

    def complete(self, **kwargs):
        assert self.tick(start=self.call)["start_fire"]
        for i in range(self.call.beats*40+100):
            e=self.tick(bank_ready=(i%7!=0),**kwargs)
            if e["complete"]:return e
        raise AssertionError("bounded software composition did not complete")

    def read_result(self):
        out=[]
        for i in range(self.call.beats):
            assert self.banks.tick(read=Read(self.call.output_slot,self.call.identity,self.call.ng,i))["read_fire"]
            self.banks.tick(response_ready=False)
            e=self.banks.tick()
            assert e["response_fire"]
            out.append(e["response"].words)
        return out


class TileSumTests(unittest.TestCase):
    def test_owner_callback_has_one_owner_and_one_bank_edge_per_tick(self):
        from .test_dense_drain import owner
        o=owner();call=SumInvocation(7,0,16,32)
        a,b=packets(call,0x3f801234),packets(call,0x33012345)
        load(o.tiles,call,0,a);load(o.tiles,call,1,b)
        c=TileSumController(o.tiles,bank_tick=lambda **p:owner_tile_edge(o,**p))
        loan=vector.VectorLoanModel()
        before_o,before_b=o.clock,o.tiles.cycle
        count=1
        self.assertTrue(shared_loan_edge(c,loan,start=call)['start_fire'])
        for index in range(4000):
            edge=shared_loan_edge(c,loan,bank_ready=index%7!=0);count+=1
            if edge['complete']:break
        else:self.fail('owner callback completion')
        self.assertEqual(o.clock-before_o,count)
        self.assertEqual(o.tiles.cycle-before_b,count)
        self.assertEqual(c.counts['completed'],1)

    def test_actual_words_all_three_slot_rotations_and_rne(self):
        for slots in ((0,1,2),(2,0,1),(1,2,0)):
            h=Harness(SumInvocation(7,64,16,32,*slots))
            underlying=h.banks.banks
            h.complete()
            self.assertIs(h.banks.banks,underlying)
            expected=[tuple(ref_add(a,b) for a,b in zip(x,y)) for x,y in zip(h.lhs,h.rhs)]
            self.assertEqual(h.read_result(),expected)
            self.assertTrue(any(w&65535 for row in expected for w in row))
            self.assertEqual(h.controller.counts["add_requests"],h.call.beats)
            self.assertEqual(h.controller.counts["add_results"],h.call.beats)
            self.assertEqual(h.controller.counts["accepted_operand_beats"],2*h.call.beats)
            self.assertEqual(len(h.loan.issued),h.call.beats)
            self.assertTrue(all(op=="add" for req in h.loan.issued for op,_,_ in req))

    def test_m128_n160_traffic_counts_all_bank_ports(self):
        h=Harness(SumInvocation(5,128,128,160));h.complete()
        n=h.call.beats;b=h.banks.counters;a=h.initial_counters
        self.assertEqual(b["read_requests"]-a["read_requests"],2*n)
        self.assertEqual(b["write_requests"]-a["write_requests"],n)
        self.assertEqual(b["physical_read_bytes"]-a["physical_read_bytes"],3*n*512)
        self.assertEqual(b["physical_write_bytes"]-a["physical_write_bytes"],n*512)
        self.assertEqual(b["logical_read_bytes"]-a["logical_read_bytes"],2*n*64)
        self.assertEqual(b["logical_write_bytes"]-a["logical_write_bytes"],n*64)
        self.assertTrue(all(len(e["bank"]["reads"])<=16 and len(e["bank"]["writes"])<=16 for e in h.edges))
        self.assertEqual(h.controller.counts["completed"],1)

    def test_request_and_result_hold_do_not_change_packets(self):
        h=Harness(lane_latency=5);self.assertTrue(h.tick(start=h.call)["start_fire"])
        hold=0
        for _ in range(4000):
            p=h.loan.ports();stall=p["result_valid"] and hold<11
            if stall:hold+=1
            e=h.tick(bank_ready=not stall)
            if e["complete"]:break
        else:self.fail("completion")
        self.assertEqual(hold,11)
        self.assertEqual(h.controller.counts["add_requests"],h.call.beats)
        self.assertEqual(h.read_result(),[tuple(ref_add(a,b) for a,b in zip(x,y)) for x,y in zip(h.lhs,h.rhs)])

    def test_completion_only_after_rmw_seal_and_releases(self):
        h=Harness();h.complete();c=h.call;t=h.banks.tags[c.output_slot]
        self.assertTrue(t.sealed and t.live)
        self.assertEqual((t.produced,t.consumed),(c.beats,0))
        self.assertFalse(h.banks.tags[c.lhs_slot].live or h.banks.tags[c.rhs_slot].live)
        self.assertTrue(h.banks.idle and h.loan.ports()["drained"])
        self.assertFalse(any(e["complete"] for e in h.edges[:-1]))

    def test_illegal_invocation_does_not_start_bank_writes(self):
        for q in (SumInvocation(0,32,16,32),SumInvocation(3,33,16,32),
                  SumInvocation(3,32,17,32),SumInvocation(3,32,16,16),
                  SumInvocation(3,32,16,32,0,0,2),SumInvocation(4,32,16,32)):
            h=Harness();before=dict(h.banks.counters)
            self.assertTrue(h.tick(start=q)["start_fire"])
            self.assertTrue(h.controller.poison)
            self.assertEqual(h.banks.counters["write_requests"],before["write_requests"])
            self.assertFalse(h.tick(start=h.call)["start_fire"])

    def test_busy_external_resource_stalls_admission(self):
        h=Harness()
        self.assertFalse(h.tick(start=h.call,bank_ready=False)["start_fire"])
        self.assertEqual(h.controller.state,"idle")
        self.assertTrue(h.tick(start=h.call)["start_fire"])

    def test_abort_with_accepted_loan_drains_before_locked(self):
        h=Harness(lane_latency=8);h.tick(start=h.call)
        for _ in range(100):
            e=h.tick()
            if e["request_fire"]:break
        self.assertTrue(h.controller.inflight)
        e=h.tick(abort=True)
        self.assertFalse(e["complete"]);self.assertEqual(h.controller.state,"drain")
        for _ in range(40):
            e=h.tick()
            self.assertFalse(e["complete"])
            if h.controller.state=="locked":break
        self.assertEqual(h.controller.state,"locked")
        self.assertTrue(h.loan.ports()["drained"])
        self.assertFalse(h.banks.tags[h.call.output_slot].sealed)
        self.assertFalse(h.tick(start=h.call)["start_fire"])

    def test_abort_same_edge_as_final_result_or_completion_never_publishes(self):
        for target in ("last_result","retire"):
            h=Harness();h.tick(start=h.call)
            for _ in range(4000):
                hit=(h.controller.state=="retire" if target=="retire" else
                     h.controller.index==h.call.beats-1 and h.loan.ports()["result_valid"])
                e=h.tick(abort=hit)
                self.assertFalse(e["complete"])
                if hit:break
            else:self.fail(target)
            self.assertTrue(h.controller.poison)
            self.assertEqual(h.controller.counts["completed"],0)

    def test_overflow_response_poison_has_no_output_write(self):
        # Legitimate typed finite inputs arrive through the real bank writes.
        h=Harness(overflow=True)
        h.tick(start=h.call)
        retired_error=False
        for _ in range(100):
            e=h.tick()
            if e["result_fire"]:
                self.assertFalse(e["loan_abort"])
                self.assertFalse(e["bank"]["write_fire"])
                retired_error=True
            if h.controller.state=="locked":break
        self.assertTrue(retired_error)
        self.assertTrue(h.controller.poison)
        self.assertEqual(h.controller.counts["output_beats"],0)
        self.assertEqual(h.controller.counts["completed"],0)

    def test_bank_poison_with_held_final_result_drains_without_false_fire(self):
        for kind in ("bank", "controller", "response"):
            h=Harness();h.tick(start=h.call)
            for _ in range(4000):
                if h.controller.index==h.call.beats-1 and h.loan.ports()["result_valid"]:
                    break
                h.tick()
            else:self.fail("held final result")
            if kind=="bank":h.banks.poison=True
            elif kind=="controller":h.controller.poison=True
            else:
                from ..ffn_window.model import Response
                h.banks.response=Response(h.call.lhs_slot,h.call.identity,h.call.ng,
                                          h.call.beats-1,(0,)*16,True)
            e=h.tick()
            self.assertTrue(e["loan_abort"])
            self.assertFalse(e["result_fire"] or e["complete"] or e["bank"]["write_fire"])
            for _ in range(40):
                e=h.tick()
                self.assertFalse(e["complete"])
                if h.controller.state=="locked":break
            self.assertEqual(h.controller.state,"locked")
            self.assertTrue(h.loan.ports()["drained"])
            self.assertEqual(h.controller.counts["completed"],0)
            self.assertFalse(h.banks.tags[h.call.output_slot].sealed)

    def test_coordinated_reset_recovers_without_publishing_old_tile(self):
        h=Harness();h.tick(start=h.call)
        for _ in range(15):h.tick()
        h.tick(coordinated_reset=True)
        self.assertFalse(any(t.live for t in h.banks.tags))
        self.assertFalse(h.controller.poison or h.loan.ports()["reset_required"])
        load(h.banks,h.call,0,h.lhs);load(h.banks,h.call,1,h.rhs)
        h.complete()
        self.assertEqual(h.controller.counts["completed"],1)


if __name__=="__main__":unittest.main()

