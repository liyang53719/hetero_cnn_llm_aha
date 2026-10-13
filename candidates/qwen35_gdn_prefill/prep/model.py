"""Memory-fed GDN InputPrep candidate: independent token preparation M1..128.

The pinned Chisel owner supports M1 ONLY. This software extension prepares
tokens without recurrence or state mutation; it is not a replacement for the
subsequent true chunk64 x 2 algorithm. Native numeric acceptance and RTL have
not been run. Software ticks and scalar calls are not hardware cycles.

The default 0.8B strides remain fixed in reduced-head transport tests:
Conv BF16 [M,6144], AB BF16 [M,32] = [A16,B16], and core FP32 [M,6400]
= [Q2048,K2048,V2048,gates256]. Each gate is {g,beta,14 positive zeros}.
Explicit35B layout uses Conv8192/AB64/Core12800 elements and repeats Q/K
by source head floor(value_head/2). Parameter banks refill in16-head groups.
One in-place FP32 head[128] cache is reused for every role, head and token.
"""
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import math
import struct
import subprocess

from ..rms_owner import (ROOT, SCALAR_SOURCE, SCALAR_SHA, ArithmeticFault,
                         MemoryRequest, MemoryResponse, finite, sha, word)
from ..typed_dense import TypedMemory, FULL_MASK
from ...qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from .scalar import PrepScalar, OPCODES
from .layout import PrepLayout, EQUAL_HEADS, GROUPED_35B, grouped_source_identity


OWNER_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnInputPrepOwner.scala'
OWNER_SHA = '86fa350cd87bc140b762db2deb5650c25e3b30bae4fb12cef7fe407e6b4faffe'
HEADS, HEAD_WIDTH, VECTOR_ELEMENTS = 16, 128, 2048
CONV_ELEMENTS, CORE_ELEMENTS = 6144, 6400
CONV_ROW_BYTES, AB_ROW_BYTES, CORE_ROW_BYTES = 12288, 64, 25600
BEAT_BYTES, PARAM_BYTES = 64, 64


def require(ok, why):
    if not ok:
        raise ValueError('typed InputPrep: ' + why)


def source_identity(root=ROOT, *, layout=EQUAL_HEADS):
    root = Path(root)
    source = subprocess.run(['git', 'show', 'HEAD:' + OWNER_SOURCE], cwd=root,
                            check=True, capture_output=True, timeout=10).stdout
    require(sha(source) == OWNER_SHA, 'committed M1 InputPrep source drift')
    require(sha((root / SCALAR_SOURCE).read_bytes()) == SCALAR_SHA, 'shared scalar source drift')
    models = ('candidates/qwen35_gdn_prefill/prep/model.py',
              'candidates/qwen35_gdn_prefill/prep/scalar.py',
              'candidates/qwen35_gdn_prefill/prep/layout.py',
              'candidates/qwen35_gdn_prefill/conv/scalar.py',
              'candidates/qwen35_gdn_prefill/rms_owner.py',
              'candidates/qwen35_gdn_prefill/typed_dense.py')
    return dict(grouped_source=grouped_source_identity(root) if layout == GROUPED_35B else None,
                source_sha256={'HEAD:' + OWNER_SOURCE: OWNER_SHA, SCALAR_SOURCE: SCALAR_SHA},
                implementation_sha256={p: sha((root / p).read_bytes()) for p in models},
                opcodes=dict(OPCODES), source_tokens=1, candidate_tokens='M1..128',
                arithmetic='source_ascending_square_add_sqrt_reciprocal_chunk_q_scale',
                token_independent=True, recurrence_implemented=False,
                required_downstream='true_chunk64_x2_for_M128',
                native_acceptance=False, rtl_executed=False, historical_pass_inherited=False)


