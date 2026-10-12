"""Memory-fed C1 Norm256 and B1 partial64 RoPE, without executing RTL.

Each arithmetic operand comes from input memory or an earlier accepted scalar
result. Only integer primitive arithmetic, ROM constants and admission are
shared with the independent references. One injected scalar is held for the
job; the owners instantiate neither arithmetic nor memory resources. Ticks
describe software memory handshakes, not scalar latency or hardware cycles.
"""
from collections import Counter
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

from heteronpu.qk_norm256_candidate import (
    EPSILON, POLICY, RSQRT_COEFFICIENTS, admit,
)
from heteronpu.rope_bf16_candidate import bf16_convert
from ...qwen35_gdn_prefill.rms_owner import ArithmeticFault, MemoryResponse, finite
from ...qwen35_gdn_prefill.typed_dense import FULL_MASK
from .scalar import FATAL_FLAGS, NormRopeScalar, RawScalarResult


BEAT_BYTES, HEAD_DIM, HEAD_BYTES = 64, 256, 512
ROPE_POLICY, ROTARY_DIM = 0xB1, 64
TORCH_DEFAULT256_POLICY = 0xC2
ROOT = Path(__file__).resolve().parents[3]
SOURCE_SHA256 = {
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QkNorm256Owner.scala':
        'c12183ddb29ab3ce66dc59083524c204f55554757218ced438c8f8ae4c7d60b6',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/PartialRope64Owner.scala':
        '7a3f5bffe06772671f30ac1484065afae9abc895063a2e4769999bf76487c322',
    'src/heteronpu/qk_norm256_candidate.py':
        '1307cfd77b105fea758e0e434caab35db908739cc8bdfa0c3857306820532f06',
    'src/heteronpu/rope_bf16_candidate.py':
        'fa647411e2c9f33c58c0b8c62d14063ebe249b199a8fcbc2c0d2cc645ff10bfd',
}


def require(ok, detail):
    if not ok:
        raise ValueError('typed Norm/RoPE: ' + detail)


def source_identity(root=ROOT, *, policy=POLICY):
    require(type(policy) is int and policy in (POLICY, TORCH_DEFAULT256_POLICY), 'source policy identity')
    for name, expected in SOURCE_SHA256.items():
        require(hashlib.sha256((Path(root) / name).read_bytes()).hexdigest() == expected,
                'frozen recipe source drift: ' + name)
    return dict(source_sha256=dict(SOURCE_SHA256), rtl_executed=False,
                hardware_cycles=None, native_acceptance=False, norm_policy=policy,
                production_chisel_policy_implemented=policy == POLICY,
                current_chisel_source_policy=POLICY,
                c2_div_sqrt_flags='unobserved; existing result/error' if policy == TORCH_DEFAULT256_POLICY else None)


def _uint(value, bits):
    return type(value) is int and 0 <= value < 1 << bits


def _spans(inputs, outputs):
    spans = (*inputs, *outputs)
    for base, extent in spans:
        require(_uint(base, 56) and base % BEAT_BYTES == 0 and
                type(extent) is int and extent > 0 and extent % BEAT_BYTES == 0 and
                base + extent <= 1 << 56, 'aligned nonempty 56-bit physical span')
    # Read-only input alias does not endanger the Chisel owner; writes must be
    # disjoint from every input and every other destination.
    for index, (base, extent) in enumerate(outputs):
        require(all(base + extent <= other or other + size <= base
                    for other, size in (*inputs, *outputs[:index])), 'output span alias')


@dataclass(frozen=True)
class QkNorm256Job:
    tag: int
    input: int
    weight: int
    output: int
    tokens: int
    role: int = 0
    gate_output: int = 0
    head_dim: int = HEAD_DIM
    policy: int = POLICY
    epsilon: int = EPSILON
    dtype: str = 'bf16'

    @property
    def heads(self):
        return 8 if self.role == 0 else 2

    @property
    def vector_bytes(self):
        return self.tokens * self.heads * HEAD_BYTES

    @property
    def input_bytes(self):
        return self.vector_bytes * (2 if self.role == 0 else 1)

    @property
    def write_bytes(self):
        return self.input_bytes

    @property
    def output_spans(self):
        norm = ((self.output, self.vector_bytes),)
        return norm + ((self.gate_output, self.vector_bytes),) if self.role == 0 else norm

    def validate(self):
        require(_uint(self.tag, 32), 'job tag domain')
        require(type(self.tokens) is int and 1 <= self.tokens <= 128 and
                type(self.role) is int and self.role in (0, 1), 'M1..128 and Q0/K1 required')
        require(type(self.head_dim) is int and self.head_dim == HEAD_DIM and
                type(self.policy) is int and self.policy in (POLICY, TORCH_DEFAULT256_POLICY) and
                type(self.epsilon) is int and self.epsilon == EPSILON and
                type(self.dtype) is str and self.dtype == 'bf16', 'C1/C2 BF16 H256/epsilon descriptor')
        require(_uint(self.gate_output, 56) and (self.role == 0 or self.gate_output == 0),
                'K gate_output must be zero')
        _spans(((self.input, self.input_bytes), (self.weight, HEAD_BYTES)), self.output_spans)


