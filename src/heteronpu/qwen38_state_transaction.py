"""Cross-engine speculative state transaction reference.

The E0 implementation snapshots state after every draft token and commits the
longest accepted prefix. Production hardware must realize the same semantics
with epochs, dirty maps and copy-on-write rather than copying full states.
"""
from __future__ import annotations
from dataclasses import dataclass, fields, is_dataclass
import copy, hashlib, json, random, struct
from typing import Callable, Generic, Mapping, Sequence, TypeVar
S=TypeVar("S"); StepFn=Callable[[int,S],S]; CloneFn=Callable[[S],S]
def deep_clone(state:S)->S:return copy.deepcopy(state)
def _canonical(value:object)->object:
    if is_dataclass(value): return {f.name:_canonical(getattr(value,f.name)) for f in fields(value)}
    if isinstance(value,Mapping): return {str(k):_canonical(value[k]) for k in sorted(value,key=str)}
    if isinstance(value,(tuple,list)): return [_canonical(x) for x in value]
    if isinstance(value,float): return {"f64_hex":struct.pack(">d",value).hex()}
    if isinstance(value,bytes): return {"bytes_hex":value.hex()}
    if isinstance(value,(str,int,bool)) or value is None:return value
    if hasattr(value,"tolist"):return _canonical(value.tolist())
    if hasattr(value,"__dict__"):return _canonical(vars(value))
    raise TypeError(type(value))
def state_digest(state:object)->str:
    return hashlib.sha256(json.dumps(_canonical(state),sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True)
class Verification: accepted:int; rejected:int; bonus_token:int|None
def verify_prefix(draft_tokens:Sequence[int],target_tokens:Sequence[int])->Verification:
    if len(target_tokens)<len(draft_tokens):raise ValueError("target does not cover draft")
    accepted=0
    for draft,target in zip(draft_tokens,target_tokens,strict=False):
        if int(draft)!=int(target):break
        accepted+=1
    bonus=int(target_tokens[len(draft_tokens)]) if accepted==len(draft_tokens) and len(target_tokens)>len(draft_tokens) else None
    return Verification(accepted,len(draft_tokens)-accepted,bonus)
@dataclass
class StateTransaction(Generic[S]):
    base_state:S; clone_fn:CloneFn[S]=deep_clone
    def __post_init__(self)->None:
        self.base_state=self.clone_fn(self.base_state);self._tokens=[];self._snapshots=[];self._closed=False
    def append(self,token:int,state_after_token:S)->None:
        if self._closed:raise RuntimeError("transaction resolved")
        self._tokens.append(int(token));self._snapshots.append(self.clone_fn(state_after_token))
    def resolve(self,target_tokens:Sequence[int])->tuple[Verification,S]:
        if self._closed:raise RuntimeError("transaction resolved")
        v=verify_prefix(self._tokens,target_tokens);committed=self.clone_fn(self.base_state if v.accepted==0 else self._snapshots[v.accepted-1]);self._snapshots.clear();self._closed=True;return v,committed
def execute_speculation(step_fn:StepFn[S],base_state:S,draft_tokens:Sequence[int],target_tokens:Sequence[int],*,clone_fn:CloneFn[S]=deep_clone)->tuple[Verification,S]:
    tx=StateTransaction(base_state,clone_fn);state=clone_fn(base_state)
    for token in draft_tokens:state=step_fn(int(token),state);tx.append(int(token),state)
    return tx.resolve(target_tokens)
@dataclass
class SyntheticHybridState:
    token_index:int;gdn_recurrent:list[list[float]];gdn_conv:list[float];qsa_index:list[int];qsa_kv:list[tuple[int,float]];ple_history:list[int];ple_conv:list[float];hyper_stream:list[float];paged_kv_generation:int;sampling_counter:int
    @classmethod
    def initial(cls):return cls(0,[[0.0]*4 for _ in range(3)],[0.0]*6,[],[],[],[0.0]*5,[0.0]*8,1,0)
def synthetic_step(token:int,state:SyntheticHybridState)->SyntheticHybridState:
    out=deep_clone(state);token=int(token);out.token_index+=1;out.sampling_counter=(out.sampling_counter*1664525+token+1013904223)&0xffffffff;decay=.875+(token%5)*.015625
    for row,values in enumerate(out.gdn_recurrent):
        for column,value in enumerate(values):values[column]=value*decay+(token+row-column)*.00390625
    out.gdn_conv=(out.gdn_conv+[float(token)])[-6:];out.qsa_index.append((token*17+out.token_index)%257);out.qsa_kv.append((token,token/16.0));out.ple_history=(out.ple_history+[token])[-2:];out.ple_conv=[x*.75+token*.03125 for x in out.ple_conv];out.hyper_stream=[x+(i+1)*token*.0009765625 for i,x in enumerate(out.hyper_stream)];out.paged_kv_generation+=int(token==0);return out
def run_transaction_stress(cases:int=1000,seed:int=3811)->dict[str,object]:
    rng=random.Random(seed);hist={}
    for _ in range(cases):
        base=SyntheticHybridState.initial()
        for _ in range(rng.randrange(12)):base=synthetic_step(rng.randrange(32),base)
        draft=tuple(rng.randrange(32) for _ in range(rng.randrange(1,9)));accepted=rng.randrange(len(draft)+1);target=list(draft)
        if accepted<len(draft):target[accepted]=(draft[accepted]+1+rng.randrange(31))%32
        else:target.append(rng.randrange(32))
        v,committed=execute_speculation(synthetic_step,base,draft,target);expected=deep_clone(base)
        for token in draft[:accepted]:expected=synthetic_step(token,expected)
        if v.accepted!=accepted or state_digest(committed)!=state_digest(expected):raise AssertionError("rollback mismatch")
        hist[accepted]=hist.get(accepted,0)+1
    return {"schema_version":1,"status":"PASS","evidence_class":"E0_state_atomicity_reference","cases":cases,"state_domains":["token_index","gdn_recurrent","gdn_conv","qsa_index","qsa_kv","ple_history","ple_conv","hyper_stream","paged_kv_generation","sampling_counter"],"accepted_prefix_histogram":{str(k):hist[k] for k in sorted(hist)},"whole_state_copy_is_reference_only":True,"production_contract":["epoch","dirty_bitmap","copy_on_write","atomic_commit_barrier","generation_rollback"]}
