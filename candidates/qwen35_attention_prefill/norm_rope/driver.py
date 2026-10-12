"""Actual Norm256/RoPE requests on the caller's shared physical byte map.

The adapter owns no arithmetic resource and accepts no intermediate oracle
array. Full 64-byte data and ACKs remain private staging until the consumer
accepts the held owner terminal. Q norm and gate publish as one transaction.
"""
from collections import Counter
from dataclasses import fields
import hashlib
import struct

from ...qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from ...qwen35_gdn_prefill.typed_dense import FULL_MASK, TypedMemory
from .owner import (
    BEAT_BYTES, HEAD_BYTES, MemoryRequest, MemoryResponse, PartialRope64Job,
    PartialRope64Owner, PartialRope64Result, QkNorm256Job, QkNorm256Owner,
    QkNorm256Result, require, source_identity,
)
from .scalar import NormRopeScalar


def _hash(region):
    return hashlib.sha256(region.raw()).hexdigest()


def _same_coverage(actual, frozen):
    # Preserve legacy normalization for unusual replacement containers.
    # Exact built-ins avoid fresh sets without trusting a custom __eq__.
    if type(actual) in (set, frozenset):
        return actual == frozen
    return frozenset(actual) == frozen


def _job_fields(job):
    return tuple((field.name, getattr(job, field.name)) for field in fields(job))


