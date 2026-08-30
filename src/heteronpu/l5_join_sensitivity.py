"""Sensitivity matrix for L5.3/L5.4 measured service before L5.5 E3."""
from __future__ import annotations
from dataclasses import asdict,dataclass
import hashlib,itertools,json,math
@dataclass(frozen=True)
class JoinInputs:
    clock_hz:int=1_000_000_000;sequence:int=1024;layers:int=28;target_tokens_per_second:float=300.;matrix_other_cycles:int=93_585_432;attention_matrix_cycles:int=3_244_032;sfu_other_cycles:int=507_932;attention_sfu_cycles:int=1_579_008;silu_cycles:int=9_175_040;ddr_read_bytes:int=93_585_408;ddr_write_bytes:int=1_048_576;ddr_read_peak_bytes_per_cycle:float=100.;ddr_write_peak_bytes_per_cycle:float=40.;baseline_calibration_cycles:int=1_311;events_per_block:int=18
    @property
    def target_block_cycles(self):return self.sequence*self.clock_hz/(self.target_tokens_per_second*self.layers)
@dataclass(frozen=True)
class SensitivityPoint:
    attention_matrix_scale:float=1.;attention_sfu_scale:float=1.;silu_scale:float=1.;ddr_efficiency:float=1.;queue_bubble_fraction:float=0.;bank_conflict_fraction:float=0.;event_latency_cycles:int=0
    def __post_init__(self):
        if min(self.attention_matrix_scale,self.attention_sfu_scale,self.silu_scale,self.ddr_efficiency)<=0:raise ValueError('scale')
        if not 0<=self.queue_bubble_fraction<1 or not 0<=self.bank_conflict_fraction<1 or self.event_latency_cycles<0:raise ValueError('penalty')
@dataclass(frozen=True)
class SensitivityResult:
    block_cycles:int;full_model_cycles:int;tokens_per_second:float;passes_300tps:bool;matrix_cycles:int;sfu_cycles:int;read_cycles:int;read_spill_cycles:int;write_cycles:int;queue_bubble_cycles:int;bank_conflict_cycles:int;event_cycles:int
def evaluate(p:SensitivityPoint,i:JoinInputs=JoinInputs())->SensitivityResult:
    m=i.matrix_other_cycles+math.ceil(i.attention_matrix_cycles*p.attention_matrix_scale);s=i.sfu_other_cycles+math.ceil(i.attention_sfu_cycles*p.attention_sfu_scale)+math.ceil(i.silu_cycles*p.silu_scale);compute=m+s;r=math.ceil(i.ddr_read_bytes/(i.ddr_read_peak_bytes_per_cycle*p.ddr_efficiency));spill=max(0,r-math.floor(compute*.15));w=math.ceil(i.ddr_write_bytes/(i.ddr_write_peak_bytes_per_cycle*p.ddr_efficiency));q=math.ceil(m*p.queue_bubble_fraction);b=math.ceil(compute*p.bank_conflict_fraction);e=i.events_per_block*p.event_latency_cycles;block=compute+spill+w+q+b+e+i.baseline_calibration_cycles;full=block*i.layers;tps=i.sequence*i.clock_hz/full
    return SensitivityResult(block,full,tps,tps>=i.target_tokens_per_second,m,s,r,spill,w,q,b,e)
def sensitivity_report():
    i=JoinInputs();base=evaluate(SensitivityPoint(),i)
    if base.block_cycles!=108_118_970:raise AssertionError(base)
    grid=itertools.product((.95,1.,1.05,1.10,1.25),(.95,1.,1.05,1.10,1.25),(.90,1.,1.10,1.25,1.50),(1.,.8,.6,.4),(0.,.01,.03,.07),(0.,.005,.02,.05),(0,16,64,256));cases=[]
    for v in grid:
        p=SensitivityPoint(*v);cases.append((p,evaluate(p,i)))
    passing=[x for x in cases if x[1].passes_300tps];failing=[x for x in cases if not x[1].passes_300tps];cp=min(passing,key=lambda x:x[1].tokens_per_second);cf=max(failing,key=lambda x:x[1].tokens_per_second);review=SensitivityPoint(1.05,1.10,1.10,.8,.01,.005,16);rr=evaluate(review,i);digest=hashlib.sha256(json.dumps([{'p':asdict(p),'r':asdict(r)} for p,r in cases],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'schema_version':1,'status':'PASS','evidence_class':'L5_join_sensitivity_E0_not_integrated_E3','baseline':asdict(base),'target_block_cycles':i.target_block_cycles,'baseline_headroom_cycles_per_block':i.target_block_cycles-base.block_cycles,'baseline_headroom_fraction':(i.target_block_cycles-base.block_cycles)/base.block_cycles,'grid_cases':len(cases),'passing_cases':len(passing),'failing_cases':len(failing),'pass_fraction':len(passing)/len(cases),'closest_pass':{'point':asdict(cp[0]),'result':asdict(cp[1])},'closest_fail':{'point':asdict(cf[0]),'result':asdict(cf[1])},'review_scenario':{'point':asdict(review),'result':asdict(rr)},'sha256':digest,'local_E3_minimum_counters':['measured_attention_matrix_cycles','measured_attention_sfu_cycles','measured_silu_cycles_and_producer_stall','effective_DDR_read_write_efficiency','matrix_queue_bubble_cycles','SRAM_bank_conflict_cycles','event_wait_signal_cycles'],'stop_rule':'If measured full-model projection is below 315 tps before post-route margin, reopen architecture/performance budget rather than claiming 300 tps signoff.'}
