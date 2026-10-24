"""Explicit-event phase-1 contract model, not execution of the Scala owner.

Every tick samples pre-edge signals. Memory and scalar services are external;
this owner does not calculate FP32 Add. The tests supply a SIMULATED scalar
service, not an independently executed FP32 DUT. No repository model imports,
native arithmetic, float conversions, publication, or transport-length claim.
"""

from dataclasses import dataclass, fields
from enum import IntEnum

BEAT_BYTES = 64
HEADS = 16
CHUNK_ROWS = 64
STATE_BYTES = 1048576
PER_HEAD_STATE_BYTES = 65536
CHUNK_BYTES = 806912
PREPARED_ROW_BYTES = 25600
OUTPUT_ROW_BYTES = 4096
PHASE_WRITE_BYTES = 102400
ADDRESS_LIMIT = 1 << 56
LAST_GENERATION = (1 << 32) - 1
FULL_MASK = (1 << 64) - 1
HEAD_STRIDE = {16: 872448, 128: 1679360}
ROLE_OFFSETS = (0, 4096, 36864, 69632)


class Status(IntEnum):
    OK = 0
    MEMORY = 3
    UNSUPPORTED = 4
    BOUNDS = 5
    DEPENDENCY = 6
    PROTOCOL = 7
    NUMERICAL = 8


def _uint(value, width, name):
    if type(value) is not int and not isinstance(value, IntEnum):
        raise ValueError(f"{name} must be an integer")
    if not 0 <= value < (1 << width):
        raise ValueError(f"{name} does not fit UInt({width})")


def _bool(value, name):
    if type(value) is not bool:
        raise ValueError(f"{name} must be a bool")


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
        for name, width in (("tag", 32), ("tokens", 16),
                            ("expected_generation", 32), ("vector_policy", 1)):
            _uint(getattr(self, name), width, name)
        _bool(self.cold, "cold")
        for name in ("input", "state_in", "state_out", "output", "scratch"):
            _uint(getattr(self, name), 64, name)


@dataclass(frozen=True)
class Committed:
    valid: bool
    generation: int
    state: int

    def __post_init__(self):
        _bool(self.valid, "valid")
        _uint(self.generation, 32, "generation")
        _uint(self.state, 64, "state")


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
        for name, width in (("tag", 32), ("expected_generation", 32),
                            ("head", 4), ("chunk", 1), ("phase", 5),
                            ("status", 8), ("scratch_ack_bytes", 64),
                            ("output_ack_bytes", 64), ("state_ack_bytes", 64)):
            _uint(getattr(self, name), width, name)
        _bool(self.drained, "drained")


@dataclass(frozen=True)
class PreparedReceipt:
    tag: int = 0
    expected_generation: int = 0
    tokens: int = 0
    input: int = 0
    status: int = 0
    write_bytes: int = 0
    prepared_complete: bool = False
    drained: bool = False
    recurrent_mode: bool = False

    def __post_init__(self):
        for name, width in (("tag", 32), ("expected_generation", 32),
                            ("tokens", 16), ("input", 64), ("status", 8),
                            ("write_bytes", 64)):
            _uint(getattr(self, name), width, name)
        for name in ("prepared_complete", "drained", "recurrent_mode"):
            _bool(getattr(self, name), name)


@dataclass(frozen=True)
class Job:
    context: Context
    head: int
    chunk: int
    prep_ready: PreparedReceipt = PreparedReceipt()
    initial_ready: Receipt = Receipt()
    previous_state_ready: Receipt = Receipt()
    previous_output_ready: Receipt = Receipt()

    def __post_init__(self):
        if not isinstance(self.context, Context):
            raise ValueError("context must be Context")
        _uint(self.head, 16, "head")
        _uint(self.chunk, 16, "chunk")
        if not isinstance(self.prep_ready, PreparedReceipt):
            raise ValueError("prep_ready must be PreparedReceipt")
        for name in ("initial_ready", "previous_state_ready", "previous_output_ready"):
            if not isinstance(getattr(self, name), Receipt):
                raise ValueError(f"{name} must be Receipt")


