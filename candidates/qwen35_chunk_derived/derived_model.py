"""Explicit pre-edge phase-2 protocol model, NOT execution of the Scala owner.

No FP arithmetic is performed here: memory, Exp4 and Add1/Mul2 loan services
are external response inputs. Tests supply SIMULATED integer binary32 services;
neither this model nor those helpers constitute independent HardFloat evidence.
Four integer payload words model exactly four 512-bit registers, not total area.
Reset is a model reset, NOT proof of coordinated physical fabric recovery.
"""
from dataclasses import dataclass
from enum import IntEnum

BEAT_BYTES = 64
HEADS = 16
CHUNK_ROWS = 64
STATE_BYTES = 1048576
PER_HEAD_STATE_BYTES = 65536
CHUNK_BYTES = 806912
PREPARED_ROW_BYTES = 25600
OUTPUT_ROW_BYTES = 4096
ADDRESS_LIMIT = 1 << 56
FULL_MASK = (1 << 64) - 1
HEAD_STRIDE = {16: 872448, 128: 1679360}
OFFSETS = dict(gates=0, q=4096, k=36864, v=69632, kb=102400,
               vb=135168, kbg=167936, qg=200704, ke=233472, pair=331776)
STATES = ('idle', 'issueRead', 'waitRead', 'issueLoan', 'waitLoan',
          'issueExp', 'waitExp', 'issueWrite', 'waitWrite', 'finish', 'locked')
STEPS = ('finalGate', 'chunkExp', 'rowGate', 'rowExp', 'remainingAdd',
         'remainingExp', 'readK', 'readQ', 'mulKb', 'mulKbg', 'mulQg', 'mulKe',
         'writeKb', 'writeKbg', 'writeQg', 'writeKe', 'readV', 'mulVb', 'writeVb',
         'pairRead', 'pairAdd', 'pairExp', 'pairWrite')


class Status(IntEnum):
    OK = 0
    MEMORY = 3
    UNSUPPORTED = 4
    BOUNDS = 5
    DEPENDENCY = 6
    PROTOCOL = 7
    NUMERICAL = 8


def uint(value, width, name):
    if (type(value) is not int and not isinstance(value, IntEnum)) or not 0 <= value < 1 << width:
        raise ValueError(f'{name} must fit UInt({width})')


def boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f'{name} must be bool')


def typed(value, cls, name):
    if not isinstance(value, cls):
        raise ValueError(f'{name} must be {cls.__name__}')


def widths(obj, spec):
    for name, width in spec:
        uint(getattr(obj, name), width, name)


@dataclass(frozen=True)
class Context:
    tag: int
    tokens: int
    cold: bool
    expected_generation: int
    vector_policy: int
    input: int
    state_in: int
    state_out: int
    output: int
    scratch: int

    def __post_init__(self):
        widths(self, (('tag', 32), ('tokens', 16), ('expected_generation', 32), ('vector_policy', 1)))
        boolean(self.cold, 'cold')
        widths(self, tuple((n, 64) for n in ('input', 'state_in', 'state_out', 'output', 'scratch')))


@dataclass(frozen=True)
class Committed:
    valid: bool
    generation: int
    state: int

    def __post_init__(self):
        boolean(self.valid, 'valid')
        widths(self, (('generation', 32), ('state', 64)))


@dataclass(frozen=True)
class Receipt:
    tag: int = 0
    expected_generation: int = 0
    head: int = 0
    chunk: int = 0
    phase: int = 0
    status: int = 0
    scratch_ack_bytes: int = 0
    output_ack_bytes: int = 0
    state_ack_bytes: int = 0
    drained: bool = False

    def __post_init__(self):
        widths(self, (('tag', 32), ('expected_generation', 32), ('head', 4), ('chunk', 1),
                      ('phase', 5), ('status', 8), ('scratch_ack_bytes', 64),
                      ('output_ack_bytes', 64), ('state_ack_bytes', 64)))
        boolean(self.drained, 'drained')


@dataclass(frozen=True)
class Phase1Result:
    receipt: Receipt
    read_bytes: int
    add_requests: int
    add_results: int
    cycles: int
    stage_complete: bool

    def __post_init__(self):
        typed(self.receipt, Receipt, 'receipt')
        widths(self, (('read_bytes', 64), ('add_requests', 7), ('add_results', 7), ('cycles', 64)))
        boolean(self.stage_complete, 'stage_complete')


