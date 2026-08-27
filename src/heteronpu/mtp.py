"""MTP deterministic verification and transactional state commit/rollback."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

T = TypeVar('T')


@dataclass(frozen=True)
class Result:
    accepted: int
    committed: tuple[int, ...]
    rejected: tuple[int, ...]
    bonus: int | None


def verify(draft: Sequence[int], target: Sequence[int]) -> Result:
    if len(target) < len(draft):
        raise ValueError('coverage')
    accepted = 0
    for lhs, rhs in zip(draft, target, strict=False):
        if lhs != rhs:
            break
        accepted += 1
    return Result(
        accepted,
        tuple(int(x) for x in draft[:accepted]),
        tuple(int(x) for x in draft[accepted:]),
        int(target[len(draft)]) if accepted == len(draft) and len(target) > len(draft) else None,
    )


@dataclass
class TransactionalLog(Generic[T]):
    """Minimal state journal used to validate speculative state rollback semantics."""

    committed: list[T]
    speculative: list[T]

    @classmethod
    def empty(cls) -> 'TransactionalLog[T]':
        return cls([], [])

    def checkpoint(self) -> int:
        return len(self.speculative)

    def append(self, value: T) -> None:
        self.speculative.append(value)

    def resolve(self, checkpoint: int, accepted: int) -> tuple[T, ...]:
        if not 0 <= checkpoint <= len(self.speculative):
            raise ValueError('checkpoint')
        tail = self.speculative[checkpoint:]
        if not 0 <= accepted <= len(tail):
            raise ValueError('accepted')
        commit = tail[:accepted]
        self.committed.extend(commit)
        del self.speculative[checkpoint:]
        return tuple(commit)


@dataclass(frozen=True)
class MTPResolution(Generic[T]):
    verification: Result
    state_committed: tuple[T, ...]


def resolve_speculation(draft: Sequence[int], target: Sequence[int], journal: TransactionalLog[T], checkpoint: int) -> MTPResolution[T]:
    result = verify(draft, target)
    committed = journal.resolve(checkpoint, result.accepted)
    return MTPResolution(result, committed)
