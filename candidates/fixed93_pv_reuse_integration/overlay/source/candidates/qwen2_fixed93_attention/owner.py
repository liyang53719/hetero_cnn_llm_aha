"""New fixed93 source-correspondence owner. Frozen PV32 run remains untouched.

One original M128 Attention job, token/head loops internal to that job. All
128-token Q/K/V production and KvAppend must already be published by public21.
This is a software owner, NOT a Chisel execution/cycle/resource-allocation proof.
"""
from collections import Counter
import struct
from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner
from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import LegacyRequest, MatrixProtocolError
from candidates.qwen2_resident_matrix.ffn_attention.scalar_recipe import exp_negative
from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ArithmeticFault, finite
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import (
    BEAT_BYTES, FULL_MASK, LANES, MemoryRequest, MemoryResponse, PrefixFault, uint)
from .client import PackedQkStart, PackedQkRequest, RetirePackedQk, Fixed93MatrixClient


class Fixed93AttentionOwner(OfficialAttentionOwner):
    """PackedQK16 + original PV16; admitted M<=128, source SRAM capacity1024."""
    def __init__(self, matrix, scalar=None, *, max_tokens=1024):
        super().__init__(matrix, scalar, max_tokens=max_tokens)
        self._packed_tag = 0

    def _validate(self, j):
        super()._validate(j)
        if j.m > 128:
            raise PrefixFault('Bounds', 'selected fixed93 packed QK admits at most128 tokens')

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
                for key_base in range(0, token + 1, 16):
                    count = min(16, token + 1 - key_base)
                    # Models the exclusive lease of pre-existing denseWeights,
                    # not a new physical cache, and never contains result tiles.
                    yield PackedQkStart(count)
                    dense_staging = [0] * 256
                    for depth in range(0, 128, 16):
                        for selected in range(count):
                            k = yield from self._read(j.b + ((key_base + selected) * 256 + kv_head * 128 + depth) * 4)
                            dense_staging[selected * 16:(selected + 1) * 16] = k
                        a = tuple(self._op('bf', x) >> 16 for x in q[depth:depth + 16])
                        b = tuple(self._op('bf', dense_staging[i]) >> 16 if i < count * 16 else 0 for i in range(256))
                        result = yield PackedQkRequest(depth // 16, count, a, b)
                    # Keep the actual service FIFO head borrowed until ALL
                    # selected scores are finite-checked and committed in order.
                    for selected in range(count):
                        key = key_base + selected
                        lanes = tuple(result.value[i][selected * 16 + i] for i in range(16))
                        if any(not finite(x) for x in lanes):
                            raise PrefixFault('Numerical', 'nonfinite selected packed QK final stripe')
                        total = 0
                        for lane in lanes:
                            total = self._op('add', total, lane)
                        dot = self._op('bf', total)
                        if not finite(dot):
                            raise PrefixFault('Numerical', 'nonfinite packed QK BF16 dot')
                        score = self._op('bf', self._op('mul', dot, 0x3db504f3))
                        if not finite(score):
                            raise PrefixFault('Numerical', 'nonfinite packed QK BF16 score')
                        scores.append(score)
                        if self._less(maximum, score):
                            maximum = score
                    yield RetirePackedQk(result, count)
                    result = lanes = dense_staging = None
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
                # Reuse the existing probability storage after denominator use.
                # Only col=0 evaluates Mul; all eight PV inputs stay raw FP32
                # until the unchanged per-use Matrix BF16 ingress conversion.
                for col in range(0, 128, 16):
                    for key, probability in enumerate(probabilities):
                        if col == 0:
                            probability = self._op('mul', probability, inverse)
                            probabilities[key] = probability
                        v = yield from self._read(j.c + (key * 256 + kv_head * 128 + col) * 4)
                        lanes = yield from self._matrix_step(0x24, (probability,) + (0,) * 15, v,
                            clear=key == 0, last=key == token, steps=token + 1)
                    output = tuple(self._op('bf', lane) for lane in lanes)
                    yield from self._write(j.dst + (token * 1536 + head * 128 + col) * 4, output)
                self.row_words = 0

    def _advance(self, response=None):
        try:
            action = self.program.send(response)
            if isinstance(action, (LegacyRequest, PackedQkStart, PackedQkRequest)):
                self.matrix_request, self.state = action, 'matrix_issue'
                return
            if isinstance(action, RetirePackedQk):
                self.matrix_client.commit(action)
                self.matrix_request, self.state = None, 'packed_retire'
                return
            address, data = action
            if self.serial == 1 << 32:
                raise PrefixFault('Protocol', 'Attention memory request sequence exhausted')
            self.request = MemoryRequest(address, (self.tag_prefix << 32) | self.serial,
                data is not None, data, FULL_MASK if data is not None else 0)
            self.serial += 1
            self.state = 'issue'
        except StopIteration:
            if self.ack_bytes != self.job.write_bytes:
                self._fault('Protocol', 'Attention terminal before exact write ACK fence')
            elif self.matrix_client is None or not self.matrix_client.ports()['drained']:
                self._fault('Protocol', 'Attention terminal before Matrix obligations retire')
            else:
                self._finish()
        except PrefixFault as error:
            self._fault(error.status, error.detail)
        except ArithmeticFault as error:
            self._fault('Numerical', str(error))
        except MatrixProtocolError as error:
            self._fault('Protocol', str(error))

    def tick(self, *, job=None, memory_ready=False, memory_response=None,
             response_ready=False, local_reset=False, reset=False,
             matrix_request_ready=True, matrix_result_ready=True,
             service_result_ready=True, service_done_ready=True, done_override=None):
        p = self.ports()
        p.update(job_fire=False, memory_fire=False, memory_response_fire=False,
                 matrix_request_fire=False, matrix_result_fire=False, response_fire=False)
        self.clock += 1
        if reset and self.state in ('idle', 'locked'):
            # Do not reset someone else's shared service. The coordinated
            # caller resets MatrixService, which remains poisoned until then.
            self.__init__(self.matrix, self.scalar, max_tokens=self.max_tokens)
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
                self.matrix_client = Fixed93MatrixClient(self.matrix, self, packed_tag=self._packed_tag)
                self.program = self._attention(job)
                self._advance()
            except PrefixFault as error:
                self._fault(error.status, error.detail)
        if p['memory'] is not None and memory_ready:
            p['memory_fire'] = True
            self.counts['write_requests' if self.request.write else 'read_requests'] += 1
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
        if self.matrix_client is not None and self.state != 'finish':
            draining = self.state == 'drain'
            offered = p['matrix'] if matrix_request_ready and not draining else None
            ready = (p['state'] in ('matrix_wait', 'packed_retire') and matrix_result_ready) or draining
            try:
                mp = self.matrix_client.tick(request=offered, result_ready=ready,
                    service_result_ready=service_result_ready, service_done_ready=service_done_ready,
                    abort=self.abort_pending, done_override=done_override)
                self.abort_pending = False
                if mp['request_fire']:
                    self._packed_tag = self.matrix_client.packed.tag
                    p['matrix_request_fire'] = True
                    self.counts['matrix_requests'] += 1
                    self.state = 'matrix_wait'
                if mp.get('packed_start_fire'):
                    self.matrix_request = None
                    self._advance()
                if mp.get('packed_step_fire'):
                    self.useful_macs += 16 * mp['packed_active_keys']
                    self.counts['packed_steps'] += 1
                    if self.matrix_request.index < 7:
                        self.matrix_request = None
                        self._advance()
                if mp.get('packed_borrow_fire'):
                    self.counts['packed_result_borrows'] += 1
                    self.matrix_request = None
                    self._advance(mp['packed_result'])
                if mp.get('packed_completion_fire'):
                    self.counts['packed_completions'] += 1
                    self._advance()
                if mp['result_fire']:
                    p['matrix_result_fire'] = True
                    self.counts['matrix_results'] += 1
                    self.matrix_request = None
                    if not draining:
                        self._advance(mp['result'])
                if self.state == 'drain' and not self.memory_pending and self.matrix_client.ports()['drained']:
                    self._finish(self.status, self.detail)
            except MatrixProtocolError as error:
                self._fault('Protocol', str(error))
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
        r = super().report()
        r.update(candidate='fixed93_packed_qk16_pv16_normalization_reuse_candidate',
                 normalization_evaluations_per_causal_key=1,
                 probability_use_repeats=8, normalization_reuses_per_causal_key=7,
                 scalar_schedule_changed=True,
                 integration_review_pending=True, fullblock_candidate_run_executed=False,
                 hardware_simulation=False, model_ticks_are_hardware_cycles=False,
                 packed_operand_staging_words=256,
                 staging_source='exclusive existing Qwen2Block denseWeights lease',
                 post_retirement_wide_result_cache_words=0,
                 source_selected_token_limit=128,
                 control_scope='software events; local SRAM and scalar cycles collapsed')
        return r
