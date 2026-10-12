"""Source-only Bf16CausalGqaOwner using the caller's Matrix and Scalar.

The physical recipe is Q16x256, K32x256, scores16x<=256, QK16x32,
context16x256 and one V256. Every Q/K/V word comes from an accepted memory
response. QK and PV use the same normal Matrix stream and its real immutable
result then terminal done; softmax uses the same injected scalar service.
No attention reference, full-M score buffer, Matrix, Scalar or DMA is created.

PairHighFirst changes only the QK operand route to 1,0,3,2,...,255,254.
LegacyAscending preserves the production Chisel d0..255 route. Pair routing
is a numerical model policy, not VDPBF16PS DAZ/FTZ or RTL equivalence.
Software ticks are accepted protocol events, never hardware cycles.
"""
from array import array
from collections import Counter
from dataclasses import dataclass
from enum import Enum
import hashlib
from pathlib import Path
import struct

from ...qwen2_resident_matrix.ffn_attention.matrix_service import (
    MatrixService, MatrixResult, MatrixDone, MatrixValue, NormalGroup, NormalStep,
)
from ...qwen35_gdn_prefill.rms_owner import ArithmeticFault, finite
from ...qwen35_gdn_prefill.typed_dense import FULL_MASK
from ..norm_rope.scalar import NormRopeScalar


BEAT_BYTES, HEAD_DIM, HEAD_BYTES = 64, 256, 512
QUERY_TOKEN_BYTES, KV_TOKEN_BYTES = 4096, 1024
ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Bf16CausalGqaOwner.scala'
PRODUCTION_SHA256 = 'd4c1047d275fa0b38d9498fdf6c22018f52138b21a49e55866661a4d4e635cd9'
SOURCE_PATHS = (
    PRODUCTION_SOURCE,
    'candidates/qwen35_attention_prefill/gqa/__init__.py',
    'candidates/qwen35_attention_prefill/gqa/owner.py',
    'candidates/qwen35_attention_prefill/gqa/driver.py',
    'candidates/qwen35_attention_prefill/norm_rope/scalar.py',
    'candidates/qwen35_gdn_prefill/conv/scalar.py',
    'candidates/qwen35_gdn_prefill/rms_owner.py',
    'candidates/qwen35_gdn_prefill/typed_dense.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp',
    'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp',
    'candidates/qwen2_resident_matrix/transposed_down/model.py',
    'src/heteronpu/rope_bf16_candidate.py',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala',
)


def require(condition, detail):
    if not condition:
        raise ValueError('typed BF16 GQA: ' + detail)


def uint(value, width):
    return type(value) is int and 0 <= value < 1 << width


def source_identity(root=ROOT):
    hashes = {name: hashlib.sha256((Path(root) / name).read_bytes()).hexdigest() for name in SOURCE_PATHS}
    require(hashes[PRODUCTION_SOURCE] == PRODUCTION_SHA256, 'frozen production GQA source drift')
    return dict(source_sha256=hashes,
                scope='BF16_CAUSAL_GQA_SOFTWARE_OWNER', rtl_executed=False,
                hardware_cycles=None, native_acceptance=False, fullblock_executed=False,
                production_chisel_qk_policy='legacy_ascending',
                pair_high_first_isa_emulation=False)


class QkOrder(str, Enum):
    LegacyAscending = 'legacy_ascending'
    PairHighFirst = 'pair_high_first'


def _span(base, extent):
    require(uint(base, 56) and base % BEAT_BYTES == 0 and type(extent) is int and
            extent > 0 and extent % BEAT_BYTES == 0 and base + extent <= 1 << 56,
            'aligned nonempty 56-bit physical span')


