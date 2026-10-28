"""Independent Commands output-tail contract model, NOT Scala/RTL/DUT execution."""
from dataclasses import dataclass,replace
import unittest
S=(1<<24)-1

def f(v,h,l):return (v>>l)&((1<<(h-l+1))-1)
def gate_policy(role):
 return (0x24|(42<<32)|(3<<56)|(7<<64)|(128<<100)|(role<<116),0x26|(S<<32)|(2<<56)|(128<<64)|(1<<123)|(1<<124))
def attention_policy(cp,cx,role):
 return (f(cp,7,0)==0x24 and f(cp,31,8)==0 and f(cp,55,32)!=S and f(cp,63,56)==3 and f(cp,67,64)==7 and
 f(cp,99,68)==0 and f(cp,107,100)==128 and f(cp,115,108)==0 and f(cp,118,116)==role and role in (0,1) and f(cp,127,119)==0 and
 f(cx,7,0)==0x26 and f(cx,31,8)==0 and f(cx,55,32)==S and f(cx,63,56)==2 and f(cx,72,64)==128 and
 f(cx,81,73)==0 and f(cx,90,82)==0 and f(cx,122,91)==0 and f(cx,123,123)==1 and f(cx,124,124)==1 and f(cx,127,125)==0)
def gdnp(op,role):return 0x21|(S<<32)|(3<<56)|(op<<64)|(1<<80)|(role<<82)
def gdn_policy(v,op,role):
 return f(v,7,0)==0x21 and f(v,31,8)==0 and f(v,55,32)==S and f(v,63,56)==3 and f(v,71,64)==op and f(v,79,72)==0 and f(v,80,80)==1 and f(v,81,81)==0 and f(v,84,82)==role and f(v,87,85)==0 and f(v,119,88)==0 and f(v,127,120)==0
@dataclass(frozen=True)
class Tensor:
 base:int;rows:int;width:int;dtype:int=5;rank:int=2;extent:int=0
 @property
 def size(self):return self.rows*self.width*2
 @property
 def end(self):return self.base+self.size+self.extent
 def legal(self):return self.base%64==0 and self.base>=0 and self.end<=1<<56 and self.dtype==5 and self.rank==2 and self.extent==0

def overlaps(a,b):return a.base<b.end and b.base<a.end
class Tail:
 def __init__(self,profile=4,rows=128):
  self.p=profile;self.hidden={1:1024,2:1024,3:2048,4:2048}.get(profile,0);self.width=self.hidden*2;self.rows=rows
  self.hidden_tensor=Tensor(0x1000000,rows,self.hidden);self.gate=Tensor(0x2000000,rows,self.width);self.context=Tensor(0x3000000,rows,self.width)
  self.gated=Tensor(0x4000000,rows,self.width);self.norm=self.gated;self.output=Tensor(0x5000000,rows,self.hidden);self.residual=Tensor(0x6000000,rows,self.hidden)
  self.weight=Tensor(0x7000000,self.width,self.hidden);self.gate_ack=self.context_ack=self.norm_ack=True;self.gated_ack=self.o_ack=self.residual_ack=False
  self.cold=True;self.generation=0;self.global_root=False;self.pending=True;self.pending_len=128;self.accepted=None;self.done=False;self.fault=False
 def common(self):return self.p in (1,2,3,4) and self.rows in ((16,128) if self.p in (1,3) else (128,)) and self.cold and self.generation==0 and not self.global_root and not self.fault
 def accept(self,kind,a=None,b=None,d=None):
  if not self.common() or self.accepted is not None:return False
  if kind=='gate':
   a=a or self.gate;b=b or self.context;d=d or self.gated
   good=self.p in (2,4) and self.pending and self.pending_len==128 and self.gate_ack and self.context_ack and not self.gated_ack and a==self.gate and b==self.context and d.rows==self.rows and d.width==self.width
  elif kind=='o':
   a=a or self.gated;b=b or self.weight;d=d or self.output
   good=(self.norm_ack if self.p in (1,3) else self.gated_ack) and not self.o_ack and a==self.gated and b==self.weight and d.rows==self.rows and d.width==self.hidden
  elif kind=='residual':
   a=a or self.hidden_tensor;b=b or self.output;d=d or self.residual
   good=self.o_ack and not self.residual_ack and a==self.hidden_tensor and b==self.output and d.rows==self.rows and d.width==self.hidden
  else:return False
  if not good or any(not t.legal() for t in (a,b,d)) or any(overlaps(x,y) for x,y in ((a,b),(a,d),(b,d))):return False
  self.accepted=(kind,d);return True
 def ack(self,status=0,tag=73,bytes_=None,fire=True):
  if not self.accepted or not fire:return False
  good=status==0 and tag==73 and (bytes_ is None or bytes_==self.accepted[1].size)
  self.done=good
  if not good:self.fault=True
  return good
 def completion(self,ready=True,fault=False):
  if not self.done:return None
  kind,d=self.accepted
  if not ready:return kind
  if fault:self.fault=True
  else:setattr(self,{'gate':'gated_ack','o':'o_ack','residual':'residual_ack'}[kind],True)
  self.done=False;self.accepted=None;return kind
 def finish(self,kind):
  ok=self.accept(kind)
  if ok:self.ack();self.completion()
  return ok

