"""Compact two-level paged-KV E0 reference with prefix sharing and COW."""
from dataclasses import dataclass,field
@dataclass(frozen=True)
class Key: sequence:int;layer:int;head:int
@dataclass
class Stream:generation:int;length:int=0;pages:dict=field(default_factory=dict)
class PagedKV:
    def __init__(self,page_tokens=16,max_pages=256):self.page_tokens=page_tokens;self.free=list(range(max_pages));self.payload={};self.refs={};self.streams={}
    def create(self,key,generation):self.streams[key]=Stream(generation)
    def _state(self,key,generation):
        s=self.streams[key]
        if s.generation!=generation:raise ValueError('stale generation')
        return s
    def _alloc(self,copy=None):
        if not self.free:raise MemoryError('KV OOM')
        p=self.free.pop(0);self.payload[p]=[None]*self.page_tokens if copy is None else list(self.payload[copy]);self.refs[p]=1;return p
    def append(self,key,generation,value):
        s=self._state(key,generation);lp,off=divmod(s.length,self.page_tokens);p=s.pages.get(lp)
        if p is None:p=self._alloc();s.pages[lp]=p
        elif self.refs[p]>1:
            np=self._alloc(p);self.refs[p]-=1;s.pages[lp]=p=np
        self.payload[p][off]=value;s.length+=1
    def gather(self,key,generation,start,count):
        s=self._state(key,generation)
        if start+count>s.length:raise ValueError('range')
        return tuple(self.payload[s.pages[i//self.page_tokens]][i%self.page_tokens] for i in range(start,start+count))
    def fork(self,parent,child,generation,prefix):
        ps=self._state(parent,generation);cs=Stream(generation,prefix);full,tail=divmod(prefix,self.page_tokens)
        for lp in range(full):p=ps.pages[lp];self.refs[p]+=1;cs.pages[lp]=p
        if tail:cs.pages[full]=self._alloc(ps.pages[full]);self.payload[cs.pages[full]][tail:]=[None]*(self.page_tokens-tail)
        self.streams[child]=cs
    def free_stream(self,key,generation):
        s=self._state(key,generation)
        for p in s.pages.values():
            self.refs[p]-=1
            if not self.refs[p]:del self.refs[p];del self.payload[p];self.free.append(p)
        del self.streams[key]
    def assert_ok(self):
        seen={p:0 for p in self.refs}
        for s in self.streams.values():
            for p in s.pages.values():seen[p]+=1
        assert seen==self.refs
def analyze(tokens,page_tokens=16,radix_bits=10):
    pages=(tokens+page_tokens-1)//page_tokens
    if pages>1<<(2*radix_bits):raise ValueError('range')
    return {'tokens':tokens,'logical_pages':pages,'leaf_tables':(pages+(1<<radix_bits)-1)//(1<<radix_bits)}