@dataclass(frozen=True)
class Bf16CausalGqaJob:
    tag: int
    query_input: int
    cache_base: int
    output: int
    tokens: int
    query_start: int
    cache_length: int
    capacity_tokens: int = 256
    query_heads: int = 8
    kv_heads: int = 2
    head_dim: int = HEAD_DIM
    qk_policy: QkOrder = QkOrder.LegacyAscending
    dtype: str = 'bf16'

    @property
    def cache_v(self):
        return self.cache_base + self.capacity_tokens * KV_TOKEN_BYTES

    @property
    def write_bytes(self):
        return self.tokens * QUERY_TOKEN_BYTES

    @property
    def input_spans(self):
        return ((self.query_input, self.write_bytes),
                (self.cache_base, self.cache_length * KV_TOKEN_BYTES),
                (self.cache_v, self.cache_length * KV_TOKEN_BYTES))

    @property
    def output_spans(self):
        return ((self.output, self.write_bytes),)

    def validate(self):
        require(uint(self.tag, 32), 'job tag domain')
        require(type(self.tokens) is int and 1 <= self.tokens <= 128 and
                type(self.capacity_tokens) is int and 1 <= self.capacity_tokens <= 256 and
                type(self.cache_length) is int and 1 <= self.cache_length <= self.capacity_tokens,
                'M1..128/cache1..capacity<=256 required')
        require(uint(self.query_start, 32) and self.query_start + self.tokens == self.cache_length,
                'query start plus token count must equal staged cache length')
        require(type(self.query_heads) is int and self.query_heads == 8 and
                type(self.kv_heads) is int and self.kv_heads == 2 and
                type(self.head_dim) is int and self.head_dim == HEAD_DIM and
                type(self.dtype) is str and self.dtype == 'bf16', 'BF16 GQA8/2 H256 required')
        require(type(self.qk_policy) is QkOrder, 'explicit named QK operand-order policy required')
        # The unused K/V capacity remains reserved even when physical valid
        # K/V regions are separate allocations with a gap between them.
        regions = ((self.query_input, self.write_bytes),
                   (self.cache_base, self.capacity_tokens * KV_TOKEN_BYTES * 2),
                   (self.output, self.write_bytes))
        for base, extent in regions:
            _span(base, extent)
        require(all(a + na <= b or b + nb <= a for i, (a, na) in enumerate(regions)
                    for b, nb in regions[:i]), 'Q/cache capacity/context allocation alias')


@dataclass(frozen=True)
class MemoryRequest:
    address: int
    tag: int
    data: bytes | None = None

    @property
    def write(self):
        return self.data is not None

    @property
    def nbytes(self):
        return BEAT_BYTES

    @property
    def mask(self):
        return FULL_MASK if self.write else 0


@dataclass(frozen=True)
class MemoryResponse:
    tag: int
    data: bytes = b''
    error: bool = False
    nbytes: int = BEAT_BYTES


@dataclass(frozen=True)
class Bf16CausalGqaResult:
    tag: int
    status: str | None
    write_bytes: int
    model_ticks: int
    attention_status: int
    output_committed: bool


class _Fault(Exception):
    def __init__(self, status, attention_status=0):
        self.status, self.attention_status = status, attention_status


def _bf16(bits):
    if not uint(bits, 32) or not finite(bits):
        raise _Fault('Numerical', 1)
    rounded = ((bits + 0x7fff + ((bits >> 16) & 1)) >> 16) & 0xffff
    if rounded & 0x7f80 == 0x7f80:
        raise _Fault('Numerical', 1)
    return rounded


def _less(a, b):
    # Finite FP32 comparison only; no host arithmetic supplies a result node.
    return struct.unpack('<f', struct.pack('<I', a))[0] < struct.unpack('<f', struct.pack('<I', b))[0]