class OutputCommands(unittest.TestCase):
 def test_all_profiles_actual_widths(self):
  for p in range(1,5):
   for rows in ((16,128) if p in (1,3) else (128,)):
    l=Tail(p,rows)
    if p in (2,4):self.assertTrue(l.finish('gate'))
    self.assertTrue(l.finish('o'));self.assertTrue(l.finish('residual'));self.assertTrue(l.residual_ack);self.assertFalse(l.global_root)
 def test_qwen2_materialization_no_hetero_pc_collision(self):
  for pc in range(24):
   original=pc in (13,16,17,19)
   for runtime_projection,runtime_o in ((True,False),(False,True),(False,False)):
    materialize=original and not runtime_projection and not runtime_o
    self.assertEqual(materialize,original if not (runtime_projection or runtime_o) else False)
 def test_attention_gate_is_not_gdn(self):
  for p in (1,3):self.assertFalse(Tail(p).accept('gate'))
 def test_no_o_without_ack(self):
  for p in (1,2,3,4):
   l=Tail(p);l.norm_ack=False;self.assertFalse(l.accept('o'))
 def test_attention_gate_requires_both_producers(self):
  for name in ('gate_ack','context_ack','pending'):
   l=Tail();setattr(l,name,False);self.assertFalse(l.accept('gate'))
 def test_gate_declared_shape_cannot_replace_qgate(self):
  l=Tail()
  for t in (replace(l.gate,base=l.gate.base+64),replace(l.gate,width=2048),replace(l.gate,rows=16),replace(l.gate,dtype=7),replace(l.gate,rank=3),replace(l.gate,extent=64)):
   self.assertFalse(l.accept('gate',a=t))
 def test_gate_declared_shape_cannot_replace_gqa(self):
  l=Tail();self.assertFalse(l.accept('gate',b=replace(l.context,base=l.context.base+64)))
 def test_o_cannot_take_context_directly(self):
  l=Tail();l.finish('gate');self.assertFalse(l.accept('o',a=l.context))
 def test_o_weight_geometry(self):
  for p in (1,2,3,4):
   l=Tail(p);l.gated_ack=True
   for t in (replace(l.weight,width=l.width),replace(l.weight,rows=l.hidden),replace(l.weight,dtype=7)):
    self.assertFalse(l.accept('o',b=t))
 def test_residual_requires_real_o(self):
  l=Tail();self.assertFalse(l.accept('residual'));l.finish('gate');l.finish('o');self.assertTrue(l.accept('residual'))
 def test_residual_original_input_not_norm(self):
  l=Tail();l.o_ack=True;self.assertFalse(l.accept('residual',a=l.norm))
 def test_no_root_commit(self):
  l=Tail();l.finish('gate');l.finish('o');l.finish('residual');self.assertFalse(l.global_root)
 def test_replay_each_completed_role(self):
  l=Tail()
  for k in ('gate','o','residual'):self.assertTrue(l.finish(k));self.assertFalse(l.accept(k))
 def test_ack_required_and_held_completion(self):
  l=Tail();l.accept('gate');self.assertIsNone(l.completion());self.assertFalse(l.gated_ack);self.assertFalse(l.ack(fire=False));l.ack()
  for _ in range(5):self.assertEqual(l.completion(ready=False),'gate');self.assertFalse(l.gated_ack)
  l.completion();self.assertTrue(l.gated_ack)
 def test_bad_ack(self):
  for kw in (dict(status=1),dict(tag=74),dict(bytes_=0)):
   l=Tail();l.accept('gate');self.assertFalse(l.ack(**kw));self.assertFalse(l.gated_ack)
 def test_late_fault_never_publishes(self):
  for k in ('gate','o','residual'):
   l=Tail();l.gated_ack=k!='gate';l.o_ack=k=='residual';self.assertTrue(l.accept(k));l.ack();self.assertEqual(l.completion(fault=True),k)
   self.assertFalse(getattr(l,{'gate':'gated_ack','o':'o_ack','residual':'residual_ack'}[k]));self.assertFalse(l.global_root)
 def test_context_and_profiles_fail_closed(self):
  for attr,value in [('p',0),('p',5),('rows',1),('cold',False),('generation',1),('global_root',True),('fault',True),('pending_len',127)]:
   l=Tail();setattr(l,attr,value);self.assertFalse(l.accept('gate'))
 def test_output_alias(self):
  l=Tail();self.assertFalse(l.accept('gate',d=l.context));self.assertFalse(l.accept('gate',d=l.gate))
 def test_attention_policy_bits(self):
  for role in (0,1):
   cp,cx=gate_policy(role);self.assertTrue(attention_policy(cp,cx,role))
   for bit in list(range(32))+list(range(56,128)):self.assertFalse(attention_policy(cp^(1<<bit),cx,role),('cp',role,bit))
   for bit in range(128):self.assertFalse(attention_policy(cp,cx^(1<<bit),role),('cx',role,bit))
 def test_attention_policy_pointer_not_authority(self):
  cp,cx=gate_policy(0);self.assertTrue(attention_policy(cp^(1<<32),cx,0));self.assertFalse(attention_policy(cp|S<<32,cx,0))
 def test_original_gdn_policies_exact(self):
  for op,role in ((2,3),(9,0)):
   v=gdnp(op,role);self.assertTrue(gdn_policy(v,op,role))
   for bit in range(128):self.assertFalse(gdn_policy(v^(1<<bit),op,role),(op,role,bit))
if __name__=='__main__':unittest.main()
