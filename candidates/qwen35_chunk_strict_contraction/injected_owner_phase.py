"""Test-only strict phase injection into the unchanged real ChunkOwner.

This is NOT a selectable owner arithmetic policy or a full ChunkJob program.
Synthetic phase operands are written through the real driver's scratch path,
then the original _matmul runs through real tick/response/ACK/drain control.
No preceding numerical producer is qualified. No output/state writes are
generated: even exhausting this phase produces the owner's Protocol result,
never a successful complete-chunk staging receipt.
"""
from candidates.qwen35_gdn_prefill.chunk.model import (
    ChunkOwner, ChunkJob, ScratchPlan, LEGACY_MATMUL, require,
)
from candidates.qwen35_gdn_prefill.rms_owner import ArithmeticFault as OwnerArithmeticFault
from .model import ArithmeticFault, Matrix, validate_contraction
from .upstream_coroutine import StrictUpstreamCoroutine


class InjectedOwnerPhase:
    """Explicit instance-local test hook; production class methods stay intact.

    The supplied owner's Scalar/Vector leases remain real and are acquired and
    released by ChunkOwner.tick/_finish. Vector arithmetic is NOT called: this
    hook substitutes strict integer software _op and reports its counts apart
    from the owner's (zero) native Vector operation counts.
    Call detach after the failed terminal is consumed and before owner reuse.
    """
    def __init__(self, owner, job, *, phase, operands, observe=None):
        require(type(owner) is ChunkOwner and type(job) is ChunkJob, 'exact test resources')
        require(owner.ports()['job_ready'] and owner.job is None, 'fresh unadmitted test owner')
        require(not owner.host_batch and owner.matmul_policy == LEGACY_MATMUL,
                'injected phase requires original separate Mul/Add row schedule')
        require(job.heads == 1 and job.tokens == 64 and job.key_dim == job.value_dim == 128,
                'injected one-head chunk64 full K128 fixture')
        job.validate(owner.geometry, owner.layout, owner.cumsum_policy, owner.exp_policy,
                     owner.matmul_policy)
        mats = ScratchPlan(job).chunks[0][0]
        names = ('kb' if phase == 5 else 'q', 'kt', 'pair', 'ut' if phase == 5 else 'intra')
        selected = tuple(mats[name] for name in names)
        validate_contraction(*(Matrix(m.base, m.rows, m.cols) for m in selected), phase)
        require(type(operands) is tuple and len(operands) == 3 and
                all(type(raw) is bytes and len(raw) == m.rows * m.cols * 4
                    for raw, m in zip(operands, selected)), 'complete injected operand bytes')
        require('_compute' not in owner.__dict__ and '_op' not in owner.__dict__,
                'no stacked instance test hooks')
        self.owner, self.job, self.phase = owner, job, phase
        self.matrices, self.operands = selected, operands
        self.strict = StrictUpstreamCoroutine(observe=observe)
        self.fixture_write_beats, self.phase_exhausted = 0, False
        # Deliberately visible injection, not a new production policy or clone.
        owner._compute, owner._op = self._compute, self._op

    def detach(self):
        owner = self.owner
        require(owner.state in ('idle', 'locked') and owner.request is None and
                owner.program is None and owner.scalar.client is not owner and
                owner.vector.client is not owner, 'detach requires drain and retired terminal')
        require(owner.__dict__.get('_compute') == self._compute and
                owner.__dict__.get('_op') == self._op, 'injected hooks replaced')
        del owner._compute, owner._op

    def _op(self, operation, a, b):
        owner = self.owner
        require(owner.scalar.client is owner and owner.vector.client is owner,
                'strict injection without real owner leases')
        self.strict.position = owner.position
        try:
            return self.strict._op(operation, a, b)
        except ArithmeticFault as fault:
            # The actual owner's _advance catches only its own ArithmeticFault.
            # Preserve strict flags/context while entering its Numerical path.
            error = OwnerArithmeticFault(str(fault))
            error.diagnostic = dict(resource='injected_strict_integer_software',
                                    stage=fault.stage, reduction_k=fault.k,
                                    lane=fault.lane, result_word=fault.word,
                                    exception_flags=fault.flags)
            raise error from fault

    def _compute(self, job):
        require(job is self.job, 'one-shot injected job identity')
        owner = self.owner
        owner.context = dict(phase='injected_fixture_writes', head=0, chunk=0)
        # Every synthetic operand beat is accepted, physically written and ACKed
        # by TypedChunkDriver before the actual matmul reads it. Do not prefill
        # scratch or invent ACK sets; this is transport, not producer arithmetic.
        for m, raw in zip(self.matrices, self.operands):
            for offset in range(0, len(raw), 64):
                yield m.base + offset, raw[offset:offset + 64]
                self.fixture_write_beats += 1
        owner._phase('ut_matmul' if self.phase == 5 else 'intra_matmul')
        a, kt, pair, destination = self.matrices
        yield from owner._matmul(a, kt, destination, factor=pair)
        self.phase_exhausted = True
        # No job.output/state_out write is possible here. The unchanged owner
        # rejects incomplete job.write_bytes with Protocol on StopIteration.