@dataclass(frozen=True)
class Request:
    address: int
    data: int
    mask: int
    tag: int
    write: bool

    def __post_init__(self):
        for name, width in (("address", 64), ("data", 512), ("mask", 64), ("tag", 64)):
            _uint(getattr(self, name), width, name)
        _bool(self.write, "write")


@dataclass(frozen=True)
class Response:
    tag: int
    data: int = 0
    error: bool = False

    def __post_init__(self):
        _uint(self.tag, 64, "tag")
        _uint(self.data, 512, "data")
        _bool(self.error, "error")


@dataclass(frozen=True)
class ScalarRequest:
    op: int
    a: int
    b: int

    def __post_init__(self):
        _uint(self.op, 3, "op")
        _uint(self.a, 32, "a")
        _uint(self.b, 32, "b")


@dataclass(frozen=True)
class ScalarResult:
    result: int
    error: bool = False

    def __post_init__(self):
        _uint(self.result, 32, "result")
        _bool(self.error, "error")


@dataclass(frozen=True)
class Result:
    """Flattened convenience views supplement the Scala receipt-based result.

    add_issues corresponds to Scala addRequests; local_drained and write_bytes
    are exactly the receipt's drained and scratchAckBytes fields. Flattened
    head/chunk preserve the submitted job; the receipt uses hardware widths.
    """
    tag: int
    expected_generation: int
    head: int
    chunk: int
    phase: int
    status: int
    read_bytes: int
    write_bytes: int
    add_issues: int
    add_results: int
    cycles: int
    stage_complete: bool
    local_drained: bool
    receipt: Receipt


@dataclass(frozen=True)
class Signals:
    job_ready: bool
    memory_request: object
    response_ready: bool
    scalar_request: object
    scalar_result_ready: bool
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
    done_fire: bool


def spans(context):
    return ((context.input, context.tokens * PREPARED_ROW_BYTES),
            (context.state_in, STATE_BYTES), (context.state_out, STATE_BYTES),
            (context.output, context.tokens * OUTPUT_ROW_BYTES),
            (context.scratch, HEADS * HEAD_STRIDE[context.tokens]))


def _receipt_ok(receipt, job, phase, scratch, output):
    c = job.context
    return (receipt.tag == c.tag and receipt.expected_generation == c.expected_generation
            and receipt.head == job.head and receipt.chunk == 0 and receipt.phase == phase
            and receipt.status == Status.OK and receipt.scratch_ack_bytes == scratch
            and receipt.output_ack_bytes == output and receipt.state_ack_bytes == 0
            and receipt.drained)


def admission_status(job, committed):
    c = job.context
    if committed.generation != c.expected_generation:
        return Status.DEPENDENCY
    if c.cold:
        if c.expected_generation != 0 or committed.valid:
            return Status.DEPENDENCY
    elif not (c.expected_generation > 0 and committed.valid and committed.state == c.state_in):
        return Status.DEPENDENCY
    if c.tokens not in HEAD_STRIDE or job.head >= HEADS:
        return Status.BOUNDS
    if job.chunk >= (1 if c.tokens == 16 else 2) or c.expected_generation >= LAST_GENERATION:
        return Status.BOUNDS
    full = spans(c)
    for base, size in full:
        if base % BEAT_BYTES or size % BEAT_BYTES or base + size > ADDRESS_LIMIT:
            return Status.BOUNDS
    for index, (base, size) in enumerate(full):
        for other, other_size in full[:index]:
            if not (base + size <= other or other + other_size <= base):
                return Status.BOUNDS
    if c.vector_policy != 0:
        return Status.UNSUPPORTED
    p = job.prep_ready
    if not (p.tag == c.tag and p.expected_generation == c.expected_generation
            and p.tokens == c.tokens and p.input == c.input and p.status == Status.OK
            and p.write_bytes == c.tokens * PREPARED_ROW_BYTES and p.prepared_complete
            and p.drained and not p.recurrent_mode):
        return Status.DEPENDENCY
    if job.chunk == 0:
        if not _receipt_ok(job.initial_ready, job, 0, PER_HEAD_STATE_BYTES, 0):
            return Status.DEPENDENCY
    elif (not _receipt_ok(job.previous_state_ready, job, 16, PER_HEAD_STATE_BYTES, 0)
          or not _receipt_ok(job.previous_output_ready, job, 17, 0, 16384)):
        return Status.DEPENDENCY
    return Status.OK


