"""Memory-fed GDN gated RMSNorm software owner, BF16 [M,H,128], H16 default or explicit H32, M1..128.

The pinned Chisel owner already defaults to maxTokens=128. This is a candidate
software owner, not a production Host command or RTL/native numerical pass.
Arithmetic follows its ascending FP32 recipe: square, sum, mean, eps=1e-6,
sqrt, reciprocal, normalize, BF16 RNE, original FP32 weight, FP32 SiLU(z),
then BF16 RNE. There is no Attention 1+weight and no BF16 SiLU intermediate.

One caller-owned ConvScalar (including its PrepScalar subclass) is reused.
One 128-element head cache, 128 shared FP32 weights, and 64B packets suffice;
gates are streamed per beat instead of retaining another complete head.
Software scalar calls and ticks are not hardware cycles. No recurrent state,
history root or generation is changed here.
"""
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import struct
import subprocess

from ..rms_owner import (ROOT, SCALAR_SOURCE, SCALAR_SHA, ArithmeticFault,
                         MemoryRequest, MemoryResponse, finite, sha, word)
from ..conv.scalar import ConvScalar, OPCODES
from ..typed_dense import TypedMemory, FULL_MASK
from ..prep.layout import PrepLayout, EQUAL_HEADS, GROUPED_35B, grouped_source_identity
from ...qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck


OWNER_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnGatedNormOwner.scala'
OWNER_SHA = '00b47be5e72aa580ce9049c2036a23268da859ae7f1728bfea1d348f70a4f2db'
OFFICIAL_SOURCE = 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py'
OFFICIAL_SHA = 'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18'
REAL_SPEC_SOURCE = 'chisel/continuous_prefill/src/test/scala/heteronpu/continuous/GdnGatedNormOwnerSpec.scala'
REAL_SPEC_SHA = 'eb8b3444bc6eca2207549adcb53b5c837e91a0a5b87fb2faf445321e286321a3'
HEADS, HEAD_WIDTH, HEAD_BYTES, ROW_BYTES, WEIGHT_BYTES = 16, 128, 256, 4096, 512
BEAT_BYTES = 64


def require(ok, why):
    if not ok:
        raise ValueError('typed GatedNorm: ' + why)


def source_identity(root=ROOT,layout=EQUAL_HEADS):
    require(type(layout) is PrepLayout and layout in (EQUAL_HEADS,GROUPED_35B), "explicit norm layout")
    root = Path(root)
    source = subprocess.run(['git', 'show', 'HEAD:' + OWNER_SOURCE], cwd=root,
                            check=True, capture_output=True, timeout=10).stdout
    require(sha(source) == OWNER_SHA, 'committed gated norm source drift')
    sources = {SCALAR_SOURCE: SCALAR_SHA, OFFICIAL_SOURCE: OFFICIAL_SHA,
               REAL_SPEC_SOURCE: REAL_SPEC_SHA}
    for name, digest in sources.items():
        require(sha((root / name).read_bytes()) == digest, 'source drift: ' + name)
    models = ('candidates/qwen35_gdn_prefill/gated_norm/model.py',
              'candidates/qwen35_gdn_prefill/conv/scalar.py',
              'candidates/qwen35_gdn_prefill/prep/scalar.py',
              'candidates/qwen35_gdn_prefill/rms_owner.py',
              'candidates/qwen35_gdn_prefill/typed_dense.py',
              'candidates/qwen35_gdn_prefill/prep/layout.py')
    return dict(layout=dict(value_heads=layout.value_heads,width=layout.width,row_bytes=layout.vector_elements*2),
                grouped_source=grouped_source_identity(root) if layout==GROUPED_35B else None,
                grouped_layout_chisel_bound=False,
                source_sha256={'HEAD:' + OWNER_SOURCE: OWNER_SHA, **sources},
                implementation_sha256={p: sha((root / p).read_bytes()) for p in models},
                opcodes=dict(OPCODES), source_default_max_tokens=128,
                candidate_tokens='M1..128', production_host_command=False,
                arithmetic='ascending_fp32_mean_sqrt_reciprocal_bf16norm_fp32weight_fp32silu_bf16',
                gate_storage='streamed_64B_packets', token_independent=True,
                native_acceptance=False, native_numeric_diagnostics_executed=False,
                rtl_executed=False, historical_pass_inherited=False)