@dataclass(frozen=True)
class PartialRope64Job:
    tag: int
    input: int
    trig: int
    output: int
    tokens: int
    heads: int
    position_base: int
    trig_tokens: int
    head_dim: int = HEAD_DIM
    rotary_dim: int = ROTARY_DIM
    policy: int = ROPE_POLICY
    dtype: str = 'bf16'

    @property
    def write_bytes(self):
        return self.tokens * self.heads * HEAD_BYTES

    @property
    def input_bytes(self):
        return self.write_bytes

    @property
    def trig_bytes(self):
        return self.trig_tokens * 128

    @property
    def output_spans(self):
        return ((self.output, self.write_bytes),)

    def validate(self):
        require(_uint(self.tag, 32), 'job tag domain')
        require(type(self.tokens) is int and 1 <= self.tokens <= 128 and
                type(self.heads) is int and 1 <= self.heads <= 8, 'M1..128 and heads1..8 required')
        require(type(self.head_dim) is int and self.head_dim == HEAD_DIM and
                type(self.rotary_dim) is int and self.rotary_dim == ROTARY_DIM and
                type(self.policy) is int and self.policy == ROPE_POLICY and
                type(self.dtype) is str and self.dtype == 'bf16', 'B1 BF16 partial64/H256 descriptor')
        require(_uint(self.position_base, 32) and _uint(self.trig_tokens, 32) and
                self.position_base + self.tokens <= self.trig_tokens, 'absolute trig position range')
        _spans(((self.input, self.input_bytes), (self.trig, self.trig_bytes)), self.output_spans)


@dataclass(frozen=True)
class MemoryRequest:
    address: int
    tag: int
    data: bytes | None = None

    @property
    def write(self):
        return self.data is not None

    @property
    def mask(self):
        return FULL_MASK if self.write else 0

    @property
    def nbytes(self):
        return BEAT_BYTES


@dataclass(frozen=True)
class PartialRope64Result:
    tag: int
    status: str | None
    write_bytes: int
    model_ticks: int
    exception_flags: int


@dataclass(frozen=True)
class QkNorm256Result(PartialRope64Result):
    norm_status: int
    last_mean_eps: int
    last_inverse: int


class _Fault(Exception):
    def __init__(self, status, norm_status=0):
        self.status, self.norm_status = status, norm_status


