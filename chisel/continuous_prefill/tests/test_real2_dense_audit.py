#!/usr/bin/env python3
"""Independent checker unit tests. These are not RTL tests."""
from pathlib import Path
import ctypes,ctypes.util,struct,sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_real2_dense import dense,weight_matrix
from audit_real2_boundary import bf16_rne


def scalar_weight(i,j,salt):
    x=(i*1664525+j*1013904223+salt*2654435761)&0xffffffff
    x^=x>>13;x=(x*2246822519)&0xffffffff
    return (x%31-15)/256


class DenseAuditTests(unittest.TestCase):
    def test_weight_recipe_wraparound(self):
        for salt in (0,1,18,24,100000):
            w=weight_matrix(33,65,salt)
            for i in (0,1,31,32):
                for j in (0,1,32,64):self.assertEqual(float(w[i,j]),scalar_weight(i,j,salt))
            self.assertEqual(bf16_rne(w).tobytes(),w.tobytes())

    def test_distinct_layer_weights(self):
        for salt in range(1,8):self.assertFalse(np.array_equal(weight_matrix(32,32,salt),weight_matrix(32,32,salt+17)))

    def test_matches_explicit_libm_fmaf(self):
        lib=ctypes.CDLL(ctypes.util.find_library('m') or None)
        fma=lib.fmaf;fma.argtypes=[ctypes.c_float]*3;fma.restype=ctypes.c_float
        rng=np.random.default_rng(20260907)
        for rows,k,n in [(1,1,1),(3,17,19),(2,257,9),(5,32,33)]:
            a=bf16_rne(rng.standard_normal((rows,k)).astype(np.float32))
            w=bf16_rne(rng.standard_normal((k,n)).astype(np.float32))
            ref=np.zeros((rows,n),dtype=np.float32)
            for i in range(rows):
                for j in range(n):
                    acc=0.
                    for t in range(k):acc=fma(float(a[i,t]),float(w[t,j]),acc)
                    ref[i,j]=acc
            self.assertEqual(dense(a,w).tobytes(),ref.tobytes())

    def test_k_order_not_reassociated(self):
        a=np.ones((1,3),dtype=np.float32);w=np.array([[2**24],[1],[-2**24]],dtype=np.float32)
        self.assertEqual(float(dense(a,w)[0,0]),0.)
        self.assertEqual(float(dense(a,w[[0,2,1]])[0,0]),1.)

    def test_bad_geometry(self):
        for a,w in [(np.zeros(3),np.zeros((3,2))),(np.zeros((2,3)),np.zeros((4,2))),(np.zeros((0,2)),np.zeros((2,4)))]:
            with self.assertRaises(ValueError):dense(a,w)

    def test_nonfinite(self):
        for v in (float('nan'),float('inf'),-float('inf')):
            with self.assertRaises(ValueError):dense(np.array([[v]],dtype=np.float32),np.ones((1,1),dtype=np.float32))

    def test_zero_identity(self):
        a=np.arange(32,dtype=np.float32).reshape(2,16)/8
        self.assertEqual(dense(a,np.eye(16,dtype=np.float32)).tobytes(),a.tobytes())


if __name__=='__main__':unittest.main(verbosity=2)
