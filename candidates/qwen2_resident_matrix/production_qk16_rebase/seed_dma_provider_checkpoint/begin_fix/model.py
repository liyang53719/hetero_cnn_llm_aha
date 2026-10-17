"""Two-valued seed-BEGIN boundary model; not a full RTL/FSM proof."""
from itertools import product

def solve(n,offer,work,selected,admit,quiet,step,blocked,split_ready=False):
 solutions=[]
 for all_begin,can_issue in product((False,True),repeat=2):
  valid=[bool(offer and all_begin and selected>>i&1) for i in range(n)]
  ready_step=[bool(step>>i&1 and not(blocked>>i&1 or valid[i])) for i in range(n)]
  issue=[bool(can_issue and selected>>i&1 and ready_step[i]) for i in range(n)]
  ready=[bool(admit>>i&1 and quiet>>i&1 and (split_ready or not issue[i])) for i in range(n)]
  expected_begin=all(not(selected>>i&1) or ready[i] for i in range(n))
  expected_issue=bool(work and all(not(selected>>i&1) or ready_step[i] for i in range(n)))
  if all_begin==expected_begin and can_issue==expected_issue:
   solutions.append(dict(all_begin=all_begin,can_issue=can_issue,valid=valid,issue=issue,ready=ready,accepted=[v and r for v,r in zip(valid,ready)]))
 return solutions

def audit():
 controls=set()
 for state,active,upstream_begin,any_ack,poison,work_base in product(range(8),(False,True),(False,True),(False,True),(False,True),(False,True)):
  offer=state==1 and active and not poison
  block=state!=0 or upstream_begin or any_ack or poison
  work=work_base and not block
  if offer and work:raise ValueError('controller interlock failed')
  controls.add((offer,work))
 standalone_count=0
 for begin,beat,commit,step_valid,step_ready,quiet,reserved,ack,poison,abort in product((False,True),repeat=10):
  blocked=reserved or ack or poison or abort or begin or beat or commit
  issue=step_valid and step_ready and not blocked
  admit=not(reserved or ack or poison or abort)
  old_ready=admit and quiet and not issue
  new_ready=admit and quiet
  if (begin and old_ready)!=(begin and new_ready):raise ValueError('standalone begin handshake changed')
  if begin and new_ready and issue:raise ValueError('standalone simultaneous seed and issue')
  standalone_count+=1
 count=0
 for offer,work in controls:
  for masks in product(range(4),repeat=5):
   old=solve(2,offer,work,*masks);new=solve(2,offer,work,*masks,split_ready=True)
   if len(old)!=1 or len(new)!=1:raise ValueError('nonunique fixedpoint')
   for field in ['can_issue','valid','issue','accepted']:
    if old[0][field]!=new[0][field]:raise ValueError('operational boundary mismatch '+field)
   count+=1
 # Without original interlock an idle single leaf permits two stable solutions.
 mutant=solve(1,True,True,1,1,1,1,0)
 if len(mutant)!=2:raise ValueError('missing interlock negative control')
 return dict(scope='BOOLEAN_BOUNDARY_ENUMERATION_NOT_FULL_FSM',controller_combinations=256,standalone_endpoint_boolean_combinations=standalone_count,includes_invalid_state_encoding_7=True,two_leaf_mask_combinations=count,unique_fixedpoint=True,accepted_and_issue_preserved=True,ready_may_change_when_no_offer=True,interlock_removed_fixedpoints=len(mutant),eight_leaf_generalization='offer=>work0; !offer=>all begin valid0, hence readiness feedback independent in either branch')
if __name__=='__main__':
 import json;print(json.dumps(audit(),indent=2))
