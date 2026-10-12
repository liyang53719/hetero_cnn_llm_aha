"""Memory-fed BF16 residual Add and BF16-SiLU-then-Mul software owner.

Maps committed GdnElementwiseOwner onto one caller-owned ConvScalar/PrepScalar.
Add/Div retain legacy fault flags; only source opcode 6 accepts tiny inexact
multiplication. Negative SiLU gates <= -80 remain Unsupported. The official
SiLU BF16 boundary occurs BEFORE multiplying by the BF16 up projection.

Production widths are H1024 and FFN3584. Explicit reduced test widths are
multiples of 32: this candidate makes no claim for arbitrary partial tails.
Three 32-element input/output beat buffers are retained, never a tensor.
Software ticks are not hardware cycles; no Host command or RTL is introduced.
"""
from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
import struct
import subprocess

from ..rms_owner import (ROOT, SCALAR_SOURCE, SCALAR_SHA, ArithmeticFault,
                         MemoryRequest, MemoryResponse, finite, sha, word)
from ..conv.scalar import ConvScalar, OPCODES
from ..typed_dense import TypedMemory, FULL_MASK, GUARD
from ...qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck


OWNER_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnElementwiseOwner.scala'
OWNER_SHA = '01b394526f75b9732c3e605652c64f3968851aca97258a3a640bc056de1f2fe3'
OFFICIAL_SOURCE = 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py'
OFFICIAL_SHA = 'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18'
HIDDEN_WIDTH, FFN_WIDTH, BEAT_ELEMENTS, BEAT_BYTES = 1024, 3584, 32, 64


def require(ok, why):
    if not ok:
        raise ValueError('typed Elementwise: ' + why)


class ElementwiseOp(IntEnum):
    Add = 0
    SiluMul = 1


def _geometry(hidden_width, ffn_width, test_geometry):
    require(type(test_geometry) is bool and all(type(n) is int and n > 0 and n % 32 == 0
            for n in (hidden_width, ffn_width)), 'full 32-element beat geometry required')
    require((hidden_width, ffn_width) == (HIDDEN_WIDTH, FFN_WIDTH) or
            (test_geometry and hidden_width <= HIDDEN_WIDTH and ffn_width <= FFN_WIDTH),
            'production H1024/FFN3584 or explicit reduced test geometry required')


def source_identity(root=ROOT):
    root = Path(root)
    source = subprocess.run(['git', 'show', 'HEAD:' + OWNER_SOURCE], cwd=root,
                            check=True, capture_output=True, timeout=10).stdout
    require(sha(source) == OWNER_SHA, 'committed elementwise source drift')
    sources = {SCALAR_SOURCE: SCALAR_SHA, OFFICIAL_SOURCE: OFFICIAL_SHA}
    for name, digest in sources.items():
        require(sha((root / name).read_bytes()) == digest, 'source drift: ' + name)
    # Explicit execution closure: adding reference/test files cannot change it.
    models = ('candidates/qwen35_gdn_prefill/elementwise/model.py',
              'candidates/qwen35_gdn_prefill/conv/scalar.py',
              'candidates/qwen35_gdn_prefill/prep/scalar.py',
              'candidates/qwen35_gdn_prefill/rms_owner.py',
              'candidates/qwen35_gdn_prefill/typed_dense.py')
    return dict(source_sha256={'HEAD:' + OWNER_SOURCE: OWNER_SHA, **sources},
                implementation_sha256={p: sha((root / p).read_bytes()) for p in models},
                opcodes=dict(OPCODES), source_default_max_tokens=128,
                candidate_tokens='M1..128', production_host_command=False,
                arithmetic='BF16_Add_or_BF16_SiLU_before_BF16_product',
                negative_silu_le_minus80='Unsupported', arbitrary_tail_supported=False,
                native_acceptance=False, native_numeric_diagnostics_executed=False,
                rtl_executed=False, historical_pass_inherited=False)


