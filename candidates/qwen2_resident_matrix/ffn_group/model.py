"""Bounded FFN group control and public-root safety specification.

This is an independent event model, NOT execution of the Scala Host decoder,
Chisel/RTL, Matrix, SFU, arithmetic, SRAM transport, or a cycle prediction. Job
and descriptor objects represent externally decoded values. Opaque terminal
ports are injected by the harness; counters are taken only from accepted
terminals, never inferred from tensor shapes. The retained window/drain models
separately test physical transport. This model owns no tensor payload storage.

A controlled backend must keep busy asserted while its terminal is offered,
retire every accepted obligation, and flush old traffic on coordinated reset.
A matching tag/identity is not proof of generation freshness across reset.
"""
from dataclasses import dataclass
from math import prod

U64 = (1 << 64) - 1
LIMIT = 1 << 56
NULL = 0xffffff
WINDOW = 160
WIDTH = 8960
RESET_DOMAIN = frozenset({"host", "coordinator", "window", "drain", "tiles", "sfu", "dma", "matrix"})


def uint(value, bits):
    return type(value) is int and 0 <= value < (1 << bits)


def overlap(a, e, b, f):
    return a < f and b < e


@dataclass(frozen=True)
class Job:
    kind: str
    tag: int
    a: int
    b: int
    dst: int
    m: int
    n: int
    k: int
    write_bytes: int
    weight_bf16: bool = False
    activation_bf16: bool = False
    output_bf16: bool = False


@dataclass(frozen=True)
class GroupRequest:
    gate: Job
    up: Job
    act: Job
    identity: int

    def valid(self):
        def dense(j):
            return (j.kind == "Dense" and j.m in (16, 128) and j.n == WIDTH and j.k == 1536
                    and j.weight_bf16 and not j.activation_bf16 and not j.output_bf16
                    and j.write_bytes == j.m * WIDTH * 4)
        g, u, a = self.gate, self.up, self.act
        return (uint(self.identity, 32) and self.identity != 0 and dense(g) and dense(u)
                and u.m == g.m and u.a == g.a and a.kind == "Activation" and a.m == g.m
                and a.n == a.k == WIDTH and not (a.weight_bf16 or a.activation_bf16 or a.output_bf16)
                and a.a == g.dst and a.b == u.dst and a.write_bytes == g.write_bytes)


@dataclass(frozen=True)
class WindowRequest:
    job: Job
    identity: int
    ng: int
    cols: int
    slot: int
    reuse_a: bool


@dataclass(frozen=True)
class DrainRequest:
    job: Job
    identity: int
    ng: int
    cols: int


@dataclass(frozen=True)
class SiluRequest:
    identity: int
    ng: int
    rows: int
    cols: int


@dataclass(frozen=True)
class WindowResult:
    tag: int
    identity: int
    ng: int
    rows: int
    cols: int
    slot: int
    committed: bool
    produced_beats: int
    status: str | None = None
    ddr_write_bytes: int = 0
    useful_macs: int = 0
    executed_macs: int = 0


@dataclass(frozen=True)
class DrainResult:
    tag: int
    identity: int
    ng: int
    rows: int
    cols: int
    committed: bool
    consumed_beats: int
    ddr_write_bytes: int
    status: str | None = None
    useful_macs: int = 0
    executed_macs: int = 0


@dataclass(frozen=True)
class OwnerResult:
    tag: int
    status: str | None
    write_bytes: int
    cycles: int
    useful_macs: int
    executed_macs: int


@dataclass(frozen=True)
class Services:
    window_busy: bool = False
    drain_busy: bool = False
    tiles_drained: bool = True
    tiles_leased: bool = False
    silu_drained: bool = True
    bridge_busy: bool = False
    lease_valid: bool = False
    window_reset: bool = False
    drain_reset: bool = False
    bridge_reset: bool = False

    @property
    def error(self):
        return self.window_reset or self.drain_reset or self.bridge_reset


