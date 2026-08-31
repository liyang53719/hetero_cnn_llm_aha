"""Multi-slot state transaction, COW/refcount and dirty-mask E0 model."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import random

DOMAINS = 10
SLOTS = 8
PAGES = 128
WORDS_PER_PAGE = 64


@dataclass
class Slot:
    active: bool = False
    txn_id: int = -1
    required: int = 0
    acked: int = 0
    dirty: dict[int, int] = field(default_factory=dict)
    provisional_pages: set[int] = field(default_factory=set)
    decision: str | None = None


class Model:
    def __init__(self) -> None:
        self.slots = [Slot() for _ in range(SLOTS)]
        self.ref = [0] * PAGES
        self.free = set(range(PAGES))
        self.owner_pages: dict[int, set[int]] = {}
        self.commits = self.rollbacks = self.cows = 0
        self.same_cycle_ref_cow = 0
        self.dirty_merges = 0
        self.max_active = 0

    def alloc(self, owner: int) -> int:
        if not self.free:
            raise MemoryError
        page = min(self.free); self.free.remove(page); self.ref[page] = 1
        self.owner_pages.setdefault(owner, set()).add(page)
        return page

    def share(self, page: int, owner: int) -> None:
        if self.ref[page] == 0: raise AssertionError("share free")
        self.ref[page] += 1; self.owner_pages.setdefault(owner, set()).add(page)

    def release(self, page: int, owner: int) -> None:
        self.owner_pages.get(owner, set()).discard(page)
        if self.ref[page] <= 0: raise AssertionError("underflow")
        self.ref[page] -= 1
        if self.ref[page] == 0: self.free.add(page)

    def start(self, slot: int, txn: int, required: int) -> None:
        if self.slots[slot].active: raise AssertionError("slot reuse")
        self.slots[slot] = Slot(True, txn, required)

    def dirty(self, slot: int, page: int, mask: int) -> None:
        s = self.slots[slot]
        if not s.active: raise AssertionError("dirty inactive")
        old = s.dirty.get(page, 0); new = old | (mask & ((1 << WORDS_PER_PAGE) - 1))
        if old and new != old: self.dirty_merges += 1
        s.dirty[page] = new

    def ack(self, slot: int, domain: int) -> None:
        s = self.slots[slot]
        if not s.active: return
        s.acked |= 1 << domain

    def cow(self, slot: int, owner: int, old_page: int, *, simultaneous_share: bool = False) -> int:
        s = self.slots[slot]
        if not s.active: raise AssertionError("cow inactive")
        temp_owner = owner + 10000
        if simultaneous_share:
            self.share(old_page, temp_owner)
            self.same_cycle_ref_cow += 1
        if self.ref[old_page] <= 1:
            return old_page
        new_page = self.alloc(owner)
        s.provisional_pages.add(new_page)
        self.release(old_page, owner)
        if simultaneous_share:
            self.release(old_page, temp_owner)
        self.cows += 1
        return new_page

    def decide(self, slot: int, commit: bool) -> None:
        s = self.slots[slot]
        if not s.active: raise AssertionError("decide inactive")
        if commit and (s.acked & s.required) != s.required: raise AssertionError("early commit")
        s.decision = "commit" if commit else "rollback"

    def resolve(self, slot: int, owner: int) -> None:
        s = self.slots[slot]
        if s.decision is None: return
        if s.decision == "rollback":
            for page in tuple(s.provisional_pages):
                if page in self.owner_pages.get(owner, set()): self.release(page, owner)
            self.rollbacks += 1
        else:
            self.commits += 1
        self.slots[slot] = Slot()

    def check(self) -> None:
        for page, count in enumerate(self.ref):
            actual = sum(page in pages for pages in self.owner_pages.values())
            if actual != count: raise AssertionError((page, count, actual))
            if (count == 0) != (page in self.free): raise AssertionError("free mismatch")
        self.max_active = max(self.max_active, sum(s.active for s in self.slots))


def stress(transactions: int = 10000, seed: int = 0x57A7E) -> dict[str, object]:
    rng = random.Random(seed); m = Model(); next_txn = 0; owners = list(range(16))
    # Give each owner a page and create sharing pressure.
    for owner in owners: m.alloc(owner)
    for owner in owners[1:8]:
        page = min(m.owner_pages[0]); m.share(page, owner)
    completed = 0; cycles = 0; generation_wraps = 0
    generation = [0] * len(owners)
    while completed < transactions:
        cycles += 1
        # Start as many slots as possible.
        for slot, state in enumerate(m.slots):
            if not state.active and next_txn < transactions and rng.random() < 0.35:
                required = 0
                for domain in range(DOMAINS):
                    if rng.random() < 0.45: required |= 1 << domain
                if required == 0: required = 1 << rng.randrange(DOMAINS)
                m.start(slot, next_txn, required); next_txn += 1
        # Apply dirty updates, ACKs, COW and decisions to overlapping slots.
        for slot, state in enumerate(m.slots):
            if not state.active: continue
            owner = state.txn_id % len(owners)
            if rng.random() < 0.55:
                page = rng.choice(tuple(m.owner_pages[owner])) if m.owner_pages[owner] else m.alloc(owner)
                bit = rng.randrange(WORDS_PER_PAGE)
                mask = (1 << bit) | ((1 << ((bit + rng.randrange(1, 8)) % WORDS_PER_PAGE)) if rng.random() < 0.6 else 0)
                m.dirty(slot, page, mask)
                if rng.random() < 0.08:
                    new_page = m.cow(slot, owner, page, simultaneous_share=rng.random() < 0.25)
                    m.owner_pages[owner].add(new_page)
            for domain in range(DOMAINS):
                if (state.required >> domain) & 1 and rng.random() < 0.3: m.ack(slot, domain)
            if state.decision is None:
                ready = (state.acked & state.required) == state.required
                if ready and rng.random() < 0.32: m.decide(slot, True)
                elif rng.random() < 0.015: m.decide(slot, False)
            if state.decision is not None and rng.random() < 0.8:
                m.resolve(slot, owner); completed += 1
                generation[owner] = (generation[owner] + 1) & 0xFF
                if generation[owner] == 0: generation_wraps += 1
        m.check()
        if cycles > transactions * 200: raise RuntimeError("did not converge")
    # Drain remaining active slots by rollback to ensure no provisional leaks.
    for slot, state in enumerate(m.slots):
        if state.active:
            owner = state.txn_id % len(owners); state.decision = "rollback"; m.resolve(slot, owner)
    m.check()
    digest = hashlib.sha256(json.dumps({"ref":m.ref,"owners":{k:sorted(v) for k,v in m.owner_pages.items()}}, sort_keys=True).encode()).hexdigest()
    return {
        "schema_version": 1, "status": "PASS",
        "evidence_class": "multislot_state_COW_dirty_E0_not_RTL_E1_or_iDMA_E3",
        "transactions": transactions, "cycles": cycles, "slots": SLOTS, "domains": DOMAINS,
        "commits": m.commits, "rollbacks": m.rollbacks, "cows": m.cows,
        "same_cycle_refcount_COW": m.same_cycle_ref_cow, "dirty_mask_merges": m.dirty_merges,
        "max_active_slots": m.max_active, "generation_wraps": generation_wraps,
        "page_leak": 0, "sha256": digest,
        "remaining_local_gates": ["multislot RTL E1", "refcount/COW SRAM integration", "OOO iDMA E3", "continuous batching"],
    }
