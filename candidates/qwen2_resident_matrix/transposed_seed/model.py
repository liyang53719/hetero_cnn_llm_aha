"""Clocked port/control reference for the default-off transposed prefix owner.

This is an independent executable specification, not an RTL simulator or an
FPU oracle. Matrix results are supplied by the test environment. Integers are
IEEE wire encodings; only finiteness and the specified BF16 RNE conversion are
implemented. ``tick`` returns pre-edge ports plus that edge's transfer/port
events. Sync RAM responses cannot stall: their FIFO credit is reserved when
the read is issued. ``coordinated_reset`` means the environment actually reset
both DMA and matrix backends; a local reset never manufactures that evidence.

Physical-port precondition: each backend has one controlled outstanding
transaction and cannot deliver an unsolicited or cross-job stale response.
An accepted terminal retires that physical obligation even when its tag is
bad; it fails the job and locks the owner. A one-beat read drains its one
accepted descriptor beat even if LAST is malformed. Missing responses have
no bounded-liveness guarantee. These are not generation/freshness proofs.
"""
from collections import deque
from dataclasses import dataclass


def finite16(x):
    return type(x) is int and 0 <= x <= 0xffff and x & 0x7f80 != 0x7f80


def finite32(x):
    return type(x) is int and 0 <= x <= 0xffffffff and x & 0x7f800000 != 0x7f800000


def bf16_rne(x):
    if not finite32(x):
        raise ValueError("nonfinite FP32 input")
    y = ((x + 0x7fff + ((x >> 16) & 1)) >> 16) & 0xffff
    return y


