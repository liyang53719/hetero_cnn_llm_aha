"""Single-parent-edge KV transport for the existing public Attention channel.

No arithmetic or payload storage is implemented here. The public binding patch
retains exact official owner/service policy checks. Scripted consumers may test
this channel contract in isolation; they are never numerical evidence.
"""
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import MemoryResponse
from candidates.qwen2_resident_matrix.raw_kv_parent.model import ParentLoan
from candidates.qwen2_resident_matrix.raw_kv_attention.model import KvSupply,Binding,Read,Reply
from candidates.qwen2_resident_matrix.raw_kv_attention.numeric_bridge import decode_ddr_response,require


class PublicKvTransport:
    def __init__(self,*,owner,parent,job,owner_id=7):
        require(type(parent) is ParentLoan and parent.enabled,'enabled original parent required')
        require(parent.raw.banks is parent.owner.a_banks,'one original bank allocation required')
        require(owner.ports()['job_ready'],'Attention must be ready before binding')
        self.owner,self.parent,self.job=owner,parent,job
        self.supply=KvSupply(parent=parent,enabled=True)
        self.supply.bind(Binding(owner_id,job.tag,job.b,job.c,job.m,job.dst,job.write_bytes))
        self.kv_request=None;self.kv_admitted=False
        self.pending=None;self.route=None
        self.supply_done=False;self.fault_notified=False;self.ticks=0

    def is_kv(self,q):
        return q is not None and not q.write and any(
            base<=q.address<base+self.job.m*1024 for base in (self.job.b,self.job.c))

    def ports(self):
        op=self.owner.ports().copy();q=op['memory'];external=None
        if self.pending is None:
            if self.supply.state=='miss_req':external=self.kv_request
            elif self.kv_request is None and not self.is_kv(q):external=q
        op['memory']=external
        # This is the existing Python driver's offered-response/accepted-event
        # API, not a new Decoupled port. KV acceptance depends on the actual
        # returned beat and raw fill handshake; do not advertise core ready
        # as an external ready signal. The physical driver uses only fire.
        op.pop('memory_response_ready',None)
        if not self.supply_done:op['response']=None
        return op

    def tick(self,*,job=None,memory_ready=True,memory_response=None,
             response_ready=False,raw_ack_ready=True,abort=False,**controls):
        allowed={'matrix_request_ready','matrix_result_ready','service_result_ready',
                 'service_done_ready','done_override'}
        require(set(controls)<=allowed,'unsupported Attention control')
        require(all(type(x) is bool for x in (memory_ready,response_ready,raw_ack_ready,abort)),
                'canonical transport handshake')
        require(job is None or job is self.job,'exact bound public job required')
        op=self.owner.ports();advertised=self.ports();completion_ready=self.supply_done
        pending,route=self.pending,self.route
        require((pending is None)==(route is None),'external request debt mismatch')
        incoming=None;direct_response=None;foreign=False
        if memory_response is not None:
            if route=='direct':
                r=memory_response
                canonical=type(r) is MemoryResponse and type(r.tag) is int and 0<=r.tag<1<<64
                if not canonical or r.tag!=pending.tag:foreign=True
                else:
                    clean=(type(r.error) is bool and type(r.nbytes) is int and r.nbytes==64 and
                           (r.data is None if pending.write else type(r.data) is bytes and len(r.data)==64))
                    direct_response=r if clean else MemoryResponse(pending.tag,None if pending.write else bytes(64),True)
            else:incoming=decode_ddr_response(memory_response,MemoryResponse)
        if foreign:self.supply.fault('foreign direct DDR reply')
        accepted=self.kv_request
        offered=Read(accepted.tag,accepted.address) if accepted is not None and not self.kv_admitted else None
        parent_clock=self.parent.owner.clock
        se=self.supply.tick(request=offered,ddr_ready=memory_ready and pending is None,
            ddr_response=incoming,response_ready=bool(self.kv_admitted and op['memory_response_ready']),
            raw_ack_ready=raw_ack_ready,terminal=op['response'] is not None,
            abort=abort or foreign or self.owner.poison)
        require(self.parent.owner.clock==parent_clock+1,'exactly one parent edge required')
        if se['request_fire']:self.kv_admitted=True
        if se['done_ready']:self.supply_done=True
        notify=se['reset_required'] and not self.fault_notified and not self.owner.poison
        if se['reset_required']:self.fault_notified=True
        core_response=direct_response
        if se['response_fire']:
            require(self.kv_admitted and accepted is not None,'unowned KV reply')
            r=se['response'];require(r.tag==accepted.tag,'KV response identity')
            core_response=MemoryResponse(r.tag,r.data.to_bytes(64,'little'),r.error)
        q=op['memory'];kv=self.is_kv(q)
        core_ready=(self.kv_request is None and se['request_ready']) if kv else (
            memory_ready and pending is None and advertised['memory'] is q)
        edge=self.owner.tick(job=job,memory_ready=core_ready,memory_response=core_response,
            local_reset=notify,response_ready=response_ready and completion_ready,**controls)
        external_response_fire=False
        if edge['memory_response_fire'] and route=='direct':
            require(direct_response is not None,'direct reply without matching debt')
            self.pending=None;self.route=None;external_response_fire=True
        if se['ddr_response_fire']:
            # Foreign replies are quarantined, not acknowledged to the existing
            # PhysicalMemory driver, whose genuine pending request must survive.
            if route=='kv' and not self.supply.ddr_pending:
                self.pending=None;self.route=None;external_response_fire=True
        if se['response_fire']:
            require(edge['memory_response_fire'],'core did not consume advertised KV response')
            self.kv_request=None;self.kv_admitted=False
        external_fire=False
        if edge['memory_fire']:
            q=edge['memory']
            if self.is_kv(q):
                require(q.data is None and self.kv_request is None,'only one payload-free KV request')
                self.kv_request=q;self.kv_admitted=False
            else:
                require(self.pending is None and not se['ddr_fire'],'shared external port overlap')
                self.pending=q;self.route='direct';external_fire=True
        if se['ddr_fire']:
            require(accepted is not None and self.kv_admitted and self.pending is None,'DDR miss ownership')
            require((se['ddr_request'].tag,se['ddr_request'].address)==(accepted.tag,accepted.address),'DDR miss identity')
            self.pending=accepted;self.route='kv';external_fire=True
        if edge['response_fire']:
            require(completion_ready and self.pending is None and self.kv_request is None and
                    self.parent.raw.drained and not self.parent.raw.blocked and not self.supply.ddr_pending,
                    'Host terminal before supplier debt retirement')
        # Preserve the actual core and Matrix events, but expose only the shared
        # external channel to the existing physical driver and its ACK ledger.
        edge['core_memory']=edge['memory'];edge['core_memory_fire']=edge['memory_fire']
        edge['core_memory_response_fire']=edge['memory_response_fire']
        edge['core_memory_response_ready']=edge.pop('memory_response_ready',False)
        edge['memory']=advertised['memory'];edge['memory_fire']=external_fire
        edge['memory_response_fire']=external_response_fire
        edge['response']=advertised['response'];edge['supply']=se
        edge['completion_ready']=completion_ready;self.ticks+=1
        return edge
