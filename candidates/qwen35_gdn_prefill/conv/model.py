"""Memory-fed BF16 Conv4/SiLU and raw-history staging, not a block commit.

One 32-channel group, four tap weights/history and one raw/output packet are
retained. The accepted source sequence is weights, optional history, then each
token read/compute/output ACK, followed by four raw-history writes/ACKs.
Software ticks and scalar calls are not hardware cycles or RTL evidence.
"""
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import struct
import subprocess

from ..rms_owner import (ROOT, SCALAR_SOURCE, SCALAR_SHA, ArithmeticFault,
                         MemoryRequest, MemoryResponse, finite, sha, word)
from ..typed_dense import TypedMemory, FULL_MASK
from ...qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from .scalar import ConvScalar, OPCODES


OWNER_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnConv4Owner.scala'
OWNER_SHA = '99b7e4a4cbf2df234fc831cd1a85d44b032f981221f57fde504f3f5aebe6a28a'
BEAT_BYTES = 64


def require(ok, why):
    if not ok:
        raise ValueError('typed Conv4: ' + why)


def source_identity(root=ROOT):
    root = Path(root)
    source = subprocess.run(['git', 'show', 'HEAD:' + OWNER_SOURCE], cwd=root,
                            check=True, capture_output=True, timeout=10).stdout
    require(sha(source) == OWNER_SHA, 'committed Conv4 source drift')
    require(sha((root / SCALAR_SOURCE).read_bytes()) == SCALAR_SHA, 'shared scalar source drift')
    models = ('candidates/qwen35_gdn_prefill/conv/model.py',
              'candidates/qwen35_gdn_prefill/conv/scalar.py',
              'candidates/qwen35_gdn_prefill/rms_owner.py',
              'candidates/qwen35_gdn_prefill/typed_dense.py')
    return dict(source_sha256={'HEAD:' + OWNER_SOURCE: OWNER_SHA, SCALAR_SOURCE: SCALAR_SHA},
                implementation_sha256={p: sha((root / p).read_bytes()) for p in models},
                opcodes=dict(OPCODES), arithmetic='four_op6_products_ascending_op0_adds_bf16_then_source_silu',
                lifecycle='local_staging_only_final_block_fence_required',
                source_history_commit_replaced_by_staging_receipt=True,
                abort_reset_software_transport_extension=True,
                native_acceptance=False, rtl_executed=False, historical_pass_inherited=False)


@dataclass(frozen=True)
class ConvJob:
    tag: int
    input: int
    weight: int
    output: int
    history_in: int
    history_out: int
    tokens: int
    cold: bool
    expected_generation: int
    channels: int = 6144

    @property
    def vector_bytes(self):
        return self.tokens * self.channels * 2

    @property
    def history_bytes(self):
        return self.channels * 8

    @property
    def write_bytes(self):
        return self.vector_bytes + self.history_bytes

    def validate(self, channels=6144, current_generation=0):
        require(type(channels) is int and 0 < channels <= 65535 and channels % 32 == 0,
                '32-channel groups required')
        require(type(self.channels) is int and self.channels == channels and
                type(self.tokens) is int and 1 <= self.tokens <= 128, 'channel/M1..128 domain')
        require(type(self.tag) is int and 0 <= self.tag < 1 << 32, 'job tag domain')
        require(type(self.cold) is bool and type(self.expected_generation) is int and
                0 <= self.expected_generation < (1 << 32) - 1 and
                type(current_generation) is int and current_generation == self.expected_generation and
                (not self.cold or self.expected_generation == 0), 'history generation dependency')
        spans = ((self.input, self.vector_bytes), (self.weight, self.history_bytes),
                 (self.output, self.vector_bytes), (self.history_in, self.history_bytes),
                 (self.history_out, self.history_bytes))
        for base, extent in spans:
            require(type(base) is int and base >= 0 and base % 64 == 0 and base + extent <= 1 << 56,
                    'aligned nonempty 56-bit physical span')
        # TypedMemory has one nonoverlapping allocation per complete tensor.
        require(all(a + n <= b or b + m <= a for i, (a, n) in enumerate(spans) for b, m in spans[:i]),
                'five typed allocations must be disjoint')


@dataclass(frozen=True)
class ConvResult:
    tag: int
    status: str | None
    write_bytes: int
    model_ticks: int
    staging_complete: bool
    output_ack_bytes: int
    history_ack_bytes: int
    generation: int
    history_committed: bool = False


