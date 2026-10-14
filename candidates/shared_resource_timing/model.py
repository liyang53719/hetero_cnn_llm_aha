"""Bounded, source-pinned single-clock timing ledger and basic Scalar1 replay.

This is a conditional source-FSM model, NEVER RTL measurement, a conversion of
typed-driver ticks, or a full-block cycle prediction. Only finite-input scalar
Add/Mul/op6 is replayed. Matrix leaf and DDR events can be checked when supplied
explicitly; their integrated scheduling/physical service is not synthesized here.

An event at E[k] describes pre-edge ready/valid sampled at that rising edge.
``done`` is the first edge at which result.valid can be sampled (not the edge
after which the result register changes). Windows are explicit [start, end)
clock slots. A scalar-only replay ends at the first reusable edge: accept E0,
normal E1, result.fire E2, next accept E3. This three-slot service window must
not be substituted for a hardware owner's launch-to-terminal interval.

No per-cycle arrays are allocated. Record limits bound diagnostic traces;
interval sweeps scale with the number of records, including very long holds.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import Iterable


class TimingError(ValueError):
    """Invalid/incomplete event evidence; no utilization result is admissible."""


class UnboundTimingError(TimingError):
    """No implemented production-source timing path for the requested action."""


CAPACITIES = MappingProxyType({
    "matrix_lanes": 4096, "matrix_contexts": 5, "matrix_issue_slots": 1,
    "vector_lanes": 16, "vector_requests": 1,
    "scalar_units": 1, "ddr_transfers": 1, "ddr_beats_per_slot": 1,
    "ddr_beat_bits": 512,
})
BASE = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/"
RTL_BASE = "rtl/matrix/candidates/rev8b_b/"


@dataclass(frozen=True)
class SourcePin:
    path: str
    sha256: str
    lines: tuple[tuple[int, int], ...]
    establishes: str


SOURCE_PINS = (
    SourcePin(BASE + "BlockFloat.scala",
              "9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5",
              ((15, 21), (39, 55), (58, 82), (108, 108)),
              "one Scalar; finite Add/Mul/op6 idle-normal-done; held result"),
    SourcePin(BASE + "MatrixPipeline.scala",
              "dd1f3859ac65fa4d4839105cf166cb5d3a1f4d2d786991eb0f22749ad4ceca3d",
              ((11, 22), (49, 71), (78, 108), (112, 135)),
              "8 physical slices; 5 contexts; tag8/result2; gating; group lifecycle"),
    SourcePin(RTL_BASE + "bf16_outer_product_array_control5_rev8b_b_candidate.sv",
              "e1afd499281df0493f1660bbfe8b1a5f6bfeea9e49899b0368372d23d4c790c2",
              ((10, 35),), "leaf E0 accept; E4 post-edge valid; E5 earliest fire"),
    SourcePin(RTL_BASE + "bf16_context_scheduler5_rev8b_b_candidate.sv",
              "a4c37b485f1e7eeed3012372024e8e7207bc33af6ff97bc307a5572aced6890e",
              ((21, 39), (52, 66)),
              "5 busy contexts; output fire releases context with same-edge reuse"),
    SourcePin(BASE + "VectorSilu.scala",
              "758f48c6f945fe78fafeb9d4086c43d4041ece5ead9a90b947379f7f522c32f9",
              ((21, 67), (94, 97)),
              "one 16-lane vector service; not a generic 35B Add/Mul binding"),
    SourcePin(BASE + "RetainedIdma.scala",
              "b7e424bca21cecc561045a707b62ee24a7cc7a0314cf8d218ce8e64bb24f29ee",
              ((7, 21), (41, 45), (53, 74)),
              "512-bit mailbox; single transfer through reply; true external write ACK"),
    SourcePin("candidates/qwen35_35b_exp/scalar.py",
              "5e8f44c7a9ab95d9b18fff2fe443b4cc8742b0f037b61ff12121f6ba12c2e8c5",
              ((1, 17), (38, 71)), "new IEEE decay is software-only, not old opcode4"),
    SourcePin("candidates/qwen35_35b_exp/gate_scalar.py",
              "c3661f498912ec55b70bd4344a53013409e567c6f01f78af26fe515e8710532d",
              ((1, 11), (19, 38)), "new Softplus has no production opcode binding"),
)

COMPLETE_BLOCK_BLOCKERS = (
    "35B IEEE decay exp and new Softplus lack production timing bindings",
    "35B generic Vector Add/Mul and IEEE policy lack an integrated timing binding",
    "physical DDR/controller timing is unknown; explicit external events are conditional inputs",
    "Matrix group/FIFO/operand/owner scheduling is not replayed by this scalar-only model",
    "full MoE/final-output and state/history commit path is not established by a prefix",
)
SCALAR_OPS = MappingProxyType({"add": 0, "mul": 1, "mul_ieee_rne": 6})
RESOURCES = frozenset(("matrix", "vector", "scalar", "ddr"))
EVENT_KINDS = frozenset(("request", "start", "normal", "done", "ack",
                         "read_data", "write_data", "write_ack"))
# Accounting priority, not a claim about the hardware critical path. Simultaneous
# activities are reported separately as activity totals, never added to wall time.
CYCLE_PRIORITY = ("matrix_issue", "vector_issue", "scalar_issue", "scalar_compute",
                  "result_retire", "ddr_service", "result_backpressure",
                  "matrix_in_flight", "ddr_wait", "dependency_wait", "input_wait", "control", "idle")


def _integer(value: int, label: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise TimingError(f"{label} must be an integer >= {minimum}")


def verify_sources(repo: Path) -> tuple[dict, ...]:
    """Refuse stale source assumptions before producing any timing result."""
    records = []
    for pin in SOURCE_PINS:
        try:
            raw = (Path(repo) / pin.path).read_bytes()
        except OSError as exc:
            raise TimingError(f"source pin unavailable: {pin.path}") from exc
        if hashlib.sha256(raw).hexdigest() != pin.sha256:
            raise TimingError(f"source pin changed; re-audit required: {pin.path}")
        if max(end for _, end in pin.lines) > len(raw.splitlines()):
            raise TimingError(f"source attribution out of range: {pin.path}")
        records.append(dict(path=pin.path, sha256=pin.sha256,
                            lines=[list(x) for x in pin.lines], establishes=pin.establishes))
    return tuple(records)


@dataclass(frozen=True)
class Interval:
    start: int
    end: int

    def __post_init__(self) -> None:
        _integer(self.start, "interval start")
        _integer(self.end, "interval end")
        if self.end <= self.start:
            raise TimingError("interval must be nonempty and half-open")

    @property
    def cycles(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class Phase:
    name: str
    window: Interval


@dataclass(frozen=True)
class Signal:
    window: Interval
    category: str


@dataclass(frozen=True)
class Event:
    cycle: int
    kind: str
    transaction: str
    clock: str = "core"
    unit: str = "hardware_cycle"


@dataclass(frozen=True)
class Operation:
    identity: str
    phase: str
    resource: str
    variant: str
    active_lanes: int = 1
    useful_macs: int = 0
    executed_macs: int = 0
    context: int | None = None
    operands: tuple[int, int] | None = None
    dependencies: tuple[str, ...] = ()
    # Required only for supplied DDR event traces. This identifies caller-owned
    # external inputs; it is not certification or a hardware-measurement claim.
    external_trace_sha256: str | None = None


def _finite_words(words: tuple[int, int] | None) -> None:
    if words is None or len(words) != 2:
        raise UnboundTimingError("basic Scalar timing requires both raw FP32 operand words")
    for word in words:
        if type(word) is not int or not 0 <= word < 1 << 32:
            raise TimingError("invalid FP32 operand word")
        if word & 0x7f800000 == 0x7f800000:
            raise UnboundTimingError("nonfinite precheck uses a different path; not replayed")


def _validate_operation(op: Operation) -> None:
    if not op.identity or not op.phase or op.resource not in RESOURCES:
        raise TimingError("operation needs identity, phase, and a known fixed resource")
    _integer(op.active_lanes, "active lanes", 1)
    _integer(op.useful_macs, "useful MACs")
    _integer(op.executed_macs, "executed MACs")
    if op.useful_macs > op.executed_macs:
        raise TimingError("useful MACs exceed executed MACs")
    if len(set(op.dependencies)) != len(op.dependencies) or op.identity in op.dependencies:
        raise TimingError("duplicate or self dependency")
    if op.resource != "matrix" and (op.useful_macs or op.executed_macs or op.context is not None):
        raise TimingError("only Matrix physical accepted lanes count as Matrix MACs/contexts")
    if op.resource == "scalar":
        if op.variant not in SCALAR_OPS:
            raise UnboundTimingError(f"Scalar path is not implemented: {op.variant}")
        if op.active_lanes != 1:
            raise TimingError("Scalar1 capacity cannot be expanded")
        _finite_words(op.operands)
    elif op.resource == "matrix":
        if op.variant != "retained_leaf_step":
            raise UnboundTimingError("only explicit retained leaf-step event checking is supported")
        if op.active_lanes > 4096 or op.active_lanes % 512 or op.executed_macs != op.active_lanes:
            raise TimingError("one accepted Matrix step executes selected physical 512-lane slices")
        if type(op.context) is not int or not 0 <= op.context < 5:
            raise TimingError("Matrix context must be 0..4; contexts do not multiply MAC capacity")
    elif op.resource == "vector":
        if op.active_lanes > 16:
            raise TimingError("Vector16 capacity cannot be expanded")
        raise UnboundTimingError("35B generic Vector timing is unbound; no default latency")
    else:
        if op.variant not in ("external_read64", "external_write64") or op.active_lanes != 1:
            raise UnboundTimingError("DDR requires explicit single-mailbox external cycle events")
        digest = op.external_trace_sha256
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise UnboundTimingError("DDR requires the SHA256 identity of its external input trace")


def _capacity_check(intervals: Iterable[tuple[Interval, int]], capacity: int, label: str) -> int:
    changes: Counter = Counter()
    for window, units in intervals:
        changes[window.start] += units
        changes[window.end] -= units
    active = peak = 0
    for cycle, delta in sorted(changes.items()):
        active += delta  # release and reuse on this boundary are simultaneous
        if not 0 <= active <= capacity:
            raise TimingError(f"{label} capacity conflict at E{cycle}: {active} > {capacity}")
        peak = max(peak, active)
    if active:
        raise TimingError(f"{label} resource interval did not close")
    return peak


def exclusive_cycle_buckets(window: Interval, signals: Iterable[Signal]) -> dict[str, int]:
    """Sweep boundaries, assigning exactly one category to every window cycle."""
    changes: dict[int, Counter] = defaultdict(Counter)
    changes[window.start]
    changes[window.end]
    for signal in signals:
        if signal.category not in CYCLE_PRIORITY or signal.category == "idle":
            raise TimingError(f"unknown/explicit idle activity category: {signal.category}")
        left, right = max(window.start, signal.window.start), min(window.end, signal.window.end)
        if left < right:
            changes[left][signal.category] += 1
            changes[right][signal.category] -= 1
    buckets = dict.fromkeys(CYCLE_PRIORITY, 0)
    active: Counter = Counter()
    points = sorted(changes)
    for left, right in zip(points, points[1:]):
        active.update(changes[left])
        category = next((name for name in CYCLE_PRIORITY if active[name] > 0), "idle")
        buckets[category] += right - left
    if sum(buckets.values()) != window.cycles:
        raise TimingError("cycle denominator partition is not exhaustive")
    return buckets


class Ledger:
    """A bounded diagnostic trace with fixed capacities and one global clock.

    Explicit Matrix/DDR traces are conditional inputs, not a latency generator.
    Unknown/missing timing cannot be hidden in a fabricated default duration.
    """

    def __init__(self, *, repo: Path, window: Interval, phases: Iterable[Phase],
                 scope: str = "primitive_subset", clock: str = "core", max_records: int = 65536):
        _integer(max_records, "record bound", 1)
        if scope not in ("primitive_subset", "prefix", "full_block") or not clock:
            raise TimingError("invalid scope or clock")
        self.repo, self.window, self.scope, self.clock = Path(repo), window, scope, clock
        self.max_records = max_records
        self.phases = tuple(phases)
        self.operations: dict[str, Operation] = {}
        self.events: list[Event] = []
        self.extra_signals: list[Signal] = []
        verify_sources(self.repo)
        self._check_phases()

    def _check_phases(self) -> None:
        names, cursor = set(), self.window.start
        for phase in self.phases:
            if not phase.name or phase.name in names or phase.window.start != cursor:
                raise TimingError("phase boundaries must be unique, ordered, gap-free and nonoverlapping")
            names.add(phase.name)
            cursor = phase.window.end
        if cursor != self.window.end:
            raise TimingError("phase boundaries must cover the entire declared wall window")

    def register(self, operation: Operation) -> None:
        _validate_operation(operation)
        if operation.identity in self.operations:
            raise TimingError("duplicate transaction identity")
        if operation.phase not in {p.name for p in self.phases}:
            raise TimingError("operation references an undeclared phase")
        if len(self.operations) + len(self.events) + len(self.extra_signals) >= self.max_records:
            raise TimingError("bounded diagnostic record limit reached; stream/chunk the source trace")
        self.operations[operation.identity] = operation

    def record(self, event: Event) -> None:
        _integer(event.cycle, "event cycle")
        if event.clock != self.clock or event.unit != "hardware_cycle":
            raise TimingError("mixed clocks or driver/handshake ticks are not hardware cycle evidence")
        if event.transaction not in self.operations or event.kind not in EVENT_KINDS:
            raise TimingError("event references unknown transaction or kind")
        if not self.window.start <= event.cycle < self.window.end:
            raise TimingError("event lies outside the explicit global window")
        if len(self.operations) + len(self.events) + len(self.extra_signals) >= self.max_records:
            raise TimingError("bounded diagnostic record limit reached; stream/chunk the source trace")
        self.events.append(event)

    def add_stall(self, signal: Signal) -> None:
        if signal.category not in ("dependency_wait", "input_wait", "control"):
            raise TimingError("only explicit dependency/input/control annotations may be added")
        if not self.window.start <= signal.window.start < signal.window.end <= self.window.end:
            raise TimingError("stall annotation outside global window")
        if len(self.operations) + len(self.events) + len(self.extra_signals) >= self.max_records:
            raise TimingError("bounded diagnostic record limit reached")
        self.extra_signals.append(signal)

    def _validate(self) -> tuple[dict[str, dict[str, int]], list[Signal], dict[str, int]]:
        self._check_phases()
        by_id: dict[str, dict[str, int]] = {identity: {} for identity in self.operations}
        phases = {p.name: p.window for p in self.phases}
        for event in self.events:
            edges = by_id[event.transaction]
            if event.kind in edges:
                raise TimingError(f"duplicate {event.kind} event: {event.transaction}")
            edges[event.kind] = event.cycle
            phase = phases[self.operations[event.transaction].phase]
            if not phase.start <= event.cycle < phase.end:
                raise TimingError("transaction crosses declared phase terminal boundary")
        resources: dict[str, list[tuple[Interval, int]]] = defaultdict(list)
        signals = list(self.extra_signals)
        for identity, op in self.operations.items():
            _validate_operation(op)
            edges = by_id[identity]
            required = {"request", "start", "done", "ack"}
            if op.resource == "scalar":
                required.add("normal")
            if op.resource == "ddr":
                required |= ({"write_data", "write_ack"} if op.variant == "external_write64" else {"read_data"})
            if set(edges) != required:
                raise TimingError(f"missing/unexpected events for {identity}: expected {sorted(required)}, got {sorted(edges)}")
            request, start, done, ack = (edges[k] for k in ("request", "start", "done", "ack"))
            if not request <= start <= done <= ack:
                raise TimingError(f"request/start/done/ACK ordering violated: {identity}")
            if start > request:
                signals.append(Signal(Interval(request, start), "input_wait"))
            if ack > done:
                signals.append(Signal(Interval(done, ack), "result_backpressure"))
            signals.append(Signal(Interval(ack, ack + 1), "result_retire"))
            if op.resource == "scalar":
                if edges["normal"] != start + 1 or done != start + 2:
                    raise TimingError("Scalar finite Add/Mul/op6 must follow E0/E1/E2 edges")
                resources["scalar_units"].append((Interval(start, ack + 1), 1))
                resources["scalar_request_port"].append((Interval(request, start + 1), 1))
                signals.extend((Signal(Interval(start, start + 1), "scalar_issue"),
                                Signal(Interval(start + 1, start + 2), "scalar_compute")))
            elif op.resource == "matrix":
                if done < start + 5:
                    raise TimingError("Matrix leaf result cannot fire before E5; service FIFO is not modeled")
                resources["matrix_lanes"].append((Interval(start, start + 1), op.active_lanes))
                resources["matrix_issue_slots"].append((Interval(start, start + 1), 1))
                resources["matrix_request_port"].append((Interval(request, start + 1), 1))
                resources["matrix_contexts"].append((Interval(start, ack), 1))
                resources[f"context_{op.context}"].append((Interval(start, ack), 1))
                signals.append(Signal(Interval(start, start + 1), "matrix_issue"))
                # In-flight is not a claim that all lanes toggle each cycle.
                # Clock-gated intervals still remain in the wall denominator.
                signals.append(Signal(Interval(start + 1, done), "matrix_in_flight"))
            elif op.resource == "ddr":
                data = edges["write_data"] if op.variant == "external_write64" else edges["read_data"]
                if not start <= data <= done:
                    raise TimingError("DDR data must occur after start and before response visibility")
                if "write_ack" in edges and not data < edges["write_ack"] <= done:
                    raise TimingError("DDR write needs a distinct external B ACK after data and before response")
                resources["ddr_transfers"].append((Interval(start, ack + 1), 1))
                resources["ddr_request_port"].append((Interval(request, start + 1), 1))
                resources["ddr_beats_per_slot"].append((Interval(data, data + 1), 1))
                signals.append(Signal(Interval(data, data + 1), "ddr_service"))
                if done > start:
                    signals.append(Signal(Interval(start, done), "ddr_wait"))
                if "write_ack" in edges:
                    signals.append(Signal(Interval(edges["write_ack"], edges["write_ack"] + 1), "ddr_service"))
            for dependency in op.dependencies:
                if dependency not in by_id or "ack" not in by_id[dependency]:
                    raise TimingError(f"missing dependency ACK: {dependency}")
                if start <= by_id[dependency]["ack"]:
                    raise TimingError("registered dependency cannot consume a result on its producer ACK edge")
        peaks = {name: _capacity_check(spans, 1 if name.startswith("context_") or name.endswith("_request_port") else CAPACITIES[name], name)
                 for name, spans in resources.items()}
        return by_id, signals, peaks

    def report(self) -> dict:
        pins = verify_sources(self.repo)
        _, signals, peaks = self._validate()
        phases = []
        for phase in self.phases:
            ops = [op for op in self.operations.values() if op.phase == phase.name]
            useful = sum(op.useful_macs for op in ops)
            executed = sum(op.executed_macs for op in ops)
            denominator = CAPACITIES["matrix_lanes"] * phase.window.cycles
            phases.append(dict(name=phase.name, start=phase.window.start, end=phase.window.end,
                               wall_cycles=phase.window.cycles, matrix_lane_cycle_denominator=denominator,
                               useful_matrix_macs=useful, executed_matrix_macs=executed,
                               padding_matrix_macs=executed - useful,
                               conditional_useful_matrix_fraction=useful / denominator,
                               conditional_executed_matrix_fraction=executed / denominator,
                               exclusive_cycle_buckets=exclusive_cycle_buckets(phase.window, signals)))
        useful = sum(x["useful_matrix_macs"] for x in phases)
        executed = sum(x["executed_matrix_macs"] for x in phases)
        denominator = 4096 * self.window.cycles
        blockers = list(COMPLETE_BLOCK_BLOCKERS)
        if self.scope != "full_block":
            blockers.insert(0, "declared scope is a prefix/subset, never a complete block")
        return dict(schema_version=1, evidence_kind="conditional_source_fsm_event_model",
                    clock=self.clock, time_unit="hardware_cycle", scope=self.scope,
                    window_start=self.window.start, window_end_exclusive=self.window.end,
                    wall_cycles=self.window.cycles,
                    denominator_convention="explicit [start_edge,end_edge); no inferred block terminal",
                    phase_boundaries_are_supplied=True, owner_terminal_fsm_replayed=False,
                    fixed_resources=dict(CAPACITIES), source_pins_verified=True, source_attribution=pins,
                    rtl_executed=False, rtl_measured_cycles=None, rtl_measured_utilization=None,
                    hardware_frequency_hz=None, complete_block=False,
                    full_block_cycles=None, full_block_utilization=None, completeness_blockers=blockers,
                    matrix_lane_cycle_denominator=denominator,
                    useful_matrix_macs=useful, executed_matrix_macs=executed,
                    padding_matrix_macs=executed - useful,
                    conditional_useful_matrix_fraction=useful / denominator,
                    conditional_executed_matrix_fraction=executed / denominator,
                    scalar_requests=sum(op.resource == "scalar" for op in self.operations.values()),
                    scalar_ops_are_matrix_macs=False, resource_peak_occupancy=peaks,
                    exclusive_cycle_buckets=exclusive_cycle_buckets(self.window, signals),
                    cycle_category_priority=list(CYCLE_PRIORITY),
                    cycle_categories_are_critical_path_measurement=False,
                    phases=phases, transaction_count=len(self.operations), event_count=len(self.events),
                    record_limit=self.max_records)

    def require_full_block_utilization(self) -> float:
        report = self.report()  # invalid/missing events must fail before completeness checks
        raise UnboundTimingError("complete-block utilization unavailable: " + "; ".join(report["completeness_blockers"]))


@dataclass(frozen=True)
class ScalarRequest:
    identity: str
    offered_cycle: int
    operation: str
    a_bits: int
    b_bits: int


def replay_scalar_primitives(requests: Iterable[ScalarRequest], *, repo: Path,
                             result_ready_low: Iterable[Interval] = (), start_cycle: int = 0,
                             stop_cycle: int | None = None, max_records: int = 65536) -> Ledger:
    """Execute the production finite-input idle/normal/done state transition.

    One request can be offered/held at a time; this does not insert a queue.
    ``result_ready_low`` is an explicit conditional environment waveform; outside
    those intervals ready is assumed high. The replay skips held intervals rather
    than iterating clock by clock. Numeric values/flags are not calculated here:
    finite inputs traverse normal even when arithmetic later reports an error.
    This function never authorizes continuing a real owner after such an error.
    """
    _integer(start_cycle, "start cycle")
    _integer(max_records, "record bound", 1)
    verify_sources(Path(repo))
    if stop_cycle is not None:
        _integer(stop_cycle, "stop cycle", start_cycle + 1)
    low = []
    for interval in result_ready_low:
        if len(low) >= max_records:
            raise TimingError("bounded ready waveform limit reached")
        low.append(interval)
    low.sort(key=lambda x: x.start)
    if any(a.end > b.start for a, b in zip(low, low[1:])):
        raise TimingError("ready-low intervals must not overlap")
    generated: list[tuple[Operation, tuple[Event, ...]]] = []
    next_accept, previous_accept, count = start_cycle, start_cycle - 1, 0
    for request in requests:
        count += 6  # one operation plus its five source-FSM events
        if count > max_records:
            raise TimingError("bounded scalar replay record limit reached")
        _integer(request.offered_cycle, "request offer")
        if request.offered_cycle < start_cycle or request.offered_cycle <= previous_accept:
            raise TimingError("single request port cannot replace a held request or offer two requests on one edge")
        op = Operation(request.identity, "scalar_replay", "scalar", request.operation,
                       operands=(request.a_bits, request.b_bits))
        _validate_operation(op)
        accepted = max(request.offered_cycle, next_accept)
        done = accepted + 2
        ack = done
        for interval in low:
            if interval.start > ack:
                break
            if interval.start <= ack < interval.end:
                ack = interval.end
        if stop_cycle is not None and ack >= stop_cycle:
            raise TimingError("missing result ACK inside requested replay window; result remains held")
        generated.append((op, tuple(Event(cycle, kind, request.identity) for kind, cycle in (
            ("request", request.offered_cycle), ("start", accepted),
            ("normal", accepted + 1), ("done", done), ("ack", ack)))))
        previous_accept, next_accept = accepted, ack + 1
    if not generated:
        raise TimingError("scalar replay requires at least one request")
    end = stop_cycle if stop_cycle is not None else next_accept
    ledger = Ledger(repo=repo, window=Interval(start_cycle, end),
                    phases=(Phase("scalar_replay", Interval(start_cycle, end)),), max_records=max_records)
    for operation, events in generated:
        ledger.register(operation)
        for event in events:
            ledger.record(event)
    ledger.report()  # fail closed before returning a purported completed replay
    return ledger
