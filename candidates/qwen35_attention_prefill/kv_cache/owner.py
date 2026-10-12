"""Memory-request KV prefix copy and append, retaining one 64-byte beat.

K and V are token-major BF16 [tokens, 2, 256]. The owner has no arithmetic
array, cache commit operation, direct physical memory access, or oracle input.
Every copied byte arrives in a read response and leaves in a write request.
Software handshake ticks do not represent hardware cycles or RTL execution.
"""
from collections import Counter
from dataclasses import dataclass
import hashlib
from pathlib import Path


BEAT_BYTES, TOKEN_BYTES, CAPACITY = 64, 1024, 256
FULL_MASK = (1 << BEAT_BYTES) - 1
ROOT = Path(__file__).resolve().parents[3]
NEW_SOURCES = tuple('candidates/qwen35_attention_prefill/kv_cache/' + name for name in
                    ('__init__.py', 'owner.py', 'driver.py', 'fence.py', 'test_kv_cache.py'))
SHARED_TRANSPORT_SOURCES = (
    'candidates/qwen35_gdn_prefill/typed_dense.py',
    'candidates/qwen2_resident_matrix/transposed_down/model.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py',
)


def require(condition, detail):
    if not condition:
        raise ValueError('typed KV: ' + detail)


def uint(value, bits):
    return type(value) is int and 0 <= value < 1 << bits


def same_coverage(actual, expected):
    """Bounded exact-int offset check; never trust a container/element __eq__."""
    if type(actual) in (set, frozenset):
        return len(actual) == len(expected) and all(type(offset) is int for offset in actual) and actual == expected
    offsets = []
    for index, offset in enumerate(actual):
        if index >= len(expected) or type(offset) is not int:
            return False
        offsets.append(offset)
    return frozenset(offsets) == expected


def span(base, extent):
    require(uint(base, 56) and base % BEAT_BYTES == 0 and
            type(extent) is int and extent > 0 and extent % BEAT_BYTES == 0 and
            base + extent <= 1 << 56, 'aligned nonempty 56-bit physical span')


def disjoint(a, b):
    return a[0] + a[1] <= b[0] or b[0] + b[1] <= a[0]


def source_identity(root=ROOT):
    """New KV sources have their own identity, independent of earlier gates."""
    return dict(source_sha256={name: hashlib.sha256((Path(root) / name).read_bytes()).hexdigest()
                               for name in NEW_SOURCES},
                shared_transport_sha256={name: hashlib.sha256((Path(root) / name).read_bytes()).hexdigest()
                                         for name in SHARED_TRANSPORT_SOURCES},
                scope='KV_COPY_APPEND_SOFTWARE_ONLY', rtl_executed=False,
                hardware_cycles=None, native_acceptance=False, fullblock_executed=False)


