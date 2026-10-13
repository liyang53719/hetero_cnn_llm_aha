"""Memory-fed BF16 residual Add, SiLU-Mul and opt-in attention sigmoid-Mul.

Maps committed GdnElementwiseOwner onto one caller-owned ConvScalar/PrepScalar.
Add/Div retain legacy fault flags; only source opcode 6 accepts tiny inexact
multiplication. Negative activation gates <= -80 remain Unsupported. The
official SiLU or sigmoid BF16 boundary occurs BEFORE the final BF16 product.

Production widths are H1024, FFN3584 and attention2048. SigmoidMul is disabled
by default, exactly as in the committed owner. Explicit reduced test widths are
multiples of 32: this candidate makes no claim for arbitrary partial tails.
Three 32-element input/output beat buffers are retained, never a tensor.
Software ticks are not hardware cycles; no Host command or RTL is introduced.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, fields
from enum import IntEnum
import hashlib
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
HIDDEN_WIDTH, FFN_WIDTH, ATTENTION_WIDTH = 1024, 3584, 2048
BEAT_ELEMENTS, BEAT_BYTES = 32, 64


def require(ok, why):
    if not ok:
        raise ValueError('typed Elementwise: ' + why)


def _field_binding(value):
    return tuple((field.name, type(getattr(value, field.name)), getattr(value, field.name))
                 for field in fields(value))


def _same_coverage(actual, expected):
    return (type(actual) in (set, frozenset) and all(type(offset) is int for offset in actual)
            and actual == expected)


class ElementwiseOp(IntEnum):
    Add = 0
    SiluMul = 1
    SigmoidMul = 2


def _geometry(hidden_width, ffn_width, test_geometry, attention_width=ATTENTION_WIDTH):
    require(type(test_geometry) is bool and all(type(n) is int and n > 0 and n % 32 == 0
            for n in (hidden_width, ffn_width, attention_width)), 'full 32-element beat geometry required')
    require((hidden_width, ffn_width, attention_width) == (HIDDEN_WIDTH, FFN_WIDTH, ATTENTION_WIDTH) or
            (test_geometry and hidden_width <= HIDDEN_WIDTH and ffn_width <= FFN_WIDTH and
             attention_width <= ATTENTION_WIDTH),
            'production H1024/FFN3584/attention2048 or explicit reduced test geometry required')


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
                arithmetic='BF16_Add_or_BF16_SiLU_or_opt_in_BF16_sigmoid_before_BF16_product',
                source_default_attention_width=ATTENTION_WIDTH,
                source_default_enable_attention_sigmoid_mul=False,
                elementwise_opcodes={op.name: int(op) for op in ElementwiseOp},
                negative_silu_le_minus80='Unsupported', negative_sigmoid_le_minus80='Unsupported',
                arbitrary_tail_supported=False,
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

    def validate(self, hidden_width=HIDDEN_WIDTH, ffn_width=FFN_WIDTH, test_geometry=False,
                 *, attention_width=ATTENTION_WIDTH, enable_attention_sigmoid_mul=False):
        _geometry(hidden_width, ffn_width, test_geometry, attention_width)
        require(type(enable_attention_sigmoid_mul) is bool, 'explicit attention SigmoidMul enable flag')
        require(type(self.op) in (int, ElementwiseOp) and self.op in tuple(ElementwiseOp),
                'only existing Add=0, SiluMul=1 and opt-in SigmoidMul=2 operations supported')
        require(self.op != ElementwiseOp.SigmoidMul or enable_attention_sigmoid_mul,
                'attention SigmoidMul disabled; explicit opt-in required')
        width = {ElementwiseOp.Add: hidden_width, ElementwiseOp.SiluMul: ffn_width,
                 ElementwiseOp.SigmoidMul: attention_width}[self.op]
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

    Optional sigmoid_observer(index, fp32_word, bf16_word) sees the actual
    SigmoidMul boundary, using a flattened element index and a 16-bit BF16
    word. Optional silu_observer uses the same signature for the actual SiLU
    boundary before multiplication with up. Returns are ignored. The owner
    retains no observations, and reset preserves both observers and all
    explicit constructor parameters.
    """
    def __init__(self, scalar, *, hidden_width=HIDDEN_WIDTH, ffn_width=FFN_WIDTH,
                 test_geometry=False, attention_width=ATTENTION_WIDTH,
                 enable_attention_sigmoid_mul=False, sigmoid_observer=None, silu_observer=None):
        require(isinstance(scalar, ConvScalar), 'explicit caller-owned ConvScalar or PrepScalar required')
        _geometry(hidden_width, ffn_width, test_geometry, attention_width)
        require(type(enable_attention_sigmoid_mul) is bool, 'explicit attention SigmoidMul enable flag')
        require(sigmoid_observer is None or callable(sigmoid_observer), 'callable sigmoid observer required')
        require(silu_observer is None or callable(silu_observer), 'callable silu observer required')
        self.scalar = scalar
        self.hidden_width, self.ffn_width, self.test_geometry = hidden_width, ffn_width, test_geometry
        self.attention_width, self.enable_attention_sigmoid_mul = attention_width, enable_attention_sigmoid_mul
        self.sigmoid_observer = sigmoid_observer
        self.silu_observer = silu_observer
        self._parameter_binding = self._parameters()
        self._observer_binding = sigmoid_observer
        self._silu_observer_binding = silu_observer
        self.state, self.job, self.request, self.result = 'idle', None, None, None
        self._terminal_receipt = None
        self.program, self.poison, self.status = None, False, None
        self.ticks, self.start, self.sequence, self.ack_bytes = 0, 0, 0, 0
        self.counts, self.scalar_baseline, self.scalar_counts = Counter(), Counter(), Counter()
        self.exp_baseline, self.exp_counts = Counter(), Counter()
        self.identity, self.numerical_detail = None, None

    def _parameters(self):
        return (self.hidden_width, self.ffn_width, self.test_geometry,
                self.attention_width, self.enable_attention_sigmoid_mul)

    def _check_parameters(self):
        actual = self._parameters()
        require(len(actual) == len(self._parameter_binding) and
                all(type(a) is type(b) and a == b for a, b in zip(actual, self._parameter_binding)) and
                self.sigmoid_observer is self._observer_binding and
                self.silu_observer is self._silu_observer_binding, 'owner parameters changed after construction')

    def _validate_job(self, job):
        self._check_parameters()
        job.validate(self.hidden_width, self.ffn_width, self.test_geometry,
                     attention_width=self.attention_width,
                     enable_attention_sigmoid_mul=self.enable_attention_sigmoid_mul)

    def ports(self):
        self._check_parameters()
        return dict(job_ready=self.state == 'idle' and not self.poison and self.scalar.client is None,
                    memory=self.request if self.state == 'issue' else None,
                    memory_response_ready=self.state in ('wait', 'drain'),
                    response=self.result if self.state == 'finish' else None,
                    reset_required=self.poison, state=self.state)

    def reset(self):
        self._check_parameters()
        require(self.state in ('idle', 'locked') and self.request is None and self.scalar.client is not self,
                'reset requires drained transport and retired held completion')
        self.__init__(self.scalar, hidden_width=self.hidden_width, ffn_width=self.ffn_width,
                      test_geometry=self.test_geometry, attention_width=self.attention_width,
                      enable_attention_sigmoid_mul=self.enable_attention_sigmoid_mul,
                      sigmoid_observer=self.sigmoid_observer, silu_observer=self.silu_observer)

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
                        activation = 'SiLU' if j.op == ElementwiseOp.SiluMul else 'sigmoid'
                        raise UnsupportedGate('source ' + activation + ' gate requires finite x > -80')
                    exponential = self._op('exp_negative', x)
                    denominator = self._op('add', word(1), exponential)
                    inverse = self._op('div', word(1), denominator)
                    sigmoid = self._op('mul_ieee_rne', inverse, exponential if x >> 31 else word(1))
                    if j.op == ElementwiseOp.SigmoidMul:
                        activated = self._bf16(sigmoid)
                        # Observe actual scalar output and the consumed BF16
                        # boundary. Return values never enter computation; no
                        # observations or additional tensor buffers are retained.
                        if self.sigmoid_observer is not None:
                            self.sigmoid_observer(offset // 2 + lane, sigmoid, activated >> 16)
                    else:
                        silu = self._op('mul_ieee_rne', sigmoid, x)
                        activated = self._bf16(silu)
                        if self.silu_observer is not None:
                            self.silu_observer(offset // 2 + lane, silu, activated >> 16)
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
        # Retain the real immutable receipt, including its original metadata,
        # so the transport can reject substituted terminals before acceptance.
        self._terminal_receipt = (self.result, _field_binding(self.result))
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
            self._validate_job(job)
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
        self._check_parameters()
        active = self.state not in ('finish', 'idle', 'locked')
        return dict(scope='GDN_ELEMENTWISE_SOFTWARE_OWNER', identity=self.identity,
                    status=self.status, numerical_detail=self.numerical_detail,
                    accepted=dict(self.counts), acknowledged_write_bytes=self.ack_bytes,
                    scalar_calls=dict(self.scalar.calls - self.scalar_baseline if active else self.scalar_counts),
                    exp_internal_calls=dict(self.scalar.internal_calls - self.exp_baseline if active else self.exp_counts),
                    operation=None if self.job is None else ElementwiseOp(self.job.op).name,
                    hidden_width=self.hidden_width, ffn_width=self.ffn_width,
                    attention_width=self.attention_width,
                    enable_attention_sigmoid_mul=self.enable_attention_sigmoid_mul,
                    parameter_binding=self._parameter_binding,
                    production_geometry=(self.hidden_width, self.ffn_width, self.attention_width) ==
                        (HIDDEN_WIDTH, FFN_WIDTH, ATTENTION_WIDTH),
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
        owner._validate_job(job)
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
        self.parameter_binding = owner._parameter_binding
        self.source_hashes = tuple(sha(r.raw()) for r in self.sources)
        self._owner, self._memory, self._job = owner, memory, job
        self._scalar, self._regions = owner.scalar, memory.regions
        self._job_binding = _field_binding(job)
        self._sources, self._output = self.sources, self.output
        self._bindings = tuple((r, r.base, r.extent, r.storage, r.readonly)
                               for r in (*self.sources, self.output))
        self._source_hashes = self.source_hashes
        self._source_coverage = tuple((frozenset(r.written), frozenset(r.acknowledged))
                                      for r in self.sources)
        self._output_hash = hashlib.sha256()
        self.pending, self.response, self.aborted = None, None, False
        self.pending_request, self.pending_write = None, None
        self.counts = Counter()
        require(owner.tick(job=job)['job_fire'], 'elementwise admission rejected')
        self._source_identity = deepcopy(owner.identity)

    def preflight_response(self):
        """Return the validated held real terminal without accepting it.

        This is a read-only preparation boundary for a caller's final fence.
        It does not reserve success: tick rechecks before terminal acceptance.
        An integrity failure leaves the real terminal held and unpublished;
        it never fabricates a failure or cancels an accepted memory obligation.
        Restore trusted bindings before retry/drain when they were corrupted.
        Abort/reset can replace an unaccepted success with the owner's real
        failed receipt, but cannot repair lost physical transport obligations.
        """
        require(self.response is None, 'elementwise invocation already retired')
        require(self.owner is self._owner and self.memory is self._memory and
                self.owner.scalar is self._scalar and self.scalar_resource is self._scalar and
                self.memory.regions is self._regions, 'owner/memory/shared scalar resource replaced')
        self.owner._check_parameters()
        require(self.parameter_binding == self.owner._parameter_binding,
                'owner parameter binding replaced during invocation')
        require(self.job is self._job and self.owner.job is self._job and
                _field_binding(self.job) == self._job_binding, 'original immutable job changed')
        require(self.sources is self._sources and self.a is self._sources[0] and
                self.b is self._sources[1] and self.output is self._output,
                'typed source/output binding replaced')
        for region, base, extent, storage, readonly in self._bindings:
            require(self.memory.regions.get(base) is region and type(region.base) is int and
                    region.base == base and type(region.extent) is int and region.extent == extent and
                    region.storage is storage and len(storage) == extent + 128 and
                    type(region.readonly) is bool and region.readonly == readonly,
                    'physical region geometry or storage binding changed')
            require(self.memory._resolve(base, extent) is region, 'physical region allocation alias')
            region.check()
        require(self.source_hashes is self._source_hashes, 'source hash binding replaced')
        for region, coverage, digest in zip(self._sources, self._source_coverage, self._source_hashes):
            require(region.published is True and _same_coverage(region.written, coverage[0]) and
                    _same_coverage(region.acknowledged, coverage[1]) and
                    sha(memoryview(region.storage)[64:-64]) == digest,
                    'producer bytes changed or publication/data/ACK coverage changed')
        result = self.owner.ports()['response']
        receipt = self.owner._terminal_receipt
        require(type(result) is ElementwiseResult and receipt is not None and
                result is receipt[0] and _field_binding(result) == receipt[1],
                'original held real terminal required')
        require(self.pending is None and self.pending_request is None and self.pending_write is None and
                self.memory.pending is None and self.owner.request is None and self.owner.program is None,
                'terminal before transport drained')
        require(type(result.tag) is int and result.tag == self._job.tag and
                type(result.write_bytes) is int and
                result.write_bytes == self.owner.ack_bytes == self.counts['ack_bytes'] and
                0 <= result.write_bytes <= self._job.write_bytes and result.write_bytes % 64 == 0 and
                type(result.model_ticks) is int and result.model_ticks >= 0 and
                (result.status is None or type(result.status) is str and bool(result.status)) and
                result.status == self.owner.status and type(result.staging_complete) is bool and
                all(type(value) is bool and not value for value in
                    (result.state_committed, result.history_committed, result.generation_advanced)),
                'terminal tag/extent/stateless receipt changed')
        require(self._scalar.client is None, 'terminal retained the shared scalar')
        require(self.output.published is False, 'output published before accepted owner terminal')
        if result.status is None:
            require(not self.aborted and not self.owner.poison and result.staging_complete and
                    result.write_bytes == self.counts['write_bytes'] == self._job.write_bytes,
                    'complete stateless staging receipt required')
            coverage = set(range(0, self._job.write_bytes, 64))
            require(_same_coverage(self.output.written, coverage) and
                    _same_coverage(self.output.acknowledged, coverage),
                    'incomplete actual output data/ACK coverage')
            raw = memoryview(self.output.storage)[64:-64]
            require(hashlib.sha256(raw).digest() == self._output_hash.digest() and
                    all(finite(bits << 16) for (bits,) in struct.iter_unpack('<H', raw)),
                    'output differs from actual finite write data')
            require(self.owner.identity == self._source_identity == source_identity(),
                    'elementwise source changed during execution')
        else:
            require(not result.staging_complete and self.owner.poison,
                    'failed terminal cannot publish staging')
        return result

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             abort=False, reset=False, read_error=False, ack_error=False,
             read_tag=None, read_nbytes=None, ack_tag=None, ack_nbytes=None):
        require(self.response is None, 'elementwise invocation already retired')
        require(self.resource_identity == (id(self.owner), id(self.memory), id(self.owner.scalar)) and
                self.owner.scalar is self.scalar_resource, 'owner/memory/shared scalar resource replaced')
        self.owner._check_parameters()
        require(self.parameter_binding == self.owner._parameter_binding,
                'owner parameter binding replaced during invocation')
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
        # The owner's own abort/reset logic suppresses its pre-edge response.
        # Validate before tick can count/accept success, including ready-high
        # operation, while preserving that existing fault priority.
        if response_ready and not (abort_edge or reset) and self.owner.ports()['response'] is not None:
            self.preflight_response()
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
                if not malformed and not pending.error:
                    self.counts['ack_bytes'] += command.beats * 64
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
                self._output_hash.update(q.data)
                self.pending_write = (self.memory.pending, tuple(self.memory.pending))
                self.pending = MemoryResponse(q.tag)
                self.counts['write_bytes'] += 64
            else:
                require(any(region is r for r in self.sources), 'read escaped immutable inputs')
                self.pending = MemoryResponse(q.tag, self.memory.read64(q.address))
                self.counts['read_bytes'] += 64
        if e['response_fire']:
            self.response = e['response']
            if self.response.status is None:
                self.memory.publish(self.job.output, (self.response.tag, None, self.job.write_bytes))
        return e

    def report(self):
        return dict(owner=self.owner.report(), complete=self.response is not None,
                    status=None if self.response is None else self.response.status,
                    staging_complete=self.response is not None and self.response.staging_complete,
                    counts=dict(self.counts), output_published=self.output.published,
                    state_committed=False, history_committed=False, generation_advanced=False,
                    input_sha256=list(self.source_hashes), output_sha256=sha(self.output.raw()))