def a_address(k, m):
    if not (0 <= k < 1536 and 0 <= m < 128):
        raise ValueError("A coordinate")
    return (k & 15) ^ (m // 16), (k // 16) * 8 + m // 16, m % 16


def b_address(half, k, context, n_half):
    if half not in (0, 1) or not (0 <= k < 1536 and 0 <= context < 5 and n_half in (0, 1)):
        raise ValueError("B coordinate")
    linear = half * 1280 + (k % 128) * 10 + 2 * context + n_half
    return linear % 16, linear // 16


def output_coordinate(m, n):
    if not (0 <= m < 128 and 0 <= n < 32):
        raise ValueError("output coordinate")
    return n % 16, 32 * (4 * (n // 16) + m // 32) + m % 32


def kernel_can_start(*, enable_transposed_dense=False, transposed_reset_required=False,
                     selected_owner_ready=True):
    """Kernel-wide admission guard, independent of which owner is selected.

    The optional profile defaults off, preserving legacy admission. When the
    profile is enabled, poisoned Dense/backend state blocks every owner until
    a coordinated reset; merely selecting another owner cannot bypass it.
    """
    return selected_owner_ready and not (enable_transposed_dense and transposed_reset_required)


def pack16(words):
    return sum(x << (16 * i) for i, x in enumerate(words))


def unpack16(word):
    return tuple((word >> (16 * i)) & 0xffff for i in range(16))


@dataclass(frozen=True)
class Job:
    m: int = 128
    k: int = 32
    n: int = 32
    tag: int = 1
    activation_bf16: bool = True
    weight_bf16: bool = True
    output_bf16: bool = False
    a: int = 0x100000
    b: int = 0x400000
    dst: int = 0x800000
    kind: str = "Dense"
    write_bytes: int | None = None

    def validate(self):
        if self.kind != "Dense" or self.m not in (16, 128) or not (0 < self.k <= 1536 and self.k % 16 == 0):
            raise ValueError("full-A M16/M128, 0<K<=1536, K divisible by 16")
        if self.activation_bf16 and self.k % 32:
            raise ValueError("native BF16 A requires K divisible by 32")
        if not (0 < self.n < 65536 and self.n % 32 == 0 and 0 <= self.tag < 2**32):
            raise ValueError("N32 shape/tag")
        if any(x < 0 or x % 64 for x in (self.a, self.b, self.dst)):
            raise ValueError("aligned DDR addresses")
        a_end = self.a + self.m * self.k * (2 if self.activation_bf16 else 4)
        b_end = self.b + self.k * self.n * (2 if self.weight_bf16 else 4)
        expected_bytes = self.m * self.n * (2 if self.output_bf16 else 4)
        d_end = self.dst + expected_bytes
        if max(a_end, b_end, d_end) > 2**56:
            raise ValueError("DDR span exceeds 56-bit address domain")
        if (self.a < d_end and self.dst < a_end) or (self.b < d_end and self.dst < b_end):
            raise ValueError("output aliases an input span")
        if self.write_bytes not in (None, expected_bytes):
            raise ValueError("declared output byte count")


@dataclass(frozen=True)
class ReadCommand:
    kind: str
    address: int
    beats: int
    tag: int


@dataclass(frozen=True)
class ReadBeat:
    tag: int
    words: tuple
    last: bool
    error: bool = False


@dataclass(frozen=True)
class Step:
    k: int
    context: int
    clear: bool
    last: bool
    finish: bool
    emit: bool
    a: tuple
    b: tuple


@dataclass(frozen=True)
class MatrixResult:
    context: int
    value: tuple
    last: bool = True
    error: bool = False


@dataclass(frozen=True)
class MatrixDone:
    tag: int
    error: bool = False


@dataclass(frozen=True)
class WriteCommand:
    address: int
    beats: int
    tag: int


@dataclass(frozen=True)
class WriteBeat:
    words: tuple
    last: bool


@dataclass(frozen=True)
class WriteAck:
    tag: int
    error: bool = False
    nbytes: int | None = None


class Banks:
    """One synchronous read and one write per bank per clock, 256-bit words."""
    def __init__(self, depth):
        self.depth = depth
        self.words = [[0] * depth for _ in range(16)]
        self.begin_cycle()

    def begin_cycle(self):
        self.reads, self.writes = {}, {}

    def read(self, bank, word):
        assert 0 <= bank < 16 and 0 <= word < self.depth
        assert bank not in self.reads, "second SRAM read port inferred"
        self.reads[bank] = word
        return self.words[bank][word]

    def write(self, bank, word, data):
        assert 0 <= bank < 16 and 0 <= word < self.depth
        assert bank not in self.writes, "second SRAM write port inferred"
        assert 0 <= data < 2**256
        self.writes[bank] = word
        self.words[bank][word] = data


@dataclass(frozen=True)
class PrefixWorkspace:
    base: int
    extent: int
    generation: int
    split_k: int = 768

    def validate(self, job):
        if self.base < 0 or self.base % 64 or self.extent < job.n // 32 * 16384:
            raise ValueError("prefix workspace alignment/extent")
        if not 0 < self.generation < 2**32 or not 0 < self.split_k < job.k or self.split_k % 128:
            raise ValueError("prefix workspace generation/split")
        end = self.base + self.extent
        if end > 2**56:
            raise ValueError("prefix workspace 56-bit span")
        for base, size in ((job.a, job.m*job.k*(2 if job.activation_bf16 else 4)),
                           (job.b, job.k*job.n*(2 if job.weight_bf16 else 4)),
                           (job.dst, job.m*job.n*(2 if job.output_bf16 else 4))):
            if self.base < base + size and base < end:
                raise ValueError("prefix workspace aliases live tensor")


def prefix_ddr_beat(index):
    if not 0 <= index < 256:
        raise ValueError("prefix beat index")
    slice_, cluster = divmod(index, 32)
    return 16*(cluster >> 1) + 2*slice_ + (cluster & 1)


@dataclass(frozen=True)
class SeedRequest:
    tag: int
    sequence: int
    generation: int
    context: int
    slice_mask: int = 255


@dataclass(frozen=True)
class SeedBeat:
    request: SeedRequest
    index: int
    words: tuple
    last: bool
    error: bool = False


@dataclass(frozen=True)
class SeedAck:
    request: SeedRequest
    error: bool = False


class DenseOwnerModel:
    FIFO_DEPTH = 4

    def __init__(self, workspace=None):
        self.workspace = workspace
        self.a_banks, self.b_banks = Banks(1376), Banks(160)
        self.clock = 0
        self.responses = 0
        self._reset()

    def _reset(self):
        self.state, self.error, self.job = "idle", None, None
        self.read_active = None
        self.a_hold = None
        self.a_rmw_pending = None
        self.pending = None
        self.fifo = deque()
        self.ready = [False, False]
        self.ready_k = [None, None]
        self.group_started = self.group_done = False
        self.write_state = "idle"
        self.final_value = None
        self.write_bytes = self.read_sequence = self.write_sequence = 0
        self.accepted_steps = self.rmw_commits = 0
        self.written = 0
        self.max_reserved = 0
        self.restoring = False
        self.prefix_valid = False
        self.prefix_bytes = 0
        self.group_sequence = 0
        self.seed_state = "idle"
        self.seed_context = self.seed_index = 0
        self.seed_hold = None
        self.seed_acked = set()

    def _fault(self, reason):
        if self.error is None:
            self.error = reason
        self.ready[:] = [False, False]
        self.prefix_valid = False
        self.seed_hold = None
        if self.write_state == "request":
            self.write_state = "idle"  # no accepted write to drain
        if self.state not in ("finish", "locked"):
            self.state = "drain"

    @property
    def saving_prefix(self):
        return self.workspace is not None and not self.restoring

    @property
    def chunk_start(self):
        return self.workspace.split_k if self.restoring else 0

    @property
    def chunk_end(self):
        return self.workspace.split_k if self.saving_prefix else self.job.k

    def _seed_request(self):
        return SeedRequest(self.job.tag, self.group_sequence, self.workspace.generation, self.seed_context)

    def _window(self):
        self.contexts = min(5, (self.job.n - self.n_base) // 32)
        self.group_started = self.group_done = False
        self.group_accepted_steps = self.results_received = self.written = 0
        self.terminal_issued = set()
        self.issue_k = self.load_k = self.chunk_start
        self.issue_context = self.load_depth = self.load_beat = 0
        self.group_sequence += 1
        if self.group_sequence >= 2**32:
            self._fault("nonwrapping group sequence exhausted")
            return
        self.seed_context = self.seed_index = 0
        self.seed_hold = None
        self.seed_acked = set()
        self.seed_state = "begin" if self.restoring else "idle"
        self.ready[:] = [False, False]
        self.ready_k[:] = [None, None]
        self.pending = None
        self.fifo.clear()
        self.state = "execute"

    def _read_command(self):
        if self.error or self.read_active or self.a_hold or self.a_rmw_pending:
            return None
        j = self.job
        if self.state == "a_load":
            per = 32 if j.activation_bf16 else 16
            if self.a_beat == j.k // per:
                return None
            address = j.a + (self.a_row * j.k + self.a_beat * per) * (2 if j.activation_bf16 else 4)
            return ReadCommand("a", address, 1,
                               (j.tag << 32) | self.read_sequence)
        if self.state == "execute" and self.restoring and self.seed_state != "idle":
            if self.seed_state == "read" and self.group_started and self.prefix_valid:
                address = self.workspace.base + (self.n_base//32+self.seed_context)*16384 + prefix_ddr_beat(self.seed_index)*64
                return ReadCommand("prefix", address, 1, (j.tag << 32) | self.read_sequence)
            return None
        if self.state == "execute" and self.load_k < self.chunk_end:
            half = (self.load_k // 128) & 1
            if self.ready[half]:
                return None
            per = 32 if j.weight_bf16 else 16
            address = j.b + ((self.load_k + self.load_depth) * j.n + self.n_base + self.load_beat * per) * (2 if j.weight_bf16 else 4)
            return ReadCommand("b", address, 1,
                               (j.tag << 32) | self.read_sequence)
        return None

    def _write_command(self):
        if self.write_state != "request" or self.error:
            return None
        j = self.job
        if self.saving_prefix:
            address = self.workspace.base + (self.n_base//32+self.write_context)*16384 + self.write_prefix_index*64
            return WriteCommand(address, 1, (j.tag << 32) | self.write_sequence)
        address = j.dst + (self.write_row * j.n + self.n_base + self.write_context * 32) * (2 if j.output_bf16 else 4) + self.write_row_beat * 64
        beats = min((1 if j.output_bf16 else 2) - self.write_row_beat, 16 - ((address >> 6) & 15))
        return WriteCommand(address, beats, (j.tag << 32) | self.write_sequence)

    def _write_data(self):
        if self.write_state != "data":
            return None
        if self.saving_prefix:
            row, beat = divmod(self.write_prefix_index, 16)
            return WriteBeat(tuple(self.final_value[row][beat*16:beat*16+16]), True)
        per = 32 if self.job.output_bf16 else 16
        first = (self.write_row_beat + self.write_index) * per
        values = tuple(self.final_value[output_coordinate(self.write_row, first + n)[0]]
                      [output_coordinate(self.write_row, first + n)[1]] for n in range(per))
        if self.job.output_bf16:
            values = tuple(bf16_rne(x) for x in values)
        return WriteBeat(values, self.write_index + 1 == self.accepted_write.beats)

    def ports(self):
        return dict(seed_begin=self._seed_request() if self.restoring and self.seed_state == "begin" and self.group_started and not self.error else None,
                    seed_beat=SeedBeat(self._seed_request(), self.seed_index, self.seed_hold, self.seed_index == 255)
                        if self.restoring and self.seed_state == "send" and not self.error else None,
                    seed_ack_ready=self.restoring and (self.seed_state == "ack" or bool(self.error)),
                    job_ready=self.state == "idle", read_command=self._read_command(),
                    read_ready=self.read_active is not None and (bool(self.error) or not (self.a_hold or self.a_rmw_pending)),
                    group=(self.job.tag, 0x20, 0xff, True) if self.state == "execute" and not self.error and not self.group_started else None,
                    step=self.fifo[0] if self.state == "execute" and not self.error and self.fifo else None,
                    result_ready=self.state in ("execute", "drain") and self.group_started and (bool(self.error) or self.write_state == "idle"),
                    matrix_done_ready=self.group_started and not self.group_done,
                    abort=bool(self.error) and self.group_started and not self.group_done,
                    write_command=self._write_command(), write_data=self._write_data(),
                    write_ack_ready=self.write_state == "ack",
                    response=(self.job.tag if self.job else None, self.error, self.write_bytes) if self.state == "finish" else None,
                    reset_required=bool(self.error) or self.state == "locked")

    def _convert(self, words, native):
        if len(words) != (32 if native else 16):
            raise ValueError("DDR beat width")
        if native:
            if not all(finite16(x) for x in words):
                raise ValueError("nonfinite BF16")
            return tuple(words)
        converted = tuple(bf16_rne(x) for x in words)
        if not all(finite16(x) for x in converted):
            raise ValueError("FP32 RNE produces nonfinite BF16")
        return converted

    def _receive_read(self, beat):
        cmd, index = self.read_active
        if cmd.kind == "prefix":
            self.read_active = None
            self.read_sequence += 1
            if beat.tag != cmd.tag or beat.error or not beat.last:
                self._fault("prefix DMA tag/error/LAST")
            elif not self.error:
                if len(beat.words) != 16 or not all(finite32(x) for x in beat.words):
                    self._fault("prefix finite FP32/beat width")
                else:
                    self.seed_hold = tuple(beat.words)
                    self.seed_state = "send"
            return
        valid = beat.tag == cmd.tag and not beat.error and beat.last == (index + 1 == cmd.beats)
        if not valid:
            self._fault("DMA tag/error/LAST")
        if not self.error:
            try:
                words = self._convert(beat.words, self.job.activation_bf16 if cmd.kind == "a" else self.job.weight_bf16)
            except ValueError as exc:
                self._fault(str(exc))
            else:
                if cmd.kind == "a":
                    per = len(words)
                    first_k = self.a_beat * per
                    self.a_hold = deque(tuple((self.a_row, first_k + offset + i, x)
                                             for i, x in enumerate(words[offset:offset + 16]))
                                        for offset in range(0, per, 16))
                    self.a_beat += 1
                    # The lower 256-bit RMW read starts at DDR acceptance.
                    # Only the remaining upper 256 bits occupy the owner hold.
                    self._start_a_rmw()
                else:
                    per = len(words)
                    group16 = self.load_beat * per // 16
                    half = (self.load_k // 128) & 1
                    for offset in range(per // 16):
                        group = group16 + offset
                        bank, word = b_address(half, self.load_k + self.load_depth, group // 2, group % 2)
                        self.b_banks.write(bank, word, pack16(words[offset * 16:offset * 16 + 16]))
                    self.load_beat += 1
        # Unique controlled physical response: drain the accepted beat count.
        terminal = index + 1 == cmd.beats
        self.read_active = None if terminal else (cmd, index + 1)
        self.read_sequence += int(terminal)
        if cmd.kind == "b" and beat.last and not self.error:
            per = 32 if self.job.weight_bf16 else 16
            if self.load_beat == self.contexts * 32 // per:
                self.load_beat = 0
                self.load_depth += 1
                if self.load_depth == min(128, self.chunk_end - self.load_k):
                    half = (self.load_k // 128) & 1
                    self.ready[half], self.ready_k[half] = True, self.load_k
                    self.load_k += self.load_depth
                    self.load_depth = 0

    def _a_cycle(self):
        was_pending = self.a_rmw_pending is not None
        if self.a_rmw_pending is not None:
            for bank, word, lane, value, old in self.a_rmw_pending:
                mask = 0xffff << (16 * lane)
                self.a_banks.write(bank, word, (old & ~mask) | (value << (16 * lane)))
            self.rmw_commits += 16
            self.a_rmw_pending = None
            if not self.a_hold:
                self.a_hold = None
        # Banks.activation.ready is false on its reserved response/write edge.
        if self.a_hold and not was_pending:
            self._start_a_rmw()
        if self.state == "a_load" and not self.read_active and not self.a_hold and not self.a_rmw_pending:
            per = 32 if self.job.activation_bf16 else 16
            if self.a_beat == self.job.k // per:
                self.a_beat = 0
                self.a_row += 1
                if self.a_row == self.job.m:
                    assert self.rmw_commits == self.job.m * self.job.k
                    self._window()

    def _start_a_rmw(self):
        updates = self.a_hold.popleft()
        self.a_rmw_pending = []
        for m, k, value in updates:
            bank, word, lane = a_address(k, m)
            self.a_rmw_pending.append((bank, word, lane, value, self.a_banks.read(bank, word)))

    def _operand_response(self, pending):
        k, context, awords, bwords = pending
        activations = tuple(x for word in awords for x in unpack16(word))
        weights = tuple(x for word in bwords for x in unpack16(word))
        last = k + 1 == self.chunk_end
        return Step(k, context, k == 0, last, last and context + 1 == self.contexts, last,
                    weights[:16], activations + weights[16:] + (0,) * 112)

    def _issue_read(self):
        k, ctx = self.issue_k, self.issue_context
        half = (k // 128) & 1
        awords = tuple(self.a_banks.read((k & 15) ^ group, (k // 16) * 8 + group) for group in range(8))
        bwords = tuple(self.b_banks.read(*b_address(half, k, ctx, nh)) for nh in range(2))
        self.pending = (k, ctx, awords, bwords)
        self.issue_context += 1
        if self.issue_context == self.contexts:
            self.issue_context = 0
            self.issue_k += 1
            if self.issue_k % 128 == 0 or self.issue_k == self.chunk_end:
                self.ready[half] = False

    def _receive_result(self, result, terminal_at_edge):
        if self.error:
            return
        if result.error or not result.last or result.context != self.results_received or result.context >= self.contexts:
            self._fault("matrix result order/context/last/error")
            return
        if result.context not in terminal_at_edge:
            self._fault("matrix result before final accepted step")
            return
        if len(result.value) != 16 or any(len(row) != 256 for row in result.value):
            self._fault("matrix result shape")
            return
        try:
            for m in range(128 if self.saving_prefix else self.job.m):
                for n in range(32):
                    row, col = output_coordinate(m, n)
                    x = result.value[row][col]
                    if not finite32(x):
                        raise ValueError("nonfinite result")
                    if self.job.output_bf16 and not self.saving_prefix:
                        if (x & 0x7fffffff) >= 0x7f7f8000:
                            raise ValueError("result outside finite BF16 output domain")
        except ValueError as exc:
            self._fault(str(exc))
            return
        self.final_value = result.value
        self.write_prefix_index = 0
        self.write_context = result.context
        self.write_row = 0
        self.write_row_beat = 0
        self.results_received += 1
        self.write_state = "request"

    def tick(self, *, job=None, read_command_ready=True, read_beat=None,
             group_ready=True, step_ready=True, result=None, matrix_done=None,
             write_command_ready=True, write_data_ready=True, write_ack=None,
             response_ready=True, local_reset=False, coordinated_reset=False,
             seed_begin_ready=True, seed_beat_ready=True, seed_ack=None):
        p = self.ports()
        for bank in (self.a_banks, self.b_banks):
            bank.begin_cycle()
        self.clock += 1
        if coordinated_reset:
            self._reset()
            return dict(p, coordinated_reset=True)
        if local_reset:
            self._fault("local reset requires coordinated backend reset")
        error_at_edge = self.error is not None
        terminal_at_edge = set(getattr(self, "terminal_issued", ()))
        old_pending = self.pending
        done_prerequisites_at_edge = (p["matrix_done_ready"] and self.issue_k == self.chunk_end and
                                      self.group_accepted_steps == (self.chunk_end-self.chunk_start) * self.contexts and
                                      self.results_received == self.contexts and
                                      old_pending is None and not self.fifo)
        reserved = len(self.fifo) + int(old_pending is not None)
        self.max_reserved = max(self.max_reserved, reserved)
        assert reserved <= self.FIFO_DEPTH
        can_issue = (not self.error and self.state == "execute" and self.group_started and
                     not self.group_done and self.seed_state == "idle" and self.issue_k < self.chunk_end and reserved < self.FIFO_DEPTH and
                     self.ready[(self.issue_k // 128) & 1] and
                     self.ready_k[(self.issue_k // 128) & 1] == self.issue_k // 128 * 128)
        p.update(read_fire=False, step_fire=False, operand_read=False, operand_response=False, result_fire=False,
                 write_command_fire=False, write_data_fire=False, write_ack_fire=False, response_fire=False,
                 seed_begin_fire=False, seed_beat_fire=False, seed_ack_fire=False)
        if p["response"] is not None and response_ready:
            self.responses += 1
            p["response_fire"] = True
            self.state = "locked" if self.error else "idle"
        if job is not None and p["job_ready"] and not local_reset:
            self.job = job
            self.write_bytes = self.rmw_commits = self.accepted_steps = self.prefix_bytes = 0
            self.restoring = self.prefix_valid = False
            self.group_started = self.group_done = False
            self.error = None
            try:
                job.validate()
                if self.workspace is not None: self.workspace.validate(job)
            except ValueError as exc:
                self._fault(str(exc))
            else:
                self.state = "clear"
                self.clear_word = self.a_row = self.a_beat = self.n_base = 0
        if self.state == "clear":
            for bank in range(16):
                self.a_banks.write(bank, self.clear_word, 0)
            self.clear_word += 1
            if self.clear_word == self.job.k // 16 * 8:
                self.state = "a_load"
        if p["read_command"] is not None and read_command_ready and not self.error:
            self.read_active = (p["read_command"], 0)
            p["read_command_fire"] = True
        else:
            p["read_command_fire"] = False
        # Responses to a read accepted on this edge cannot appear until later.
        self._a_cycle()
        if read_beat is not None and p["read_ready"]:
            p["read_fire"] = True
            self._receive_read(read_beat)
        if p["group"] is not None and group_ready and not local_reset:
            self.group_started = True
            p["group_fire"] = True
        else:
            p["group_fire"] = False
        if p["seed_begin"] is not None and seed_begin_ready and not local_reset:
            if not self.prefix_valid:
                self._fault("uncommitted prefix restore")
            else:
                self.seed_state = "read"
                p["seed_begin_fire"] = True
        if p["seed_beat"] is not None and seed_beat_ready and not local_reset:
            self.seed_hold = None
            self.seed_state = "ack" if self.seed_index == 255 else "read"
            self.seed_index += int(self.seed_index != 255)
            p["seed_beat_fire"] = True
        if seed_ack is not None:
            if not p["seed_ack_ready"]:
                self._fault("unexpected late seed ACK")
            else:
                p["seed_ack_fire"] = True
                if seed_ack.error or seed_ack.request != self._seed_request():
                    self._fault("seed ACK identity/error")
                elif not self.error:
                    self.seed_acked.add(self.seed_context)
                    self.seed_context += 1
                    self.seed_index = 0
                    self.seed_state = "idle" if self.seed_context == self.contexts else "begin"
        if p["step"] is not None and step_ready and not local_reset:
            p["step_fire"] = True
            self.fifo.popleft()
            self.accepted_steps += 1
            self.group_accepted_steps += 1
            if p["step"].last:
                self.terminal_issued.add(p["step"].context)
        elif error_at_edge and self.fifo:
            self.fifo.popleft()  # Drain one accepted FIFO entry per clock.
        self.pending = None
        if old_pending is not None and not error_at_edge:
            assert len(self.fifo) < self.FIFO_DEPTH, "reserved sync response was stalled"
            self.fifo.append(self._operand_response(old_pending))
            p["operand_response"] = True
        if can_issue:
            self._issue_read()
            p["operand_read"] = True
        if result is not None and p["result_ready"]:
            p["result_fire"] = True
            self._receive_result(result, terminal_at_edge)
        if p["write_command"] is not None and write_command_ready and not local_reset:
            self.accepted_write = p["write_command"]
            self.write_index = 0
            self.write_state = "data"
            p["write_command_fire"] = True
        if p["write_data"] is not None and write_data_ready:
            self.write_index += 1
            p["write_data_fire"] = True
            if self.write_index == self.accepted_write.beats:
                self.write_state = "ack"
        if write_ack is not None and p["write_ack_ready"]:
            p["write_ack_fire"] = True
            expected_bytes = self.accepted_write.beats * 64
            self.write_state = "idle"
            if write_ack.tag != self.accepted_write.tag or write_ack.error or write_ack.nbytes not in (None, expected_bytes):
                self._fault("write ACK tag/error/bytes")
            else:
                self.write_state = "idle"
                if self.saving_prefix: self.prefix_bytes += expected_bytes
                else: self.write_bytes += expected_bytes
                self.write_sequence += 1
                if not self.error:
                    if self.saving_prefix:
                        self.write_prefix_index += 1
                        if self.write_prefix_index == 256:
                            self.written += 1
                            self.final_value = None
                        else:
                            self.write_state = "request"
                    else:
                        self._advance_final_write()
        if matrix_done is not None and p["matrix_done_ready"]:
            self.group_done = True
            if matrix_done.tag != self.job.tag:
                self._fault("matrix done tag")
            else:
                if matrix_done.error:
                    self._fault("matrix done error")
                elif not self.error and not done_prerequisites_at_edge:
                    self._fault("matrix done before all accepted steps/results")
        if self.error and self.state == "drain":
            if not (self.read_active or self.a_hold or self.a_rmw_pending or self.pending or self.fifo) and self.write_state == "idle" and (not self.group_started or self.group_done):
                self.state = "finish"
        elif self.state == "execute" and self.group_done and self.written == self.contexts:
            assert not (self.read_active or self.a_hold or self.a_rmw_pending or self.pending or self.fifo)
            if self.issue_k != self.chunk_end or self.group_accepted_steps != (self.chunk_end-self.chunk_start) * self.contexts:
                self._fault("incomplete issue at completion")
            elif self.saving_prefix:
                if self.prefix_bytes != (self.n_base//32+self.contexts)*16384:
                    self._fault("exact prefix ACK byte count")
                else:
                    # Whole-window publication: all context writes ACKed AND
                    # Matrixdone before a single restore read is possible.
                    self.prefix_valid = True
                    self.restoring = True
                    self._window()
            elif self.write_bytes != self.job.m * (self.n_base + self.contexts * 32) * (2 if self.job.output_bf16 else 4):
                self._fault("exact output byte count")
            elif self.n_base + self.contexts * 32 < self.job.n:
                self.n_base += self.contexts * 32
                self.restoring = self.prefix_valid = False
                self._window()
            else:
                self.state = "finish"
        p["a_reads"], p["a_writes"] = dict(self.a_banks.reads), dict(self.a_banks.writes)
        p["b_reads"], p["b_writes"] = dict(self.b_banks.reads), dict(self.b_banks.writes)
        p["reserved_after"] = len(self.fifo) + int(self.pending is not None)
        assert p["reserved_after"] <= self.FIFO_DEPTH
        return p

    def _advance_final_write(self):
        self.write_row_beat += self.accepted_write.beats
        if self.write_row_beat == (1 if self.job.output_bf16 else 2):
            self.write_row_beat = 0
            self.write_row += 1
        if self.write_row == self.job.m:
            self.written += 1
            self.final_value = None
        else:
            self.write_state = "request"


class MatrixSeedLifecycleModel:
    """Service lifecycle reference with sets, separate from FMA/leaf models.

    Seeded contexts are obligations even before their first arithmetic issue.
    A controller commit is accepted only for the current legal transposed group.
    Rejected steps are terminal protocol errors and do not change issue counts.
    """
    def __init__(self, transposed=True, opcode=0x20, mask=255):
        self.transposed, self.opcode, self.mask = transposed, opcode, mask
        self.seen, self.seeded, self.closed = set(), set(), set()
        self.poison = self.finished = False
        self.accepted_steps = 0

    def commit_seed(self, context, *, quiescent=True, abort=False):
        legal = (not self.poison and not self.finished and not abort and quiescent
                 and self.transposed and self.opcode == 0x20 and self.mask == 255
                 and context in range(5) and context not in self.seen | self.seeded | self.closed)
        if legal: self.seeded.add(context)
        else: self.poison = True
        return legal

    def issue(self, context, clear, *, last=False, finish=False, begin_valid=False):
        if begin_valid or self.poison or self.finished:
            return False
        obligations = self.seen | self.seeded | {context}
        closing = self.closed | ({context} if last else set())
        legal = (context in range(5) and context not in self.closed
                 and clear == (context not in self.seen | self.seeded)
                 and (not finish or (last and closing == obligations)))
        if not legal:
            self.poison = True
            return False
        self.seen.add(context)
        if last: self.closed.add(context)
        self.accepted_steps += 1
        self.finished = finish
        return True
