"""Small real Matrix→Conv→Prep chain; synthetic K32, full production heads."""
import ctypes as C
import struct
import unittest

import numpy as np

from .. import typed_dense as d
from .. import rms_owner as r
from ..conv import model as conv
from . import model as prep
from .test_model import oracle_row
from ...qwen2_resident_matrix.ffn_attention.matrix_service import configure_library


class PrepChainTests(unittest.TestCase):
    def test_actual_two_dense_outputs_conv_and_fp32_prep_share_memory_resources(self):
        library=d.library_from_environment(r.ROOT)
        lib=configure_library(C.CDLL(str(library)))
        self.assertEqual(lib.td_reset(),0)
        matrix=d.MatrixService(lib)
        memory=d.TypedMemory()
        scalar=prep.PrepScalar(enable_softplus=True)
        dense=d.down.DenseOwnerModel(d.down.PrefixWorkspace(0x9000000,64,1))
        convolution=conv.ConvOwner(scalar)
        preparation=prep.InputPrepOwner(scalar)
        rows=16
        original=((np.arange(rows*32,dtype=np.uint32)%37)+0x3d80).astype('<u2').tobytes()
        memory.add_readonly(0x100000,original)
        stages={}
        for tag,role,width,wbase,base in ((1,'qkv',6144,0x200000,0x300000),(2,'ab',32,0x400000,0x500000)):
            weight=np.zeros((32,width),dtype='<u2')
            weight[np.arange(width)%32,np.arange(width)]=0x3f80
            memory.add_readonly(wbase,weight.tobytes())
            memory.allocate_output(base,rows*width*2)
            job=d.down.Job(m=rows,k=32,n=width,tag=tag,a=0x100000,b=wbase,dst=base,
                activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=rows*width*2)
            driver=d.TypedDenseDriver(dense,matrix,memory,job)
            for _ in range(50000):
                driver.tick()
                if driver.response is not None:break
            self.assertIsNotNone(driver.response)
            self.assertTrue(driver.output.published)
            stages[role]=driver.output
        weights=np.zeros((6144,4),dtype='<u2');weights[:,3]=0x3f80
        memory.add_readonly(0x600000,weights.tobytes())
        for base,size in ((0x700000,rows*12288),(0x800000,49152),(0x900000,49152)):
            memory.allocate_output(base,size)
        c=conv.TypedConvDriver(convolution,memory,conv.ConvJob(3,0x300000,0x600000,0x700000,
            0x800000,0x900000,rows,True,0),current_generation=0)
        while c.response is None:c.tick()
        self.assertTrue(c.output.published)
        self.assertFalse(c.history_out.published)
        alog=struct.pack('<16f',*([0.1234567]*16));bias=bytes(64)
        memory.add_readonly(0xa00000,alog);memory.add_readonly(0xa00040,bias)
        memory.allocate_output(0xb00000,rows*25600)
        p=prep.TypedInputPrepDriver(preparation,memory,
            prep.InputPrepJob(4,0x700000,0x500000,0xa00000,0xa00040,0xb00000,rows))
        for i in range(50000):
            p.tick(memory_ready=i%3!=0,memory_response_ready=i%4!=0,response_ready=i%5!=0)
            if p.response is not None:break
        self.assertIsNotNone(p.response)
        expected=b''.join(oracle_row(c.output.raw()[t*12288:(t+1)*12288],
            stages['ab'].raw()[t*64:(t+1)*64],alog,bias,16) for t in range(rows))
        self.assertEqual(p.output.raw(),expected)
        self.assertIs(p.conv,c.output);self.assertIs(p.ab,stages['ab'])
        self.assertIs(convolution.scalar,preparation.scalar)
        self.assertIs(r.RmsOwner(scalar).scalar,scalar)
        self.assertEqual(p.response.write_bytes,rows*25600)
        self.assertTrue(p.output.published)
        self.assertFalse(c.history_out.published)
        self.assertIsNone(scalar.client)
        self.assertIsNone(matrix.owner)
        self.assertEqual(matrix.counts['owner_acquires'],2)
        self.assertEqual(matrix.counts['owner_releases'],2)


if __name__=='__main__':unittest.main()
