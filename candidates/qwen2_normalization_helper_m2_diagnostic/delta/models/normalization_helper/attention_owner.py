"""Memory-fed legacy Qwen2 Attention over the ONE shared Matrix/scalar service.

Qwen2Block.scala:148-175,438-466 and MatrixPipeline.scala's legacy client are
the ordered arithmetic and transaction contract. Only accepted 64B memory
responses supply operands. The generator collapses local/scalar scheduling,
so ticks are software handshake events, NEVER hardware execution cycles.

The retained tensors are one 128-word Q head, at most max_tokens scores and
probabilities, and bounded packets. MatrixService owns the existing five-bank
accumulator resource; this owner never creates an arithmetic array or SFU.
The caller owns physical memory publication, after the accepted owner result.
"""
from collections import Counter
import struct

from ..ffn_public.prefix_arithmetic import ArithmeticFault, NATIVE_ACCEPTANCE, finite
from ..ffn_public.prefix_owners import (BEAT_BYTES, FULL_MASK, LANES, LIMIT, Job,
    MemoryRequest, MemoryResponse, OwnerResult, PrefixFault, PrefixOwner, uint)
from .matrix_service import LegacyMatrixClient, LegacyRequest, MatrixProtocolError
from .scalar_recipe import exp_negative
from ..attention_packed_owner import hooks as packed


