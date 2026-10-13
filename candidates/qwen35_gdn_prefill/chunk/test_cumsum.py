"""Bounded arithmetic, real owner staging/faults; no full35B acceptance."""
import ctypes,json,os,struct,tempfile,time,unittest
from pathlib import Path
from dataclasses import replace
import numpy as np
from .cumsum import GuardedCumsum,CumsumDomainFault,LEGACY_CUMSUM,GUARDED_CUMSUM
from .vector import Vector16,VectorArithmeticFault,build_library
from . import model as m
from .test_model import produced
from ..prep.scalar import PrepScalar

class CumsumTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.library=Path(os.environ['GDN_VECTOR16_LIBRARY']) if os.environ.get('GDN_VECTOR16_LIBRARY') else build_library(cls.tmp.name)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def arithmetic(self):
  v=Vector16(self.library);client=object();self.assertTrue(v.acquire(client))
  return v,GuardedCumsum(lambda a,b:v.op(client,'add',[a],[b])[0])
 def reference(self,xs):
  # Domain proof ensures binary64 prefixes exact here; independent oracle only.
  # CPU source starts running at +0; numpy.cumsum uses first -0 directly.
  total=np.float64(0);out=[]
  for x in np.asarray(xs,'<u4').view('<f4'):
   total=np.add(total,np.float64(x),dtype=np.float64);out.append(np.float32(total))
  return np.asarray(out,'<f4').view('<u4').tolist()
 def test_signed_zero_normal_boundaries_and_chunk_reset(self):
  cases=[[0]*64,[0x80000000]*64,[0,0x80000000]*32,[0xbf800000]*64,
         [0x80800000]*64,[0x80800000,0x80800001]+[0]*62,[0xfb800000]*64,[0x80800000,0x89800000]+[0]*62,
         [0xbf800000,0xb6800000]+[0]*62,[0xbf800000,0xbf800001]+[0]*62]
  for xs in cases:
   v,a=self.arithmetic();out=[a.step(x) for x in xs]
   self.assertEqual(out,self.reference(xs));self.assertEqual(v.calls['add'],13*len(xs))
   self.assertEqual(a.count,len(xs))
   # New chunk starts at +0; no emitted value/high/low carried across chunks.
   b=GuardedCumsum(a.add);self.assertEqual([b.step(x) for x in [0]*64],[0]*64)
 def test_domain_length_residual_poison_and_no_silent_fallback(self):
  for xs,idx in [([0x80000001],0),([0x807fffff],0),([0xfc000000],0),
                  ([0xff7fffff],0),([0xff800000],0),([0x7fc00001],0),
                  ([0x3f800000],0),([0xbf800000,0xb6000000],1),
                  ([0xbf800000,0x80000001],1),([0xbf800000]*65,64)]:
   v,a=self.arithmetic()
   with self.assertRaises(CumsumDomainFault) as caught:
    for x in xs:a.step(x)
   self.assertEqual(caught.exception.diagnostic['index'],idx)
   self.assertEqual(v.calls['add'],13*idx)
   with self.assertRaises(CumsumDomainFault):a.step(0)
   self.assertEqual(v.calls['add'],13*idx)
  fixture=json.loads(Path(__file__).with_name('cumsum_counterexample.json').read_text())
  xs=[int(x,16) if isinstance(x,str) else x for x in fixture['input_words']]
  v,a=self.arithmetic();out=[]
  with self.assertRaises(CumsumDomainFault) as caught:
   for x in xs:out.append(a.step(x))
  self.assertEqual(caught.exception.diagnostic['reason'],'nonzero_low_residual')
  self.assertEqual(caught.exception.diagnostic['index'],63)
  self.assertEqual(caught.exception.diagnostic['discarded'],0xac000000)
  self.assertEqual(v.calls['add'],831);self.assertEqual(len(out),63)
  self.assertEqual(out,self.reference(xs)[:63])
 def test_wrong_rounding_rejected_and_restore_environment(self):
  libc=ctypes.CDLL(None);saved=libc.fegetround();self.assertEqual(saved,0)
  v,a=self.arithmetic()
  try:
   self.assertEqual(libc.fesetround(0x400),0)
   with self.assertRaises(VectorArithmeticFault):a.step(0xbf800000)
   self.assertTrue(a.poison)
  finally:self.assertEqual(libc.fesetround(saved),0)
  v,a=self.arithmetic();self.assertEqual(a.step(0xbf800000),0xbf800000)
 def driver(self,words,owner=None):
  n=len(words);mem=m.TypedMemory()
  owner=owner or m.ChunkOwner(PrepScalar(),Vector16(self.library),heads=32,key_dim=16,value_dim=32,
      host_batch=True,layout=m.GROUPED_35B,cumsum_policy=GUARDED_CUMSUM)
  j=m.ChunkJob(352,0x100000,0x800000,0x900000,0xa00000,0x1000000,n,heads=32,key_dim=16,value_dim=32,
      layout=m.GROUPED_35B,cumsum_policy=GUARDED_CUMSUM)
  x=np.zeros((n,12800),'<u4');x[:,12289::16]=0x3f000000;x[:,12288]=words
  produced(mem,j.input,x.tobytes())
  for base,size in ((j.output,j.output_bytes),(j.state_out,j.state_bytes),(j.scratch,j.scratch_bytes)):mem.allocate_output(base,size)
  return m.TypedChunkDriver(owner,mem,j)
 def finish(self,d,hook=None):
  deadline=time.monotonic()+95
  while d.response is None:
   self.assertLess(time.monotonic(),deadline)
   d.tick(**({} if hook is None else hook(d)))
 def test_owner_late_guard_failure_preserves_staging_and_actual_counts(self):
  f=json.loads(Path(__file__).with_name('cumsum_counterexample.json').read_text())
  xs=[int(x,16) if isinstance(x,str) else x for x in f['input_words']]
  d=self.driver(xs);self.finish(d)
  self.assertEqual(d.response.status,'Numerical');self.assertEqual(d.owner.counts['cumsum_terms'],63)
  self.assertEqual(d.owner.counts['cumsum_add_issues'],831)
  self.assertEqual(d.owner.first_numerical_failure['diagnostic']['reason'],'nonzero_low_residual')
  self.assertEqual(d.owner.first_numerical_failure['row'],63)
  self.assertTrue(d.scratch.acknowledged);self.assertFalse(d.output.published or d.state_out.published or d.scratch.published)
  self.assertIsNone(d.memory.pending);self.assertIsNone(d.owner.scalar.client);self.assertIsNone(d.owner.vector.client)
  d.owner.reset();self.assertEqual(d.owner.cumsum_policy,GUARDED_CUMSUM)
 def test_actual32head_small_owner_after_abort_reset_and_identity(self):
  d=self.driver([0]);self.finish(d,lambda x:{'abort':True} if x.pending_request is not None else {})
  self.assertEqual(d.response.status,'Aborted');owner=d.owner;owner.reset()
  d=self.driver([0xbf800000,0xbf800001],owner);self.finish(d);self.assertIsNone(d.response.status)
  self.assertEqual(d.owner.counts['cumsum_terms'],32*64)
  self.assertEqual(d.owner.counts['cumsum_add_issues'],32*64*13)
  self.assertEqual(d.output.raw(),bytes(d.job.output_bytes));self.assertEqual(d.state_out.raw(),bytes(d.job.state_bytes))
  self.assertFalse(d.output.published or d.state_out.published or d.scratch.published)
  plan=m.ScratchPlan(d.job)
  raw=d.scratch.raw()
  def gate(h,row):return struct.unpack_from('<I',raw,plan.chunks[h][0]['gates'].address(row)-d.job.scratch)[0]
  self.assertEqual(gate(0,0),0xbf800000);self.assertEqual(gate(0,1),0xc0000000)
  self.assertTrue(all(gate(h,row)==0 for h in range(1,32) for row in range(64)))
  self.assertFalse(d.report()['owner']['production_geometry'])
  print('GUARDED_CUMSUM_OWNER '+json.dumps(d.report(),sort_keys=True))
  bad=self.driver([0]);bad.owner.cumsum_policy=LEGACY_CUMSUM
  with self.assertRaises(ValueError):bad.tick()
  with self.assertRaises(ValueError):m.ChunkOwner(PrepScalar(),Vector16(self.library),cumsum_policy=GUARDED_CUMSUM)
  with self.assertRaises(ValueError):replace(d.job,cumsum_policy=LEGACY_CUMSUM).validate(owner.geometry,m.GROUPED_35B,GUARDED_CUMSUM)

if __name__=='__main__':unittest.main()
