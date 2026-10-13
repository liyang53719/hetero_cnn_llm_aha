"""32-head real transactions with explicitly reduced synthetic dk/dv.

No checkpoint numeric or complete 35B chunk128 acceptance. Original exp and
FP32 ascending cumsum remain; layout does not silently approve those policies.
"""
import os,struct,tempfile,time,json,hashlib
from pathlib import Path
from dataclasses import replace
import unittest
import numpy as np
from . import model as m
from .vector import Vector16,build_library
from .test_model import produced,bf_bytes
from ..prep.scalar import PrepScalar

class GroupedChunkTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.library=Path(os.environ['GDN_VECTOR16_LIBRARY']) if os.environ.get('GDN_VECTOR16_LIBRARY') else build_library(cls.tmp.name)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def driver(self):
  mem=m.TypedMemory();scalar=PrepScalar(enable_softplus=True);vector=Vector16(self.library)
  owner=m.ChunkOwner(scalar,vector,heads=32,key_dim=16,value_dim=32,host_batch=True,layout=m.GROUPED_35B)
  job=m.ChunkJob(351,0x100000,0x200000,0x300000,0x400000,0x1000000,2,True,0,32,16,32,m.GROUPED_35B)
  raw=np.zeros((2,12800),'<f4')
  for token in range(2):
   for h in range(32):
    raw[token,h*128:h*128+16]=.125
    raw[token,4096+h*128:4096+h*128+16]=.25
    raw[token,8192+h*128:8192+h*128+32]=(h+1+32*token)/128
    raw[token,12288+h*16]=0.;raw[token,12288+h*16+1]=.5
  produced(mem,job.input,raw.tobytes())
  for base,size in ((job.output,job.output_bytes),(job.state_out,job.state_bytes),(job.scratch,job.scratch_bytes)):mem.allocate_output(base,size)
  return m.TypedChunkDriver(owner,mem,job)
 def finish(self,d,hook=None):
  end=time.monotonic()+90;reads=set()
  while d.response is None:
   self.assertLess(time.monotonic(),end)
   p=d.owner.ports();e=d.tick(**({} if hook is None else hook(d)))
   if e['memory_fire'] and not p['memory'].write and d.job.input<=p['memory'].address<d.job.input+d.job.input_bytes:reads.add(p['memory'].address)
  return reads
 def test_all32_heads_execute_actual_addresses_state_and_ack(self):
  d=self.driver();reads=self.finish(d);self.assertIsNone(d.response.status,d.owner.numerical_detail)
  expected=np.zeros((2,32,32),'<f4');state=np.zeros((32,16,32),'<f4')
  for h in range(32):
   v0=(h+1)/128;v1=(h+33)/128
   expected[0,h,:]=v0/4;expected[1,h,:]=v0/8+v1/4;state[h,:,:]=v0/16+v1/8
  self.assertEqual(d.output.raw(),bf_bytes(expected));self.assertEqual(d.state_out.raw(),state.tobytes())
  wanted=set()
  for token in range(2):
   for h in range(32):
    wanted.add(d.job.input+token*51200+(12288+h*16)*4)
    for role,dim in ((0,16),(1,16),(2,32)):
     for col in range(0,dim,16):wanted.add(d.job.input+token*51200+(role*4096+h*128+col)*4)
  self.assertEqual(reads,wanted);self.assertEqual(len(reads),320)
  self.assertEqual(d.owner.counts['chunks_completed'],32)
  self.assertEqual(d.owner.counts['scratch_ack_bytes'],d.job.scratch_bytes)
  self.assertFalse(d.output.published or d.state_out.published or d.scratch.published)
  r=d.report();d.owner.reset();self.assertEqual(d.owner.layout,m.GROUPED_35B)
  self.assertFalse(r['owner']['production_geometry']);self.assertEqual(r['owner']['physical_vector_lanes'],16)
  print('GROUPED_CHUNK_CASE '+json.dumps(dict(tokens=2,heads=32,key_dim=16,value_dim=32,synthetic_reduced_dimensions=True,checkpoint_payload_used=False,native_acceptance=False,rtl_executed=False,output_sha256=hashlib.sha256(d.output.raw()).hexdigest(),state_sha256=hashlib.sha256(d.state_out.raw()).hexdigest(),report=r),sort_keys=True))
 def test_full35_capacity_m16_m128_and_layout_identity(self):
  for tokens,scratch in ((16,27918336),(128,53739520)):
   j=m.ChunkJob(1,0x100000,0x1000000,0x2000000,0x3000000,0x4000000,tokens,heads=32,layout=m.GROUPED_35B)
   j.validate((32,128,128),m.GROUPED_35B)
   self.assertEqual(j.input_bytes,tokens*51200);self.assertEqual(j.state_bytes,2097152);self.assertEqual(j.scratch_bytes,scratch)
   plan=m.ScratchPlan(j);self.assertEqual(len(plan.initial),32);self.assertEqual(len(plan.chunks[31]),j.chunks)
   with self.assertRaises(ValueError):j.validate((32,128,128),m.EQUAL_HEADS)
  d=self.driver();d.owner.layout=m.EQUAL_HEADS
  with self.assertRaises(ValueError):d.tick()
 def test_first_real_read_error_releases_and_keeps_state_unpublished(self):
  d=self.driver()
  self.finish(d,lambda x: {'read_error':True} if x.pending_request is not None and not x.pending_request.write else {})
  self.assertIsNotNone(d.response.status);self.assertFalse(d.output.published or d.state_out.published)
  self.assertIsNone(d.owner.scalar.client);self.assertIsNone(d.owner.vector.client)

 def test_full_capacity_tail_state_ack_error_transport_only(self):
  # Script only two physical writes. No arithmetic or full-state numeric PASS.
  mem=m.TypedMemory();owner=m.ChunkOwner(PrepScalar(),Vector16(self.library),heads=32,layout=m.GROUPED_35B)
  j=m.ChunkJob(901,0x100000,0x1000000,0x2000000,0x3000000,0x4000000,1,heads=32,layout=m.GROUPED_35B)
  produced(mem,j.input,bytes(j.input_bytes))
  for base,size in ((j.output,j.output_bytes),(j.state_out,j.state_bytes),(j.scratch,j.scratch_bytes)):mem.allocate_output(base,size)
  tail=j.state_out+j.state_bytes-64;scratch_tail=j.scratch+j.scratch_bytes-64
  def script(job):
   yield scratch_tail,bytes(64)
   yield tail,bytes(64)
  owner._compute=script
  d=m.TypedChunkDriver(owner,mem,j);seen=False
  def hook(x):
   nonlocal seen
   if x.pending_request is not None and x.pending_request.address==tail:
    seen=True;return {'ack_error':True}
   return {}
  self.finish(d,hook);self.assertTrue(seen);self.assertIsNotNone(d.response.status)
  self.assertFalse(d.output.published or d.state_out.published or d.scratch.published)
  self.assertIsNone(mem.pending);self.assertIsNone(owner.scalar.client);self.assertIsNone(owner.vector.client)
  self.assertEqual(d.scratch.acknowledged,{j.scratch_bytes-64})
  self.assertNotIn(j.state_bytes-64,d.state_out.acknowledged)
