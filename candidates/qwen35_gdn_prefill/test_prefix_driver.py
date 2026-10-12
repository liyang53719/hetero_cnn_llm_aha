import ctypes as C
import struct
import unittest

import numpy as np

from . import typed_dense as d
from . import rms_owner as r
from .prefix_reference import rms_recipe
from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library


class PrefixDriverTests(unittest.TestCase):
    def test_same_physical_memory_rms_to_actual_matrix_two_invocations(self):
        library=d.library_from_environment(r.ROOT)
        lib=configure_library(C.CDLL(str(library)))
        self.assertEqual(lib.td_reset(),0)
        matrix=d.MatrixService(lib)
        memory=d.TypedMemory()
        dense=d.down.DenseOwnerModel(d.down.PrefixWorkspace(0x9000000,64,1))
        scalar=r.SharedScalar(); norm=r.RmsOwner(scalar)
        weight=np.zeros((1024,32),dtype='<u2')
        for col in range(32): weight[(col*29)%1024,col]=0x3f80
        memory.add_readonly(0x400000,weight.tobytes())
        memory.add_readonly(0x500000,bytes(2048))
        old_outputs=[]
        for phase in range(2):
            source=((np.arange(16*1024,dtype=np.uint32)+phase)%37 + 0x3d80).astype('<u2').tobytes()
            input_base=0x100000+phase*0x10000
            norm_base=0x200000+phase*0x10000
            dense_base=0x300000+phase*0x10000
            memory.add_readonly(input_base,source)
            memory.allocate_output(norm_base,len(source))
            memory.allocate_output(dense_base,16*32*2)
            rms=r.TypedRmsDriver(norm,memory,r.RmsJob(phase*2+1,input_base,0x500000,norm_base,16,
                r.ReductionPolicy.Torch210CpuDefault1024))
            while rms.response is None: rms.tick()
            self.assertTrue(rms.output.published)
            expected=rms_recipe(source,bytes(2048),'torch210_cpu_default1024')
            self.assertEqual(rms.output.raw(),expected)
            job=d.down.Job(m=16,k=1024,n=32,tag=phase*2+2,a=norm_base,b=0x400000,dst=dense_base,
                activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=1024)
            driver=d.TypedDenseDriver(dense,matrix,memory,job)
            while driver.response is None: driver.tick()
            # One-hot raw weights select genuine prior RMS writes exactly.
            expected_dense=np.frombuffer(expected,'<u2').reshape(16,1024)[:,[(c*29)%1024 for c in range(32)]].tobytes()
            self.assertEqual(driver.output.raw(),expected_dense)
            self.assertIs(driver.a,rms.output)
            old_outputs.append((driver.output,driver.output.raw()))
            for region,raw in old_outputs: self.assertEqual(region.raw(),raw)
        self.assertEqual(matrix.counts['owner_acquires'],2)
        self.assertEqual(matrix.counts['owner_releases'],2)
        self.assertEqual(matrix.epoch,0)
        self.assertIsNone(matrix.owner)
        self.assertIsNone(scalar.client)
        self.assertEqual(norm.state,'idle')
        self.assertEqual(dense.state,'idle')


if __name__=='__main__': unittest.main()
