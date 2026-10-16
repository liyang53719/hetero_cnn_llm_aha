"""Conservative one-context projection of the existing Matrix stream fences.

All enabled32-column slices issue together, and join into ONE wide result tile.
Latency is an explicit hypothetical parameter, not an RTL timing measurement.
The held object is metadata only, not a payload backpressure proof.
This model intentionally leaves four contexts, seven metadata slots and one
result tile unused. No overlap/SFU/bank/DDR throughput benefit is assumed.
"""
from .model import need

class GroupSchedule:
    def __init__(self,steps,mask,*,latency):
        need(type(steps) is int and 1<=steps<=128 and type(mask) is int and mask in (0x0f,0xff))
        need(type(latency) is int and latency>=1)
        self.steps,self.mask,self.latency=steps,mask,latency
        self.index=0;self.pending=None;self.held=None;self.state='command';self.ticks=0
        self.accepted=0;self.returned=0;self.result_acks=0;self.stalls=0
    def tick(self,*,step_valid=True,result_ready=True,done_ready=True):
        need(all(type(x) is bool for x in (step_valid,result_ready,done_ready)))
        result=self.held
        out=dict(state=self.state,step_ready=False,step_fire=False,result=result,
                 result_fire=False,done_valid=self.state=='done',done_fire=False)
        if self.state=='command':self.state='running'
        elif self.state=='running':
            if self.pending is not None:
                index,due=self.pending
                if self.ticks>=due:
                    self.pending=None;self.returned+=1
                    if index==self.steps-1:
                        self.held=(index,self.mask,True);self.state='result'
            # Conservative pre-edge credit: a returning step doesn't issue again here.
            elif self.index<self.steps:
                out['step_ready']=True
                if step_valid:
                    out['step_fire']=True;self.pending=(self.index,self.ticks+self.latency)
                    self.index+=1;self.accepted+=1
        elif self.state=='result':
            if result_ready:
                out['result_fire']=True;self.result_acks+=1;self.held=None;self.state='completion'
            else:self.stalls+=1
        elif self.state=='completion':self.state='done'
        elif self.state=='done' and done_ready:out['done_fire']=True;self.state='retired'
        self.ticks+=1
        return out
