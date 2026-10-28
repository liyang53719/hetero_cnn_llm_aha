"""Independent bounded admission/retirement model. Not Chisel or DUT simulation."""
from dataclasses import dataclass, replace
import unittest

@dataclass(frozen=True)
class Host:
 epoch:int=7
 profile:int=2
 program:int=0x1000
 regions:tuple=((0,1<<56,True,True),)

@dataclass(frozen=True)
class Job:
 tag:int=13
 tokens:int=128
 heads:int=8
 dim:int=256
 q:int=0x100000
 cache:int=0x400000
 out:int=0x800000
 start:int=0
 capacity:int=128
 length:int=128
 expected_length:int=0
 generation:int=0
 cold:bool=True
 order:int=1

@dataclass(frozen=True)
class Proof:
 host:Host=Host()
 transaction:int=(1<<40)+9
 q_tag:int=9
 q_result_tag:int=9
 q_valid:bool=True
 q_committed:bool=True
 q_ack:int=128*8*512
 q_tokens:int=128
 q_heads:int=8
 q_dim:int=256
 q_output:int=0x100000
 q_start:int=0
 cache_tag:int=12
 cache_result_tag:int=12
 cache_valid:bool=True
 cache_proposal:bool=True
 cache_drained:bool=True
 cache_base:int=0x400000
 cache_capacity:int=128
 proposed_length:int=128
 proposed_generation:int=1
 key_ack:int=128*1024
 value_ack:int=128*1024
 cache_memory_accepted:int=128*64
 cache_memory_returned:int=128*64
 cache_status:int=0
 q_status:int=0


def admission(job, proof, *, host=Host(), transaction=(1<<40)+9, q_host=None, q_transaction=None, previous=None, fault=False):
 if q_host is None: q_host=proof.host
 if q_transaction is None: q_transaction=proof.transaction
 if fault or not(proof.q_valid and proof.q_committed and proof.cache_valid and proof.cache_proposal and proof.cache_drained): return False
 if host!=proof.host or host!=q_host or transaction!=proof.transaction or transaction!=q_transaction: return False
 if host.profile not in (2,4) or job.heads!={2:8,4:16}[host.profile] or job.tokens!=128 or job.dim!=256: return False
 if (job.start,job.capacity,job.length,job.expected_length,job.generation,job.cold,job.order)!=(0,128,128,0,0,True,1): return False
 if not(0<=proof.q_tag<job.tag<0xffffffff and 0<=proof.cache_tag<job.tag): return False
 if proof.q_tag!=proof.q_result_tag or proof.cache_tag!=proof.cache_result_tag: return False
 if (proof.q_tokens,proof.q_heads,proof.q_dim,proof.q_output,proof.q_start)!=(job.tokens,job.heads,job.dim,job.q,job.start): return False
 if proof.q_status or proof.cache_status or proof.q_ack!=job.tokens*job.heads*512: return False
 if (proof.cache_base,proof.cache_capacity,proof.proposed_length,proof.proposed_generation)!=(job.cache,job.capacity,job.length,job.generation+1): return False
 if (proof.key_ack,proof.value_ack)!=(job.tokens*1024,job.tokens*1024): return False
 if proof.cache_memory_accepted!=job.tokens*64 or proof.cache_memory_returned!=proof.cache_memory_accepted: return False
 if previous is not None:
  tx,q,c=previous
  if transaction<tx or (transaction==tx and (proof.q_tag<=q or proof.cache_tag<=c)): return False
 return True