@dataclass(frozen=True)
class GatedNormJob:
    tag: int
    core: int
    gate: int
    weight: int
    output: int
    tokens: int
    heads: int = HEADS
    layout: PrepLayout = EQUAL_HEADS

    @property
    def write_bytes(self):
        return self.tokens * self.layout.vector_elements * 2

    def validate(self, heads=HEADS,layout=EQUAL_HEADS):
        require(type(self.layout) is PrepLayout and self.layout==layout and layout in (EQUAL_HEADS,GROUPED_35B), "explicit job/owner layout identity")
        require(layout==EQUAL_HEADS or heads==32, "35B requires all32 heads")
        require(type(heads) is int and 1 <= heads <= layout.value_heads and
                type(self.heads) is int and self.heads == heads and
                type(self.tokens) is int and 1 <= self.tokens <= 128, 'heads/M1..128 domain')
        require(type(self.tag) is int and 0 <= self.tag < 1 << 32, 'job tag domain')
        spans = ((self.core, self.write_bytes), (self.gate, self.write_bytes),
                 (self.weight, WEIGHT_BYTES), (self.output, self.write_bytes))
        for base, extent in spans:
            require(type(base) is int and base >= 0 and base % 64 == 0 and base + extent <= 1 << 56,
                    'aligned nonempty 56-bit physical span')
        require(all(a + n <= b or b + m <= a for i, (a, n) in enumerate(spans)
                    for b, m in spans[:i]), 'four complete typed allocations must be disjoint')


@dataclass(frozen=True)
class GatedNormResult:
    tag: int
    status: str | None
    write_bytes: int
    model_ticks: int
    staging_complete: bool
    state_committed: bool = False
    history_committed: bool = False
    generation_advanced: bool = False


