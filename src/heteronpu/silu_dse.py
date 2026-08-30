"""Numerical and throughput DSE for fused SiLU(gate)*up."""
from __future__ import annotations
from dataclasses import dataclass
from functools import cached_property
import math,random,struct
from typing import Iterable

def bf16_round(v:float)->float:
 b=struct.unpack('>I',struct.pack('>f',float(v)))[0];lsb=(b>>16)&1;b=(b+0x7fff+lsb)&0xffffffff;return struct.unpack('>f',struct.pack('>I',b&0xffff0000))[0]
def fp16_round(v:float)->float:return struct.unpack('>e',struct.pack('>e',float(v)))[0]
def silu_exact(x:float)->float:
 if x>=0:return x/(1+math.exp(-x))
 e=math.exp(x);return x*e/(1+e)
@dataclass(frozen=True)
class DirectSiluLut:
 entries:int;limit:float=8.0
 @property
 def step(self)->float:return 2*self.limit/(self.entries-1)
 @cached_property
 def table(self):return tuple(fp16_round(silu_exact(-self.limit+i*self.step)) for i in range(self.entries))
 def evaluate(self,x:float)->float:
  if x<=-self.limit:return 0.0
  if x>=self.limit:return x
  pos=(x+self.limit)/self.step;i=max(0,min(self.entries-2,int(math.floor(pos))));f=pos-i;return self.table[i]+f*(self.table[i+1]-self.table[i])
 def fused(self,gate:float,up:float)->float:return bf16_round(self.evaluate(bf16_round(gate))*bf16_round(up))
def _metrics(e:Iterable[float],r:Iterable[float]):
 e=list(e);r=list(r);m=sum(x*x for x in e)/len(e);re=sum(x*x for x in r)/len(r);return {'max_abs':max(map(abs,e)),'mean_abs':sum(map(abs,e))/len(e),'rmse':math.sqrt(m),'relative_l2':math.sqrt(m/re) if re else 0.0}
def evaluate_candidate(entries:int,*,limit:float=8.0,random_cases:int=100_000,seed:int=0x51A4):
 lut=DirectSiluLut(entries,limit);se=[];sr=[];fe=[];fr=[]
 for i in range(65537):
  x=bf16_round(-16+32*i/65536);ref=silu_exact(x);got=lut.evaluate(x);se.append(got-ref);sr.append(ref)
 rng=random.Random(seed+entries)
 for _ in range(random_cases):
  g=bf16_round(max(-16,min(16,rng.gauss(0,2.5))));u=bf16_round(max(-4,min(4,rng.gauss(0,1.25))));ref=bf16_round(silu_exact(g)*u);got=lut.fused(g,u);fe.append(got-ref);fr.append(ref)
 return {'entries':entries,'limit':limit,'step':lut.step,'rom_bits_fp16':entries*16,'estimated_fp_multipliers_per_lane':2,'estimated_fp_adders_per_lane':1,'estimated_pipeline_II':1,'silu':_metrics(se,sr),'fused':_metrics(fe,fr)}
def throughput_dse(*,pairs:int=3_440_640,matrix_cycles:int=20_643_840,tile_pairs:int=512):
 rate=pairs/matrix_cycles;lanes=[]
 for n in (1,2,4,8):
  drain=math.ceil(tile_pairs/n);period=tile_pairs/rate;lanes.append({'lanes':n,'average_utilization':rate/n,'tile_drain_cycles':drain,'tile_period_cycles':period,'drains_before_next_tile':drain<=period,'minimum_pingpong_tile_storage_pairs':2*tile_pairs})
 return {'pairs':pairs,'matrix_cycles':matrix_cycles,'producer_pairs_per_cycle':rate,'tile_pairs':tile_pairs,'lanes':lanes,'recommendation':'1_lane_II1_functionally_sufficient_2_lanes_preferred_for_integration_margin'}
def silu_dse_report():
 c=[evaluate_candidate(e) for e in (64,128,256,512)];t={'relative_l2':0.001,'mean_abs':0.001,'max_abs':0.125};p=[x for x in c if x['fused']['relative_l2']<=t['relative_l2'] and x['fused']['mean_abs']<=t['mean_abs'] and x['fused']['max_abs']<=t['max_abs']];s=min(p,key=lambda x:x['rom_bits_fp16'])
 return {'schema_version':1,'status':'PASS','evidence_class':'numerical_and_throughput_DSE_not_RTL_E1_or_mapped_E4','fused_numerical_screen':t,'candidates':c,'selected_source_candidate':{'entries':s['entries'],'limit':s['limit'],'rom_bits_fp16':s['rom_bits_fp16'],'fused_metrics':s['fused']},'throughput':throughput_dse(),'local_gates':['RTL_ready_valid_E1','1_2_lane_mapped_PPA','Matrix_producer_stall_measurement','q384_numerical_E2']}
