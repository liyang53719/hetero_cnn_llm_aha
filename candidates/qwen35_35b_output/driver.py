"""Explicit four-K1024 driver over unchanged Matrix/Vector transport edges.

The constructor specializes the existing typed driver admission for a bounded
four-part profile and no-seed window workspace. Arithmetic and all tick-level
DMA/Matrix/Vector retirement/publication remain the inherited implementation.
"""
from collections import Counter, deque
from dataclasses import dataclass
import hashlib
from ..qwen35_gdn_prefill import projection_driver as base
from ..qwen35_35b_prefill import projection_driver as large
from ..qwen35_35b_prefill.projection_owner import LargeKReductionRequest, LargeKReductionCoordinator, LargeKWindowRequest
from ..qwen2_resident_matrix.dense_block_reduce.profile import ReductionProfile
from .streaming_owner import StreamingProjectionOwner, StreamingWindowRequest, NoPrefixWorkspace
from .chained_sum import ChainedSumController, LegacyInplaceSumController
from .coordinator import FourReductionRequest, FourReductionCoordinator, RANGES
require,t,Job,down,SharedVector16Loan=base.require,base.t,base.Job,base.down,base.SharedVector16Loan

@dataclass(frozen=True)
class FourProfile:
    name: str
    source_sha256: str
    ranges: tuple = RANGES
    pair_reverse: bool = True

    def validate(self,k):
        require(k==4096 and self.ranges==RANGES and self.pair_reverse is True and
            type(self.name) is str and bool(self.name) and type(self.source_sha256) is str and
            len(self.source_sha256)==64 and all(c in '0123456789abcdef' for c in self.source_sha256),
            'exact four-K1024 independent pair-high left-fold profile')

class TypedStreamingProjectionDriver(base.TypedProjectionDriver):
    OWNER_TYPE=StreamingProjectionOwner
    WINDOW_REQUEST_TYPE=StreamingWindowRequest

    def _validate_family(self,job,role,profile,family):
        require(family=='o_four_k1024' and role=='synthetic' and type(profile) is FourProfile,
            'explicit O-only diagnostic profile')
        require(job.m in (16,128) and job.k==4096 and job.n>0 and job.n<=2048 and job.n%32==0,
            'bounded original O geometry')

    def _make_call(self,typed_job,profile):
        # Distinct identities bind each partial and every destructive sum.
        first=typed_job.tag or 1
        return FourReductionRequest(typed_job,first,RANGES,True,
            tuple(first+i for i in range(1,5)),tuple(first+i for i in range(5,8)))

    def _make_sum(self,owner):
        return ChainedSumController(owner.tiles,bank_tick=lambda **p: base.owner_tile_edge(owner,**p))

    def _make_coordinator(self):return FourReductionCoordinator()

    def __init__(self, owner, matrix_service, memory, job, *, vector, role,
                 profile, family='o_four_k1024'):
        require(type(owner) is self.OWNER_TYPE, 'exact selected projection owner required')
        require(type(matrix_service) is t.MatrixService and type(memory) is t.TypedMemory,
                'same base MatrixService and typed physical byte map required')
        require(type(job) in (t.down.Job, down.Job, Job), 'supported complete original Dense Job authority')
        require(type(profile) in (ReductionProfile, FourProfile), 'explicit immutable reduction profile required')
        profile.validate(job.k)
        self._validate_family(job, role, profile, family)
        typed_job = Job(**vars(job))
        self.call = self._make_call(typed_job, profile)
        self.call.validate()
        require(type(owner.workspace) is NoPrefixWorkspace, 'explicit no-seed streaming workspace identity required')
        owner.workspace.validate(typed_job)
        require(owner.state == 'idle' and not owner.error and not owner.drain_poison and
                owner.tiles.idle and not owner.tiles.leased and not owner.tiles.poison and
                owner.lease is None, 'drained unpoisoned projection owner required')
        require(memory.pending is None and matrix_service.owner is None and not matrix_service.reset_required,
                'physical Matrix/DMA must be drained before projection admission')
        self.a = memory.exact(job.a, job.m * job.k * 2, readable=True)
        self.b = memory.exact(job.b, job.k * job.n * 2, readable=True)
        self.output = memory.exact(job.dst, job.write_bytes, readable=False)
        self.owner, self.matrix, self.memory, self.job = owner, matrix_service, memory, job
        self.family, self.role, self.profile = family, role, profile
        self.binding_identity = self._binding_identity()
        self.loan = SharedVector16Loan(vector)
        self.sum = self._make_sum(owner)
        self.coordinator = self._make_coordinator()
        self.pending_read = self.pending_ack = self.bridge = None
        self.results = deque()
        self.response = None
        self._terminal_report = None
        self.aborted = self.abort_sent = False
        self.numeric_fault = None
        self.counts = Counter()
        self.partials, self.drains, self.groups = [], [], []
        self.input_hashes = tuple(hashlib.sha256(r.raw()).hexdigest() for r in (self.a, self.b))
        self.bank_identity = self._identity()
        self.epoch = self.matrix.epoch
        self.fma_before = int(self.matrix.lib.matrix_dense_fmas())
        self.vector_calls_before = vector.calls['add']
        self.vector_lanes_before = vector.lane_ops['add']
        self.fences_before = (owner.a_fences, owner.k_a_fences)
        e = self.coordinator.tick(request=self.call, services=self.services())
        require(e['request_fire'] and not self.coordinator.poison, 'typed projection admission failed')


    def _report(self):
        r=super()._report()
        r.update(scope='FOUR_K1024_STREAMING_A_LEFT_FOLD_SOFTWARE_OWNER',
            native_acceptance=False,seeded_prefix_used=False,private_prefix_bytes=0,
            arithmetic_recipe='four independent pair-high K1024; FP32 left-fold; final BF16 RNE',
            resident_a_bytes=262144,extra_tensor_storage_bytes=0)
        return r

class TypedStreamingUpstreamDriver(TypedStreamingProjectionDriver):
    WINDOW_REQUEST_TYPE=LargeKWindowRequest
    def _validate_family(self,job,role,profile,family):
        require(family=='upstream_two_partials' and role=='synthetic' and type(profile) is ReductionProfile,
            'existing upstream two-partial profile only')
        require(0<job.k<=2048,'upstream resident A extent')
    def _make_call(self,typed_job,profile):
        return LargeKReductionRequest(typed_job,typed_job.tag or 1,profile.ranges,
            profile.pair_reverse,sum_identity=self.sum_identity)
    def _make_sum(self,owner):
        return LegacyInplaceSumController(owner.tiles,bank_tick=lambda **p: base.owner_tile_edge(owner,**p))
    def _make_coordinator(self):return LargeKReductionCoordinator()
    def __init__(self,owner,matrix_service,memory,job,*,vector,profile,sum_identity,role='synthetic'):
        require(type(sum_identity) is int and 0<sum_identity<1<<32 and sum_identity!=(job.tag or 1),
            'distinct upstream sum identity')
        self.sum_identity=sum_identity
        super().__init__(owner,matrix_service,memory,job,vector=vector,role=role,
            profile=profile,family='upstream_two_partials')
    def _binding_identity(self):return super()._binding_identity()+(self.sum_identity,)
    def _report(self):
        r=base.TypedProjectionDriver._report(self)
        r.update(scope='UNCHANGED_TWO_PARTIAL_ARITHMETIC_ON_STREAMING_OWNER',
            sum_identity=self.sum_identity,native_acceptance=False)
        return r
