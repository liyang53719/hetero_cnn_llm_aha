"""Cross-engine speculative-state commit barrier reference (E0)."""
from __future__ import annotations
from dataclasses import dataclass,field
from enum import IntEnum
import hashlib,random
from typing import Iterable

class StateDomain(IntEnum):
    KV=0;GDN_MATRIX=1;GDN_CONV=2;QSA_INDEX=3;QSA_KV=4;PLE_HISTORY=5;PLE_CONV=6;HYPER_STREAM=7;SAMPLER=8;RUNTIME=9

def domain_mask(domains:Iterable[StateDomain])->int:
    mask=0
    for d in domains:mask|=1<<int(StateDomain(d))
    return mask
@dataclass(frozen=True)
class StateWrite:
    step:int;domain:StateDomain;key:int;value:int
    def __post_init__(self):
        if self.step<0 or self.key<0:raise ValueError('negative write field')
@dataclass
class _Txn:
    txn_id:int;sequence_id:int;base_generation:int;speculative_steps:int;expected_mask:int;ack_mask:int=0;failed:bool=False;writes:list[StateWrite]=field(default_factory=list)
    @property
    def ready(self)->bool:return not self.failed and (self.ack_mask&self.expected_mask)==self.expected_mask
@dataclass(frozen=True)
class CommitResult:
    txn_id:int;sequence_id:int;committed:bool;accepted_steps:int;writes_committed:int;old_generation:int;new_generation:int
class StateCommitModel:
    def __init__(self):
        self.generations={};self.state={};self.active={};self.counters={'started':0,'committed':0,'rolled_back':0,'writes_recorded':0,'writes_committed':0,'stale_responses_suppressed':0,'protocol_errors':0}
    def generation(self,sequence_id:int)->int:return self.generations.setdefault(int(sequence_id),0)
    def start(self,txn_id:int,sequence_id:int,speculative_steps:int,expected_domains:Iterable[StateDomain])->int:
        if txn_id in self.active:raise ValueError('duplicate txn')
        if speculative_steps<=0:raise ValueError('steps')
        expected=domain_mask(expected_domains)
        if not expected:raise ValueError('empty domains')
        gen=self.generation(sequence_id);self.active[txn_id]=_Txn(txn_id,sequence_id,gen,speculative_steps,expected);self.counters['started']+=1;return gen
    def record_write(self,txn_id:int,write:StateWrite):
        t=self.active[txn_id]
        if not 0<=write.step<t.speculative_steps:raise ValueError('window')
        if not t.expected_mask&(1<<int(write.domain)):self.counters['protocol_errors']+=1;raise ValueError('unexpected domain')
        t.writes.append(write);self.counters['writes_recorded']+=1
    def acknowledge(self,txn_id:int,domain:StateDomain):
        t=self.active[txn_id];bit=1<<int(domain)
        if not t.expected_mask&bit or t.ack_mask&bit:self.counters['protocol_errors']+=1;raise ValueError('bad ack')
        t.ack_mask|=bit
    def fail(self,txn_id:int):self.active[txn_id].failed=True
    def _advance(self,sequence_id:int,old:int)->int:
        if self.generation(sequence_id)!=old:self.counters['protocol_errors']+=1;raise RuntimeError('stale txn')
        new=(old+1)&0xffffffff;self.generations[sequence_id]=new;return new
    def commit(self,txn_id:int,accepted_steps:int)->CommitResult:
        t=self.active[txn_id]
        if not t.ready:raise RuntimeError('barrier')
        if not 0<=accepted_steps<=t.speculative_steps:raise ValueError('prefix')
        selected={}
        for w in t.writes:
            if w.step<accepted_steps:selected[(w.domain,w.key)]=w
        for (d,k),w in selected.items():self.state[(t.sequence_id,d,k)]=w.value
        new=self._advance(t.sequence_id,t.base_generation);del self.active[txn_id];self.counters['committed']+=1;self.counters['writes_committed']+=len(selected)
        return CommitResult(txn_id,t.sequence_id,True,accepted_steps,len(selected),t.base_generation,new)
    def rollback(self,txn_id:int)->CommitResult:
        t=self.active[txn_id];new=self._advance(t.sequence_id,t.base_generation);del self.active[txn_id];self.counters['rolled_back']+=1
        return CommitResult(txn_id,t.sequence_id,False,0,0,t.base_generation,new)
    def response_is_current(self,sequence_id:int,generation:int)->bool:
        ok=self.generation(sequence_id)==generation
        if not ok:self.counters['stale_responses_suppressed']+=1
        return ok
    def snapshot(self,sequence_id:int):return {(d,k):v for (s,d,k),v in self.state.items() if s==sequence_id}

def protocol_stress(transactions:int=1000,*,seed:int=0xC017)->dict[str,object]:
    rng=random.Random(seed);m=StateCommitModel();baseline={};digest=hashlib.sha256();accepted=generated=0
    for tid in range(transactions):
        sid=tid%7;baseline.setdefault(sid,{});steps=rng.randint(1,8);domains=tuple(rng.sample(tuple(StateDomain),rng.randint(1,len(StateDomain))));base=m.start(tid,sid,steps,domains);writes=[]
        for step in range(steps):
            for _ in range(rng.randint(1,5)):
                w=StateWrite(step,rng.choice(domains),rng.randrange(32),rng.getrandbits(32));m.record_write(tid,w);writes.append(w);generated+=1
        order=list(domains);rng.shuffle(order)
        for d in order:m.acknowledge(tid,d)
        if rng.random()<.15:result=m.rollback(tid);prefix=0
        else:
            prefix=rng.randint(0,steps);result=m.commit(tid,prefix);selected={}
            for w in writes:
                if w.step<prefix:selected[(w.domain,w.key)]=w
            for loc,w in selected.items():baseline[sid][loc]=w.value
        accepted+=prefix
        if m.snapshot(sid)!=baseline[sid]:raise AssertionError('state divergence')
        if m.response_is_current(sid,base):raise AssertionError('stale accepted')
        if not m.response_is_current(sid,result.new_generation):raise AssertionError('current rejected')
        digest.update(tid.to_bytes(4,'little')+result.new_generation.to_bytes(4,'little')+result.writes_committed.to_bytes(4,'little'))
    if m.active:raise AssertionError('leak')
    return {'schema_version':1,'status':'PASS','evidence_class':'state_commit_barrier_E0_not_atomic_RTL_or_iDMA_E3','transactions':transactions,'accepted_steps':accepted,'generated_writes':generated,'counters':m.counters,'sha256':digest.hexdigest(),'contract':{'state_domains':[d.name.lower() for d in StateDomain],'domain_acknowledgements_may_arrive_out_of_order':True,'accepted_prefix_commit':True,'last_write_wins_within_prefix':True,'generation_advances_on_commit_and_rollback':True,'stale_response_suppression':True,'atomic_commit_barrier':True,'first_RTL_transaction_slots':8},'remaining_local_gates':['state_epoch_table_RTL_E1','commit_barrier_RTL_E1','COW_refcount_dirty_bitmap_integration_E1','out_of_order_iDMA_transaction_E3']}