@dataclass(frozen=True)
class ElementwiseJob:
    tag: int
    a: int
    b: int
    output: int
    tokens: int
    op: ElementwiseOp = ElementwiseOp.Add
    row_width: int = HIDDEN_WIDTH

    @property
    def write_bytes(self):
        return self.tokens * self.row_width * 2

    def validate(self, hidden_width=HIDDEN_WIDTH, ffn_width=FFN_WIDTH, test_geometry=False):
        _geometry(hidden_width, ffn_width, test_geometry)
        require(type(self.op) in (int, ElementwiseOp) and self.op in tuple(ElementwiseOp),
                'only existing Add=0 and SiluMul=1 operations supported')
        width = hidden_width if self.op == ElementwiseOp.Add else ffn_width
        require(type(self.tokens) is int and 1 <= self.tokens <= 128 and
                type(self.row_width) is int and self.row_width == width, 'M1..128 / exact operation width')
        require(type(self.tag) is int and 0 <= self.tag < 1 << 32, 'job tag domain')
        spans = ((self.a, self.write_bytes), (self.b, self.write_bytes), (self.output, self.write_bytes))
        for base, extent in spans:
            require(type(base) is int and base >= 0 and base % 64 == 0 and base + extent <= 1 << 56,
                    'aligned nonempty 56-bit physical span')
        require(all(a + n <= b or b + m <= a for i, (a, n) in enumerate(spans)
                    for b, m in spans[:i]), 'three complete typed allocations must be disjoint')


@dataclass(frozen=True)
class ElementwiseResult:
    tag: int
    status: str | None
    write_bytes: int
    model_ticks: int
    staging_complete: bool
    state_committed: bool = False
    history_committed: bool = False
    generation_advanced: bool = False


class UnsupportedGate(ArithmeticFault):
    pass