@dataclass(frozen=True)
class InputPrepJob:
    tag: int
    conv: int
    ab: int
    a_log: int
    dt_bias: int
    output: int
    tokens: int
    heads: int = HEADS
    layout: PrepLayout = EQUAL_HEADS

    @property
    def conv_bytes(self):
        return self.tokens * self.layout.conv_row_bytes

    @property
    def ab_bytes(self):
        return self.tokens * self.layout.ab_row_bytes

    @property
    def write_bytes(self):
        return self.tokens * self.layout.core_row_bytes

    def validate(self, heads=HEADS, layout=EQUAL_HEADS):
        require(type(self.layout) is PrepLayout and self.layout == layout, 'explicit caller/owner layout identity')
        require(type(heads) is int and 1 <= heads <= layout.value_heads and
                type(self.heads) is int and self.heads == heads and
                type(self.tokens) is int and 1 <= self.tokens <= 128, 'heads/M1..128 domain')
        require(type(self.tag) is int and 0 <= self.tag < 1 << 32, 'job tag domain')
        spans = ((self.conv, self.conv_bytes), (self.ab, self.ab_bytes),
                 (self.a_log, self.layout.a_log_bytes), (self.dt_bias, self.layout.dt_bias_bytes),
                 (self.output, self.write_bytes))
        for base, extent in spans:
            require(type(base) is int and base >= 0 and base % 64 == 0 and base + extent <= 1 << 56,
                    'aligned nonempty 56-bit physical span')
        require(all(a + n <= b or b + m <= a for i, (a, n) in enumerate(spans) for b, m in spans[:i]),
                'five complete typed allocations must be disjoint')


@dataclass(frozen=True)
class InputPrepResult:
    tag: int
    status: str | None
    write_bytes: int
    model_ticks: int
    staging_complete: bool
    history_committed: bool = False
    state_committed: bool = False
    generation_advanced: bool = False