class AttentionOwner(PrefixOwner):
    """Fixed H1536/12 heads/KV256/2 heads/HD128, source max_tokens<=1024.

    m16 and m128 are the public fullgraph profiles. Smaller m values are useful
    synthetic tests, not evidence of complete public-profile execution.
    Reset while active first drains accepted memory and Matrix obligations.
    Once the rejected terminal is accepted, reset both this owner and the
    shared MatrixService explicitly before admitting a new owner job.
    """
    KINDS = ('Attention',)

    def __init__(self, matrix, scalar=None, *, max_tokens=1024, packed_schedule=None):
        if not uint(max_tokens, 16) or not 0 < max_tokens <= 1024:
            raise ValueError('Attention source supports at most 1024 tokens')
        packed.install(self, packed_schedule)
        super().__init__(scalar, max_tokens=max_tokens)
        self.matrix, self.matrix_client = matrix, None
        self.matrix_request = None
        self.matrix_baseline = Counter()
        self.matrix_counts = Counter()
        self.fma_baseline = self.useful_macs = 0
        self.executed_macs = 0
        self.memory_pending = self.abort_pending = False
        self.peak_score_words = self.peak_probability_words = 0

    def ports(self):
        ready = (self.state == 'idle' and not self.poison and self.scalar.client is None
                 and self.matrix.owner is None and not self.matrix.reset_required)
        return packed.ports(self, dict(job_ready=ready, memory=self.request if self.state == 'issue' else None,
                    memory_response_ready=self.memory_pending,
                    response_ready=self.memory_pending,
                    matrix=self.matrix_request if self.state == 'matrix_issue' else None,
                    response=self.result if self.state == 'finish' else None,
                    reset_required=self.poison or self.matrix.reset_required, state=self.state))

    def _validate(self, j):
        packed.validate(self,j)
        if j.kind != 'Attention' or any(getattr(j, name, False) for name in
                ('weight_bf16', 'activation_bf16', 'output_bf16')):
            raise PrefixFault('Unsupported', 'legacy Attention uses FP32 memory containers')
        if not (uint(j.tag, 32) and uint(j.m, 16)
                and 0 < j.m <= self.max_tokens and j.n == 1536 and j.k == 128):
            raise PrefixFault('Bounds', 'legacy Attention tag/shape/profile')
        extent, cache_extent = j.m * 1536 * 4, j.m * 256 * 4
        if j.write_bytes != extent:
            raise PrefixFault('Bounds', 'Attention output extent')
        spans = ((j.a, extent), (j.b, cache_extent), (j.c, cache_extent))
        for address, size in (*spans, (j.dst, extent)):
            if not (uint(address, 64) and address % 64 == 0 and address + size <= LIMIT):
                raise PrefixFault('Bounds', 'Attention physical span alignment/overflow')
        if any(base < j.dst + extent and j.dst < base + size for base, size in spans):
            raise PrefixFault('Permission', 'Attention output overlaps input')
        if any(a < b + nb and b < a + na for i, (a, na) in enumerate(spans)
               for b, nb in spans[i + 1:]):
            raise PrefixFault('Permission', 'Attention input views overlap')

    def _op(self, operation, a, b=0, *, policy='legacy_scalar'):
        if operation == 'div' or operation == 'mul':
            return self._normalization_helper(operation, a, b, policy=policy)
        return self.scalar.op(self, operation, a, b, policy=policy)

    def _normalization_helper(self, operation, a, b=0, *, policy='legacy_scalar'):
        return self.scalar.op(self, operation, a, b, policy=policy)

    def _matrix_step(self, opcode, a, b, *, clear, last, steps):
        # Source BF16 conversion is performed at the Matrix input boundary.
        a = tuple(self._op('bf', x) >> 16 for x in a)
        b = tuple(self._op('bf', x) >> 16 for x in b) + (0,) * 240
        result = yield LegacyRequest(opcode, a, b, clear, last, steps)
        lanes = None if result.value is None else tuple(
            result.value[i if opcode == 0x23 else 0][i] for i in range(16))
        if lanes is not None:
            # Source macs increments on fmDone even when the later finite
            # check rejects this packet. Count actually returned lane work.
            self.useful_macs += 16
        # Qwen2Block's last-connect finite check overrides matrixFault only
        # when an actual returned selected lane is nonfinite (lines493-494).
        if lanes is not None and any(not finite(x) for x in lanes):
            raise PrefixFault('Numerical', 'nonfinite legacy Matrix output lane')
        if result.error or lanes is None:
            raise PrefixFault('Protocol', 'legacy Matrix returned error')
        return lanes

    def _attention(self, j):
        for token in range(j.m):
            for head in range(12):
                kv_head = head // 6
                q = []
                for depth in range(0, 128, 16):
                    q.extend((yield from self._read(j.a + (token * 1536 + head * 128 + depth) * 4)))
                self.row_words = len(q)
                self.peak_row_words = max(self.peak_row_words, len(q))
                scores, maximum = [], 0xff800000
                for key in range(token + 1):
                    for depth in range(0, 128, 16):
                        k = yield from self._read(j.b + (key * 256 + kv_head * 128 + depth) * 4)
                        lanes = yield from self._matrix_step(0x23, q[depth:depth + 16], k,
                            clear=depth == 0, last=depth == 112, steps=8)
                    total = 0
                    for lane in lanes:
                        total = self._op('add', total, lane)
                    score = self._op('mul', total, 0x3db504f3)  # FP32 1/sqrt(128)
                    scores.append(score)
                    # Exact finite F32.less ordering; +0 and -0 compare equal.
                    if self._less(maximum, score):
                        maximum = score
                self.peak_score_words = max(self.peak_score_words, len(scores))
                probabilities, total = [], 0
                for score in scores:
                    difference = self._op('add', score, maximum ^ 0x80000000)
                    probability = exp_negative(self.scalar, self, difference)
                    self.counts['exp_negative_requests'] += 1
                    probabilities.append(probability)
                    total = self._op('add', total, probability)
                self.peak_probability_words = max(self.peak_probability_words, len(probabilities))
                inverse = self._op('div', 0x3f800000, total)
                for col in range(0, 128, 16):
                    for key, probability in enumerate(probabilities):
                        probability = self._op('mul', probability, inverse)
                        v = yield from self._read(j.c + (key * 256 + kv_head * 128 + col) * 4)
                        lanes = yield from self._matrix_step(0x24, (probability,) + (0,) * 15, v,
                            clear=key == 0, last=key == token, steps=token + 1)
                    yield from self._write(j.dst + (token * 1536 + head * 128 + col) * 4, lanes)
                self.row_words = 0

    @staticmethod
    def _less(a, b):
        if (a ^ b) >> 31:
            return bool(a >> 31 and ((a | b) & 0x7fffffff))
        return (a & 0x7fffffff) > (b & 0x7fffffff) if a >> 31 else a < b

    def _finish(self, status=None, detail=None):
        super()._finish(status, detail)
        self.matrix_request = None
        executed = int(self.matrix.lib.matrix_normal_fmas()) - self.fma_baseline
        self.executed_macs = executed
        self.matrix_counts = self.matrix.counts - self.matrix_baseline
        self.result = OwnerResult(self.job.tag, status, self.ack_bytes,
                                  self.clock - self.start_clock, self.useful_macs, executed)

    def _fault(self, status, detail):
        self.status, self.detail, self.poison = status, detail, True
        self.program = self.matrix_request = self.result = None
        if not self.memory_pending:
            self.request = None
        self.state = 'drain'
        packed.fault(self)
        self.abort_pending = self.matrix_client is not None
        if self.matrix_client is None and not self.memory_pending and not self.scratch_pending and not self.scratch_leased:
            self._finish(status, detail)

    def _advance(self, response=None):
        try:
            action = self.program.send(response)
            if packed.action(self, action):
                return
            if isinstance(action, LegacyRequest):
                self.matrix_request, self.state = action, 'matrix_issue'
                return
            address, data = action
            if self.serial == 1 << 32:
                raise PrefixFault('Protocol', 'Attention memory request sequence exhausted')
            self.request = MemoryRequest(address, (self.tag_prefix << 32) | self.serial,
                data is not None, data, FULL_MASK if data is not None else 0)
            self.serial += 1
            self.state = 'issue'
        except StopIteration:
            if self.scratch_pending or self.scratch_request is not None or self.scratch_leased:
                self._fault('Protocol', 'packed scratch debt at terminal')
            elif self.ack_bytes != self.job.write_bytes:
                self._fault('Protocol', 'Attention terminal before exact write ACK fence')
            elif self.matrix_client is None or not self.matrix_client.ports()['drained']:
                self._fault('Protocol', 'Attention terminal before Matrix obligations retire')
            else:
                self._finish()
        except PrefixFault as error:
            self._fault(error.status, error.detail)
        except ArithmeticFault as error:
            self._fault('Numerical', str(error))

    def tick(self, *, job=None, memory_ready=False, memory_response=None,
             response_ready=False, local_reset=False, reset=False,
             matrix_request_ready=True, matrix_result_ready=True,
             service_result_ready=True, service_done_ready=True, done_override=None,
             scratch_ready=False, scratch_response=None):
        p = self.ports()
        p.update(job_fire=False, memory_fire=False, memory_response_fire=False,
                 matrix_request_fire=False, matrix_result_fire=False, response_fire=False)
        self.clock += 1
        if reset and self.state in ('idle', 'locked'):
            # Do not reset someone else's shared service. The coordinated
            # caller resets MatrixService, which remains poisoned until then.
            self.__init__(self.matrix, self.scalar, max_tokens=self.max_tokens, packed_schedule=self.packed_schedule)
            p['job_ready'] = False
            return p
        matrix_poison = (self.matrix.owner is self and self.matrix.reset_required
                         and self.state not in ('drain', 'finish'))
        if local_reset or reset or matrix_poison:
            p['job_ready'], p['memory'], p['matrix'], p['response'] = False, None, None, None
            if self.job is None or self.state in ('idle', 'locked'):
                self.poison, self.state = True, 'locked'
            else:
                self._fault('Protocol', 'shared Matrix quarantine' if matrix_poison
                            else 'reset while Attention active')
        elif job is not None and p['job_ready']:
            p['job_fire'] = True
            self.job, self.start_clock = job, self.clock
            self.ack_bytes = self.serial = self.useful_macs = 0
            self.counts = Counter(job_fire=1)
            self.scalar_baseline, self.scalar_counts = self.scalar.calls.copy(), Counter()
            self.matrix_baseline = self.matrix.counts.copy()
            self.matrix_counts = Counter()
            self.fma_baseline = int(self.matrix.lib.matrix_normal_fmas())
            self.tag_prefix = job.tag >> 16
            self.peak_row_words = self.peak_score_words = self.peak_probability_words = 0
            try:
                self._validate(job)
                if not self.scalar.acquire(self):
                    raise PrefixFault('Protocol', 'shared scalar admission mismatch')
                if not self.matrix.acquire(self, 'normal', job.tag):
                    raise PrefixFault('Protocol', 'shared Matrix admission mismatch')
                self.matrix_client = (LegacyMatrixClient(self.matrix, self) if self.packed_schedule is None
                                      else packed.client(self))
                self.program = self._attention(job)
                self._advance()
            except PrefixFault as error:
                self._fault(error.status, error.detail)
        packed.ordered_pre_client(self, p, done_override)
        if p['memory'] is not None and memory_ready:
            p['memory_fire'] = True
            self.counts['write_requests' if self.request.write else 'read_requests'] += 1
            packed.memory_accept(self, self.request)
            self.memory_pending, self.state = True, 'wait'
        if p['memory_response_ready'] and memory_response is not None:
            q, r = self.request, memory_response
            # A foreign response cannot discharge the accepted request. Keep
            # its memory debt through poison/drain until its own reply arrives.
            # response_fire counts matched consumption, as in the exact64 owner.
            if not (type(r) is MemoryResponse and uint(r.tag, 64) and r.tag == q.tag):
                self.counts['foreign_response_rejected'] += 1
                self._fault('Protocol', 'foreign Attention response; accepted debt retained')
            else:
                packed.memory_ack(self, q, r)
                p['memory_response_fire'] = True
                self.memory_pending = False
                self.counts['memory_responses'] += 1
                status = 'Protocol' if r.nbytes != BEAT_BYTES else 'Memory' if r.error else None
                if status is None and q.write:
                    self.ack_bytes += BEAT_BYTES
                    self.counts['write_acks'] += 1
                if self.state == 'drain':
                    self.request = None
                elif status is not None:
                    self._fault(status, 'Attention memory response tag/error/byte count')
                elif q.write:
                    self._advance()
                else:
                    data = r.data
                    if isinstance(data, bytes) and len(data) == BEAT_BYTES:
                        data = struct.unpack('<16I', data)
                    if not isinstance(data, tuple) or len(data) != LANES or not all(uint(v, 32) for v in data):
                        self._fault('Protocol', 'Attention read must be exactly 16 FP32 words')
                    else:
                        self.counts['read_responses'] += 1
                        self._advance(data)
        packed.edge(self, p, scratch_ready, scratch_response)
        if self.matrix_client is not None and self.state != 'finish':
            draining = self.state == 'drain'
            offered = p['matrix'] if matrix_request_ready and not draining else None
            ready = (p['state'] == 'matrix_wait' and matrix_result_ready) or draining
            try:
                mp = self.matrix_client.tick(request=offered, result_ready=ready,
                    service_result_ready=service_result_ready, service_done_ready=service_done_ready,
                    abort=self.abort_pending, done_override=done_override)
                self.abort_pending = False
                if mp['request_fire']:
                    p['matrix_request_fire'] = True
                    self.counts['matrix_requests'] += 1
                    self.state = 'matrix_wait'
                if mp['result_fire']:
                    p['matrix_result_fire'] = True
                    packed.record_result(self, mp['result'])
                    self.matrix_request = None
                    if not draining and not packed.ordered_result_error(self, mp['result']):
                        self._advance(mp['result'])
                if self.state == 'drain' and not self.memory_pending and not self.scratch_pending and not self.scratch_leased and self.matrix_client.ports()['drained']:
                    self._finish(self.status, self.detail)
            except MatrixProtocolError as error:
                self._fault('Protocol', str(error))
        packed.ordered_post_client(self, p)
        if p['response'] is not None and response_ready:
            if self.matrix.owner is self:
                self.matrix.retire_owner_response(self)
                self.matrix.release(self)
                self.matrix_counts = self.matrix.counts - self.matrix_baseline
            p['response_fire'] = True
            self.counts['owner_results'] += 1
            self.state = 'locked' if self.poison else 'idle'
            self.result = self.matrix_client = None
        return p

    def report(self):
        report = super().report()
        terminal = self.state in ('finish', 'idle', 'locked')
        report.update(row_buffer_capacity_words=128, peak_row_buffer_words=self.peak_row_words,
            score_buffer_capacity_words=self.max_tokens, peak_score_buffer_words=self.peak_score_words,
            probability_buffer_capacity_words=self.max_tokens,
            peak_probability_buffer_words=self.peak_probability_words,
            copy_tile_capacity_words=0, peak_copy_tile_words=0,
            matrix_accepted=dict(self.matrix_counts if terminal else self.matrix.counts - self.matrix_baseline),
            matrix_normal_fma_calls=self.executed_macs if terminal else int(self.matrix.lib.matrix_normal_fmas()) - self.fma_baseline,
            matrix_useful_lane_fmas=self.useful_macs,
            one_shared_matrix_software_service=True,
            matrix_resource_address=self.matrix.resource_address,
            fullgraph_profile=None if self.job is None or self.job.m not in (16, 128) else self.job.m,
            synthetic_shape=self.job is not None and self.job.m not in (16, 128),
            native_acceptance=NATIVE_ACCEPTANCE)
        return report
