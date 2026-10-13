"""True chunk64 GDN candidate on addressed DDR and one shared Vector16.

No Matrix invocation or FP32-to-BF16 operand narrowing, hidden tensor SRAM,
BLAS, token-at-a-time recurrence, or new exp service is used. Prep already
normalized and scaled Q. Only the final core output rounds to BF16.
This is a software mapping candidate, not RTL or an 80%-throughput claim.
"""
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import struct

from ..prep.scalar import PrepScalar
from ..prep.model import CORE_ROW_BYTES, CORE_ELEMENTS
from ..prep.layout import PrepLayout, EQUAL_HEADS, GROUPED_35B, grouped_source_identity
from ..rms_owner import ROOT, SCALAR_SOURCE, SCALAR_SHA, ArithmeticFault, MemoryRequest, MemoryResponse, finite, sha
from ..typed_dense import TypedMemory, FULL_MASK
from ...qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from .vector import Vector16
from .cumsum import LEGACY_CUMSUM, GUARDED_CUMSUM, GuardedCumsum
from . import exp_policy as ep


CHUNK = 64
IMPLEMENTATION_SOURCES = ('model.py', 'vector.py', 'vector16.cpp', 'cumsum.py', 'exp_policy.py')
SOURCE_HASHES = {
    SCALAR_SOURCE: SCALAR_SHA,
    'integration/gemmini/EmitHeteroFP32Alu.scala': '83fb6b55fe4362b58ddf740f7bfccd16f86779bda68e2e6e879052749cad88b1',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/ElementwiseMemoryEngine.scala':
        'cb8a338051cce94dda613603df892bd0f43b6ea62423ad1f9d28b24f98b73845',
    'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py':
        'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18',
}


def require(ok, why):
    if not ok:
        raise ValueError('typed GDN chunk: ' + why)


def source_identity(vector_policy='legacy_vector_fatal_underflow',layout=EQUAL_HEADS,cumsum_policy=LEGACY_CUMSUM,exp_policy=ep.LEGACY_EXP):
    for name, digest in SOURCE_HASHES.items():
        require(sha((ROOT / name).read_bytes()) == digest, 'source drift: ' + name)
    return dict(cumsum_policy=cumsum_policy,cumsum_chisel_bound=False,
                cumsum_source_sha256=sha(Path(__file__).with_name('cumsum.py').read_bytes()),
                layout=dict(key_heads=layout.key_heads,value_heads=layout.value_heads,width=layout.width,core_row_bytes=layout.core_row_bytes),
                layout_source_sha256=sha((ROOT / "candidates/qwen35_gdn_prefill/prep/layout.py").read_bytes()),
                grouped_source=grouped_source_identity(ROOT) if layout==GROUPED_35B else None,
                source_sha256=dict(SOURCE_HASHES),
                implementation_sha256={name: sha((Path(__file__).parent / name).read_bytes())
                                       for name in IMPLEMENTATION_SOURCES},
                vector_underflow_policy=vector_policy,
                vector_exception_control_chisel_bound=(vector_policy == 'legacy_vector_fatal_underflow'),
                ieee_mode_integration_gap='ElementwiseMemoryEngine.scala binary fatal mask is still flags[4:1]; explicit per-job policy selection and physical shared Vector routing remain required',
                exp_policy=exp_policy, exp_identity=ep.identity(exp_policy),
                mapping='one_retained_16_lane_Add_Mul_resource_candidate',
                matrix_used=False, new_array=False, rtl_executed=False, native_acceptance=False,
                throughput_80_percent_achieved=False)


@dataclass(frozen=True)
class Matrix:
    base: int
    rows: int
    cols: int

    def address(self, row, col=0):
        require(0 <= row < self.rows and 0 <= col < self.cols and col % 16 == 0,
                'matrix beat index')
        return self.base + 4 * (row * self.cols + col)


def _shapes(dk, dv):
    return [('gates', 64, 16), ('q', 64, dk), ('k', 64, dk), ('v', 64, dv),
            ('kb', 64, dk), ('vb', 64, dv), ('kbg', 64, dk), ('qg', 64, dk),
            ('ke', 64, dk), ('kt', dk, 64), ('ket', dk, 64), ('pair', 64, 64),
            ('ut', 64, 64), ('intra', 64, 64), ('solvek', 64, dk), ('solvev', 64, dv),
            ('pred', 64, dv), ('vnew', 64, dv), ('inter', 64, dv), ('local', 64, dv),
            ('out', 64, dv), ('state_update', dk, dv), ('decay_state', dk, dv), ('next_state', dk, dv)]