class ResidentCoordinator:
    STATES = ("idle", "gateFlush", "gateIssue", "gateWait", "upFlush", "upIssue", "upWait",
              "siluIssue", "siluWait", "actFlush", "actIssue", "actWait", "invalidate",
              "retire", "draining", "reply", "locked")

    def __init__(self):
        self.state = "idle"
        self.call = self.result = None
        self.ng = self.cycles = self.write_bytes = self.useful = self.executed = 0
        self.poison = False
        self.status = None

    def ports(self, services=Services(), *, abort=False):
        s = self.state
        bad = self.poison or abort or services.error
        up = s in ("upFlush", "upIssue", "upWait")
        window_job = (self.call.up if up else self.call.gate) if self.call else None
        handoff = None
        if not bad and s in ("gateFlush", "upFlush", "actFlush"):
            handoff = self.call.act if s == "actFlush" else window_job
        return dict(state=s, busy=s not in ("idle", "locked"), reset_required=bool(bad),
                    request_ready=s == "idle" and not bad and not services.window_busy
                    and not services.drain_busy and services.tiles_drained
                    and not services.tiles_leased and services.silu_drained,
                    result=self.result if s == "reply" else None, handoff=handoff,
                    window_request=WindowRequest(window_job, self.call.identity, self.ng, WINDOW,
                                                 int(up), up or self.ng != 0)
                    if not bad and s in ("gateIssue", "upIssue") else None,
                    drain_request=DrainRequest(self.call.act, self.call.identity, self.ng, WINDOW)
                    if not bad and s == "actIssue" else None,
                    silu_request=SiluRequest(self.call.identity, self.ng, self.call.gate.m, WINDOW)
                    if not bad and s == "siluIssue" else None,
                    window_result_ready=s in ("gateWait", "upWait", "draining"),
                    drain_result_ready=s in ("actWait", "draining"),
                    invalidate_lease=self.poison or abort or s in ("invalidate", "retire"),
                    backend_abort=self.poison or abort)

    def _fail(self, status=None):
        self.poison = True
        self.status = status or "Protocol"
        self.state = "draining"

    def _reply(self, status):
        self.result = OwnerResult(self.call.act.tag, status, self.write_bytes, self.cycles,
                                  self.useful, self.executed)
        self.state = "reply"

    def tick(self, *, request=None, services=Services(), abort=False, local_reset=False,
             coordinated_reset=None, window_ready=True, drain_ready=True, silu_ready=True,
             window_result=None, drain_result=None, silu_complete=False, result_ready=False):
        abort = abort or local_reset
        p = self.ports(services, abort=abort)
        p.update(request_fire=False, result_fire=False, window_fire=False, drain_fire=False,
                 silu_fire=False, window_result_fire=False, drain_result_fire=False)
        if coordinated_reset is not None:
            if frozenset(coordinated_reset) != RESET_DOMAIN:
                raise ValueError("coordinated reset must include all retained and external backends")
            self.__init__()
            return p
        s = self.state
        bad = abort or self.poison or services.error
        live = s not in ("idle", "reply", "locked")
        if live:
            self.cycles = (self.cycles + 1) & U64
        wf = p["window_result_ready"] and window_result is not None
        df = p["drain_result_ready"] and drain_result is not None
        # The single original owner cannot expose two terminals at once.
        if wf and df:
            raise ValueError("window and drain share one terminal backend")
        if (wf and not services.window_busy) or (df and not services.drain_busy):
            raise ValueError("terminal backend must remain busy until its acceptance edge")
        if wf:
            p["window_result_fire"] = True
            self.useful = (self.useful + window_result.useful_macs) & U64
            self.executed = (self.executed + window_result.executed_macs) & U64
        if df:
            p["drain_result_fire"] = True
            self.write_bytes = (self.write_bytes + drain_result.ddr_write_bytes) & U64
            self.useful = (self.useful + drain_result.useful_macs) & U64
            self.executed = (self.executed + drain_result.executed_macs) & U64
        if request is not None and p["request_ready"]:
            p["request_fire"] = True
            self.call = request
            self.ng = self.cycles = self.write_bytes = self.useful = self.executed = 0
            self.status = None
            if request.valid():
                self.state = "gateFlush"
            else:
                self._fail("Malformed")
        if s in ("gateFlush", "upFlush", "actFlush") and not bad:
            self.state = {"gateFlush": "gateIssue", "upFlush": "upIssue", "actFlush": "actIssue"}[s]
        if p["window_request"] is not None and window_ready:
            p["window_fire"] = True
            self.state = "upWait" if s == "upIssue" else "gateWait"
        if wf and s in ("gateWait", "upWait"):
            r, j = window_result, self.call.up if s == "upWait" else self.call.gate
            exact = ((r.tag, r.identity, r.ng, r.rows, r.cols, r.slot) ==
                     (j.tag, self.call.identity, self.ng, self.call.gate.m, WINDOW, int(s == "upWait"))
                     and r.committed and r.produced_beats == (self.call.gate.m // 16) * WINDOW
                     and r.ddr_write_bytes == 0 and services.lease_valid)
            if r.status or not exact or bad:
                self._fail(r.status)
            else:
                self.state = "siluIssue" if s == "upWait" else "upFlush"
        if p["silu_request"] is not None and silu_ready:
            p["silu_fire"] = True
            self.state = "siluWait"
        if s == "siluWait" and silu_complete and not bad:
            self.state = "actFlush"
        if p["drain_request"] is not None and drain_ready:
            p["drain_fire"] = True
            self.state = "actWait"
        if df and s == "actWait":
            r = drain_result
            exact = ((r.tag, r.identity, r.ng, r.rows, r.cols) ==
                     (self.call.act.tag, self.call.identity, self.ng, self.call.gate.m, WINDOW)
                     and r.committed and r.consumed_beats == self.call.gate.m // 16 * WINDOW
                     and r.ddr_write_bytes == self.call.gate.m * WINDOW * 4
                     and not services.tiles_leased and services.tiles_drained)
            if r.status or not exact or bad:
                self._fail(r.status)
            elif self.ng + WINDOW == WIDTH:
                if self.write_bytes == self.call.act.write_bytes:
                    self.state = "invalidate"
                else:
                    self._fail()
            else:
                self.ng += WINDOW
                self.state = "gateFlush"
        if s == "invalidate" and not bad:
            self.state = "retire"
        if (s == "retire" and not bad and not services.lease_valid and not services.window_busy
                and not services.drain_busy and not services.tiles_leased
                and services.tiles_drained and services.silu_drained):
            self._reply(None)
        explicit_error = (wf and bool(window_result.status)) or (df and bool(drain_result.status))
        if bad and live and s != "draining" and not explicit_error:
            self._fail()
        # Raw reset/abort is sticky even while a terminal is held or idle.
        if abort or services.error:
            self.poison = True
        if (s == "draining" and not services.window_busy and not services.drain_busy
                and services.tiles_drained and services.silu_drained and not services.bridge_busy):
            self._reply(self.status or "Protocol")
        if p["result"] is not None and result_ready:
            p["result_fire"] = True
            self.state = "locked" if self.poison or bad else "idle"
        return p


@dataclass(frozen=True)
class Region:
    base: int
    limit: int
    read: bool
    write: bool

    def contains(self, t):
        return self.base <= t.address < t.padded_end <= self.limit


@dataclass(frozen=True)
class Tensor:
    address: int
    dims: tuple
    dtype: int = 7
    tail: int = NULL
    # An injected TypedTensorReader terminal error, not a fake decoded success.
    reader_error: str | None = None

    @property
    def rank(self):
        return len(self.dims)

    @property
    def element_count(self):
        return prod(self.dims)

    @property
    def payload_bytes(self):
        return self.element_count * (2 if self.dtype == 5 else 4)

    @property
    def padded_end(self):
        return self.address + ((self.payload_bytes + 63) // 64) * 64

    def same_allocation(self, other):
        # Consumer policy tail and prefix-index provenance are not allocation.
        return (self.address, self.rank, self.dtype, self.dims, self.element_count,
                self.payload_bytes, self.padded_end) == (
                other.address, other.rank, other.dtype, other.dims, other.element_count,
                other.payload_bytes, other.padded_end)

    def overlaps(self, other):
        return overlap(self.address, self.padded_end, other.address, other.padded_end)


class Rejected(ValueError):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


class TypedRootReader:
    """Typed-reader boundary, not raw descriptor-chain/stride decoding."""
    def __init__(self, tensors, regions, descriptor_count=None):
        self.tensors = dict(tensors)
        self.regions = tuple(regions)
        self.descriptor_count = max(tensors, default=-1) + 1 if descriptor_count is None else descriptor_count
        self.reads = []

    def read(self, root, write=False):
        self.reads.append((root, write))
        if not uint(root, 24) or root == NULL or root >= self.descriptor_count or root not in self.tensors:
            raise Rejected("Malformed", "descriptor root bounds")
        t = self.tensors[root]
        if t.reader_error:
            raise Rejected(t.reader_error, "injected typed-reader terminal error")
        if t.dtype not in (5, 7) or not 1 <= t.rank <= 4:
            raise Rejected("Unsupported", "typed dtype/rank")
        if (not all(uint(d, 18) and d > 0 for d in t.dims) or t.element_count > 0xffffffff
                or not uint(t.address, 64) or t.address % 64 or t.padded_end > LIMIT):
            raise Rejected("Bounds", "typed full padded allocation")
        if not any((r.write if write else r.read) and r.contains(t) for r in self.regions):
            raise Rejected("Permission", "typed root access permission")
        return t


@dataclass(frozen=True)
class Policy:
    kind: str
    m: int = 0
    n: int = 0
    k: int = 0
    opcode: int = 0
    inputs: int = 2
    valid: bool = True


@dataclass(frozen=True)
class Command:
    opcode: int
    engine: int
    a: int
    b: int
    d: int
    wait: int
    signal: int
    reserved: int = 0

    @property
    def roots(self):
        return self.a, self.b, self.d


class VirtualRootPreflight:
    """Read all primary roots of every command, including unknown opcodes.

    Only the three captured group command words are compared for stability.
    Future opcode/policy semantics still belong to later normal Host decode.
    Softmax's public null B is skipped. Extra-root native profiles are excluded
    by the caller's profile admission. Reservation is the caller's final step.
    """
    def __init__(self, program, reader, gate_pc, captured, gate, up, *, max_commands=64, fetch_command=None):
        if not 21 <= max_commands <= 255 or not 0 < len(program) <= max_commands:
            raise Rejected("Bounds", "bounded public command count")
        if not 0 <= gate_pc <= len(program) - 3:
            raise Rejected("Malformed", "three consecutive public commands")
        self.program, self.reader = program, reader
        self.gate_pc, self.captured, self.gate, self.up = gate_pc, tuple(captured), gate, up
        self.fetch_command = fetch_command
        self.scan_command = None
        self.pc = self.slot = 0
        self.done = False
        self.trace = []

    def step(self):
        if self.done:
            return None
        if self.fetch_command is None:
            c = self.program[self.pc]
        else:
            if self.slot == 0:
                self.scan_command = self.fetch_command(self.pc)
            c = self.scan_command
        if self.slot == 0:
            valid = all(uint(x, 24) and x < self.reader.descriptor_count and x != NULL for x in (c.a, c.d))
            valid = valid and (c.b == NULL if c.opcode == 0x33 else uint(c.b, 24) and c.b != NULL and c.b < self.reader.descriptor_count)
            if not valid:
                raise Rejected("Malformed", "scanner public root bounds")
            if self.gate_pc <= self.pc < self.gate_pc + 3 and c != self.captured[self.pc - self.gate_pc]:
                raise Rejected("Protocol", "captured group command changed during scan")
        t = self.reader.read(c.roots[self.slot], self.slot == 2)
        self.trace.append((self.pc, self.slot, c.roots[self.slot]))
        gate_use = (self.pc, self.slot) in ((self.gate_pc, 2), (self.gate_pc + 2, 0))
        up_use = (self.pc, self.slot) in ((self.gate_pc + 1, 2), (self.gate_pc + 2, 1))
        exact_gate = gate_use and t.same_allocation(self.gate)
        exact_up = up_use and t.same_allocation(self.up)
        if ((t.overlaps(self.gate) and not exact_gate) or (t.overlaps(self.up) and not exact_up)
                or (gate_use and not exact_gate) or (up_use and not exact_up)):
            raise Rejected("Dependency", "non-designated virtual allocation consumer")
        if self.slot == 2:
            self.pc += 1
            self.slot = 0
            self.done = self.pc == len(self.program)
        else:
            self.slot = 2 if self.slot == 0 and c.opcode == 0x33 else self.slot + 1
        return self.trace[-1]


@dataclass(frozen=True)
class Completion:
    pc: int
    engine: int
    signal: int
    status: str | None


class HostControl:
    """Bounded decoded-command admission, scan and publication specification.

    Ordinary jobs use the same externally serviced DDR terminal path when the
    extension is off or no eligible gate is encountered. Only Dense/Activation
    ordinary semantics are modeled here; other commands can be scanned safely,
    then rejected by this bounded subset if execution reaches them.
    """
    def __init__(self, *, enabled=False, profile="legacy_qwen2", max_commands=64, event_slots=256):
        if enabled and profile != "legacy_qwen2":
            raise ValueError("resident FFN excludes native extra-root profiles")
        if not 21 <= max_commands <= 255 or event_slots < 4 or event_slots & (event_slots - 1):
            raise ValueError("Host parameter domain")
        self.enabled, self.profile, self.max_commands, self.event_slots = enabled, profile, max_commands, event_slots
        self.state = "idle"
        self.poison = False
        self.program = ()
        self.result = None

    def launch(self, program, reader, policies, *, epoch=0, reset_required=False, frontend=None):
        if self.state != "idle" or self.poison or reset_required:
            return False
        # Public-byte frontend is an explicit demand-fetch interface. The default
        # decoded path remains a launch snapshot for retained model fixtures.
        self.frontend = frontend
        self.program = list(program) if frontend is None else program
        self.reader, self.policies = reader, dict(policies)
        self.current_command = Command(0, 0, NULL, NULL, NULL, 0, 0)
        self.epoch = epoch
        self.pc = self.completed = self.jobs = self.useful = self.executed = self.written = 0
        self.events, self.published, self.virtual = {0}, [], []
        self.group = self.scanner = self.bound = None
        self.group_commands = ()
        self.completion_index = 0
        self.status = self.reason = None
        if not uint(epoch, 16) or not 0 < len(program) <= self.max_commands or not 0 < reader.descriptor_count <= NULL:
            self.status, self.state = "Bounds", "finish"
        else:
            self.state = "decode"
        return True

    def _fail(self, error):
        self.status, self.reason = error.status, str(error)
        self.poison = True
        self.state = "complete"
        self.completion_index = 0
        self.group_commands = ()

    def live(self, t):
        initial = any(r.read and not r.write and r.contains(t) for r in self.reader.regions)
        published = any(a <= t.address < t.padded_end <= e for a, e in self.published)
        return (initial or published) and not any(overlap(t.address, t.padded_end, a, e) for a, e in self.virtual)

    def _fresh(self, t):
        return not any(overlap(t.address, t.padded_end, a, e) for a, e in self.published + self.virtual)

    def _decode(self, pc, *, expected_wait=None, blocked_signals=(), virtual_inputs=None,
                expected_opcode=None):
        if self.frontend is None:
            c = self.program[pc]
        else:
            self.current_command = Command(0, 0, NULL, NULL, NULL, 0, 0)
            c = self.frontend.fetch_command(pc)
        self.current_command = c
        if c.opcode not in (0x20, 0x35) or c.engine != (2 if c.opcode == 0x20 else 3):
            raise Rejected("Unsupported", "bounded ordinary opcode/engine")
        if c.reserved:
            raise Rejected("Malformed", "reserved command bits")
        if self.frontend is not None:
            self.frontend.validate_command(c)
        if expected_opcode is not None and c.opcode != expected_opcode:
            raise Rejected("Malformed", "resident public command order")
        dependency = c.wait in self.events if expected_wait is None else c.wait == expected_wait
        if (not uint(c.wait, 16) or not uint(c.signal, 16) or c.wait >= self.event_slots
                or not 0 < c.signal < self.event_slots or not dependency or c.signal in self.events
                or c.signal == c.wait or c.signal in blocked_signals):
            raise Rejected("Dependency", "public event chain")
        a, b, d = tuple(self.reader.read(root, slot == 2) for slot, root in enumerate(c.roots))
        p = (self.policies.get(a.tail) if self.frontend is None else
             self.frontend.read_policy(c, (a, b, d)))
        if p is None or not p.valid or b.tail != NULL or d.tail != NULL:
            raise Rejected("Unsupported", "typed consumer policy/tails")
        if a.dtype != 7 or d.dtype != 7 or a.rank != 2 or b.rank != 2 or d.rank != 2:
            raise Rejected("Unsupported", "ordinary dtype/rank")
        m, n = d.dims
        if c.opcode == 0x20:
            k = a.dims[1]
            shape = (a.dims == (m, k) and b.dims == (k, n) and b.dtype in (5, 7)
                     and p.kind == "matrix" and (p.m, p.n, p.k) == (m, n, k)
                     and m > 0 and m <= 128 and 0 < n <= WIDTH and n % 16 == 0
                     and 0 < k <= WIDTH and k % 16 == 0 and (b.dtype != 5 or n % 32 == 0))
        else:
            k = n
            shape = (a.dims == b.dims == d.dims and n == WIDTH and 0 < m <= 128 and b.dtype == 7
                     and p.kind == "sfu" and p.opcode == 0x35 and p.inputs == 2)
        if not shape:
            raise Rejected("Unsupported", "ordinary shape/policy")
        if virtual_inputs is None:
            inputs_ok = self.live(a) and self.live(b)
        else:
            inputs_ok = a.same_allocation(virtual_inputs[0]) and b.same_allocation(virtual_inputs[1])
        if not inputs_ok:
            raise Rejected("Dependency", "source allocation liveness")
        if d.overlaps(a) or d.overlaps(b) or not self._fresh(d):
            raise Rejected("Permission", "destination allocation freshness")
        j = Job("Dense" if c.opcode == 0x20 else "Activation", (self.epoch << 16) | pc,
                a.address, b.address, d.address, m, n, k, d.payload_bytes, b.dtype == 5)
        return j, (a, b, d)

    def _admit(self):
        j, (a, b, d) = self._decode(self.pc)
        eligible = self.enabled and j.kind == "Dense" and j.m in (16, 128) and j.k == 1536 and j.n == WIDTH and j.weight_bf16
        self.bound = j
        if not eligible:
            self.group = None
            self.group_commands = ()
            self.state = "issue"
            return
        if self.pc + 2 >= len(self.program):
            raise Rejected("Malformed", "incomplete resident group")
        gate_pc = self.pc
        if self.frontend is None:
            c0, c1, c2 = self.program[gate_pc:gate_pc + 3]
            self.pc = gate_pc + 1
            if c1.opcode != 0x20:
                raise Rejected("Malformed", "resident public command order")
            u, (ua, ub, ud) = self._decode(self.pc, expected_wait=c0.signal, blocked_signals=(c0.signal,))
            self.pc = gate_pc + 2
            if c2.opcode != 0x35:
                raise Rejected("Malformed", "resident public command order")
            v, (_, _, vd) = self._decode(self.pc, expected_wait=c1.signal,
                                        blocked_signals=(c0.signal,), virtual_inputs=(d, ud))
        else:
            c0 = self.current_command
            self.frontend.validate_resident_gate((a, b, d))
            self.pc = gate_pc + 1
            u, (ua, ub, ud) = self._decode(self.pc, expected_wait=c0.signal,
                blocked_signals=(c0.signal,), expected_opcode=0x20)
            c1 = self.current_command
            if (u.m, u.n, u.k, u.weight_bf16) != (j.m, WIDTH, 1536, True):
                raise Rejected("Unsupported", "resident fixed Up profile")
            self.frontend.validate_resident_up((ua, ub, ud), (a, b, d))
            self.pc = gate_pc + 2
            v, (_, _, vd) = self._decode(self.pc, expected_wait=c1.signal,
                blocked_signals=(c0.signal,), virtual_inputs=(d, ud), expected_opcode=0x35)
            c2 = self.current_command
        if not ua.same_allocation(a):
            raise Rejected("Dependency", "Up requires exact A allocation")
        if (u.m, u.n, u.k, u.weight_bf16) != (j.m, WIDTH, 1536, True) or v.m != j.m:
            raise Rejected("Unsupported", "resident fixed profile")
        operands = (a, b, ub, d, ud, vd)
        if any(x.overlaps(y) for i, x in enumerate(operands) for y in operands[i + 1:]):
            raise Rejected("Permission", "resident full allocations pairwise disjoint")
        if not all(any(r.read and not r.write and r.contains(t) for r in self.reader.regions) for t in (b, ub)):
            raise Rejected("Permission", "resident weights readonly")
        if not all(any(r.read and r.write and r.contains(t) for r in self.reader.regions) for t in (d, ud, vd)):
            raise Rejected("Permission", "resident destinations readwrite")
        if len(self.virtual) + 2 > self.max_commands:
            raise Rejected("Permission", "widened virtual capacity")
        self.group = GroupRequest(j, u, v, (j.tag + 1) & 0xffffffff)
        self.group_commands = (c0, c1, c2)
        self.bound, self.pc = v, gate_pc + 2
        self.scanner = VirtualRootPreflight(self.program, self.reader, gate_pc, self.group_commands,
                                           d, ud, max_commands=self.max_commands,
                                           fetch_command=None if self.frontend is None else self.frontend.fetch_command)
        self.state = "scan"

    def ports(self, *, reset_required=False):
        command = (self.current_command if getattr(self, "frontend", None) is not None else
                   self.program[self.pc] if self.program and self.pc < len(self.program) else None)
        group_pending = self.group is not None
        completion = None
        if self.state == "complete" and not (self.enabled and self.status is None and reset_required):
            pc = self.pc
            if self.group_commands and self.status is None:
                command = self.group_commands[self.completion_index]
                pc = self.pc - 2 + self.completion_index
            completion = Completion(pc, command.engine, command.signal, self.status)
        return dict(state=self.state, group_request=self.group if self.state == "issue" else None,
                    ordinary_request=self.bound if self.state == "issue" and not group_pending else None,
                    owner_result_ready=self.state == "waitDone", completion=completion,
                    launch_result=self.result if self.state == "finish" else None,
                    reset_required=self.poison or reset_required)

    def tick(self, *, request_ready=True, owner_result=None, completion_ready=False,
             result_ready=False, reset_required=False, coordinated_reset=None):
        p = self.ports(reset_required=reset_required)
        p.update(request_fire=False, owner_result_fire=False, completion_fire=False, result_fire=False)
        if coordinated_reset is not None:
            if frozenset(coordinated_reset) != RESET_DOMAIN:
                raise ValueError("coordinated reset must cover complete backend domain")
            self.__init__(enabled=self.enabled, profile=self.profile, max_commands=self.max_commands,
                          event_slots=self.event_slots)
            return p
        s = self.state
        try:
            if s == "decode":
                self._admit()
            elif s == "scan":
                self.scanner.step()
                if self.scanner.done:
                    if len(self.virtual) + 2 > self.max_commands:
                        raise Rejected("Permission", "widened virtual reservation capacity")
                    self.virtual.extend((t.address, t.padded_end) for t in (self.scanner.gate, self.scanner.up))
                    self.state = "issue"
            elif s == "issue" and request_ready:
                p["request_fire"] = True
                self.jobs += 1
                self.state = "waitDone"
            elif s == "waitDone" and owner_result is not None:
                p["owner_result_fire"] = True
                r = owner_result
                if self.enabled and reset_required and (self.group is not None or r.status is None):
                    raise Rejected("Protocol", "raw backend reset fences unaccepted success")
                if r.tag != self.bound.tag:
                    raise Rejected("Protocol", "owner terminal tag")
                if r.status:
                    raise Rejected(r.status, "owner terminal error")
                if r.write_bytes != self.bound.write_bytes:
                    raise Rejected("Protocol", "owner terminal byte count")
                self.useful += r.useful_macs
                self.executed += r.executed_macs
                self.written += r.write_bytes
                self.completion_index = 0
                self.state = "complete"
            elif s == "complete":
                if self.enabled and self.status is None and reset_required:
                    raise Rejected("Protocol", "raw backend reset fences held unaccepted completion")
                if p["completion"] is not None and completion_ready:
                    p["completion_fire"] = True
                    if self.status:
                        self.state = "finish"
                    else:
                        self.events.add(p["completion"].signal)
                        self.completed += 1
                        if self.group_commands and self.completion_index < 2:
                            self.completion_index += 1
                        else:
                            self.published.append((self.bound.dst, self.bound.dst + self.bound.write_bytes))
                            self.group, self.group_commands = None, ()
                            self.pc += 1
                            self.state = "finish" if self.pc == len(self.program) else "decode"
            elif s == "finish" and result_ready:
                p["result_fire"] = True
                self.state = "locked" if self.poison else "idle"
        except Rejected as error:
            self._fail(error)
        if self.state == "finish":
            self.result = dict(status=self.status, completed=self.completed, jobs=self.jobs,
                               useful_macs=self.useful, executed_macs=self.executed, write_bytes=self.written)
        return p
