"""Opt-in shared-tile owner transport and reduced real arithmetic regression."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
import tempfile,unittest
from . import model as m
from .test_model import produced,fixture
from .vector import Vector16,build_library
from ..prep.scalar import PrepScalar

def make(policy=m.ROW4_MATMUL,*,library=None,script=False):
    memory=m.TypedMemory();scalar=PrepScalar(enable_softplus=True)
    if library is None:
        vector=object.__new__(Vector16);vector.client=None;vector.resource_address=id(vector)
        vector.exception_policy='legacy_vector_fatal_underflow';vector.fatal_mask=30
        vector.calls,vector.lane_ops,vector.host_calls,vector.flags=(Counter() for _ in range(4))
    else:vector=Vector16(library)
    owner=m.ChunkOwner(scalar,vector,heads=1,key_dim=16,value_dim=32,host_batch=True,matmul_policy=policy)
    job=m.ChunkJob(19,0x100000,0x500000,0x510000,0x520000,0x600000,2,True,0,1,16,32,matmul_policy=policy)
    produced(memory,job.input,fixture(2) if library else bytes(job.input_bytes))
    for base,size in ((job.output,job.output_bytes),(job.state_out,job.state_bytes),(job.scratch,job.scratch_bytes)):memory.allocate_output(base,size)
    if script:
        def transport(j):
            tile=owner.shared_scratch;tile.acquire(owner)
            try:
                tile.put(owner,0,[0]*256)
                yield(j.input,None)
                for base,size in ((j.scratch,j.scratch_bytes),(j.output,j.output_bytes),(j.state_out,j.state_bytes)):
                    for offset in range(0,size,64):yield(base+offset,bytes(64))
            finally:tile.release(owner)
        owner._compute=transport
    return m.TypedChunkDriver(owner,memory,job)

def finish(d):
    for _ in range(1000000):
        d.tick()
        if d.response is not None:return d.response
    raise AssertionError('bounded reduced driver')

class ReuseOwnerTransportTests(unittest.TestCase):
    def test_abort_reset_and_ack_fault_hold_tile_until_actual_drain(self):
        for control in ('abort','reset','ack_error'):
            d=make(script=True);tile=d.owner.shared_scratch
            for _ in range(20):
                if d.pending is not None and d.pending_request.write:break
                d.tick()
            self.assertIsNotNone(d.memory.pending);self.assertIs(tile.client,d.owner)
            physical=d.memory.pending
            d.tick(memory_response_ready=False,**({control:True} if control!='ack_error' else {}))
            self.assertIs(d.memory.pending,physical);self.assertIs(tile.client,d.owner)
            with self.assertRaises(ValueError):d.owner.reset()
            d.tick(response_ready=False,**({'ack_error':True} if control=='ack_error' else {}))
            self.assertIsNone(d.memory.pending);self.assertIsNone(tile.client)
            self.assertEqual(d.owner.result.status,'Memory' if control=='ack_error' else 'Aborted')
            with self.assertRaises(ValueError):d.owner.reset()
            d.tick();self.assertIsNotNone(d.response);d.owner.reset()
            self.assertIs(d.owner.shared_scratch,tile);self.assertIsNone(tile.client)
            self.assertFalse(d.output.published or d.state_out.published or d.scratch.published)
    def test_last_write_ack_backpressure_and_success_terminal(self):
        d=make(script=True);tile=d.owner.shared_scratch;target=d.job.state_out+d.job.state_bytes-64
        for _ in range(20000):
            if d.pending is not None and d.pending_request.address==target:break
            d.tick()
        self.assertEqual(d.pending_request.address,target)
        for _ in range(4):d.tick(memory_response_ready=False,response_ready=False);self.assertIs(tile.client,d.owner)
        d.tick(response_ready=False);self.assertIsNone(tile.client);self.assertIsNone(d.owner.result.status)
        d.tick(response_ready=False,abort=True);self.assertEqual(d.owner.result.status,'Aborted');d.tick()
        self.assertFalse(d.output.published or d.state_out.published)
    def test_read_error_and_identity_drift_fail_closed(self):
        d=make(script=True);d.tick();d.tick(read_error=True,response_ready=False)
        self.assertIsNone(d.owner.shared_scratch.client);self.assertEqual(d.owner.result.status,'Memory')
        d=make(script=True);d.owner.matmul_policy=m.LEGACY_MATMUL
        with self.assertRaises(ValueError):d.tick()
    def test_policy_mismatch_rejected_before_resource_use(self):
        vector=object.__new__(Vector16)
        with self.assertRaisesRegex(ValueError,'matmul policy'):
            m.ChunkJob(1,0,1<<20,2<<20,3<<20,4<<20,1,matmul_policy=m.ROW4_MATMUL).validate()

class ReuseOwnerNumericTests(unittest.TestCase):
    def test_real_reduced_owner_output_state_scratch_and_arithmetic_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=build_library(tmp);old=make(m.LEGACY_MATMUL,library=lib);self.assertIsNone(finish(old).status)
            new=make(library=lib);tile=new.owner.shared_scratch;self.assertIsNone(finish(new).status)
            for name in ('output','state_out','scratch'):self.assertEqual(getattr(old,name).raw(),getattr(new,name).raw())
            self.assertEqual(old.owner.report()['vector_issue_counts'],new.owner.report()['vector_issue_counts'])
            from candidates.qwen35_35b_prep.chunk_budget import closed_counts
            for driver,policy in ((old,m.LEGACY_MATMUL),(new,m.ROW4_MATMUL)):
                prediction=closed_counts(2,16,32,heads=1,guarded=False,matmul_policy=policy)
                for key in ('read_bytes','write_bytes','scratch_read_bytes'):
                    self.assertEqual(driver.counts[key],prediction[key],key)
            self.assertLess(new.counts['read_bytes'],old.counts['read_bytes'])
            self.assertEqual(new.counts['write_bytes'],old.counts['write_bytes'])
            self.assertIsNone(tile.client);self.assertEqual(tile.high_water_words,256)
            self.assertTrue(new.owner.report()['transpose_and_matmul_share_one_tile'])
            self.assertFalse(new.output.published or new.state_out.published)
if __name__=='__main__':unittest.main()
