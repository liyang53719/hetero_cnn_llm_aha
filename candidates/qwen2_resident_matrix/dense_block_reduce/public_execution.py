"""Public Command128 QKV dispatch through actual two-partial owner transactions.

No arithmetic/reference tensors live in this driver. Every accepted physical
request is serviced from the same public memory map; Matrix results come only
from the acquired existing ELF service. The complete original Dense Job is
published after coordinator terminal, all output windows, final ACK and lease
invalidation. Following Bias/RoPE and all other public jobs use the old driver.
"""
from collections import Counter,deque
from dataclasses import asdict,replace
import ctypes as C
from pathlib import Path
from types import SimpleNamespace
import time

from ..official_bf16.execution import (OfficialPublicExecution,OfficialPrefixOwner,
    OfficialAttentionOwner,OPCODES,validate_job)
from ..ffn_public.execute_numeric import PublicExecution,require,numeric
from ..ffn_public import prefix_execution as prefix
from ..ffn_attention.matrix_service import MatrixValue
from .dense_drain import DenseReductionOwner,Job,drain
from .k_window_model import ReadBeat,MatrixResult,MatrixDone
from .matrix_binding import ProfiledMatrixService
from .public_coordinator import DenseReductionCoordinator,DenseReductionRequest,Services
from .sum_tiles import TileSumController,shared_loan_edge,owner_tile_edge
from .vector_add_model import VectorLoanModel


class ReducedPublicExecution(OfficialPublicExecution):
    """Explicit new policy class; old default/official execution is unchanged."""
    def __init__(self,*args,fixture,**kwargs):
        require(fixture.scope=='QWEN2_21_METADATA_ONLY' and fixture.config.command.count==21 and
            len(fixture.commands)==21 and tuple(int(c.opcode) for c in fixture.commands)==OPCODES and
            all(c.event_wait==i and c.event_signal==i+1 for i,c in enumerate(fixture.commands)),
            'reduced official policy requires the original public21 profile')
        require(type(kwargs.get('prefix_owner')) is OfficialPrefixOwner and
            type(kwargs.get('attention_owner')) is OfficialAttentionOwner and
            type(kwargs.get('matrix_service')) is ProfiledMatrixService and
            type(args[1]) is DenseReductionOwner,'mixed or detached numerical services')
        physical=getattr(args[0].memory,'physical_memory',None)
        require(args[0].config==fixture.config and physical is not None and physical.fixture is fixture,
                'public metadata/actual data source identity')
        self.policy_fixture=fixture;self.policy_jobs={};self.reduction=None;self.reduction_reports=[]
        PublicExecution.__init__(self,*args,**kwargs)

    def reset_required(self):
        base=super().reset_required()
        r=getattr(self,'reduction',None)
        return bool(base or (r is not None and (r.c.poison or r.sum.poison or r.loan.ports()['reset_required'])))

    def report(self):
        r=super().report()
        r.update(qkv_reduction_profile=asdict(self.matrix_service.profile),
            qkv_reductions=list(self.reduction_reports),hardware_cycles=None)
        return r