class ElementwiseOwner:
    """Held request, one in flight, final ACK, held terminal, then publication.

    Abort/reset drains an accepted external request and poisons admission until
    reset. A held success can still be aborted before terminal acceptance.
    Accepted completion is not retracted; earlier faults retain their status.
    """
    def __init__(self, scalar, *, hidden_width=HIDDEN_WIDTH, ffn_width=FFN_WIDTH,
                 test_geometry=False):
        require(isinstance(scalar, ConvScalar), 'explicit caller-owned ConvScalar or PrepScalar required')
        _geometry(hidden_width, ffn_width, test_geometry)
        self.scalar = scalar
        self.hidden_width, self.ffn_width, self.test_geometry = hidden_width, ffn_width, test_geometry
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
        self.__init__(self.scalar, hidden_width=self.hidden_width, ffn_width=self.ffn_width,
                      test_geometry=self.test_geometry)

    def _op(self, operation, a, b=0):
        return self.scalar.op(self, operation, a, b)

    @staticmethod
    def _bf16(bits):
        rounded = ((bits + 0x7fff + ((bits >> 16) & 1)) & 0xffffffff) & 0xffff0000
        if not finite(rounded):
            raise ArithmeticFault('nonfinite BF16 rounded result')
        return rounded

    def _compute(self, j):
        input_a, input_b, output = [0] * 32, [0] * 32, [0] * 32
        for offset in range(0, j.write_bytes, 64):
            input_a[:] = struct.unpack('<32H', (yield (j.a + offset, None)))
            input_b[:] = struct.unpack('<32H', (yield (j.b + offset, None)))
            for lane in range(32):
                x, y = input_a[lane] << 16, input_b[lane] << 16
                if not finite(x) or not finite(y):
                    raise ArithmeticFault('nonfinite BF16 input')
                if j.op == ElementwiseOp.Add:
                    result = self._op('add', x, y)
                else:
                    if x >> 31 and x & 0x7fffffff >= word(80):
                        raise UnsupportedGate('source SiLU gate requires finite x > -80')
                    exponential = self._op('exp_negative', x)
                    denominator = self._op('add', word(1), exponential)
                    inverse = self._op('div', word(1), denominator)
                    sigmoid = self._op('mul_ieee_rne', inverse, exponential if x >> 31 else word(1))
                    activated = self._bf16(self._op('mul_ieee_rne', sigmoid, x))
                    result = self._op('mul_ieee_rne', activated, y)
                output[lane] = self._bf16(result) >> 16
            yield (j.output + offset, struct.pack('<32H', *output))

    def _finish(self, status=None):
        self.status = status
        self.poison |= status is not None
        if self.scalar.client is self:
            self.scalar_counts = self.scalar.calls - self.scalar_baseline
            self.exp_counts = self.scalar.internal_calls - self.exp_baseline
            self.scalar.release(self)
        self.request, self.program = None, None
        self.result = ElementwiseResult(self.job.tag, status, self.ack_bytes,
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
            self._finish('Unsupported' if isinstance(error, UnsupportedGate) else 'Numerical')

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
            require(type(job) is ElementwiseJob, 'typed immutable ElementwiseJob required')
            job.validate(self.hidden_width, self.ffn_width, self.test_geometry)
            identity = source_identity()
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
        return dict(scope='GDN_ELEMENTWISE_SOFTWARE_OWNER', identity=self.identity,
                    status=self.status, numerical_detail=self.numerical_detail,
                    accepted=dict(self.counts), acknowledged_write_bytes=self.ack_bytes,
                    scalar_calls=dict(self.scalar.calls - self.scalar_baseline if active else self.scalar_counts),
                    exp_internal_calls=dict(self.scalar.internal_calls - self.exp_baseline if active else self.exp_counts),
                    operation=None if self.job is None else ElementwiseOp(self.job.op).name,
                    hidden_width=self.hidden_width, ffn_width=self.ffn_width,
                    production_geometry=(self.hidden_width, self.ffn_width) == (HIDDEN_WIDTH, FFN_WIDTH),
                    test_geometry=self.test_geometry, arbitrary_tail_supported=False,
                    retained_a_elements=32, retained_b_elements=32, retained_output_elements=32,
                    tensor_buffered=False, output_mask=FULL_MASK,
                    state_committed=False, history_committed=False, generation_advanced=False,
                    hardware_cycles=None, rtl_executed=False, native_acceptance=False,
                    native_numeric_diagnostics_executed=False)


class TypedElementwiseDriver:
    """Physical 64B data/ACK transport; accepted success alone publishes output.

    Add may consume authenticated readonly initial hidden bytes as input A.
    Every other BF16 input requires actual written, ACKed, published producer
    storage; readonly input bytes never fabricate producer write/ACK coverage.
    """
    def __init__(self, owner, memory, job):
        require(type(owner) is ElementwiseOwner and type(memory) is TypedMemory and
                type(job) is ElementwiseJob, 'elementwise owner, shared TypedMemory and immutable job required')
        job.validate(owner.hidden_width, owner.ffn_width, owner.test_geometry)
        require(owner.ports()['job_ready'] and memory.pending is None, 'drained resources required')
        self.a = memory.exact(job.a, job.write_bytes, readable=True)
        self.b = memory.exact(job.b, job.write_bytes, readable=True)
        for index, region in enumerate((self.a, self.b)):
            if index == 0 and job.op == ElementwiseOp.Add and region.readonly:
                continue
            require(not region.readonly and region.written == region.acknowledged == set(range(0, region.extent, 64)),
                    'inputs require previous actual producer data/ACK and publication')
        self.output = memory.exact(job.output, job.write_bytes, readable=False)
        require(self.output.raw() == GUARD * (job.write_bytes // 64), 'output must retain initial sentinels')
        self.owner, self.memory, self.job = owner, memory, job
        self.sources = (self.a, self.b)
        self.scalar_resource = owner.scalar
        self.resource_identity = (id(owner), id(memory), id(owner.scalar))
        self.source_hashes = tuple(sha(r.raw()) for r in self.sources)
        self.pending, self.response, self.aborted = None, None, False
        self.pending_request, self.pending_write = None, None
        self.counts = Counter()
        require(owner.tick(job=job)['job_fire'], 'elementwise admission rejected')

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             abort=False, reset=False, read_error=False, ack_error=False,
             read_tag=None, read_nbytes=None, ack_tag=None, ack_nbytes=None):
        require(self.response is None, 'elementwise invocation already retired')
        require(self.resource_identity == (id(self.owner), id(self.memory), id(self.owner.scalar)) and
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
            require(self.pending is None, 'multiple outstanding elementwise requests')
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
                require(any(region is r for r in self.sources), 'read escaped immutable inputs')
                self.pending = MemoryResponse(q.tag, self.memory.read64(q.address))
                self.counts['read_bytes'] += 64
        if e['response_fire']:
            require(self.pending is None and self.memory.pending is None, 'terminal before transport drained')
            require(self.source_hashes == tuple(sha(r.raw()) for r in self.sources), 'producer bytes changed')
            self.response = e['response']
            if self.response.status is None:
                require(self.owner.identity == source_identity(), 'elementwise source changed during execution')
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
