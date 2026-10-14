"""Exact public21 role binding for new PV32; unchanged inherited QKV execution.

Only constructor type admission changes. The old ReducedPublicExecution and
ReductionDriver remain unchanged; all execution/transaction methods are reused.
"""
from collections import Counter,deque
from dataclasses import asdict
from candidates.qwen2_resident_matrix.dense_block_reduce import public_execution as base
from candidates.qwen2_resident_matrix.ffn_public.execute_numeric import PublicExecution
from .pv32_owner import OfficialPV32AttentionOwner
require=base.require


class PV32PublicExecution(base.ReducedPublicExecution):
    def __init__(self,*args,fixture,**kwargs):
        require(fixture.scope=='QWEN2_21_METADATA_ONLY' and fixture.config.command.count==21 and
            len(fixture.commands)==21 and tuple(int(c.opcode) for c in fixture.commands)==base.OPCODES and
            all(c.event_wait==i and c.event_signal==i+1 for i,c in enumerate(fixture.commands)),
            'PV32 requires original public21 profile')
        require(type(kwargs.get('prefix_owner')) is base.OfficialPrefixOwner and
            type(kwargs.get('attention_owner')) is OfficialPV32AttentionOwner and
            type(kwargs.get('matrix_service')) is base.ProfiledMatrixService and
            type(args[1]) is base.DenseReductionOwner,'mixed/detached PV32 services')
        physical=getattr(args[0].memory,'physical_memory',None)
        require(args[0].config==fixture.config and physical is not None and physical.fixture is fixture,
            'PV32 metadata and operands require same physical map')
        self.policy_fixture=fixture;self.policy_jobs={};self.reduction=None;self.reduction_reports=[]
        PublicExecution.__init__(self,*args,**kwargs)


class PV32ReductionDriver(base.ReductionDriver):
    def __init__(self,x,memory,job,*,final_ack_stall=5):
        require(type(x) is PV32PublicExecution and x.reduction is None,'one PV32 public reduction')
        require(base.validate_job(x.policy_fixture,job) in (1,4,7),'only original QKV Dense roles')
        require(x.ports()['ordinary_request'] is job and x.down_job is None,'original public request object')
        self.x,self.memory,self.public_job=x,memory,job
        fields={k:v for k,v in asdict(job).items() if k!='c'}
        require(getattr(job,'c',0)==0,'Dense third root must stay zero')
        self.call=base.DenseReductionRequest(base.Job(**fields),job.tag+1,x.matrix_service.profile.ranges,
            x.matrix_service.profile.pair_reverse)
        self.call.validate()
        self.source=memory.dense_source(self.call.job);self.source_sha=self.source.validate(self.call.job)
        self.c=base.DenseReductionCoordinator();self.owner=x.owner;self.service=x.matrix_service
        self.loan=base.VectorLoanModel(lane_latency=2)
        self.sum=base.TileSumController(self.owner.tiles,bank_tick=lambda **p:base.owner_tile_edge(self.owner,**p))
        self.read=None;self.results=deque();self.adapter=None;self.matrix_abort_sent=False
        self.matrix_fault=None;self.matrix_fmas_before=int(self.service.lib.matrix_dense_fmas())
        self.write=None;self.write_index=0;self.ack=None
        self.counts=Counter();self.partials=[];self.drains=[];self.terminal=None
        self.remaining=final_ack_stall;self.final_ack_stall=final_ack_stall
        self.started=False;self.bank_ids=(id(self.owner),id(self.owner.a_banks),id(self.owner.b_banks))
        self.fences_before=(self.owner.a_fences,self.owner.k_a_fences)
        self.matrix_before=dict(self.service.report()['counters'])
        x.reduction=self