def finite(word):
    return (word & 0x7F800000) != 0x7F800000


def valid_payload(payload, gate=False):
    words = tuple((payload >> (32 * lane)) & 0xFFFFFFFF for lane in range(16))
    if not all(finite(word) for word in words):
        return False
    if not gate:
        return True
    g, beta = words[:2]
    g_ok = bool(g & 0x80000000) or (g & 0x7FFFFFFF) == 0
    beta_ok = ((beta & 0x7FFFFFFF) == 0
               or (not beta & 0x80000000 and beta <= 0x3F800000))
    return g_ok and beta_ok and all(word == 0 for word in words[2:])


class Owner:
    """One memory request OR one scalar request outstanding, never both.

    A failed accepted job locks after its held result is consumed. reset() is
    only a model operation, not evidence of physical transport/service recovery.
    Stable prep/root and trusted receipt provenance remain scheduler contracts.
    """
    IDLE = "idle"
    ISSUE_READ = "issueRead"
    WAIT_READ = "waitRead"
    ISSUE_ADD = "issueAdd"
    WAIT_ADD = "waitAdd"
    ISSUE_WRITE = "issueWrite"
    WAIT_WRITE = "waitWrite"
    FINISH = "finish"
    LOCKED = "locked"

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = self.IDLE
        self.job = None
        self.row = self.role = self.beat = 0
        self.sequence = self.buffer = self.cumulative = 0
        self.expected_tag = 0
        self.outstanding = self.scalar_outstanding = False
        self.read_bytes = self.write_bytes = self.cycles = 0
        self.add_issues = self.add_results = 0
        self.status = Status.OK

    def _valid_row(self):
        return self.job.chunk * CHUNK_ROWS + self.row < self.job.context.tokens

    def _request(self):
        if self.state not in (self.ISSUE_READ, self.ISSUE_WRITE):
            return None
        j, c = self.job, self.job.context
        write = self.state == self.ISSUE_WRITE
        if write:
            base = c.scratch + j.head * HEAD_STRIDE[c.tokens] + PER_HEAD_STATE_BYTES + j.chunk * CHUNK_BYTES
            offset = self.row * BEAT_BYTES if self.role == 0 else self.row * 512 + self.beat * BEAT_BYTES
            address = base + ROLE_OFFSETS[self.role] + offset
        else:
            base = c.input + (j.chunk * CHUNK_ROWS + self.row) * PREPARED_ROW_BYTES
            address = (base + 24576 + j.head * BEAT_BYTES if self.role == 0
                       else base + ((self.role - 1) * HEADS + j.head) * 512 + self.beat * BEAT_BYTES)
        return Request(address, self.buffer if write else 0, FULL_MASK if write else 0,
                       (c.tag << 32) | self.sequence, write)

    def signals(self):
        result = None
        if self.state == self.FINISH:
            j, c = self.job, self.job.context
            drained = self.status == Status.OK and not self.outstanding and not self.scalar_outstanding
            complete = (drained and self.write_bytes == PHASE_WRITE_BYTES
                        and self.add_issues == 64 and self.add_results == 64)
            receipt = Receipt(c.tag, c.expected_generation, j.head & 15, j.chunk & 1,
                              1, int(self.status), self.write_bytes, 0, 0, drained)
            result = Result(c.tag, c.expected_generation, j.head, j.chunk, 1,
                            int(self.status), self.read_bytes, self.write_bytes,
                            self.add_issues, self.add_results, self.cycles,
                            complete, drained, receipt)
        scalar = (ScalarRequest(0, self.cumulative, self.buffer & 0xFFFFFFFF)
                  if self.state == self.ISSUE_ADD else None)
        return Signals(self.state == self.IDLE, self._request(),
                       self.state in (self.WAIT_READ, self.WAIT_WRITE), scalar,
                       self.state == self.WAIT_ADD, result, self.status != Status.OK)

    def tick(self, *, job=None, committed=None, memory_ready=False, response=None,
             scalar_ready=False, scalar_result=None, done_ready=False):
        for value, cls, name in ((job, Job, "job"), (response, Response, "response"),
                                 (scalar_result, ScalarResult, "scalar_result")):
            if value is not None and not isinstance(value, cls):
                raise ValueError(f"{name} has wrong type")
        for name, value in (("memory_ready", memory_ready), ("scalar_ready", scalar_ready),
                            ("done_ready", done_ready)):
            _bool(value, name)
        before = self.signals()
        e = Events(before, job is not None and before.job_ready,
                   before.memory_request is not None and memory_ready,
                   response is not None and before.response_ready,
                   before.scalar_request is not None and scalar_ready,
                   scalar_result is not None and before.scalar_result_ready,
                   before.done is not None and done_ready)
        old = self.state
        if e.job_fire:
            if not isinstance(committed, Committed):
                raise ValueError("accepted job requires Committed snapshot")
            self.reset()
            self.job = job
            self.status = admission_status(job, committed)
            self.state = self.ISSUE_READ if self.status == Status.OK else self.FINISH
            return e
        if old in (self.ISSUE_READ, self.WAIT_READ, self.ISSUE_ADD, self.WAIT_ADD,
                   self.ISSUE_WRITE, self.WAIT_WRITE):
            self.cycles = (self.cycles + 1) & FULL_MASK
        if e.memory_fire:
            if self.outstanding or self.scalar_outstanding:
                raise AssertionError("overlapping service requests")
            self.outstanding = True
            self.expected_tag = before.memory_request.tag
            self.state = self.WAIT_READ if old == self.ISSUE_READ else self.WAIT_WRITE
        elif e.response_fire:
            if response.tag != self.expected_tag:
                self.status, self.state = Status.PROTOCOL, self.FINISH
            elif response.error:
                self.outstanding = False
                self.status, self.state = Status.MEMORY, self.FINISH
            else:
                self.outstanding = False
                self.sequence += 1
                if old == self.WAIT_READ:
                    self.read_bytes += BEAT_BYTES
                    if not valid_payload(response.data, self.role == 0):
                        self.status, self.state = Status.NUMERICAL, self.FINISH
                    else:
                        self.buffer = response.data
                        self.state = self.ISSUE_ADD if self.role == 0 else self.ISSUE_WRITE
                else:
                    self.write_bytes += BEAT_BYTES
                    if self.role == 3 and self.beat == 7:
                        if self.row == 63:
                            self.state = self.FINISH
                        else:
                            self.row += 1
                            self.role = self.beat = self.buffer = 0
                            self.state = self.ISSUE_READ if self._valid_row() else self.ISSUE_ADD
                    else:
                        if self.role == 0:
                            self.role, self.beat = 1, 0
                        elif self.beat == 7:
                            self.role += 1
                            self.beat = 0
                        else:
                            self.beat += 1
                        self.buffer = 0
                        self.state = self.ISSUE_READ if self._valid_row() else self.ISSUE_WRITE
        elif e.scalar_fire:
            if self.outstanding or self.scalar_outstanding:
                raise AssertionError("overlapping service requests")
            self.add_issues += 1
            self.scalar_outstanding = True
            self.state = self.WAIT_ADD
        elif e.scalar_result_fire:
            self.scalar_outstanding = False
            if scalar_result.error or not finite(scalar_result.result):
                self.status, self.state = Status.NUMERICAL, self.FINISH
            else:
                self.add_results += 1
                self.cumulative = scalar_result.result
                self.buffer = (self.buffer & (0xFFFFFFFF << 32)) | self.cumulative
                self.state = self.ISSUE_WRITE
        elif e.done_fire:
            self.state = self.IDLE if self.status == Status.OK else self.LOCKED
        return e


RESULT_FIELDS = tuple(field.name for field in fields(Result))