class Bf16CausalGqaOwner:
    """One bounded owner holding the same Matrix and Scalar for its whole job.

    Matrix output is collected provisionally under backpressure in 32-lane
    beats. Only the final collection beat retires the entire immutable result;
    the generator cannot see staging buffers until the actual MatrixDone.
    Abort drains accepted memory and Matrix obligations and poisons admission
    until a joint reset. ACK byte counts include successful accepted writes
    that drain after explicit abort, as transport evidence. The source owner
    has no explicit abort port; this software sideband can cancel a held
    success before terminal acceptance. The scalar API is synchronous, so it cannot leave an
    unreturned accepted scalar operation. It still has one ready/fire edge per
    scalar request. The optional observer sees only already-computed immutable
    nodes; snapshots retained by a callback are explicitly host-only storage.
    """
    def __init__(self, matrix, scalar, observer=None):
        require(type(matrix) is MatrixService and isinstance(scalar, NormRopeScalar),
                'caller-owned shared MatrixService and NormRopeScalar required')
        require(observer is None or callable(observer), 'optional host observer callback')
        self.matrix, self.scalar, self.observer = matrix, scalar, observer
        self.query = array('H', [0]) * (16 * 256)
        self.keys = array('H', [0]) * (32 * 256)
        self.scores = array('I', [0]) * (16 * 256)
        self.qk = array('H', [0]) * (16 * 32)
        self.context = array('H', [0]) * (16 * 256)
        self.value = array('H', [0]) * 256
        require(self.query.itemsize == 2 and self.scores.itemsize == 4, 'bounded buffer word widths')
        self.maximum, self.seen = [0] * 16, [False] * 16
        self.state, self.poison = 'idle', False
        self.job = self.request = self.result = self.program = self.action = None
        self.status, self.attention_status = None, 0
        self.sequence = self.ack_bytes = self.ticks = self.start = self.matrix_tag = 0
        self.matrix_active = self.memory_pending = False
        self._held_result = None
        self._held_value = self._held_raw = self._held_metadata = None
        self._held_done = self._held_done_metadata = None
        self._collect_row = self._collect_beat = 0
        self._epoch = matrix.epoch
        self.counts, self.scalar_counts, self._scalar_baseline = Counter(), Counter(), Counter()
        self.scalar_internal_counts, self._scalar_internal_baseline = Counter(), Counter()

    def ports(self):
        return dict(job_ready=self.state == 'idle' and not self.poison and self.matrix.owner is None and
                    not self.matrix.reset_required and self.scalar.client is None,
                    memory=self.request if self.state == 'memory_issue' else None,
                    memory_response_ready=self.memory_pending and self.state in ('memory_wait', 'drain'),
                    response=self.result if self.state == 'finish' else None,
                    reset_required=self.poison or self.matrix.reset_required, state=self.state)

    def reset(self):
        require(self.state in ('idle', 'locked') and not self.memory_pending and not self.matrix_active and
                self.request is None and self.matrix.owner is None and self.scalar.client is None and
                not self.matrix.reset_required and (not self.poison or self.matrix.epoch != self._epoch),
                'joint reset requires drained/retired transport and reset shared Matrix')
        self.__init__(self.matrix, self.scalar, self.observer)

    def _observe(self, stage, token, head, first_key, words):
        if self.observer is not None:
            snapshot = tuple(words)
            require(all(uint(word, 32) for word in snapshot), 'observer raw-word domain')
            try:
                self.observer(stage, token, head, first_key, snapshot)
            except Exception as error:
                raise _Fault('Observer') from error

    def _read_head(self, target, offset, address):
        for beat in range(8):
            raw = yield ('memory', address + beat * BEAT_BYTES, None)
            words = struct.unpack('<32H', raw)
            if any(word & 0x7f80 == 0x7f80 for word in words):
                raise _Fault('Numerical', 1)
            target[offset + beat * 32:offset + (beat + 1) * 32] = array('H', words)

    def _matrix_group(self, opcode, count, rows, columns):
        group = NormalGroup(opcode, count, self.matrix_tag, 1 if opcode == 0x23 else 255, 1)
        yield ('group', group)
        if opcode == 0x23:
            for index in range(256):
                d = index ^ 1 if self.job.qk_policy is QkOrder.PairHighFirst else index
                a = tuple(int(self.query[r * 256 + d]) if r < rows else 0 for r in range(16))
                b = tuple(int(self.keys[c * 256 + d]) if c < columns else 0 for c in range(256))
                last = index == 255
                yield ('step', NormalStep(index, a, b, index == 0, last, 0, last, last))
        else:
            for key in range(count):
                yield from self._read_head(self.value, 0, self.job.cache_v + key * KV_TOKEN_BYTES +
                                           (self._head // 4) * HEAD_BYTES)
                a = tuple(int(self.scores[r * 256 + key]) >> 16 if r < rows else 0 for r in range(16))
                b = tuple(int(word) for word in self.value)
                last = key + 1 == count
                yield ('step', NormalStep(key, a, b, key == 0, last, 0, last, last))
        yield ('result', opcode, rows, columns)
        yield ('done', group.tag)
        self.matrix_tag = (self.matrix_tag + 1) & 0xffffffff

    def _softmax(self, qtile, head, rows):
        count = self.job.cache_length
        for row in range(rows):
            base, token = row * 256, qtile + row
            if not self.seen[row]:
                raise _Fault('Numerical', 4)
            self._observe('scaled_scores_bf16', token, head, 0,
                          (int(x) for x in self.scores[base:base + count]))
            self._observe('row_max_fp32', token, head, 0, (self.maximum[row],))
            total = 0
            causal_end = self.job.query_start + token
            for key in range(count):
                if key > causal_end:
                    self.scores[base + key] = 0
                    continue
                difference = yield ('scalar', 'add', int(self.scores[base + key]), self.maximum[row] ^ 0x80000000)
                self._observe('score_difference_fp32', token, head, key, (difference,))
                if not difference & 0x80000000 and difference & 0x7fffffff:
                    raise _Fault('Numerical', 2)
                if difference & 0x7fffffff >= 0x42a00000:
                    raise _Fault('Unsupported', 3)
                exponential = yield ('scalar', 'exp_negative', difference, 0)
                if exponential & 0x80000000 or exponential & 0x7fffffff == 0 or _less(0x3f800000, exponential):
                    raise _Fault('Numerical', 2)
                self.scores[base + key] = exponential
                self._observe('exp_fp32', token, head, key, (exponential,))
                total = yield ('scalar', 'add', total, exponential)
                self._observe('sum_exp_fp32', token, head, key, (total,))
            if total & 0x80000000 or total & 0x7fffffff == 0 or not finite(total):
                raise _Fault('Numerical', 2)
            for key in range(count):
                if key > causal_end:
                    self.scores[base + key] = 0
                    self._observe('probability_fp32', token, head, key, (0,))
                    continue
                probability = yield ('scalar', 'div', int(self.scores[base + key]), total)
                self._observe('probability_fp32', token, head, key, (probability,))
                if probability & 0x80000000 or _less(0x3f800000, probability):
                    raise _Fault('Numerical', 2)
                self.scores[base + key] = _bf16(probability) << 16
            self._observe('probabilities_bf16', token, head, 0,
                          (int(x) for x in self.scores[base:base + count]))

    def _execute(self):
        job = self.job
        for qtile in range(0, job.tokens, 16):
            rows = min(16, job.tokens - qtile)
            for head in range(8):
                self._head = head
                self.seen[:] = [False] * 16
                for row in range(rows):
                    yield from self._read_head(self.query, row * 256, job.query_input +
                                               (qtile + row) * QUERY_TOKEN_BYTES + head * HEAD_BYTES)
                for ktile in range(0, job.cache_length, 32):
                    columns = min(32, job.cache_length - ktile)
                    for col in range(columns):
                        yield from self._read_head(self.keys, col * 256, job.cache_base +
                                                   (ktile + col) * KV_TOKEN_BYTES + (head // 4) * HEAD_BYTES)
                    yield from self._matrix_group(0x23, 256, rows, columns)
                    for row in range(rows):
                        token = qtile + row
                        self._observe('qk_bf16', token, head, ktile,
                                      (int(self.qk[row * 32 + col]) << 16 for col in range(columns)))
                        for col in range(columns):
                            key = ktile + col
                            scaled = yield ('scalar', 'mul_ieee_rne', int(self.qk[row * 32 + col]) << 16, 0x3d800000)
                            rounded = _bf16(scaled) << 16
                            self.scores[row * 256 + key] = rounded
                            if key <= job.query_start + token and (not self.seen[row] or _less(self.maximum[row], rounded)):
                                self.maximum[row], self.seen[row] = rounded, True
                yield from self._softmax(qtile, head, rows)
                yield from self._matrix_group(0x24, job.cache_length, rows, 256)
                for row in range(rows):
                    self._observe('context_bf16', qtile + row, head, 0,
                                  (int(word) << 16 for word in self.context[row * 256:(row + 1) * 256]))
                    for beat in range(8):
                        offset = row * 256 + beat * 32
                        data = struct.pack('<32H', *self.context[offset:offset + 32])
                        yield ('memory', job.output + (qtile + row) * QUERY_TOKEN_BYTES +
                               head * HEAD_BYTES + beat * BEAT_BYTES, data)

    def _finish(self):
        require(not self.memory_pending and not self.matrix_active and self.matrix.result is None and
                self.matrix.group is None and self.matrix.done is None, 'terminal before shared obligations drain')
        if self.status is None and self.ack_bytes != self.job.write_bytes:
            self.status, self.poison = 'Protocol', True
            self.matrix.abort(self)
        self.scalar_counts = self.scalar.calls - self._scalar_baseline
        self.scalar_internal_counts = self.scalar.internal_calls - self._scalar_internal_baseline
        if self.scalar.client is self:
            self.scalar.release(self)
        self.request = self.action = self.program = self._held_result = None
        self._held_value = self._held_raw = self._held_metadata = None
        self._held_done = self._held_done_metadata = None
        self.result = Bf16CausalGqaResult(self.job.tag, self.status, self.ack_bytes,
                                         self.ticks - self.start, self.attention_status,
                                         self.status is None)
        self.state = 'finish'

    def _fail(self, status, attention_status=0):
        self.status = self.status or status
        self.attention_status = self.attention_status or attention_status
        self.poison = True
        if self.matrix.owner is self and not self.matrix.reset_required:
            self.matrix.abort(self)
        self.program = self.action = None
        if not self.memory_pending:
            self.request = None
        self.state = 'drain'

    def _advance(self, value=None):
        try:
            self.action = self.program.send(value)
            kind = self.action[0]
            if kind == 'memory':
                require(self.sequence < 1 << 32, 'memory sequence exhausted')
                self.request = MemoryRequest(self.action[1], (self.job.tag << 32) | self.sequence, self.action[2])
                self.sequence += 1
                self.state = 'memory_issue'
            else:
                self.state = kind
                if kind == 'result':
                    self._collect_row = self._collect_beat = 0
                    self._held_result = None
                    self._held_value = self._held_raw = self._held_metadata = None
                elif kind == 'done':
                    self._held_done = self._held_done_metadata = None
        except StopIteration:
            self._finish()
        except _Fault as error:
            self._fail(error.status, error.attention_status)

    def _check_result(self, result):
        if (type(result) is not MatrixResult or type(result.value) is not MatrixValue or
                type(result.value.raw) is not bytes or len(result.value.raw) != 16384 or
                type(result.context) is not int or result.context != 0 or
                type(result.error) is not bool or result.error or type(result.last) is not bool or not result.last or
                not uint(result.ticket, 64) or not uint(result.epoch, 64) or
                result.ticket != self.matrix.ticket or result.epoch != self._epoch):
            raise _Fault('Protocol')
        metadata = (result.context, result.last, result.error, result.ticket, result.epoch)
        if self._held_result is not None:
            if (result is not self._held_result or result.value is not self._held_value or
                    result.value.raw is not self._held_raw or metadata != self._held_metadata):
                raise _Fault('Protocol')
        # These are references to the service's same immutable result, not a
        # second result allocation. Freeze from first valid observation,
        # including an observation while collection is backpressured.
        self._held_result = result
        self._held_value, self._held_raw, self._held_metadata = result.value, result.value.raw, metadata

    def _collect(self, result):
        _, opcode, rows, columns = self.action
        self._check_result(result)
        row, beat = self._collect_row, self._collect_beat
        count = columns if opcode == 0x23 else 32
        start = 0 if opcode == 0x23 else beat * 32
        converted = tuple(_bf16(int(result.value[row][start + col])) for col in range(count))
        target, offset = (self.qk, row * 32) if opcode == 0x23 else (self.context, row * 256 + start)
        target[offset:offset + count] = array('H', converted)
        final = row + 1 == rows and (opcode == 0x23 or beat == 7)
        if final:
            self.matrix.retire_result(self, result)
            self._held_result = None
            self._held_value = self._held_raw = self._held_metadata = None
            self.counts['matrix_results'] += 1
            self._advance()
        elif opcode == 0x23 or beat == 7:
            self._collect_row, self._collect_beat = row + 1, 0
        else:
            self._collect_beat += 1
        return final

    def _check_done(self, done):
        if (type(done) is not MatrixDone or not uint(done.tag, 32) or
                type(done.error) is not bool or done.error or
                not uint(done.ticket, 64) or not uint(done.epoch, 64) or
                done.tag != self.action[1] or done.ticket != self.matrix.ticket or done.epoch != self._epoch):
            raise _Fault('Protocol')
        metadata = (done.tag, done.error, done.ticket, done.epoch)
        if self._held_done is not None and (done is not self._held_done or metadata != self._held_done_metadata):
            raise _Fault('Protocol')
        self._held_done, self._held_done_metadata = done, metadata

    def tick(self, *, job=None, memory_ready=False, memory_response=None, response_ready=False,
             matrix_group_ready=True, matrix_step_ready=True, matrix_result_ready=True,
             matrix_done_ready=True, scalar_ready=True, abort=False):
        require(all(type(v) is bool for v in (memory_ready, response_ready, matrix_group_ready,
                matrix_step_ready, matrix_result_ready, matrix_done_ready, scalar_ready, abort)),
                'boolean owner controls required')
        p = self.ports()
        p.update(job_fire=False, memory_fire=False, memory_response_fire=False, response_fire=False,
                 matrix_group_fire=False, matrix_step_fire=False, matrix_result_fire=False,
                 matrix_done_fire=False, scalar_fire=False)
        self.ticks += 1
        if abort:
            p['job_ready'], p['memory'], p['response'] = False, None, None
            if self.job is None or self.state in ('idle', 'locked'):
                self.poison, self.state = True, 'locked'
                return p
            self._fail('Aborted')
        if not abort and job is not None and p['job_ready']:
            require(type(job) is Bf16CausalGqaJob, 'immutable GQA job required')
            job.validate()
            require(self.matrix.acquire(self, 'normal', job.tag), 'shared Matrix admission')
            require(self.scalar.acquire(self), 'shared Scalar admission')
            self.job, self.start, self.matrix_tag, self._epoch = job, self.ticks, job.tag, self.matrix.epoch
            self.sequence = self.ack_bytes = 0
            self.status, self.attention_status = None, 0
            self.counts, self._scalar_baseline = Counter(), self.scalar.calls.copy()
            self._scalar_internal_baseline = self.scalar.internal_calls.copy()
            self.program = self._execute()
            p['job_fire'] = True
            self._advance()
            return p
        # This monitor is global, including PV's interleaved V memory reads.
        # An early terminal blocks new traffic on this edge but still allows
        # an already accepted memory response to drain below.
        if self.matrix.owner is self and self.status is None and self.state != 'drain':
            early_done = self.matrix_active and self.matrix.done is not None and self.state != 'done'
            if early_done or self.matrix.reset_required:
                self._fail('Protocol')
                p['memory'], p['response'] = None, None
        if p['memory_response_ready'] and memory_response is not None:
            p['memory_response_fire'] = True
            request, response = self.request, memory_response
            self.memory_pending = False
            valid = (type(response) is MemoryResponse and uint(response.tag, 64) and response.tag == request.tag and
                     type(response.nbytes) is int and response.nbytes == 64 and type(response.error) is bool)
            status = 'Protocol' if not valid else 'Memory' if response.error else None
            self.counts['memory_responses'] += 1
            if request.write and status is None:
                self.ack_bytes += BEAT_BYTES
                self.counts['write_acks'] += 1
            self.request = None
            if self.state == 'drain':
                pass
            elif status is not None:
                self._fail(status)
            elif request.write:
                self._advance()
            elif type(response.data) is not bytes or len(response.data) != BEAT_BYTES:
                self._fail('Protocol')
            else:
                self._advance(response.data)
        elif not abort and p['memory'] is not None and memory_ready:
            p['memory_fire'] = True
            self.memory_pending, self.state = True, 'memory_wait'
            self.counts['write_requests' if self.request.write else 'read_requests'] += 1
        elif not abort and self.state not in ('idle', 'locked', 'finish', 'memory_issue', 'memory_wait', 'drain'):
            try:
                self.matrix._check_owner(self, 'normal')
                self.matrix._check_event(epoch=self._epoch)
                if self.matrix_active and self.matrix.done is not None and self.state != 'done':
                    raise _Fault('Protocol')
                if self.state == 'group' and matrix_group_ready:
                    if self.matrix.accept_group(self, self.action[1]):
                        self.matrix_active = True
                        self.counts['qk_groups' if self.action[1].opcode == 0x23 else 'pv_groups'] += 1
                        p['matrix_group_fire'] = True
                        self._advance()
                elif self.state == 'step' and matrix_step_ready:
                    if self.matrix.accept_step(self, self.action[1]):
                        self.counts['matrix_steps'] += 1
                        p['matrix_step_fire'] = True
                        self._advance()
                elif self.state == 'result':
                    result = self.matrix.result
                    if result is None and self._held_result is not None:
                        raise _Fault('Protocol')
                    if result is not None:
                        self._check_result(result)
                        if matrix_result_ready:
                            p['matrix_result_fire'] = self._collect(result)
                elif self.state == 'done':
                    done = self.matrix.done
                    if done is None and self._held_done is not None:
                        raise _Fault('Protocol')
                    if done is not None:
                        self._check_done(done)
                        if matrix_done_ready:
                            self.matrix.retire_done(self, done)
                            self._held_done = self._held_done_metadata = None
                            self.matrix_active = False
                            self.counts['matrix_done'] += 1
                            p['matrix_done_fire'] = True
                            self._advance()
                elif self.state == 'scalar' and scalar_ready:
                    _, operation, a, b = self.action
                    p['scalar_fire'] = True
                    self.counts['scalar_requests'] += 1
                    try:
                        result = self.scalar.op(self, operation, a, b)
                    except ArithmeticFault as error:
                        raise _Fault('Numerical', 2) from error
                    if not uint(result, 32) or not finite(result):
                        raise _Fault('Numerical', 2)
                    self._advance(result)
                if self.matrix.reset_required and self.state != 'drain':
                    self._fail('Protocol')
            except _Fault as error:
                self._fail(error.status, error.attention_status)
        if self.state == 'drain':
            # Accept only real held events. Abort may create terminal error
            # done without a result when a group stopped before its last step.
            result = self.matrix.result
            if result is not None and matrix_result_ready:
                self.matrix.retire_result(self, result)
                self._held_result = None
                self._held_value = self._held_raw = self._held_metadata = None
                self.counts['matrix_results'] += 1
                p['matrix_result_fire'] = True
            done = self.matrix.done
            if done is not None and matrix_done_ready:
                self.matrix.retire_done(self, done)
                self._held_done = self._held_done_metadata = None
                self.matrix_active = False
                self.counts['matrix_done'] += 1
                p['matrix_done_fire'] = True
            if not self.memory_pending and not self.matrix_active and self.matrix.group is None:
                self._finish()
        if not abort and p['response'] is not None and response_ready:
            p['response_fire'] = True
            self.matrix.retire_owner_response(self)
            self.matrix.release(self)
            self.counts['owner_results'] += 1
            self.state = 'locked' if self.poison else 'idle'
            self.result = None
        return p

    def report(self):
        buffers = dict(query=16 * 256 * 2, keys=32 * 256 * 2, scores=16 * 256 * 4,
                       qk=16 * 32 * 2, context=16 * 256 * 2, value=256 * 2)
        return dict(scope='BF16_CAUSAL_GQA_SOFTWARE_OWNER', status=self.status,
                    attention_status=self.attention_status, accepted=dict(self.counts),
                    scalar_calls=dict(self.scalar_counts if self.state in ('finish', 'idle', 'locked') else
                                      self.scalar.calls - self._scalar_baseline),
                    scalar_internal_calls=dict(self.scalar_internal_counts if self.state in ('finish', 'idle', 'locked') else
                                               self.scalar.internal_calls - self._scalar_internal_baseline),
                    qk_policy=None if self.job is None else self.job.qk_policy.value,
                    pv_policy='increasing_keys', acknowledged_write_bytes=self.ack_bytes,
                    bounded_payload_bytes=buffers, retained_payload_bytes=sum(buffers.values()),
                    arithmetic_resources_created=0, shared_matrix_resource_address=self.matrix.resource_address,
                    host_observer_snapshots=self.observer is not None, hardware_cycles=None,
                    rtl_executed=False, native_acceptance=False, fullblock_executed=False,
                    physical_bank_allocation_proven=False, generation_advanced=False)