@dataclass(frozen=True)
class KvCacheJob:
    tag: int
    previous_k: int
    previous_v: int
    previous_tokens: int
    new_k: int
    new_v: int
    staging_k: int
    tokens: int
    expected_generation: int
    current_generation: int
    capacity: int = CAPACITY
    dtype: str = 'bf16'

    @property
    def staging_v(self):
        return self.staging_k + self.capacity * TOKEN_BYTES

    @property
    def valid_tokens(self):
        return self.previous_tokens + self.tokens

    @property
    def output_spans(self):
        return ((self.staging_k, self.valid_tokens * TOKEN_BYTES),
                (self.staging_v, self.valid_tokens * TOKEN_BYTES))

    @property
    def input_spans(self):
        old = ((self.previous_k, self.previous_tokens * TOKEN_BYTES),
               (self.previous_v, self.previous_tokens * TOKEN_BYTES)) if self.previous_tokens else ()
        return old + ((self.new_k, self.tokens * TOKEN_BYTES),
                      (self.new_v, self.tokens * TOKEN_BYTES))

    @property
    def write_bytes(self):
        return 2 * self.valid_tokens * TOKEN_BYTES

    def validate(self):
        require(uint(self.tag, 32), 'job tag domain')
        require(type(self.dtype) is str and self.dtype == 'bf16', 'BF16 dtype required')
        require(type(self.capacity) is int and self.capacity == CAPACITY,
                'Qwen3.5 KV capacity must be 256 tokens')
        require(type(self.tokens) is int and 1 <= self.tokens <= 128 and
                type(self.previous_tokens) is int and 0 <= self.previous_tokens <= self.capacity and
                self.valid_tokens <= self.capacity, 'new/prefix length or capacity overflow')
        require(uint(self.expected_generation, 64) and uint(self.current_generation, 64) and
                self.expected_generation == self.current_generation and
                self.current_generation < (1 << 64) - 1, 'generation mismatch or overflow')
        require(uint(self.previous_k, 56) and uint(self.previous_v, 56), 'previous root domain')
        if self.previous_tokens:
            require(self.previous_v == self.previous_k + self.capacity * TOKEN_BYTES,
                    'previous V must follow the full K capacity')
            span(self.previous_k, 2 * self.capacity * TOKEN_BYTES)
        else:
            require(self.previous_k == self.previous_v == 0, 'cold prefix must have zero roots')
        span(self.staging_k, 2 * self.capacity * TOKEN_BYTES)
        for region in self.input_spans + self.output_spans:
            span(*region)
        for i, region in enumerate(self.input_spans):
            require(all(disjoint(region, prior) for prior in self.input_spans[:i]),
                    'input span alias')
        staging_reservation = (self.staging_k, 2 * self.capacity * TOKEN_BYTES)
        require(all(disjoint(staging_reservation, region) for region in self.input_spans),
                'staging/input span alias')
        if self.previous_tokens:
            old_reservation = (self.previous_k, 2 * self.capacity * TOKEN_BYTES)
            require(disjoint(staging_reservation, old_reservation) and
                    all(disjoint(old_reservation, region) for region in self.input_spans[-2:]),
                    'previous capacity reservation alias')


@dataclass(frozen=True)
class MemoryRequest:
    address: int
    tag: int
    data: bytes | None = None

    @property
    def write(self):
        return self.data is not None

    @property
    def mask(self):
        return FULL_MASK if self.write else 0

    @property
    def nbytes(self):
        return BEAT_BYTES


@dataclass(frozen=True)
class MemoryResponse:
    tag: int
    data: bytes = b''
    error: bool = False
    nbytes: int = BEAT_BYTES


@dataclass(frozen=True)
class KvCacheResult:
    tag: int
    status: str | None
    write_bytes: int
    valid_tokens: int
    current_generation: int
    model_ticks: int


