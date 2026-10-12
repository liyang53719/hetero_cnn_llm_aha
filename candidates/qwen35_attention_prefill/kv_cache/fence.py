"""Separate internal KV readability from external fullblock cache commit.

The future fullblock coordinator must construct FullBlockTerminal only from
its actual accepted final residual terminal. Unit tests use an explicitly
synthetic downstream stand-in; this module does not implement that block.
The copy/append owner cannot call commit_after_fullblock or advance an epoch.
"""
from dataclasses import dataclass, fields
import hashlib

from ...qwen35_gdn_prefill.typed_dense import TypedMemory
from .owner import CAPACITY, TOKEN_BYTES, KvCacheJob, disjoint, require, same_coverage, uint


def _fields(value):
    return tuple((field.name, getattr(value, field.name)) for field in fields(value))


@dataclass(frozen=True)
class CommittedKvState:
    k_root: int = 0
    v_root: int = 0
    valid_tokens: int = 0
    generation: int = 0
    capacity: int = CAPACITY
    dtype: str = 'bf16'


@dataclass(frozen=True)
class KvStagingReceipt:
    tag: int
    committed_before: CommittedKvState
    k_root: int
    v_root: int
    valid_tokens: int
    write_bytes: int
    output_sha256: tuple[str, str]

    @property
    def output_spans(self):
        return ((self.k_root, self.valid_tokens * TOKEN_BYTES),
                (self.v_root, self.valid_tokens * TOKEN_BYTES))


@dataclass(frozen=True)
class FullBlockTerminal:
    """Accepted final-residual evidence supplied by the fullblock coordinator.

    tag identifies the enclosing KV transaction; final_owner_tag identifies
    the final residual owner. A successful record must bind the exact staged
    receipt and a fully published final residual output in the same memory.
    This typed integration boundary is not an independently authenticated
    proof of a future owner's implementation or of the complete fullblock.
    The caller must bind final_owner_tag, status, byte extent and output root
    to that actual owner's accepted terminal and publication record; this
    module cannot authenticate a producer tag from TypedMemory alone. Future
    fullblock integration must reject a forged in-range final_owner_tag.
    """
    tag: int
    expected_generation: int
    kv_receipt: KvStagingReceipt
    status: str | None
    accepted: bool
    final_owner_tag: int
    final_output_root: int
    final_output_bytes: int
    final_write_bytes: int


