"""One outer edge per shared Dense owner and raw bank port.

This new routing adapter is not wired into PublicKvTransport yet. Its response
means the physical raw matching ACK retired, never just a request acceptance.
"""
from .protocol import ScratchAction,ScratchResponse
from ..raw_kv_parent.model import ParentLoan
from ..attention_bank_scratch.port import RawKvPort,Key,Request

class ScratchBridge:
    def __init__(self,owner=None):
        self.parent=ParentLoan(owner=owner,enabled=True)
        if any(self.parent.debts().values()) or not self.parent.raw.drained or self.parent.raw.owner is not None:raise ValueError('scratch install debt')
        self.parent.raw=RawKvPort(self.parent.owner.a_banks,enabled=True,scratch_enabled=True)
        self.banks=self.parent.owner.a_banks;self.context=None;self.valid=set();self.active=None;self.response=None;self.key=None;self.edges=0;self.last_serial=0
    def ports(self):return dict(ready=self.active is None and self.response is None,response=self.response)
    def tick(self,*,action=None,response_ready=False,abort=False):
        p=self.ports();p.update(accepted=False,response_fire=False)
        if p['response'] is not None and response_ready:self.response=None;p['response_fire']=True
        inputs={'abort':abort}
        a=action if p['ready'] else None
        if a is not None:
            if type(a) is not ScratchAction or not a.valid() or a.serial<=self.last_serial:raise ValueError('scratch action')
            if a.operation in ('read','write') and self.context!=(a.generation,a.query,a.kv_head):raise ValueError('stale scratch context')
            if a.operation=='read' and a.line not in self.valid:raise ValueError('unwritten scratch read')
            if a.operation=='acquire':inputs['acquire']=1
            elif a.operation=='release':inputs['release']=1
            elif a.operation=='begin':
                if not self.parent.raw.drained or self.parent.raw.owner!=1 or (self.context and a.generation<=self.context[0]):raise ValueError('scratch generation debt')
            else:
                self.key=Key(1,a.serial,a.line,a.operation=='write')
                inputs['request']=Request(self.key,sum(x<<(32*i) for i,x in enumerate(a.words)))
        held=self.parent.raw.response
        if self.active is not None and held is not None:
            if held.key!=self.key:raise ValueError('foreign raw response')
            inputs['ack']=self.key
        out=self.parent.tick(**inputs)['raw'];self.edges+=1
        if a is not None:
            if a.operation in ('read','write'):
                if not out['accepted']:raise ValueError('raw scratch request rejected')
                self.active=a
            else:
                ok=out['acquired'] if a.operation=='acquire' else out['released'] if a.operation=='release' else not self.parent.raw.poison
                if a.operation=='begin' and ok:self.context=(a.generation,a.query,a.kv_head);self.valid.clear()
                self.response=ScratchResponse(a,(),not ok)
            self.last_serial=a.serial
            if a.operation in ('acquire','release') and not self.response.error:self.context=None;self.valid.clear()
            p['accepted']=True
        if out['acked']:
            a=self.active;bad=self.parent.poison or self.parent.raw.poison
            words=tuple((held.data>>(32*i))&0xffffffff for i in range(16)) if a.operation=='read' else ()
            if a.operation=='write' and not bad:self.valid.add(a.line)
            self.response=ScratchResponse(a,words,bad);self.active=self.key=None
        return p
