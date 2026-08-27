"""Accumulator context scheduling E0 model."""
from collections import deque
from dataclasses import dataclass
@dataclass(frozen=True)
class Step:context:int;delta:tuple;tag:int
class Model:
    def __init__(self,contexts,lanes,latency):self.contexts=contexts;self.lanes=lanes;self.latency=latency;self.busy=[0]*contexts;self.acc=[[0.0]*lanes for _ in range(contexts)];self.q=deque();self.cycle=0;self.accepted=0;self.completed=0
    def issue(self,s):
        if self.busy[s.context]:return False
        self.busy[s.context]=1;self.q.append((self.cycle+self.latency,s));self.accepted+=1;return True
    def tick(self):
        self.cycle+=1;out=[]
        while self.q and self.q[0][0]<=self.cycle:
            _,s=self.q.popleft();self.acc[s.context]=[a+d for a,d in zip(self.acc[s.context],s.delta)];self.busy[s.context]=0;self.completed+=1;out.append(s.tag)
        return tuple(out)
def utilization(contexts,latency):return min(1.0,contexts/latency)
