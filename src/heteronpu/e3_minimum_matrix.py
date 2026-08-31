"""Reduced but coverage-driven L5.5 integrated-E3 test matrix."""
from __future__ import annotations
from dataclasses import asdict
import hashlib,itertools,json
from .l5_join_sensitivity import SensitivityPoint,evaluate
LEVELS={'attention_matrix_scale':(1.,1.05,1.25),'attention_sfu_scale':(1.,1.10,1.25),'silu_scale':(1.,1.10,1.50),'ddr_efficiency':(1.,.8,.4),'queue_bubble_fraction':(0.,.01,.07),'bank_conflict_fraction':(0.,.005,.05),'event_latency_cycles':(0,16,256)};NAMES=tuple(LEVELS)
def _tags(point:SensitivityPoint)->set[str]:
 d=asdict(point);tags=set();active=[]
 for name,levels in LEVELS.items():
  if d[name]!=levels[0]:tags.add(f"{name}:{'moderate' if d[name]==levels[1] else 'severe'}");active.append(name)
 for a,b in itertools.combinations(active,2):tags.add(f'pair:{a}+{b}')
 r=evaluate(point);tags.add('class:pass' if r.passes_300tps else 'class:fail')
 if 298<=r.tokens_per_second<=302:tags.add('boundary_300')
 if 313<=r.tokens_per_second<=317:tags.add('review_315')
 return tags
def _candidate_points():
 for combo in itertools.product(*(LEVELS[n] for n in NAMES)):yield SensitivityPoint(**dict(zip(NAMES,combo)))
def minimum_e3_matrix(max_cases:int=20)->dict[str,object]:
 candidates=list(_candidate_points());baseline=SensitivityPoint();review=SensitivityPoint(1.05,1.10,1.10,.8,.01,.005,16);evaluated=[(p,evaluate(p),_tags(p)) for p in candidates];passing=[x for x in evaluated if x[1].passes_300tps];failing=[x for x in evaluated if not x[1].passes_300tps];cp=min(passing,key=lambda x:x[1].tokens_per_second);cf=max(failing,key=lambda x:x[1].tokens_per_second);selected=[]
 def add(point,label):
  if all(point!=x[0] for x in selected):selected.append((point,label))
 add(baseline,'baseline');add(review,'review_scenario');add(cp[0],'closest_pass_300');add(cf[0],'closest_fail_300')
 for name,levels in LEVELS.items():kwargs={n:LEVELS[n][0] for n in NAMES};kwargs[name]=levels[-1];add(SensitivityPoint(**kwargs),f'individual_severe:{name}')
 required=set()
 for name in NAMES:required.add(f'{name}:moderate');required.add(f'{name}:severe')
 pairs=(('attention_matrix_scale','queue_bubble_fraction'),('attention_matrix_scale','bank_conflict_fraction'),('attention_sfu_scale','silu_scale'),('attention_sfu_scale','event_latency_cycles'),('ddr_efficiency','queue_bubble_fraction'),('ddr_efficiency','bank_conflict_fraction'),('queue_bubble_fraction','bank_conflict_fraction'),('queue_bubble_fraction','event_latency_cycles'),('bank_conflict_fraction','event_latency_cycles'))
 required.update(f'pair:{a}+{b}' for a,b in pairs);covered=set().union(*(_tags(p) for p,_ in selected))
 while required-covered and len(selected)<max_cases:
  best=None
  for p,r,tags in evaluated:
   if any(p==x[0] for x in selected):continue
   gain=len((required-covered)&tags)
   if gain==0:continue
   score=(gain,-abs(r.tokens_per_second-315),r.tokens_per_second)
   if best is None or score>best[0]:best=(score,p)
  if best is None:break
  add(best[1],'greedy_pair_coverage');covered|=_tags(best[1])
 if required-covered:raise AssertionError(sorted(required-covered))
 cases=[]
 for case_id,(p,label) in enumerate(selected):r=evaluate(p);cases.append({'case_id':case_id,'label':label,'point':asdict(p),'projection':asdict(r),'coverage_tags':sorted(_tags(p))})
 digest=hashlib.sha256(json.dumps(cases,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 return {'schema_version':1,'status':'PASS','evidence_class':'minimum_E3_test_matrix_E0_not_integrated_E3','cases':cases,'case_count':len(cases),'coverage_tags':sorted(required),'sha256':digest,'mandatory_counters':['measured_attention_matrix_cycles','measured_attention_sfu_cycles','measured_silu_cycles','matrix_producer_stall_cycles','effective_DDR_read_efficiency','effective_DDR_write_efficiency','matrix_queue_bubble_cycles','SRAM_bank_conflict_cycles','event_wait_signal_cycles','score_DDR_bytes','probability_DDR_bytes'],'acceptance':{'score_DDR_bytes':0,'probability_DDR_bytes':0,'pre_route_review_floor_tps':315,'target_tps':300,'sram_mib_max':4,'ddr_read_GBps_max':100,'ddr_write_GBps_max':40},'stop_rule':'If measured service curves project below 315 token/s before post-route, reopen architecture/performance budget.'}
