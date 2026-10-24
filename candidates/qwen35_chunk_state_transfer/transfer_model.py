"""Small, explicit-event reference for the private chunk state-transfer owner.

This is a Python contract model, NOT an execution of Chisel, an RTL simulator,
an AXI model, or evidence that the RTL elaborates. A tick samples all valid /
ready decisions from the pre-cycle state. In particular, a response offered
on a request-acceptance cycle is not accepted until a subsequent wait cycle.
There is no response byte-count field in the existing MemoryResponse ABI.

No external modules, repository models, floating-point operations, subprocesses,
or native backends are used. FP32 payloads are opaque 512-bit integers.
"""

from dataclasses import dataclass, fields
from enum import IntEnum


BEAT_BYTES = 64
HEADS = 16
STATE_BYTES = 1048576
PER_HEAD_STATE_BYTES = 65536
STATE_BEATS = PER_HEAD_STATE_BYTES // BEAT_BYTES
PREPARED_ROW_BYTES = 25600
OUTPUT_ROW_BYTES = 4096
ADDRESS_LIMIT = 1 << 56
LAST_GENERATION = (1 << 32) - 1
FULL_MASK = (1 << 64) - 1
HEAD_STRIDE = {16: 872448, 128: 1679360}
FINAL_NEXT_OFFSET = {16: 806912, 128: 1613824}


class Operation(IntEnum):
    INITIALIZE = 0
    EXPORT_FINAL = 1


class Status(IntEnum):
    OK = 0
    MEMORY = 3
    UNSUPPORTED = 4
    BOUNDS = 5
    DEPENDENCY = 6
    PROTOCOL = 7


def _uint(value, width, name):
    """Reject Python values that cannot appear on the represented UInt wire."""
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
        _uint(self.tag, 32, "tag")
        _uint(self.tokens, 16, "tokens")
        _bool(self.cold, "cold")
        _uint(self.expected_generation, 32, "expected_generation")
        _uint(self.vector_policy, 1, "vector_policy")
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
        for name, width in (
            ("tag", 32), ("expected_generation", 32), ("head", 4),
            ("chunk", 1), ("phase", 5), ("status", 8),
            ("scratch_ack_bytes", 64), ("output_ack_bytes", 64),
            ("state_ack_bytes", 64),
        ):
            _uint(getattr(self, name), width, name)
        _bool(self.drained, "drained")


@dataclass(frozen=True)
class Job:
    context: Context
    head: int
    operation: int
    next_state_ready: Receipt = Receipt()
    output_ready: Receipt = Receipt()

    def __post_init__(self):
        if not isinstance(self.context, Context):
            raise ValueError("context must be Context")
        _uint(self.head, 16, "head")
        _uint(self.operation, 2, "operation")
        if not isinstance(self.next_state_ready, Receipt):
            raise ValueError("next_state_ready must be Receipt")
        if not isinstance(self.output_ready, Receipt):
            raise ValueError("output_ready must be Receipt")


@dataclass(frozen=True)
class Request:
    address: int
    data: int
    mask: int
    tag: int
    write: bool

    def __post_init__(self):
        _uint(self.address, 64, "address")
        _uint(self.data, 512, "data")
        _uint(self.mask, 64, "mask")
        _uint(self.tag, 64, "tag")
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
class Result:
    tag: int
    expected_generation: int
    head: int
    operation: int
    status: int
    read_bytes: int
    write_bytes: int
    cycles: int
    transfer_complete: bool
    local_drained: bool


@dataclass(frozen=True)
class Signals:
    """Signals sampled BEFORE the edge represented by Owner.tick()."""
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


def spans(context):
    """All five FULL spans, not just the selected head or touched addresses."""
    return (
        (context.input, context.tokens * PREPARED_ROW_BYTES),
        (context.state_in, STATE_BYTES),
        (context.state_out, STATE_BYTES),
        (context.output, context.tokens * OUTPUT_ROW_BYTES),
        (context.scratch, HEADS * HEAD_STRIDE[context.tokens]),
    )