class GatedNormOwner:
    """Single request in flight, held terminal, and exclusive shared scalar.

    heads<16 is synthetic test geometry only. Production strides stay fixed;
    inactive heads get actual zero writes and ACKs, never invented coverage.
    A successful held terminal linearizes only when its consumer accepts it.
    Abort/reset suppress same-tick acceptance and preserve an earlier failure.
    """
    def __init__(self, scalar, *, heads=HEADS,layout=EQUAL_HEADS):
        require(isinstance(scalar, ConvScalar), 'explicit caller-owned ConvScalar or PrepScalar required')
        require(type(layout) is PrepLayout and layout in (EQUAL_HEADS,GROUPED_35B), 'explicit norm layout')
        require(type(heads) is int and 1 <= heads <= layout.value_heads and (layout==EQUAL_HEADS or heads==32), 'supported full head geometry')
        self.layout=layout
        self.scalar, self.heads = scalar, heads
        self.state, self.job, self.request, self.result = 'idle', None, None, None
        self.program, self.poison, self.status = None, False, None
        self.ticks, self.start, self.sequence, self.ack_bytes = 0, 0, 0, 0
        self.counts, self.scalar_baseline, self.scalar_counts = Counter(), Counter(), Counter()
        self.exp_baseline, self.exp_counts = Counter(), Counter()
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
        self.__init__(self.scalar, heads=self.heads,layout=self.layout)

    def _op(self, operation, a, b=0):
        return self.scalar.op(self, operation, a, b)

    @staticmethod
    def _bf16(bits):
        rounded = ((bits + 0x7fff + ((bits >> 16) & 1)) & 0xffffffff) & 0xffff0000
        if not finite(rounded):
            raise ArithmeticFault('nonfinite BF16 rounded result')
        return rounded

    def _compute(self, j):
        weights = [0] * HEAD_WIDTH
        for beat in range(8):
            weights[beat * 16:beat * 16 + 16] = struct.unpack('<16I', (yield (j.weight + beat * 64, None)))
        cache = [0] * HEAD_WIDTH
        for token in range(j.tokens):
            for head in range(j.heads):
                offset = token * j.layout.vector_elements * 2 + head * HEAD_BYTES
                for beat in range(4):
                    packet = struct.unpack('<32H', (yield (j.core + offset + beat * 64, None)))
                    for lane, raw in enumerate(packet):
                        cache[beat * 32 + lane] = raw << 16
                total = 0
                for x in cache:
                    total = self._op('add', total, self._op('mul_ieee_rne', x, x))
                mean = self._op('mul_ieee_rne', total, word(1 / 128))
                epsilon = self._op('add', mean, word(1e-6))
                inverse = self._op('div', word(1), self._op('sqrt', epsilon))
                for beat in range(4):
                    packet = struct.unpack('<32H', (yield (j.gate + offset + beat * 64, None)))
                    for lane, raw in enumerate(packet):
                        index, z = beat * 32 + lane, raw << 16
                        normalized = self._bf16(self._op('mul_ieee_rne', cache[index], inverse))
                        weighted = self._op('mul_ieee_rne', weights[index], normalized)
                        if not finite(z) or (z >> 31 and z & 0x7fffffff >= word(80)):
                            raise ArithmeticFault('source gate requires finite z > -80')
                        exponential = self._op('exp_negative', z)
                        denominator = self._op('add', word(1), exponential)
                        reciprocal = self._op('div', word(1), denominator)
                        sigmoid = self._op('mul_ieee_rne', reciprocal, exponential if z >> 31 else word(1))
                        activated = self._op('mul_ieee_rne', sigmoid, z)
                        cache[index] = self._bf16(self._op('mul_ieee_rne', weighted, activated))
                    yield (j.output + offset + beat * 64,
                           struct.pack('<32H', *(x >> 16 for x in cache[beat * 32:beat * 32 + 32])))
            for offset in range(j.heads * HEAD_BYTES, j.layout.vector_elements * 2, 64):
                yield (j.output + token * j.layout.vector_elements * 2 + offset, bytes(64))

    def _finish(self, status=None):
        self.status = status
        self.poison |= status is not None
        if self.scalar.client is self:
            self.scalar_counts = self.scalar.calls - self.scalar_baseline
            self.exp_counts = self.scalar.internal_calls - self.exp_baseline
            self.scalar.release(self)
        self.request, self.program = None, None
        self.result = GatedNormResult(self.job.tag, status, self.ack_bytes,
                                      self.ticks - self.start, status is None)
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
        fault = abort or reset
        if fault:
            p['job_ready'], p['memory'], p['response'] = False, None, None
            self.poison = True
            if self.state in ('wait', 'drain'):
                self.status, self.state = self.status or 'Aborted', 'drain'
            elif self.state in ('issue', 'finish'):
                self._finish(self.status or 'Aborted')
            elif self.state == 'idle':
                self.state = 'locked'
        if not fault and job is not None and p['job_ready']:
            require(type(job) is GatedNormJob, 'typed immutable GatedNormJob required')
            job.validate(self.heads,self.layout)
            identity = source_identity(layout=self.layout)
            require(self.scalar.acquire(self), 'shared scalar acquisition')
            p['job_fire'] = True
            self.job, self.start, self.identity = job, self.ticks, identity
            self.sequence, self.ack_bytes, self.status, self.counts = 0, 0, None, Counter()
            self.numerical_detail = None
            self.scalar_baseline, self.scalar_counts = self.scalar.calls.copy(), Counter()
            self.exp_baseline, self.exp_counts = self.scalar.internal_calls.copy(), Counter()
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
            if not q.write and status is None and (type(r.data) is not bytes or len(r.data) != 64):
                status = 'Protocol'
            if q.write and status is None:
                self.ack_bytes += 64
                self.counts['write_acks'] += 1
            if self.state == 'drain':
                # A response retires the single physical obligation. Preserve
                # a prior failure; retain a concurrent real transport error.
                self._finish(self.status if self.status != 'Aborted' else status or self.status)
            elif status is not None:
                self._finish(status)
            else:
                self._advance(None if q.write else r.data)
        if p['response'] is not None and response_ready:
            p['response_fire'] = True
            self.counts['owner_results'] += 1
            self.state = 'locked' if self.poison else 'idle'
            self.result = None
        return p

    def report(self):
        active = self.state not in ('finish', 'idle', 'locked')
        return dict(scope='GDN_GATED_NORM_SOFTWARE_OWNER', identity=self.identity,
                    status=self.status, numerical_detail=self.numerical_detail,
                    accepted=dict(self.counts), acknowledged_write_bytes=self.ack_bytes,
                    scalar_calls=dict(self.scalar.calls - self.scalar_baseline if active else self.scalar_counts),
                    exp_internal_calls=dict(self.scalar.internal_calls - self.exp_baseline if active else self.exp_counts),
                    active_heads=self.heads, production_geometry=self.heads == self.layout.value_heads,
                    test_only_zero_filled_heads=self.layout.value_heads - self.heads,
                    retained_fp32_head_capacity=HEAD_WIDTH, retained_weight_fp32_elements=HEAD_WIDTH,
                    retained_gate_packet_bytes=64, retained_output_packet_bytes=64,
                    tensor_buffered=False, row_bytes=self.layout.vector_elements*2, weight_bytes=WEIGHT_BYTES,
                    state_committed=False, history_committed=False, generation_advanced=False,
                    hardware_cycles=None, rtl_executed=False, native_acceptance=False,
                    native_numeric_diagnostics_executed=False)