class TypedNormRopeDriver:
    """One injected owner, scalar and TypedMemory; no alternate producer path.

    The single outstanding response is generated only after an actual read or
    complete write-data beat. Read/ACK errors exercise the same accepted
    transport obligation, including abort drain. Job and allocation bindings
    are fixed for the entire invocation, including held terminal backpressure.
    """
    def __init__(self, owner, memory, job):
        pair = (type(owner), type(job))
        require(pair in ((QkNorm256Owner, QkNorm256Job),
                         (PartialRope64Owner, PartialRope64Job)),
                'matching typed owner and immutable job required')
        require(type(memory) is TypedMemory and isinstance(owner.scalar, NormRopeScalar),
                'caller-owned shared typed memory and scalar required')
        job.validate()
        require(owner.ports()['job_ready'] and memory.pending is None,
                'drained unpoisoned owner, scalar and memory required')
        self.input = memory.exact(job.input, job.input_bytes, readable=True)
        if type(job) is QkNorm256Job:
            self.weight = memory.exact(job.weight, HEAD_BYTES, readable=True)
            self.inputs = (self.input, self.weight)
        else:
            self.trig = memory.exact(job.trig, job.trig_bytes, readable=True)
            self.inputs = (self.input, self.trig)
        self.outputs = tuple(memory.exact(base, extent, readable=False)
                             for base, extent in job.output_spans)
        self.output = self.outputs[0]
        self.gate_output = self.outputs[1] if len(self.outputs) == 2 else None
        self.owner, self.memory, self.job = owner, memory, job
        self._owner, self._memory, self._job, self._scalar = owner, memory, job, owner.scalar
        self._regions = memory.regions
        self._job_fields = _job_fields(job)
        self._inputs, self._outputs = self.inputs, self.outputs
        self._bindings = tuple((r, r.base, r.extent, r.storage, r.readonly)
                               for r in (*self.inputs, *self.outputs))
        # Diagnostic host snapshots, never owner buffers or hardware resources.
        # The buffer view and base-class equality bypass user-defined equality.
        require(all(isinstance(r.storage, bytearray) for r in self.inputs),
                'physical input storage must be a bytearray buffer')
        self._source_storage = tuple(bytes(memoryview(r.storage)) for r in self.inputs)
        self.source_hashes = tuple(hashlib.sha256(memoryview(b)[64:-64]).hexdigest()
                                   for b in self._source_storage)
        self._source_hashes = self.source_hashes
        self._source_coverage = tuple((frozenset(r.written), frozenset(r.acknowledged))
                                      for r in self.inputs)
        for r in self.inputs:
            require(r.readonly or r.written == r.acknowledged == set(range(0, r.extent, 64)),
                    'input needs actual full producer data/ACK coverage')
        self.identity = source_identity(policy=job.policy) if type(job) is QkNorm256Job else source_identity()
        self.pending, self.response, self.aborted = None, None, False
        self._accepted, self._physical_pending, self._pending_response = None, None, None
        self._accepted_fields, self._response_fields = None, None
        self.counts = Counter()
        require(owner.tick(job=job)['job_fire'], 'typed Norm/RoPE admission rejected')

    def _check_bindings(self):
        require(self.owner is self._owner and self.memory is self._memory and
                self.job is self._job and self.owner.job is self._job and
                self.owner.scalar is self._scalar and self.memory.regions is self._regions,
                'physical resources or job identity replaced')
        require(_job_fields(self.job) == self._job_fields,
                'immutable job descriptor changed')
        require(self.inputs is self._inputs and self.outputs is self._outputs and
                self.input is self._inputs[0] and self.output is self._outputs[0] and
                self.gate_output is (self._outputs[1] if len(self._outputs) == 2 else None),
                'typed span binding replaced')
        require((self.weight if type(self.job) is QkNorm256Job else self.trig) is self._inputs[1],
                'parameter span binding replaced')
        for r, base, extent, storage, readonly in self._bindings:
            require(self.memory.regions.get(base) is r and type(r.base) is int and r.base == base and
                    type(r.extent) is int and r.extent == extent and r.storage is storage and
                    len(r.storage) == extent + 128 and type(r.readonly) is bool and r.readonly == readonly,
                    'physical span geometry or storage identity changed')
            r.check()
        require(self.source_hashes is self._source_hashes, 'source hash binding replaced')
        for r, coverage, frozen in zip(self._inputs, self._source_coverage, self._source_storage):
            require(r.published is True and
                    _same_coverage(r.written, coverage[0]) and
                    _same_coverage(r.acknowledged, coverage[1]) and
                    bytearray.__eq__(r.storage, frozen),
                    'published input or producer coverage changed')
        require(all(r.published is False for r in self._outputs),
                'output published before accepted owner terminal')
        require(self.pending is self._pending_response and
                self.memory.pending is self._physical_pending,
                'accepted transport obligation replaced')
        if self._accepted is not None:
            require(self.owner.request is self._accepted and
                    self._request_fields(self._accepted) == self._accepted_fields and
                    _job_fields(self.pending) == self._response_fields,
                    'accepted owner request changed before response')
            if self._accepted.write:
                physical = self._physical_pending
                require(physical is not None and len(physical) == 4 and
                        physical[0] == WriteCommand(self._accepted.address, 1, self._accepted.tag) and
                        physical[1] is self.memory._resolve(self._accepted.address) and
                        physical[2] == (self._accepted.address - physical[1].base,) and physical[3] == 1,
                        'accepted physical write descriptor changed')
            else:
                require(self._physical_pending is None, 'read owns a physical write obligation')

    @staticmethod
    def _request_fields(request):
        return (_job_fields(request), request.nbytes, request.mask)

    def _check_request(self, request):
        require(type(request) is MemoryRequest and type(request.tag) is int and
                request.tag == ((self.job.tag << 32) | self.counts['memory_requests']) and
                type(request.nbytes) is int and request.nbytes == BEAT_BYTES,
                'full beat request tag/byte identity')
        region = self.memory._resolve(request.address)
        if request.write:
            require(any(region is r for r in self._outputs) and type(request.data) is bytes and
                    len(request.data) == BEAT_BYTES and type(request.mask) is int and request.mask == FULL_MASK,
                    'write escaped typed outputs or full 64-byte mask')
        else:
            require(any(region is r for r in self._inputs) and request.mask == 0,
                    'read escaped typed inputs or read mask')

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             abort=False, read_error=False, ack_error=False):
        require(self.response is None, 'typed Norm/RoPE invocation already retired')
        require(all(type(v) is bool for v in (memory_ready, memory_response_ready, response_ready,
                                             abort, read_error, ack_error)), 'boolean transport controls required')
        self._check_bindings()
        p = self.owner.ports()
        if p['memory'] is not None:
            self._check_request(p['memory'])
        accepted = self._accepted
        pending = self.pending if memory_response_ready else None
        if pending is not None:
            require(accepted is not None and pending.tag == accepted.tag and
                    pending.nbytes == BEAT_BYTES, 'response does not match accepted request')
            pending = MemoryResponse(pending.tag, pending.data,
                                     ack_error if accepted.write else read_error, pending.nbytes)
        abort_edge = abort and not self.aborted
        self.aborted |= abort_edge
        e = self.owner.tick(memory_ready=memory_ready, memory_response=pending,
                            response_ready=response_ready and not abort_edge, abort=abort_edge)
        self.counts['ticks'] += 1
        if e['memory_response_fire']:
            require(pending is not None and accepted is not None,
                    'response without an accepted physical request')
            if accepted.write:
                self.memory.acknowledge(WriteAck(pending.tag, pending.error, pending.nbytes))
                self.counts['ack_bytes'] += 0 if pending.error else BEAT_BYTES
            self.pending = self._pending_response = None
            self._accepted = self._physical_pending = None
            self._accepted_fields = self._response_fields = None
            self.counts['memory_responses'] += 1
        if e['memory_fire']:
            require(self.pending is None and self.memory.pending is None,
                    'multiple outstanding typed Norm/RoPE requests')
            q = e['memory']
            self._check_request(q)
            if q.write:
                self.memory.begin_write(WriteCommand(q.address, 1, q.tag))
                self.memory.write_data(struct.unpack('<32H', q.data), True, mask=q.mask)
                self.pending = MemoryResponse(q.tag)
                self.counts['write_bytes'] += BEAT_BYTES
            else:
                self.pending = MemoryResponse(q.tag, self.memory.read64(q.address))
                self.counts['read_bytes'] += BEAT_BYTES
            self._accepted, self._physical_pending = q, self.memory.pending
            self._pending_response = self.pending
            self._accepted_fields = self._request_fields(q)
            self._response_fields = _job_fields(self.pending)
            self.counts['memory_requests'] += 1
        if e['response_fire']:
            require(self.pending is None and self.memory.pending is None and self._accepted is None,
                    'terminal before accepted transport drained')
            require(tuple(_hash(r) for r in self._inputs) == self._source_hashes,
                    'terminal input SHA identity changed')
            result = e['response']
            expected_type = QkNorm256Result if type(self.job) is QkNorm256Job else PartialRope64Result
            require(type(result) is expected_type and type(result.tag) is int and result.tag == self.job.tag and
                    type(result.write_bytes) is int and result.write_bytes == self.counts['ack_bytes'],
                    'held terminal tag/ACK byte identity')
            require(self._scalar.client is None, 'terminal retained the shared scalar')
            if result.status is None:
                require(not self.aborted and not self.owner.ports()['reset_required'] and
                        result.write_bytes == self.job.write_bytes and
                        self.counts['write_bytes'] == self.job.write_bytes,
                        'success before complete accepted output writes/ACKs')
                current = (source_identity(policy=self.job.policy) if type(self.job) is QkNorm256Job
                           else source_identity())
                require(current == self.identity, 'frozen source identity changed during execution')
                response = (result.tag, result.status, result.write_bytes)
                bases = tuple(r.base for r in self._outputs)
                if len(bases) == 1:
                    self.memory.publish(bases[0], response)
                else:
                    self.memory.publish_many(bases, response)
            self.response = result
        return e

    def report(self):
        return dict(owner=self.owner.report(), complete=self.response is not None,
                    status=None if self.response is None else self.response.status,
                    counts=dict(self.counts), input_sha256=list(self.source_hashes),
                    output_sha256=[_hash(r) for r in self._outputs],
                    output_published=[r.published for r in self._outputs],
                    identity=self.identity, hardware_cycles=None, rtl_executed=False,
                    native_acceptance=False)


TypedQkNorm256Driver = TypedNormRopeDriver
TypedPartialRope64Driver = TypedNormRopeDriver