class KvBlockFence:
    """Caller-owned committed state, with one outstanding block transaction."""
    def __init__(self, memory):
        require(type(memory) is TypedMemory, 'fence requires the same caller TypedMemory')
        self._memory = memory
        self._state = CommittedKvState()
        self._state_fields = _fields(self._state)
        self._active = self._receipt = None
        self._receipt_fields = None
        self._staged_regions = self._staged_bindings = None
        self._used_reservations = []
        self._committed_regions = self._committed_bindings = self._committed_digests = ()
        self._published_before = ()

    @property
    def memory(self):
        return self._memory

    @property
    def state(self):
        return self._state

    @property
    def pending_receipt(self):
        return self._receipt

    def _validate_committed(self):
        spans = ((self._state.k_root, self._state.valid_tokens * TOKEN_BYTES),
                 (self._state.v_root, self._state.valid_tokens * TOKEN_BYTES)) if self._state.valid_tokens else ()
        self._validate_regions(self._committed_regions, self._committed_bindings, spans,
                               self._committed_digests, 'committed prefix changed')

    def _validate_regions(self, regions, bindings, spans, digests, detail):
        require(len(regions) == len(bindings) == len(spans) == len(digests), detail)
        for region, binding, expected, digest in zip(regions, bindings, spans, digests):
            base, extent, storage = binding
            require(self._memory.exact(*expected, readable=True) is region and
                    region.base == base and region.extent == extent and region.storage is storage and
                    not region.readonly and
                    same_coverage(region.written, frozenset(range(0, region.extent, 64))) and
                    same_coverage(region.acknowledged, frozenset(range(0, region.extent, 64))) and
                    hashlib.sha256(region.raw()).hexdigest() == digest,
                    detail)

    def validate_job(self, job):
        require(type(job) is KvCacheJob, 'typed KV job required by fence')
        job.validate()
        require(_fields(self._state) == self._state_fields, 'committed state descriptor changed')
        self._validate_committed()
        require(self._active is None and self._receipt is None,
                'previous fullblock transaction has not retired')
        require(all(disjoint((job.staging_k, 2 * job.capacity * TOKEN_BYTES), old)
                    for old in self._used_reservations), 'retry must use a fresh staging reservation')
        state = self._state
        require((job.previous_k, job.previous_v, job.previous_tokens, job.current_generation,
                 job.expected_generation, job.capacity, job.dtype) ==
                (state.k_root, state.v_root, state.valid_tokens, state.generation,
                 state.generation, state.capacity, state.dtype),
                'job does not match committed prefix/generation')

    def _begin(self, driver):
        self.validate_job(driver.job)
        require(driver.memory is self._memory, 'fence memory identity')
        self._active = driver
        self._used_reservations.append((driver.job.staging_k, 2 * driver.job.capacity * TOKEN_BYTES))
        self._published_before = tuple((r.base, r.extent) for r in self._memory.regions.values() if r.published)

    def _check_active(self, driver, state):
        require(self._active is driver and self._state is state and self._receipt is None,
                'active block/fence state changed before KV terminal')
        require(_fields(self._state) == self._state_fields, 'committed state descriptor changed')

    def _accept_kv(self, driver):
        self._check_active(driver, driver.committed_before)
        require(driver.response is not None and driver.owner.counts['owner_results'] == 1,
                'staging receipt requires a real accepted owner terminal')
        if driver.response.status is not None:
            self._active = None
            return None
        require(driver.response.write_bytes == driver.job.write_bytes and
                driver.response.current_generation == self._state.generation,
                'staging receipt aggregate bytes/generation')
        outputs = tuple(self._memory.exact(base, extent, readable=True)
                        for base, extent in driver.job.output_spans)
        require(all(not region.readonly for region in outputs), 'actual producer outputs required')
        receipt = KvStagingReceipt(driver.job.tag, self._state, driver.job.staging_k,
                                   driver.job.staging_v, driver.job.valid_tokens,
                                   driver.response.write_bytes,
                                   tuple(hashlib.sha256(r.raw()).hexdigest() for r in outputs))
        self._receipt, self._staged_regions = receipt, outputs
        self._receipt_fields = _fields(receipt)
        self._staged_bindings = tuple((r.base, r.extent, r.storage) for r in outputs)
        return receipt

    def _validate_terminal(self, receipt, terminal):
        require(_fields(self._state) == self._state_fields, 'committed state descriptor changed')
        self._validate_committed()
        require(type(receipt) is KvStagingReceipt and receipt is self._receipt and
                self._active is not None and receipt.committed_before is self._state,
                'stale, duplicate, or foreign staging receipt')
        require(_fields(receipt) == self._receipt_fields, 'immutable staging receipt changed')
        require(type(terminal) is FullBlockTerminal and terminal.kv_receipt is receipt and
                type(terminal.tag) is int and terminal.tag == receipt.tag and
                type(terminal.expected_generation) is int and
                terminal.expected_generation == self._state.generation and
                type(terminal.accepted) is bool and terminal.accepted and
                uint(terminal.final_owner_tag, 32),
                'exact accepted fullblock terminal/tag/generation required')

    def commit_after_fullblock(self, receipt, terminal):
        """Promote only after the actual downstream final terminal was accepted."""
        self._validate_terminal(receipt, terminal)
        require(terminal.status is None and type(terminal.final_output_bytes) is int and
                terminal.final_output_bytes > 0 and
                type(terminal.final_write_bytes) is int and
                terminal.final_write_bytes == terminal.final_output_bytes,
                'successful complete final residual terminal required')
        require(type(terminal.final_output_root) is int and
                terminal.final_output_root not in (receipt.k_root, receipt.v_root),
                'distinct final residual output required')
        require(all(disjoint((terminal.final_output_root, terminal.final_output_bytes), old)
                    for old in self._published_before),
                'final residual output was already published before this block')
        final_output = self._memory.exact(terminal.final_output_root, terminal.final_output_bytes,
                                          readable=True)
        require(not final_output.readonly and
                same_coverage(final_output.written, frozenset(range(0, final_output.extent, 64))) and
                same_coverage(final_output.acknowledged, frozenset(range(0, final_output.extent, 64))),
                'final residual producer data/ACK coverage')
        require(self._memory.pending is None, 'fullblock commit with in-flight write')
        self._validate_regions(self._staged_regions, self._staged_bindings, receipt.output_spans,
                               receipt.output_sha256, 'staging changed or incomplete at external commit')
        require(receipt.valid_tokens <= CAPACITY and receipt.write_bytes ==
                2 * receipt.valid_tokens * TOKEN_BYTES and self._state.generation < (1 << 64) - 1,
                'commit length/byte/generation overflow')
        self._state = CommittedKvState(receipt.k_root, receipt.v_root, receipt.valid_tokens,
                                        self._state.generation + 1)
        self._state_fields = _fields(self._state)
        self._committed_regions = self._staged_regions
        self._committed_bindings = self._staged_bindings
        self._committed_digests = receipt.output_sha256
        self._active = self._receipt = self._staged_regions = self._staged_bindings = None
        self._receipt_fields = None
        return self._state

    def discard_after_fullblock(self, receipt, terminal):
        """A drained failed block leaves its readable staging uncommitted."""
        self._validate_terminal(receipt, terminal)
        require(type(terminal.status) is str and bool(terminal.status),
                'failed accepted fullblock terminal required to discard')
        require(self._memory.pending is None, 'failed fullblock terminal before write drain')
        self._active = self._receipt = self._staged_regions = self._staged_bindings = None
        self._receipt_fields = None
        return self._state
