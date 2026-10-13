"""Memory-fed H1024 packed-BF16 RMS owner; software transactions, not RTL.

Both policies keep every arithmetic node FP32 and only the final BF16 RNE.
Scalar calls are synchronous software events, not a hardware latency model.
One retained input row, weight row and output row are sufficient. No oracle
array feeds this owner and no existing Qwen2 4-byte wire policy is inherited.
"""
from collections import Counter
import ctypes
from dataclasses import dataclass
from enum import Enum
import hashlib
from pathlib import Path
import struct
import subprocess

import numpy as np

from .typed_dense import TypedMemory, FULL_MASK
from ..qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck

ROOT = Path(__file__).resolve().parents[2]
OWNER_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnRmsNormOwner.scala'
LEGACY_SHA = '77beb04c0646eee8f53b8c44190f641f4efc900f552523ab6b0cc4f7aed8a065'
CANDIDATE_SHA = '850f31afbee6c53b65fc3463082cd32aa8dced47cfdb665a001d1269387c87ca'
RECIPE_SOURCE = 'chisel/continuous_prefill/scripts/gdn_rmsnorm_reference.py'
RECIPE_SHA = 'd84da5a66d42251f4e9ec88696a6573bf30ea03ba4ca4abf8f5e7005075d304b'
SCALAR_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala'
SCALAR_SHA = '9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5'
WIDTH, ROW_BYTES, BEAT_BYTES = 1024, 2048, 64