@dataclass(frozen=True)
class ChunkJob:
    tag: int
    input: int
    state_in: int
    state_out: int
    output: int
    scratch: int
    tokens: int
    cold: bool = True
    expected_generation: int = 0
    heads: int = 16
    key_dim: int = 128
    value_dim: int = 128
    layout: PrepLayout = EQUAL_HEADS
    cumsum_policy: str = LEGACY_CUMSUM
    exp_policy: str = ep.LEGACY_EXP

    @property
    def chunks(self): return (self.tokens + 63) // 64
    @property
    def input_bytes(self): return self.tokens * self.layout.core_row_bytes
    @property
    def state_bytes(self): return self.heads * self.key_dim * self.value_dim * 4
    @property
    def output_bytes(self): return self.tokens * self.heads * self.value_dim * 2
    @property
    def write_bytes(self): return self.state_bytes + self.output_bytes
    @property
    def scratch_bytes(self):
        return self.heads * (self.key_dim * self.value_dim * 4 +
                self.chunks * sum(r * c * 4 for _, r, c in _shapes(self.key_dim, self.value_dim)))

    def validate(self, geometry=None,layout=EQUAL_HEADS,cumsum_policy=LEGACY_CUMSUM,exp_policy=ep.LEGACY_EXP):
        require(self.exp_policy==exp_policy,"explicit chunk exp policy identity")
        ep.validate_policy(exp_policy,layout)
        require(self.cumsum_policy==cumsum_policy and cumsum_policy in (LEGACY_CUMSUM,GUARDED_CUMSUM), "explicit cumsum policy identity")
        require(cumsum_policy==LEGACY_CUMSUM or layout==GROUPED_35B,"bounded cumsum only explicit35B")
        require(type(self.layout) is PrepLayout and self.layout==layout, "explicit input layout identity")
        require(type(self.tag) is int and 0 <= self.tag < 1 << 32, 'job tag')
        require(type(self.tokens) is int and 1 <= self.tokens <= 128, 'M1..128 only; true chunk64 padding')
        require(type(self.heads) is int and 1 <= self.heads <= self.layout.value_heads and
                type(self.key_dim) is int and self.key_dim in range(16, 129, 16) and
                type(self.value_dim) is int and self.value_dim in range(32, 129, 32), 'supported geometry')
        require(layout==EQUAL_HEADS or self.heads==32,"explicit35B requires all32 heads")
        require(geometry is None or geometry == (self.heads, self.key_dim, self.value_dim), 'owner geometry')
        require(type(self.cold) is bool and type(self.expected_generation) is int and
                0 <= self.expected_generation < (1 << 32) - 1 and
                (not self.cold or self.expected_generation == 0), 'cold/generation domain')
        spans = [(self.input, self.input_bytes), (self.state_in, self.state_bytes),
                 (self.output, self.output_bytes), (self.state_out, self.state_bytes),
                 (self.scratch, self.scratch_bytes)]
        for base, size in spans:
            require(type(base) is int and base >= 0 and base % 64 == 0 and
                    size > 0 and size % 64 == 0 and base + size <= 1 << 56, 'complete aligned 56-bit span')
        require(all(a + n <= b or b + m <= a for i, (a, n) in enumerate(spans)
                    for b, m in spans[:i]), 'input/state/output/scratch allocations must be disjoint')


class ScratchPlan:
    """SSA DDR allocation: every beat written once, ACKed, then locally readable.

    No workspace is published as a tensor. The transport enforces this owner's
    scratch capability and per-beat ACK visibility. All matrices live in DDR.
    """
    def __init__(self, job):
        self.initial, self.chunks = [], []
        next_address = job.scratch
        for _ in range(job.heads):
            self.initial.append(Matrix(next_address, job.key_dim, job.value_dim))
            next_address += job.key_dim * job.value_dim * 4
            head = []
            for _ in range(job.chunks):
                mats = {}
                for name, rows, cols in _shapes(job.key_dim, job.value_dim):
                    mats[name] = Matrix(next_address, rows, cols)
                    next_address += rows * cols * 4
                head.append(mats)
            self.chunks.append(head)
        require(next_address == job.scratch + job.scratch_bytes, 'scratch sizing')


@dataclass(frozen=True)
class ChunkResult:
    tag: int
    status: str | None
    write_bytes: int
    output: int
    state_out: int
    output_bytes: int
    state_bytes: int
    expected_generation: int
    model_ticks: int
    staging_complete: bool
    state_committed: bool = False
    history_committed: bool = False
    generation_advanced: bool = False


