"""Explicit outer-edge scratch protocol; no callback may tick a parent owner."""
from dataclasses import dataclass

def uint(v,bits):return type(v) is int and 0 <= v < 1 << bits
@dataclass(frozen=True)
class ScratchAction:
    serial:int
    operation:str
    generation:int
    query:int
    kv_head:int
    line:int=0
    words:tuple=()
    def valid(self):
        return (uint(self.serial,32) and uint(self.generation,32) and uint(self.query,7) and uint(self.kv_head,1) and uint(self.line,13)
            and self.operation in ('acquire','begin','read','write','release')
            and type(self.words) is tuple and all(uint(x,32) for x in self.words)
            and (self.operation not in ('read','write') or type(self.line) is int and 4096<=self.line<4192)
            and (len(self.words)==16 if self.operation=='write' else len(self.words)==0))
@dataclass(frozen=True)
class ScratchResponse:
    action:ScratchAction
    words:tuple=()
    error:bool=False
