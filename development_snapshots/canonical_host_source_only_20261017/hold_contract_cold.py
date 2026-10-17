"""Python-only negative control contract; NOT the C++ implementation or RTL probe.
Used to specify the required rejected sequences while C++ remains uncompiled.
"""
from dataclasses import dataclass

def need(ok, reason):
 if not ok:raise ValueError(reason)

def normal_result(status,completed,failed_pc,epoch):
 need((status,completed,failed_pc,epoch)==(0,21,20,7),'all four normal-result fields')

@dataclass(frozen=True)
class Observation:
 ar:bool=False
 aw:bool=False
 w:bool=False
 axi_debt:int=0
 physical_debt:int=0
 issued:int=1
 axi_counts:tuple=(0,0,0,0,0)
 hub_counts:tuple=(0,0,0,0)
 # Abstract actual-observer cumulative activity; intentionally not RTL port names.
 owner_activity:tuple=(1,1)
 matrix_loan_prefix_activity:tuple=(0,0,0,0,0,0)

def quiet(o):
 need(not(o.ar or o.aw or o.w),'no new AXI offers')
 need(o.axi_debt==0,'AXI debt must remain zero')
 need(o.physical_debt==0,'independent physical debt must remain zero')

class Hold:
 def __init__(self):self.snapshot=None;self.word=None;self.compares=0;self.released=False
 def observe(self,word,o):
  need(not self.released,'observation after hold release')
  quiet(o)
  if self.snapshot is None:
   self.snapshot=o;self.word=word;self.compares+=1
  else:
   need(self.word==word,'payload stability')
   need(self.snapshot==o,'no activity since FIRST visible snapshot')
 def ack(self,word,o,valid,ready):
  need(valid and ready,'actual ACK required for release')
  self.observe(word,o);self.released=True
