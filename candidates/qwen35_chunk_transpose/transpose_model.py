"""Pure pre-edge protocol model for the private phase3 THEN phase4 proposal.

This is NOT Scala, Chisel, RTL, a transport, an arithmetic service, receipt
authentication, or proof of actual wiring. Accepted memory responses/ACKs are
caller-supplied SIMULATED inputs. Exactly sixteen 512-bit integers model the
1024-byte tile payload; context/control/counters are additional. Finite FP32
words move only as bits, with no floating-point conversion or arithmetic.
reset() resets this Python object only, never the shared physical transport.
"""
from dataclasses import dataclass
from enum import IntEnum

BEAT_BYTES = 64
HEADS = 16
STATE_BYTES = 1048576
PER_HEAD_STATE_BYTES = 65536
CHUNK_BYTES = 806912
PREPARED_ROW_BYTES = 25600
OUTPUT_ROW_BYTES = 4096
ADDRESS_LIMIT = 1 << 56
FULL_MASK = (1 << 64) - 1
HEAD_STRIDE = {16: 872448, 128: 1679360}
SOURCE_OFFSETS = (36864, 233472)
DESTINATION_OFFSETS = (266240, 299008)
STATES = ('idle', 'issueRead', 'waitRead', 'issueWrite', 'waitWrite', 'finish', 'locked')


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
class PrivateDecay:
    context: Context
    head: int
    chunk: int
    value: int
    valid: bool

    def __post_init__(self):
        typed(self.context, Context, 'context')
        widths(self, (('head', 4), ('chunk', 1), ('value', 32)))
        boolean(self.valid, 'valid')


@dataclass(frozen=True)
class Phase2Result:
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

    def __post_init__(self):
        typed(self.receipt, Receipt, 'receipt')
        typed(self.decay, PrivateDecay, 'decay')
        widths(self, (('read_bytes', 64), ('cycles', 64)))
        widths(self, tuple((n, 12) for n in ('exp_requests', 'exp_results', 'add_requests',
                                          'add_results', 'mul_requests', 'mul_results')))
        boolean(self.stage_complete, 'stage_complete')


@dataclass(frozen=True)
class Job:
    context: Context
    head: int
    chunk: int
    phase2_ready: Phase2Result

    def __post_init__(self):
        typed(self.context, Context, 'context')
        typed(self.phase2_ready, Phase2Result, 'phase2_ready')
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
class Result:
    phase3: Receipt
    phase4: Receipt
    decay: PrivateDecay
    phase3_read_bytes: int
    phase4_read_bytes: int
    cycles: int
    phase3_complete: bool
    phase4_complete: bool
    stage_complete: bool
    drained: bool
    status: int


@dataclass(frozen=True)
class Signals:
    job_ready: bool
    memory_request: object
    response_ready: bool
    done: object
    reset_required: bool


@dataclass(frozen=True)
class Events:
    before: Signals
    job_fire: bool
    memory_fire: bool
    response_fire: bool
    done_fire: bool


def finite(word):
    return (word & 0x7F800000) != 0x7F800000


def finite_beat(value):
    return all(finite((value >> (32 * lane)) & 0xFFFFFFFF) for lane in range(16))


def spans(c):
    stride = HEAD_STRIDE[128 if c.tokens == 128 else 16]
    return ((c.input, c.tokens * PREPARED_ROW_BYTES), (c.state_in, STATE_BYTES),
            (c.state_out, STATE_BYTES), (c.output, c.tokens * OUTPUT_ROW_BYTES),
            (c.scratch, HEADS * stride))