class ReductionDriver:
    def __init__(self,x,memory,job,*,final_ack_stall=5):
        require(type(x) is ReducedPublicExecution and x.reduction is None,'one selected public reduction')
        require(validate_job(x.policy_fixture,job) in (1,4,7),'only explicit public Q/K/V Dense roles')
        require(x.ports()['ordinary_request'] is job and x.down_job is None,'original public request object')
        self.x,self.memory,self.public_job=x,memory,job
        fields={k:v for k,v in asdict(job).items() if k!='c'}
        require(getattr(job,'c',0)==0,'Dense third root must stay zero')
        self.call=DenseReductionRequest(Job(**fields),job.tag+1,x.matrix_service.profile.ranges,
                                        x.matrix_service.profile.pair_reverse)
        self.call.validate()
        self.source=memory.dense_source(self.call.job);self.source_sha=self.source.validate(self.call.job)
        self.c=DenseReductionCoordinator();self.owner=x.owner;self.service=x.matrix_service
        self.loan=VectorLoanModel(lane_latency=2)
        self.sum=TileSumController(self.owner.tiles,bank_tick=lambda **p:owner_tile_edge(self.owner,**p))
        self.read=None;self.results=deque();self.adapter=None;self.matrix_abort_sent=False
        self.matrix_fault=None;self.matrix_fmas_before=int(self.service.lib.matrix_dense_fmas())
        self.write=None;self.write_index=0;self.ack=None
        self.counts=Counter();self.partials=[];self.drains=[];self.terminal=None
        self.remaining=final_ack_stall;self.final_ack_stall=final_ack_stall
        self.started=False;self.bank_ids=(id(self.owner),id(self.owner.a_banks),id(self.owner.b_banks))
        self.fences_before=(self.owner.a_fences,self.owner.k_a_fences)
        self.matrix_before=dict(self.service.report()['counters'])
        x.reduction=self

    def services(self):
        o=self.owner
        return Services(window_busy=o.window_request is not None and o.state not in ('idle','locked'),
            drain_busy=o.drain_request is not None and o.state not in ('idle','locked'),
            tiles_drained=o.tiles.idle,tiles_leased=o.tiles.leased,vector_drained=self.loan.ports()['drained'],
            sum_busy=self.sum.busy,lease_valid=o.lease is not None,matrix_drained=self.service.owner is None,
            dma_drained=self.read is None and self.write is None,
            window_reset=bool(o.error),drain_reset=bool(o.drain_poison),sum_reset=self.sum.poison,
            vector_reset=self.loan.ports()['reset_required'],tiles_reset=o.tiles.poison,
            backend_reset=self.service.reset_required or self.matrix_fault is not None)

    def tick(self,*,abort=False):
        x,o=self.x,self.owner
        require(time.monotonic()<=x.deadline,'public reduced Dense host wall budget')
        require(self.bank_ids==(id(o),id(o.a_banks),id(o.b_banks)),'public reduction replaced owner/banks')
        svc,op,hp=self.services(),o.ports(),x.ports()
        cp=self.c.ports(svc,abort=abort);before_reset=x.reset_required() or cp['reset_required']
        # Abort is a real one-shot operation on the currently acquired Matrix.
        # Accepted results remain queued and must retire before real Done.
        # Merely poisoning the bank owner cannot close the ELF's live group.
        if cp['backend_abort'] and self.service.owner is o and not self.matrix_abort_sent:
            self.service.abort(o);self.matrix_abort_sent=True
            self.counts['matrix_abort_fire']+=1
        args=dict(abort=cp['backend_abort'],invalidate_lease=cp['invalidate_lease'],
            window_result_ready=cp['window_result_ready'],drain_result_ready=cp['drain_result_ready'])
        se={};t=self.counts['model_ticks']
        if self.c.state in ('sumIssue','sumWait') or self.sum.busy:
            se=shared_loan_edge(self.sum,self.loan,start=cp['sum_request'],abort=cp['backend_abort'],
                                bank_ready=cp['sum_bank_granted'])
            oe={}
        else:
            if cp['window_request'] is not None and op['window_ready']:
                require(self.adapter is None and self.service.acquire(o,'dense',self.call.job.tag),
                        'partial could not acquire same serialized Matrix')
                self.adapter=self.service.dense_library(o);self.matrix_abort_sent=False
                args['window']=cp['window_request']
            if cp['drain_request'] is not None:args['drain']=cp['drain_request']
            backend_fault=self.service.reset_required or self.matrix_fault is not None
            # A negative arithmetic return is a latched backend fault. Block
            # new operands immediately, while accepted DMA/results still drain.
            args.update(read_command_ready=t%5!=0 and not backend_fault,
                        step_ready=t%7!=0 and not backend_fault,group_ready=not backend_fault,
                        write_command_ready=t%5!=0,write_data_ready=t%7!=0)
            # Reserve the existing bounded result queue BEFORE the accepted
            # terminal Matrix step produces a packet. No extra result storage.
            if op.get('step') is not None and op['step'].last and len(self.results)>=2:
                args['step_ready']=False;self.counts['matrix_result_capacity_stall']+=1
            if self.read is not None:
                command,words=self.read;args['read_beat']=ReadBeat(command.tag,words,True)
            if self.results:args['result']=self.results[0]
            q=o.window_request
            if (q is not None and o.group_started and not o.group_done and
                    self.service.owner is o and self.adapter is not None and
                    self.service.lib.matrix_done_ready()):
                # Source readiness includes actual return-queue retirement;
                # neither owner.error nor a logical step count invents Done.
                args['matrix_done']=MatrixDone(q.job.tag,bool(o.error or self.service.reset_required))
            if self.ack is not None:
                final=self.c.write_bytes+o.write_bytes+self.ack.nbytes==self.public_job.write_bytes
                if final and self.remaining:
                    require(cp['result'] is None and o.tiles.tags[2].live,'public success before final ACK')
                    self.remaining-=1;self.counts['final_ack_stall']+=1
                else:args['write_ack']=self.ack
            oe=o.tick(**args)
        ce=self.c.tick(request=self.call if not self.started else None,services=svc,abort=abort,
            window_ready=bool(oe.get('window_fire')),drain_ready=bool(oe.get('drain_fire')),
            sum_ready=bool(se.get('start_fire')),window_result=op.get('window_result'),
            drain_result=op.get('drain_result'),sum_complete=bool(se.get('complete')),
            result_ready=hp['owner_result_ready'])
        self.started|=ce['request_fire']
        for key in ('window_fire','window_result_fire','drain_fire','drain_result_fire'):
            require(bool(ce[key])==bool(oe.get(key)),'public reduction endpoint handshake: '+key)
        require(ce['sum_fire']==bool(se.get('start_fire')),'public shared sum handshake')
        if oe.get('read_fire'):self.read=None
        if oe.get('read_command_fire'):
            require(self.read is None,'overlapping DMA read')
            command=oe['read_command'];require(command.beats==1,'original aligned DDR beat')
            _,words=self.memory.read64(command.address);self.read=(command,words)
        if oe.get('group_fire'):
            q=o.window_request
            require(self.adapter.td_group(0,q.k_end-q.k_begin,q.cols//32)==0,'actual partial Matrix group')
        if oe.get('result_fire'):
            require(self.results,'unsolicited Matrix result');self.adapter.retire_result(self.results.popleft())
        if oe.get('step_fire'):
            s=oe['step'];a=(C.c_uint16*16)(*s.a);b=(C.c_uint16*256)(*s.b);out=(C.c_uint32*4096)()
            rc=self.adapter.td_step(s.k,s.context,s.clear,s.last,s.finish,s.emit,a,b,out)
            if rc<0:
                # The real ELF may fail on finite-input overflow at a terminal
                # lane. Its partial output buffer is NOT a result packet.
                # Preserve the diagnostic, then retire actual Done/owner ACKs.
                if self.matrix_fault is None:
                    self.matrix_fault=dict(rc=rc,tag=self.public_job.tag,k=s.k,context=s.context,
                        block_id=o.window_request.block_id,
                        accepted_steps=self.counts['backend_step_fire']+1,
                        actual_dense_fma_calls=int(self.service.lib.matrix_dense_fmas()))
                self.counts['matrix_step_errors']+=1
            else:
                require(rc==int(s.last),'shared Matrix step/terminal mismatch')
                if rc==1:self.results.append(MatrixResult(s.context,MatrixValue(bytes(out))))
        require(len(self.results)<=2,'actual Matrix result queue overflow')
        if oe.get('matrix_done_fire'):self.adapter.retire_done(args['matrix_done'])
        if ce['window_result_fire']:
            self.partials.append(asdict(op['window_result']))
            self.service.retire_owner_response(o);self.service.release(o);self.adapter=None
        if oe.get('write_command_fire'):
            require(self.write is None,'overlapping write descriptor')
            self.write=oe['write_command'];self.write_index=0
            self.memory.write_event('command',self.write)
        if oe.get('write_data_fire'):
            require(self.write is not None,'write data without accepted descriptor')
            self.memory.write_event('data',oe['write_data']);self.write_index+=1
            if oe['write_data'].last:
                require(self.write_index==self.write.beats,'DMA final data count')
                self.ack=drain.WriteAck(self.write.tag,False,self.write.beats*64)
        if oe.get('write_ack_fire'):
            self.memory.write_event('ack',args['write_ack']);self.write=self.ack=None
        if ce['drain_result_fire']:self.drains.append(asdict(op['drain_result']))
        if ce['request_fire']:
            x.down_job=self.call.job;x.down_start_tick=o.clock
        terminal=None
        if ce['result_fire']:
            require(self.terminal is None,'duplicate public reduction terminal')
            r=ce['result']
            # A held success is stable at the coordinator, but its current
            # reset sideband rejects it at the Host boundary. Once accepted,
            # the resulting terminal is never rewritten or retracted.
            failed=bool(r.status is not None or ce['reset_required'] or x.reset_required())
            if failed and r.status is None:r=replace(r,status='Protocol')
            self.terminal=r
            require(self.read is None and self.write is None and self.ack is None and
                    not self.results and self.adapter is None and self.service.owner is None and
                    self.memory.pending is None and o.tiles.idle and self.loan.ports()['drained'] and
                    not self.sum.busy and o.read_active is None and o.a_hold is None and
                    o.a_rmw_pending is None and o.pending is None and not o.fifo and
                    o.accepted_write is None,
                    'public terminal before all accepted physical obligations retire')
            terminal=numeric.group.OwnerResult(r.tag,r.status,r.write_bytes,r.model_ticks,r.useful_macs,r.executed_macs)
            x.down_terminal=(r.tag,r.status,r.write_bytes);x.down_terminal_tick=o.clock
            if not failed:
                require(o.lease is None and not o.tiles.leased and self.remaining==0 and
                        self.source.validate(self.call.job)==self.source_sha,
                        'success before final ACK hold, tile release or original A provenance')
                self.memory.terminal(self.public_job,terminal)
            # Failed resident tiles remain live/poisoned for coordinated reset;
            # actual already-ACKed DDR bytes are counted but never published.
        x._host_edge(request_ready=ce['request_fire'],owner_result=terminal,
                     reset_required=before_reset or ce['reset_required'])
        require(bool(x.last_host_edge['request_fire'])==ce['request_fire'] and
                bool(x.last_host_edge['owner_result_fire'])==ce['result_fire'],'public Host reduction handshake')
        self.counts['model_ticks']+=1
        for key in ('window_fire','window_result_fire','drain_fire','drain_result_fire','sum_fire','result_fire'):
            self.counts[key]+=ce[key]
        for key in ('read_command_fire','read_fire','step_fire','result_fire','matrix_done_fire',
                    'write_command_fire','write_data_fire','write_ack_fire'):
            self.counts['backend_'+key]+=bool(oe.get(key))
        return ce

    def run(self):
        while self.terminal is None:self.tick()
        counts=self.service.report()['counters']
        report=dict(terminal=asdict(self.terminal),partials=self.partials,drains=self.drains,
            accepted=dict(self.counts),matrix_counter_delta={k:counts.get(k,0)-self.matrix_before.get(k,0)
                for k in counts.keys()|self.matrix_before.keys()},shared_vector=dict(self.sum.counts),
            matrix_step_failure=self.matrix_fault,
            actual_dense_fma_calls_delta=int(self.service.lib.matrix_dense_fmas())-self.matrix_fmas_before,
            failed_step_counter_note=('Owner useful/executed MACs count accepted Matrix step slots; '
                'the software FMA helper can stop mid-step on error.' if self.matrix_fault is not None else None),
            same_owner_and_banks=True,hardware_cycles=None,model_ticks_are_hardware_cycles=False,
            a_fence_events=dict(legacy_ffn_a_fences=self.owner.a_fences,k_window_a_fences=self.owner.k_a_fences,total_window_a_load_fences=self.owner.total_window_a_load_fences,
                legacy_delta=self.owner.a_fences-self.fences_before[0],k_delta=self.owner.k_a_fences-self.fences_before[1]),
            original_public_job=asdict(self.public_job),profile=asdict(self.service.profile))
        self.x.reduction_reports.append(report)
        if self.terminal.status is None:self.x.reduction=None
        return report


def execute_public_prefix(x,memory,lib,output):
    """Same ten public commands; only explicit QKV Dense dispatch is extended."""
    require(len(x.host.program)==21 and x.host.pc==0,'original complete public21 launch from pc0')
    reports=[]
    for pc in range(10):
        ports=x.advance_to_request();job=ports['ordinary_request']
        require(job is not None and job.tag&0xffff==pc,'original public prefix ordering')
        if job.kind=='Dense':report=ReductionDriver(x,memory,job).run()
        else:report=prefix.execute_prefix_owner(x,memory,job)
        x.publish_completions((pc,));memory.publish(job,x.host)
        if job.kind=='Dense':x.retire_ordinary_bookkeeping()
        reports.append(dict(pc=pc,kind=job.kind,report=report))
    return reports
