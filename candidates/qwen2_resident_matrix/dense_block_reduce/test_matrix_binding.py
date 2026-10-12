"""Explicit profile binding to the existing real serialized Matrix recipe."""
from dataclasses import replace
import os
import unittest
from .profile import ReductionProfile,QWEN2_QKV_PROFILE
from .matrix_binding import ProfiledMatrixService
from .dense_drain import DenseReductionOwner,Job,drain
from .k_window_model import KWindowRequest
from .test_k_window import ActualMatrixHarness
from ..official_bf16.test_owners import verified_library
from ..ffn_public.prefix_owners import Job as PublicJob


class ProfileTests(unittest.TestCase):
    def test_generic_even_ranges_are_explicit_not_a_universal_1024(self):
        for k,spans in ((32,((0,16),(16,32))),(128,((0,64),(64,128))),
                        (1536,((0,1024),(1024,1536)))):
            ReductionProfile('fixture',spans,True,'0'*64).validate(k)
        for q in (replace(QWEN2_QKV_PROFILE,ranges=((0,1024),(1026,1536))),
                  replace(QWEN2_QKV_PROFILE,ranges=((0,1023),(1023,1536))),
                  replace(QWEN2_QKV_PROFILE,ranges=((0,512),(512,1024))),
                  replace(QWEN2_QKV_PROFILE,pair_reverse=1),
                  replace(QWEN2_QKV_PROFILE,source_sha256='x'*64)):
            with self.assertRaises(ValueError):q.validate(1536)


class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('MATRIX_SERVICE_LIBRARY'):
            raise AssertionError('explicit freshly built Matrix recipe and compile receipt required')
        cls.lib=verified_library()

    def setup_case(self):
        self.assertEqual(self.lib.td_reset(),0)
        s=ProfiledMatrixService(self.lib,QWEN2_QKV_PROFILE)
        public=PublicJob('Dense',13,0x100000,0x400000,0x4000000,16,256,1536,16*256*4,
                         weight_bf16=True)
        s.bind_dense_job(public,'k_raw')
        j=Job(m=16,k=1536,n=256,tag=13,a=public.a,b=public.b,dst=public.dst,
              activation_bf16=False,weight_bf16=True,write_bytes=public.write_bytes)
        o=DenseReductionOwner(drain.PrefixWorkspace(0x10000000,786432,11),
            enable_dense_drain=True,enable_k_window=True,enable_ffn_drain=True,
            enable_ffn_window=True,enable_ffn_tiles=True)
        q=KWindowRequest(j,7,0,32,0,k_begin=0,k_end=1024,block_id=1,pair_reverse=True)
        return s,o,q

    def test_actual_two_partial_requests_keep_binding_and_resource(self):
        s,o,q=self.setup_case();resource=s.resource_address
        h=ActualMatrixHarness(instance=o,service=s,
            source=lambda kind,row,col:0x3f800000 if kind=='a' else 0x3f81)
        h.submit(q);self.assertIsNone(h.finish().status)
        h.submit(replace(q,k_begin=1024,k_end=1536,slot=1,block_id=2,reuse_a=True))
        self.assertIsNone(h.finish().status)
        self.assertEqual(s.resource_address,resource)
        self.assertEqual(s.report()['counters']['dense_groups'],2)
        self.assertEqual(s.report()['counters']['owner_releases'],2)
        self.assertIsNone(s.owner)

    def test_range_pair_job_and_seed_mismatch_rejected_before_group(self):
        for change in (dict(k_begin=0,k_end=512),dict(pair_reverse=False),dict(block_id=2),
                       dict(job=None)):
            s,o,q=self.setup_case()
            if 'job' in change:change['job']=replace(q.job,b=q.job.b+64)
            bad=replace(q,**change)
            self.assertTrue(s.acquire(o,'dense',q.job.tag))
            facade=s.dense_library(o)
            self.assertTrue(o.tick(window=bad)['window_fire'])
            with self.assertRaises(ValueError):facade.td_group(0,bad.k_end-bad.k_begin,1)
            with self.assertRaises(ValueError):facade.td_seed_begin(0)
            self.assertEqual(s.report()['dense_fma_calls'],0)


if __name__=='__main__':unittest.main()
