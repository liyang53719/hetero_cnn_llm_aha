"""Cold control projection of the proposed core connection; no arithmetic."""
from candidates.qwen2_resident_matrix.attention_packed_stream.model import Client,Result
class Owner:
 def __init__(self,enabled=False):
  if type(enabled) is not bool:raise ValueError('canonical flag')
  self.enabled=enabled;self.client=Client(enabled=enabled);self.owned=False;self.tag=1
  self.depth=0;self.final_issued=False;self.committed=False;self.poison=False
  self.state='key';self.lane=0;self.events=[];self.held=None;self.debts=dict(memory=False,local=False,scalar=False);self.memory_tag=None
 def tick(self,*,group_ready=False,step_ready=False,result=None,selected_finite=True,done=None,
          scalar_ack=False,score_ready=True,fault=False,accepted=(),returned=(),memory_tag=1,response_tag=1,legacy_invalid_error=False,owner_ack=False):
  old=self.state;busy=self.owned;poison=self.poison or fault
  previous_debt=any(self.debts.values())
  for kind in accepted:
   if kind not in self.debts:raise ValueError('resource')
   if busy and not self.poison and not self.client.poison:
    if self.debts[kind]:raise ValueError('one outstanding request')
    self.debts[kind]=True
    if kind=='memory':self.memory_tag=memory_tag
  for kind in returned:
   if kind not in self.debts:raise ValueError('resource')
   if self.debts[kind] and (kind!='memory' or response_tag==self.memory_tag):self.debts[kind]=False
  c=self.client.tick(start=(self.tag,False,1) if old=='key' and not busy and not poison and self.tag else None,
   operand=self.depth if old=='dot' and busy and not self.final_issued and not poison else None,
   group_ready=group_ready,step_ready=step_ready,result=result,done=done,abort=poison,
   result_ready=self.committed and not poison,completion_ready=busy and (self.committed or poison or self.client.poison))
  if c.get('start_fire'):
   self.owned=True;self.tag=(self.tag+1)&0xffffffff;self.depth=0;self.final_issued=False;self.committed=False;self.state='dot';self.events.append('begin')
  if c.get('operand_fire'):
   self.events.append(('accepted',self.depth))
   if self.depth==7:self.final_issued=True
   else:self.depth+=1
  if old=='dot' and self.depth==7 and c['result_valid']:
   if not selected_finite:poison=True
   else:self.held=result;self.lane=0;self.state='fold';self.events.append('selected-final')
  if old=='fold' and scalar_ack and not poison:
   self.events.append(('fold',self.lane));self.lane+=1
   if self.lane==16:self.state='scale'
  if old=='scale' and scalar_ack and not poison:self.events.append('scale');self.state='score'
  if old=='score' and score_ready and not poison and not self.client.poison and done is None:self.events.append('score-commit');self.committed=True;self.state='next'
  if c.get('result_fire'):self.events.append('result-ack');self.held=None
  if c.get('done_fire'):self.events.append('done-ack')
  if c.get('completion_fire'):self.events.append('completion-ack');self.owned=False
  if self.client.poison:poison=True
  if old=='key' and not busy and not self.tag:poison=True
  if poison:
   self.poison=True
   if old!='locked':self.state='finish'
  if owner_ack and old=='finish' and not busy and not previous_debt:self.state='locked'
  if old=='next' and not busy:self.state='key'
  return dict(client=c,owner_done=self.state=='finish' and not self.owned and not previous_debt and not any(self.debts.values()),poison=self.poison,selected_held=self.held)
