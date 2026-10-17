"""Two-state endpoint boundary enumeration. No clocks, X/Z, or full FSM proof."""
from itertools import product

def boundary(bits,count,split=False,omit_reserved_block=False):
 begin,beat,commit,sv,sr,quiet,reserved,ack,poison,abort,identity,cluster,finite,context_ok=bits
 blocked=(reserved and not omit_reserved_block) or ack or poison or abort or begin or beat or commit
 issue=sv and sr and not blocked
 fullquiet=quiet and not issue
 admissible=reserved and not ack and not poison and not abort
 beatready=admissible and (quiet if split else fullquiet)
 commitready=beatready
 beginready=not(reserved or ack or poison or abort) and quiet
 bf=begin and beginready;wf=beat and beatready;cf=commit and commitready
 legalbegin=context_ok and not beat and not commit
 legalbeat=identity and count<32 and cluster and finite and not commit and not begin
 legalcommit=identity and count==32 and not beat and not begin
 fault=abort or (reserved and not fullquiet) or (begin and not fullquiet) or (bf and not legalbegin) or (wf and not legalbeat) or (cf and not legalcommit) or (begin and (reserved or ack)) or ((beat or commit) and (not reserved or ack))
 return dict(issue=issue,beat_ready=beatready,commit_ready=commitready,begin_fire=bf,beat_fire=wf,commit_fire=cf,fault=bool(fault),reserve=bf and legalbegin and not fault,write=wf and legalbeat and not fault,commit=cf and legalcommit and not fault,invalidate=bool(fault or poison),hold=bool(reserved or ack),ack_valid=bool(ack))

def audit():
 n=0
 for bits in product((False,True),repeat=14):
  for count in (0,31,32,33):
   old=boundary(bits,count);new=boundary(bits,count,True)
   if old!=new:raise ValueError('boundary mismatch')
   if not bits[6] and (new['beat_ready'] or new['commit_ready']):raise ValueError('early ready')
   if bits[6] and not bits[5] and not new['fault']:raise ValueError('retained fault lost')
   if new['write'] and (not bits[10] or not bits[11] or not bits[12] or count>=32):raise ValueError('write legality')
   n+=1
 # Removing the local reserved interlock changes READY even with all valids low.
 bits=(False,False,False,True,True,True,True,False,False,False,True,True,True,True)
 if boundary(bits,0,False,True)==boundary(bits,0,True,True):raise ValueError('mutant not caught')
 return dict(scope='TWO_STATE_ENDPOINT_BOUNDARY_NOT_FULL_FSM',combinations=n,all_outputs_equal=True,ready_and_fire_equal=True,invalid_early_beat_commit_rejected=True,retained_fault_unchanged=True,reserved_interlock_removed_mutant_detected=True,new_state_bits=0)
if __name__=='__main__':
 import json;print(json.dumps(audit(),indent=2))