class ConvOwner:
    """One physical request in flight, one held terminal, caller-owned scalar."""
    def __init__(self, scalar, *, channels=6144, observe=None):
        require(isinstance(scalar, ConvScalar), 'explicit shared ConvScalar instance required')
        require(type(channels) is int and 0 < channels <= 65535 and channels % 32 == 0,
                '32-channel groups required')
        self.scalar, self.channels = scalar, channels
        require(observe is None or callable(observe), 'optional readonly observation callback')
        self.observe = observe
        self.state, self.job, self.request, self.result = 'idle', None, None, None
        self.program, self.poison, self.status = None, False, None
        self.ticks, self.start, self.sequence, self.ack_bytes = 0, 0, 0, 0
        self.output_ack_bytes, self.history_ack_bytes = 0, 0
        self.counts, self.scalar_baseline, self.scalar_counts = Counter(), Counter(), Counter()
        self.internal_baseline, self.internal_counts = Counter(), Counter()
        self.identity = None

    def ports(self):
        return dict(job_ready=self.state == 'idle' and not self.poison and self.scalar.client is None,
                    memory=self.request if self.state == 'issue' else None,
                    memory_response_ready=self.state in ('wait', 'drain'),
                    response=self.result if self.state == 'finish' else None,
                    reset_required=self.poison, state=self.state)

    def reset(self):
        require(self.state in ('idle', 'locked') and self.request is None and self.scalar.client is not self,
                'reset requires drained transport and retired held completion')
        self.__init__(self.scalar, channels=self.channels, observe=self.observe)

    def _op(self, operation, a, b=0):
        return self.scalar.op(self, operation, a, b)

    def _read_group(self, base):
        values = []
        for beat in range(4):
            raw = yield (base + beat * 64, None)
            values.extend(struct.unpack('<32H', raw))
        return [values[lane * 4:lane * 4 + 4] for lane in range(32)]

    def _compute(self, j):
        for group in range(0, self.channels, 32):
            weights = yield from self._read_group(j.weight + group * 8)
            history = ([[0] * 4 for _ in range(32)] if j.cold else
                       (yield from self._read_group(j.history_in + group * 8)))
            for token in range(j.tokens):
                offset = (token * self.channels + group) * 2
                packet = yield (j.input + offset, None)
                raw = struct.unpack('<32H', packet)
                output = []
                for lane in range(32):
                    accumulator = 0
                    for tap in range(4):
                        sample = raw[lane] if tap == 3 else history[lane][tap + 1]
                        product = self._op('mul_ieee_rne', sample << 16, weights[lane][tap] << 16)
                        accumulator = self._op('add', accumulator, product)
                    conv = ((accumulator + 0x7fff + ((accumulator >> 16) & 1)) & 0xffffffff) & 0xffff0000
                    if not finite(conv) or (conv >> 31 and conv & 0x7fffffff >= 0x42a00000):
                        raise ArithmeticFault('BF16 conv overflow or unsupported negative conv <= -80')
                    if self.observe is not None:
                        # Only raw immutable coordinates/bits leave the owner. The
                        # callback return value never participates in computation.
                        self.observe(j.tag,token,group+lane,conv >> 16)
                    probability = self._op('exp_negative', conv)
                    denominator = self._op('add', word(1), probability)
                    inverse = self._op('div', word(1), denominator)
                    signed = self._op('mul', inverse, probability if conv >> 31 else word(1))
                    activated = self._op('mul', signed, conv)
                    rounded = ((activated + 0x7fff + ((activated >> 16) & 1)) & 0xffffffff) >> 16
                    if not finite(rounded << 16):
                        raise ArithmeticFault('terminal BF16 conversion overflow')
                    output.append(rounded)
                yield (j.output + offset, struct.pack('<32H', *output))
                # Generator resumes only on the real output write ACK.
                history = [row[1:] + [raw[lane]] for lane, row in enumerate(history)]
            flat = [v for row in history for v in row]
            for beat in range(4):
                yield (j.history_out + group * 8 + beat * 64,
                       struct.pack('<32H', *flat[beat * 32:(beat + 1) * 32]))

    def _finish(self, status=None):
        self.status = status
        self.poison |= status is not None
        if self.scalar.client is self:
            self.scalar_counts = self.scalar.calls - self.scalar_baseline
            self.internal_counts = self.scalar.internal_calls - self.internal_baseline
            self.scalar.release(self)
        self.request, self.program = None, None
        self.result = ConvResult(self.job.tag, status, self.ack_bytes, self.ticks - self.start,
                                 status is None, self.output_ack_bytes, self.history_ack_bytes,
                                 self.job.expected_generation)
        self.state = 'finish'

    def _advance(self, data=None):
        try:
            address, output = self.program.send(data)
            require(self.sequence < 1 << 32, 'memory sequence exhausted')
            self.request = MemoryRequest(address, (self.job.tag << 32) | self.sequence, output)
            self.sequence += 1
            self.state = 'issue'
        except StopIteration:
            complete = (self.output_ack_bytes == self.job.vector_bytes and
                        self.history_ack_bytes == self.job.history_bytes)
            self._finish(None if complete else 'Protocol')
        except ArithmeticFault:
            self._finish('Numerical')

    def tick(self, *, job=None, current_generation=0, memory_ready=False, memory_response=None,
             response_ready=False, abort=False, reset=False):
        p = self.ports()
        p.update(job_fire=False, memory_fire=False, memory_response_fire=False, response_fire=False)
        self.ticks += 1
        if reset and self.state in ('idle', 'locked'):
            self.reset()
            p['job_ready'] = False
            return p
        if reset and self.state == 'finish':
            raise ValueError('typed Conv4: reset cannot erase a held completion')
        fault = abort or reset
        if fault:
            p['job_ready'], p['memory'] = False, None
            self.poison = True
            if self.state in ('wait', 'drain'):
                self.status, self.state = 'Aborted', 'drain'
            elif self.state in ('issue', 'finish'):
                # A held success is not yet linearized and cannot publish on
                # abort. Preserve an earlier fault's reason for diagnostics.
                self._finish(self.status or 'Aborted')
                p['response'] = None
            elif self.state == 'idle':
                self.state = 'locked'
        if not fault and job is not None and p['job_ready']:
            require(type(job) is ConvJob, 'typed immutable ConvJob required')
            job.validate(self.channels, current_generation)
            identity = source_identity()
            require(self.scalar.acquire(self), 'shared scalar acquisition')
            p['job_fire'] = True
            self.job, self.start, self.identity = job, self.ticks, identity
            self.sequence, self.ack_bytes, self.output_ack_bytes, self.history_ack_bytes = 0, 0, 0, 0
            self.status, self.counts = None, Counter()
            self.scalar_baseline, self.scalar_counts = self.scalar.calls.copy(), Counter()
            self.internal_baseline, self.internal_counts = self.scalar.internal_calls.copy(), Counter()
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
            # One accepted physical response retires the sole obligation even
            # on bad tag, matching the source owner; no hidden reply filter.
            if q.write and status is None:
                self.ack_bytes += 64
                self.counts['write_acks'] += 1
                if self.job.output <= q.address < self.job.output + self.job.vector_bytes:
                    self.output_ack_bytes += 64
                else:
                    self.history_ack_bytes += 64
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
        return dict(scope='PACKED_BF16_CONV4_SILU_HISTORY_STAGING_SOFTWARE_OWNER', identity=self.identity,
                    status=self.status, accepted=dict(self.counts), acknowledged_write_bytes=self.ack_bytes,
                    output_ack_bytes=self.output_ack_bytes, history_ack_bytes=self.history_ack_bytes,
                    scalar_calls=dict(self.scalar.calls - self.scalar_baseline if active else self.scalar_counts),
                    exp_internal_calls=dict(self.scalar.internal_calls - self.internal_baseline if active else self.internal_counts),
                    retained_bf16_weight_capacity=128, retained_bf16_history_capacity=128,
                    retained_bf16_input_capacity=32, retained_bf16_output_capacity=32,
                    global_history_committed=False, generation_advanced=False,
                    external_readonly_observer=self.observe is not None,
                    hardware_cycles=None, rtl_executed=False, native_acceptance=False)


