"""Only KV supply changes; all live PV32 arithmetic functions are inherited."""
import struct
from candidates.qwen2_live_attention_model_m128.pv32_owner import OfficialPV32AttentionOwner
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import PrefixFault
from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ArithmeticFault
from .scratch import SharedAScratch,ReadonlyKVIdentity,LocalRequest,LocalResponse,CacheFault,need

class _Replay:
    """Feed an already yielded non-cache action to the unchanged dispatcher."""
    def __init__(self,action,error):self.action,self.error=action,error
    def send(self,unused):
        if self.error is not None:raise self.error
        return self.action

class ResidentPV32AttentionOwner(OfficialPV32AttentionOwner):
    def __init__(self,matrix,scalar=None,*,max_tokens=128,scratch=None,identity=None):
        scratch=scratch if scratch is not None else getattr(self,'scratch',None)
        identity=identity if identity is not None else getattr(self,'kv_identity',None)
        need(type(scratch) is SharedAScratch and type(identity) is ReadonlyKVIdentity,'caller-owned scratch and KV producer identity required')
        need(scratch.owner is None and scratch.pending is None,'owner construction/reset before A drain')
        super().__init__(matrix,scalar,max_tokens=max_tokens)
        self.scratch=scratch;self.kv_identity=identity;self.local_request=None
        self.local_pending=False;self.local_serial=0;self.deferred_finish=None
    def _validate(self,j):
        super()._validate(j)
        if j.m>128:raise PrefixFault('Bounds','resident M128 fixed capacity')
        if self.scratch.owner is not None or self.scratch.pending is not None:
            raise PrefixFault('Protocol','shared A lease busy')
        self.kv_identity.validate()
    def _read(self,address):
        j=self.job
        if self.scratch.owner is None:
            self.scratch.acquire(self,j,self.kv_identity)
        self.scratch.check(self)
        line=self.scratch.line(address)
        if line is None:return (yield from super()._read(address))
        self.local_serial+=1
        if self.scratch.present(line):
            response=yield self.scratch.make_request(self,address,self.local_serial)
            return struct.unpack('<16I',response.data)
        words=yield from super()._read(address)
        # Original memory tag/error/length validation has already accepted words.
        # Raw FP32 bits, including nonfinite payloads, retain original arithmetic
        # fault timing. Valid is set only after the local fill commit ACK.
        response=yield self.scratch.make_request(self,address,self.local_serial,struct.pack('<16I',*words))
        return words
    def _advance(self,response=None):
        source=self.program;action=error=None
        try:action=source.send(response)
        except (StopIteration,PrefixFault,ArithmeticFault) as e:error=e
        except CacheFault as e:error=PrefixFault('Protocol',str(e))
        if isinstance(action,LocalRequest):
            self.local_request=action;self.state='cache_issue';return
        replay=_Replay(action,error);self.program=replay
        super()._advance()
        if self.program is replay:self.program=source
    def ports(self):
        p=super().ports();p.update(cache_request=self.local_request if self.state=='cache_issue' else None,
          cache_response=self.scratch.response() if self.local_pending else None,
          cache_response_ready=self.local_pending)
        p['job_ready']=p['job_ready'] and self.scratch.owner is None and self.scratch.pending is None
        return p
    def _fault(self,status,detail):
        self.local_request=None
        if self.scratch.owner is self:self.scratch.revoke()
        super()._fault(status,detail)
    def _finish(self,status=None,detail=None):
        if self.local_pending:
            self.deferred_finish=(status,detail);self.state='drain';return
        super()._finish(status,detail)
    def tick(self,*,cache_request_ready=True,cache_response_ready=True,cache_response_override=None,**inputs):
        self.scratch.clock+=1;p=self.ports()
        if self.scratch.owner is self and self.scratch.revoked and not self.poison:
            self._fault('Protocol','KV lease write/generation revoked')
        edge=super().tick(**inputs)
        edge.update(cache_request=p['cache_request'],cache_response=p['cache_response'],
          cache_request_fire=False,cache_response_fire=False)
        cancelling=self.poison or any(inputs.get(k,False) for k in ('local_reset','reset'))
        if p['cache_request'] is not None and cache_request_ready and not cancelling:
            try:
                self.scratch.accept(self,p['cache_request']);self.local_pending=True
                self.local_request=None;self.state='cache_wait';edge['cache_request_fire']=True
            except CacheFault as e:self._fault('Protocol',str(e))
        if p['cache_response'] is not None and cache_response_ready:
            authentic=p['cache_response'];visible=authentic if cache_response_override is None else cache_response_override
            valid=(type(visible) is LocalResponse and visible==authentic)
            self.scratch.consume(self,abort=cancelling or not valid)
            self.local_pending=False;edge['cache_response_fire']=True
            if not valid:self._fault('Protocol','local cache response identity/data mismatch')
            elif not cancelling and self.state!='drain':self._advance(authentic)
            if self.deferred_finish is not None:
                status,detail=self.deferred_finish;self.deferred_finish=None;super()._finish(status,detail)
        if edge['response_fire'] and self.scratch.owner is self:self.scratch.release(self)
        return edge
    def report(self):
        r=super().report();r.update(resident_cache=self.scratch.report(),local_pending=self.local_pending,
          supply_policy='RAW_FP32_LAZY_FILL_ACCEPTED_MEMORY_ONLY',arithmetic='INHERITED_LIVE_PV32_FUNCTIONS',
          rtl_executed=False,m128_executed=False)
        return r
