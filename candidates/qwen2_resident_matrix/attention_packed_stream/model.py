"""Control-only reservation model, no arithmetic or payload copy.

Counters are test instrumentation, not proposed RTL registers. service_drained
is an actual matching service metadata-queue observation in the proposed RTL.
"""
from dataclasses import dataclass
@dataclass(frozen=True)
class Result:
 context:int=0
 last:bool=True
 error:bool=False
 payload:object=None
class Client:
 def __init__(self,*,enabled=False):
  if type(enabled) is not bool:raise ValueError('canonical flag')
  self.enabled=enabled;self.state='idle';self.tag=0;self.pv=False;self.count=0;self.index=0;self.poison=False
  self.counts=dict(groups=0,steps=0,results=0,done=0,completion=0)
 def tick(self,*,start=None,operand=None,group_ready=False,step_ready=False,result=None,done=None,
          pause=False,service_drained=False,abort=False,result_ready=False,completion_ready=False):
  s=self.state;active=s in ('issuing','result','done','draining');final=(self.count-1 if self.pv else 7)
  bad=result is not None and (result.context!=0 or result.last is not True or result.error is not False)
  matching=done is not None and done[0]==self.tag
  offer=self.enabled and s=='issuing' and not(pause or abort or self.poison or result is not None or done is not None)
  legal=operand is not None and operand==self.index
  out=dict(start_ready=self.enabled and s=='idle' and not abort,
   group_valid=self.enabled and s=='opening' and not abort,
   step_valid=offer and operand is not None and legal,
   operand_ready=offer and (step_ready if legal else True),
   result_valid=self.enabled and s=='result' and result is not None and not(bad or abort or self.poison),
   result=result,
   result_ready=self.enabled and (s=='draining' or (s=='result' and (bad or result_ready) and not abort)),
   done_ready=self.enabled and s in ('done','draining') and matching,
   completion_valid=self.enabled and s=='reply',completion=(self.tag,self.poison or (s=='reply' and abort)),
   pause_granted=self.enabled and s=='issuing' and pause and service_drained and not(abort or self.poison or result is not None or done is not None),
   abort=self.enabled and (s=='draining' or (active and abort)))
  out['step']=(self.index,0,self.index==0,self.index==final,self.index==final,self.index==final) if out['step_valid'] else None
  out['group']=(self.tag,0x24 if self.pv else 0x23,0x0f if self.pv else 0xff) if out['group_valid'] else None
  for name,condition in [('start',start is not None and out['start_ready']),('group',group_ready and out['group_valid']),
    ('step',step_ready and out['step_valid']),('operand',operand is not None and out['operand_ready']),
    ('result',result is not None and out['result_ready']),('done',done is not None and out['done_ready']),
    ('completion',completion_ready and out['completion_valid'])]:out[name+'_fire']=bool(condition)
  out['success_accepted']=out['completion_fire'] and not out['completion'][1]
  if not self.enabled:return out
  if out['start_fire']:
   self.tag,self.pv,self.count=start;self.index=0
   valid=type(self.tag) is int and 0<self.tag<2**32 and type(self.pv) is bool and type(self.count) is int and 0<self.count<=(128 if self.pv else 16)
   self.state='opening' if valid else 'reply';self.poison=not valid
  if out['group_fire']:self.state='issuing';self.counts['groups']+=1
  if out['operand_fire']:
   if not legal:self.poison=True;self.state='draining'
   elif self.index==final:self.state='result'
   else:self.index+=1
  if out['step_fire']:self.counts['steps']+=1
  if out['result_fire']:
   self.counts['results']+=1
   if s=='result':
    self.state='draining' if bad else 'done'
    if bad:self.poison=True
  if out['done_fire']:
   self.counts['done']+=1;self.state='reply'
   if done[1]:self.poison=True
  if out['completion_fire']:
   self.counts['completion']+=1;self.state='locked' if self.poison or abort else 'idle'
  if active and ((result is not None and s not in ('result','draining')) or (done is not None and (not matching or s not in ('done','draining')))):
   self.poison=True;self.state='reply' if out['done_fire'] else 'draining'
  if s=='reply' and abort:self.poison=True
  if abort and s not in ('idle','reply','locked'):
   self.poison=True;self.state='reply' if s=='opening' or out['done_fire'] else 'draining'
  return out
