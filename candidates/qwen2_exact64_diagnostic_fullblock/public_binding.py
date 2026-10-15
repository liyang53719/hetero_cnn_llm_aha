"""Opt-in diagnostic public21 binding; no changes to published executions.

Q/K are selected by the runner's separate Exact64 projection owner. Only the
original V pc7 enters this inherited two-partial PV32 reduction driver. The
fused pc12 retains real Host and owner handshakes while sharing existing A.
"""
from collections import Counter, deque
from dataclasses import asdict

from candidates.qwen2_attention_resident_candidate.owner import ResidentPV32AttentionOwner
from candidates.qwen2_attention_shared_a_integration.banks import LoanDenseOwner, BankByteView
from candidates.qwen2_live_attention_model_m128.public_binding import PV32PublicExecution, PV32ReductionDriver
from candidates.qwen2_resident_matrix.dense_block_reduce import public_execution as base
from candidates.qwen2_resident_matrix.ffn_public.execute_numeric import PublicExecution
from candidates.qwen2_resident_matrix.ffn_public import model as public
from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory
from .publication import (
    DiagnosticPublicKvPublication, DiagnosticSharedALoanRouter,
    expected_kv_identity, validate_public21_fixture,
)

require = base.require


class DiagnosticPublicExecution(PV32PublicExecution):
    """Real PublicExecution initialization with explicit diagnostic type gates."""
    def __init__(self, *args, fixture, **kwargs):
        require(len(args) >= 2, 'diagnostic frontend and owner required')
        require(type(args[0]) is public.PublicFrontend and
                (kwargs.get('host') is None or type(kwargs['host']) is public.group.HostControl),
                'diagnostic launch requires original public frontend and Host')
        physical = getattr(args[0].memory, 'physical_memory', None)
        require(type(physical) is PhysicalMemory and args[0].config == fixture.config and
                physical.fixture is fixture, 'diagnostic metadata/operands need the same physical map')
        validate_public21_fixture(fixture, physical)
        require(type(kwargs.get('prefix_owner')) is base.OfficialPrefixOwner and
                type(kwargs.get('attention_owner')) is ResidentPV32AttentionOwner and
                type(kwargs.get('matrix_service')) is base.ProfiledMatrixService and
                type(args[1]) is LoanDenseOwner,
                'mixed/detached diagnostic shared-A services')
        owner, attention = args[1], kwargs['attention_owner']
        require(type(attention.scratch.storage) is BankByteView and
                attention.scratch.storage.banks is owner.a_banks and owner.tiles.banks is owner.a_banks and
                attention.kv_identity == expected_kv_identity(physical),
                'resident cache must view existing A with the expected original KV identity')
        self.policy_fixture, self.policy_jobs = fixture, {}
        self.reduction, self.reduction_reports = None, []
        self.exact64_projection = None
        self.attention_publication = self.attention_router = None
        # Retain the actual raw launch, Host, requests, terminal and completion
        # bookkeeping. Never construct a host checkpoint or replay receipts.
        PublicExecution.__init__(self, *args, **kwargs)

    def reset_required(self):
        original = super().reset_required()
        projection = getattr(self, 'exact64_projection', None)
        route = getattr(self, 'attention_router', None)
        return bool(original or (projection is not None and projection.backend.poison) or
                    (route is not None and route.fault is not None))

    def arm_attention(self, physical, job):
        """Prepare after actual pc9 publication and original pc12 offer.

        The first attention_edge(job=job) acquires the checked A loan. Merely
        predicting expected_kv_identity() or constructing this execution grants
        no read permission and cannot bypass the producer publication gate.
        """
        require(self.attention_router is None and self.attention_publication is None and
                self.reduction is None and self.exact64_projection is None and self.down_job is None,
                'one diagnostic attention route after all Dense work retires')
        publication = DiagnosticPublicKvPublication(self, physical, job)
        router = DiagnosticSharedALoanRouter(self.owner, self.prefix_owner, self.attention_owner, publication)
        router.quiescent()
        self.attention_publication, self.attention_router = publication, router
        return router

    def attention_edge(self, **inputs):
        backend, route = self.attention_owner, self.attention_router
        require(route is not None and route.attention is backend and backend.matrix is self.matrix_service,
                'call arm_attention on the actual public pc12 before Attention edges')
        require(self.owner.state == 'idle' and self.owner.lease is None and self.owner.tiles.idle and
                self.owner.ports()['response'] is None and self.prefix_owner.state == 'idle',
                'Attention conflicts with retained Dense/prefix obligations')
        hp = self.ports()
        before_reset = self.reset_required()
        if 'job' in inputs:
            decoded = hp['ordinary_request']
            require(decoded is inputs['job'] is route.publication.job and decoded.kind == 'Attention' and
                    hp['group_request'] is None, 'Attention needs the original offered fused public job')
        require('response_ready' not in inputs, 'Attention result readiness belongs to Host')
        inputs['response_ready'] = hp['owner_result_ready']
        # The router clocks Dense/Tile exactly once before cache operations.
        # Do not append the legacy backend.tick(); owner.tick() pair here.
        edge = route.tick(**inputs)
        accepted = bool(edge.get('job_fire'))
        terminal = edge['response'] if edge.get('response_fire') else None
        self.attention_jobs += accepted
        self.attention_results += terminal is not None
        self._host_edge(request_ready=accepted, owner_result=terminal,
                        reset_required=before_reset or self.reset_required() or route.fault is not None)
        require(bool(self.last_host_edge['request_fire']) == accepted and
                bool(self.last_host_edge['owner_result_fire']) == (terminal is not None),
                'public/shared-A Attention request or terminal handshake disagreement')
        return edge

    def report(self):
        result = super().report()
        result.update(scope='DIAGNOSTIC_SOFTWARE_OWNER', performance='NO_GO', hardware='NOT_IMPLEMENTED',
                      attention_shared_a=None if self.attention_router is None else self.attention_router.report(),
                      diagnostic_projection_roles=(1, 4), inherited_reduction_roles=(7,))
        return result