class ChunkOwner:
    def __init__(self, scalar, vector, *, heads=16, key_dim=128, value_dim=128, host_batch=False,layout=EQUAL_HEADS,cumsum_policy=LEGACY_CUMSUM,exp_policy=ep.LEGACY_EXP):
        require(isinstance(scalar, PrepScalar) and type(vector) is Vector16, 'caller-owned shared PrepScalar/Vector16')
        require(type(host_batch) is bool, 'host_batch must be an explicit bool')
        require(type(layout) is PrepLayout,"explicit layout profile")
        require(cumsum_policy in (LEGACY_CUMSUM,GUARDED_CUMSUM) and (cumsum_policy==LEGACY_CUMSUM or layout==GROUPED_35B),"supported cumsum layout policy")
        self.layout=layout
        self.cumsum_policy=cumsum_policy
        ep.validate_policy(exp_policy,layout,scalar,vector)
        self.exp_policy=exp_policy
        self.decay_baseline,self.decay_counts=Counter(),Counter()
        self.scalar, self.vector = scalar, vector
        self.host_batch = host_batch
        self.geometry = (heads, key_dim, value_dim)
        self.state, self.job, self.request, self.result = 'idle', None, None, None
        self.program, self.status, self.poison, self.numerical_detail = None, None, False, None
        self.ticks, self.start, self.sequence, self.ack_bytes = 0, 0, 0, 0
        self.counts, self.exp_stats = Counter(), Counter()
        self.scalar_baseline, self.vector_baseline, self.lane_baseline = Counter(), Counter(), Counter()
        self.scalar_counts, self.vector_counts, self.lane_counts = Counter(), Counter(), Counter()
        self.host_baseline, self.host_counts = Counter(), Counter()
        self.flag_baseline, self.flag_counts = Counter(), Counter()
        self.identity = None
        self.context = dict(phase='idle', head=None, chunk=None)
        self.position, self.first_numerical_failure = {}, None

    def ports(self):
        return dict(job_ready=self.state == 'idle' and not self.poison and
                    self.scalar.client is None and self.vector.client is None,
                    memory=self.request if self.state == 'issue' else None,
                    memory_response_ready=self.state in ('wait', 'drain'),
                    response=self.result if self.state == 'finish' else None,
                    reset_required=self.poison, state=self.state)

    def reset(self):
        require(self.state in ('idle', 'locked') and self.request is None and
                self.scalar.client is not self and self.vector.client is not self, 'reset requires drain and retired terminal')
        self.__init__(self.scalar, self.vector, heads=self.geometry[0], key_dim=self.geometry[1],
                      value_dim=self.geometry[2], host_batch=self.host_batch,layout=self.layout,cumsum_policy=self.cumsum_policy,exp_policy=self.exp_policy)

    def _phase(self, phase):
        self.context['phase'], self.position = phase, {}

    def _remember_failure(self, error, diagnostic=None):
        if self.first_numerical_failure is None:
            self.first_numerical_failure = dict(self.context, **self.position,
                memory_sequence=self.sequence,
                diagnostic=diagnostic if diagnostic is not None else getattr(error, 'diagnostic', None),
                reason=str(error))

    def _op(self, op, a, b):
        try:
            return self.vector.op(self, op, a, b)
        except ArithmeticFault as error:
            self._remember_failure(error)
            raise

    def _exp(self, raw):
        if not finite(raw) or (not raw >> 31 and raw & 0x7fffffff):
            error = ArithmeticFault('chunk exponential requires finite nonpositive input')
            self._remember_failure(error, dict(resource='PrepScalar', operation=ep.operation(self.exp_policy),
                a_words=[raw], b_words=[0], result_words=None, exception_flags=None))
            raise error
        magnitude = raw & 0x7fffffff
        self.exp_stats['calls'] += 1
        self.exp_stats['inputs_abs_ge_80'] += magnitude >= 0x42a00000
        self.exp_stats['saturated_abs_ge_80'] += self.exp_policy==ep.LEGACY_EXP and magnitude >= 0x42a00000
        self.exp_stats['max_abs_input_word'] = max(self.exp_stats['max_abs_input_word'], magnitude)
        try:
            result = self.scalar.op(self, ep.operation(self.exp_policy), raw)
            self.exp_stats['subnormal_outputs'] += 0 < (result & 0x7fffffff) < 0x00800000
            self.exp_stats['zero_outputs'] += not result & 0x7fffffff
            return result
        except ArithmeticFault as error:
            self._remember_failure(error, dict(resource='PrepScalar', operation=ep.operation(self.exp_policy),
                a_words=[raw], b_words=[0], result_words=None, exception_flags=None))
            raise

    def _cumsum_add(self, a, b):
        self.counts['cumsum_add_issues'] += 1
        return self._op('add', [a], [b])[0]

    def _mul_add(self, a, b, total):
        if not self.host_batch:
            return self._op('add', total, self._op('mul', a, b))
        try:
            return self.vector.mul_add(self, a, b, total)
        except ArithmeticFault as error:
            self._remember_failure(error)
            raise

    def _read(self, address):
        raw = yield (address, None)
        words = list(struct.unpack('<16I', raw))
        if not all(finite(v) for v in words):
            error = ArithmeticFault('nonfinite FP32 addressed input/intermediate')
            self._remember_failure(error, dict(resource='TypedMemory', operation='read64',
                address=address, result_words=words, exception_flags=None))
            raise error
        return words

    def _write(self, address, words):
        require(len(words) == 16, 'full FP32 beat')
        yield (address, struct.pack('<16I', *words))

    def _transpose(self, source, destination):
        # The largest local tile is 16x16 FP32 = 1024 bytes.
        for r in range(0, source.rows, 16):
            for c in range(0, source.cols, 16):
                tile = []
                for i in range(16):
                    tile.append((yield from self._read(source.address(r + i, c))))
                for i in range(16):
                    yield from self._write(destination.address(c + i, r), [tile[j][i] for j in range(16)])

    def _matmul(self, a, b, destination, *, factor=None):
        require(a.cols == b.rows and (destination.rows, destination.cols) == (a.rows, b.cols), 'matmul dimensions')
        for row in range(a.rows):
            for col in range(0, b.cols, 16):
                total = [0] * 16
                # Each output lane reduces K in ascending order from +0.
                # Separate Mul then Add, never FMA or a tree reduction.
                for start in range(0, a.cols, 16):
                    av = yield from self._read(a.address(row, start))
                    for lane in range(16):
                        self.position = dict(row=row, column=col, reduction_k=start + lane)
                        bv = yield from self._read(b.address(start + lane, col))
                        total = self._mul_add([av[lane]] * 16, bv, total)
                if factor is not None:
                    self.position = dict(row=row, column=col, reduction_k=None, node='pair_decay_mul')
                    weights = yield from self._read(factor.address(row, col))
                    total = self._op('mul', total, weights)
                yield from self._write(destination.address(row, col), total)

    def _solve(self, lower, rhs, destination):
        # Unit diagonal is implicit. Never divide by stored ut diagonal.
        for row in range(64):
            for col in range(0, rhs.cols, 16):
                total = [0] * 16
                for start in range(0, row, 16):
                    coeff = yield from self._read(lower.address(row, start))
                    for lane in range(min(16, row - start)):
                        self.position = dict(row=row, column=col, reduction_k=start + lane)
                        solved = yield from self._read(destination.address(start + lane, col))
                        total = self._mul_add([coeff[lane]] * 16, solved, total)
                incoming = yield from self._read(rhs.address(row, col))
                self.position = dict(row=row, column=col, reduction_k=None, node='rhs_subtract')
                yield from self._write(destination.address(row, col),
                                      self._op('add', incoming, [x ^ 0x80000000 for x in total]))

    def _binary(self, a, b, out, *, subtract=False):
        for row in range(a.rows):
            for col in range(0, a.cols, 16):
                self.position = dict(row=row, column=col)
                av = yield from self._read(a.address(row, col))
                bv = yield from self._read(b.address(row, col))
                if subtract: bv = [x ^ 0x80000000 for x in bv]
                yield from self._write(out.address(row, col), self._op('add', av, bv))

    def _compute(self, j):
        plan = ScratchPlan(j)
        for head in range(j.heads):
            self.context.update(head=head, chunk=None)
            self._phase('initial_state')
            previous = plan.initial[head]
            for row in range(j.key_dim):
                for col in range(0, j.value_dim, 16):
                    words = [0] * 16 if j.cold else (yield from self._read(
                        j.state_in + ((head * j.key_dim + row) * j.value_dim + col) * 4))
                    yield from self._write(previous.address(row, col), words)
            for chunk, m in enumerate(plan.chunks[head]):
                self.context['chunk'] = chunk
                self._phase('load_prep_and_cumsum')
                self.counts['chunks_started'] += 1
                cumulative = 0
                guarded = (GuardedCumsum(self._cumsum_add)
                           if self.cumsum_policy==GUARDED_CUMSUM else None)
                for row in range(64):
                    self.position = dict(row=row)
                    token = chunk * 64 + row
                    if token < j.tokens:
                        gates = yield from self._read(j.input + token * j.layout.core_row_bytes + (3*j.layout.vector_elements + head * 16) * 4)
                        g, beta = gates[:2]
                        if any(gates[2:]) or (not g >> 31 and g & 0x7fffffff) or (beta >> 31 and beta & 0x7fffffff) or beta & 0x7fffffff > 0x3f800000:
                            error = ArithmeticFault('prep gate domain/padding')
                            self._remember_failure(error, dict(resource='gate_validation', operation='domain_padding',
                                a_words=gates, result_words=None, exception_flags=None))
                            raise error
                    else:
                        g, beta = 0, 0
                    cumulative = (guarded.step(g) if guarded is not None else
                                  self._cumsum_add(cumulative, g))
                    self.counts['cumsum_terms'] += 1
                    yield from self._write(m['gates'].address(row), [cumulative, beta] + [0] * 14)
                    for role, name, dim in ((0, 'q', j.key_dim), (1, 'k', j.key_dim), (2, 'v', j.value_dim)):
                        for col in range(0, dim, 16):
                            words = ([0] * 16 if token >= j.tokens else (yield from self._read(
                                j.input + token * j.layout.core_row_bytes + (role * j.layout.vector_elements + head * j.layout.width + col) * 4)))
                            yield from self._write(m[name].address(row, col), words)
                self._phase('chunk_decay_exp')
                chunk_decay = self._exp(cumulative)
                for row in range(64):
                    self._phase('cumulative_and_remaining_decay')
                    self.position = dict(row=row)
                    gate = yield from self._read(m['gates'].address(row))
                    cum, beta = gate[:2]
                    exp_g = self._exp(cum)
                    rem = self._op('add', [cumulative], [cum ^ 0x80000000])[0]
                    exp_rem = self._exp(rem)
                    for col in range(0, j.key_dim, 16):
                        self._phase('prepare_key_query_products')
                        self.position = dict(row=row, column=col)
                        k = yield from self._read(m['k'].address(row, col))
                        q = yield from self._read(m['q'].address(row, col))
                        kb = self._op('mul', k, [beta] * 16)
                        for name, words in (('kb', kb), ('kbg', self._op('mul', kb, [exp_g] * 16)),
                                            ('qg', self._op('mul', q, [exp_g] * 16)),
                                            ('ke', self._op('mul', k, [exp_rem] * 16))):
                            yield from self._write(m[name].address(row, col), words)
                    for col in range(0, j.value_dim, 16):
                        self._phase('prepare_vbeta')
                        self.position = dict(row=row, column=col)
                        v = yield from self._read(m['v'].address(row, col))
                        yield from self._write(m['vb'].address(row, col), self._op('mul', v, [beta] * 16))
                    for col in range(0, 64, 16):
                        self._phase('pairwise_decay')
                        self.position = dict(row=row, column=col)
                        pair = [0] * 16
                        for lane in range(min(16, max(0, row - col + 1))):
                            earlier = yield from self._read(m['gates'].address(col + lane))
                            diff = self._op('add', [cum], [earlier[0] ^ 0x80000000])[0]
                            pair[lane] = self._exp(diff)
                        self.counts['upper_triangle_masked'] += 16 - min(16, max(0, row - col + 1))
                        yield from self._write(m['pair'].address(row, col), pair)
                self._phase('transpose_k'); yield from self._transpose(m['k'], m['kt'])
                self._phase('transpose_decayed_k'); yield from self._transpose(m['ke'], m['ket'])
                self._phase('ut_matmul'); yield from self._matmul(m['kb'], m['kt'], m['ut'], factor=m['pair'])
                self._phase('intra_matmul'); yield from self._matmul(m['q'], m['kt'], m['intra'], factor=m['pair'])
                self._phase('solve_v'); yield from self._solve(m['ut'], m['vb'], m['solvev'])
                self._phase('solve_k'); yield from self._solve(m['ut'], m['kbg'], m['solvek'])
                self._phase('predict_matmul'); yield from self._matmul(m['solvek'], previous, m['pred'])
                self._phase('vnew_subtract'); yield from self._binary(m['solvev'], m['pred'], m['vnew'], subtract=True)
                self._phase('inter_matmul'); yield from self._matmul(m['qg'], previous, m['inter'])
                self._phase('local_matmul'); yield from self._matmul(m['intra'], m['vnew'], m['local'])
                self._phase('output_add'); yield from self._binary(m['inter'], m['local'], m['out'])
                self._phase('state_update_matmul'); yield from self._matmul(m['ket'], m['vnew'], m['state_update'])
                self._phase('state_decay')
                for row in range(j.key_dim):
                    for col in range(0, j.value_dim, 16):
                        self.position = dict(row=row, column=col)
                        state = yield from self._read(previous.address(row, col))
                        yield from self._write(m['decay_state'].address(row, col), self._op('mul', state, [chunk_decay] * 16))
                self._phase('state_add'); yield from self._binary(m['decay_state'], m['state_update'], m['next_state'])
                self._phase('output_bf16_materialization')
                for row in range(min(64, j.tokens - chunk * 64)):
                    for col in range(0, j.value_dim, 32):
                        low = yield from self._read(m['out'].address(row, col))
                        high = yield from self._read(m['out'].address(row, col + 16))
                        packed = [((x + 0x7fff + ((x >> 16) & 1)) & 0xffffffff) >> 16 for x in low + high]
                        if any(x & 0x7f80 == 0x7f80 for x in packed):
                            error = ArithmeticFault('nonfinite BF16 output rounding')
                            self.position = dict(row=row, column=col)
                            self._remember_failure(error, dict(resource='bf16_materialization', operation='bf16_rne',
                                a_words=low + high, result_words=packed, exception_flags=None))
                            raise error
                        yield (j.output + (((chunk * 64 + row) * j.heads + head) * j.value_dim + col) * 2,
                               struct.pack('<32H', *packed))
                previous = m['next_state']
                self.counts['chunks_completed'] += 1
            self._phase('state_staging_write')
            for row in range(j.key_dim):
                for col in range(0, j.value_dim, 16):
                    words = yield from self._read(previous.address(row, col))
                    yield from self._write(j.state_out + ((head * j.key_dim + row) * j.value_dim + col) * 4, words)

    def _finish(self, status):
        self.status, self.poison = status, self.poison or status is not None
        if self.scalar.client is self:
            self.scalar_counts = self.scalar.calls - self.scalar_baseline
            self.decay_counts = getattr(self.scalar,'decay_internal_calls',Counter()) - self.decay_baseline
            self.scalar.release(self)
        if self.vector.client is self:
            self.vector_counts = self.vector.calls - self.vector_baseline
            self.lane_counts = self.vector.lane_ops - self.lane_baseline
            self.host_counts = self.vector.host_calls - self.host_baseline
            self.flag_counts = self.vector.flags - self.flag_baseline
            self.vector.release(self)
        self.program, self.request = None, None
        j = self.job
        self.result = ChunkResult(j.tag, status, self.ack_bytes, j.output, j.state_out,
                                  j.output_bytes, j.state_bytes, j.expected_generation,
                                  self.ticks - self.start, status is None)
        self.state = 'finish'

    def _advance(self, data=None):
        try:
            address, output = self.program.send(data)
            require(self.sequence < 1 << 32, 'memory sequence overflow')
            self.request = MemoryRequest(address, (self.job.tag << 32) | self.sequence, output)
            self.sequence += 1
            self.state = 'issue'
        except StopIteration:
            self._finish(None if self.ack_bytes == self.job.write_bytes else 'Protocol')
        except ArithmeticFault as error:
            self._remember_failure(error)
            self.numerical_detail = str(error)
            self._finish('Numerical')

    def tick(self, *, job=None, memory_ready=False, memory_response=None,
             response_ready=False, abort=False, reset=False):
        p = self.ports()
        p.update(job_fire=False, memory_fire=False, memory_response_fire=False, response_fire=False)
        self.ticks += 1
        if reset and self.state in ('idle', 'locked'):
            self.reset(); p['job_ready'] = False
            return p
        if reset and self.state == 'finish':
            raise ValueError('typed GDN chunk: reset cannot erase held completion')
        fault = abort or reset
        if fault:
            p['job_ready'], p['memory'] = False, None
            self.poison = True
            if self.state in ('wait', 'drain'):
                self.status, self.state = self.status or 'Aborted', 'drain'
            elif self.state in ('issue', 'finish'):
                self._finish(self.status or 'Aborted'); p['response'] = None
            elif self.state == 'idle': self.state = 'locked'
        if not fault and job is not None and p['job_ready']:
            require(type(job) is ChunkJob, 'immutable ChunkJob')
            job.validate(self.geometry,self.layout,self.cumsum_policy,self.exp_policy)
            ep.validate_policy(self.exp_policy,self.layout,self.scalar,self.vector)
            self.identity = source_identity(self.vector.exception_policy,self.layout,self.cumsum_policy,self.exp_policy)
            require(self.scalar.acquire(self) and self.vector.acquire(self), 'shared leases')
            self.job, self.start, self.status, self.numerical_detail = job, self.ticks, None, None
            self.context, self.position, self.first_numerical_failure = dict(phase='admitted', head=None, chunk=None), {}, None
            self.sequence, self.ack_bytes, self.counts, self.exp_stats = 0, 0, Counter(), Counter()
            self.scalar_baseline = self.scalar.calls.copy()
            self.decay_baseline = getattr(self.scalar,'decay_internal_calls',Counter()).copy()
            self.decay_counts = Counter()
            self.vector_baseline, self.lane_baseline = self.vector.calls.copy(), self.vector.lane_ops.copy()
            self.host_baseline, self.host_counts = self.vector.host_calls.copy(), Counter()
            self.flag_baseline, self.flag_counts = self.vector.flags.copy(), Counter()
            self.scalar_counts, self.vector_counts, self.lane_counts = Counter(), Counter(), Counter()
            self.program = self._compute(job)
            p['job_fire'] = True
            self._advance()
        if not fault and p['memory'] is not None and memory_ready:
            p['memory_fire'] = True
            self.counts['write_requests' if self.request.write else 'read_requests'] += 1
            self.state = 'wait'
        if p['memory_response_ready'] and memory_response is not None:
            p['memory_response_fire'] = True
            q, r = self.request, memory_response
            require(type(r) is MemoryResponse, 'typed response')
            bad = type(r.tag) is not int or r.tag != q.tag or type(r.nbytes) is not int or r.nbytes != 64 or type(r.error) is not bool
            status = 'Protocol' if bad else 'Memory' if r.error else None
            if not q.write and status is None and (type(r.data) is not bytes or len(r.data) != 64):
                status = 'Protocol'
            self.counts['memory_responses'] += 1
            if q.write and status is None:
                self.counts['write_acks'] += 1
                if self.job.scratch <= q.address < self.job.scratch + self.job.scratch_bytes:
                    self.counts['scratch_ack_bytes'] += 64
                else: self.ack_bytes += 64
            if self.state == 'drain':
                self._finish(self.status if self.status != 'Aborted' else status or self.status)
            elif status is not None: self._finish(status)
            elif q.write: self._advance()
            else: self._advance(r.data)
        if p['response'] is not None and response_ready:
            p['response_fire'] = True
            self.counts['owner_results'] += 1
            self.state, self.result = ('locked' if self.poison else 'idle'), None
        return p

    def report(self):
        active = self.state not in ('idle', 'finish', 'locked')
        return dict(scope='TRUE_CHUNK64_GDN_SOFTWARE_MAPPING', identity=self.identity, status=self.status,
                    numerical_detail=self.numerical_detail, accepted=dict(self.counts), exp=dict(self.exp_stats),
                    first_numerical_failure=self.first_numerical_failure,
                    scalar_calls=dict(self.scalar.calls - self.scalar_baseline if active else self.scalar_counts),
                    vector_issue_counts=dict(self.vector.calls - self.vector_baseline if active else self.vector_counts),
                    vector_lane_operations=dict(self.vector.lane_ops - self.lane_baseline if active else self.lane_counts),
                    host_batch=self.host_batch,
                    host_call_counts=dict(self.vector.host_calls - self.host_baseline if active else self.host_counts),
                    vector_exception_flag_counts=dict(self.vector.flags - self.flag_baseline if active else self.flag_counts),
                    physical_vector_lanes=16, vector_instances=1, scalar_instances_created=0,
                    arithmetic='FP32_each_Mul_Add_RNE_ascending_K_no_FMA',
                    transpose_tile_fp32_payload_bytes=1024,
                    hardware_register_allocation_established=False,
                    python_diagnostic_storage=dict(adapter_fp32_buffer_words=64, adapter_lane_flag_words=16,
                        adapter_issue_flag_words=2,
                        vector_failure_capture_max_words=64, peak_live_python_storage_bytes=None,
                        suspended_generator_locals='Retained across yield: at least nine FP32 lists in _compute, '
                            'plus nested helper locals and adapter buffers; no proven register or live-list bound.'),
                    scratch_ddr_bytes=None if self.job is None else self.job.scratch_bytes,
                    production_geometry=self.geometry == (self.layout.value_heads,128,128),
                    cumsum_policy=self.cumsum_policy,
                    chunk_exp_policy=self.exp_policy,
                    decay_internal_calls=dict(getattr(self.scalar,'decay_internal_calls',Counter())-self.decay_baseline if active else self.decay_counts),
                    cumsum_hardware_binding=False,
                    input_core_row_bytes=self.layout.core_row_bytes,
                    input_role_elements=self.layout.vector_elements,
                    state_fp32_bytes=self.geometry[0]*self.geometry[1]*self.geometry[2]*4,
                    synthetic_reduced_dimensions=self.geometry[1:]!=(128,128),
                    state_committed=False, history_committed=False, generation_advanced=False,
                    hardware_cycles=None, rtl_executed=False, native_acceptance=False,
                    throughput_80_percent_achieved=False)


