"""BF16 causal GQA transport on the caller's one TypedMemory byte map.

Only real published Q/K/V producers may feed the owner. The adapter creates
no arithmetic service or tensor: owner requests fetch individual 64-byte beats,
and actual output write data and ACKs stay private until its successful held
terminal is accepted. Host identity snapshots never feed owner arithmetic.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import fields
import hashlib
import struct

from ...qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from ...qwen35_gdn_prefill.typed_dense import TypedMemory
from .owner import (
    BEAT_BYTES, FULL_MASK, Bf16CausalGqaJob, Bf16CausalGqaOwner,
    Bf16CausalGqaResult, MemoryRequest, MemoryResponse, require, source_identity,
)


def _field_values(value):
    # Include exact field types: bools and integer-like objects cannot stand in
    # for an admitted integer merely because their equality happens to match.
    return tuple((field.name, type(getattr(value, field.name)),
                  getattr(value, field.name)) for field in fields(value))


def _same_coverage(actual, expected):
    # Real TypedMemory producers use exact sets; another GQA invocation may
    # already have sealed them. Reject custom equality/iteration and bool/int
    # aliases before converting the actual metadata to an immutable object.
    return (type(actual) in (set, frozenset) and len(actual) == len(expected) and
            all(type(offset) is int for offset in actual) and actual == expected)


class TypedBf16CausalGqaDriver:
    """One injected owner, Matrix, scalar and memory, with one pending beat.

    Software handshake ticks are not hardware cycles. An integrity failure
    poisons this invocation; explicit abort still drains an already accepted
    read/write and retires a failed terminal without publishing the output.
    """
    def __init__(self, owner, memory, job):
        require(type(owner) is Bf16CausalGqaOwner and type(job) is Bf16CausalGqaJob and
                type(memory) is TypedMemory,
                'explicit typed GQA owner/job/shared memory required')
        job.validate()
        require(owner.ports()['job_ready'] and memory.pending is None,
                'drained unpoisoned GQA owner and memory required')
        require(job.input_spans == ((job.query_input, job.tokens * 4096),
                                   (job.cache_base, job.cache_length * 1024),
                                   (job.cache_base + job.capacity_tokens * 1024,
                                    job.cache_length * 1024)) and
                job.output_spans == ((job.output, job.tokens * 4096),),
                'exact BF16 Q/K/V and output span geometry required')
        inputs = tuple(memory.exact(base, extent, readable=True)
                       for base, extent in job.input_spans)
        outputs = tuple(memory.exact(base, extent, readable=False)
                        for base, extent in job.output_spans)
        require(all(r.readonly is False and r.published is True and
                    _same_coverage(r.written, frozenset(range(0, r.extent, BEAT_BYTES))) and
                    _same_coverage(r.acknowledged, frozenset(range(0, r.extent, BEAT_BYTES)))
                    for r in inputs), 'actual published Q/K/V producer data/ACK required')
        require(all(r.readonly is False and r.published is False and
                    _same_coverage(r.written, frozenset()) and
                    _same_coverage(r.acknowledged, frozenset()) for r in outputs),
                'fresh output cannot contain prior write/ACK coverage')
        require(type(memory.regions) is dict and
                all(type(r.storage) is bytearray for r in (*inputs, *outputs)),
                'physical bytearray storage and exact allocation map required')
        self.owner, self.matrix, self.scalar = owner, owner.matrix, owner.scalar
        self.memory, self.job = memory, job
        self.inputs, self.outputs = inputs, outputs
        self.query, self.key, self.value = inputs
        self.output = outputs[0]
        self._owner, self._matrix, self._scalar = owner, owner.matrix, owner.scalar
        self._memory, self._job, self._regions = memory, job, memory.regions
        self._matrix_library = self.matrix.lib
        self._matrix_address, self._matrix_epoch = self.matrix.resource_address, self.matrix.epoch
        self._owner_buffers = tuple((name, getattr(owner, name), type(getattr(owner, name)),
                                     len(getattr(owner, name)))
                                    for name in ('query', 'keys', 'scores', 'qk', 'context', 'value',
                                                 'maximum', 'seen'))
        self._observer = owner.observer
        self._inputs, self._outputs = inputs, outputs
        self._job_fields = _field_values(job)
        self._bindings = tuple((r, r.base, r.extent, r.storage, r.readonly)
                               for r in (*inputs, *outputs))
        # Immutable host diagnostics, including source guards. They are never
        # passed to the owner and cannot become an alternate arithmetic path.
        self._source_storage = tuple(bytes(memoryview(r.storage)) for r in inputs)
        self._source_coverage = tuple((frozenset(r.written), frozenset(r.acknowledged))
                                      for r in inputs)
        for r, coverage in zip(inputs, self._source_coverage):
            r.written, r.acknowledged = coverage
        self._source_hashes = tuple(hashlib.sha256(memoryview(raw)[64:-64]).hexdigest()
                                    for raw in self._source_storage)
        self._written_offsets, self._acknowledged_offsets = set(), set()
        self._seal_output_coverage()
        self._output_hash = hashlib.sha256()
        self.identity = source_identity()
        self._identity, self._identity_object = deepcopy(self.identity), self.identity
        self._integrity_errors = []
        self._owner_terminal_report = None
        self.pending = self.response = None
        self._pending_response = self._accepted = self._physical_pending = None
        self._accepted_fields = self._response_fields = None
        self._held_request = self._held_request_fields = None
        self._held_terminal = self._held_terminal_fields = None
        self.aborted = False
        self.counts = Counter()
        require(owner.tick(job=job)['job_fire'], 'GQA owner admission rejected')

    def _integrity(self, condition, detail, *, cancelling=False):
        if not condition:
            if detail not in self._integrity_errors:
                self._integrity_errors.append(detail)
            self.owner.poison = True
            require(cancelling, detail)

    @staticmethod
    def _request_fields(request):
        return (_field_values(request), type(request.nbytes), request.nbytes,
                type(request.mask), request.mask, type(request.write), request.write)

    def _seal_output_coverage(self):
        # Validate metadata produced by the actual memory operation, then
        # freeze those values, never the driver's expected offset ledger.
        require(_same_coverage(self.output.written, self._written_offsets) and
                _same_coverage(self.output.acknowledged, self._acknowledged_offsets),
                'altered actual output write/ACK coverage')
        self._output_coverage = (frozenset(self.output.written),
                                 frozenset(self.output.acknowledged))
        self.output.written, self.output.acknowledged = self._output_coverage

    def _thaw_output_coverage(self, field):
        require(self.output.written is self._output_coverage[0] and
                self.output.acknowledged is self._output_coverage[1],
                'altered output write/ACK coverage seal')
        # Only the field mutated by the immediately following TypedMemory
        # operation is writable. Every tick boundary retains exact frozensets.
        setattr(self.output, field, set(getattr(self.output, field)))

    def _check_bindings(self, *, cancelling=False):
        require(self.owner is self._owner and self.matrix is self._matrix and
                self.scalar is self._scalar and self.memory is self._memory and
                self.job is self._job and self.owner.job is self._job and
                self.owner.matrix is self._matrix and self.owner.scalar is self._scalar and
                self.memory.regions is self._regions,
                'physical resources or job identity replaced')
        require(self.matrix.lib is self._matrix_library and
                type(self.matrix.resource_address) is int and
                self.matrix.resource_address == self._matrix_address and
                type(self.matrix.epoch) is int and self.matrix.epoch == self._matrix_epoch and
                self.matrix.owner is self._owner and
                (self.scalar.client is None or self.scalar.client is self._owner),
                'shared Matrix/scalar resource or ownership changed')
        require(_field_values(self.job) == self._job_fields, 'immutable job descriptor changed')
        require(self.owner.observer is self._observer and
                all(getattr(self.owner, name) is buffer and type(buffer) is kind and len(buffer) == size
                    for name, buffer, kind, size in self._owner_buffers),
                'bounded owner buffer or observer identity changed')
        require(self.inputs is self._inputs and self.outputs is self._outputs and
                self.query is self._inputs[0] and self.key is self._inputs[1] and
                self.value is self._inputs[2] and self.output is self._outputs[0],
                'typed Q/K/V/output span identity replaced')
        for r, base, extent, storage, readonly in self._bindings:
            require(self.memory.regions.get(base) is r and type(r.base) is int and r.base == base and
                    type(r.extent) is int and r.extent == extent and r.storage is storage and
                    len(r.storage) == extent + 128 and type(r.readonly) is bool and r.readonly == readonly,
                    'physical span geometry or storage identity changed')
            # Source guard corruption is a latched source failure below, so a
            # known accepted transport obligation can still drain on abort.
            if r is self._outputs[0]:
                r.check()
        for r, frozen, coverage in zip(self._inputs, self._source_storage, self._source_coverage):
            self._integrity(r.published is True and bytearray.__eq__(r.storage, frozen) and
                            r.written is coverage[0] and r.acknowledged is coverage[1],
                            'published source bytes or producer coverage changed', cancelling=cancelling)
        require(not self._integrity_errors or cancelling,
                'latched integrity failure requires abort before further execution')
        require(self.output.published is False and
                self.output.written is self._output_coverage[0] and
                self.output.acknowledged is self._output_coverage[1] and
                self.counts['write_bytes'] == len(self._written_offsets) * BEAT_BYTES and
                self.counts['ack_bytes'] == len(self._acknowledged_offsets) * BEAT_BYTES,
                'premature output publication or altered write/ACK coverage')
        require(self.pending is self._pending_response and self.memory.pending is self._physical_pending,
                'accepted transport obligation replaced')
        if self._accepted is not None:
            require(self.owner.request is self._accepted and
                    self._request_fields(self._accepted) == self._accepted_fields and
                    _field_values(self.pending) == self._response_fields,
                    'accepted request/response changed before drain')
            if self._accepted.write:
                physical = self._physical_pending
                require(type(physical) is list and len(physical) == 4 and
                        type(physical[0]) is WriteCommand and
                        _field_values(physical[0]) ==
                        _field_values(WriteCommand(self._accepted.address, 1, self._accepted.tag)) and
                        physical[1] is self.output and
                        type(physical[2]) is tuple and
                        all(type(offset) is int for offset in physical[2]) and
                        physical[2] == (self._accepted.address - self.output.base,) and
                        type(physical[3]) is int and physical[3] == 1,
                        'accepted physical write descriptor changed')
            else:
                require(self._physical_pending is None, 'read acquired a physical write obligation')

    def _write_offset(self, index):
        # Production order is tile, head, row, beat; rows are token-major in
        # physical memory, so the accepted address stream is not monotonic.
        tile, within_tile = divmod(index, 16 * 8 * 8)
        first_row = tile * 16
        rows = min(16, self.job.tokens - first_row)
        require(rows > 0, 'write beyond exact GQA output')
        head, within_head = divmod(within_tile, rows * 8)
        row, beat = divmod(within_head, 8)
        require(head < 8 and row < rows, 'write beyond active GQA tile')
        return (first_row + row) * 4096 + head * 512 + beat * BEAT_BYTES

    def _check_request(self, request):
        require(type(request) is MemoryRequest and type(request.tag) is int and
                request.tag == ((self.job.tag << 32) | self.counts['memory_requests']) and
                type(request.nbytes) is int and request.nbytes == BEAT_BYTES and
                type(request.address) is int and type(request.write) is bool and type(request.mask) is int,
                'full beat request tag/address/byte identity')
        region = self.memory._resolve(request.address)
        if request.write:
            offset = self._write_offset(self.counts['write_bytes'] // BEAT_BYTES)
            require(region is self.output and request.address == self.output.base + offset and
                    offset not in self._written_offsets and type(request.data) is bytes and
                    len(request.data) == BEAT_BYTES and request.mask == FULL_MASK,
                    'write escaped exact GQA output order or full 64-byte data/mask')
        else:
            require(any(region is r for r in self._inputs) and request.mask == 0 and request.data is None,
                    'read escaped typed Q/K/V producer spans')

    def _validate_held_terminal(self, result):
        require(self.pending is None and self.memory.pending is None and self._accepted is None,
                'GQA terminal before accepted transport drained')
        require(type(result) is Bf16CausalGqaResult and type(result.tag) is int and
                result.tag == self.job.tag and type(result.write_bytes) is int and
                result.write_bytes == self.counts['ack_bytes'] and
                type(result.model_ticks) is int and result.model_ticks >= 0 and
                type(result.attention_status) is int and 0 <= result.attention_status < 1 << 32 and
                (result.status is None or type(result.status) is str and bool(result.status)) and
                type(result.output_committed) is bool,
                'held terminal tag/ACK byte/commit identity')
        require(self.scalar.client is None, 'held GQA terminal retained the shared scalar')
        if self._integrity_errors:
            require(self.aborted and self.owner.poison and result.status is not None,
                    'integrity failure requires a drained failed terminal')
        else:
            self._integrity(tuple(hashlib.sha256(r.raw()).hexdigest() for r in self._inputs) ==
                            self._source_hashes, 'terminal source byte identity changed')
        if result.status is None:
            require(not self.aborted and not self.owner.ports()['reset_required'] and
                    result.output_committed and result.attention_status == 0 and
                    result.write_bytes == self.counts['write_bytes'] == self.job.write_bytes,
                    'success before complete accepted output writes/ACKs')
            actual = hashlib.sha256()
            storage = memoryview(self.output.storage)
            for index in range(self.job.write_bytes // BEAT_BYTES):
                offset = self._write_offset(index)
                actual.update(storage[64 + offset:128 + offset])
            self._integrity(actual.digest() == self._output_hash.digest(),
                            'terminal output differs from actual accepted write data')
            self._integrity(self.identity is self._identity_object and self.identity == self._identity and
                            source_identity() == self._identity,
                            'GQA source identity changed during execution')
        else:
            require(not result.output_committed, 'failed terminal cannot commit GQA output')

    def _checked_success_revocation(self, previous, current):
        """Accept only this transaction's poisoned, unaccepted-success revoke.

        The owner globally monitors shared-Matrix faults, including while a
        successful terminal is backpressured. That fault replaces the held
        success with a fresh failed terminal. Ordinary terminal drift, a new
        resource epoch, and any already accepted terminal remain inadmissible.
        No bytes are published or arithmetic recomputed by this transition.
        """
        return (
            self.response is None and self._owner_terminal_report is None and
            type(previous) is Bf16CausalGqaResult and type(current) is Bf16CausalGqaResult and
            previous is not current and _field_values(previous) == self._held_terminal_fields and
            previous.status is None and previous.output_committed is True and
            current.status in ('Protocol', 'Aborted') and current.output_committed is False and
            type(current.tag) is int and current.tag == previous.tag == self.job.tag and
            type(current.write_bytes) is int and
            current.write_bytes == previous.write_bytes == self.counts['ack_bytes'] == self.job.write_bytes and
            type(current.model_ticks) is int and current.model_ticks >= previous.model_ticks and
            type(current.attention_status) is int and current.attention_status == previous.attention_status == 0 and
            self.owner.state == 'finish' and self.owner.result is current and
            self.owner.job is self._job and self.owner.status == current.status and self.owner.poison is True and
            self.matrix.owner is self.owner and self.matrix.reset_required and
            self.matrix.epoch == self._matrix_epoch == self.owner._epoch and
            self.pending is None and self.memory.pending is None and self._accepted is None and
            self.scalar.client is None
        )

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             matrix_group_ready=True, matrix_step_ready=True, matrix_result_ready=True,
             matrix_done_ready=True, scalar_ready=True, abort=False, read_error=False, ack_error=False):
        require(self.response is None, 'GQA invocation already retired')
        require(all(type(v) is bool for v in (memory_ready, memory_response_ready, response_ready,
                    matrix_group_ready, matrix_step_ready, matrix_result_ready, matrix_done_ready,
                    scalar_ready, abort, read_error, ack_error)), 'boolean transport controls required')
        self._check_bindings(cancelling=abort or self.aborted)
        ports = self.owner.ports()
        request = ports['memory']
        if self._held_request is not None:
            require((request is self._held_request and
                     self._request_fields(request) == self._held_request_fields) or
                    (request is None and (abort or self.aborted or self.owner.poison)),
                    'stalled memory request changed before acceptance')
        if request is not None:
            self._check_request(request)
            self._held_request, self._held_request_fields = request, self._request_fields(request)
        else:
            self._held_request = self._held_request_fields = None
        accepted = self._accepted
        pending = self.pending if memory_response_ready else None
        if pending is not None:
            require(accepted is not None and pending.tag == accepted.tag and pending.nbytes == BEAT_BYTES,
                    'response does not match accepted request')
            pending = MemoryResponse(pending.tag, pending.data,
                                     ack_error if accepted.write else read_error, pending.nbytes)
        abort_edge = abort and not self.aborted
        self.aborted |= abort_edge
        terminal_ready = response_ready and not abort_edge
        result = ports['response']
        if self._held_terminal is not None:
            require((result is self._held_terminal and _field_values(result) == self._held_terminal_fields) or
                    self._checked_success_revocation(self._held_terminal, result),
                    'held terminal changed before acceptance')
        if result is not None:
            self._held_terminal, self._held_terminal_fields = result, _field_values(result)
            # Let the owner's global fault monitor revoke its unaccepted
            # success first, even if the receiver is ready on this edge.
            # Validating/accepting that stale success would either publish
            # after a Matrix fault or block the required failed-terminal drain.
            if (result.status is None and self.owner.status is None and self.matrix.reset_required and
                    self.owner.state == 'finish' and self.owner.result is result and
                    self.matrix.epoch == self._matrix_epoch == self.owner._epoch):
                terminal_ready = False
            if terminal_ready:
                self._validate_held_terminal(result)
        event = self.owner.tick(memory_ready=memory_ready, memory_response=pending,
                                response_ready=terminal_ready, matrix_group_ready=matrix_group_ready,
                                matrix_step_ready=matrix_step_ready, matrix_result_ready=matrix_result_ready,
                                matrix_done_ready=matrix_done_ready, scalar_ready=scalar_ready, abort=abort_edge)
        self.counts['ticks'] += 1
        if abort_edge:
            self._held_request = self._held_request_fields = None
            self._held_terminal = self._held_terminal_fields = None
        if event['memory_response_fire']:
            require(pending is not None and accepted is not None, 'response without physical request')
            if accepted.write:
                self._thaw_output_coverage('acknowledged')
                self.memory.acknowledge(WriteAck(pending.tag, pending.error, pending.nbytes))
                if not pending.error:
                    self._acknowledged_offsets.add(accepted.address - self.output.base)
                    self.counts['ack_bytes'] += BEAT_BYTES
                self._seal_output_coverage()
            self.pending = self._pending_response = None
            self._accepted = self._physical_pending = None
            self._accepted_fields = self._response_fields = None
            self.counts['memory_responses'] += 1
        if event['memory_fire']:
            require(self.pending is None and self.memory.pending is None, 'multiple outstanding GQA requests')
            request = event['memory']
            self._check_request(request)
            if request.write:
                self.memory.begin_write(WriteCommand(request.address, 1, request.tag))
                self._thaw_output_coverage('written')
                self.memory.write_data(struct.unpack('<32H', request.data), True, mask=request.mask)
                self.pending = MemoryResponse(request.tag)
                self._written_offsets.add(request.address - self.output.base)
                self._output_hash.update(request.data)
                self.counts['write_bytes'] += BEAT_BYTES
                self._seal_output_coverage()
            else:
                self.pending = MemoryResponse(request.tag, self.memory.read64(request.address))
                self.counts['read_bytes'] += BEAT_BYTES
            self._accepted, self._physical_pending = request, self.memory.pending
            self._pending_response = self.pending
            self._accepted_fields, self._response_fields = self._request_fields(request), _field_values(self.pending)
            self._held_request = self._held_request_fields = None
            self.counts['memory_requests'] += 1
        if event['response_fire']:
            result = event['response']
            require(result is ports['response'], 'owner changed the validated held terminal')
            require(self.matrix.owner is None and self.scalar.client is None,
                    'accepted GQA terminal retained shared arithmetic resources')
            if result.status is None:
                self.memory.publish(self.output.base, (result.tag, result.status, result.write_bytes))
            # The accepted terminal ends this invocation's seal ownership.
            # Return actual coverage to the shared memory's ordinary mutable
            # representation without clearing any writes/ACKs or repairing
            # bytes. A wholly unwritten failed output can then be reused by
            # another producer; partial output still fails the fresh fence.
            self.output.written, self.output.acknowledged = (
                set(self.output.written), set(self.output.acknowledged))
            self.response = result
            self._owner_terminal_report = deepcopy(self.owner.report())
            self._held_terminal = self._held_terminal_fields = None
        return event

    def report(self):
        return dict(owner=(deepcopy(self._owner_terminal_report) if self._owner_terminal_report is not None
                           else self.owner.report()), complete=self.response is not None,
                    status=None if self.response is None else self.response.status,
                    counts=dict(self.counts), input_sha256=list(self._source_hashes),
                    output_sha256=[hashlib.sha256(self.output.raw()).hexdigest()],
                    output_published=[self.output.published], identity=deepcopy(self._identity),
                    integrity_errors=list(self._integrity_errors), software_only=True,
                    hardware_cycles=None, rtl_executed=False, native_acceptance=False,
                    fullblock_executed=False)