class InputPrepOwner:
    """One physical request in flight and one held terminal, shared scalar only.

    Reduced heads are explicitly synthetic test geometry. Every inactive head
    is zero-written and ACKed at its production offset. Default heads=16 has
    no inactive-head fill and computes every production head.
    """
    def __init__(self, scalar, *, heads=HEADS, layout=EQUAL_HEADS):
        require(isinstance(scalar, PrepScalar), 'explicit caller-owned PrepScalar required')
        require(type(layout) is PrepLayout, 'explicit pinned geometry required')
        require(type(heads) is int and 1 <= heads <= layout.value_heads, 'head count within pinned layout')
        require(layout == EQUAL_HEADS or heads == 32, '35B geometry requires all32 value heads')
        self.scalar, self.heads, self.layout = scalar, heads, layout
        self.state, self.job, self.request, self.result = 'idle', None, None, None
        self.program, self.poison, self.status = None, False, None
        self.ticks, self.start, self.sequence, self.ack_bytes = 0, 0, 0, 0
        self.counts, self.scalar_baseline, self.scalar_counts = Counter(), Counter(), Counter()
        self.exp_baseline, self.exp_counts = Counter(), Counter()
        self.soft_baseline, self.soft_counts = Counter(), Counter()
        self.identity, self.numerical_detail = None, None

    def ports(self):
        return dict(job_ready=self.state == 'idle' and not self.poison and self.scalar.client is None,
                    memory=self.request if self.state == 'issue' else None,
                    memory_response_ready=self.state in ('wait', 'drain'),
                    response=self.result if self.state == 'finish' else None,
                    reset_required=self.poison, state=self.state)

    def reset(self):
        require(self.state in ('idle', 'locked') and self.request is None and self.scalar.client is not self,
                'reset requires drained transport and retired held completion')
        self.__init__(self.scalar, heads=self.heads, layout=self.layout)

    def _op(self, operation, a, b=0):
        return self.scalar.op(self, operation, a, b)

    def _compute(self, j):
        if self.layout == EQUAL_HEADS:
            a_log = struct.unpack('<16I', (yield (j.a_log, None)))
            bias = struct.unpack('<32H', (yield (j.dt_bias, None)))[:16]
        # Only this 128-element cache scales with head width; no token array,
        # all-head tensor, or recurrent/chunk state is retained by this owner.
        cache = [0] * HEAD_WIDTH
        if self.layout == GROUPED_35B:
            ab = [0] * 32
        for token in range(j.tokens):
            if self.layout == EQUAL_HEADS:
                ab = struct.unpack('<32H', (yield (j.ab + token * self.layout.ab_row_bytes, None)))
            for head in range(j.heads):
                if self.layout == GROUPED_35B and head % 16 == 0:
                    # Refill the same four16-value parameter banks, never all32 FP32 heads.
                    group = head // 16
                    a_log = struct.unpack('<16I', (yield (j.a_log + group*64, None)))
                    bias = struct.unpack('<32H', (yield (j.dt_bias, None)))[group*16:group*16+16]
                    ab[:16] = struct.unpack('<32H', (yield (j.ab + token*self.layout.ab_row_bytes, None)))[group*16:group*16+16]
                    ab[16:] = struct.unpack('<32H', (yield (j.ab + token*self.layout.ab_row_bytes + 64, None)))[group*16:group*16+16]
                parameter_head = head % 16
                for role in range(3):
                    element = role * self.layout.vector_elements + head * HEAD_WIDTH
                    source = j.conv + token * self.layout.conv_row_bytes + self.layout.source_element(role, head) * 2
                    destination = j.output + token * self.layout.core_row_bytes + element * 4
                    for beat in range(4):
                        packet = struct.unpack('<32H', (yield (source + beat * 64, None)))
                        if any(not finite(v << 16) for v in packet):
                            raise ArithmeticFault('nonfinite BF16 ConvOut input')
                        for lane, raw in enumerate(packet):
                            cache[beat * 32 + lane] = raw << 16
                    if role != 2:
                        total = 0
                        for x in cache:
                            square = self._op('mul_ieee_rne', x, x)
                            total = self._op('add', total, square)
                        variance = self._op('add', total, word(1e-6))
                        root = self._op('sqrt', variance)
                        inverse = self._op('div', word(1), root)
                        for lane, x in enumerate(cache):
                            normalized = self._op('mul_ieee_rne', x, inverse)
                            cache[lane] = (self._op('mul_ieee_rne', normalized, word(1 / math.sqrt(128)))
                                           if role == 0 else normalized)
                    for beat in range(8):
                        yield (destination + beat * 64, struct.pack('<16I', *cache[beat * 16:beat * 16 + 16]))

                # Preserve source gate ordering and domain checks, after V ACK.
                a, b, log = ab[parameter_head] << 16, ab[16 + parameter_head] << 16, a_log[parameter_head]
                if (not finite(log) or log & 0x7fffffff >= word(80) or not finite(b) or
                        (b >> 31 and b & 0x7fffffff >= word(80))):
                    raise ArithmeticFault('A_log requires abs < 80 and beta input requires b > -80')
                biased = self._op('add', a, bias[parameter_head] << 16)
                positive = self._op('softplus', biased)
                if positive >> 31:
                    raise ArithmeticFault('negative Softplus result')
                exponential = self._op('exp_negative', log)
                if not log >> 31:
                    exponential = self._op('div', word(1), exponential)
                g = self._op('mul_ieee_rne', exponential ^ 0x80000000, positive)
                if (not g >> 31 and g & 0x7fffffff) or g & 0x7fffffff >= word(80):
                    raise ArithmeticFault('source gate decay requires -80 < g <= 0')
                exponential = self._op('exp_negative', b)
                denominator = self._op('add', word(1), exponential)
                inverse = self._op('div', word(1), denominator)
                beta = self._op('mul_ieee_rne', inverse, exponential if b >> 31 else word(1))
                if beta >> 31 or beta > word(1):
                    raise ArithmeticFault('source beta outside [0,1]')
                beta = ((beta + 0x7fff + ((beta >> 16) & 1)) & 0xffffffff) & 0xffff0000
                yield (j.output + token * self.layout.core_row_bytes + 3*self.layout.vector_elements * 4 + head * 64,
                       struct.pack('<16I', g, beta, *([0] * 14)))

            if j.heads != self.layout.value_heads:
                # Test-only reduced geometry: complete the fixed production
                # allocation honestly with actual zero writes and ACKs.
                for role in range(3):
                    for offset in range(j.heads * HEAD_WIDTH * 4, self.layout.vector_elements * 4, 64):
                        yield (j.output + token * self.layout.core_row_bytes + role * self.layout.vector_elements * 4 + offset,
                               bytes(64))
                for head in range(j.heads, self.layout.value_heads):
                    yield (j.output + token * self.layout.core_row_bytes + 3*self.layout.vector_elements * 4 + head * 64, bytes(64))

    def _finish(self, status=None):
        self.status = status
        self.poison |= status is not None
        if self.scalar.client is self:
            self.scalar_counts = self.scalar.calls - self.scalar_baseline
            self.exp_counts = self.scalar.internal_calls - self.exp_baseline
            self.soft_counts = self.scalar.soft_internal_calls - self.soft_baseline
            self.scalar.release(self)
        self.request, self.program = None, None
        self.result = InputPrepResult(self.job.tag, status, self.ack_bytes, self.ticks - self.start,
                                     status is None)
        self.state = 'finish'

    def _advance(self, data=None):
        try:
            address, output = self.program.send(data)
            require(self.sequence < 1 << 32, 'memory sequence exhausted')
            self.request = MemoryRequest(address, (self.job.tag << 32) | self.sequence, output)
            self.sequence += 1
            self.state = 'issue'
        except StopIteration:
            self._finish(None if self.ack_bytes == self.job.write_bytes else 'Protocol')
        except ArithmeticFault as error:
            self.numerical_detail = str(error)
            self._finish('Numerical')

    def tick(self, *, job=None, memory_ready=False, memory_response=None,
             response_ready=False, abort=False, reset=False):
        p = self.ports()
        p.update(job_fire=False, memory_fire=False, memory_response_fire=False, response_fire=False)
        self.ticks += 1
        if reset and self.state in ('idle', 'locked'):
            self.reset()
            p['job_ready'] = False
            return p
        if reset and self.state == 'finish':
            raise ValueError('typed InputPrep: reset cannot erase a held completion')
        fault = abort or reset
        if fault:
            p['job_ready'], p['memory'] = False, None
            self.poison = True
            if self.state in ('wait', 'drain'):
                self.status, self.state = 'Aborted', 'drain'
            elif self.state in ('issue', 'finish'):
                # Held success has not linearized; preserve any earlier fault.
                self._finish(self.status or 'Aborted')
                p['response'] = None
            elif self.state == 'idle':
                self.state = 'locked'
        if not fault and job is not None and p['job_ready']:
            require(type(job) is InputPrepJob, 'typed immutable InputPrepJob required')
            job.validate(self.heads, self.layout)
            identity = source_identity(layout=self.layout)
            require(self.scalar.acquire(self), 'shared scalar acquisition')
            p['job_fire'] = True
            self.job, self.start, self.identity = job, self.ticks, identity
            self.sequence, self.ack_bytes, self.status, self.counts = 0, 0, None, Counter()
            self.numerical_detail = None
            self.scalar_baseline, self.scalar_counts = self.scalar.calls.copy(), Counter()
            self.exp_baseline, self.exp_counts = self.scalar.internal_calls.copy(), Counter()
            self.soft_baseline, self.soft_counts = self.scalar.soft_internal_calls.copy(), Counter()
            self.program = self._compute(job)
            self._advance()
        if not fault and p['memory'] is not None and memory_ready:
            p['memory_fire'] = True
            self.counts['write_requests' if self.request.write else 'read_requests'] += 1
            self.state = 'wait'
        if p['memory_response_ready'] and memory_response is not None:
            p['memory_response_fire'] = True
            q, r = self.request, memory_response
            require(type(r) is MemoryResponse, 'typed response required')
            self.counts['memory_responses'] += 1
            bad = (type(r.tag) is not int or r.tag != q.tag or type(r.nbytes) is not int or
                   r.nbytes != 64 or type(r.error) is not bool)
            status = 'Protocol' if bad else 'Memory' if r.error else None
            # An accepted physical response retires the single obligation even
            # with a bad tag; no unrelated-response filter is invented here.
            if q.write and status is None:
                self.ack_bytes += 64
                self.counts['write_acks'] += 1
            if self.state == 'drain':
                self._finish(self.status)
            elif status is not None:
                self._finish(status)
            elif q.write:
                self._advance()
            elif type(r.data) is not bytes or len(r.data) != 64:
                self._finish('Protocol')
            else:
                self._advance(r.data)
        if p['response'] is not None and response_ready:
            p['response_fire'] = True
            self.counts['owner_results'] += 1
            self.state = 'locked' if self.poison else 'idle'
            self.result = None
        return p

    def report(self):
        active = self.state not in ('finish', 'idle', 'locked')
        return dict(scope='GDN_TOKEN_INDEPENDENT_INPUT_PREP_SOFTWARE_OWNER', identity=self.identity,
                    status=self.status, numerical_detail=self.numerical_detail,
                    accepted=dict(self.counts), acknowledged_write_bytes=self.ack_bytes,
                    scalar_calls=dict(self.scalar.calls - self.scalar_baseline if active else self.scalar_counts),
                    exp_internal_calls=dict(self.scalar.internal_calls - self.exp_baseline if active else self.exp_counts),
                    softplus_internal_calls=dict(self.scalar.soft_internal_calls - self.soft_baseline if active else self.soft_counts),
                    softplus_enabled=self.scalar.enable_softplus,
                    active_heads=self.heads, production_geometry=self.heads == self.layout.value_heads,
                    key_heads=self.layout.key_heads, value_heads=self.layout.value_heads,
                    qk_head_mapping='value_head // (value_heads/key_heads)',
                    grouped_parameter_refill=self.layout == GROUPED_35B,
                    test_only_zero_filled_heads=self.layout.value_heads - self.heads,
                    retained_fp32_head_capacity=HEAD_WIDTH, head_width=HEAD_WIDTH,
                    retained_parameter_elements=64, retained_output_packet_bytes=64,
                    conv_row_bytes=self.layout.conv_row_bytes, ab_row_bytes=self.layout.ab_row_bytes, core_row_bytes=self.layout.core_row_bytes,
                    history_committed=False, state_committed=False, generation_advanced=False,
                    hardware_cycles=None, rtl_executed=False, native_acceptance=False,
                    native_numeric_diagnostics_executed=False, downstream_chunk_executed=False)