class TypedChunkDriver:
    """One memory request, exact full-beat writes and ACKs, held staging receipt.

    Successful terminal consumption exposes a receipt only. Neither output nor
    state is published here. A caller's joint block commit must validate both
    complete spans, publish them together, and then advance its generation.
    For warm calls, published_state_base is the caller's last committed state.
    """
    def __init__(self, owner, memory, job, *, current_generation=0, published_state_base=None):
        require(type(owner) is ChunkOwner and type(memory) is TypedMemory and type(job) is ChunkJob, 'typed resources')
        job.validate(owner.geometry,owner.layout,owner.cumsum_policy,owner.exp_policy)
        ep.validate_policy(owner.exp_policy,owner.layout,owner.scalar,owner.vector)
        require(owner.ports()['job_ready'] and memory.pending is None, 'drained unleased resources')
        require(type(current_generation) is int and current_generation == job.expected_generation, 'generation dependency')
        require((job.cold and current_generation == 0 and published_state_base is None) or
                (not job.cold and current_generation > 0 and published_state_base == job.state_in), 'last published state identity')
        self.input = memory.exact(job.input, job.input_bytes, readable=True)
        self.sources = [self.input]
        if not job.cold: self.sources.append(memory.exact(job.state_in, job.state_bytes, readable=True))
        for r in self.sources:
            require(not r.readonly and r.written == r.acknowledged == set(range(0, r.extent, 64)), 'actual producer data/ACK and publication')
        self.output = memory.exact(job.output, job.output_bytes, readable=False)
        self.state_out = memory.exact(job.state_out, job.state_bytes, readable=False)
        self.scratch = memory.exact(job.scratch, job.scratch_bytes, readable=False)
        self.owner, self.memory, self.job = owner, memory, job
        self.resource_identity = (id(owner), id(memory), id(owner.scalar), id(owner.vector),
                                  owner.vector.resource_address, owner.host_batch, owner.vector.exception_policy, owner.vector.fatal_mask,owner.layout,owner.cumsum_policy,owner.exp_policy,getattr(owner.scalar,'enable_ieee_exp',False))
        self.source_hashes = tuple(sha(r.raw()) for r in self.sources)
        self.pending, self.response, self.aborted, self.counts = None, None, False, Counter()
        self.pending_request, self.pending_write = None, None
        require(owner.tick(job=job)['job_fire'], 'chunk admission')

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             abort=False, reset=False, read_error=False, ack_error=False,
             read_tag=None, read_nbytes=None, ack_tag=None, ack_nbytes=None):
        require(self.response is None, 'already retired')
        require(self.resource_identity == (id(self.owner), id(self.memory), id(self.owner.scalar),
                id(self.owner.vector), self.owner.vector.resource_address, self.owner.host_batch, self.owner.vector.exception_policy, self.owner.vector.fatal_mask,self.owner.layout,self.owner.cumsum_policy,self.owner.exp_policy,getattr(self.owner.scalar,'enable_ieee_exp',False)), 'resources replaced')
        p = self.owner.ports()
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
            require(self.pending is not None, 'unsolicited physical response')
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
            require(self.pending is None, 'multiple physical obligations')
            q = e['memory']
            region = self.memory._resolve(q.address)
            self.pending_request = q
            if q.write:
                require(any(region is r for r in (self.output, self.state_out, self.scratch)) and len(q.data) == 64, 'write escaped allocation')
                self.memory.begin_write(WriteCommand(q.address, 1, q.tag))
                self.memory.write_data(struct.unpack('<32H', q.data), True, mask=FULL_MASK)
                self.pending_write = (self.memory.pending, tuple(self.memory.pending))
                self.pending = MemoryResponse(q.tag)
                self.counts['write_bytes'] += 64
            else:
                if region is self.scratch:
                    offset = q.address - region.base
                    require(offset in region.written and offset in region.acknowledged and not region.published,
                            'scratch read before this owner accepted write ACK')
                    region.check()
                    raw = bytes(region.storage[64 + offset:128 + offset])
                    self.counts['scratch_read_bytes'] += 64
                else:
                    require(any(region is r for r in self.sources), 'read escaped published input/previous state')
                    raw = self.memory.read64(q.address)
                    self.counts['source_read_bytes'] += 64
                self.pending = MemoryResponse(q.tag, raw)
                self.counts['read_bytes'] += 64
        if e['response_fire']:
            require(self.pending is None and self.memory.pending is None, 'terminal before drain')
            require(self.source_hashes == tuple(sha(r.raw()) for r in self.sources), 'published source changed')
            self.response = e['response']
            if self.response.status is None:
                require(self.owner.identity == source_identity(self.owner.vector.exception_policy,self.owner.layout,self.owner.cumsum_policy,self.owner.exp_policy), 'source changed during execution')
                require(self.response.staging_complete and self.response.write_bytes == self.job.write_bytes, 'complete double-span receipt')
                for r in (self.output, self.state_out, self.scratch):
                    require(not r.published and r.written == r.acknowledged == set(range(0, r.extent, 64)), 'full staging ACK coverage')
        return e

    def report(self):
        return dict(owner=self.owner.report(), complete=self.response is not None,
                    status=None if self.response is None else self.response.status, counts=dict(self.counts),
                    staging_complete=self.response is not None and self.response.staging_complete,
                    output_published=self.output.published, state_published=self.state_out.published,
                    state_committed=False, history_committed=False, generation_advanced=False,
                    input_sha256=list(self.source_hashes), output_sha256=sha(self.output.raw()),
                    state_sha256=sha(self.state_out.raw()))
