"""Public pc1/4 bridge for the explicit serial diagnostic software owner.

One actual original Host, PhysicalMemory, Dense/Banks and shared Matrix identity
are retained. The Matrix is exclusively reserved, with zero Matrix arithmetic
issues. The new native kernel executes the reported FMA/Add work independently.
"""
from collections import Counter
from dataclasses import asdict
from types import SimpleNamespace
import time
from .owner import Exact64ProjectionOwner, MemoryResponse, need
from candidates.qwen2_resident_matrix.ffn_public.execute_numeric import PublicExecution
from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory
from candidates.qwen2_resident_matrix.official_bf16.execution import validate_job
from candidates.qwen2_attention_shared_a_integration.banks import LoanDenseOwner

class Exact64PublicDriver:
    def __init__(self,x,physical,job,projection_owner,*,final_ack_stall=5):
        need(isinstance(x,PublicExecution) and type(physical) is PhysicalMemory,'actual public execution/physical memory')
        need(type(projection_owner) is Exact64ProjectionOwner and type(x.owner) is LoanDenseOwner,'exact diagnostic owner and original guarded Dense')
        need(type(final_ack_stall) is int and final_ack_stall>=0,'natural final ACK delay')
        need(physical.fixture is x.policy_fixture and getattr(x.frontend.memory,'physical_memory',None) is physical,
             'same public allocation/metadata authority')
        self.pc=validate_job(x.policy_fixture,job);need(self.pc in (1,4),'diagnostic exact64 only pc1/4')
        need(x.ports()['ordinary_request'] is job and x.down_job is None and x.reduction is None and
             getattr(x,'exact64_projection',None) is None,'original unaccepted public job')
        need(projection_owner.ports()['job_ready'] and not x.reset_required(),'clean diagnostic admission')
        projection_owner.validate(job)
        self.x,self.memory,self.public_job,self.backend=x,physical,job,projection_owner
        self.owner=x.owner;self.service=x.matrix_service;self.guard=self.owner.bank_guard
        self._quiescent()
        # Existing publication validation is host auditing, not an arithmetic
        # source or a hidden full-row/weight cache. Arithmetic still reads beats.
        self.source=physical.dense_source(job);self.source_sha=self.source.validate(job)
        weight_name,weight=physical.region(job.b,job.k*job.n*2)
        need(weight['readonly'] and weight['dtype']==5 and callable(weight['provider']),'typed original weight source')
        self.weight_identity=(weight_name,id(weight),id(weight['provider']))
        self.bank_ids=(id(self.owner),id(self.owner.a_banks),id(self.owner.b_banks),id(self.owner.tiles.banks))
        self.counts=Counter();self.pending=None;self.held=None;self.started=False;self.terminal=None;self.cancelled=False
        self.remaining=final_ack_stall;self.final_ack_stall=final_ack_stall;self.final_ack_tick=None;self.terminal_tick=None
        self.matrix_before=dict(self.service.report()['counters'])
        self.dense_before=int(self.service.lib.matrix_dense_fmas());self.normal_before=int(self.service.lib.matrix_normal_fmas())
        self.kernel_before=self.backend.kernel.report();self.matrix_abort_sent=False
        x.exact64_projection=self
    def _quiescent(self):
        d=self.owner;a=self.x.attention_owner;s=self.x.prefix_owner.scalar
        need(d.state=='idle' and d.lease is None and d.tiles.idle and not d.tiles.leased and
          d.read_active is None and d.a_hold is None and d.a_rmw_pending is None and d.pending is None and
          not d.fifo and d.accepted_write is None and not d.ports().get('response') and
          self.memory.pending is None and self.guard.lease is None and self.service.owner is None and
          self.service.lib.matrix_state()==0 and s.client is None and self.x.prefix_owner.state=='idle' and
          a.state=='idle' and not a.memory_pending and not a.abort_pending and
          a.matrix_client is None and a.matrix_request is None,'projection entry requires original complete drain')
    def _exclusive(self):
        d=self.owner
        need(self.bank_ids==(id(d),id(d.a_banks),id(d.b_banks),id(d.tiles.banks)),'original bank identity changed')
        need(self.guard.lease is self and self.service.owner is self.backend and
          d.state=='idle' and d.lease is None and d.tiles.idle and not d.tiles.leased and
          d.read_active is None and d.a_hold is None and d.a_rmw_pending is None and d.pending is None and
          not d.fifo and d.accepted_write is None and self.x.prefix_owner.scalar.client is None and
          self.x.prefix_owner.state=='idle' and self.x.attention_owner.state=='idle' and
          not self.x.attention_owner.memory_pending and not self.x.attention_owner.abort_pending and
          self.x.attention_owner.matrix_client is None and self.x.attention_owner.matrix_request is None,
          'diagnostic projection exclusion violated')
        name,w=self.memory.region(self.public_job.b,self.public_job.k*self.public_job.n*2)
        need(self.weight_identity==(name,id(w),id(w['provider'])),'weight provider identity drift')
    def tick(self,*,abort=False):
        need(type(abort) is bool,'canonical driver abort')
        need(not self.cancelled and self.terminal is None,'closed diagnostic driver')
        if abort and not self.started:
            # Nothing has been accepted. Do not acquire Matrix/A or invent a
            # terminal for a job still offered by the public Host.
            self.cancelled=True;self.x.exact64_projection=None
            return dict(cancelled=True,job_fire=False,memory_fire=False,memory_response_fire=False,response_fire=False)
        need(time.monotonic()<=self.x.deadline,'diagnostic projection host wall budget')
        x=self.x;b=self.backend;hp=x.ports();bp=b.ports();t=self.counts['ticks']
        if not self.started:
            self._quiescent()
            need(self.service.acquire(b,'dense',self.public_job.tag),'serialized Matrix reservation')
            self.guard.lease=self
        self._exclusive()
        if abort and not self.matrix_abort_sent:
            self.service.abort(b);self.matrix_abort_sent=True
        args=dict(job=self.public_job if not self.started else None,memory_ready=t%5!=0,
                  response_ready=bool(hp['owner_result_ready']),abort=abort)
        response=None
        if self.pending is not None:
            q,data=self.pending
            if q.write and b.ack_bytes+64==self.public_job.write_bytes and self.remaining and not abort:
                need(bp['response'] is None and (self.public_job.dst,self.public_job.dst+self.public_job.write_bytes) not in x.host.published,
                     'projection final ACK precedes terminal/publication')
                self.remaining-=1;self.counts['final_ack_stall']+=1
            else:response=MemoryResponse(q.tag,data);args['memory_response']=response
        # Guarded original Dense/Tile tick is the sole A begin_cycle this edge.
        # Its direct external entry points remain blocked for the whole lease.
        with self.guard.edge():
            self.guard.clock_only=True;self.owner.tick()
        edge=b.tick(**args)
        if self.held is not None and not abort:need(edge['memory']==self.held,'held memory request drift')
        self.held=edge['memory'] if edge['memory'] is not None and not args['memory_ready'] else None
        if edge['memory_response_fire']:
            need(self.pending is not None,'response without accepted memory debt')
            q,_=self.pending
            if q.write:
                self.memory.write_event('ack',SimpleNamespace(tag=response.tag,error=response.error,nbytes=response.nbytes))
                if b.ack_bytes==self.public_job.write_bytes:self.final_ack_tick=t
            self.pending=None
        if edge['memory_fire']:
            need(self.pending is None,'overlapping physical memory request')
            q=edge['memory']
            if q.write:
                self.memory.write_event('command',SimpleNamespace(address=q.address,beats=1,tag=q.tag))
                self.memory.write_event('data',SimpleNamespace(words=q.words,mask=q.mask,last=True));data=None
            else:data=self.memory.read_bytes64(q.address)
            self.pending=(q,data)
        if edge['job_fire']:
            x.down_job=self.public_job;x.down_start_tick=self.owner.clock;self.started=True
        terminal=None
        if edge['response_fire']:
            need(self.pending is None and self.memory.pending is None,'terminal before physical debt drain')
            terminal=edge['response'];self.terminal=terminal;self.terminal_tick=t
            if terminal.status is None:
                need(self.remaining==0 and self.final_ack_tick is not None and t>self.final_ack_tick and
                     self.source.validate(self.public_job)==self.source_sha,'terminal ACK/source fence')
                self.memory.terminal(self.public_job,terminal)
            x.down_terminal=(terminal.tag,terminal.status,terminal.write_bytes);x.down_terminal_tick=self.owner.clock
        x._host_edge(request_ready=edge['job_fire'],owner_result=terminal,
                     reset_required=bool(b.poison or self.service.reset_required))
        need(bool(x.last_host_edge['request_fire'])==edge['job_fire'] and
             bool(x.last_host_edge['owner_result_fire'])==edge['response_fire'],'actual public Host handshake')
        if edge['response_fire']:
            self.service.retire_owner_response(b);self.service.release(b)
            need(self.guard.lease is self,'projection lease owner drift');self.guard.lease=None
            if terminal.status is None:x.exact64_projection=None
        self.counts['ticks']+=1
        for name in ('job_fire','memory_fire','memory_response_fire','response_fire'):self.counts[name]+=edge[name]
        return edge
    def run(self):
        need(not self.cancelled,'cancelled before job acceptance')
        while self.terminal is None:self.tick()
        r=self.backend.report();counters=self.service.report()['counters'];k=self.backend.kernel.report()
        r.update(job=asdict(self.public_job),terminal=asdict(self.terminal),
          useful_macs=self.terminal.useful_macs,executed_macs=self.terminal.executed_macs,
          driver_counts=dict(self.counts),partial_bytes=16384,
          matrix_counter_delta={n:counters.get(n,0)-self.matrix_before.get(n,0) for n in counters.keys()|self.matrix_before.keys()},
          actual_dense_fma_calls_delta=int(self.service.lib.matrix_dense_fmas())-self.dense_before,
          actual_normal_fma_calls_delta=int(self.service.lib.matrix_normal_fmas())-self.normal_before,
          final_ack_fence=dict(terminal_strictly_after_final_ack=self.final_ack_tick is not None and self.terminal_tick>self.final_ack_tick,
            held_ticks=self.counts['final_ack_stall'],final_ack_tick=self.final_ack_tick,terminal_tick=self.terminal_tick),
          same_owner_and_banks=True,hardware_cycles=None,
          host_audit_full_n0_copy_bytes=self.public_job.m*1536*4,
          payload_capacity_scope='ARITHMETIC_OWNER_ONLY_EXCLUDES_HOST_PHYSICAL_MEMORY_AND_AUDIT')
        r['kernel_delta']['tiles_started']=k['tiles_started']-self.kernel_before['tiles_started']
        return r
