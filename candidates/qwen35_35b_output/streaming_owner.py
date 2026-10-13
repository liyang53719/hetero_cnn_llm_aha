"""Bounded K1024 resident slabs from a complete strided K4096 source.

The request retains the full original source Job. Only the engine's resident
geometry is derived as K1024, after the original window admission handshake.
All clear/RMW/fence, Matrix handshakes, result adaptation, sum SRAM and final
BF16 write/ACK machinery remains inherited. No host gather or tensor is added.
"""
from dataclasses import dataclass, replace

from ..qwen35_35b_prefill import projection_owner as large
from ..qwen35_gdn_prefill import projection_owner as base
from .chained_tiles import ChainedTileBankModel

Job, PrefixWorkspace, down = large.Job, large.PrefixWorkspace, large.down
K, RESIDENT_K, MAX_N = 4096, 1024, 2048
RANGES = ((0,1024), (1024,2048), (2048,3072), (3072,4096))


def require(condition, detail):
    if not condition:
        raise ValueError('streaming O owner: ' + detail)


def validate_full_job(job):
    """Complete source contract; N<2048 is only bounded transport testing."""
    require(type(job) is Job, 'exact complete source Job required')
    job.validate()
    require(all(type(v) is int for v in
                (job.m,job.n,job.k,job.tag,job.a,job.b,job.dst,job.write_bytes)) and
            job.m in (16,128) and job.k == K and 0 < job.n <= MAX_N and job.n % 32 == 0 and
            job.activation_bf16 is True and job.weight_bf16 is True and job.output_bf16 is True and
            job.materialize_dense_output is False and job.write_bytes == job.m * job.n * 2,
            'full BF16 K4096 source and complete BF16 output geometry')
    spans = base.projection_spans(job)
    require(not any(a < d and c < b for i,(a,b) in enumerate(spans) for c,d in spans[i+1:]),
            'complete A/W/D source spans alias')


def _validate_window_key(q):
    validate_full_job(q.job)
    require(all(type(v) is int for v in (q.identity,q.ng,q.cols)) and
            0 < q.identity < 1 << 32 and 0 <= q.ng < 1 << 16 and q.ng % 32 == 0 and
            q.cols in (32,64,96,128,160) and q.ng + q.cols <= q.job.n,
            'complete source window identity/extent')


@dataclass(frozen=True)
class NoPrefixWorkspace(PrefixWorkspace):
    """Address reservation only; streaming windows never save or seed a prefix.

    Existing K<=2048 calls retain their original workspace validation. The O
    path validates this unused reservation against full sources without making
    a seeded-spill capacity claim. It does not allocate a TypedMemory Region.
    """
    split_k: int = 2048

    def validate(self, job):
        require(all(type(v) is int for v in (self.base,self.extent,self.generation,self.split_k)),
                'typed workspace metadata')
        if job.k <= 2048:
            return super().validate(job)
        validate_full_job(job)
        require(self.base >= 0 and self.base % 64 == 0 and self.extent > 0 and
                self.extent % 64 == 0 and 0 < self.generation < 1 << 32 and
                self.split_k == 2048, 'explicit no-prefix reservation; old split bound unchanged')
        end = self.base + self.extent
        require(end <= 1 << 56 and not any(self.base < hi and lo < end
                for lo,hi in base.projection_spans(job)), 'no-prefix reservation aliases complete source')


@dataclass(frozen=True, kw_only=True)
class StreamingWindowRequest(large.LargeKWindowRequest):
    block_index: int

    @classmethod
    def from_full(cls, job, identity, ng, cols, block_index):
        require(type(block_index) is int and 0 <= block_index < 4, 'four explicit source blocks')
        begin,end = RANGES[block_index]
        q = cls(job,identity,ng,cols,0 if block_index == 0 else 1,False,
                k_begin=begin,k_end=end,block_id=block_index+1,pair_reverse=True,
                block_index=block_index)
        q.validate()
        return q

    @property
    def full_job(self):
        return self.job

    def resident_job(self):
        self.validate()
        result = replace(self.job,k=RESIDENT_K)
        large.validate_projection(result)
        return result

    def validate(self):
        _validate_window_key(self)
        require(type(self.block_index) is int and 0 <= self.block_index < 4 and
                all(type(v) is int for v in (self.slot,self.k_begin,self.k_end,self.block_id)) and
                self.slot == (0 if self.block_index == 0 else 1) and
                (self.k_begin,self.k_end) == RANGES[self.block_index] and
                self.block_id == self.block_index+1 and self.pair_reverse is True and self.reuse_a is False,
                'exact independent pair-high K1024 block/slot with mandatory actual reload')


@dataclass(frozen=True)
class StreamingDrainRequest(large.LargeKDrainRequest):
    def validate(self):
        _validate_window_key(self)