class _Owner:
    """Single outstanding full beat, drain on abort, held terminal on failure.

    ACK counts expose raw accepted transport only. The caller publishes all
    output spans atomically after accepting a successful terminal response.
    Explicit software abort may cancel a held success before that acceptance,
    including a simultaneous ready edge. This sideband extension is not a
    Chisel abort-port equivalence claim. Ordinary backpressure holds payloads.
    """
    def __init__(self, scalar, observer=None):
        require(isinstance(scalar, NormRopeScalar), 'caller-owned raw-flag shared scalar required')
        require(observer is None or callable(observer), 'optional read-only observer callback')
        self.scalar, self.observer = scalar, observer
        self.state, self.job, self.request, self.result = 'idle', None, None, None
        self.program, self.poison, self.status = None, False, None
        self.ticks, self.start, self.sequence, self.ack_bytes = 0, 0, 0, 0
        self.exception_flags, self.norm_status, self.last_mean_eps, self.last_inverse = 0, 0, 0, 0
        self.counts, self.scalar_baseline, self.scalar_counts = Counter(), Counter(), Counter()
        self.head_scalars = []

    def ports(self):
        return dict(job_ready=self.state == 'idle' and not self.poison and self.scalar.client is None,
                    memory=self.request if self.state == 'issue' else None,
                    memory_response_ready=self.state in ('wait', 'drain'),
                    response=self.result if self.state == 'finish' else None,
                    reset_required=self.poison, state=self.state)

    def reset(self):
        require(self.state in ('idle', 'locked') and self.request is None and self.scalar.client is not self,
                'reset requires drained transport and retired held completion')
        self.__init__(self.scalar, self.observer)

    def _observe(self, stage, token, head, words):
        """Send immutable actual-node snapshots; callback return is ignored.

        These optional per-head buffers are host observability storage, never
        inferred hardware registers or physical resource evidence. A callback
        exception fails the software invocation before success/publication.
        """
        if self.observer is not None:
            snapshot = tuple(words)
            require(all(_uint(word, 32) for word in snapshot), 'observer FP32 raw-word snapshot')
            try:
                self.observer(stage, token, head, snapshot)
            except Exception as error:
                raise _Fault('Observer') from error

    def _op(self, operation, a, b, *, convert=False):
        result = self.scalar.raw_op(self, operation, a, b)
        if (type(result) is not RawScalarResult or not _uint(result.bits, 32) or
                not _uint(result.flags, 5) or type(result.error) is not bool or
                type(result.flags_valid) is not bool or not result.flags_valid):
            raise _Fault('Protocol')
        bits, flags = result.bits, result.flags
        if convert:
            bits, conversion_flags = bf16_convert(bits)
            flags |= conversion_flags
        self.exception_flags |= flags
        if result.error or flags & FATAL_FLAGS or not finite(result.bits) or not finite(bits):
            raise _Fault('Numerical', 4)
        return bits

    def _convert(self, bits):
        rounded, flags = bf16_convert(bits)
        self.exception_flags |= flags
        if flags & FATAL_FLAGS or not finite(rounded):
            raise _Fault('Numerical', 4)
        return rounded

    def _unflagged_op(self, operation, a, b=0):
        # Existing shared Div2/Sqrt3 expose result/error, not raw flagsValid.
        # Do not invent flags or weaken the C1/Add0/Mul1 raw-flag checks.
        require(operation in ('sqrt', 'div') and self.job.policy == TORCH_DEFAULT256_POLICY,
                'unflagged Div/Sqrt only in explicit C2 policy')
        try:
            bits = self.scalar.op(self, operation, a, b)
        except ArithmeticFault as error:
            raise _Fault('Numerical', 4) from error
        if not _uint(bits, 32):
            raise _Fault('Protocol')
        if not finite(bits):
            raise _Fault('Numerical', 4)
        return bits

    def _read(self, base, count, *, finite_beats=0):
        raw = bytearray()
        for beat in range(count):
            packet = yield base + beat * BEAT_BYTES, None
            if beat < finite_beats and any(not finite(v << 16) for v in struct.unpack('<32H', packet)):
                raise _Fault('Numerical')
            raw.extend(packet)
        return bytes(raw)

    def _write(self, base, raw):
        require(type(raw) is bytes and len(raw) % BEAT_BYTES == 0, 'full native output beats')
        for offset in range(0, len(raw), BEAT_BYTES):
            yield base + offset, raw[offset:offset + BEAT_BYTES]

    def _finish(self, status=None):
        self.status = status
        self.poison |= status is not None
        if self.scalar.client is self:
            self.scalar_counts = self.scalar.calls - self.scalar_baseline
            self.scalar.release(self)
        self.request, self.program = None, None
        values = (self.job.tag, status, self.ack_bytes, self.ticks - self.start, self.exception_flags)
        self.result = (QkNorm256Result(*values, self.norm_status, self.last_mean_eps, self.last_inverse)
                       if type(self.job) is QkNorm256Job else PartialRope64Result(*values))
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
        except _Fault as error:
            self.norm_status = error.norm_status
            self._finish(error.status)
        except ArithmeticFault:
            self.norm_status = 4
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
            raise ValueError('typed Norm/RoPE: reset cannot erase a held completion')
        fault = abort or reset
        if fault:
            p['job_ready'], p['memory'] = False, None
            self.poison = True
            if self.state in ('wait', 'drain'):
                self.status, self.state = 'Aborted', 'drain'
            elif self.state == 'issue':
                self._finish('Aborted')
            elif self.state == 'finish' and self.status is None:
                # Sideband cancellation wins over accepting a held success.
                # A failed/Aborted terminal stays stable on repeated aborts.
                self._finish('Aborted')
                p['response'] = None
            elif self.state == 'idle':
                self.state = 'locked'
        if not fault and job is not None and p['job_ready']:
            require(type(job) is self.job_type, 'typed immutable owner job required')
            job.validate()
            require(self.scalar.acquire(self), 'shared scalar acquisition')
            p['job_fire'] = True
            self.job, self.start = job, self.ticks
            self.sequence, self.ack_bytes, self.status = 0, 0, None
            self.exception_flags, self.norm_status, self.last_mean_eps, self.last_inverse = 0, 0, 0, 0
            self.counts, self.scalar_baseline, self.scalar_counts = Counter(), self.scalar.calls.copy(), Counter()
            self.head_scalars = []
            self.program = self._compute(job)
            self._advance()
        if not fault and p['memory'] is not None and memory_ready:
            p['memory_fire'] = True
            self.counts['write_requests' if self.request.write else 'read_requests'] += 1
            self.state = 'wait'
        if p['memory_response_ready'] and memory_response is not None:
            p['memory_response_fire'] = True
            q, r = self.request, memory_response
            require(type(r) is MemoryResponse, 'typed memory response required')
            self.counts['memory_responses'] += 1
            bad = (type(r.tag) is not int or r.tag != q.tag or type(r.nbytes) is not int or
                   r.nbytes != BEAT_BYTES or type(r.error) is not bool)
            status = 'Protocol' if bad else 'Memory' if r.error else None
            if q.write and status is None:
                self.ack_bytes += BEAT_BYTES
                self.counts['write_acks'] += 1
            if self.state == 'drain':
                self._finish(self.status)
            elif status is not None:
                self._finish(status)
            elif q.write:
                self._advance()
            elif type(r.data) is not bytes or len(r.data) != BEAT_BYTES:
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
        return dict(scope=self.scope, status=self.status, accepted=dict(self.counts),
                    policy=None if self.job is None else self.job.policy,
                    acknowledged_write_bytes=self.ack_bytes, exception_flags=self.exception_flags,
                    norm_status=self.norm_status, last_mean_eps=self.last_mean_eps, last_inverse=self.last_inverse,
                    scalar_calls=dict(self.scalar_counts if self.state in ('finish', 'idle', 'locked')
                                      else self.scalar.calls - self.scalar_baseline),
                    head_scalars=list(self.head_scalars), hardware_cycles=None, rtl_executed=False,
                    software_abort_contract='cancel_until_terminal_acceptance',
                    software_observer_enabled=self.observer is not None,
                    observer_buffers_are_hardware_resources=False,
                    physical_bank_allocation_proven=False, native_acceptance=False)