class TypedConvDriver:
    """Real 64B read/write/ACK service; publish output only after both spans ACK.

    history_out remains unpublished staging even after successful terminal.
    Only the caller's eventual complete-block fence may select/commit that root.
    Warm history must be an actual ACKed, published previous producer allocation.
    """
    def __init__(self, owner, memory, job, *, current_generation=0):
        require(type(owner) is ConvOwner and type(memory) is TypedMemory and type(job) is ConvJob,
                'Conv owner, shared TypedMemory and immutable job required')
        job.validate(owner.channels, current_generation)
        require(owner.ports()['job_ready'] and memory.pending is None, 'drained resources required')
        self.input = memory.exact(job.input, job.vector_bytes, readable=True)
        require(not self.input.readonly and
                self.input.written == self.input.acknowledged == set(range(0, job.vector_bytes, 64)),
                'QKV input requires previous actual producer data/ACK and publication')
        self.weight = memory.exact(job.weight, job.history_bytes, readable=True)
        if job.cold:
            # Source cold admission validates the span, but never reads it.
            # The arithmetic program initializes its retained history to +0.
            self.history_in = memory.regions.get(job.history_in)
            require(self.history_in is not None and self.history_in.extent == job.history_bytes,
                    'complete cold history physical allocation required')
            self.history_in.check()
        else:
            self.history_in = memory.exact(job.history_in, job.history_bytes, readable=True)
            require(not self.history_in.readonly and
                    self.history_in.written == self.history_in.acknowledged == set(range(0, job.history_bytes, 64)),
                    'warm history requires previous actual data/ACK and caller publication')
        self.output = memory.exact(job.output, job.vector_bytes, readable=False)
        self.history_out = memory.exact(job.history_out, job.history_bytes, readable=False)
        self.owner, self.memory, self.job = owner, memory, job
        self.scalar_resource = owner.scalar
        self.resource_identity = (id(owner), id(memory), id(owner.scalar))
        self.source_hashes = tuple(sha(r.raw()) for r in (self.input, self.weight, self.history_in))
        self.pending, self.response, self.aborted = None, None, False
        self.counts = Counter()
        require(owner.tick(job=job, current_generation=current_generation)['job_fire'], 'Conv admission rejected')

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             abort=False, reset=False, read_error=False, ack_error=False):
        require(self.response is None, 'Conv invocation already retired')
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
            require(self.pending is None, 'multiple outstanding Conv requests')
            q = e['memory']
            region = self.memory._resolve(q.address)
            if q.write:
                require((region is self.output or region is self.history_out) and len(q.data) == 64,
                        'write escaped the two typed staging spans')
                self.memory.begin_write(WriteCommand(q.address, 1, q.tag))
                self.memory.write_data(struct.unpack('<32H', q.data), True, mask=FULL_MASK)
                self.pending = MemoryResponse(q.tag)
                self.counts['write_bytes'] += 64
            else:
                require(any(region is r for r in (self.input, self.weight, self.history_in)), 'read escaped inputs')
                self.pending = MemoryResponse(q.tag, self.memory.read64(q.address))
                self.counts['read_bytes'] += 64
        if e['response_fire']:
            require(self.pending is None and self.memory.pending is None, 'terminal before transport drained')
            require(self.source_hashes == tuple(sha(r.raw()) for r in (self.input, self.weight, self.history_in)),
                    'actual input/weight/history changed')
            self.response = e['response']
            if self.response.status is None:
                require(self.owner.identity == source_identity(), 'Conv source changed during execution')
                require(self.response.staging_complete and not self.response.history_committed and
                        self.response.output_ack_bytes == self.job.vector_bytes and
                        self.response.history_ack_bytes == self.job.history_bytes,
                        'two-span staging receipt incomplete')
                for region in (self.output, self.history_out):
                    region.check()
                    require(region.written == region.acknowledged == set(range(0, region.extent, 64)),
                            'incomplete actual data/ACK coverage')
                self.memory.publish(self.job.output, (self.response.tag, None, self.job.vector_bytes))
        return e

    def report(self):
        return dict(owner=self.owner.report(), complete=self.response is not None,
                    status=None if self.response is None else self.response.status,
                    staging_complete=self.response is not None and self.response.staging_complete,
                    counts=dict(self.counts), output_published=self.output.published,
                    history_staging_unpublished=not self.history_out.published,
                    cold_history_initialization='internal_bf16_positive_zero' if self.job.cold else None,
                    history_input_consumed=not self.job.cold,
                    history_committed=False, generation_advanced=False,
                    input_sha256=list(self.source_hashes), output_sha256=sha(self.output.raw()),
                    history_staging_sha256=sha(self.history_out.raw()))
