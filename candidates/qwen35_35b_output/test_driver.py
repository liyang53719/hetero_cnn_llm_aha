"""Actual Matrix/Vector/DDR four-slab witnesses, no checkpoint or RTL.

Sparse BF16 terms force left-fold != balanced and make each source row unique.
Full K4096 is executed; N32/N288 are bounded synthetic output dimensions.
"""
import os,struct,time,unittest
from .driver import TypedStreamingProjectionDriver,TypedStreamingUpstreamDriver,FourProfile
from .streaming_owner import StreamingProjectionOwner,NoPrefixWorkspace
from ..qwen35_gdn_prefill import typed_dense as d,test_typed_dense as numeric
from ..qwen35_gdn_prefill.chunk.vector import Vector16,IEEE_POLICY
from ..qwen2_resident_matrix.dense_block_reduce.profile import ReductionProfile

def setUpModule():numeric.setUpModule()

def bf(x):return struct.unpack('<I',struct.pack('<f',float(x)))[0]>>16

class FourDriverTests(unittest.TestCase):
    def fixture(self,m=16,n=32,upstream=False):
        self.assertEqual(numeric.LIB.td_reset(),0)
        matrix=d.MatrixService(numeric.LIB)
        vector=Vector16(os.environ['GDN_VECTOR16_LIBRARY'],exception_policy=IEEE_POLICY)
        owner=StreamingProjectionOwner(NoPrefixWorkspace(0x100000000,16384,1,2048))
        memory=d.TypedMemory()
        a=bytearray(m*4096*2)
        for row in range(m):
            for k,val in ((0,33554432),(1024,1),(2048,-33554432),(3072,row+1)):
                struct.pack_into('<H',a,(row*4096+k)*2,bf(val))
        memory.add_readonly(0x100000,bytes(a))
        memory.add_readonly(0x200000,struct.pack('<H',bf(1))*(4096*n))
        memory.allocate_output(0x2000000,m*n*2)
        job=d.down.Job(m=m,k=4096,n=n,tag=35501,a=0x100000,b=0x200000,dst=0x2000000,
            activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=m*n*2)
        if upstream:
            aid,bid,did=0x3000000,0x3100000,0x3200000
            memory.add_readonly(aid,bytes(m*2048*2));memory.add_readonly(bid,bytes(2048*32*2))
            memory.allocate_output(did,m*32*2)
            prior=d.down.Job(m=m,k=2048,n=32,tag=35001,a=aid,b=bid,dst=did,
                activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=m*32*2)
            old=TypedStreamingUpstreamDriver(owner,matrix,memory,prior,vector=vector,
                profile=ReductionProfile('upstream_test',((0,1024),(1024,2048)),True,'0'*64),sum_identity=36001)
            self.finish(old)
            self.assertEqual(old.response,(35001,None,m*32*2))
            self.assertEqual(old.output.raw(),bytes(m*32*2));self.assertFalse(owner.tiles.leased)
        driver=TypedStreamingProjectionDriver(owner,matrix,memory,job,vector=vector,
            profile=FourProfile('synthetic_four_k1024_leftfold','0'*64),role='synthetic')
        return driver

    def finish(self,x,hook=None):
        until=time.monotonic()+90
        for tick in range(2000000):
            self.assertLess(time.monotonic(),until,'bounded synthetic actual transport')
            x.tick(**({} if hook is None else hook(x,tick)))
            if x.response is not None:return x.report()
        self.fail('transport watchdog')

    def check(self,m,n):
        x=self.fixture(m,n);identity=x.bank_identity
        r=self.finish(x)
        expected=b''.join(struct.pack('<H',bf(row+1))*n for row in range(m))
        self.assertEqual(x.output.raw(),expected)
        self.assertEqual(x.response,(35501,None,m*n*2));self.assertTrue(x.output.published)
        windows=(n+159)//160
        self.assertEqual(len(r['partials']),4*windows);self.assertEqual(len(r['drains']),windows)
        self.assertEqual(r['a_load_fences'],4*windows)
        self.assertEqual(r['vector_add_calls'],3*m*n//16)
        self.assertEqual(r['executed_fmas'],4096*(n//32)*4096)
        self.assertEqual(r['counts']['a_read_beats'],4*windows*m*1024//32)
        self.assertEqual(r['counts']['ack_bytes'],m*n*2)
        self.assertEqual(identity,x.bank_identity);self.assertFalse(x.owner.tiles.leased)
        self.assertIsNone(x.matrix.owner);self.assertIsNone(x.loan.vector.client)
        self.assertFalse(r['seeded_prefix_used']);self.assertEqual(r['private_prefix_bytes'],0)
        return x

    def test_m16_full_k4096_tail_n128_and_leftfold(self):self.check(16,288)
    def test_m128_full_k4096_one_context(self):self.check(128,32)

    def test_upstream_two_partial_then_four_partial_same_owner(self):
        x=self.fixture(upstream=True);epoch=x.matrix.epoch
        r=self.finish(x)
        expected=b''.join(struct.pack('<H',bf(row+1))*32 for row in range(16))
        self.assertEqual(x.output.raw(),expected)
        self.assertEqual(x.matrix.epoch,epoch);self.assertTrue(x.output.published)
        self.assertEqual(x.matrix.counts['owner_acquires'],6)

    def test_abort_held_success_and_last_ack_error(self):
        for mode in ('held_success','last_ack'):
            x=self.fixture()
            def hook(d,t):
                if mode=='held_success':
                    return dict(response_ready=False,abort=d.coordinator.state=='reply') if not d.aborted else {}
                last=d.pending_ack is not None and d.counts['ack_bytes']+d.pending_ack.nbytes==d.job.write_bytes
                return dict(ack_error=last)
            r=self.finish(x,hook)
            self.assertIsNotNone(x.response[1]);self.assertFalse(x.output.published)
            self.assertIsNone(x.memory.pending);self.assertIsNone(x.matrix.owner)

if __name__=='__main__':unittest.main()
