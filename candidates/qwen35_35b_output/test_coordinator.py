"""Control-only endpoint witnesses, not Matrix numerical acceptance."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from . import coordinator as c
from ..qwen35_gdn_prefill.projection_owner import Job

class CoordinatorTests(unittest.TestCase):
    def request(self,n=160):
        j=Job(m=16,k=4096,n=n,tag=35501,a=0x100000,b=0x200000,dst=0x2000000,
            activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=16*n*2)
        return c.FourReductionRequest(j,10,c.RANGES,True,(11,12,13,14),(15,16,17))

    def test_strict_four_range_identity(self):
        q=self.request();q.validate()
        for bad in (replace(q,partial_ids=(11,12,13,13)),replace(q,sum_ids=(15,16,11)),
                    replace(q,pair_reverse=False),replace(q,k_ranges=((0,2048),(2048,4096)))):
            with self.assertRaises(ValueError):bad.validate()

    def test_real_retirement_fences_require_three_sums_before_drain(self):
        o=c.FourReductionCoordinator();q=self.request()
        self.assertTrue(o.tick(request=q)['request_fire'])
        for block in range(4):
            self.assertEqual(o.state,'partialFlush');o.tick()
            p=o.ports();w=p['window_request']
            self.assertEqual((w.slot,w.k_begin,w.k_end,w.identity),
                (0 if block==0 else 1,*c.RANGES[block],q.partial_ids[block]))
            self.assertTrue(o.tick()['window_fire'])
            r=SimpleNamespace(tag=q.job.tag,identity=q.partial_ids[block],ng=0,rows=16,cols=160,
                slot=0 if block==0 else 1,k_begin=c.RANGES[block][0],k_end=c.RANGES[block][1],
                block_id=block+1,pair_reverse=True,committed=True,produced_beats=160,
                ddr_write_bytes=0,useful_macs=17,executed_macs=29,status=None)
            svc=c.Services(window_busy=True,lease_valid=True,tiles_leased=True)
            self.assertTrue(o.tick(window_result=r,services=svc)['window_result_fire'])
            if block==0:continue
            self.assertEqual(o.state,'sumIssue')
            call=o.ports(c.Services(tiles_leased=True))['sum_request']
            self.assertEqual(call.identity,q.sum_ids[block-1])
            self.assertEqual(call.lhs_phase,'partial' if block==1 else 'sum')
            self.assertTrue(o.tick(services=c.Services(tiles_leased=True))['sum_fire'])
            o.tick(sum_complete=True,services=c.Services(tiles_leased=True))
            self.assertEqual(o.state,'drainFlush' if block==3 else 'partialFlush')
        self.assertEqual((o.useful,o.executed),(4*17,4*29))
        o.tick();self.assertEqual(o.ports()['drain_request'].identity,17)
        self.assertTrue(o.tick()['drain_fire'])
        r=SimpleNamespace(tag=q.job.tag,identity=17,ng=0,rows=16,cols=160,consumed_beats=160,
            committed=True,ddr_write_bytes=q.job.write_bytes,useful_macs=0,executed_macs=0,status=None)
        o.tick(drain_result=r,services=c.Services(drain_busy=True))
        o.tick();o.tick();self.assertEqual(o.state,'reply')
        self.assertEqual(o.ports()['result'].write_bytes,q.job.write_bytes)
        self.assertFalse(o.poison)

    def test_wrong_partial_identity_and_unretired_sum_poison(self):
        o=c.FourReductionCoordinator();o.tick(request=self.request());o.tick();o.tick()
        r=SimpleNamespace(tag=35501,identity=999,ng=0,rows=16,cols=160,slot=0,k_begin=0,k_end=1024,
            block_id=1,pair_reverse=True,committed=True,produced_beats=160,ddr_write_bytes=0,
            useful_macs=0,executed_macs=0,status=None)
        o.tick(window_result=r,services=c.Services(window_busy=True,lease_valid=True,tiles_leased=True))
        self.assertTrue(o.poison)
        x=c.FourReductionCoordinator();x.tick(request=self.request());x.tick(sum_complete=True)
        self.assertTrue(x.poison)

if __name__=='__main__':unittest.main()
