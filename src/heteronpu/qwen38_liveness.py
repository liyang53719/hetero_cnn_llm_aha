"""Candidate 48-layer Qwen3.8 SRAM liveness and interval allocation."""
from __future__ import annotations
from dataclasses import asdict,dataclass
from typing import Iterable
KIB=1024
@dataclass(frozen=True)
class BufferRequest:
 name:str;pool:str;size:int;begin:int;end:int;alignment:int=4096;owner:str=""
 def __post_init__(self):
  if self.size<=0 or self.begin<0 or self.end<=self.begin:raise ValueError(self.name)
  if self.alignment<=0 or self.alignment&(self.alignment-1):raise ValueError("alignment")
@dataclass(frozen=True)
class Allocation:
 request:BufferRequest;offset:int
 @property
 def limit(self):return self.offset+self.request.size
def align(value,alignment):return(value+alignment-1)&-alignment
def time_overlap(a,b):return a.begin<b.end and b.begin<a.end
def address_overlap(a,b):return a.offset<b.limit and b.offset<a.limit
class IntervalAllocator:
 def __init__(self,capacity):self.capacity=capacity
 def allocate(self,requests:Iterable[BufferRequest]):
  allocations=[]
  for request in sorted(requests,key=lambda x:(x.begin,-x.size,x.name)):
   conflicts=[x for x in allocations if time_overlap(request,x.request)];candidates={0,*(align(x.limit,request.alignment) for x in conflicts)}
   for offset in sorted(candidates):
    candidate=Allocation(request,align(offset,request.alignment))
    if candidate.limit<=self.capacity and all(not address_overlap(candidate,x) for x in conflicts):allocations.append(candidate);break
   else:raise MemoryError(request.name)
  return tuple(sorted(allocations,key=lambda x:x.request.name))
def validate_allocations(items,capacity):
 items=tuple(items)
 for item in items:
  if item.offset<0 or item.limit>capacity:raise AssertionError("range")
 for i,a in enumerate(items):
  for b in items[i+1:]:
   if time_overlap(a.request,b.request) and address_overlap(a,b):raise AssertionError("overlap")
def peak_live_bytes(items):
 items=tuple(items);points=sorted({p for x in items for p in(x.begin,x.end)});return max((sum(x.size for x in items if x.begin<=p<x.end) for p in points),default=0)
def candidate_requests():return(
 BufferRequest("hyper_tile_pingpong","shared_l2",640*KIB,0,100,owner="GR"),BufferRequest("gdn_projection_tile","shared_l2",160*KIB,4,28,owner="GDN"),BufferRequest("ple_projection_tile","shared_l2",64*KIB,0,18,owner="PLE"),BufferRequest("qsa_query_tile","shared_l2",192*KIB,30,55,owner="QSA"),BufferRequest("qsa_kv_microtile","shared_l2",64*KIB,38,60,owner="QSA"),BufferRequest("qsa_mlo_and_selected_list","shared_l2",32*KIB,38,60,owner="QSA"),BufferRequest("moe_activation_tile","shared_l2",160*KIB,60,92,owner="MoE"),BufferRequest("gdn_state_pingpong_4heads","state_staging",512*KIB,8,30,owner="GDN"),BufferRequest("gdn_conv_state","state_staging",128*KIB,4,30,owner="GDN"),BufferRequest("qsa_index_window","state_staging",128*KIB,30,60,owner="QSA"),BufferRequest("mtp_shadow_metadata","state_staging",64*KIB,0,100,owner="MTP"),BufferRequest("ple_rows_pingpong","expert_row_staging",16*KIB,0,18,owner="PLE"),BufferRequest("expert_weight_tile_pingpong","expert_row_staging",320*KIB,58,92,owner="MoE"),BufferRequest("sparse_request_metadata","expert_row_staging",48*KIB,0,100,owner="memory"))
def liveness_report():
 owners={"shared_l2":1280,"matrix_scratchpad":768,"matrix_accumulator":512,"state_staging":768,"expert_row_staging":384,"aha_sidecar":256,"control_trace":128};assert sum(owners.values())==4096;by={}
 for request in candidate_requests():by.setdefault(request.pool,[]).append(request)
 pools={}
 for pool,requests in sorted(by.items()):
  capacity=owners[pool]*KIB;alloc=IntervalAllocator(capacity).allocate(requests);validate_allocations(alloc,capacity);peak=peak_live_bytes(requests);pools[pool]={"capacity_bytes":capacity,"peak_live_bytes":peak,"headroom_bytes":capacity-peak,"allocations":[{**asdict(x.request),"offset":x.offset,"limit":x.limit}for x in alloc]}
 return{"schema_version":1,"status":"PASS","evidence_class":"candidate_liveness_not_integrated_SRAM_measurement","total_sram_kib":4096,"owner_budget_kib":owners,"pools":pools,"architecture_delta":["split KV staging into Sequence State and Sparse Row/Expert staging","reserve 512 KiB for four-head GDN state ping-pong","make four-branch hyper tile a first-class tensor layout","do not assume a complete expert is resident on chip"]}
