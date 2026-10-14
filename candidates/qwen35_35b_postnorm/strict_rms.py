"""Fail-closed postnorm fence around the unchanged H2048 RMS driver.

Only a written, ACKed and published producer span can be the hidden input.
The existing RMS owner, scalar, three 2048-byte banks and wire schedule do all
arithmetic and transport. Hashes and receipts below are host-only integrity
observations, not numeric inputs, new physical arrays or hardware evidence.
"""
from copy import deepcopy
from dataclasses import fields
import hashlib
import struct

from ..qwen35_35b_rms import owner as rms
from ..qwen35_gdn_prefill.typed_dense import GUARD, Region


def require(ok, detail):
    if not ok:
        raise ValueError('strict postnorm: ' + detail)


def _fields(value):
    return tuple((field.name, type(getattr(value, field.name)), getattr(value, field.name))
                 for field in fields(value))


def _coverage(actual, expected):
    return (type(actual) in (set, frozenset) and
            all(type(offset) is int for offset in actual) and actual == expected)


class StrictPostNormDriver(rms.TypedRmsDriver):
    """Preserve TypedRmsDriver.tick and validate before its terminal handshake.

    Integrity errors do not invent a failed terminal, erase pending transport,
    or repair malformed ACKs. A caller must restore corrupted bindings before
    retry/drain. An actual first abort can replace held success with the real
    owner's Aborted receipt; holding abort high cannot bypass later preflight.
    """

    def __init__(self, owner, memory, job):
        require(type(owner) is rms.RmsOwner and type(memory) is rms.TypedMemory and
                type(job) is rms.RmsJob, 'original owner, memory and immutable H2048 job required')
        job.validate()
        require(owner.ports()['job_ready'] and memory.pending is None, 'drained resources required')
        source = memory.exact(job.input, job.write_bytes, readable=True)
        weight = memory.exact(job.weight, rms.ROW_BYTES, readable=True)
        output = memory.exact(job.output, job.write_bytes, readable=False)
        complete = set(range(0, job.write_bytes, rms.BEAT_BYTES))
        require(source.readonly is False and source.published is True and
                _coverage(source.written, complete) and _coverage(source.acknowledged, complete),
                'input requires actual nonreadonly producer data/ACK/publication')
        require(weight.readonly is True and weight.published is True and
                _coverage(weight.written, set()) and _coverage(weight.acknowledged, set()),
                'weight requires immutable readonly BF16[2048] bytes')
        require(output.published is False and _coverage(output.written, set()) and
                _coverage(output.acknowledged, set()) and
                output.raw() == GUARD * (job.write_bytes // rms.BEAT_BYTES),
                'output must retain fresh initial sentinels')
        self._owner, self._memory, self._job = owner, memory, job
        self._scalar, self._regions = owner.scalar, memory.regions
        self._job_binding = _fields(job)
        self._sources, self._output = (source, weight), output
        self._bindings = tuple((region, region.base, region.extent, region.storage, region.readonly)
                               for region in (source, weight, output))
        self._banks = (owner.row_bank, owner.weight_bank, owner.output_bank)
        self._observer = owner.observer
        self._source_coverage = tuple((frozenset(region.written), frozenset(region.acknowledged))
                                      for region in self._sources)
        # Validate geometry/resources before super.__init__ acquires the scalar.
        self._check_regions()
        self._check_banks()
        super().__init__(owner, memory, job)
        self._source_hashes = self.source_hashes
        self._source_identity = deepcopy(owner.identity)
        self._output_hash = hashlib.sha256()
        self._write_bytes, self._ack_bytes = 0, 0
        self._terminal_receipt = None
        self._pending_receipt, self._pending_write = None, None
        self._request_receipt = (owner.request, _fields(owner.request))

    def _check_banks(self):
        banks = (self._owner.row_bank, self._owner.weight_bank, self._owner.output_bank)
        require(all(actual is original and type(actual) is bytearray and len(actual) == rms.CHUNK_BYTES
                    for actual, original in zip(banks, self._banks)) and
                len({id(bank) for bank in banks}) == 3, 'original three 2048B banks changed')

    def _check_regions(self):
        require(type(self._regions) is dict and self._memory.regions is self._regions,
                'physical allocation map replaced')
        for region, base, extent, storage, readonly in self._bindings:
            require(type(region) is Region and self._regions.get(base) is region and
                    type(region.base) is int and region.base == base and
                    type(region.extent) is int and region.extent == extent and
                    region.storage is storage and type(storage) is bytearray and len(storage) == extent + 128 and
                    type(region.readonly) is bool and region.readonly == readonly,
                    'physical region geometry or storage binding changed')
            # Check partial overlaps as well as aliases covering an entire span.
            require(all(other is region and key == base or
                        type(other) is Region and type(other.base) is int and
                        type(other.extent) is int and other.extent > 0 and
                        (other.base + other.extent <= base or base + extent <= other.base)
                        for key, other in self._regions.items()), 'physical region allocation alias')
            region.check()

    def _check_bindings(self):
        require(self.owner is self._owner and self.memory is self._memory and
                self.owner.scalar is self._scalar and self.owner.observer is self._observer,
                'owner/memory/scalar/observer resource replaced')
        require(self.job is self._job and self.owner.job is self._job and
                _fields(self.job) == self._job_binding, 'original immutable job changed')
        require(self.input is self._sources[0] and self.weight is self._sources[1] and
                self.output is self._output, 'typed source/output binding replaced')
        require(self.source_hashes is self._source_hashes, 'source hash binding replaced')
        self._check_regions()
        self._check_banks()

    def _check_transport(self):
        """Reject tampering before the inherited tick can retire an obligation."""
        receipt = self._request_receipt
        require(self.owner.request is (None if receipt is None else receipt[0]) and
                (receipt is None or _fields(self.owner.request) == receipt[1]),
                'original owner request changed')
        if self._pending_receipt is None:
            require(self.pending is None and self.memory.pending is None and self._pending_write is None,
                    'unrecorded pending transport obligation')
            return
        pending, binding = self._pending_receipt
        require(self.pending is pending and _fields(pending) == binding and receipt is not None and
                self.owner.state in ('wait', 'drain') and pending.tag == receipt[0].tag,
                'accepted pending response changed')
        if receipt[0].write:
            require(self._pending_write is not None, 'missing physical write obligation')
            record, command, command_binding, region, offsets, count = self._pending_write
            require(self.memory.pending is record and type(record) is list and len(record) == 4 and
                    record[0] is command and _fields(command) == command_binding and
                    record[1] is region and type(record[2]) is tuple and record[2] == offsets and
                    all(type(offset) is int for offset in record[2]) and
                    type(record[3]) is int and record[3] == count,
                    'accepted physical write obligation changed')
        else:
            require(self._pending_write is None and self.memory.pending is None,
                    'read response cannot retire a physical write')

    def preflight_response(self):
        """Read-only inspection of the genuine held terminal, rechecked on ready."""
        require(self.response is None, 'RMS invocation already retired')
        self._check_bindings()
        self._check_transport()
        result = self.owner.ports()['response']
        receipt = self._terminal_receipt
        require(type(result) is rms.RmsResult and receipt is not None and result is receipt[0] and
                _fields(result) == receipt[1], 'original held real terminal required')
        require(self.pending is None and self.memory.pending is None and self._pending_receipt is None and
                self._pending_write is None and self.owner.request is None and self.owner.program is None,
                'terminal before transport drained')
        require(type(result.tag) is int and result.tag == self._job.tag and
                type(result.write_bytes) is int and type(self.owner.ack_bytes) is int and
                type(self.counts['ack_bytes']) is int and
                result.write_bytes == self.owner.ack_bytes == self._ack_bytes == self.counts['ack_bytes'] and
                0 <= result.write_bytes <= self._write_bytes <= self._job.write_bytes and
                result.write_bytes % rms.BEAT_BYTES == 0 and
                type(result.model_ticks) is int and result.model_ticks >= 0 and
                (result.status is None or type(result.status) is str and bool(result.status)) and
                result.status == self.owner.status, 'terminal tag/status/byte/tick receipt changed')
        require(self._scalar.client is None, 'terminal retained shared scalar')
        require(self.output.published is False, 'output published before accepted owner terminal')
        for region, coverage, digest in zip(self._sources, self._source_coverage, self._source_hashes):
            require(region.published is True and _coverage(region.written, coverage[0]) and
                    _coverage(region.acknowledged, coverage[1]) and
                    rms.sha(memoryview(region.storage)[64:-64]) == digest,
                    'producer/weight bytes or publication/data/ACK coverage changed')
        if result.status is None:
            require(self.aborted is False and self.owner.poison is False and
                    type(self.counts['write_bytes']) is int and
                    type(self.owner.counts['write_acks']) is int and
                    result.write_bytes == self._write_bytes == self.counts['write_bytes'] == self._job.write_bytes and
                    self.owner.counts['write_acks'] * rms.BEAT_BYTES == result.write_bytes,
                    'complete actual write/ACK receipt required')
            complete = set(range(0, self._job.write_bytes, rms.BEAT_BYTES))
            require(_coverage(self.output.written, complete) and _coverage(self.output.acknowledged, complete),
                    'incomplete actual output write/ACK coverage')
            raw = memoryview(self.output.storage)[64:-64]
            require(hashlib.sha256(raw).digest() == self._output_hash.digest() and
                    all(rms.finite(bits << 16) for (bits,) in struct.iter_unpack('<H', raw)),
                    'output differs from actual finite write data')
            require(self.owner.identity == self._source_identity == self.owner.source_identity(self._job.policy),
                    'RMS source changed during execution')
        else:
            require(self.owner.poison is True, 'failed terminal must poison owner')
        return result

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             abort=False, read_error=False, ack_error=False):
        require(self.response is None, 'RMS invocation already retired')
        self._check_bindings()
        self._check_transport()
        abort_edge = abort and not self.aborted
        before = self.owner.state
        if response_ready and not abort_edge and self.owner.ports()['response'] is not None:
            self.preflight_response()
        request = self.owner.request
        if request is not None and request.write and before == 'issue' and memory_ready and not abort_edge:
            require(type(request.data) is bytes and len(request.data) == rms.BEAT_BYTES and
                    request.address == self._job.output + self._write_bytes,
                    'actual output writes must follow complete physical order')
        event = super().tick(memory_ready=memory_ready, memory_response_ready=memory_response_ready,
                             response_ready=response_ready, abort=abort,
                             read_error=read_error, ack_error=ack_error)
        if event['memory_response_fire']:
            if request.write and not ack_error:
                self._ack_bytes += rms.BEAT_BYTES
                self.counts['ack_bytes'] += rms.BEAT_BYTES
            self._pending_receipt, self._pending_write = None, None
        if event['memory_fire']:
            actual = event['memory']
            if actual.write:
                # Expected digest is observed from actual accepted request DATA,
                # never reconstructed from output storage or a reference array.
                self._output_hash.update(actual.data)
                self._write_bytes += rms.BEAT_BYTES
                record = self.memory.pending
                command, region, offsets, count = record
                self._pending_write = (record, command, _fields(command), region, offsets, count)
            self._pending_receipt = (self.pending, _fields(self.pending))
        current = self.owner.request
        self._request_receipt = None if current is None else (current, _fields(current))
        # PRE-edge response ports mean the final ACK cannot accept its newly
        # produced result. Capture it only at creation, never refresh a held
        # receipt from potentially replaced/mutated public state.
        if self.owner.state == 'finish' and (before != 'finish' or abort_edge):
            self._terminal_receipt = (self.owner.result, _fields(self.owner.result))
        return event
