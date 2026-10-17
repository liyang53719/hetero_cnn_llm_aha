import tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
from . import prepare as P
from .model import GatherOwner,counts
from candidates.qwen2_resident_matrix.attention_packed_stream.model import Result

def feed(o,*,stall=False):
 o.tick();o.tick(group_ready=True)
 for d in range(8):
  o.tick(q=tuple(10000+d*16+i for i in range(16)))
  for k in range(o.count):
   if stall:
    old=o.tick(read_ready=False)['request'];assert old==o.tick(read_ready=False)['request']
   req=o.tick(read_ready=True)['request']
   assert req[1:]==(o.base+k,16*d)
   if stall:o.tick()
   o.tick(response=(req[0],False,tuple(100000*(o.base+k)+16*d+i for i in range(16))))
   o.tick()
  if stall:
   assert not o.tick(step_ready=False)['client']['step_fire']
  o.tick(step_ready=True)
 return Result(payload=tuple(tuple(1000*i+j for j in range(256)) for i in range(16)))

def fold_all(o,r):
 o.tick(result=r)
 for k in range(o.count):
  assert o.acc==tuple(1000*i+16*k+i for i in range(16))
  for _ in range(17):o.tick(result=r,scalar_ack=True)
  o.tick(result=r)
  if k+1<o.count:
   o.tick(result=r);o.tick(result=r)
 return o

class Control(unittest.TestCase):
 def test_default_off(self):
  o=GatherOwner(0)
  for _ in range(10):o.tick(group_ready=True,read_ready=True,step_ready=True,q=tuple(range(16)))
  self.assertEqual(o.reads,0);self.assertEqual(o.steps,[])
 def test_all_counts_mapping_stalls_and_tail(self):
  for n in (1,2,15,16):
   with self.subTest(n=n):
    register=[0xdeadbeef]*256;o=GatherOwner(n-1,enabled=True,weights=register);r=feed(o,stall=True)
    self.assertIs(o.weights,register);self.assertEqual(o.reads,8*n);self.assertEqual(o.acks,8*n)
    self.assertEqual(len(o.steps),8)
    for d,q,b in o.steps:
     for k in range(n):self.assertEqual(b[16*k:16*k+16],tuple(100000*k+16*d+i for i in range(16)))
     self.assertEqual(b[16*n:],tuple([0]*(256-16*n)))
    fold_all(o,r);self.assertEqual(o.scores,list(range(n)))
    self.assertEqual(o.client.counts['results'],0);o.tick(result=r)
    self.assertEqual(o.client.counts['results'],1);self.assertTrue(o.owned)
    o.tick(done=(1,False));o.tick();o.tick();self.assertEqual(o.state,'complete')
    self.assertLess(o.events.index(('score',n-1)),o.events.index('result_ack'))
    self.assertEqual([e for e in o.events if isinstance(e,tuple) and e[0]=='fold'],[('fold',k,i) for k in range(n) for i in range(16)])
 def test_causal_tiles_global_key_order(self):
  for token in (16,31,32,127):
   keys=[]
   for base in range(0,token+1,16):
    o=GatherOwner(token,base,enabled=True);r=feed(o);fold_all(o,r);keys.extend(o.scores)
   self.assertEqual(keys,list(range(token+1)))
 def test_foreign_ack_cannot_retire_pending_read(self):
  o=GatherOwner(15,enabled=True);o.tick();o.tick(group_ready=True);o.tick(q=tuple(range(16)))
  req=o.tick(read_ready=True)['request'];o.tick(response=(req[0]+1,False,tuple(range(16))))
  self.assertTrue(o.poison);self.assertIsNotNone(o.pending);self.assertEqual(o.events.count(('gather',0,0)),0)
  o.tick(done=(1,True));o.tick();self.assertFalse(o.tick()['error_done'])
  self.assertFalse(o.tick(response=(req[0],False,tuple(range(16))))['error_done']);self.assertTrue(o.tick()['error_done'])
 def test_matching_error_no_gather_or_score(self):
  o=GatherOwner(15,enabled=True);o.tick();o.tick(group_ready=True);o.tick(q=tuple(range(16)))
  req=o.tick(read_ready=True)['request'];o.tick(response=(req[0],True,tuple(range(16))))
  self.assertTrue(o.poison);self.assertFalse(o.steps);self.assertFalse(o.scores)
  o.tick(done=(1,True));self.assertTrue(o.tick()['error_done'])
 def test_abort_held_tile_after_some_commits(self):
  o=GatherOwner(15,enabled=True);r=feed(o);o.tick(result=r)
  for _ in range(17):o.tick(result=r,scalar_ack=True)
  o.tick(result=r);self.assertEqual(o.scores,[0]);o.tick(result=r,fault=True)
  o.tick(result=r);o.tick(done=(1,True));self.assertTrue(o.tick()['error_done']);self.assertEqual(o.scores,[0])
 def test_later_selected_nonfinite_suppresses_that_score(self):
  o=GatherOwner(1,enabled=True);r=feed(o);o.tick(result=r)
  for _ in range(17):o.tick(result=r,scalar_ack=True)
  o.tick(result=r);o.tick(result=r);o.tick(result=r,selected_finite=False)
  self.assertTrue(o.poison);self.assertEqual(o.scores,[0]);o.tick(result=r);o.tick(done=(1,True));self.assertTrue(o.tick()['error_done'])
 def test_current_fault_on_score_edge(self):
  o=GatherOwner(0,enabled=True);r=feed(o);o.tick(result=r)
  for _ in range(17):o.tick(result=r,scalar_ack=True)
  o.tick(result=r,fault=True);self.assertEqual(o.scores,[])
 def test_counts(self):
  c=counts(128);self.assertEqual(c,dict(groups=6912,matrix_steps=55296,ddr_k_beats=792576,local_q_reads=55296,ordered_adds=1585152,scales=99072,score_writes=99072,physical_fmas=226492416))
  self.assertEqual(counts(16)['matrix_steps'],1536)

