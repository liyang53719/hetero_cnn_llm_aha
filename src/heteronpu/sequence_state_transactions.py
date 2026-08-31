"""Cross-engine speculative state transaction reference.

The model covers state required by KV, Gated DeltaNet, QSA, PLE,
hyper-residual streams and sampling. It provides page sharing, copy-on-write,
per-step speculative writes, partial-prefix commit, epoch/generation checks and
refcount/leak invariants. This is E0; production RTL still needs atomic state
metadata, a page walker and iDMA/AXI integration.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import random
from typing import Iterable


class StateDomain(str, Enum):
    KV = "kv"
    GDN_MATRIX = "gdn_matrix"
    GDN_CONV = "gdn_conv"
    QSA_INDEX = "qsa_index"
    QSA_KV = "qsa_kv"
    PLE_HISTORY = "ple_history"
    PLE_CONV = "ple_conv"
    HYPER_STREAM = "hyper_stream"
    SAMPLER = "sampler"
    RUNTIME = "runtime"


@dataclass(frozen=True, order=True)
class PageKey:
    domain: StateDomain
    layer: int
    head: int
    logical_page: int


@dataclass(frozen=True, order=True)
class StateAddress:
    key: PageKey
    word: int

    def __post_init__(self) -> None:
        if min(self.key.layer, self.key.head, self.key.logical_page, self.word) < 0:
            raise ValueError("negative state address")


@dataclass
class PhysicalPage:
    page_id: int
    values: dict[int, int] = field(default_factory=dict)
    refcount: int = 1


@dataclass(frozen=True)
class StateResponse:
    sequence_id: int
    generation: int
    address: StateAddress
    value: int


@dataclass
class Transaction:
    transaction_id: int
    sequence_id: int
    base_generation: int
    max_steps: int
    writes: list[dict[StateAddress, int]]
    closed: bool = False

    @classmethod
    def create(
        cls,
        transaction_id: int,
        sequence_id: int,
        generation: int,
        max_steps: int,
    ) -> "Transaction":
        if max_steps <= 0:
            raise ValueError("max_steps")
        return cls(
            transaction_id,
            sequence_id,
            generation,
            max_steps,
            [dict() for _ in range(max_steps)],
        )

    def write(self, step: int, address: StateAddress, value: int) -> None:
        if self.closed:
            raise RuntimeError("transaction closed")
        if not 0 <= step < self.max_steps:
            raise IndexError("transaction step")
        self.writes[step][address] = int(value) & 0xFFFFFFFF

    @property
    def dirty_pages(self) -> frozenset[PageKey]:
        return frozenset(address.key for step in self.writes for address in step)

    @property
    def dirty_words(self) -> int:
        return sum(len(step) for step in self.writes)


@dataclass
class SequenceMeta:
    generation: int = 1
    epoch: int = 0
    mappings: dict[PageKey, int] = field(default_factory=dict)


class SequenceStateStore:
    def __init__(self, words_per_page: int = 1024) -> None:
        if words_per_page <= 0:
            raise ValueError("words_per_page")
        self.words_per_page = int(words_per_page)
        self.sequences: dict[int, SequenceMeta] = {}
        self.pages: dict[int, PhysicalPage] = {}
        self.free_pages: list[int] = []
        self.next_page_id = 1
        self.next_transaction_id = 1
        self.counters = defaultdict(int)

    def create_sequence(self, sequence_id: int, *, generation: int = 1) -> None:
        if sequence_id in self.sequences:
            raise ValueError("sequence exists")
        self.sequences[int(sequence_id)] = SequenceMeta(int(generation), 0, {})

    def _meta(self, sequence_id: int) -> SequenceMeta:
        try:
            return self.sequences[int(sequence_id)]
        except KeyError as error:
            raise KeyError(f"unknown sequence {sequence_id}") from error

    def _allocate_page(self, values: dict[int, int] | None = None) -> int:
        if self.free_pages:
            page_id = self.free_pages.pop()
            self.counters["page_reuse"] += 1
        else:
            page_id = self.next_page_id
            self.next_page_id += 1
        self.pages[page_id] = PhysicalPage(page_id, dict(values or {}), 1)
        self.counters["page_alloc"] += 1
        return page_id

    def _release_page(self, page_id: int) -> None:
        page = self.pages[page_id]
        page.refcount -= 1
        if page.refcount < 0:
            raise AssertionError("negative refcount")
        if page.refcount == 0:
            del self.pages[page_id]
            self.free_pages.append(page_id)
            self.counters["page_free"] += 1

    def _resolve_page(
        self,
        sequence_id: int,
        key: PageKey,
        *,
        create: bool,
    ) -> PhysicalPage | None:
        metadata = self._meta(sequence_id)
        page_id = metadata.mappings.get(key)
        if page_id is None:
            if not create:
                return None
            page_id = self._allocate_page()
            metadata.mappings[key] = page_id
        return self.pages[page_id]

    def read_committed(
        self,
        sequence_id: int,
        address: StateAddress,
        default: int = 0,
    ) -> int:
        if address.word >= self.words_per_page:
            raise IndexError("word offset")
        page = self._resolve_page(sequence_id, address.key, create=False)
        return int(default) if page is None else int(page.values.get(address.word, default))

    def write_committed(
        self,
        sequence_id: int,
        address: StateAddress,
        value: int,
    ) -> None:
        if address.word >= self.words_per_page:
            raise IndexError("word offset")
        metadata = self._meta(sequence_id)
        page = self._resolve_page(sequence_id, address.key, create=True)
        assert page is not None
        if page.refcount > 1:
            old_page_id = page.page_id
            page.refcount -= 1
            new_page_id = self._allocate_page(page.values)
            metadata.mappings[address.key] = new_page_id
            page = self.pages[new_page_id]
            self.counters["copy_on_write"] += 1
            self.counters["copy_on_write_words"] += len(self.pages[old_page_id].values)
        page.values[address.word] = int(value) & 0xFFFFFFFF
        self.counters["committed_writes"] += 1

    def share_prefix(
        self,
        parent_sequence: int,
        child_sequence: int,
        keys: Iterable[PageKey],
    ) -> None:
        parent = self._meta(parent_sequence)
        if child_sequence in self.sequences:
            raise ValueError("child exists")
        child = SequenceMeta(parent.generation, parent.epoch, {})
        self.sequences[int(child_sequence)] = child
        for key in keys:
            if key not in parent.mappings:
                continue
            page_id = parent.mappings[key]
            child.mappings[key] = page_id
            self.pages[page_id].refcount += 1
            self.counters["shared_pages"] += 1

    def begin(self, sequence_id: int, *, max_steps: int) -> Transaction:
        metadata = self._meta(sequence_id)
        transaction = Transaction.create(
            self.next_transaction_id,
            sequence_id,
            metadata.generation,
            max_steps,
        )
        self.next_transaction_id += 1
        self.counters["transactions_started"] += 1
        return transaction

    def read_speculative(
        self,
        transaction: Transaction,
        step: int,
        address: StateAddress,
        default: int = 0,
    ) -> int:
        if transaction.closed:
            raise RuntimeError("transaction closed")
        if not 0 <= step < transaction.max_steps:
            raise IndexError("step")
        for prior in range(step, -1, -1):
            if address in transaction.writes[prior]:
                return transaction.writes[prior][address]
        return self.read_committed(transaction.sequence_id, address, default)

    def commit(self, transaction: Transaction, accepted_steps: int) -> dict[str, int]:
        if transaction.closed:
            raise RuntimeError("transaction closed")
        if not 0 <= accepted_steps <= transaction.max_steps:
            raise ValueError("accepted_steps")
        metadata = self._meta(transaction.sequence_id)
        if metadata.generation != transaction.base_generation:
            transaction.closed = True
            self.counters["stale_transaction_rejected"] += 1
            raise RuntimeError("stale transaction generation")
        applied_words = 0
        applied_pages: set[PageKey] = set()
        for step in range(accepted_steps):
            for address, value in transaction.writes[step].items():
                self.write_committed(transaction.sequence_id, address, value)
                applied_words += 1
                applied_pages.add(address.key)
        rejected_words = sum(len(step) for step in transaction.writes[accepted_steps:])
        metadata.generation += 1
        metadata.epoch += 1
        transaction.closed = True
        self.counters["transactions_committed"] += 1
        self.counters["accepted_speculative_steps"] += accepted_steps
        self.counters["rejected_speculative_words"] += rejected_words
        return {
            "accepted_steps": accepted_steps,
            "applied_words": applied_words,
            "applied_pages": len(applied_pages),
            "rejected_words": rejected_words,
            "new_generation": metadata.generation,
            "new_epoch": metadata.epoch,
        }

    def abort(self, transaction: Transaction) -> None:
        if transaction.closed:
            raise RuntimeError("transaction closed")
        transaction.closed = True
        self.counters["transactions_aborted"] += 1
        self.counters["rejected_speculative_words"] += transaction.dirty_words

    def accept_response(self, response: StateResponse) -> bool:
        accepted = response.generation == self._meta(response.sequence_id).generation
        self.counters[
            "responses_accepted" if accepted else "stale_responses_suppressed"
        ] += 1
        return accepted

    def delete_sequence(self, sequence_id: int) -> None:
        metadata = self._meta(sequence_id)
        for page_id in tuple(metadata.mappings.values()):
            self._release_page(page_id)
        del self.sequences[sequence_id]
        self.counters["sequences_deleted"] += 1

    def logical_snapshot(
        self,
        sequence_id: int,
    ) -> tuple[tuple[PageKey, tuple[tuple[int, int], ...]], ...]:
        metadata = self._meta(sequence_id)
        return tuple(
            (key, tuple(sorted(self.pages[page_id].values.items())))
            for key, page_id in sorted(metadata.mappings.items())
        )

    def validate(self) -> None:
        expected = defaultdict(int)
        for metadata in self.sequences.values():
            for page_id in metadata.mappings.values():
                if page_id not in self.pages:
                    raise AssertionError("dangling mapping")
                expected[page_id] += 1
        if set(expected) != set(self.pages):
            raise AssertionError("unreachable physical page")
        for page_id, page in self.pages.items():
            if page.refcount != expected[page_id] or page.refcount <= 0:
                raise AssertionError((page_id, page.refcount, expected[page_id]))
        if set(self.free_pages) & set(self.pages):
            raise AssertionError("free page still live")

    def snapshot_hash(self, sequence_id: int) -> str:
        digest = hashlib.sha256()
        metadata = self._meta(sequence_id)
        digest.update(metadata.generation.to_bytes(4, "little"))
        digest.update(metadata.epoch.to_bytes(4, "little"))
        for key, values in self.logical_snapshot(sequence_id):
            digest.update(key.domain.value.encode() + b"\x00")
            digest.update(key.layer.to_bytes(2, "little"))
            digest.update(key.head.to_bytes(2, "little"))
            digest.update(key.logical_page.to_bytes(4, "little"))
            for word, value in values:
                digest.update(word.to_bytes(2, "little"))
                digest.update(value.to_bytes(4, "little"))
        return digest.hexdigest()


def _addresses() -> tuple[StateAddress, ...]:
    return tuple(
        StateAddress(PageKey(domain, layer % 4, head % 8, page % 5), word)
        for domain in StateDomain
        for layer in range(2)
        for head in range(2)
        for page in range(2)
        for word in range(4)
    )


def transaction_stress_report(
    transactions: int = 1000,
    *,
    seed: int = 0x7A7E,
) -> dict[str, object]:
    rng = random.Random(seed)
    store = SequenceStateStore(words_per_page=64)
    baseline = SequenceStateStore(words_per_page=64)
    store.create_sequence(1)
    baseline.create_sequence(1)
    addresses = _addresses()
    for index, address in enumerate(addresses[:96]):
        value = (index * 0x10203 + 7) & 0xFFFFFFFF
        store.write_committed(1, address, value)
        baseline.write_committed(1, address, value)
    store.share_prefix(1, 2, list(store._meta(1).mappings))
    parent_hash = store.snapshot_hash(1)
    total_steps = 0
    total_accepted = 0
    total_writes = 0
    for transaction_index in range(transactions):
        max_steps = rng.randint(1, 8)
        accepted_steps = rng.randint(0, max_steps)
        transaction = store.begin(2, max_steps=max_steps)
        baseline_transaction = baseline.begin(1, max_steps=max_steps)
        for step in range(max_steps):
            for _ in range(rng.randint(1, 8)):
                address = rng.choice(addresses)
                value = rng.getrandbits(32)
                transaction.write(step, address, value)
                baseline_transaction.write(step, address, value)
                assert store.read_speculative(transaction, step, address) == value
                total_writes += 1
        store.commit(transaction, accepted_steps)
        baseline.commit(baseline_transaction, accepted_steps)
        if store.logical_snapshot(2) != baseline.logical_snapshot(1):
            raise AssertionError(f"accepted-prefix mismatch at {transaction_index}")
        store.validate()
        baseline.validate()
        total_steps += max_steps
        total_accepted += accepted_steps
    if store.snapshot_hash(1) != parent_hash:
        raise AssertionError("shared parent modified")
    child_hash = store.snapshot_hash(2)
    if child_hash != baseline.snapshot_hash(1):
        raise AssertionError("baseline hash mismatch")
    generation = store._meta(2).generation
    stale = StateResponse(2, generation - 1, addresses[0], 123)
    fresh = StateResponse(2, generation, addresses[0], 123)
    if store.accept_response(stale) or not store.accept_response(fresh):
        raise AssertionError("generation response policy")
    store.delete_sequence(2)
    store.delete_sequence(1)
    baseline.delete_sequence(1)
    store.validate()
    baseline.validate()
    return {
        "schema_version": 1,
        "status": "PASS",
        "evidence_class": "cross_engine_state_transaction_E0_not_RTL_E1_or_iDMA_E3",
        "transactions": transactions,
        "speculative_steps": total_steps,
        "accepted_steps": total_accepted,
        "writes_generated": total_writes,
        "final_logical_sha256": child_hash,
        "counters": dict(sorted(store.counters.items())),
        "frozen_contract": {
            "state_domains": [domain.value for domain in StateDomain],
            "partial_prefix_commit": True,
            "page_copy_on_write": True,
            "refcount_validation": True,
            "epoch_generation": True,
            "stale_response_suppression": True,
            "atomic_commit_barrier_required_in_RTL": True,
            "recommended_dirty_granularity": "page_plus_word_mask",
        },
        "remaining_local_gates": [
            "state_epoch_dirty_bitmap_RTL_E1",
            "atomic_refcount_COW_RTL_E1",
            "cross_engine_commit_barrier_E1",
            "out_of_order_iDMA_rollback_E3",
        ],
    }
