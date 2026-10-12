import ctypes as C
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from . import typed_dense as d
from . import rms_owner as r
from .prefix_reference import rms_recipe
from . import prefix_driver as runner
from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library


class PrefixDriverTests(unittest.TestCase):
    def test_final_identity_keeps_missing_source_and_changed_input_as_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('model.py','library.so','receipt.json','manifest.json'):
                (root/name).write_bytes(name.encode())
            report=dict(source_sha256={'model.py':runner.sha(b'model.py')},library=str(root/'library.so'),
                library_sha256=runner.sha(b'library.so'),compile_receipt=str(root/'receipt.json'),
                compile_receipt_sha256=runner.sha(b'receipt.json'),input_fixture_sha256=runner.sha(b'manifest.json'))
            with patch.object(runner,'load_fixture',return_value=({'manifest':True},{'input':b'abc'})) as load:
                result=runner.final_identity(report,root,root=root)
                self.assertTrue(all(result[k] for k in ('source_unchanged','library_unchanged','fixture_unchanged')))
                load.assert_called_once_with(root,root)
            (root/'model.py').unlink()
            with patch.object(runner,'load_fixture',side_effect=ValueError('raw input changed')):
                result=runner.final_identity(report,root,root=root)
            self.assertFalse(result['source_unchanged'])
            self.assertFalse(result['fixture_unchanged'])
            self.assertTrue(result['library_unchanged'])
            self.assertEqual(set(result['identity_read_errors']),{'source_unchanged','fixture_unchanged'})

    def test_shared_scalar_rms_dense_conv_two_groups_with_unpublished_history(self):
        from .conv import model as c
        from .conv.test_model import oracle
        library=d.library_from_environment(r.ROOT)
        lib=configure_library(C.CDLL(str(library)))
        self.assertEqual(lib.td_reset(),0)
        matrix=d.MatrixService(lib)
        memory=d.TypedMemory()
        scalar=c.ConvScalar(); norm=r.RmsOwner(scalar); conv=c.ConvOwner(scalar,channels=64)
        dense=d.down.DenseOwnerModel(d.down.PrefixWorkspace(0x9000000,64,1))
        source=((np.arange(16*1024,dtype=np.uint32)%37)+0x3d80).astype('<u2').tobytes()
        weights=np.zeros((1024,64),dtype='<u2')
        for col in range(64): weights[(col*29)%1024,col]=0x3f80
        conv_weights=np.full((64,4),0x3e00,dtype='<u2').tobytes()
        memory.add_readonly(0x100000,source)
        memory.add_readonly(0x400000,weights.tobytes())
        memory.add_readonly(0x500000,bytes(2048))
        memory.add_readonly(0x600000,conv_weights)
        for address,size in ((0x200000,len(source)),(0x300000,2048),(0x700000,2048),
                             (0x800000,512),(0x900000,512)):
            memory.allocate_output(address,size)
        rms=r.TypedRmsDriver(norm,memory,r.RmsJob(1,0x100000,0x500000,0x200000,16,
            r.ReductionPolicy.Torch210CpuDefault1024))
        while rms.response is None: rms.tick()
        matrix_job=d.down.Job(m=16,k=1024,n=64,tag=2,a=0x200000,b=0x400000,dst=0x300000,
            activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=2048)
        projection=d.TypedDenseDriver(dense,matrix,memory,matrix_job)
        while projection.response is None: projection.tick()
        job=c.ConvJob(3,0x300000,0x600000,0x700000,0x800000,0x900000,16,True,0,64)
        driver=c.TypedConvDriver(conv,memory,job,current_generation=0)
        for i in range(10000):
            driver.tick(memory_ready=i%3!=0,memory_response_ready=i%4!=0,response_ready=i%5!=0)
            if driver.response is not None: break
        self.assertIsNotNone(driver.response)
        expected,history=oracle(projection.output.raw(),conv_weights,bytes(512),16,64)
        self.assertEqual(driver.output.raw(),expected)
        self.assertEqual(driver.history_out.raw(),history)
        self.assertIs(driver.input,projection.output)
        self.assertIs(norm.scalar,conv.scalar)
        self.assertIsNone(scalar.client)
        self.assertEqual(matrix.counts['owner_releases'],1)
        self.assertEqual(driver.response.write_bytes,2560)
        self.assertTrue(driver.output.published)
        self.assertFalse(driver.history_out.published)
        self.assertFalse(driver.response.history_committed)
        self.assertEqual(driver.response.generation,0)
        with self.assertRaises(ValueError): memory.read64(0x900000)

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
