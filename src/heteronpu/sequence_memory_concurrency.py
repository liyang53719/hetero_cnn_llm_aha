"""Cycle model for concurrent Sequence Memory translation and data service.

This is an executable protocol reference for the future KV/QSA/GDN state
memory complex.  It models TLB and leaf-cache lookup, page-walk MSHRs,
miss coalescing, bounded outstanding data transactions, out-of-order response,
in-order retirement and stale-generation suppression.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import asdict, dataclass
import hashlib
import heapq
import random
from typing import Iterable


@dataclass(frozen=True)
class MemoryRequest:
    request_id: int
    sequence_id: int
    logical_page: int
    generation: int
    write: bool = False

    @property
    def page_key(self) -> tuple[int, int, int]:
        return (self.sequence_id, self.logical_page, self.generation)

    @property
    def leaf_key(self) -> tuple[int, int, int]:
        return (self.sequence_id, self.logical_page // 1024, self.generation)


@dataclass(frozen=True)
class Completion:
    request_id: int
    cycle: int
    stale: bool
    physical_page: int | None


@dataclass(frozen=True)
class ModelConfig:
    tlb_entries: int = 64
    leaf_cache_entries: int = 4
    mshr_entries: int = 8
    max_outstanding_walks: int = 4
    max_outstanding_data: int = 16
    issue_width: int = 2
    leaf_hit_walk_latency: int = 18
    leaf_miss_walk_latency: int = 72
    data_latency_min: int = 48
    data_latency_max: int = 128

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if int(value) <= 0:
                raise ValueError("all configuration values must be positive")
        if self.data_latency_min > self.data_latency_max:
            raise ValueError("data latency range")


class _LRU:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.values: OrderedDict[object, object] = OrderedDict()

    def get(self, key: object) -> object | None:
        if key not in self.values:
            return None
        value = self.values.pop(key)
        self.values[key] = value
        return value

    def put(self, key: object, value: object) -> None:
        if key in self.values:
            self.values.pop(key)
        elif len(self.values) >= self.capacity:
            self.values.popitem(last=False)
        self.values[key] = value


@dataclass
class _MSHR:
    request_ids: list[int]
    requests: list[MemoryRequest]
    due_cycle: int
    physical_page: int
    leaf_key: tuple[int, int, int]
    leaf_miss: bool


class SequenceMemoryModel:
    def __init__(self, config: ModelConfig, *, seed: int = 0x5E0C) -> None:
        self.config = config
        self.rng = random.Random(seed)
        self.tlb = _LRU(config.tlb_entries)
        self.leaf_cache = _LRU(config.leaf_cache_entries)
        self.generations: dict[int, int] = {}
        self.next_physical_page = 1

    def set_generation(self, sequence_id: int, generation: int) -> None:
        self.generations[int(sequence_id)] = int(generation)

    def _physical_page(self, request: MemoryRequest) -> int:
        digest = hashlib.blake2s(
            f"{request.sequence_id}:{request.logical_page}:{request.generation}".encode(),
            digest_size=4,
        ).digest()
        return 1 + int.from_bytes(digest, "little")

    def run(self, requests: Iterable[MemoryRequest]) -> dict[str, object]:
        incoming = deque(sorted(tuple(requests), key=lambda item: item.request_id))
        if len({request.request_id for request in incoming}) != len(incoming):
            raise ValueError("request IDs must be unique")
        request_by_id = {request.request_id: request for request in incoming}
        next_retire = min(request_by_id, default=0)
        final_retire = max(request_by_id, default=-1)
        cycle = 0
        mshr: dict[tuple[int, int, int], _MSHR] = {}
        walk_events: list[tuple[int, int, tuple[int, int, int]]] = []
        data_events: list[tuple[int, int, int, int]] = []
        reorder: dict[int, Completion] = {}
        completions: list[Completion] = []
        serial = 0
        counters = {
            "accepted": 0,
            "retired": 0,
            "stale_rejected": 0,
            "tlb_hits": 0,
            "tlb_misses": 0,
            "leaf_hits": 0,
            "leaf_misses": 0,
            "walks_issued": 0,
            "mshr_coalesced": 0,
            "mshr_full_stalls": 0,
            "walk_limit_stalls": 0,
            "data_limit_stalls": 0,
            "out_of_order_arrivals": 0,
            "max_mshr_used": 0,
            "max_data_outstanding": 0,
            "max_reorder_used": 0,
        }
        ready_for_data: deque[tuple[MemoryRequest, int]] = deque()

        while incoming or mshr or walk_events or ready_for_data or data_events or reorder:
            cycle += 1
            while walk_events and walk_events[0][0] <= cycle:
                _, _, key = heapq.heappop(walk_events)
                entry = mshr.pop(key)
                self.leaf_cache.put(entry.leaf_key, True)
                self.tlb.put(key, entry.physical_page)
                for request in entry.requests:
                    ready_for_data.append((request, entry.physical_page))

            while data_events and data_events[0][0] <= cycle:
                _, _, request_id, physical_page = heapq.heappop(data_events)
                request = request_by_id[request_id]
                stale = self.generations.get(request.sequence_id, request.generation) != request.generation
                completion = Completion(request_id, cycle, stale, None if stale else physical_page)
                if request_id != next_retire:
                    counters["out_of_order_arrivals"] += 1
                reorder[request_id] = completion
                counters["max_reorder_used"] = max(counters["max_reorder_used"], len(reorder))

            while next_retire in reorder:
                completion = reorder.pop(next_retire)
                completions.append(completion)
                counters["retired"] += 1
                if completion.stale:
                    counters["stale_rejected"] += 1
                next_retire += 1

            issue_budget = self.config.issue_width
            while ready_for_data and issue_budget:
                if len(data_events) >= self.config.max_outstanding_data:
                    counters["data_limit_stalls"] += 1
                    break
                request, physical_page = ready_for_data.popleft()
                latency = self.rng.randint(self.config.data_latency_min, self.config.data_latency_max)
                serial += 1
                heapq.heappush(data_events, (cycle + latency, serial, request.request_id, physical_page))
                issue_budget -= 1
                counters["max_data_outstanding"] = max(counters["max_data_outstanding"], len(data_events))

            accept_budget = self.config.issue_width
            while incoming and accept_budget:
                request = incoming[0]
                current_generation = self.generations.setdefault(request.sequence_id, request.generation)
                if current_generation != request.generation:
                    incoming.popleft()
                    reorder[request.request_id] = Completion(request.request_id, cycle, True, None)
                    counters["accepted"] += 1
                    accept_budget -= 1
                    continue

                physical = self.tlb.get(request.page_key)
                if physical is not None:
                    incoming.popleft()
                    ready_for_data.append((request, int(physical)))
                    counters["tlb_hits"] += 1
                    counters["accepted"] += 1
                    accept_budget -= 1
                    continue

                counters["tlb_misses"] += 1
                if request.page_key in mshr:
                    incoming.popleft()
                    entry = mshr[request.page_key]
                    entry.request_ids.append(request.request_id)
                    entry.requests.append(request)
                    counters["mshr_coalesced"] += 1
                    counters["accepted"] += 1
                    accept_budget -= 1
                    continue

                if len(mshr) >= self.config.mshr_entries:
                    counters["mshr_full_stalls"] += 1
                    break
                if len(walk_events) >= self.config.max_outstanding_walks:
                    counters["walk_limit_stalls"] += 1
                    break

                incoming.popleft()
                leaf_hit = self.leaf_cache.get(request.leaf_key) is not None
                if leaf_hit:
                    counters["leaf_hits"] += 1
                    latency = self.config.leaf_hit_walk_latency
                else:
                    counters["leaf_misses"] += 1
                    latency = self.config.leaf_miss_walk_latency
                physical = self._physical_page(request)
                due = cycle + latency
                entry = _MSHR([request.request_id], [request], due, physical, request.leaf_key, not leaf_hit)
                mshr[request.page_key] = entry
                serial += 1
                heapq.heappush(walk_events, (due, serial, request.page_key))
                counters["walks_issued"] += 1
                counters["accepted"] += 1
                accept_budget -= 1
                counters["max_mshr_used"] = max(counters["max_mshr_used"], len(mshr))

            if cycle > 10_000_000:
                raise RuntimeError("Sequence Memory model deadlock")

        if counters["accepted"] != len(request_by_id) or counters["retired"] != len(request_by_id):
            raise AssertionError(counters)
        if completions and [item.request_id for item in completions] != list(range(min(request_by_id), final_retire + 1)):
            raise AssertionError("retirement order")

        return {
            "schema_version": 1,
            "status": "PASS",
            "config": asdict(self.config),
            "requests": len(request_by_id),
            "cycles": cycle,
            "requests_per_cycle": len(request_by_id) / cycle if cycle else 0.0,
            "counters": counters,
            "completion_sha256": hashlib.sha256(
                b"".join(
                    item.request_id.to_bytes(4, "little")
                    + item.cycle.to_bytes(8, "little")
                    + bytes([item.stale])
                    + int(item.physical_page or 0).to_bytes(4, "little")
                    for item in completions
                )
            ).hexdigest(),
        }


def coalesced_trace(groups: int = 128, requests_per_page: int = 8) -> tuple[MemoryRequest, ...]:
    requests: list[MemoryRequest] = []
    request_id = 0
    for group in range(groups):
        page = group % 32
        for _ in range(requests_per_page):
            requests.append(MemoryRequest(request_id, group % 4, page, 1))
            request_id += 1
    return tuple(requests)


def random_trace(count: int = 4096, *, seed: int = 0x51A7) -> tuple[MemoryRequest, ...]:
    rng = random.Random(seed)
    return tuple(
        MemoryRequest(request_id, rng.randrange(16), rng.randrange(16384), 1, bool(rng.getrandbits(1)))
        for request_id in range(count)
    )


def sequence_memory_concurrency_report() -> dict[str, object]:
    cases: dict[str, object] = {}
    for mshr_entries in (4, 8, 16):
        for data_outstanding in (8, 16, 32):
            config = ModelConfig(mshr_entries=mshr_entries, max_outstanding_walks=min(8, mshr_entries), max_outstanding_data=data_outstanding)
            model = SequenceMemoryModel(config, seed=0x5000 + mshr_entries * 100 + data_outstanding)
            for sequence in range(16):
                model.set_generation(sequence, 1)
            result = model.run(random_trace())
            cases[f"random_m{mshr_entries}_d{data_outstanding}"] = result

    coalesced_model = SequenceMemoryModel(ModelConfig(mshr_entries=8, max_outstanding_walks=8, max_outstanding_data=32), seed=0xC011)
    for sequence in range(4):
        coalesced_model.set_generation(sequence, 1)
    coalesced = coalesced_model.run(coalesced_trace())

    stale_model = SequenceMemoryModel(ModelConfig(), seed=0x57A1)
    stale_model.set_generation(7, 2)
    stale = stale_model.run(tuple(MemoryRequest(i, 7, i, 1) for i in range(64)))

    selected = min(
        ((name, result) for name, result in cases.items()),
        key=lambda item: (item[1]["cycles"], item[1]["config"]["mshr_entries"] + item[1]["config"]["max_outstanding_data"]),
    )
    return {
        "schema_version": 1,
        "status": "PASS",
        "evidence_class": "SequenceMemory_concurrent_cycle_E0_not_AXI_iDMA_E3",
        "sweep": {
            name: {
                "status": result["status"],
                "cycles": result["cycles"],
                "requests_per_cycle": result["requests_per_cycle"],
            }
            for name, result in cases.items()
        },
        "coalescing_case": coalesced,
        "stale_generation_case": stale,
        "selected_sandbox_point": {
            "name": selected[0],
            "config": selected[1]["config"],
            "cycles": selected[1]["cycles"],
            "requests_per_cycle": selected[1]["requests_per_cycle"],
        },
        "frozen_contract": {
            "request_order_retirement": True,
            "out_of_order_device_response": True,
            "same_page_miss_coalescing": True,
            "stale_generation_suppression": True,
            "recommended_first_RTL_MSHR_entries": 8,
            "recommended_first_RTL_data_outstanding": 16,
        },
        "remaining_local_gates": [
            "page_walker_TLB_MSHR_RTL_E1",
            "out_of_order_iDMA_response_E1",
            "COW_refcount_epoch_integration_E1",
            "AXI_iDMA_integrated_E3",
        ],
    }
