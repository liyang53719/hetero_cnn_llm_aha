"""C06.1 executable control oracle, NOT a production Command128/RTL backend.

Separate a 16-bit total program counter from bounded live tensor slots and
64-command fetch windows. Lifetimes end only at acknowledged completion,
never at a fetch-window boundary. The emitter/RTL integration is C06.2.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType


class ControlError(ValueError):
    pass


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ControlError(why)


def uint(value: int, bits: int, name: str, positive: bool = False) -> int:
    need(type(value) is int and int(positive) <= value < (1 << bits), 'invalid ' + name)
    return value


@dataclass(frozen=True)
class Tensor:
    name: str
    address: int
    size: int
    keep: bool = False

    def check(self) -> None:
        need(isinstance(self.name, str) and bool(self.name.strip()), 'tensor name')
        uint(self.address, 56, 'address')
        uint(self.size, 56, 'size', True)
        need(type(self.keep) is bool, 'keep must be boolean')
        need(self.address % 64 == 0 and self.size % 64 == 0, '64-byte extents required')
        need(self.address + self.size <= 1 << 56, 'address overflow')

    def overlaps(self, other: Tensor) -> bool:
        return self.address < other.address + other.size and other.address < self.address + self.size


@dataclass(frozen=True)
class Command:
    inputs: tuple[str, ...]
    output: Tensor


@dataclass(frozen=True)
class Program:
    readonly: tuple[Tensor, ...]
    commands: tuple[Command, ...]
    slots: int = 8
    window: int = 64


@dataclass(frozen=True)
class Compiled:
    program: Program
    last_use: Mapping[str, int]
    peak_live: int
    windows: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        need(isinstance(self.last_use, Mapping), 'last_use mapping required')
        # frozen=True alone does not freeze an embedded dict or its aliases.
        object.__setattr__(self, 'last_use', MappingProxyType(dict(self.last_use)))


def compile_program(program: Program) -> Compiled:
    need(isinstance(program, Program), 'Program required')
    uint(program.slots, 16, 'slots', True)
    uint(program.window, 16, 'window', True)
    need(isinstance(program.readonly, tuple) and isinstance(program.commands, tuple), 'immutable program required')
    count = len(program.commands)
    uint(count, 16, 'command count', True)
    defined: dict[str, Tensor] = {}
    last: dict[str, int] = {}
    for tensor in program.readonly:
        need(isinstance(tensor, Tensor), 'readonly tensor')
        tensor.check()
        need(tensor.name not in defined, 'duplicate tensor')
        need(not any(tensor.overlaps(t) for t in defined.values()), 'readonly overlap')
        defined[tensor.name] = tensor
        last[tensor.name] = -1
    for pc, cmd in enumerate(program.commands):
        need(isinstance(cmd, Command) and isinstance(cmd.inputs, tuple), 'immutable command required')
        need(all(isinstance(n, str) and n in defined for n in cmd.inputs), f'undefined/future producer pc={pc}')
        need(isinstance(cmd.output, Tensor), 'output tensor')
        cmd.output.check()
        need(cmd.output.name not in defined, 'duplicate producer identity')
        for name in cmd.inputs:
            last[name] = pc
        defined[cmd.output.name] = cmd.output
        last[cmd.output.name] = pc
    for name, tensor in defined.items():
        if tensor.keep:
            last[name] = count  # stays externally observable after program completion
    live = {t.name: t for t in program.readonly if last[t.name] >= 0}
    peak = len(live)
    need(peak <= program.slots, 'readonly live set exceeds capacity')
    for pc, cmd in enumerate(program.commands):
        need(set(cmd.inputs) <= live.keys(), 'producer released before final consumer')
        # Readonly memory is protected even after its handle can be reclaimed.
        need(not any(cmd.output.overlaps(t) for t in program.readonly), 'overwrite readonly region')
        need(not any(cmd.output.overlaps(t) for t in live.values()), f'live address alias pc={pc}')
        peak = max(peak, len(live) + 1)
        need(peak <= program.slots, f'live-slot capacity pc={pc}')
        live[cmd.output.name] = cmd.output
        live = {n: t for n, t in live.items() if last[n] > pc}
    windows = tuple((i, min(i + program.window, count)) for i in range(0, count, program.window))
    return Compiled(program, last, peak, windows)


@dataclass(frozen=True)
class Offer:
    epoch: int
    pc: int
    inputs: tuple[tuple[str, int, int], ...]  # identity, physical slot, slot generation
    output: tuple[str, int, int]
    address: int
    size: int


class WindowMachine:
    """Serial owner/event reference with stable offers, ACK fencing and lockout.

    This is event-driven software, not a hardware cycle/performance model.
    A slot generation prevents stale handles from aliasing newly reused slots.
    """
    def __init__(self, compiled: Compiled):
        need(isinstance(compiled, Compiled), 'compiled program required')
        checked = compile_program(compiled.program)
        need(compiled.last_use == checked.last_use and compiled.peak_live == checked.peak_live
             and compiled.windows == checked.windows and type(compiled.peak_live) is int
             and all(type(v) is int for v in compiled.last_use.values())
             and isinstance(compiled.windows, tuple)
             and all(isinstance(w, tuple) and len(w) == 2
                     and all(type(v) is int for v in w) for w in compiled.windows),
             'compiled metadata drift')
        self.spec = checked
        self.epoch = 0
        self.state = 'idle'
        self.pc = 0
        self.loaded_end = 0
        self.completed = 0
        self.acked_bytes = 0
        self.fault = ''
        self.live: dict[str, tuple[Tensor, int, int]] = {}
        self.generations = [0] * compiled.program.slots
        self.held: Offer | None = None
        self.trace: list[tuple] = []

    def start(self, epoch: int) -> None:
        uint(epoch, 16, 'epoch', True)
        need(self.state in ('idle', 'done'), 'busy or reset required')
        need(epoch > self.epoch, 'epoch reuse/wrap requires new session')
        self.epoch = epoch
        self.pc = self.loaded_end = self.completed = self.acked_bytes = 0
        self.fault = ''
        self.live = {}
        self.held = None
        self.trace = []
        for t in self.spec.program.readonly:
            if self.spec.last_use[t.name] >= 0:
                slot = len(self.live)
                self.generations[slot] += 1
                self.live[t.name] = (t, slot, self.generations[slot])
        self.state = 'fetch'

    def window_request(self) -> tuple[int, int, int] | None:
        if self.state != 'fetch':
            return None
        return (self.epoch, self.pc, min(self.pc + self.spec.program.window, len(self.spec.program.commands)))

    def _lock(self, message: str) -> None:
        self.fault = message
        self.state = 'locked'
        raise ControlError(message)

    def accept_window(self, epoch: int, start: int, end: int) -> None:
        if any(type(x) is not int for x in (epoch, start, end)) or self.window_request() != (epoch, start, end):
            self._lock('stale/malformed window')
        self.loaded_end = end
        self.trace.append(('window', start, end))
        self.state = 'offer'

    def offer(self) -> Offer | None:
        if self.state != 'offer':
            return None
        if self.held is None:
            cmd = self.spec.program.commands[self.pc]
            used = {slot for _, slot, _ in self.live.values()}
            slot = next(i for i in range(self.spec.program.slots) if i not in used)
            self.held = Offer(self.epoch, self.pc,
                tuple((n, self.live[n][1], self.live[n][2]) for n in cmd.inputs),
                (cmd.output.name, slot, self.generations[slot] + 1), cmd.output.address, cmd.output.size)
        return self.held

    def issue(self, ready: bool) -> Offer | None:
        need(type(ready) is bool, 'ready must be boolean')
        offer = self.offer()
        if offer is not None and ready:
            self.state = 'wait_ack'
            self.trace.append(('issue', self.pc))
            return offer
        return None

    def acknowledge(self, epoch: int, pc: int, write_bytes: int, error: bool = False) -> None:
        if type(epoch) is not int or type(pc) is not int or self.state != 'wait_ack' or epoch != self.epoch or pc != self.pc:
            self._lock('unexpected/stale/duplicate ACK')
        if type(error) is not bool or error or type(write_bytes) is not int or write_bytes != self.held.size:
            self._lock('failed/incomplete write ACK')
        # Physical ACK counted now; tensor/event visibility waits for completion.
        self.acked_bytes += write_bytes
        self.state = 'completion'

    def completion(self) -> tuple[int, int, int] | None:
        return (self.epoch, self.pc, self.held.size) if self.state == 'completion' else None

    def retire(self, ready: bool) -> bool:
        need(type(ready) is bool, 'ready must be boolean')
        if self.state != 'completion' or not ready:
            return False
        out = self.spec.program.commands[self.pc].output
        _, slot, generation = self.held.output
        self.generations[slot] = generation
        self.live[out.name] = (out, slot, generation)
        self.live = {n: v for n, v in self.live.items() if self.spec.last_use[n] > self.pc}
        self.trace.append(('retire', self.pc))
        self.completed += 1
        self.pc += 1
        self.held = None
        self.state = 'done' if self.pc == len(self.spec.program.commands) else ('fetch' if self.pc == self.loaded_end else 'offer')
        return True

    def reset(self) -> None:
        # Do not clear the epoch watermark: late responses cannot name a new run.
        self.live.clear()
        self.held = None
        self.state = 'idle'
        self.fault = ''


def chain_program(count: int, window: int = 64) -> Program:
    """Deterministic high-address, two reusable output extent control fixture."""
    uint(count, 16, 'count', True)
    base = 0x100000000
    ro = Tensor('input', base, 64)
    cmds = tuple(Command(('input' if i == 0 else f't{i-1}',),
        Tensor(f't{i}', base + 64 * (1 + i % 2), 64, keep=i == count - 1)) for i in range(count))
    return Program((ro,), cmds, slots=2, window=window)