class QkNorm256Owner(_Owner):
    job_type = QkNorm256Job
    scope = 'PACKED_BF16_EXPLICIT_POLICY_QK_NORM256_SOFTWARE_OWNER'

    def _compute(self, j):
        raw_weight = yield from self._read(j.weight, 8)
        weights = tuple(v << 16 for v in struct.unpack('<256H', raw_weight))
        for token in range(j.tokens):
            for head in range(j.heads):
                row = token * j.heads + head
                raw = yield from self._read(j.input + row * (1024 if j.role == 0 else 512),
                                            16 if j.role == 0 else 8)
                x = tuple(v << 16 for v in struct.unpack('<256H', raw[:HEAD_BYTES]))
                # Descriptor policy was checked at admission. Both policies
                # deliberately retain the frozen C1 finite operand domain.
                admission = admit(x, weights, policy=POLICY, role=j.role,
                                  head_dim=j.head_dim, epsilon=j.epsilon)
                if admission:
                    raise _Fault('Numerical', admission)
                squares = [0] * 256 if self.observer is not None else None
                total = 0
                if j.policy == TORCH_DEFAULT256_POLICY:
                    # Torch 2.10 CPU DEFAULT V8/ILP4, H256. The serial owner
                    # reads the existing head buffer in this order; the host
                    # observer alone retains the full square tensor.
                    for lane in range(8):
                        lane_sum = None
                        for residue in range(4):
                            partial = 0
                            for term in range(8):
                                index = 32 * term + 8 * residue + lane
                                square = self._op('mul', x[index], x[index])
                                if squares is not None:
                                    squares[index] = square
                                partial = self._op('add', partial, square)
                            lane_sum = partial if lane_sum is None else self._op('add', lane_sum, partial)
                        total = self._op('add', total, lane_sum)
                else:
                    for chunk in range(16):
                        level = [self._op('mul', v, v) for v in x[chunk * 16:(chunk + 1) * 16]]
                        if squares is not None:
                            squares[chunk * 16:(chunk + 1) * 16] = level
                        while len(level) > 1:
                            level = [self._op('add', level[i], level[i + 1]) for i in range(0, len(level), 2)]
                        total = self._op('add', total, level[0])
                if squares is not None:
                    self._observe('squares', token, head, squares)
                self._observe('sum', token, head, (total,))
                mean = self._op('mul', total, 0x3B800000)
                self._observe('mean', token, head, (mean,))
                mean_eps = self._op('add', mean, j.epsilon)
                self.last_mean_eps = mean_eps
                self._observe('mean_eps', token, head, (mean_eps,))
                exponent = (mean_eps >> 23) & 255
                if mean_eps >> 31 or not 2 <= exponent <= 253:
                    raise _Fault('Numerical', 4)
                if j.policy == TORCH_DEFAULT256_POLICY:
                    root = self._unflagged_op('sqrt', mean_eps)
                    inverse = self._unflagged_op('div', 0x3F800000, root)
                else:
                    e = exponent - 127
                    odd = e & 1
                    normalized = ((128 if odd else 127) << 23) | (mean_eps & 0x7FFFFF)
                    scale = ((127 - ((e - odd) // 2)) & 255) << 23
                    coefficient = RSQRT_COEFFICIENTS[(odd << 4) | ((mean_eps >> 19) & 15)]
                    slope = self._op('mul', coefficient >> 32, normalized)
                    seed = self._op('add', slope, coefficient & 0xFFFFFFFF)
                    square = self._op('mul', seed, seed)
                    product = self._op('mul', normalized, square)
                    half = self._op('mul', 0x3F000000, product)
                    term = self._op('add', 0x3FC00000, half ^ 0x80000000)
                    refined = self._op('mul', seed, term)
                    inverse = self._op('mul', refined, scale)
                self.last_inverse = inverse
                if inverse >> 31 or not 1 <= ((inverse >> 23) & 255) <= 254:
                    raise _Fault('Numerical', 4)
                self._observe('inverse', token, head, (inverse,))
                self.head_scalars.append(dict(token=token, head=head, sum=total, mean=mean,
                                              mean_eps=mean_eps, inverse=inverse))
                output = []
                gamma_words, scaled_words, weighted_words = (([], [], []) if self.observer is not None
                                                             else (None, None, None))
                for value, weight in zip(x, weights):
                    gamma = self._op('add', 0x3F800000, weight)
                    scaled = self._op('mul', value, inverse)
                    weighted = self._op('mul', scaled, gamma)
                    output.append(self._convert(weighted) >> 16)
                    if gamma_words is not None:
                        gamma_words.append(gamma)
                        scaled_words.append(scaled)
                        weighted_words.append(weighted)
                if gamma_words is not None:
                    self._observe('gamma', token, head, gamma_words)
                    self._observe('scaled', token, head, scaled_words)
                    self._observe('weighted', token, head, weighted_words)
                    self._observe('output', token, head, (v << 16 for v in output))
                yield from self._write(j.output + row * HEAD_BYTES, struct.pack('<256H', *output))
                if j.role == 0:
                    yield from self._write(j.gate_output + row * HEAD_BYTES, raw[HEAD_BYTES:])


class PartialRope64Owner(_Owner):
    job_type = PartialRope64Job
    scope = 'PACKED_BF16_B1_PARTIAL64_ROPE_SOFTWARE_OWNER'

    def _compute(self, j):
        for token in range(j.tokens):
            trig = yield from self._read(j.trig + (j.position_base + token) * 128, 2, finite_beats=2)
            coefficients = tuple(v << 16 for v in struct.unpack('<64H', trig))
            for head in range(j.heads):
                row = token * j.heads + head
                raw = yield from self._read(j.input + row * HEAD_BYTES, 8, finite_beats=2)
                words = struct.unpack('<256H', raw)
                output = list(words)
                cos_products = [0] * 64 if self.observer is not None else None
                sin_products = [0] * 64 if self.observer is not None else None
                for pair in range(32):
                    even, odd = words[pair] << 16, words[pair + 32] << 16
                    cos, sin = coefficients[pair], coefficients[pair + 32]
                    ec = self._op('mul', even, cos, convert=True)
                    os = self._op('mul', odd, sin, convert=True)
                    es = self._op('mul', even, sin, convert=True)
                    oc = self._op('mul', odd, cos, convert=True)
                    if cos_products is not None:
                        cos_products[pair], cos_products[pair + 32] = ec, oc
                        sin_products[pair], sin_products[pair + 32] = os ^ 0x80000000, es
                    output[pair] = self._op('add', ec, os ^ 0x80000000, convert=True) >> 16
                    output[pair + 32] = self._op('add', es, oc, convert=True) >> 16
                if cos_products is not None:
                    self._observe('cos_product', token, head, cos_products)
                    self._observe('sin_product', token, head, sin_products)
                    self._observe('rotated', token, head, (v << 16 for v in output[:64]))
                    self._observe('output', token, head, (v << 16 for v in output))
                yield from self._write(j.output + row * HEAD_BYTES, struct.pack('<256H', *output))