@dataclass(frozen=True)
class StreamingALease:
    """Only the physically loaded slab, never a fictitious full-K A lease."""
    base: int
    rows: int
    source_k: int
    row_stride: int
    k_begin: int
    k_end: int
    resident_k: int
    identity: int
    job_tag: int
    block_id: int

    @classmethod
    def for_request(cls, q):
        q.validate()
        return cls(q.job.a,q.job.m,K,K*2,q.k_begin,q.k_end,RESIDENT_K,q.identity,q.job.tag,q.block_id)


class StreamingProjectionOwner(large.LargeKProjectionOwner):
    def __init__(self, workspace=None):
        super().__init__(workspace)
        # Constructor-only control-wrapper selection; no Banks allocation or
        # replacement. Legacy two-partial traffic uses the same physical SRAM.
        self.tiles = ChainedTileBankModel(self.a_banks)
        self.resident_descriptor = None

    def _reset(self):
        super()._reset()
        self.resident_descriptor = None

    def _streaming_request(self):
        q = self.window_request
        return q if type(q) is StreamingWindowRequest else None

    def _read_command(self):
        q = self._streaming_request()
        if q is None or self.state != 'a_load':
            # B load_k is global, and resident_job retains original full N/b.
            return super()._read_command()
        if self.error or self.read_active or self.a_hold or self.a_rmw_pending or self.a_beat == RESIDENT_K//32:
            return None
        address = q.job.a + (self.a_row*K + q.k_begin + self.a_beat*32)*2
        return base.kw.ReadCommand('a',address,1,(q.job.tag<<32)|self.read_sequence)

    def _issue_read(self):
        q = self._streaming_request()
        if q is None:
            return super()._issue_read()
        # This is the inherited K-window operand issue, with only A's logical
        # source coordinate translated to its explicitly bound local slab.
        ordinal,ctx = self.issue_k-q.k_begin,self.issue_context
        logical_k = q.k_begin+(ordinal^1)
        local_k = logical_k-q.k_begin
        require(0 <= local_k < RESIDENT_K, 'Matrix A issue outside loaded resident slab')
        half = (logical_k//128)&1
        awords = tuple(self.a_banks.read(*down.a_address(local_k,16*group)[:2]) for group in range(8))
        bwords = tuple(self.b_banks.read(*down.b_address(half,logical_k,ctx,nh)) for nh in range(2))
        self.pending = (ordinal,logical_k,ctx,awords,bwords)
        self.issue_context += 1
        if self.issue_context == self.contexts:
            self.issue_context = 0
            self.issue_k += 1
            if self.issue_k%128 == 0 or self.issue_k == q.k_end:
                self.ready[half] = False

    def tick(self, **kwargs):
        ordinary = kwargs.get('job')
        if ordinary is not None and type(self.workspace) is NoPrefixWorkspace:
            require(ordinary.k <= 2048, 'no-prefix workspace cannot authorize ordinary seeded large-K work')
        offered = kwargs.get('window')
        active = self._streaming_request()
        offered_drain = kwargs.get('drain')
        streaming_drain = (type(offered_drain) is StreamingDrainRequest or
                           type(self.drain_request) is StreamingDrainRequest)
        if type(offered) is not StreamingWindowRequest and active is None and not streaming_drain:
            if isinstance(offered,StreamingWindowRequest):
                raise ValueError('streaming O owner: exact bound request type required')
            # Ordinary/legacy windows and new BF16 drains preserve the existing
            # LargeK dispatch, guards, ACK retirement and default behavior.
            return super().tick(**kwargs)
        require(offered_drain is None or type(offered_drain) is StreamingDrainRequest,
                'cannot mix another drain authority into accepted streaming work')
        require(offered is None or type(offered) is StreamingWindowRequest,
                'cannot mix another window authority into accepted streaming work')
        if active is not None and not self.error:
            require(self.resident_descriptor == active.resident_job() and
                    self.job == self.resident_descriptor,
                    'accepted full-source/resident geometry binding changed')
        reset_rejected = bool(kwargs.get('coordinated_reset') and not self.tiles.idle)
        if reset_rejected:
            kwargs = dict(kwargs,coordinated_reset=False,abort=True)
        # Skip only LargeK's exact-old-window/drain-type guards. Its complete inherited
        # GDN/K-window tick still owns every accepted memory/Matrix obligation.
        event = base.GdnProjectionOwner.tick(self,**kwargs)
        current = self._streaming_request()
        if event.get('window_fire') and current is not None and not self.error:
            self.resident_descriptor = current.resident_job()
            self.job = self.resident_descriptor
        if any(word < large.A_WORDS for word in event.get('a_writes',{}).values()):
            self.lease = None
        if event.get('a_fence') and current is not None and not self.error and not kwargs.get('invalidate_lease'):
            # The inherited fence checked real M*resident_K ingress/RMW counts.
            # Replace its full-request lease before exposing this completed edge.
            self.lease = StreamingALease.for_request(current)
        if event.get('window_result_fire') or event.get('coordinated_reset'):
            self.resident_descriptor = None
        if reset_rejected:
            event.update(coordinated_reset=False,reset_rejected=True)
        return event