class TypedInputPrepDriver:
    """Actual 64B reads/writes/ACKs; one complete FP32 byte span publication.

    TypedMemory's 32 uint16 transport lanes preserve the 64 raw bytes exactly,
    including FP32 output. They do not convert or quantize FP32 into BF16.
    Both ConvOut and AB must be real previously ACKed, published producers.
    A_log and dtBias are read-only 64B parameters (BF16 bias padding ignored).
    """
    def __init__(self, owner, memory, job):
        require(type(owner) is InputPrepOwner and type(memory) is TypedMemory and type(job) is InputPrepJob,
                'InputPrep owner, shared TypedMemory and immutable job required')
        job.validate(owner.heads, owner.layout)
        require(owner.ports()['job_ready'] and memory.pending is None, 'drained resources required')
        self.conv = memory.exact(job.conv, job.conv_bytes, readable=True)
        self.ab = memory.exact(job.ab, job.ab_bytes, readable=True)
        for region in (self.conv, self.ab):
            require(not region.readonly and region.written == region.acknowledged == set(range(0, region.extent, 64)),
                    'ConvOut/AB require previous actual producer data/ACK and publication')
        self.a_log = memory.exact(job.a_log, job.layout.a_log_bytes, readable=True)
        self.dt_bias = memory.exact(job.dt_bias, job.layout.dt_bias_bytes, readable=True)
        require(self.a_log.readonly and self.dt_bias.readonly, 'original A_log/dtBias parameters must be readonly')
        self.output = memory.exact(job.output, job.write_bytes, readable=False)
        self.owner, self.memory, self.job = owner, memory, job
        self.sources = (self.conv, self.ab, self.a_log, self.dt_bias)
        self.scalar_resource = owner.scalar
        self.resource_identity = (id(owner), id(memory), id(owner.scalar))
        self.source_hashes = tuple(sha(r.raw()) for r in self.sources)
        self.pending, self.response, self.aborted = None, None, False
        self.counts = Counter()
        require(owner.tick(job=job)['job_fire'], 'InputPrep admission rejected')

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             abort=False, reset=False, read_error=False, ack_error=False):
        require(self.response is None, 'InputPrep invocation already retired')
        require(self.resource_identity == (id(self.owner), id(self.memory), id(self.owner.scalar)) and
                self.owner.scalar is self.scalar_resource, 'owner/memory/shared scalar resource replaced')
        p = self.owner.ports()
        pending = self.pending if memory_response_ready else None
        if pending is not None:
            pending = MemoryResponse(pending.tag, pending.data,
                                     bool(ack_error if self.owner.request.write else read_error), pending.nbytes)
        abort_edge = abort and not self.aborted
        self.aborted |= abort_edge or reset
        e = self.owner.tick(memory_ready=memory_ready, memory_response=pending,
                            response_ready=response_ready, abort=abort_edge, reset=reset)
        self.counts['ticks'] += 1
        if e['memory_response_fire']:
            require(self.pending is not None, 'response without accepted request')
            if p['state'] in ('wait', 'drain') and self.memory.pending is not None:
                self.memory.acknowledge(WriteAck(pending.tag, pending.error, pending.nbytes))
            self.pending = None
        if e['memory_fire']:
            require(self.pending is None, 'multiple outstanding InputPrep requests')
            q = e['memory']
            region = self.memory._resolve(q.address)
            if q.write:
                require(region is self.output and len(q.data) == 64, 'write escaped the complete FP32 core span')
                self.memory.begin_write(WriteCommand(q.address, 1, q.tag))
                self.memory.write_data(struct.unpack('<32H', q.data), True, mask=FULL_MASK)
                self.pending = MemoryResponse(q.tag)
                self.counts['write_bytes'] += 64
            else:
                require(any(region is r for r in self.sources), 'read escaped immutable sources')
                self.pending = MemoryResponse(q.tag, self.memory.read64(q.address))
                self.counts['read_bytes'] += 64
        if e['response_fire']:
            require(self.pending is None and self.memory.pending is None, 'terminal before transport drained')
            require(self.source_hashes == tuple(sha(r.raw()) for r in self.sources), 'actual producer/parameters changed')
            self.response = e['response']
            if self.response.status is None:
                require(self.owner.identity == source_identity(layout=self.owner.layout), 'InputPrep source changed during execution')
                require(self.response.staging_complete and self.response.write_bytes == self.job.write_bytes and
                        not any((self.response.history_committed, self.response.state_committed,
                                 self.response.generation_advanced)), 'complete stateless staging receipt required')
                self.memory.publish(self.job.output, (self.response.tag, None, self.job.write_bytes))
        return e

    def report(self):
        return dict(owner=self.owner.report(), complete=self.response is not None,
                    status=None if self.response is None else self.response.status,
                    staging_complete=self.response is not None and self.response.staging_complete,
                    counts=dict(self.counts), output_published=self.output.published,
                    history_committed=False, state_committed=False, generation_advanced=False,
                    input_sha256=list(self.source_hashes), output_sha256=sha(self.output.raw()))