@dataclass(frozen=True)
class Job:
    context: Context
    head: int
    chunk: int
    phase1_context: Context
    phase1_ready: Phase1Result

    def __post_init__(self):
        typed(self.context, Context, 'context')
        typed(self.phase1_context, Context, 'phase1_context')
        typed(self.phase1_ready, Phase1Result, 'phase1_ready')
        widths(self, (('head', 16), ('chunk', 16)))


@dataclass(frozen=True)
class MemoryRequest:
    address: int
    data: int
    mask: int
    tag: int
    write: bool

    def __post_init__(self):
        widths(self, (('address', 64), ('data', 512), ('mask', 64), ('tag', 64)))
        boolean(self.write, 'write')


@dataclass(frozen=True)
class MemoryResponse:
    tag: int
    data: int = 0
    error: bool = False

    def __post_init__(self):
        widths(self, (('tag', 64), ('data', 512)))
        boolean(self.error, 'error')


@dataclass(frozen=True)
class ScalarRequest:
    op: int
    a: int
    b: int = 0

    def __post_init__(self):
        widths(self, (('op', 3), ('a', 32), ('b', 32)))


@dataclass(frozen=True)
class ScalarResult:
    result: int
    error: bool = False

    def __post_init__(self):
        uint(self.result, 32, 'result')
        boolean(self.error, 'error')


@dataclass(frozen=True)
class LoanRequest:
    tag: int
    op: int
    a: int
    b: int
    inverse: int = 0

    def __post_init__(self):
        widths(self, (('tag', 32), ('op', 3), ('a', 512), ('b', 512), ('inverse', 32)))


@dataclass(frozen=True)
class LoanResult:
    tag: int
    status: int = 0
    value: int = 0

    def __post_init__(self):
        widths(self, (('tag', 32), ('status', 8), ('value', 512)))


@dataclass(frozen=True)
class PrivateDecay:
    context: Context
    head: int
    chunk: int
    value: int
    valid: bool


@dataclass(frozen=True)
class Result:
    receipt: Receipt
    decay: PrivateDecay
    read_bytes: int
    exp_requests: int
    exp_results: int
    add_requests: int
    add_results: int
    mul_requests: int
    mul_results: int
    cycles: int
    stage_complete: bool


@dataclass(frozen=True)
class Signals:
    job_ready: bool
    memory_request: object
    response_ready: bool
    scalar_request: object
    scalar_result_ready: bool
    loan_request: object
    loan_result_ready: bool
    loan_abort: bool
    reset_loan: bool
    done: object
    reset_required: bool


@dataclass(frozen=True)
class Events:
    before: Signals
    job_fire: bool
    memory_fire: bool
    response_fire: bool
    scalar_fire: bool
    scalar_result_fire: bool
    loan_fire: bool
    loan_result_fire: bool
    done_fire: bool


def spans(c):
    return ((c.input, c.tokens * PREPARED_ROW_BYTES), (c.state_in, STATE_BYTES),
            (c.state_out, STATE_BYTES), (c.output, c.tokens * OUTPUT_ROW_BYTES),
            (c.scratch, HEADS * HEAD_STRIDE[c.tokens]))


def admission_status(job, committed):
    c, r = job.context, job.phase1_ready
    p = r.receipt
    if c.expected_generation != committed.generation:
        return Status.DEPENDENCY
    if c.cold:
        if c.expected_generation != 0 or committed.valid:
            return Status.DEPENDENCY
    elif c.expected_generation == 0 or not committed.valid or c.state_in != committed.state:
        return Status.DEPENDENCY
    if (c.tokens not in HEAD_STRIDE or job.head >= 16 or
            job.chunk >= (2 if c.tokens == 128 else 1) or c.expected_generation == 0xFFFFFFFF):
        return Status.BOUNDS
    allocations = spans(c)
    if any(base % 64 or size == 0 or base + size > ADDRESS_LIMIT for base, size in allocations):
        return Status.BOUNDS
    if any(a < b + nb and b < a + na for i, (a, na) in enumerate(allocations)
           for b, nb in allocations[:i]):
        return Status.BOUNDS
    if c.vector_policy != 0:
        return Status.UNSUPPORTED
    if not (job.phase1_context == c and r.stage_complete and p.tag == c.tag
            and p.expected_generation == c.expected_generation and p.head == job.head
            and p.chunk == job.chunk and p.phase == 1 and p.status == Status.OK
            and p.drained and p.scratch_ack_bytes == 102400
            and p.output_ack_bytes == p.state_ack_bytes == 0
            and r.add_requests == r.add_results == 64
            and r.read_bytes == (102400 if c.tokens == 128 else 25600)):
        return Status.DEPENDENCY
    return Status.OK


