"""Fast numerical boundary and authority tests; no model capture or RTL build."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pack_host_bf16_gdn_fixture import GdnFixtureSession, CHANNELS, bf16, conv_recipe, ulp_metric


class HostGdnFixtureTests(unittest.TestCase):
    def test_signed_zeros_remain_raw_bit_differences(self):
        metric=ulp_metric(np.array([0,0x8000,0x3f80],dtype='<u2'),np.array([0x8000,0,0x3f81],dtype='<u2'))
        self.assertEqual(metric['bit_mismatches'],3)
        self.assertEqual(metric['numeric_mismatches'],1)
        self.assertEqual(metric['max_bf16_ulp'],1)
        self.assertTrue(metric['pass_'])
    def test_history_is_raw_and_carried_from_preceding_token(self):
        first=np.full((1,CHANNELS),0x3f80,dtype='<u2')
        second=np.full((1,CHANNELS),0x4000,dtype='<u2')
        weights=np.zeros((CHANNELS,4),dtype='<u2');weights[:,3]=0x3f80
        stale=np.full((CHANNELS,4),0x4040,dtype='<u2')
        _,output,h0=conv_recipe(first,weights,stale,True)
        self.assertTrue(np.all(h0[:,:3]==0));self.assertTrue(np.all(h0[:,3]==0x3f80))
        self.assertTrue(np.all(output!=first))
        _,_,h1=conv_recipe(second,weights,h0,False)
        self.assertTrue(np.all(h1[:,:2]==0));self.assertTrue(np.all(h1[:,2]==0x3f80));self.assertTrue(np.all(h1[:,3]==0x4000))
        self.assertTrue(np.all(stale==0x4040))
    def test_negative_saturation_rejects(self):
        x=bf16(np.full((1,CHANNELS),-80,dtype='<f4'));w=np.zeros((CHANNELS,4),dtype='<u2');w[:,3]=0x3f80
        with self.assertRaises(ValueError):conv_recipe(x,w,np.zeros_like(w),True)
    def test_caller_cannot_construct_reference_authority(self):
        with self.assertRaises(TypeError):GdnFixtureSession()
        forged=object.__new__(GdnFixtureSession)
        with self.assertRaises(ValueError):forged.verify(Path('/tmp'))

if __name__=='__main__':unittest.main()