def _receipt_ok(receipt, job, phase, scratch, output):
    context = job.context
    return (
        receipt.tag == context.tag
        and receipt.expected_generation == context.expected_generation
        and receipt.head == job.head
        and receipt.chunk == (0 if context.tokens == 16 else 1)
        and receipt.phase == phase
        and receipt.status == Status.OK
        and receipt.scratch_ack_bytes == scratch
        and receipt.output_ack_bytes == output
        and receipt.state_ack_bytes == 0
        and receipt.drained
    )


def admission_status(job, committed):
    """Read-only checks in Scala priority order; no receipt provenance claim."""
    context = job.context
    if committed.generation != context.expected_generation:
        return Status.DEPENDENCY
    if context.cold:
        if context.expected_generation != 0 or committed.valid:
            return Status.DEPENDENCY
    elif not (
        context.expected_generation > 0
        and committed.valid
        and committed.state == context.state_in
    ):
        return Status.DEPENDENCY
    if context.tokens not in HEAD_STRIDE or job.head >= HEADS:
        return Status.BOUNDS
    if context.expected_generation >= LAST_GENERATION:
        return Status.BOUNDS
    complete_spans = spans(context)
    for base, size in complete_spans:
        # Python's wide integer addition mirrors the explicit widened Scala sum.
        if base % BEAT_BYTES or size % BEAT_BYTES or base + size > ADDRESS_LIMIT:
            return Status.BOUNDS
    for index, (base, size) in enumerate(complete_spans):
        for other, other_size in complete_spans[:index]:
            if not (base + size <= other or other + other_size <= base):
                return Status.BOUNDS
    if job.operation not in (Operation.INITIALIZE, Operation.EXPORT_FINAL):
        return Status.UNSUPPORTED
    if job.operation == Operation.EXPORT_FINAL:
        output = 4096 if context.tokens == 16 else 16384
        if not _receipt_ok(job.next_state_ready, job, 16, PER_HEAD_STATE_BYTES, 0):
            return Status.DEPENDENCY
        if not _receipt_ok(job.output_ready, job, 17, 0, output):
            return Status.DEPENDENCY
    return Status.OK


def admissible(job, committed):
    return admission_status(job, committed) == Status.OK


