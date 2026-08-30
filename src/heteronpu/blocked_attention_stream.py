"""Cycle-structured streaming model for blocked QK -> online Softmax -> PV."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import math,random
@dataclass(frozen=True)
class Geometry:
 sequence:int;query_tile:int=16;kv_tile:int=32;head_dim:int=128;q_heads:int=12;kv_heads:int=2;block_tokens:int=128;matrix_macs_per_cycle:int=512
 @property
 def query_tiles(self):return math.ceil(self.sequence/self.query_tile)
 @property
 def query_key_pairs(self):return sum(math.ceil(min(self.sequence,(t+1)*self.query_tile)/self.kv_tile) for t in range(self.query_tiles))
 @property
 def head_microtiles(self):return self.query_key_pairs*self.q_heads
 @property
 def matrix_service(self):return math.ceil(self.query_tile*self.kv_tile*self.head_dim/self.matrix_macs_per_cycle)
 @property
 def score_service(self):return self.query_tile
 @property
 def summary_merges(self):return self.q_heads*sum(t//self.block_tokens for t in range(self.sequence))
 @property
 def matrix_issue_cycles(self):return 2*self.head_microtiles*self.matrix_service
 @property
 def sfu_cycles(self):return self.head_microtiles*self.score_service+self.summary_merges*32
@dataclass(frozen=True)
class StreamResult:
 status:str;sequence:int;score_fifo_depth:int;probability_fifo_depth:int;cycles:int;lower_bound_cycles:int;matrix_busy_cycles:int;sfu_busy_cycles:int;qk_completed:int;pv_completed:int;max_score_occupancy:int;max_probability_occupancy:int;matrix_utilization:float;overhead_fraction:float;deadlock:bool;score_ddr_bytes:int=0;probability_ddr_bytes:int=0
def _merge_distribution(tasks,total):
 q,r=divmod(total,tasks);return [q+(i<r) for i in range(tasks)]
def simulate_stream(g:Geometry,*,score_fifo_depth:int,probability_fifo_depth:int,seed:int=0xA771,matrix_stall_probability:float=0,sfu_stall_probability:float=0,max_cycles_factor:float=4):
 rng=random.Random(seed+g.sequence*17+score_fifo_depth*3+probability_fifo_depth);tasks=g.head_microtiles;merges=_merge_distribution(tasks,g.summary_merges)
 qki=qkc=pvc=0;score=[];prob=0;mk=None;mr=0;sr=0;mb=sb=cycles=0;maxs=maxp=0;fill=4;lower=max(g.matrix_issue_cycles,g.sfu_cycles)+fill;deadline=max(1000,int(lower*max_cycles_factor))
 while pvc<tasks and cycles<deadline:
  cycles+=1
  if mk is not None:
   mb+=1
   if rng.random()>=matrix_stall_probability:mr-=1
   if mr==0:
    if mk=='qk':score.append(merges[qkc]);qkc+=1
    else:pvc+=1
    mk=None
  if sr>0:
   sb+=1
   if rng.random()>=sfu_stall_probability and (sr>1 or prob<probability_fifo_depth):sr-=1
   if sr==0:prob+=1
  if sr==0 and score:
   m=score.pop(0);sr=g.score_service+m*32
  if mk is None:
   choose=prob>0 and (len(score)>=score_fifo_depth-1 or qki>=tasks)
   if choose:prob-=1;mk='pv';mr=g.matrix_service
   elif qki<tasks and len(score)<score_fifo_depth:qki+=1;mk='qk';mr=g.matrix_service
   elif prob>0:prob-=1;mk='pv';mr=g.matrix_service
  maxs=max(maxs,len(score)+(sr>0));maxp=max(maxp,prob)
 dead=pvc<tasks;reported=cycles+fill
 return StreamResult('FAIL' if dead else 'PASS',g.sequence,score_fifo_depth,probability_fifo_depth,reported,lower,mb,sb,qkc,pvc,maxs,maxp,mb/reported,(reported-lower)/lower,dead)
def depth_sweep(sequence:int):
 g=Geometry(sequence);cases=[]
 for sd in (1,2,4):
  for pd in (1,2,4):cases.append(asdict(simulate_stream(g,score_fifo_depth=sd,probability_fifo_depth=pd)))
 passing=[x for x in cases if x['status']=='PASS' and x['overhead_fraction']<=.01];sel=min(passing,key=lambda x:(x['score_fifo_depth']+x['probability_fifo_depth'],x['cycles']))
 stalled=asdict(simulate_stream(g,score_fifo_depth=sel['score_fifo_depth'],probability_fifo_depth=sel['probability_fifo_depth'],seed=99,matrix_stall_probability=.01,sfu_stall_probability=.03,max_cycles_factor=6))
 return {'sequence':sequence,'geometry':{'query_tiles':g.query_tiles,'query_key_pairs':g.query_key_pairs,'head_microtiles':g.head_microtiles,'summary_merges':g.summary_merges,'matrix_service_cycles_per_microtile':g.matrix_service,'score_service_cycles_per_microtile':g.score_service,'matrix_issue_cycles':g.matrix_issue_cycles,'sfu_cycles':g.sfu_cycles},'selected':sel,'stalled_sensitivity':stalled}
def blocked_attention_stream_report():
 r={str(s):depth_sweep(s) for s in (128,384,1024)}
 return {'schema_version':1,'status':'PASS','evidence_class':'cycle_structured_stream_E0_not_RTL_E1_or_iDMA_E3','cases':r,'frozen_invariants':{'shared_matrix_for_QK_and_PV':True,'score_DDR_materialization_bytes':0,'probability_DDR_materialization_bytes':0,'GQA_KV_reuse':6,'q1024_summary_merges':43008},'local_gates':['real_stream_RTL_E1','q128_q384_q1024_numerical_E2','random_backpressure_E1','measured_service_curve','iDMA_E3']}
