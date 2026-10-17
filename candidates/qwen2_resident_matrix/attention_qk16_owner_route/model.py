"""Cold accepted-event projection. No floating-point math or timing prediction.
Payload containers model explicitly leased existing registers/FIFO, not new SRAM.
"""
from candidates.qwen2_resident_matrix.attention_packed_stream.model import Client
class GatherOwner:
 def __init__(self,token,base=0,*,enabled=False,weights=None):
  if type(enabled) is not bool or type(token) is not int or type(base) is not int or not 0<=base<=token<128 or base%16:raise ValueError('canonical bounded group')
  self.token=token;self.base=base;self.count=min(16,token-base+1);self.enabled=enabled
  self.weights=weights if weights is not None else [None]*256
  if len(self.weights)!=256:raise ValueError('existing Dense register')
  self.client=Client(enabled=enabled);self.state='start';self.depth=0;self.gather=0;self.selected=0
  self.tag=1;self.read_tag=0;self.pending=None;self.packet=None;self.q=None;self.held=None
  self.poison=False;self.committed=False;self.owned=False;self.lane=0;self.acc=None
  self.events=[];self.scores=[];self.steps=[];self.reads=0;self.acks=0
 def tick(self,*,group_ready=False,read_ready=False,response=None,q=None,step_ready=False,result=None,scalar_ack=False,done=None,fault=False,selected_finite=True):
  old=self.state;prepending=self.pending;busy=self.owned;bad=self.poison or fault
  # Accepted DDR request identity is stable and retained through poison/drain.
  request=(self.read_tag,self.base+self.gather,16*self.depth) if old=='read' and not bad else None
  fire=request is not None and read_ready
  if fire:
   if self.pending is not None:raise ValueError('one DDR debt')
   self.pending=request;self.reads+=1;self.events.append(('read',request));self.state='response'
  if response is not None and prepending is not None:
   tag,error,words=response
   if tag==prepending[0]:
    self.pending=None;self.acks+=1;self.events.append(('ack',tag))
    if error:bad=True
    elif not bad:
     if len(words)!=16:raise ValueError('packet width')
     self.packet=tuple(words);self.state='gather'
   elif not bad:bad=True # actual original owner consumes a foreign response as protocol fault
  operand=None
  if old=='issue' and not bad:
   if self.q is None or any(x is None for x in self.weights[:16*self.count]):raise ValueError('ungathered issue')
   operand=self.depth
  c=self.client.tick(start=(1,False,self.count) if old=='start' and not bad else None,
   operand=operand,group_ready=group_ready,step_ready=step_ready,result=result,done=done,
   abort=bad,result_ready=self.committed and not bad,
   completion_ready=busy and (self.committed or bad or self.client.poison))
  if c.get('start_fire'):self.owned=True;self.state='q'
  if old=='q' and q is not None and not bad:
   if len(q)!=16:raise ValueError('Q width')
   self.q=tuple(q);self.gather=0;self.read_tag+=1;self.state='read'
  if old=='gather' and not bad:
   self.weights[16*self.gather:16*self.gather+16]=self.packet
   self.events.append(('gather',self.depth,self.gather))
   if self.gather+1<self.count:self.gather+=1;self.read_tag+=1;self.state='read'
   else:self.state='issue'
  if c.get('operand_fire'):
   b=tuple(self.weights[:16*self.count])+tuple([0]*(256-16*self.count))
   self.steps.append((self.depth,self.q,b));self.events.append(('step',self.depth))
   if self.depth==7:self.state='result'
   else:self.depth+=1;self.state='q'
  if old in ('result','select') and c['result_valid'] and not bad:
   if not selected_finite:bad=True
   else:
    self.held=result;self.acc=tuple(result.payload[i][16*self.selected+i] for i in range(16))
    self.lane=0;self.state='fold';self.events.append(('select',self.selected))
  if old=='fold' and scalar_ack and not bad:
   self.events.append(('fold',self.base+self.selected,self.lane));self.lane+=1
   if self.lane==16:self.state='scale'
  if old=='scale' and scalar_ack and not bad:self.events.append(('scale',self.base+self.selected));self.state='score'
  if old=='score' and not bad and not self.client.poison and done is None:
   self.scores.append(self.base+self.selected);self.events.append(('score',self.base+self.selected));self.state='next'
   self.committed=self.selected+1==self.count
  if old=='next' and not bad:
   if self.selected+1<self.count:self.selected+=1;self.state='select'
   elif not busy:self.state='complete'
  if c.get('result_fire'):self.events.append('result_ack');self.held=None
  if c.get('done_fire'):self.events.append('done_ack')
  if c.get('completion_fire'):self.events.append('completion_ack');self.owned=False
  if self.client.poison:bad=True
  if bad:self.poison=True;self.state='drain'
  complete=self.poison and not self.owned and self.pending is None and prepending is None
  return dict(request=request,read_fire=fire,client=c,error_done=complete,held=self.held)

def counts(tokens):
 if type(tokens) is not int or not 1<=tokens<=128:raise ValueError('tokens')
 pairs=12*tokens*(tokens+1)//2;groups=12*sum((q+16)//16 for q in range(tokens))
 return dict(groups=groups,matrix_steps=8*groups,ddr_k_beats=8*pairs,local_q_reads=8*groups,ordered_adds=16*pairs,scales=pairs,score_writes=pairs,physical_fmas=4096*8*groups)
