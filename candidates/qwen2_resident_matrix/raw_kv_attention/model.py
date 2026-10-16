"""Model-only KV transport for original PV16 Attention; no arithmetic execution.

Only metadata is retained here. Payload remains in original DDR or the parent's
sole A Banks/raw response register. reset_required is a PROPOSED consumer fault
sideband; the current Chisel core does not implement that suppression contract.
"""
from dataclasses import dataclass
from candidates.qwen2_resident_matrix.raw_kv.model import Key,Request,uint
from candidates.qwen2_resident_matrix.raw_kv_parent.model import ParentLoan

@dataclass(frozen=True)
class Binding:
    owner:int
    tag:int
    k_base:int
    v_base:int
    tokens:int
    output_base:int
    output_bytes:int

@dataclass(frozen=True)
class Read:
    tag:int
    address:int

@dataclass(frozen=True)
class Reply:
    tag:int
    data:int
    error:bool=False

class KvSupply:
    def __init__(self,parent=None,*,enabled=False):
        self.parent=parent if parent is not None else ParentLoan(enabled=enabled)
        if type(enabled) is not bool:raise ValueError('canonical enable')
        self.enabled=enabled;self.binding=None;self.valid=bytearray(512)
        self.state='idle';self.current=None;self.raw_key=None;self.serial=0
        self.poison=False;self.closing=False;self.ddr_pending=False
        self.core_pending=False;self.error_reason=None;self.bound_requests=0
        self.counts=dict(core_requests=0,ddr_requests=0,ddr_responses=0,
            foreign_responses=0,fills=0,hits=0,core_responses=0,releases=0)

    @property
    def reset_required(self):
        p=self.parent
        return self.poison or p.poison or p.raw.poison or p.owner.error is not None or p.owner.tiles.poison or p.owner.drain_poison

    def bind(self,b):
        if not self.enabled:raise ValueError('disabled: retain original memory route')
        if type(b) is not Binding or not all(uint(x,32,True) for x in (b.owner,b.tag)):
            raise ValueError('canonical owner/job identity')
        if type(b.tokens) is not int or not 1<=b.tokens<=128:raise ValueError('M1..128')
        if type(b.output_bytes) is not int or b.output_bytes!=b.tokens*6144:raise ValueError('output extent')
        spans=((b.k_base,b.tokens*1024),(b.v_base,b.tokens*1024),(b.output_base,b.output_bytes))
        if any(not uint(a,64) or a%64 or a+n>1<<64 for a,n in spans):raise ValueError('aligned nonoverflowing spans')
        if any(a<q+m and q<a+n for i,(a,n) in enumerate(spans) for q,m in spans[:i]):raise ValueError('KV/output alias')
        if self.binding is not None or self.core_pending or self.ddr_pending or not self.parent.raw.drained or self.parent.raw.blocked or self.reset_required:
            raise ValueError('binding requires retired healthy ownership')
        if not self.parent.raw.enabled:raise ValueError('parent raw port disabled')
        self.binding=b;self.valid[:]=bytes(512);self.closing=False;self.bound_requests=0

    def line(self,address):
        b=self.binding
        if b is None or not uint(address,64) or address%64:return None
        for base,start in ((b.k_base,0),(b.v_base,2048)):
            if base<=address<base+b.tokens*1024:return start+(address-base)//64
        return None

    def present(self,line):
        if not uint(line,12):raise ValueError('line')
        return bool(self.valid[line//8]&(1<<(line%8)))

    def fault(self,reason):
        self.poison=True;self.error_reason=self.error_reason or reason;self.valid[:]=bytes(512)

    def _key(self,write):
        if self.serial==(1<<32)-1:
            self.fault('raw serial exhausted');return None
        self.serial+=1
        return Key(self.binding.owner,self.serial,self.line(self.current.address),write)

    def tick(self,*,request=None,ddr_ready=False,ddr_response=None,response_ready=False,
             terminal=False,abort=False,raw_ack_ready=True,**parent_inputs):
        if not all(type(v) is bool for v in (ddr_ready,response_ready,terminal,abort,raw_ack_ready)):
            raise ValueError('canonical handshake flags')
        if any(k in parent_inputs for k in ('acquire','release','request','ack','abort','soft_reset')):
            raise ValueError('raw controls owned by supply')
        state=self.state;raw=self.parent.raw;held=raw.response
        advertised=None
        if state=='read_wait' and held is not None and held.key==self.raw_key:
            advertised=Reply(self.current.tag,held.data)
        elif state=='error_response':advertised=Reply(self.current.tag,0,True)
        ready=self.enabled and self.binding is not None and state=='idle' and not self.closing and not terminal and ((not self.reset_required and not abort) or self.bound_requests==0)
        valid_request=type(request) is Read and uint(request.tag,64) and self.line(request.address) is not None
        out=dict(request_ready=ready,request_fire=False,ddr_request=self.current if state=='miss_req' else None,
            ddr_fire=False,ddr_response_fire=False,response=advertised,response_fire=False,
            released=False,done_ready=False,reset_required=self.reset_required or abort)
        controls={}
        if terminal:self.closing=True
        if abort:self.fault('consumer abort')
        if self.enabled and self.binding is not None and ddr_response is not None and not self.ddr_pending:
            self.fault('unsolicited DDR reply');out['ddr_response_fire']=True
            self.counts['foreign_responses']+=1
        if self.reset_required:self.valid[:]=bytes(512)
        if self.enabled and self.binding is not None:
            if ready and request is not None:
                if not valid_request:raise ValueError('canonical bound KV read')
                self.current=request;self.core_pending=True;out['request_fire']=True
                self.counts['core_requests']+=1;self.bound_requests+=1
                self.state='error_response' if self.reset_required else ('acquire' if not raw.blocked else 'lookup')
            elif state=='acquire':
                if self.reset_required:self.state='error_response'
                else:
                    controls['acquire']=self.binding.owner
                    if self.parent.owner.lease is not None:parent_inputs['invalidate_lease']=True
            elif state=='lookup':
                if self.reset_required:self.state='error_response'
                elif self.present(self.line(self.current.address)):
                    self.counts['hits']+=1;self.state='read_issue'
                else:self.state='miss_req'
            elif state=='miss_req':
                # Once offered, Decoupled valid and identity remain until ready,
                # even after abort; accepted DDR debt must then drain.
                if ddr_ready:
                    self.ddr_pending=True;out['ddr_fire']=True;self.counts['ddr_requests']+=1;self.state='miss_wait'
            elif state=='miss_wait' and ddr_response is not None:
                canonical=type(ddr_response) is Reply and uint(ddr_response.tag,64) and uint(ddr_response.data,512) and type(ddr_response.error) is bool
                if not canonical or ddr_response.tag!=self.current.tag:
                    self.fault('foreign/malformed DDR reply');out['ddr_response_fire']=True
                    self.counts['foreign_responses']+=1  # does NOT retire accepted DDR debt
                elif self.reset_required or ddr_response.error:
                    self.fault('DDR error or revoked fill');self.ddr_pending=False
                    out['ddr_response_fire']=True;self.counts['ddr_responses']+=1;self.state='error_response'
                else:
                    if self.raw_key is None:self.raw_key=self._key(True)
                    if self.raw_key is not None:controls['request']=Request(self.raw_key,ddr_response.data)
                    else:
                        self.ddr_pending=False;out['ddr_response_fire']=True;self.counts['ddr_responses']+=1;self.state='error_response'
            elif state=='fill_wait' and held is not None and raw_ack_ready:
                if held.key!=self.raw_key:self.fault('foreign raw response')
                else:controls['ack']=self.raw_key
            elif state=='read_issue':
                if self.reset_required:self.state='error_response'
                else:
                    if self.raw_key is None:self.raw_key=self._key(False)
                    if self.raw_key is not None:controls['request']=Request(self.raw_key)
                    else:self.state='error_response'
            elif state=='read_wait' and held is not None:
                if held.key!=self.raw_key:self.fault('foreign raw response')
                elif response_ready:
                    out['response_fire']=True;self.core_pending=False
                    self.counts['core_responses']+=1;self.state='ack_wait'
                    if raw_ack_ready:controls['ack']=self.raw_key
            elif state=='ack_wait' and held is not None:
                if held.key!=self.raw_key:self.fault('foreign raw response')
                elif raw_ack_ready:controls['ack']=self.raw_key
            elif state=='error_response' and response_ready:
                out['response_fire']=True;self.core_pending=False;self.current=None;self.state='idle'
                self.counts['core_responses']+=1
            elif state=='idle' and self.closing and not self.core_pending and not self.ddr_pending and raw.drained:
                if raw.blocked:controls['release']=self.binding.owner
                else:self.binding=None;self.valid[:]=bytes(512);out['done_ready']=True
        if self.enabled and self.reset_required:controls['abort']=True
        edge=self.parent.tick(**controls,**parent_inputs);out['parent']=edge
        r=edge['raw']
        if r['acquired']:self.state='lookup'
        if state=='miss_wait' and r['accepted']:
            self.ddr_pending=False;out['ddr_response_fire']=True;self.counts['ddr_responses']+=1;self.state='fill_wait'
        if state=='fill_wait' and r['acked']:
            if not self.reset_required:
                line=self.raw_key.line;self.valid[line//8]|=1<<(line%8);self.counts['fills']+=1
                self.state='read_issue'
            else:self.state='error_response'
            self.raw_key=None
        if state=='read_issue' and r['accepted']:self.state='read_wait'
        if state in ('read_wait','ack_wait') and r['acked']:
            self.current=self.raw_key=None;self.state='idle'
        if r['released']:
            self.binding=None;self.valid[:]=bytes(512);out['released']=True;out['done_ready']=True;self.counts['releases']+=1
        out['reset_required']=self.reset_required or abort
        return out
