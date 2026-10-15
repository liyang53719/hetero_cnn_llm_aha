import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from . import model,probe

class Cold(unittest.TestCase):
    def test_default_does_not_compile_or_run(self):
        with patch('subprocess.run',side_effect=AssertionError('execution')):
            self.assertIsNone(model.compile_library('/not-created'))
            self.assertEqual(probe.run(),{'status':'NOT_EXECUTED'})

class SmallKernel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        cls.np=np;cls.tmp=tempfile.TemporaryDirectory()
        lib=Path(cls.tmp.name)/'test.so'
        model.compile_library(lib,execute=True);cls.c=model.Candidate(lib)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def arrays(self):
        n=self.np
        return n.zeros((1,1536),'<f4'),n.zeros((1536,1536),'<u2'),n.zeros(1536,'<f4')
    def test_spike_and_bias(self):
        x,w,b=self.arrays();x[0,64]=2;w[64,31]=0x3f80;b[31]=1
        raw,out=self.c.project(x,w,b,[31])
        self.assertEqual(raw[0,0],2);self.assertEqual(out[0,0],3)
    def test_bias_before_bf16(self):
        # dot=1+2^-8, bias=2^-8 =>1+2^-7. Premature RNE(dot) loses 2^-8.
        x,w,b=self.arrays();x[0,0]=1;x[0,1]=2**-8
        w[0,0]=w[1,0]=0x3f80;b[0]=2**-8
        raw,out=self.c.project(x,w,b,[0])
        self.assertEqual(raw[0,0],1+2**-8);self.assertEqual(out[0,0],1+2**-7)
    def test_reject_non_bf16_input(self):
        x,w,b=self.arrays();x[0,0]=1.001
        with self.assertRaises(ValueError):self.c.project(x,w,b,[0])
    def test_reject_column_and_dtype(self):
        x,w,b=self.arrays()
        for cols in ([],[-1],[1536],[True]):
            with self.assertRaises(ValueError):self.c.project(x,w,b,cols)
        with self.assertRaises(ValueError):self.c.project(x.astype('float64'),w,b,[0])
    def test_zero_rms(self):
        x,_,_=self.arrays();g=self.np.ones(1536,'<f4')
        self.assertTrue((self.c.rms(x,g)==0).all())

if __name__=='__main__':unittest.main()