class Source(unittest.TestCase):
 def test_frozen_composition_reverse_and_existing_registers(self):
  P.check()
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'out';P.compose(out)
   core=(out/P.TARGETS[0]).read_text()
   self.assertIn('enablePackedQk16Keys:Boolean=false',core)
   self.assertIn('packedGather.get+&1.U<packedKeys',core)
   self.assertIn('packedSelected.get+&1.U===packedKeys',core)
   self.assertIn('Mux((i/16).U<packedKeys,TensorMath.bf16Rne(denseWeights(i)),0.U)',core)
   self.assertIn('denseWeights((packedGather.get<<4)+i.U):=packet',core)
   self.assertIn('scores.write(key+packedSelected.getOrElse(0.U),scalarValue)',core)
   self.assertIn('state=/=st("denseWindowGot")',core)
   for payload in ('val denseWeights=Reg(Vec(denseColumns,UInt(32.W)))','val acc=Reg(Vec(16,UInt(32.W)))','val av=Reg(Vec(16,UInt(32.W)))'):
    self.assertEqual(core.count(payload),1)
   self.assertEqual(core.count('SyncReadMem('),(P.ROOT/P.TARGETS[0]).read_text().count('SyncReadMem('))
   subprocess.run(['patch','--batch','--fuzz=0','-R','-p1'],input=(P.HERE/'owner.patch').read_bytes(),cwd=out,check=True,capture_output=True)
   with tempfile.TemporaryDirectory() as e:
    base=Path(e)/'base';P.previous.compose(base)
    for n in P.TARGETS:self.assertEqual((out/n).read_bytes(),(base/n).read_bytes())
 def test_scalar_and_downstream_statements_unchanged(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'out';P.compose(out);new=(out/P.TARGETS[0]).read_text();old=(P.ROOT/P.TARGETS[0]).read_text()
   for state in ('attReduce','attReduceDone','attExpDiff','attExpResult','attExpSum','attInv','attPVCompute'):
    line=next(l for l in old.splitlines() if l.startswith('  when(state===st("'+state+'")'));self.assertIn(line,new)
 def test_drift(self):
  with patch.object(P,'sha',return_value='0'*64):
   with self.assertRaisesRegex(ValueError,'own source drift'):P.check()
