"""Generator protocol/control projections only; no native arithmetic."""
import collections,importlib.util,json,sys,tempfile,types,unittest
from pathlib import Path
from . import prepare
from ..attention_packed_owner.protocol import ScratchAction
from ..attention_packed_owner.client import PackedRequest,PackedConsumerAck,PackedTag

def load(path,name):
 spec=importlib.util.spec_from_file_location('candidates.qwen2_resident_matrix.attention_packed_owner.'+name,path)
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.exp_negative=lambda *args:0 # Explicit CONTROL_ONLY callback, no arithmetic claim.
 return m.PackedSchedule
class Owner:
 def __init__(self):self.counts=collections.Counter();self.scalar=None;self.useful_macs=0;self.peak_row_words=0;self.reads=collections.Counter();self.writes=0
 def _read(self,address):
  self.reads[address]+=1
  if False:yield
  return (0,)*16
 def _write(self,address,words):
  self.writes+=1
  if False:yield
 def _op(self,*args):return 0
 def _less(self,*args):return False

def drive(cls,m,trace=False):
 o=Owner();j=types.SimpleNamespace(m=m,a=0x100000,b=0x200000,c=0x300000,dst=0x400000)
 gen=cls().run(o,j);reply=None;counts=collections.Counter();lines=set();valid=set();held=None;group=False;index=0;events=[]
 tile=tuple((0,)*256 for _ in range(16))
 while True:
  try:q=gen.send(reply)
  except StopIteration:break
  reply=None
  if trace:events.append(q)
  if isinstance(q,ScratchAction):
   counts['scratch_'+q.operation]+=1
   if q.operation=='begin':valid.clear()
   if q.operation=='write':
    if len(q.words)!=16:raise AssertionError('full line')
    valid.add(q.line);lines.add(q.line)
   if q.operation=='read':
    if q.line not in valid:raise AssertionError('read before write')
    reply=types.SimpleNamespace(words=(0,)*16)
   if q.operation=='release' and (held or group):raise AssertionError('release with Matrix debt')
  elif isinstance(q,PackedRequest):
   if held is not None:raise AssertionError('held result overwritten')
   if q.clear:
    if group:raise AssertionError('overlapping groups')
    group=True;index=0;counts['groups']+=1
   if not group:raise AssertionError('missing group')
   index+=1;counts['qk' if q.opcode==0x23 else 'pv']+=1
   if q.last:
    if index!=q.steps:raise AssertionError('step count')
    held=PackedTag(1,counts['groups'],counts['groups'],1);selected=q.selected
    reply=types.SimpleNamespace(tag=held,selected_words=lambda selected=selected:(0,)*len(selected),value=tile,check_selected=lambda:None)
  elif isinstance(q,PackedConsumerAck):
   if q.tag!=held:raise AssertionError('matching result ACK')
   held=None;group=False;counts['acks']+=1
  else:raise AssertionError(type(q))
 if held or group:raise AssertionError('terminal debt')
 return counts,lines,o,events
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();d=Path(cls.temp.name)
  cls.old=prepare.prior.compose(d/'old');cls.new=prepare.compose(d/'new')
  cls.a=load(cls.old/prepare.TARGET,'old_control');cls.b=load(cls.new/prepare.TARGET,'new_control')
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_m1_m2_m16_event_projection_unchanged(self):
  for m in (1,2,16):
   a,b=drive(self.a,m,True),drive(self.b,m,True)
   self.assertEqual(a[:2],b[:2]);self.assertEqual(a[3],b[3]);self.assertEqual(a[2].reads,b[2].reads)
 def test_m17_tiles_and_m128_full_capacity(self):
  for m in (17,32,128):
   c,lines,o,_=drive(self.b,m);g=12*sum((n+15)//16 for n in range(1,m+1));pairs=12*m*(m+1)//2
   self.assertEqual(c['qk'],8*g);self.assertEqual(c['pv'],m*(m+1))
   self.assertEqual(c['scratch_write'],2*g);self.assertEqual(c['scratch_read'],2*g)
   self.assertEqual(c['groups'],g+2*m);self.assertEqual(c['acks'],c['groups'])
   self.assertEqual(o.useful_macs,256*pairs);self.assertEqual(o.writes,96*m)
   self.assertEqual(c['scratch_begin'],2*m);self.assertEqual(c['scratch_release'],1)
   if m==128:self.assertEqual(lines,set(range(4096,4192)))
 def test_public_admission_stays_closed(self):
  with self.assertRaises(ValueError):prepare.authorize_full_public(rows=128)
if __name__=='__main__':unittest.main()