def require(ok, detail):
    if not ok:
        raise ValueError('typed RMS: ' + detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ReductionPolicy(str, Enum):
    LegacyAscending = 'legacy_ascending'
    Torch210CpuDefault1024 = 'torch210_cpu_default1024'


def source_identity(policy, root=ROOT):
    """Committed legacy identity; the Torch formula is a new model-only policy.

    The original dirty candidate is associated evidence only. It is neither
    imported nor required in clean CI and supplies no inherited pass result.
    """
    policy, root = ReductionPolicy(policy), Path(root)
    require(sha((root / SCALAR_SOURCE).read_bytes()) == SCALAR_SHA, 'shared scalar source drift')
    original = subprocess.run(['git', 'show', 'HEAD:' + OWNER_SOURCE], cwd=root,
                              check=True, capture_output=True, timeout=10).stdout
    require(sha(original) == LEGACY_SHA, 'committed LegacyAscending source drift')
    sources = {'HEAD:' + OWNER_SOURCE: LEGACY_SHA}
    sources[SCALAR_SOURCE] = SCALAR_SHA
    return dict(policy=policy.value, source_sha256=sources,
                implementation_sha256=sha(Path(__file__).read_bytes()),
                torch_policy_model_only=policy == ReductionPolicy.Torch210CpuDefault1024,
                associated_candidate_hashes={OWNER_SOURCE: CANDIDATE_SHA, RECIPE_SOURCE: RECIPE_SHA},
                candidate_mapping_verified=False,
                historical_m1_pass_inherited=False, native_acceptance=False, rtl_executed=False)


def verify_candidate_mapping(root=ROOT):
    """Optional local source association; never required to execute either policy."""
    expected = {OWNER_SOURCE: CANDIDATE_SHA, RECIPE_SOURCE: RECIPE_SHA}
    for name, digest in expected.items():
        require(sha((Path(root) / name).read_bytes()) == digest, 'candidate association drift: ' + name)
    return dict(source_sha256=expected, source_association_only=True, historical_m1_pass_inherited=False)


def word(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def value(bits):
    return np.float32(struct.unpack('<f', struct.pack('<I', bits))[0])


def finite(bits):
    return bits & 0x7f800000 != 0x7f800000


class ArithmeticFault(Exception):
    pass


class _ObserverFault(Exception):
    pass


def _tiny_inexact(operation, a, b, result):
    if result & 0x7f800000:
        return False
    an, ad = float(value(a)).as_integer_ratio()
    bn, bd = float(value(b)).as_integer_ratio()
    rn, rd = float(value(result)).as_integer_ratio()
    if operation == 'add':
        return (an * bd + bn * ad) * rd != rn * ad * bd
    if operation == 'div':
        return an * bd * rd != rn * ad * bn
    if operation == 'sqrt':
        return rn * rn * ad != an * rd * rd
    raise ValueError('unexpected legacy scalar operation')


class SharedScalar:
    """Exclusive FP32 service: explicit op6 multiply; Add/Div/Sqrt legacy faults.

    This deliberately has no vector-policy escape. MulIeeeRne accepts rounded
    finite underflow/inexact, while invalid/overflow/nonfinite stay fatal.
    """
    def __init__(self):
        self.client, self.calls = None, Counter()
        libc = ctypes.CDLL(None)
        libc.fegetround.restype = ctypes.c_int
        require(libc.fegetround() == 0, 'FE_TONEAREST required')
        with np.errstate(all='ignore'):
            require(word(np.add(value(1), value(1), dtype=np.float32)) == 2 and
                    word(np.multiply(value(0x00800000), value(0x3f000000), dtype=np.float32)) == 0x00400000 and
                    word(np.add(value(0x80000000), value(0x80000000), dtype=np.float32)) == 0x80000000,
                    'FP32 gradual-underflow/signed-zero environment')

    def acquire(self, client):
        if self.client is not None:
            return False
        self.client = client
        return True

    def release(self, client):
        require(self.client is client, 'wrong shared scalar release')
        self.client = None

    def op(self, client, operation, a, b=0):
        require(self.client is client, 'arithmetic without exclusive scalar ownership')
        require(operation in ('add', 'mul_ieee_rne', 'div', 'sqrt'), 'explicit scalar opcode required')
        require(all(type(v) is int and 0 <= v < 1 << 32 for v in (a, b)), 'FP32 raw-word domain')
        self.calls[operation] += 1
        if not finite(a) or not finite(b):
            raise ArithmeticFault('nonfinite scalar input')
        with np.errstate(all='ignore'):
            x, y = value(a), value(b)
            result = {'add': np.add, 'mul_ieee_rne': np.multiply, 'div': np.divide}.get(operation)
            bits = word(np.sqrt(x, dtype=np.float32) if operation == 'sqrt' else result(x, y, dtype=np.float32))
        if not finite(bits):
            raise ArithmeticFault('invalid/div0/overflow/nonfinite scalar result')
        if operation != 'mul_ieee_rne' and _tiny_inexact(operation, a, b, bits):
            raise ArithmeticFault('legacy scalar rejects inexact underflow')
        return bits


@dataclass(frozen=True)
class RmsJob:
    tag: int
    input: int
    weight: int
    output: int
    tokens: int
    policy: ReductionPolicy = ReductionPolicy.LegacyAscending
    width: int = WIDTH

    @property
    def write_bytes(self):
        return self.tokens * ROW_BYTES

    def validate(self):
        require(type(self.tag) is int and 0 <= self.tag < 1 << 32, 'job tag domain')
        require(type(self.tokens) is int and 1 <= self.tokens <= 128 and
                type(self.width) is int and self.width == WIDTH, 'BF16 H1024/M1..128 required')
        ReductionPolicy(self.policy)
        spans = ((self.input, self.write_bytes), (self.weight, ROW_BYTES), (self.output, self.write_bytes))
        for base, extent in spans:
            require(type(base) is int and 0 <= base and base % 64 == 0 and base + extent <= 1 << 56,
                    'aligned 56-bit physical span required')
        require(all(a + n <= b or b + m <= a for i, (a, n) in enumerate(spans) for b, m in spans[:i]),
                'input, weight and output spans must be disjoint')


@dataclass(frozen=True)
class MemoryRequest:
    address: int
    tag: int
    data: bytes | None = None

    @property
    def write(self):
        return self.data is not None


@dataclass(frozen=True)
class MemoryResponse:
    tag: int
    data: bytes | None = None
    error: bool = False
    nbytes: int = BEAT_BYTES


@dataclass(frozen=True)
class RmsResult:
    tag: int
    status: str | None
    write_bytes: int
    model_ticks: int


class RmsOwner:
    """One outstanding 64-byte request and one held terminal per accepted job.

    Optional observer(stage, token, words) receives immutable tuples of actual
    FP32 raw uint32 nodes: squares, sum, mean, mean_eps, inverse, scaled, gamma,
    weighted and output. Vectors use original lane order; output contains the
    rounded BF16 words promoted into FP32 bit positions. Observer return values
    are ignored. Snapshot buffers/callback copies are host-only observability,
    not added hardware storage, arithmetic resources or latency evidence.

    Callbacks run synchronously during compute, after the input read response
    retires and before that row's writes. Exceptions produce an Observer error
    terminal and poison admission through the existing completion/reset path.
    Earlier rows may already have acknowledged writes, but no output publishes.
    This is not a general callback sandbox or an asynchronous transport drain;
    callbacks must not mutate owner, scalar or memory through outside references.
    """
    def __init__(self, scalar=None, observer=None):
        self.scalar = SharedScalar() if scalar is None else scalar
        require(isinstance(self.scalar, SharedScalar), 'explicit shared scalar service required')
        require(observer is None or callable(observer), 'optional host observer callback')
        self.observer = observer
        self.state, self.job, self.request, self.result = 'idle', None, None, None
        self.program, self.poison, self.status = None, False, None
        self.ticks, self.start, self.sequence, self.ack_bytes = 0, 0, 0, 0
        self.counts, self.scalar_baseline, self.scalar_counts = Counter(), Counter(), Counter()
        self.identity, self.row_scalars = None, []

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

    def _observe(self, stage, token, words):
        if self.observer is not None:
            snapshot = tuple(words)
            require(all(type(bits) is int and 0 <= bits < 1 << 32 for bits in snapshot),
                    'observer FP32 raw-word snapshot')
            try:
                self.observer(stage, token, snapshot)
            except Exception as error:
                raise _ObserverFault() from error

    def _op(self, operation, a, b=0):
        return self.scalar.op(self, operation, a, b)

    def _read_row(self, base):
        row = []
        for offset in range(0, ROW_BYTES, BEAT_BYTES):
            raw = yield (base + offset, None)
            packet = struct.unpack('<32H', raw)
            if any(not finite(x << 16) for x in packet):
                raise ArithmeticFault('nonfinite BF16 input/weight')
            row.extend(packet)
        return row

    def _compute(self, j):
        weight = yield from self._read_row(j.weight)
        for token in range(j.tokens):
            row = yield from self._read_row(j.input + token * ROW_BYTES)
            squares = [0] * WIDTH if self.observer is not None else None
            total = 0
            if ReductionPolicy(j.policy) == ReductionPolicy.LegacyAscending:
                for index, x in enumerate(row):
                    square = self._op('mul_ieee_rne', x << 16, x << 16)
                    if squares is not None:
                        squares[index] = square
                    total = self._op('add', total, square)
            else:
                for lane in range(8):
                    lane_total = 0
                    for residue in range(4):
                        residue_total = 0
                        for block in range(2):
                            block_total = 0
                            for term in range(16):
                                index = 512 * block + 32 * term + 8 * residue + lane
                                x = row[index] << 16
                                square = self._op('mul_ieee_rne', x, x)
                                if squares is not None:
                                    squares[index] = square
                                block_total = self._op('add', block_total, square)
                            residue_total = self._op('add', residue_total, block_total)
                        lane_total = self._op('add', lane_total, residue_total)
                    total = self._op('add', total, lane_total)
            if squares is not None:
                self._observe('squares', token, squares)
            self._observe('sum', token, (total,))
            mean = self._op('mul_ieee_rne', total, word(1 / WIDTH))
            self._observe('mean', token, (mean,))
            variance = self._op('add', mean, word(1e-6))
            self._observe('mean_eps', token, (variance,))
            root = self._op('sqrt', variance)
            inverse = self._op('div', word(1), root)
            self._observe('inverse', token, (inverse,))
            self.row_scalars.append(dict(token=token, sum=total, mean=mean, variance=variance, root=root, inverse=inverse))
            output = []
            scaled_words, gamma_words, weighted_words = (([], [], []) if self.observer is not None
                                                         else (None, None, None))
            for x, w in zip(row, weight):
                normalized = self._op('mul_ieee_rne', x << 16, inverse)
                scale = self._op('add', word(1), w << 16)
                weighted = self._op('mul_ieee_rne', normalized, scale)
                rounded = ((weighted + 0x7fff + ((weighted >> 16) & 1)) & 0xffffffff) >> 16
                if not finite(rounded << 16):
                    raise ArithmeticFault('terminal BF16 conversion overflow')
                output.append(rounded)
                if scaled_words is not None:
                    scaled_words.append(normalized)
                    gamma_words.append(scale)
                    weighted_words.append(weighted)
            if scaled_words is not None:
                self._observe('scaled', token, scaled_words)
                self._observe('gamma', token, gamma_words)
                self._observe('weighted', token, weighted_words)
                self._observe('output', token, (bits << 16 for bits in output))
            for offset in range(0, WIDTH, 32):
                yield (j.output + token * ROW_BYTES + offset * 2, struct.pack('<32H', *output[offset:offset + 32]))

    def _finish(self, status=None):
        self.status = status
        self.poison |= status is not None
        if self.scalar.client is self:
            self.scalar_counts = self.scalar.calls - self.scalar_baseline
            self.scalar.release(self)
        self.request, self.program = None, None
        self.result = RmsResult(self.job.tag, status, self.ack_bytes, self.ticks - self.start)
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
        except ArithmeticFault:
            self._finish('Numerical')
        except _ObserverFault:
            self._finish('Observer')

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
            raise ValueError('typed RMS: reset cannot erase a held completion')
        fault = abort or reset
        if fault:
            p['job_ready'], p['memory'] = False, None
            self.poison = True
            if self.state in ('wait', 'drain'):
                self.status, self.state = 'Aborted', 'drain'
            elif self.state == 'issue':
                self._finish('Aborted')
            elif self.state == 'finish':
                self._finish('Aborted')
                p['response'] = None
            elif self.state == 'idle':
                self.state = 'locked'
        if not fault and job is not None and p['job_ready']:
            require(type(job) is RmsJob, 'typed immutable RMS job required')
            job.validate()
            identity = source_identity(job.policy)
            require(self.scalar.acquire(self), 'shared scalar acquisition')
            p['job_fire'] = True
            self.job, self.start, self.identity = job, self.ticks, identity
            self.sequence, self.ack_bytes, self.status = 0, 0, None
            self.counts, self.scalar_baseline, self.scalar_counts = Counter(), self.scalar.calls.copy(), Counter()
            self.row_scalars = []
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
            bad_identity = (type(r.tag) is not int or r.tag != q.tag or
                            type(r.nbytes) is not int or r.nbytes != BEAT_BYTES or type(r.error) is not bool)
            status = 'Protocol' if bad_identity else 'Memory' if r.error else None
            # Exactly one physical response is in flight. Like the source
            # GdnRmsNormOwner, an accepted bad-tag reply retires that obligation
            # and fails the owner. Unrelated-response filtering belongs before
            # this interface and is not silently invented inside the owner.
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
        return dict(scope='PACKED_BF16_H1024_RMS_SOFTWARE_OWNER', identity=self.identity,
            status=self.status, accepted=dict(self.counts), acknowledged_write_bytes=self.ack_bytes,
            scalar_calls=dict(self.scalar_counts if self.state in ('finish', 'idle', 'locked')
                              else self.scalar.calls - self.scalar_baseline), row_scalars=list(self.row_scalars),
            retained_bf16_row_capacity=1024, retained_bf16_weight_capacity=1024,
            retained_bf16_output_capacity=1024, hardware_cycles=None, rtl_executed=False,
            physical_bank_allocation_proven=False, native_acceptance=False)


class TypedRmsDriver:
    """Service only actual RMS requests from the shared TypedMemory byte map."""
    def __init__(self, owner, memory, job):
        require(type(owner) is RmsOwner and type(memory) is TypedMemory and type(job) is RmsJob,
                'RMS owner, shared typed memory and immutable job required')
        job.validate()
        require(owner.ports()['job_ready'] and memory.pending is None, 'drained resources required')
        self.input = memory.exact(job.input, job.write_bytes, readable=True)
        self.weight = memory.exact(job.weight, ROW_BYTES, readable=True)
        self.output = memory.exact(job.output, job.write_bytes, readable=False)
        self.owner, self.memory, self.job = owner, memory, job
        self.source_hashes = tuple(sha(r.raw()) for r in (self.input, self.weight))
        self.pending, self.response, self.aborted = None, None, False
        self.counts = Counter()
        require(owner.tick(job=job)['job_fire'], 'RMS admission rejected')

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             abort=False, read_error=False, ack_error=False):
        require(self.response is None, 'RMS invocation already retired')
        p = self.owner.ports()
        pending = self.pending if memory_response_ready else None
        if pending is not None:
            pending = MemoryResponse(pending.tag, pending.data,
                                     bool(ack_error if self.owner.request.write else read_error), pending.nbytes)
        abort_edge = abort and not self.aborted
        self.aborted |= abort_edge
        e = self.owner.tick(memory_ready=memory_ready, memory_response=pending,
                            response_ready=response_ready, abort=abort_edge)
        self.counts['ticks'] += 1
        if e['memory_response_fire']:
            require(self.pending is not None, 'response without accepted request')
            if p['state'] in ('wait', 'drain') and self.memory.pending is not None:
                self.memory.acknowledge(WriteAck(pending.tag, pending.error, pending.nbytes))
            self.pending = None
        if e['memory_fire']:
            require(self.pending is None, 'multiple outstanding RMS requests')
            q = e['memory']
            region = self.memory._resolve(q.address)
            if q.write:
                require(region is self.output and len(q.data) == BEAT_BYTES, 'write escaped typed output')
                self.memory.begin_write(WriteCommand(q.address, 1, q.tag))
                self.memory.write_data(struct.unpack('<32H', q.data), True, mask=FULL_MASK)
                self.pending = MemoryResponse(q.tag)
                self.counts['write_bytes'] += BEAT_BYTES
            else:
                require(region is self.input or region is self.weight, 'read escaped typed inputs')
                self.pending = MemoryResponse(q.tag, self.memory.read64(q.address))
                self.counts['read_bytes'] += BEAT_BYTES
        if e['response_fire']:
            require(self.pending is None and self.memory.pending is None, 'terminal before transport drained')
            require(self.source_hashes == tuple(sha(r.raw()) for r in (self.input, self.weight)),
                    'actual input/weight changed')
            self.response = e['response']
            if self.response.status is None:
                require(self.owner.identity == source_identity(self.job.policy), 'RMS source changed during execution')
                self.memory.publish(self.job.output, (self.response.tag, None, self.response.write_bytes))
        return e

    def report(self):
        return dict(owner=self.owner.report(), complete=self.response is not None,
                    status=None if self.response is None else self.response.status,
                    counts=dict(self.counts), output_published=self.output.published,
                    input_sha256=list(self.source_hashes), output_sha256=sha(self.output.raw()))
