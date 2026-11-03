"""Bounded summary projection of the new exact host timing line, never payload.
A hash-selected wall-time sample is not CPU time, a confidence interval, a host
speedup measurement, or a cycle-utilization numerator/denominator.
"""
PARTS=('eval_low_before','eval_rising','eval_falling','readonly_offer','mutable_offer',
 'readonly_validation','mutable_validation','step')
REASONS=frozenset(('reset','running','completion','terminal','simulation_destructor'))
SCOPE='SAMPLED_HOST_ELAPSED_NS_NOT_DUT_CPU_OR_RTL_CYCLES'
NUMERIC={'pc','visited','selected','completed_selected','failed_selected','in_flight_selected',
 'sample_log2','invalid_pc_steps','clock_regressions'}|{p+s for p in PARTS for s in ('_calls','_ns','_max_ns')}
def need(v,m):
 if not v:raise ValueError(m)
def parse_line(line):
 need(type(line)is str and len(line)<=4096 and line.startswith('HOST_WALL_SAMPLE_V1 '),'timing line bound/prefix')
 fields={}
 for item in line.rstrip('\n').split()[1:]:
  pair=item.split('=');need(len(pair)==2 and pair[0]not in fields,'exact unique timing field');fields[pair[0]]=pair[1]
 need(set(fields)==NUMERIC|{'reason','scope'},'exact timing schema')
 need(fields['reason']in REASONS and fields['scope']==SCOPE,'timing scope')
 for k in NUMERIC:
  need(fields[k].isascii() and fields[k].isdigit() and len(fields[k])<=20,'bounded unsigned timing field');fields[k]=int(fields[k]);need(fields[k]<(1<<64),'uint64 timing')
 need(fields['pc']<64 and fields['sample_log2']==10 and fields['in_flight_selected']in(0,1),'fixed sampler/bucket')
 need(fields['selected']<=fields['visited'] and fields['selected']==fields['completed_selected']+fields['failed_selected']+fields['in_flight_selected'],'sample accounting including in-flight')
 need(fields['step_calls']==fields['completed_selected']+fields['failed_selected'],'inclusive Step closure')
 for part in PARTS:
  # Validation can run more than once in an observed completion step.
  need(fields[part+'_max_ns']<=fields[part+'_ns'],'max within total')
 if not fields['in_flight_selected']:
  need(sum(fields[p+'_ns']for p in PARTS[:-1])<=fields['step_ns'],'disjoint child times within inclusive Step')
  fields['unattributed_step_residual_ns']=fields['step_ns']-sum(fields[p+'_ns']for p in PARTS[:-1])
 else:fields['unattributed_step_residual_ns']=None
 fields['sampling_guarantee']='DETERMINISTIC_HASH_SELECTION_NOT_FIXED_COUNT_OR_UNBIASED_CI'
 fields['clock_overhead_calibrated']=False
 fields['unmeasured_scope']='allocation checks outside read spans; write/stability/collector/output/log costs within Step residual; build/load/reference/finaldump outside Step'
 return fields
