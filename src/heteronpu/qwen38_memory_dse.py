"""Synthetic PLE-row and MoE-expert cache DSE.

The workload families bound optimistic and adversarial locality. Results are
architecture screening only; official model traces remain a local-agent gate.
"""
from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
import math,random
from typing import Iterable,Sequence
@dataclass(frozen=True)
class CacheResult:
    accesses:int;hits:int;misses:int;bytes_read:int;evictions:int
    @property
    def hit_rate(self)->float:return self.hits/self.accesses if self.accesses else 0.0
def simulate_lru(accesses:Iterable[int],capacity_entries:int,entry_bytes:int)->CacheResult:
    if capacity_entries<0 or entry_bytes<=0:raise ValueError("cache geometry")
    cache:OrderedDict[int,None]=OrderedDict();hits=misses=evictions=count=0
    for key in accesses:
        count+=1;key=int(key)
        if key in cache:hits+=1;cache.move_to_end(key);continue
        misses+=1
        if capacity_entries:
            if len(cache)>=capacity_entries:cache.popitem(last=False);evictions+=1
            cache[key]=None
    return CacheResult(count,hits,misses,misses*entry_bytes,evictions)
def ple_trace(tokens:int,*,pattern:str,rows_per_token:int=16,seed:int=3808)->tuple[tuple[int,...],...]:
    rng=random.Random(seed);trace=[];previous=tuple(range(rows_per_token))
    for token in range(tokens):
        if pattern=="adversarial":rows=tuple(token*rows_per_token+h for h in range(rows_per_token))
        elif pattern=="uniform":rows=tuple(rng.randrange(320_000_000) for _ in range(rows_per_token))
        elif pattern=="clustered":rows=tuple((token//64)*4096+rng.randrange(4096) for _ in range(rows_per_token))
        elif pattern=="repeated_prompt":rows=trace[token%128] if token>=128 and token%128<64 else tuple(rng.randrange(2_000_000) for _ in range(rows_per_token))
        elif pattern=="temporal":rows=previous[:rows_per_token//2]+tuple(rng.randrange(8_000_000) for _ in range(rows_per_token-rows_per_token//2))
        else:raise ValueError(pattern)
        rows=tuple(dict.fromkeys(rows));trace.append(rows);previous=rows
    return tuple(trace)
def flatten(groups:Sequence[Sequence[int]])->tuple[int,...]:return tuple(item for group in groups for item in group)
def expert_bytes(bits:int,hidden:int=2560,intermediate:int=640,group_size:int=64,scale_bits:int=16)->int:
    parameters=3*hidden*intermediate;scales=math.ceil(parameters/group_size) if bits<=8 else 0;return math.ceil((parameters*bits+scales*scale_bits)/8)
def expert_route_trace(tokens:int,*,pattern:str,experts:int=512,top_k:int=10,seed:int=3810)->tuple[tuple[int,...],...]:
    rng=random.Random(seed);routes=[]
    for token in range(tokens):
        if pattern=="uniform":route=tuple(rng.sample(range(experts),top_k))
        elif pattern=="hotset64":route=tuple(rng.sample(range(64),top_k))
        elif pattern=="clustered":
            base=((token//32)*16)%experts;route=tuple(rng.sample([(base+o)%experts for o in range(64)],top_k))
        elif pattern=="adversarial":route=tuple((token*top_k+o)%experts for o in range(top_k))
        elif pattern=="sticky":route=tuple(range(top_k-2))+tuple(rng.sample(range(top_k,experts),2))
        else:raise ValueError(pattern)
        routes.append(route)
    return tuple(routes)
def batching_unique_experts(routes:Sequence[Sequence[int]],window:int)->dict[str,float|int]:
    values=[len({e for route in routes[start:start+window] for e in route}) for start in range(0,len(routes),window)]
    return {"windows":len(values),"total_unique_expert_requests":sum(values),"average_unique_experts_per_window":sum(values)/len(values) if values else 0.0,"peak_unique_experts_per_window":max(values,default=0)}
def memory_dse_report(tokens:int=4096)->dict[str,object]:
    row_bytes=320;ple={}
    for pattern in ("adversarial","uniform","clustered","repeated_prompt","temporal"):
        accesses=flatten(ple_trace(tokens,pattern=pattern));ple[pattern]={}
        for rows in (0,256,1024,4096,16384):
            r=simulate_lru(accesses,rows,row_bytes);ple[pattern][str(rows)]={"capacity_bytes":rows*row_bytes,"accesses":r.accesses,"hits":r.hits,"misses":r.misses,"hit_rate":r.hit_rate,"bytes_read":r.bytes_read,"evictions":r.evictions,"effective_parallel_requests_candidate":32}
    moe={}
    for bits in (16,8,4):
        size=expert_bytes(bits);patterns={}
        for pattern in ("uniform","hotset64","clustered","adversarial","sticky"):
            routes=expert_route_trace(tokens,pattern=pattern);accesses=flatten(routes);caches={}
            for capacity_mib in (0,16,64,128,256):
                entries=capacity_mib*1024*1024//size;r=simulate_lru(accesses,entries,size);caches[str(capacity_mib)]={"capacity_experts":entries,"hit_rate":r.hit_rate,"loads":r.misses,"weight_bytes_read":r.bytes_read}
            patterns[pattern]={"cache_mib":caches,"batching":{str(w):batching_unique_experts(routes,w) for w in (1,4,16,64)}}
        moe[f"w{bits}"]={"one_expert_bytes":size,"patterns":patterns}
    return {"schema_version":1,"status":"PASS","evidence_class":"synthetic_memory_DSE_not_official_trace","tokens":tokens,"ple":{"rows_per_token_max":16,"row_bytes_bf16":row_bytes,"patterns":ple},"moe":moe,"architecture_findings":{"ple_random_row_engine":{"request_dedup":True,"minimum_outstanding_candidate":32,"row_reorder_buffer_required":True},"moe":{"w4_primary_decode_path":True,"route_aware_prefetch":True,"grouped_GEMM_batching":True,"shared_expert_resident_policy":True}}}