class KvCacheOwner:
    """Single outstanding read or write with a held terminal and abort drain."""
    def __init__(self):
        self.state, self.poison = 'idle', False
        self.job = self.request = self.result = self.program = None
        self.status = None
        self.ticks = self.start = self.sequence = self.ack_bytes = 0
        self.counts = Counter()

    def ports(self):
        return dict(job_ready=self.state == 'idle' and not self.poison,
                    memory=self.request if self.state == 'issue' else None,
                    memory_response_ready=self.state in ('wait', 'drain'),
                    response=self.result if self.state == 'finish' else None,
                    state=self.state, reset_required=self.poison)

    def reset(self):
        require(self.state in ('idle', 'locked') and self.request is None,
                'reset requires drained transport and retired held completion')
        self.__init__()

    def _copy(self, source, destination, nbytes):
        for offset in range(0, nbytes, BEAT_BYTES):
            beat = yield source + offset, None
            yield destination + offset, beat

    def _execute(self, job):
        # Fully finish K before V so the final V ACK tests the atomic fence.
        for previous, new, destination in ((job.previous_k, job.new_k, job.staging_k),
                                            (job.previous_v, job.new_v, job.staging_v)):
            if job.previous_tokens:
                yield from self._copy(previous, destination, job.previous_tokens * TOKEN_BYTES)
            yield from self._copy(new, destination + job.previous_tokens * TOKEN_BYTES,
                                  job.tokens * TOKEN_BYTES)

    def _finish(self, status=None):
        self.status, self.poison = status, self.poison or status is not None
        self.request = self.program = None
        self.result = KvCacheResult(self.job.tag, status, self.ack_bytes,
                                    self.job.valid_tokens if status is None else 0,
                                    self.job.current_generation, self.ticks - self.start)
        self.state = 'finish'

    def _advance(self, data=None):
        try:
            address, output = self.program.send(data)
        except StopIteration:
            self._finish(None if self.ack_bytes == self.job.write_bytes else 'Protocol')
            return
        require(self.sequence < 1 << 32, 'memory sequence exhausted')
        self.request = MemoryRequest(address, (self.job.tag << 32) | self.sequence, output)
        self.sequence += 1
        self.state = 'issue'

    def tick(self, *, job=None, memory_ready=False, memory_response=None,
             response_ready=False, abort=False, reset=False):
        require(all(type(v) is bool for v in (memory_ready, response_ready, abort, reset)),
                'boolean owner controls required')
        ports = self.ports()
        ports.update(job_fire=False, memory_fire=False, memory_response_fire=False, response_fire=False)
        if reset and self.state == 'finish':
            raise ValueError('typed KV: reset cannot erase a held completion')
        self.ticks += 1
        if reset and self.state in ('idle', 'locked'):
            self.reset()
            ports['job_ready'] = False
            return ports
        fault = abort or reset
        if fault:
            ports['job_ready'], ports['memory'] = False, None
            self.poison = True
            if self.state in ('wait', 'drain'):
                self.status, self.state = 'Aborted', 'drain'
            elif self.state == 'issue':
                self._finish('Aborted')
            elif self.state == 'finish' and self.status is None:
                self._finish('Aborted')
                ports['response'] = None
            elif self.state == 'idle':
                self.state = 'locked'
        if not fault and job is not None and ports['job_ready']:
            require(type(job) is KvCacheJob, 'immutable KV job required')
            job.validate()
            ports['job_fire'] = True
            self.job, self.start = job, self.ticks
            self.sequence, self.ack_bytes, self.status = 0, 0, None
            self.counts = Counter()
            self.program = self._execute(job)
            self._advance()
        if not fault and ports['memory'] is not None and memory_ready:
            ports['memory_fire'] = True
            self.counts['write_requests' if self.request.write else 'read_requests'] += 1
            self.state = 'wait'
        if ports['memory_response_ready'] and memory_response is not None:
            ports['memory_response_fire'] = True
            request, response = self.request, memory_response
            self.counts['memory_responses'] += 1
            valid = (type(response) is MemoryResponse and type(response.tag) is int and
                     response.tag == request.tag and type(response.nbytes) is int and
                     response.nbytes == BEAT_BYTES and type(response.error) is bool)
            status = 'Protocol' if not valid else 'Memory' if response.error else None
            if request.write and status is None:
                self.ack_bytes += BEAT_BYTES
                self.counts['write_acks'] += 1
            if self.state == 'drain':
                self._finish(self.status)
            elif status is not None:
                self._finish(status)
            elif request.write:
                self._advance()
            elif type(response.data) is not bytes or len(response.data) != BEAT_BYTES:
                self._finish('Protocol')
            else:
                self._advance(response.data)
        if ports['response'] is not None and response_ready:
            ports['response_fire'] = True
            self.counts['owner_results'] += 1
            self.state = 'locked' if self.poison else 'idle'
            self.result = None
        return ports

    def report(self):
        return dict(scope='KV_COPY_APPEND_SOFTWARE_OWNER', status=self.status,
                    accepted=dict(self.counts), acknowledged_write_bytes=self.ack_bytes,
                    current_generation=None if self.job is None else self.job.current_generation,
                    generation_advanced=False, arithmetic_resources=0, retained_data_bytes=BEAT_BYTES,
                    hardware_cycles=None, rtl_executed=False, native_acceptance=False,
                    fullblock_executed=False, physical_bank_allocation_proven=False)