class DiagnosticVReductionDriver(PV32ReductionDriver):
    """Constructor admission only; inherited original V run/tick unchanged."""
    def __init__(self, x, memory, job, *, final_ack_stall=5):
        require(type(x) is DiagnosticPublicExecution and x.reduction is None,
                'one diagnostic public V reduction')
        require(base.validate_job(x.policy_fixture, job) == 7,
                'diagnostic inherited reduction permits only original pc7 V')
        require(type(memory) is PhysicalMemory and memory is x.frontend.memory.physical_memory and
                memory.fixture is x.policy_fixture, 'V reduction must use same physical memory')
        require(x.ports()['ordinary_request'] is job and x.down_job is None,
                'original public V request object')
        self.x, self.memory, self.public_job = x, memory, job
        fields = {k: v for k, v in asdict(job).items() if k != 'c'}
        require(getattr(job, 'c', 0) == 0, 'Dense third root must stay zero')
        self.call = base.DenseReductionRequest(base.Job(**fields), job.tag + 1,
            x.matrix_service.profile.ranges, x.matrix_service.profile.pair_reverse)
        self.call.validate()
        self.source = memory.dense_source(self.call.job)
        self.source_sha = self.source.validate(self.call.job)
        self.c = base.DenseReductionCoordinator()
        self.owner, self.service = x.owner, x.matrix_service
        self.loan = base.VectorLoanModel(lane_latency=2)
        # GuardedTiles is only a facade over the original TileBankModel. The
        # controller retains that actual object; all ticks use the guarded
        # owner callback, so no second bank allocation or bypass is introduced.
        tiles = self.owner.tiles._delegate
        require(tiles.banks is self.owner.a_banks and self.owner.tiles.banks is tiles.banks,
                'V sum must retain original guarded TileBankModel allocation')
        self.sum = base.TileSumController(tiles, bank_tick=lambda **p: base.owner_tile_edge(self.owner, **p))
        self.read, self.results, self.adapter, self.matrix_abort_sent = None, deque(), None, False
        self.matrix_fault = None
        self.matrix_fmas_before = int(self.service.lib.matrix_dense_fmas())
        self.write, self.write_index, self.ack = None, 0, None
        self.counts, self.partials, self.drains, self.terminal = Counter(), [], [], None
        self.remaining, self.final_ack_stall = final_ack_stall, final_ack_stall
        self.started = False
        self.bank_ids = (id(self.owner), id(self.owner.a_banks), id(self.owner.b_banks))
        self.fences_before = (self.owner.a_fences, self.owner.k_a_fences)
        self.matrix_before = dict(self.service.report()['counters'])
        x.reduction = self
