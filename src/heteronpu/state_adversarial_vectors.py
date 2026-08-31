"""Adversarial state-transaction vectors for the Sequence Memory Complex."""
from __future__ import annotations
from dataclasses import asdict,dataclass
import hashlib,json,random
DOMAINS=('kv','gdn_matrix','gdn_conv','qsa_index','qsa_kv','ple_history','ple_conv','hyper_stream','sampler','runtime');GEN_MASK=0xffffffff
@dataclass(frozen=True)
class Write:step:int;domain:int;address:int;value:int
@dataclass(frozen=True)
class Vector:
 transaction_id:int;sequence_id:int;start_generation:int;speculative_steps:int;accepted_prefix:int;outcome:str;dirty_mask:int;ack_order:tuple[int,...];duplicate_acks:tuple[int,...];stale_acks:tuple[int,...];missing_ack_domain:int|None;provisional_pages:int;oom_after_pages:int|None;writes:tuple[Write,...]
class StateModel:
 def __init__(self):
  self.state={};self.generation={};self.allocated_pages=0;self.counters={'started':0,'committed':0,'rolled_back':0,'duplicate_ack':0,'stale_ack':0,'timeout_abort':0,'oom_abort':0,'pages_allocated':0,'pages_freed':0,'writes_committed':0}
 def execute(self,v:Vector)->dict[str,object]:
  self.counters['started']+=1;current=self.generation.get(v.sequence_id,v.start_generation)&GEN_MASK
  if current!=v.start_generation:raise AssertionError((current,v.start_generation))
  allocated=0;oom=False
  for page in range(v.provisional_pages):
   if v.oom_after_pages is not None and page>=v.oom_after_pages:oom=True;break
   allocated+=1;self.allocated_pages+=1;self.counters['pages_allocated']+=1
  seen=set()
  for domain in v.ack_order:
   if domain in seen:self.counters['duplicate_ack']+=1
   seen.add(domain)
  for domain in v.duplicate_acks:
   if domain in seen:self.counters['duplicate_ack']+=1
   else:seen.add(domain)
  for _ in v.stale_acks:self.counters['stale_ack']+=1
  required={i for i in range(len(DOMAINS)) if v.dirty_mask&(1<<i)};missing=required-seen
  if v.missing_ack_domain is not None:missing.add(v.missing_ack_domain)
  abort=None
  if oom:abort='oom';self.counters['oom_abort']+=1
  elif missing:abort='timeout';self.counters['timeout_abort']+=1
  elif v.outcome=='rollback':abort='rollback'
  if abort is None:
   for w in v.writes:
    if w.step<v.accepted_prefix:self.state[(v.sequence_id,w.domain,w.address)]=w.value;self.counters['writes_committed']+=1
   self.counters['committed']+=1
  else:self.counters['rolled_back']+=1
  self.allocated_pages-=allocated;self.counters['pages_freed']+=allocated;self.generation[v.sequence_id]=(current+1)&GEN_MASK
  if self.allocated_pages!=0:raise AssertionError('page leak')
  return {'transaction_id':v.transaction_id,'abort_reason':abort,'generation_after':self.generation[v.sequence_id],'missing_domains':sorted(missing),'committed_writes':sum(1 for w in v.writes if abort is None and w.step<v.accepted_prefix)}
def make_vectors(count:int=5000,seed:int=0x57a7e)->tuple[Vector,...]:
 rng=random.Random(seed);generations={0:0xfffffffc};vectors=[]
 for tx in range(count):
  sequence=tx%17;start=generations.get(sequence,rng.randrange(0,1<<20))&GEN_MASK;steps=rng.randrange(1,9);accepted=rng.randrange(0,steps+1);dirty=sorted(rng.sample(range(len(DOMAINS)),rng.randrange(1,len(DOMAINS)+1)));mask=sum(1<<d for d in dirty);writes=[]
  for step in range(steps):
   for domain in rng.sample(dirty,rng.randrange(1,min(4,len(dirty))+1)):writes.append(Write(step,domain,rng.randrange(0,256),rng.getrandbits(32)))
  ack=dirty.copy();rng.shuffle(ack);duplicates=tuple(rng.sample(dirty,rng.randrange(0,min(3,len(dirty))+1)));stale=tuple(rng.sample(range(len(DOMAINS)),rng.randrange(0,3)));missing=None;oom_after=None;provisional=rng.randrange(0,5);outcome='commit' if rng.random()<.75 else 'rollback';mode=tx%29
  if mode==0:missing=dirty[-1];ack.remove(missing)
  elif mode==1 and provisional:oom_after=rng.randrange(0,provisional)
  elif mode==2:outcome='rollback'
  vectors.append(Vector(tx,sequence,start,steps,accepted,outcome,mask,tuple(ack),duplicates,stale,missing,provisional,oom_after,tuple(writes)));generations[sequence]=(start+1)&GEN_MASK
 return tuple(vectors)
def adversarial_report(count:int=5000,seed:int=0x57a7e)->dict[str,object]:
 vectors=make_vectors(count,seed);model=StateModel();results=[];digest=hashlib.sha256();baseline={}
 for v in vectors:
  before=dict(baseline);result=model.execute(v)
  if result['abort_reason'] is None:
   for w in v.writes:
    if w.step<v.accepted_prefix:baseline[(v.sequence_id,w.domain,w.address)]=w.value
  if model.state!=baseline:raise AssertionError((v.transaction_id,result))
  if result['abort_reason'] is not None and baseline!=before:raise AssertionError('aborted transaction mutated baseline')
  digest.update(json.dumps({'v':asdict(v),'r':result},sort_keys=True,separators=(',',':')).encode())
  if len(results)<64:results.append({'vector':asdict(v),'result':result})
 if model.allocated_pages!=0 or model.counters['pages_allocated']!=model.counters['pages_freed']:raise AssertionError(model.counters)
 if model.generation.get(0)!=((0xfffffffc+sum(1 for v in vectors if v.sequence_id==0))&GEN_MASK):raise AssertionError('generation wrap')
 return {'schema_version':1,'status':'PASS','evidence_class':'state_adversarial_vector_E0_not_RTL_E1_or_iDMA_E3','transactions':count,'domains':list(DOMAINS),'counters':model.counters,'final_state_entries':len(model.state),'generation_wrap_exercised':True,'page_leak':0,'sample_vectors':results,'sha256':digest.hexdigest(),'local_gate':'drive these transaction classes through epoch/dirty/COW/commit RTL with OOO acknowledgements and DMA responses'}
