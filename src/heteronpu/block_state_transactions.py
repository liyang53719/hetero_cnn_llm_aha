"""C07.1 word-level state/ACK event contract, not a DDR/SRAM/RTL model.

Reuse StateCommitModel for accepted-prefix publication and the ten StateDomain
IDs. Memory requests target an unpublished shadow. All issued ACKs must drain,
including after poison. Successful ACK bytes count transport completion, NOT
committed bytes. Reset invalidates ownership, not persistent committed state.

Tickets and reset epochs are non-wrapping Python integers; no finite RTL tag
width, AXI burst semantics, cache coherence, or durable crash recovery is claimed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .state_commit_protocol import StateCommitModel, StateDomain, StateWrite


class StateContractError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise StateContractError(message)


def integer(value: int, name: str, *, minimum: int = 0, maximum: int | None = None) -> None:
    require(type(value) is int and value >= minimum and
            (maximum is None or value <= maximum), 'invalid ' + name)


@dataclass(frozen=True)
class Owner:
    request: int
    layer: int
    epoch: int
    generation: int
    txn_id: int
    ticket: int

    def __post_init__(self) -> None:
        for name in ('request', 'layer', 'epoch', 'txn_id', 'ticket'):
            integer(getattr(self, name), name)
        integer(self.generation, 'generation', maximum=0xFFFFFFFF)


@dataclass(frozen=True)
class WordWrite:
    tag: int
    step: int
    domain: StateDomain
    key: int
    value: int

    def __post_init__(self) -> None:
        for name in ('tag', 'step', 'key'):
            integer(getattr(self, name), name)
        integer(self.value, 'word value', maximum=0xFFFFFFFF)
        require(type(self.domain) is StateDomain, 'invalid state domain')


@dataclass
class _Pending:
    sequence: int
    steps: int
    writes: dict[int, WordWrite]
    received: set[int] = field(default_factory=set)
    successful_ack_bytes: int = 0
    poisoned: bool = False


@dataclass(frozen=True)
class StateResult:
    owner: Owner
    committed: bool
    reason: str
    generation: int
    writes_committed: int
    successful_ack_bytes: int
    acknowledgements: int


class BlockStateTransactions:
    """Single-threaded event model. Parallel owners are explicitly interleaved."""

    def __init__(self, slots: int = 8) -> None:
        integer(slots, 'slots', minimum=1)
        self.slots = slots
        self._core = StateCommitModel()
        self._sequences: dict[tuple[int, int], int] = {}
        self._epochs: dict[int, int] = {}
        self._active: dict[Owner, _Pending] = {}
        self._next_ticket = 0
        self.counters = dict(started=0, committed=0, failed=0, resets=0,
                             reset_discarded=0, successful_ack_bytes=0,
                             error_acks=0, suppressed_acks=0, protocol_errors=0)

    def _sequence(self, request: int, layer: int) -> int:
        integer(request, 'request'); integer(layer, 'layer')
        scope = (request, layer)
        if scope not in self._sequences:
            self._sequences[scope] = len(self._sequences)
        return self._sequences[scope]

    def seed(self, request: int, layer: int,
             words: Mapping[tuple[StateDomain, int], int], *, generation: int = 0) -> None:
        """Initialize a fresh scope with nonzero pre-existing state, once only."""
        integer(request, 'request'); integer(layer, 'layer')
        integer(generation, 'generation', maximum=0xFFFFFFFF)
        require((request, layer) not in self._sequences, 'scope already exists')
        require(isinstance(words, Mapping), 'invalid seed words')
        frozen = []
        for key, value in words.items():
            require(type(key) is tuple and len(key) == 2, 'invalid seed address')
            frozen.append(WordWrite(0, 0, key[0], key[1], value))
        sequence = self._sequence(request, layer)
        self._core.generations[sequence] = generation
        for w in frozen:
            self._core.state[(sequence, w.domain, w.key)] = w.value

    def snapshot(self, request: int, layer: int) -> dict:
        return self._core.snapshot(self._sequence(request, layer))

    def generation(self, request: int, layer: int) -> int:
        return self._core.generation(self._sequence(request, layer))

    @property
    def active_count(self) -> int:
        return len(self._active)

    def begin(self, request: int, layer: int, txn_id: int, steps: int,
              writes: Iterable[WordWrite]) -> Owner:
        integer(request, 'request'); integer(layer, 'layer'); integer(txn_id, 'txn_id')
        integer(steps, 'steps', minimum=1)
        require(len(self._active) < self.slots, 'no free transaction slot')
        frozen = tuple(writes)
        require(bool(frozen) and all(type(w) is WordWrite for w in frozen), 'invalid writes')
        require(len({w.tag for w in frozen}) == len(frozen), 'duplicate write tag')
        require(all(w.step < steps for w in frozen), 'write outside speculative window')
        require(all(a.step <= b.step for a, b in zip(frozen, frozen[1:])),
                'writes must be in program step order')
        require(not any(o.request == request and o.layer == layer and o.txn_id == txn_id
                        for o in self._active), 'duplicate active transaction identity')
        sequence = self._sequence(request, layer)
        generation = self._core.generation(sequence)
        require(generation < 0xFFFFFFFF, 'generation exhausted; explicit new scope required')
        owner = Owner(request, layer, self._epochs.get(request, 0), generation,
                      txn_id, self._next_ticket)
        self._next_ticket += 1
        self._core.start(owner.ticket, sequence, steps, {w.domain for w in frozen})
        for w in frozen:
            self._core.record_write(owner.ticket, StateWrite(w.step, w.domain, w.key, w.value))
        self._active[owner] = _Pending(sequence, steps, {w.tag: w for w in frozen})
        self.counters['started'] += 1
        return owner

    def _pending(self, owner: Owner) -> _Pending:
        require(type(owner) is Owner, 'invalid owner')
        require(owner in self._active, 'inactive or stale owner')
        return self._active[owner]

    def poison(self, owner: Owner) -> None:
        self._pending(owner).poisoned = True
        self._core.fail(owner.ticket)

    def acknowledge(self, owner: Owner, tag: int, *, okay: bool, byte_count: int) -> bool:
        require(type(owner) is Owner, 'invalid owner')
        integer(tag, 'ACK tag')
        require(type(okay) is bool, 'invalid ACK status')
        integer(byte_count, 'ACK byte count')
        # Word model: errors certify no successful bytes; no invented partial B count.
        require(byte_count == (4 if okay else 0), 'ACK byte count/status mismatch')
        pending = self._active.get(owner)
        if pending is None or owner.epoch != self._epochs.get(owner.request, 0):
            self.counters['suppressed_acks'] += 1
            return False
        if tag not in pending.writes or tag in pending.received:
            self.counters['protocol_errors'] += 1
            self.poison(owner)
            raise StateContractError('unknown or duplicate ACK tag')
        pending.received.add(tag)
        if okay:
            pending.successful_ack_bytes += byte_count
            self.counters['successful_ack_bytes'] += byte_count
        else:
            self.counters['error_acks'] += 1
            self.poison(owner)
        return True

    def finish(self, owner: Owner, accepted_steps: int | None = None) -> StateResult:
        pending = self._pending(owner)
        prefix = pending.steps if accepted_steps is None else accepted_steps
        integer(prefix, 'accepted prefix', maximum=pending.steps)
        require(len(pending.received) == len(pending.writes), 'outstanding ACKs')
        current = self._core.generation(pending.sequence)
        reason = 'poisoned' if pending.poisoned else 'stale_generation' if current != owner.generation else 'committed'
        if reason == 'committed':
            for domain in {w.domain for w in pending.writes.values()}:
                self._core.acknowledge(owner.ticket, domain)
            result = self._core.commit(owner.ticket, prefix)
            self.counters['committed'] += 1
        else:
            result = self._core.discard(owner.ticket)
            self.counters['failed'] += 1
        del self._active[owner]
        return StateResult(owner, result.committed, reason, result.new_generation,
                           result.writes_committed, pending.successful_ack_bytes,
                           len(pending.received))

    def reset(self, request: int) -> int:
        """Invalidate all layers/in-flight shadows of one request, retaining old state.

        Per-transaction ACK counts disappear. Lifetime diagnostic counters retain
        previously observed successful ACKs; this is not an RTL reset-register spec.
        """
        integer(request, 'request')
        self._epochs[request] = self._epochs.get(request, 0) + 1
        victims = [o for o in self._active if o.request == request]
        for owner in victims:
            self._core.discard(owner.ticket)
            del self._active[owner]
        self.counters['reset_discarded'] += len(victims)
        self.counters['resets'] += 1
        return self._epochs[request]
