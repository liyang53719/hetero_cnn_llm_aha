"""Cycle E0 for dependent accumulator-context interleaving."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import random


@dataclass(frozen=True)
class Operation:
    context: int
    delta: int
    tag: int
    clear: bool = False
    last: bool = False


@dataclass(frozen=True)
class Completion:
    context: int
    value: int
    tag: int
    last: bool


class ContextPipeline:
    def __init__(self, contexts: int, latency: int) -> None:
        if contexts <= 0 or latency <= 0:
            raise ValueError("context pipeline geometry")
        self.contexts = contexts
        self.latency = latency
        self.cycle = 0
        self.busy = [False] * contexts
        self.valid = [False] * contexts
        self.accumulator = [0] * contexts
        self.inflight: deque[tuple[int, Operation, int]] = deque()
        self.accepted = 0
        self.completed = 0

    def ready(self, context: int) -> bool:
        return 0 <= context < self.contexts and not self.busy[context]

    def issue(self, operation: Operation) -> bool:
        if not self.ready(operation.context):
            return False
        base = 0 if operation.clear or not self.valid[operation.context] else self.accumulator[operation.context]
        self.busy[operation.context] = True
        self.inflight.append((self.cycle + self.latency, operation, base + operation.delta))
        self.accepted += 1
        return True

    def tick(self, output_ready: bool = True) -> tuple[Completion, ...]:
        self.cycle += 1
        output: list[Completion] = []
        if output_ready and self.inflight and self.inflight[0][0] <= self.cycle:
            _, operation, value = self.inflight.popleft()
            self.accumulator[operation.context] = value
            self.valid[operation.context] = True
            self.busy[operation.context] = False
            self.completed += 1
            output.append(Completion(operation.context, value, operation.tag, operation.last))
        return tuple(output)


def dependent_round_robin(steps: int, contexts: int, latency: int) -> dict[str, object]:
    model = ContextPipeline(contexts, latency)
    issued = 0
    tags: list[int] = []
    while model.completed < steps:
        context = issued % contexts if issued < steps else 0
        if issued < steps and model.issue(Operation(context, 1, issued, clear=issued < contexts, last=issued == steps - 1)):
            issued += 1
        tags.extend(completion.tag for completion in model.tick())
    if sorted(tags) != list(range(steps)):
        raise AssertionError("completion tags")
    for context in range(contexts):
        expected = (steps + contexts - 1 - context) // contexts
        if model.accumulator[context] != expected:
            raise AssertionError("context recurrence")
    return {
        "status": "PASS",
        "steps": steps,
        "contexts": contexts,
        "latency": latency,
        "cycles": model.cycle,
        "issue_utilization": steps / model.cycle,
        "accepted": model.accepted,
        "completed": model.completed,
    }


def randomized_backpressure(cases: int = 10_000, contexts: int = 4, latency: int = 4, seed: int = 5012) -> dict[str, object]:
    rng = random.Random(seed)
    model = ContextPipeline(contexts, latency)
    issued = 0
    completed_tags: set[int] = set()
    while issued < cases or model.completed < cases:
        if issued < cases:
            context = rng.randrange(contexts)
            if model.issue(Operation(context, rng.randrange(-8, 9), issued, clear=not model.valid[context])):
                issued += 1
        for completion in model.tick(output_ready=rng.randrange(4) != 0):
            if completion.tag in completed_tags:
                raise AssertionError("duplicate completion")
            completed_tags.add(completion.tag)
    if completed_tags != set(range(cases)):
        raise AssertionError("completion coverage")
    return {"status": "PASS", "cases": cases, "cycles": model.cycle}