class Owner:
    """Single-outstanding state machine with a single opaque payload register.

    Public counters facilitate assertions; callers must not mutate internals to
    skip work. Only reset(), signals(), and tick() are event entry points.
    A failed accepted command requires explicit reset(), even if no request was
    issued. Reset is a model operation, not a model of physical fabric recovery.
    """

    IDLE = "idle"
    ISSUE_READ = "issueRead"
    WAIT_READ = "waitRead"
    ISSUE_WRITE = "issueWrite"
    WAIT_WRITE = "waitWrite"
    FINISH = "finish"
    LOCKED = "locked"

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = self.IDLE
        self.job = None
        self.beat = 0
        self.sequence = 0
        self.buffer = 0
        self.outstanding = False
        self.expected_tag = 0
        self.read_bytes = 0
        self.write_bytes = 0
        self.cycles = 0
        self.status = Status.OK

    def _cold_initialize(self):
        return self.job.operation == Operation.INITIALIZE and self.job.context.cold

    def _request(self):
        if self.state not in (self.ISSUE_READ, self.ISSUE_WRITE):
            return None
        job = self.job
        context = job.context
        initial = context.scratch + job.head * HEAD_STRIDE[context.tokens]
        final_next = initial + FINAL_NEXT_OFFSET[context.tokens]
        if self.state == self.ISSUE_READ:
            base = (
                context.state_in + job.head * PER_HEAD_STATE_BYTES
                if job.operation == Operation.INITIALIZE else final_next
            )
            data, mask, write = 0, 0, False
        else:
            base = (
                initial if job.operation == Operation.INITIALIZE
                else context.state_out + job.head * PER_HEAD_STATE_BYTES
            )
            data = 0 if self._cold_initialize() else self.buffer
            mask, write = FULL_MASK, True
        return Request(base + self.beat * BEAT_BYTES, data, mask,
                       (context.tag << 32) | self.sequence, write)

    def signals(self):
        result = None
        if self.state == self.FINISH:
            job = self.job
            result = Result(
                job.context.tag, job.context.expected_generation,
                job.head, job.operation, int(self.status),
                self.read_bytes, self.write_bytes, self.cycles,
                self.status == Status.OK and self.write_bytes == PER_HEAD_STATE_BYTES
                and not self.outstanding,
                self.status == Status.OK and not self.outstanding,
            )
        return Signals(
            self.state == self.IDLE,
            self._request(),
            self.state in (self.WAIT_READ, self.WAIT_WRITE),
            result,
            self.status != Status.OK,
        )

    def tick(self, *, job=None, committed=None, memory_ready=False,
             response=None, done_ready=False):
        """Apply one edge using pre-edge signals; return accepted-event evidence.

        job/response=None represents valid=false. An unsolicited response is
        ignored, never accepted and never stored. A done consumer cannot accept
        a result created at this edge until the next tick.
        """
        if job is not None and not isinstance(job, Job):
            raise ValueError("job must be Job or None")
        if response is not None and not isinstance(response, Response):
            raise ValueError("response must be Response or None")
        _bool(memory_ready, "memory_ready")
        _bool(done_ready, "done_ready")
        before = self.signals()
        events = Events(
            before,
            job is not None and before.job_ready,
            before.memory_request is not None and memory_ready,
            response is not None and before.response_ready,
            before.done is not None and done_ready,
        )
        old_state = self.state
        if events.job_fire:
            if not isinstance(committed, Committed):
                raise ValueError("accepted job requires a Committed snapshot")
            self.job = job
            self.beat = self.sequence = self.buffer = 0
            self.read_bytes = self.write_bytes = self.cycles = 0
            self.outstanding = False
            self.expected_tag = 0
            self.status = Status.OK
            self.status = admission_status(job, committed)
            if self.status != Status.OK:
                self.state = self.FINISH
            else:
                self.state = self.ISSUE_WRITE if self._cold_initialize() else self.ISSUE_READ
            return events
        if old_state in (self.ISSUE_READ, self.WAIT_READ, self.ISSUE_WRITE, self.WAIT_WRITE):
            self.cycles = (self.cycles + 1) & FULL_MASK
        if events.memory_fire:
            if self.outstanding:
                raise AssertionError("model attempted a second outstanding request")
            self.expected_tag = before.memory_request.tag
            self.outstanding = True
            self.state = self.WAIT_READ if old_state == self.ISSUE_READ else self.WAIT_WRITE
        elif events.response_fire:
            # Wrong-tag precedence is intentional, even if error is also true.
            if response.tag != self.expected_tag:
                self.status = Status.PROTOCOL
                self.state = self.FINISH
                # Debt is not discharged by a response to a different request.
            elif response.error:
                self.outstanding = False
                self.status = Status.MEMORY
                self.state = self.FINISH
                # Same-tag error may be a folded downstream tag mismatch;
                # local_drained therefore remains false for ALL failures.
            else:
                self.outstanding = False
                self.sequence += 1
                if old_state == self.WAIT_READ:
                    self.buffer = response.data
                    self.read_bytes += BEAT_BYTES
                    self.state = self.ISSUE_WRITE
                else:
                    self.write_bytes += BEAT_BYTES
                    if self.beat == STATE_BEATS - 1:
                        self.state = self.FINISH
                    else:
                        self.beat += 1
                        self.state = self.ISSUE_WRITE if self._cold_initialize() else self.ISSUE_READ
        elif events.done_fire:
            self.state = self.IDLE if self.status == Status.OK else self.LOCKED
        return events


RESULT_FIELDS = tuple(field.name for field in fields(Result))