class TypedGatedNormDriver:
    """Physical 64B data/ACK transport; publish only an accepted success.

    Core and Dense-produced gate must already be writable producer allocations
    with complete actual write/ACK coverage and accepted publication. Readonly
    test arrays cannot masquerade as either intermediate producer. The weight
    is the original immutable FP32[128], shared across all tokens and heads.
    """
    def __init__(self, owner, memory, job):
        require(type(owner) is GatedNormOwner and type(memory) is TypedMemory and type(job) is GatedNormJob,
                'gated norm owner, shared TypedMemory and immutable job required')
        job.validate(owner.heads,owner.layout)
        require(owner.ports()['job_ready'] and memory.pending is None, 'drained resources required')
        self.core = memory.exact(job.core, job.write_bytes, readable=True)
        self.gate = memory.exact(job.gate, job.write_bytes, readable=True)
        for region in (self.core, self.gate):
            require(not region.readonly and region.written == region.acknowledged == set(range(0, region.extent, 64)),
                    'core/gate require previous actual producer data/ACK and publication')
        self.weight = memory.exact(job.weight, WEIGHT_BYTES, readable=True)
        require(self.weight.readonly, 'original FP32 weight parameter must be readonly')
        self.output = memory.exact(job.output, job.write_bytes, readable=False)
        self.owner, self.memory, self.job = owner, memory, job
        self.sources = (self.core, self.gate, self.weight)
        self.scalar_resource = owner.scalar
        self.resource_identity = (id(owner), id(memory), id(owner.scalar),owner.layout)
        self.source_hashes = tuple(sha(r.raw()) for r in self.sources)
        self.pending, self.response, self.aborted = None, None, False
        self.pending_request, self.pending_write = None, None
        self.counts = Counter()
        require(owner.tick(job=job)['job_fire'], 'gated norm admission rejected')

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             abort=False, reset=False, read_error=False, ack_error=False,
             read_tag=None, read_nbytes=None, ack_tag=None, ack_nbytes=None):
        require(self.response is None, 'gated norm invocation already retired')
        require(self.resource_identity == (id(self.owner), id(self.memory), id(self.owner.scalar),self.owner.layout) and
                self.owner.scalar is self.scalar_resource, 'owner/memory/shared scalar resource replaced')
        pending = self.pending if memory_response_ready else None
        if pending is not None:
            # Keep accepted request identity after the owner consumes the wire
            # response and clears its request on a terminal protocol failure.
            q = self.pending_request
            require(q is not None and self.owner.request is q, 'accepted request identity changed')
            if q.write:
                require(self.pending_write is not None, 'write response without physical obligation')
                record, expected = self.pending_write
                require(self.memory.pending is record and len(record) == 4 and
                        record[0] is expected[0] and record[1] is expected[1] and
                        tuple(record[2:]) == expected[2:], 'accepted physical write identity changed')
            else:
                require(self.pending_write is None and self.memory.pending is None,
                        'read response cannot retire another physical write')
            tag = ack_tag if q.write else read_tag
            nbytes = ack_nbytes if q.write else read_nbytes
            inject_error = ack_error if q.write else read_error
            pending = MemoryResponse(pending.tag if tag is None else tag, pending.data,
                                     True if inject_error and type(pending.error) is bool else pending.error,
                                     pending.nbytes if nbytes is None else nbytes)
        abort_edge = abort and not self.aborted
        self.aborted |= abort_edge or reset
        e = self.owner.tick(memory_ready=memory_ready, memory_response=pending,
                            response_ready=response_ready, abort=abort_edge, reset=reset)
        self.counts['ticks'] += 1
        if e['memory_response_fire']:
            require(self.pending is not None, 'response without accepted request')
            if self.pending_request.write:
                command = self.pending_write[1][0]
                malformed = (type(pending.tag) is not int or pending.tag != command.tag or
                             type(pending.nbytes) is not int or pending.nbytes != command.beats * 64 or
                             type(pending.error) is not bool)
                # The owner sees the original malformed wire response. Retire
                # only its latched physical obligation as failed, never credit
                # malformed ACK bytes and never touch another pending write.
                self.memory.acknowledge(WriteAck(command.tag, malformed or pending.error,
                                                 command.beats * 64))
            self.pending, self.pending_request, self.pending_write = None, None, None
        if e['memory_fire']:
            require(self.pending is None, 'multiple outstanding gated norm requests')
            q = e['memory']
            region = self.memory._resolve(q.address)
            self.pending_request = q
            if q.write:
                require(region is self.output and len(q.data) == 64, 'write escaped complete BF16 output span')
                self.memory.begin_write(WriteCommand(q.address, 1, q.tag))
                self.memory.write_data(struct.unpack('<32H', q.data), True, mask=FULL_MASK)
                self.pending_write = (self.memory.pending, tuple(self.memory.pending))
                self.pending = MemoryResponse(q.tag)
                self.counts['write_bytes'] += 64
            else:
                require(any(region is r for r in self.sources), 'read escaped immutable sources')
                self.pending = MemoryResponse(q.tag, self.memory.read64(q.address))
                self.counts['read_bytes'] += 64
        if e['response_fire']:
            require(self.pending is None and self.memory.pending is None, 'terminal before transport drained')
            require(self.source_hashes == tuple(sha(r.raw()) for r in self.sources), 'producer/parameter bytes changed')
            self.response = e['response']
            if self.response.status is None:
                require(self.owner.identity == source_identity(layout=self.owner.layout), 'gated norm source changed during execution')
                require(self.response.staging_complete and self.response.write_bytes == self.job.write_bytes and
                        not any((self.response.state_committed, self.response.history_committed,
                                 self.response.generation_advanced)), 'complete stateless staging receipt required')
                self.memory.publish(self.job.output, (self.response.tag, None, self.job.write_bytes))
        return e

    def report(self):
        return dict(owner=self.owner.report(), complete=self.response is not None,
                    status=None if self.response is None else self.response.status,
                    staging_complete=self.response is not None and self.response.staging_complete,
                    counts=dict(self.counts), output_published=self.output.published,
                    state_committed=False, history_committed=False, generation_advanced=False,
                    input_sha256=list(self.source_hashes), output_sha256=sha(self.output.raw()))
