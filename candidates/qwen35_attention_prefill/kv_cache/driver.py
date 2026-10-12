"""KV owner transport on the exact caller-owned TypedMemory byte map.

No arithmetic service or array is created. Producer inputs require actual
published data/ACK coverage. Exact valid-prefix spans become internally
readable atomically only at the accepted successful KV terminal. External
roots, length and generation remain owned by the separate fullblock fence.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import fields
import hashlib
import struct

from ...qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from ...qwen35_gdn_prefill.typed_dense import TypedMemory
from .owner import (BEAT_BYTES, FULL_MASK, TOKEN_BYTES, KvCacheJob, KvCacheOwner,
                    KvCacheResult, MemoryRequest, MemoryResponse, require, same_coverage, source_identity)
from .fence import KvBlockFence


def field_values(value):
    return tuple((field.name, getattr(value, field.name)) for field in fields(value))


class TypedKvCacheDriver:
    def __init__(self, owner, memory, job, fence):
        require(type(owner) is KvCacheOwner and type(job) is KvCacheJob and
                type(memory) is TypedMemory and type(fence) is KvBlockFence,
                'explicit typed owner/job/shared memory/block fence required')
        job.validate()
        require(fence.memory is memory, 'block fence and owner must share the same physical memory')
        fence.validate_job(job)
        require(owner.ports()['job_ready'] and memory.pending is None,
                'drained unpoisoned owner and memory required')
        inputs = tuple(memory.exact(base, extent, readable=True) for base, extent in job.input_spans)
        require(all(not r.readonly and
                    same_coverage(r.written, frozenset(range(0, r.extent, BEAT_BYTES))) and
                    same_coverage(r.acknowledged, frozenset(range(0, r.extent, BEAT_BYTES))) for r in inputs),
                'actual published upstream producer data/ACK required')
        outputs = tuple(memory.exact(base, extent, readable=False) for base, extent in job.output_spans)
        require(all(same_coverage(r.written, frozenset()) and
                    same_coverage(r.acknowledged, frozenset()) for r in outputs),
                'fresh staging cannot contain prior write/ACK coverage')
        require(all(type(r.storage) is bytearray for r in (*inputs, *outputs)),
                'physical bytearray storage required')
        self.owner, self.memory, self.job, self.fence = owner, memory, job, fence
        self.inputs, self.outputs = inputs, outputs
        self.committed_before = fence.state
        self._owner, self._memory, self._job, self._fence = owner, memory, job, fence
        self._inputs, self._outputs, self._regions = inputs, outputs, memory.regions
        self._job_fields, self._state_fields = field_values(job), field_values(fence.state)
        self._bindings = tuple((r, r.base, r.extent, r.storage, r.readonly) for r in (*inputs, *outputs))
        # Host identity guards are diagnostic snapshots, never owner storage.
        self._source_storage = tuple(bytes(r.storage) for r in inputs)
        self._source_coverage = tuple((frozenset(r.written), frozenset(r.acknowledged)) for r in inputs)
        self._source_hashes = tuple(hashlib.sha256(r.raw()).hexdigest() for r in inputs)
        self._output_hashes = tuple(hashlib.sha256() for _ in outputs)
        self.identity = source_identity()
        self._identity = deepcopy(self.identity)
        self._identity_object = self.identity
        self._integrity_errors = []
        self._owner_terminal_report = None
        self.pending = self.response = self.receipt = None
        self._pending_response = self._accepted = self._physical_pending = None
        self._accepted_fields = self._response_fields = None
        self._last_read = None
        self.aborted = False
        self.counts = Counter()
        fence._begin(self)
        require(owner.tick(job=job)['job_fire'], 'KV owner admission rejected')

    def _integrity(self, condition, detail, *, cancelling=False):
        if not condition:
            if detail not in self._integrity_errors:
                self._integrity_errors.append(detail)
            self.owner.poison = True
            require(cancelling, detail)

    def _check_bindings(self, *, cancelling=False):
        require(self.owner is self._owner and self.memory is self._memory and self.job is self._job and
                self.fence is self._fence and self.owner.job is self._job and
                self.memory.regions is self._regions and self.inputs is self._inputs and
                self.outputs is self._outputs and self.fence.memory is self._memory,
                'physical resources/job/span identity replaced')
        require(field_values(self.job) == self._job_fields and
                field_values(self.committed_before) == self._state_fields,
                'immutable job or committed state changed')
        self.fence._check_active(self, self.committed_before)
        for r, base, extent, storage, readonly in self._bindings:
            require(self.memory.regions.get(base) is r and type(r.base) is int and r.base == base and
                    type(r.extent) is int and r.extent == extent and r.storage is storage and
                    len(r.storage) == extent + 128 and type(r.readonly) is bool and r.readonly == readonly,
                    'physical span geometry/storage identity changed')
            # Input guards are part of the frozen full storage comparison
            # below. Their corruption must not block draining a known beat.
            if any(r is output for output in self._outputs):
                r.check()
        for r, frozen, coverage in zip(self._inputs, self._source_storage, self._source_coverage):
            self._integrity(r.published is True and bytearray.__eq__(r.storage, frozen) and
                            same_coverage(r.written, coverage[0]) and same_coverage(r.acknowledged, coverage[1]),
                            'published source bytes or producer coverage changed', cancelling=cancelling)
        require(not self._integrity_errors or cancelling,
                'latched integrity failure requires abort/reset before further execution')
        offset = 0
        for r in self._outputs:
            written = min(max(self.counts['write_bytes'] - offset, 0), r.extent)
            acknowledged = min(max(self.counts['ack_bytes'] - offset, 0), r.extent)
            require(r.published is False and
                    same_coverage(r.written, frozenset(range(0, written, BEAT_BYTES))) and
                    same_coverage(r.acknowledged, frozenset(range(0, acknowledged, BEAT_BYTES))),
                    'premature output publication or altered write/ACK coverage')
            offset += r.extent
        require(self.pending is self._pending_response and self.memory.pending is self._physical_pending,
                'accepted transport obligation replaced')
        if self._accepted is not None:
            require(self.owner.request is self._accepted and field_values(self._accepted) == self._accepted_fields and
                    field_values(self.pending) == self._response_fields,
                    'accepted request/response changed before drain')
            if self._accepted.write:
                physical = self._physical_pending
                require(physical is not None and len(physical) == 4 and
                        physical[0] == WriteCommand(self._accepted.address, 1, self._accepted.tag) and
                        physical[1] is self.memory._resolve(self._accepted.address) and
                        physical[2] == (self._accepted.address - physical[1].base,) and physical[3] == 1,
                        'accepted physical write descriptor changed')
            else:
                require(self._physical_pending is None, 'read acquired a physical write obligation')

    def _check_request(self, request):
        sequence = self.counts['memory_requests']
        require(type(request) is MemoryRequest and type(request.tag) is int and
                request.tag == (self.job.tag << 32) | sequence and request.nbytes == BEAT_BYTES,
                'full beat request tag/byte identity')
        plane_bytes = self.job.valid_tokens * TOKEN_BYTES
        plane, offset = divmod((sequence // 2) * BEAT_BYTES, plane_bytes)
        require(plane in (0, 1), 'request beyond exact output span')
        write = bool(sequence % 2)
        old_bytes = self.job.previous_tokens * TOKEN_BYTES
        if write:
            address = self.job.output_spans[plane][0] + offset
        elif offset < old_bytes:
            address = (self.job.previous_k, self.job.previous_v)[plane] + offset
        else:
            address = (self.job.new_k, self.job.new_v)[plane] + offset - old_bytes
        require(type(request.address) is int and request.address == address and request.write is write,
                'request address/direction escaped exact copy/append order')
        region = self.memory._resolve(address)
        if write:
            require(region is self._outputs[plane] and type(request.data) is bytes and
                    len(request.data) == BEAT_BYTES and request.data == self._last_read and
                    request.mask == FULL_MASK, 'write differs from accepted read beat')
        else:
            require(any(region is r for r in self._inputs) and request.mask == 0,
                    'read escaped typed producer inputs')

    def _validate_held_terminal(self, result):
        # Check before consuming the owner's held terminal: a rejected host
        # integrity check must still permit explicit cancellation and retry.
        require(self.pending is None and self.memory.pending is None and self._accepted is None,
                'KV terminal before transport drained')
        require(type(result) is KvCacheResult and type(result.tag) is int and result.tag == self.job.tag and
                type(result.write_bytes) is int and result.write_bytes == self.counts['ack_bytes'] and
                type(result.current_generation) is int and result.current_generation == self.job.current_generation,
                'held terminal tag/ACK byte/generation identity')
        if self._integrity_errors:
            require(self.aborted and self.owner.poison and result.status is not None,
                    'integrity failure requires a drained failed terminal')
        else:
            self._integrity(tuple(hashlib.sha256(r.raw()).hexdigest() for r in self._inputs) == self._source_hashes,
                            'terminal source byte identity changed')
        if result.status is None:
            require(not self.aborted and not self.owner.poison and result.valid_tokens == self.job.valid_tokens and
                    result.write_bytes == self.counts['write_bytes'] == self.job.write_bytes,
                    'success before full accepted writes/ACKs')
            self._integrity(tuple(hashlib.sha256(r.raw()).hexdigest() for r in self._outputs) ==
                            tuple(h.hexdigest() for h in self._output_hashes),
                            'terminal outputs differ from actual accepted write data')
            self._integrity(self.identity is self._identity_object and self.identity == self._identity and
                            source_identity() == self._identity,
                            'new KV source identity changed during execution')

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             abort=False, reset=False, read_error=False, ack_error=False):
        require(self.response is None, 'KV invocation already retired')
        require(all(type(v) is bool for v in (memory_ready, memory_response_ready, response_ready,
                                             abort, reset, read_error, ack_error)),
                'boolean transport controls required')
        self._check_bindings(cancelling=abort or reset or self.aborted)
        ports = self.owner.ports()
        require(not reset or ports['state'] != 'finish', 'reset cannot erase a held completion')
        if ports['memory'] is not None:
            self._check_request(ports['memory'])
        accepted = self._accepted
        pending = self.pending if memory_response_ready else None
        if pending is not None:
            require(accepted is not None and pending.tag == accepted.tag and pending.nbytes == BEAT_BYTES,
                    'response does not match accepted request')
            pending = MemoryResponse(pending.tag, pending.data,
                                      ack_error if accepted.write else read_error, pending.nbytes)
        abort_edge = abort and not self.aborted
        self.aborted |= abort_edge or reset
        terminal_ready = response_ready and not (abort_edge or reset)
        if ports['response'] is not None and terminal_ready:
            self._validate_held_terminal(ports['response'])
        event = self.owner.tick(memory_ready=memory_ready, memory_response=pending,
                                response_ready=terminal_ready,
                                abort=abort_edge, reset=reset)
        self.counts['ticks'] += 1
        if event['memory_response_fire']:
            require(pending is not None and accepted is not None, 'response without physical request')
            if accepted.write:
                self.memory.acknowledge(WriteAck(pending.tag, pending.error, pending.nbytes))
                self.counts['ack_bytes'] += 0 if pending.error else BEAT_BYTES
            elif not pending.error:
                self._last_read = pending.data
            self.pending = self._pending_response = None
            self._accepted = self._physical_pending = None
            self._accepted_fields = self._response_fields = None
            self.counts['memory_responses'] += 1
        if event['memory_fire']:
            require(self.pending is None and self.memory.pending is None, 'multiple outstanding KV requests')
            request = event['memory']
            self._check_request(request)
            if request.write:
                self.memory.begin_write(WriteCommand(request.address, 1, request.tag))
                self.memory.write_data(struct.unpack('<32H', request.data), True, mask=request.mask)
                self.pending = MemoryResponse(request.tag)
                self._output_hashes[int(request.address >= self.job.staging_v)].update(request.data)
                self.counts['write_bytes'] += BEAT_BYTES
                self._last_read = None
            else:
                self.pending = MemoryResponse(request.tag, self.memory.read64(request.address))
                self.counts['read_bytes'] += BEAT_BYTES
            self._accepted, self._physical_pending = request, self.memory.pending
            self._pending_response = self.pending
            self._accepted_fields, self._response_fields = field_values(request), field_values(self.pending)
            self.counts['memory_requests'] += 1
        if event['response_fire']:
            result = event['response']
            require(result is ports['response'], 'owner changed the validated held terminal')
            if result.status is None:
                self.memory.publish_many(tuple(r.base for r in self._outputs),
                                         (result.tag, result.status, result.write_bytes))
            self.response = result
            self._owner_terminal_report = deepcopy(self.owner.report())
            self.receipt = self.fence._accept_kv(self)
        return event

    def report(self):
        return dict(owner=(deepcopy(self._owner_terminal_report) if self._owner_terminal_report is not None
                           else self.owner.report()), complete=self.response is not None,
                    status=None if self.response is None else self.response.status,
                    counts=dict(self.counts), input_sha256=list(self._source_hashes),
                    output_sha256=[hashlib.sha256(r.raw()).hexdigest() for r in self._outputs],
                    output_published=[r.published for r in self._outputs],
                    receipt_available=self.receipt is not None,
                    generation_at_admission=self.committed_before.generation,
                    external_commit_performed=False, identity=deepcopy(self._identity),
                    integrity_errors=list(self._integrity_errors),
                    hardware_cycles=None, rtl_executed=False, native_acceptance=False,
                    fullblock_executed=False)
