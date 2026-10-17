"""Control/bank-port specification only. No arithmetic or shadow payload SRAM."""
from dataclasses import dataclass
from candidates.qwen2_resident_matrix.raw_kv.model import Obligations,uint
from candidates.qwen2_resident_matrix.attention_bank_scratch.port import location
@dataclass(frozen=True)
class Context:
 owner:int;generation:int;query:int;kv_head:int
@dataclass(frozen=True)
class Key:
 owner:int;tag:int;line:int;write:bool
 generation:int=0;query:int=0;kv_head:int=0
@dataclass(frozen=True)
class Request:
 key:Key;data:int=0
@dataclass(frozen=True)
class Response:
 key:Key;data:int
class Port:
 def __init__(self,banks,*,enabled=False,scratch=False):
  if type(enabled)is not bool or type(scratch)is not bool or scratch and not enabled:raise ValueError('canonical profile')
  if banks.depth!=1376 or len(banks.words)!=16:raise ValueError('physical Banks geometry')
  self.banks=banks;self.enabled=enabled;self.scratch=scratch;self.owner=None;self.poison=False
  self.pending=None;self.response=None;self.generation=0;self.query=0;self.kv_head=0;self.active=False;self.written=0
 @property
 def drained(self):return self.pending is None and self.response is None
 def canonical(self,k,*,ack=False):
  if type(k)is not Key or not(uint(k.owner,32,True) and uint(k.tag,32,True) and uint(k.line,13) and type(k.write)is bool):return False
  if not all(uint(v,b) for v,b in ((k.generation,32),(k.query,7),(k.kv_head,1))):return False
  if not self.scratch:return k.line<4096 and (k.generation,k.query,k.kv_head)==(0,0,0)
  if k.line<4096:return (k.generation,k.query,k.kv_head)==(0,0,0)
  return k.line<4192 and (self.active or ack) and (k.generation,k.query,k.kv_head)==(self.generation,self.query,self.kv_head)
 def tick(self,*,acquire=None,release=None,begin=None,request=None,ack=None,abort=False,soft_reset=False,
          obligations=Obligations(),dense=False,tile=False,clear=False):
  self.banks.begin_cycle();pre=self.drained;old=self.response;stop=abort or soft_reset
  o=dict(acquired=False,released=False,begun=False,accepted=False,acked=False,response=old,owner=self.owner)
  if not self.enabled:
   o.update(dense_allowed=True,tile_allowed=True,clear_allowed=True);return o
  if self.pending is not None:self.response=self.pending;self.pending=None
  if old is not None and self.canonical(ack,ack=True) and ack==old.key:
   self.response=None;o['acked']=True
   if self.scratch and ack.line>=4096 and ack.write and not self.poison and not stop:self.written|=1<<(ack.line-4096)
  if begin is not None:
   if (self.scratch and type(begin)is Context and self.owner is not None and pre and not self.poison and not stop and
       acquire is None and release is None and request is None and begin.owner==self.owner and uint(begin.owner,32,True) and
       uint(begin.generation,32,True) and begin.generation>self.generation and uint(begin.query,7) and uint(begin.kv_head,1)):
    self.generation=begin.generation;self.query=begin.query;self.kv_head=begin.kv_head;self.active=True;self.written=0;o['begun']=True
  elif release is not None:
   if uint(release,32,True) and release==self.owner and pre:self.owner=None;o['released']=True
  elif acquire is not None:
   if uint(acquire,32,True) and self.owner is None and pre and not self.poison and not stop and type(obligations)is Obligations and obligations.drained and not(dense or tile or clear):
    self.owner=acquire;o['acquired']=True
  elif request is not None and pre and not self.poison and not stop:
   if (type(request)is Request and self.canonical(request.key) and request.key.owner==self.owner and uint(request.data,512) and
       (request.key.line<4096 or request.key.write or bool(self.written&(1<<(request.key.line-4096))))):
    k=request.key;a,b,w=location(k.line,scratch_enabled=self.scratch)
    if k.write:self.banks.write(a,w,request.data&((1<<256)-1));self.banks.write(b,w,request.data>>256);data=0
    else:data=self.banks.read(a,w)|(self.banks.read(b,w)<<256)
    self.pending=Response(k,data);o['accepted']=True
  if stop:
   if o['owner'] is not None or not pre:self.poison=True
   elif soft_reset:self.poison=False
  if self.scratch and (o['acquired'] or o['released'] or stop):self.active=False;self.written=0
  allow=o['owner'] is None and not self.poison and not o['acquired']
  o.update(dense_allowed=allow,tile_allowed=allow,clear_allowed=allow);return o