def admission_status(job, committed):
    c, r = job.context, job.phase2_ready
    p, d = r.receipt, r.decay
    if (c.expected_generation != committed.generation or
            (c.cold and (c.expected_generation != 0 or committed.valid)) or
            (not c.cold and (c.expected_generation == 0 or not committed.valid or committed.state != c.state_in))):
        return Status.DEPENDENCY
    if (c.tokens not in HEAD_STRIDE or job.head >= HEADS or
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
    if not (r.stage_complete and p.tag == c.tag and p.expected_generation == c.expected_generation
            and p.head == job.head and p.chunk == job.chunk and p.phase == 2
            and p.status == Status.OK and p.drained and p.scratch_ack_bytes == 180224
            and p.output_ack_bytes == p.state_ack_bytes == 0 and r.read_bytes == 235584
            and r.exp_requests == r.exp_results == 2209 and r.add_requests == r.add_results == 2144
            and r.mul_requests == r.mul_results == 2560 and d.valid and finite(d.value)
            and d.context == c and d.head == job.head and d.chunk == job.chunk):
        return Status.DEPENDENCY
    return Status.OK


class Owner:
    """Seven states, one outstanding SIMULATED memory transaction, no services.

    Trusted scheduler provenance/exclusivity and unique, no-stale responses are
    obligations outside this model. An error is not a rollback or fabric drain.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.state, self.job = 'idle', None
        self.chunk_base = self.decay_value = 0
        self.second = self.phase3_done = False
        self.tile_row = self.tile_col = self.index = self.sequence = 0
        self.tile = [0] * 16
        self.outstanding = False
        self.status = Status.OK
        self.read_bytes, self.write_bytes = [0, 0], [0, 0]
        self.cycles = 0

    def _fail(self, status):
        self.status, self.state = status, 'finish'

    def _memory_request(self):
        if self.state not in ('issueRead', 'issueWrite'):
            return None
        p = int(self.second)
        write = self.state == 'issueWrite'
        if write:
            address = (self.chunk_base + DESTINATION_OFFSETS[p] +
                       (self.tile_col * 16 + self.index) * 256 + self.tile_row * 64)
            data = sum(((self.tile[lane] >> (self.index * 32)) & 0xFFFFFFFF) << (lane * 32)
                       for lane in range(16))
        else:
            address = (self.chunk_base + SOURCE_OFFSETS[p] +
                       (self.tile_row * 16 + self.index) * 512 + self.tile_col * 64)
            data = 0
        return MemoryRequest(address & FULL_MASK, data, FULL_MASK if write else 0,
                             (self.job.context.tag << 32) | self.sequence, write)

    def peek(self):
        done = None
        if self.state == 'finish':
            j, c = self.job, self.job.context
            complete = (self.status == Status.OK and not self.outstanding and self.second
                        and self.phase3_done and self.read_bytes == [32768, 32768]
                        and self.write_bytes == [32768, 32768])
            receipts = tuple(Receipt(c.tag, c.expected_generation, j.head & 15, j.chunk & 1,
                p + 3, int(Status.OK if p == 0 and self.phase3_done else self.status),
                self.write_bytes[p], 0, 0, self.phase3_done if p == 0 else complete) for p in range(2))
            decay = PrivateDecay(c, j.head & 15, j.chunk & 1, self.decay_value if complete else 0, complete)
            done = Result(receipts[0], receipts[1], decay, *self.read_bytes, self.cycles,
                          self.phase3_done, complete, complete, complete, int(self.status))
        return Signals(self.state == 'idle', self._memory_request(),
                       self.state in ('waitRead', 'waitWrite'), done, self.status != Status.OK)

    def tick(self, *, job=None, committed=None, memory_ready=False, response=None, done_ready=False):
        for value, cls, name in ((job, Job, 'job'), (response, MemoryResponse, 'response')):
            if value is not None:
                typed(value, cls, name)
        boolean(memory_ready, 'memory_ready')
        boolean(done_ready, 'done_ready')
        before = self.peek()
        event = Events(before, job is not None and before.job_ready,
                       before.memory_request is not None and memory_ready,
                       response is not None and before.response_ready,
                       before.done is not None and done_ready)
        old = self.state
        if event.job_fire:
            typed(committed, Committed, 'committed')
            self.reset()
            self.job, self.decay_value = job, job.phase2_ready.decay.value
            c = job.context
            stride = HEAD_STRIDE[128 if c.tokens == 128 else 16]
            self.chunk_base = (c.scratch + job.head * stride + 65536 + job.chunk * CHUNK_BYTES) & FULL_MASK
            self.status = admission_status(job, committed)
            if self.status == Status.OK and response is not None:
                self.status = Status.PROTOCOL
            self.state = 'issueRead' if self.status == Status.OK else 'finish'
            return event
        if old not in ('idle', 'finish', 'locked'):
            self.cycles = (self.cycles + 1) & FULL_MASK
        if event.memory_fire:
            if self.outstanding:
                raise AssertionError('overlapping simulated memory transaction')
            self.outstanding = True
            self.state = 'waitRead' if old == 'issueRead' else 'waitWrite'
        elif event.response_fire:
            if response.tag != (self.job.context.tag << 32) | self.sequence:
                self._fail(Status.PROTOCOL)  # Tag wins, preserving outstanding ambiguity.
            elif response.error:
                self.outstanding = False
                self._fail(Status.MEMORY)
            else:
                self.outstanding = False
                self.sequence = (self.sequence + 1) & 0xFFFFFFFF
                p = int(self.second)
                if old == 'waitRead':
                    self.read_bytes[p] = (self.read_bytes[p] + 64) & FULL_MASK
                    if not finite_beat(response.data):
                        self._fail(Status.NUMERICAL)
                    else:
                        self.tile[self.index] = response.data
                        self.index, self.state = ((0, 'issueWrite') if self.index == 15
                                                 else (self.index + 1, 'issueRead'))
                else:
                    previous = self.write_bytes[p]
                    self.write_bytes[p] = (previous + 64) & FULL_MASK
                    self._write_ack(previous)
        elif event.done_fire:
            self.state = 'idle' if self.status == Status.OK else 'locked'
        return event

    def _write_ack(self, previous_bytes):
        if self.index != 15:
            self.index += 1
            self.state = 'issueWrite'
            return
        self.index = 0
        if self.tile_col != 7:
            self.tile_col += 1
            self.state = 'issueRead'
        elif self.tile_row != 3:
            self.tile_col, self.tile_row, self.state = 0, self.tile_row + 1, 'issueRead'
        elif self.read_bytes[int(self.second)] != 32768 or previous_bytes != 32704:
            self._fail(Status.PROTOCOL)
        elif not self.second:
            self.phase3_done, self.second = True, True
            self.tile_row = self.tile_col = 0
            self.state = 'issueRead'
        else:
            self.state = 'finish'