def finite(word):
    return (word & 0x7F800000) != 0x7F800000


def finite_beat(value):
    return all(finite((value >> (32 * lane)) & 0xFFFFFFFF) for lane in range(16))


def exp_domain(word):
    return finite(word) and (bool(word >> 31) or (word & 0x7FFFFFFF) == 0)


def broadcast(word):
    return sum(word << (32 * lane) for lane in range(16))


class Owner:
    """Eleven explicit states, 23 micro-steps, at most one service outstanding.

    There is no local recovery port. Failed done retirement locks the owner.
    Tags prove only the currently outstanding transaction, never replay safety.
    Exclusive stable roots and valid stage-1 receipt provenance are external.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.state, self.step, self.job = 'idle', 'finalGate', None
        self.row = self.beat = self.pair_beat = self.lane = 0
        self.memory_sequence = self.loan_sequence = 0
        self.payload = [0, 0, 0, 0]
        self.final_cumulative = self.cumulative = self.beta = self.earlier_cumulative = 0
        self.difference = self.exp_g = self.exp_remaining = self.chunk_decay = 0
        self.memory_outstanding = self.scalar_outstanding = self.loan_outstanding = False
        self.status = Status.OK
        self.read_bytes = self.write_bytes = self.cycles = 0
        self.exp_requests = self.exp_results = self.add_requests = self.add_results = 0
        self.mul_requests = self.mul_results = 0

    def _go(self, step, state):
        self.step, self.state = step, state

    def _fail(self, status):
        self.status, self.state = status, 'finish'

    def _add(self):
        return self.step in ('remainingAdd', 'pairAdd')

    def _exp_argument(self):
        return (self.final_cumulative if self.step == 'chunkExp' else
                self.cumulative if self.step == 'rowExp' else self.difference)

    def _memory_request(self):
        if self.state not in ('issueRead', 'issueWrite'):
            return None
        j, s = self.job, self.step
        c = j.context
        base = c.scratch + (j.head & 15) * HEAD_STRIDE[c.tokens] + 65536 + (j.chunk & 1) * CHUNK_BYTES
        vector = self.row * 512 + self.beat * 64
        write = self.state == 'issueWrite'
        if write:
            name = {'writeKb': 'kb', 'writeKbg': 'kbg', 'writeQg': 'qg',
                    'writeKe': 'ke', 'writeVb': 'vb', 'pairWrite': 'pair'}[s]
            offset = self.row * 256 + self.pair_beat * 64 if s == 'pairWrite' else vector
            data = self.payload[{'writeKb': 2, 'writeKbg': 3, 'writeQg': 1}.get(s, 0)]
        else:
            name = {'finalGate': 'gates', 'rowGate': 'gates', 'readK': 'k',
                    'readQ': 'q', 'readV': 'v', 'pairRead': 'gates'}[s]
            offset = (63 * 64 if s == 'finalGate' else self.row * 64 if s == 'rowGate'
                      else (self.pair_beat * 16 + self.lane) * 64 if s == 'pairRead' else vector)
            data = 0
        return MemoryRequest(base + OFFSETS[name] + offset, data, FULL_MASK if write else 0,
                             (c.tag << 32) | self.memory_sequence, write)

    def peek(self, loan_reset_required=False):
        boolean(loan_reset_required, 'loan_reset_required')
        exp = self._exp_argument()
        scalar = ScalarRequest(4, exp, 0) if self.state == 'issueExp' and exp_domain(exp) else None
        loan = None
        if self.state == 'issueLoan' and not loan_reset_required:
            if self._add():
                a = self.final_cumulative if self.step == 'remainingAdd' else self.cumulative
                b = (self.cumulative if self.step == 'remainingAdd' else self.earlier_cumulative) ^ 0x80000000
            else:
                a = self.payload[{'mulKbg': 2, 'mulQg': 1}.get(self.step, 0)]
                b = broadcast(self.exp_g if self.step in ('mulKbg', 'mulQg') else
                              self.exp_remaining if self.step == 'mulKe' else self.beta)
            loan = LoanRequest(self.job.context.tag ^ self.loan_sequence, 1 if self._add() else 2, a, b)
        done = None
        if self.state == 'finish':
            j, c = self.job, self.job.context
            drained = (self.status == Status.OK and not self.memory_outstanding
                       and not self.scalar_outstanding and not self.loan_outstanding)
            complete = (drained and self.read_bytes == 235584 and self.write_bytes == 180224
                        and self.exp_requests == self.exp_results == 2209
                        and self.add_requests == self.add_results == 2144
                        and self.mul_requests == self.mul_results == 2560)
            receipt = Receipt(c.tag, c.expected_generation, j.head & 15, j.chunk & 1, 2,
                              int(self.status), self.write_bytes, 0, 0, drained)
            decay = PrivateDecay(c, j.head & 15, j.chunk & 1, self.chunk_decay if complete else 0, complete)
            done = Result(receipt, decay, self.read_bytes, self.exp_requests, self.exp_results,
                          self.add_requests, self.add_results, self.mul_requests, self.mul_results,
                          self.cycles, complete)
        return Signals(self.state == 'idle', self._memory_request(),
                       self.state in ('waitRead', 'waitWrite'), scalar, self.state == 'waitExp',
                       loan, self.state == 'waitLoan', False, False, done, self.status != Status.OK)

    def tick(self, *, job=None, committed=None, memory_ready=False, response=None,
             scalar_ready=False, scalar_result=None, loan_ready=False, loan_result=None,
             loan_busy=False, loan_reset_required=False, done_ready=False):
        for value, cls, name in ((job, Job, 'job'), (response, MemoryResponse, 'response'),
                                 (scalar_result, ScalarResult, 'scalar_result'), (loan_result, LoanResult, 'loan_result')):
            if value is not None:
                typed(value, cls, name)
        for name, value in (('memory_ready', memory_ready), ('scalar_ready', scalar_ready),
                            ('loan_ready', loan_ready), ('loan_busy', loan_busy),
                            ('loan_reset_required', loan_reset_required), ('done_ready', done_ready)):
            boolean(value, name)
        before = self.peek(loan_reset_required)
        e = Events(before, job is not None and before.job_ready,
                   before.memory_request is not None and memory_ready,
                   response is not None and before.response_ready,
                   before.scalar_request is not None and scalar_ready,
                   scalar_result is not None and before.scalar_result_ready,
                   before.loan_request is not None and loan_ready,
                   loan_result is not None and before.loan_result_ready,
                   before.done is not None and done_ready)
        old = self.state
        if e.job_fire:
            typed(committed, Committed, 'committed')
            self.reset()
            self.job = job
            self.status = admission_status(job, committed)
            if self.status == Status.OK and (response is not None or scalar_result is not None
                    or loan_result is not None or loan_busy or loan_reset_required):
                self.status = Status.PROTOCOL
            self.state = 'issueRead' if self.status == Status.OK else 'finish'
            return e
        if old not in ('idle', 'finish', 'locked'):
            self.cycles = (self.cycles + 1) & FULL_MASK
        if old == 'issueExp' and not exp_domain(self._exp_argument()):
            self._fail(Status.NUMERICAL)
        if old == 'issueLoan' and loan_reset_required:
            self._fail(Status.DEPENDENCY)
        if e.memory_fire or e.scalar_fire or e.loan_fire:
            if self.memory_outstanding or self.scalar_outstanding or self.loan_outstanding:
                raise AssertionError('overlapping service request')
        if e.memory_fire:
            self.memory_outstanding = True
            self.state = 'waitRead' if old == 'issueRead' else 'waitWrite'
        elif e.response_fire:
            if response.tag != (self.job.context.tag << 32) | self.memory_sequence:
                self._fail(Status.PROTOCOL)  # Wrong tag wins and preserves outstanding.
            elif response.error:
                self.memory_outstanding = False
                self._fail(Status.MEMORY)
            else:
                self.memory_outstanding = False
                self.memory_sequence = (self.memory_sequence + 1) & 0xFFFFFFFF
                if old == 'waitRead':
                    self.read_bytes += 64
                    if not finite_beat(response.data):
                        self._fail(Status.NUMERICAL)
                    else:
                        self._read_result(response.data)
                else:
                    self.write_bytes += 64
                    self._write_ack()
        elif e.loan_fire:
            self.loan_outstanding = True
            if self._add():
                self.add_requests += 1
            else:
                self.mul_requests += 1
            self.state = 'waitLoan'
        elif e.loan_result_fire:
            if loan_result.tag != self.job.context.tag ^ self.loan_sequence:
                self._fail(Status.PROTOCOL)
            elif loan_result.status != Status.OK:
                self.loan_outstanding = False
                self._fail(loan_result.status)
            elif not finite_beat(loan_result.value):
                self.loan_outstanding = False
                self._fail(Status.NUMERICAL)
            else:
                self.loan_outstanding = False
                self.loan_sequence = (self.loan_sequence + 1) & 0xFFFFFFFF
                if self._add():
                    self.add_results += 1
                else:
                    self.mul_results += 1
                self._loan_result(loan_result.value)
        elif e.scalar_fire:
            self.scalar_outstanding = True
            self.exp_requests += 1
            self.state = 'waitExp'
        elif e.scalar_result_fire:
            self.scalar_outstanding = False
            if scalar_result.error or not finite(scalar_result.result):
                self._fail(Status.NUMERICAL)
            else:
                self.exp_results += 1
                self._scalar_result(scalar_result.result)
        elif e.done_fire:
            self.state = 'idle' if self.status == Status.OK else 'locked'
        return e

    def _read_result(self, value):
        s = self.step
        if s == 'finalGate':
            self.final_cumulative = value & 0xFFFFFFFF
            self._go('chunkExp', 'issueExp')
        elif s == 'rowGate':
            self.cumulative, self.beta = value & 0xFFFFFFFF, (value >> 32) & 0xFFFFFFFF
            self._go('rowExp', 'issueExp')
        elif s in ('readK', 'readQ', 'readV'):
            self.payload[1 if s == 'readQ' else 0] = value
            nxt = {'readK': ('readQ', 'issueRead'), 'readQ': ('mulKb', 'issueLoan'),
                   'readV': ('mulVb', 'issueLoan')}[s]
            self._go(*nxt)
        elif s == 'pairRead':
            self.earlier_cumulative = value & 0xFFFFFFFF
            self._go('pairAdd', 'issueLoan')

    def _loan_result(self, value):
        s = self.step
        if self._add():
            self.difference = value & 0xFFFFFFFF
            self._go('remainingExp' if s == 'remainingAdd' else 'pairExp', 'issueExp')
        else:
            index, nxt, state = {'mulKb': (2, 'mulKbg', 'issueLoan'),
                'mulKbg': (3, 'mulQg', 'issueLoan'), 'mulQg': (1, 'mulKe', 'issueLoan'),
                'mulKe': (0, 'writeKb', 'issueWrite'), 'mulVb': (0, 'writeVb', 'issueWrite')}[s]
            self.payload[index] = value
            self._go(nxt, state)

    def _scalar_result(self, value):
        if self.step == 'chunkExp':
            self.chunk_decay = value
            self._go('rowGate', 'issueRead')
        elif self.step == 'rowExp':
            self.exp_g = value
            self._go('remainingAdd', 'issueLoan')
        elif self.step == 'remainingExp':
            self.exp_remaining, self.beat = value, 0
            self._go('readK', 'issueRead')
        elif self.step == 'pairExp':
            shift = self.lane * 32
            self.payload[0] = (self.payload[0] & ~(0xFFFFFFFF << shift)) | value << shift
            if self.lane != 15 and self.pair_beat * 16 + self.lane < self.row:
                self.lane += 1
                self._go('pairRead', 'issueRead')
            else:
                self._go('pairWrite', 'issueWrite')

    def _write_ack(self):
        s = self.step
        if s in ('writeKb', 'writeKbg', 'writeQg'):
            self._go({'writeKb': 'writeKbg', 'writeKbg': 'writeQg', 'writeQg': 'writeKe'}[s], 'issueWrite')
        elif s == 'writeKe':
            if self.beat == 7:
                self.beat = 0
                self._go('readV', 'issueRead')
            else:
                self.beat += 1
                self._go('readK', 'issueRead')
        elif s == 'writeVb':
            if self.beat == 7:
                self.pair_beat = self.lane = self.payload[0] = 0
                self._go('pairRead', 'issueRead')
            else:
                self.beat += 1
                self._go('readV', 'issueRead')
        elif s == 'pairWrite':
            if self.pair_beat == 3:
                if self.row == 63:
                    self.state = 'finish'
                else:
                    self.row += 1
                    self.beat = 0
                    self._go('rowGate', 'issueRead')
            else:
                self.pair_beat += 1
                self.lane = self.payload[0] = 0
                self._go('pairRead', 'issueRead') if self.pair_beat * 16 <= self.row else self._go('pairWrite', 'issueWrite')