def counts(m,c,h):
 return dict(scalar=6*m*c*h,matrix=((m+15)//16)*h*((c+31)//32+1),memory=16*h*(m+((m+15)//16)*c),ack=m*h*512)

def observed_loops(m,c,h):
 """Count the retained r3 loops independently, including masked keys."""
 scalar=memory=matrix=ack=0
 for _head in range(h):
  for tile in range(0,m,16):
   rows=min(16,m-tile)
   memory+=rows*8  # Q input
   for ktile in range(0,c,32):
    columns=min(32,c-ktile)
    memory+=columns*8
    matrix+=1
    scalar+=rows*columns*2  # actual scale then mask Add
   scalar+=rows*c*4  # diff, exp, sum, divide for ALL keys
   matrix+=1
   memory+=c*8  # V vector reload per key
   memory+=rows*8
   ack+=rows*8*64
 return dict(scalar=scalar,matrix=matrix,memory=memory,ack=ack)

def terminal(job, report, lease, *, fault=False):
 want=counts(job.tokens,job.length,job.heads)
 return not fault and report['tag']==job.tag and report['accepted']==job and report['status']==0 and report['committed'] and report['drained'] and report['attention_status']==0 and all(report[k]==want[v] for k,v in [('scalar_accepted','scalar'),('scalar_returned','scalar'),('memory_accepted','memory'),('memory_returned','memory'),('matrix_accepted','matrix'),('matrix_returned','matrix'),('ack','ack'),('bytes','ack')]) and lease==dict(accepted=want['scalar'],issued=want['scalar'],returned=want['scalar'],drained=True,kind=8,stage=76,slot=8)

class PrefixModelTests(unittest.TestCase):
 def test_both_runtime_profiles(self):
  for h,p in [(8,2),(16,4)]:
   host=Host(profile=p);self.assertTrue(admission(Job(heads=h),replace(Proof(),host=host,q_heads=h,q_ack=128*h*512),host=host))
 def test_exact_loops(self):
  for m,c in [(1,1),(15,31),(16,32),(17,33),(127,127),(128,128),(128,256)]:
   for h in (8,16): self.assertEqual(counts(m,c,h),observed_loops(m,c,h))
 def test_masked_not_skipped(self): self.assertEqual(counts(128,128,16)['scalar'],1572864)
 def test_bound(self): self.assertEqual(counts(128,256,16)['scalar'],3145728)
 def test_full_transaction_high_bits(self): self.assertFalse(admission(Job(),Proof(),transaction=9))
 def test_query_transaction_distinct(self): self.assertFalse(admission(Job(),Proof(),q_transaction=9))
 def test_epoch_full_host(self): self.assertFalse(admission(Job(),Proof(),host=Host(epoch=8)))
 def test_query_host_identity(self): self.assertFalse(admission(Job(),Proof(),q_host=Host(program=0x2000)))
 def test_region_permission_part_of_host(self): self.assertFalse(admission(Job(),Proof(),host=Host(regions=((0,1<<56,True,False),))))
 def test_strict_each_producer(self):
  for k in ('q_tag','cache_tag'):
   for tag in (13,14,0xffffffff,0x10000000d): self.assertFalse(admission(Job(),replace(Proof(),**{k:tag})))
 def test_each_result_tag(self):
  for k in ('q_result_tag','cache_result_tag'): self.assertFalse(admission(Job(),replace(Proof(),**{k:0})))
 def test_each_producer_ack(self):
  for k in ('q_ack','key_ack','value_ack'): self.assertFalse(admission(Job(),replace(Proof(),**{k:getattr(Proof(),k)-64})))
 def test_cache_memory_debt(self):
  for k in ('cache_memory_accepted','cache_memory_returned'): self.assertFalse(admission(Job(),replace(Proof(),**{k:getattr(Proof(),k)-1})))
 def test_flags_cannot_mint_proof(self):
  for k in ('q_valid','q_committed','cache_valid','cache_proposal','cache_drained'): self.assertFalse(admission(Job(),replace(Proof(),**{k:False})))
 def test_shape_address_and_generation(self):
  for k in ('q_tokens','q_heads','q_dim','q_output','q_start','cache_base','cache_capacity','proposed_length','proposed_generation'): self.assertFalse(admission(Job(),replace(Proof(),**{k:getattr(Proof(),k)+1})))
 def test_cold_only(self):
  for k,v in [('tokens',16),('start',1),('capacity',256),('length',127),('expected_length',1),('generation',1),('cold',False),('order',0)]: self.assertFalse(admission(replace(Job(),**{k:v}),Proof()))
 def test_each_replay_and_old_transaction(self):
  for previous in [((1<<40)+9,9,0),((1<<40)+9,0,12),((1<<40)+10,0,0)]: self.assertFalse(admission(Job(),Proof(),previous=previous))
  self.assertTrue(admission(Job(),Proof(),previous=((1<<40)+8,99,99)))
 def test_fault(self): self.assertFalse(admission(Job(),Proof(),fault=True))
 def test_terminal_exact_all_counts_and_identity(self):
  for h in (8,16):
   job=Job(heads=h);v=counts(128,128,h)
   report=dict(tag=job.tag,accepted=job,status=0,committed=True,drained=True,attention_status=0,scalar_accepted=v['scalar'],scalar_returned=v['scalar'],memory_accepted=v['memory'],memory_returned=v['memory'],matrix_accepted=v['matrix'],matrix_returned=v['matrix'],ack=v['ack'],bytes=v['ack'])
   lease=dict(accepted=v['scalar'],issued=v['scalar'],returned=v['scalar'],drained=True,kind=8,stage=76,slot=8)
   self.assertTrue(terminal(job,report,lease))
   for key,value in report.items():
    wrong=(replace(job,tag=0) if key=='accepted' else not value if isinstance(value,bool) else value+1)
    self.assertFalse(terminal(job,{**report,key:wrong},lease),key)
   for key,value in lease.items(): self.assertFalse(terminal(job,report,{**lease,key:(not value if isinstance(value,bool) else value+1)}),key)
   self.assertFalse(terminal(job,report,lease,fault=True))

if __name__=='__main__': unittest.main(verbosity=2)
