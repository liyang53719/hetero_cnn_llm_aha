"""Source-bound legacy Qwen2 Norm/Bias/RoPE/KV prefix transaction model.

Only accepted 64-byte DDR response words feed arithmetic. There is no tensor
store or reference injection in this owner. The caller services this port from
the same physical memory used by Dense/FFN and only makes stores readable on a
matching successful write ACK. Host publication still belongs to HostControl.

The generator collapses internal scalar/local-SRAM scheduling while preserving
ordered rounding nodes, memory operands, request stalls and ACK fences. Its
ticks are software handshake events, never Chisel execution or hardware cycles.
"""
from collections import Counter
from dataclasses import dataclass
import struct

from .prefix_arithmetic import ArithmeticFault, NATIVE_ACCEPTANCE, ScalarService, finite, word

BEAT_BYTES, LANES, FULL_MASK, LIMIT = 64, 16, (1 << 64) - 1, 1 << 56


@dataclass(frozen=True)
class Job:
    kind: str
    tag: int
    a: int
    b: int
    dst: int
    m: int
    n: int
    k: int
    write_bytes: int
    c: int = 0
    weight_bf16: bool = False
    activation_bf16: bool = False
    output_bf16: bool = False


@dataclass(frozen=True)
class MemoryRequest:
    address: int
    tag: int
    write: bool = False
    data: bytes | None = None
    mask: int = 0

    @property
    def words(self):
        return None if self.data is None else struct.unpack('<16I', self.data)


@dataclass(frozen=True)
class MemoryResponse:
    tag: int
    data: bytes | tuple | None = None
    error: bool = False
    nbytes: int = BEAT_BYTES


@dataclass(frozen=True)
class OwnerResult:
    tag: int
    status: str | None
    write_bytes: int
    cycles: int  # Host ABI field: software event ticks, explicitly NOT cycles.
    useful_macs: int = 0
    executed_macs: int = 0


class PrefixFault(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail
        super().__init__(detail)


def uint(number, bits):
    return type(number) is int and 0 <= number < 1 << bits


class PrefixOwner:
    """One serial owner over one shared ScalarService and one memory port.

    Source map (hash checked in prefix_arithmetic.py):
      Qwen2Block.scala:115-121,289-304: Norm row retained in SharedL2Fabric,
      localRows=ceil(maxRow*denseBatch*4/256), row indices col/16. This software
      subset retains exactly hidden FP32 words, H1536 = 6144 bytes, plus bounded
      16-lane packets. This does NOT prove physical bank allocation or occupancy.
      Qwen2Block.scala:426-437: four input vectors av,bv,cv,dv, FP32 RoPE nodes.
      Qwen2Block.scala:488-491: two input packets and FP32 Bias addition.
      Qwen2Block.scala:182-194,476-484 + ElementwiseMemoryEngine.scala:68-97:
      two ordered Copy jobs, each tiled by ChainConfig.tileElements=1024.
      Only one 1024-word software copy tile is needed; the source engine uses
      three bounded canonical buffers. No extra hardware or ports are claimed.
    """
    KINDS = ('Norm', 'Bias', 'Rope', 'KvAppend')

    def __init__(self, scalar=None, *, hidden=1536, kv=256, head_dim=128,
                 max_tokens=1024):
        if (hidden != 1536 or kv != 256 or head_dim != 128
                or not uint(max_tokens, 16) or not 0 < max_tokens <= 1024):
            raise ValueError('prefix shape is source Qwen2 H1536/KV256/HD128')
        self.scalar = scalar if scalar is not None else ScalarService()
        self.hidden, self.kv, self.head_dim, self.max_tokens = hidden, kv, head_dim, max_tokens
        self.state, self.poison, self.job = 'idle', False, None
        self.request = self.result = self.program = None
        self.status = self.detail = None
        self.serial = self.clock = self.start_clock = self.ack_bytes = 0
        self.counts = Counter()
        self.scalar_baseline = Counter()
        self.scalar_counts = Counter()
        self.tag_prefix = 0
        self.row_words = self.peak_row_words = self.peak_copy_words = 0

    def ports(self):
        return dict(job_ready=self.state == 'idle' and not self.poison and self.scalar.client is None,
                    memory=self.request if self.state == 'issue' else None,
                    memory_response_ready=self.state in ('wait', 'drain'),
                    response_ready=self.state in ('wait', 'drain'),
                    response=self.result if self.state == 'finish' else None,
                    reset_required=self.poison, state=self.state)

    def _validate(self, job):
        if (job.kind not in self.KINDS or any(getattr(job, name, False) for name in
                ('weight_bf16', 'activation_bf16', 'output_bf16'))):
            raise PrefixFault('Unsupported', 'legacy v0 prefix requires FP32 containers')
        if not (uint(job.tag, 32) and uint(job.m, 16) and 0 < job.m <= self.max_tokens
                and job.n == job.k and job.n in (self.hidden, self.kv)):
            raise PrefixFault('Bounds', 'normalized legacy prefix dimensions/tag')
        if job.kind == 'Norm' and job.n != self.hidden:
            raise PrefixFault('Bounds', 'Norm is fixed hidden width')
        if job.kind == 'KvAppend' and job.n != self.kv:
            raise PrefixFault('Bounds', 'KvAppend is fixed KV width')
        expected = job.m * job.n * 4 * (2 if job.kind == 'KvAppend' else 1)
        if job.write_bytes != expected:
            raise PrefixFault('Bounds', 'write_bytes differs from physical output extent')
        inputs = [(job.a, job.m * job.n * 4)]
        if job.kind in ('Norm', 'Bias'):
            inputs.append((job.b, job.n * 4))
        elif job.kind == 'KvAppend':
            inputs.append((job.b, job.m * job.n * 4))
        else:
            trig_bytes = self.max_tokens * (self.head_dim // 2) * 4
            if getattr(job, 'c', 0) != job.b + trig_bytes:
                raise PrefixFault('Bounds', 'RoPE sine half must use source maxTokens offset')
            inputs.extend(((job.b, trig_bytes), (job.c, trig_bytes)))
        for address, extent in inputs + [(job.dst, expected)]:
            if not (uint(address, 64) and address % 64 == 0 and address + extent <= LIMIT):
                raise PrefixFault('Bounds', 'unaligned/overflowing physical prefix span')
        if any(start < job.dst + expected and job.dst < start + size for start, size in inputs):
            raise PrefixFault('Permission', 'prefix destination overlaps source')

    def _op(self, operation, a, b=0, *, policy='vector'):
        return self.scalar.op(self, operation, a, b, policy=policy)

    def _read(self, address):
        words = yield (address, None)
        return words

    def _write(self, address, words):
        words = tuple(words)
        if len(words) != LANES or any(not finite(v) for v in words):
            raise PrefixFault('Numerical', 'nonfinite prefix store')
        yield (address, struct.pack('<16I', *words))

    def _norm(self, j):
        for token in range(j.m):
            row, total = [], 0
            for col in range(0, self.hidden, LANES):
                packet = yield from self._read(j.a + (token * self.hidden + col) * 4)
                row.extend(packet)
                self.row_words = len(row)
                self.peak_row_words = max(self.peak_row_words, len(row))
                squares = tuple(self._op('mul', x, x) for x in packet)
                for square in squares:
                    total = self._op('add', total, square, policy='legacy_scalar')
            mean = self._op('mul', total, word(1.0 / self.hidden), policy='legacy_scalar')
            epsilon = self._op('add', mean, word(1e-6), policy='legacy_scalar')
            root = self._op('sqrt', epsilon, policy='legacy_scalar')
            scale = self._op('div', word(1.0), root, policy='legacy_scalar')
            for col in range(0, self.hidden, LANES):
                gamma = yield from self._read(j.b + col * 4)
                scaled = tuple(self._op('mul', row[col + i], scale) for i in range(LANES))
                output = tuple(self._op('bf', self._op('mul', scaled[i], gamma[i]))
                               for i in range(LANES))
                yield from self._write(j.dst + (token * self.hidden + col) * 4, output)
            self.row_words = 0

    def _bias(self, j):
        for token in range(j.m):
            for col in range(0, j.n, LANES):
                index = (token * j.n + col) * 4
                a = yield from self._read(j.a + index)
                b = yield from self._read(j.b + col * 4)
                yield from self._write(j.dst + index,
                                       (self._op('add', x, y) for x, y in zip(a, b)))

    def _rope(self, j):
        half = self.head_dim // 2
        for token in range(j.m):
            for head in range(j.n // self.head_dim):
                for col in range(0, half, LANES):
                    index = (token * j.n + head * self.head_dim + col) * 4
                    trig_index = (token * half + col) * 4
                    x = yield from self._read(j.a + index)
                    y = yield from self._read(j.a + index + half * 4)
                    cosine = yield from self._read(j.b + trig_index)
                    sine = yield from self._read(j.c + trig_index)
                    xc = tuple(self._op('mul', a, b) for a, b in zip(x, cosine))
                    ys = tuple(self._op('mul', a, b) for a, b in zip(y, sine))
                    low = tuple(self._op('add', a, b ^ 0x80000000) for a, b in zip(xc, ys))
                    xs = tuple(self._op('mul', a, b) for a, b in zip(x, sine))
                    yc = tuple(self._op('mul', a, b) for a, b in zip(y, cosine))
                    yield from self._write(j.dst + index, low)
                    high = tuple(self._op('add', a, b) for a, b in zip(xs, yc))
                    yield from self._write(j.dst + index + half * 4, high)

    def _append(self, j):
        elements, tile_elements = j.m * j.n, 1024
        for half, source in enumerate((j.a, j.b)):
            # Each source Copy is an ElementwiseMemoryEngine job. Its source
            # tag is Cat(epoch, phase=16), and seq restarts for the second half.
            self.serial = 0
            for base in range(0, elements, tile_elements):
                count = min(tile_elements, elements - base)
                tile = []
                for offset in range(0, count, LANES):
                    tile.extend((yield from self._read(source + (base + offset) * 4)))
                self.peak_copy_words = max(self.peak_copy_words, len(tile))
                # ElementwiseMemoryEngine calculates/checks the complete tile
                # before entering its output loop; a bad later lane must not
                # leak earlier stores from that same copy tile.
                if any(not finite(value) for value in tile):
                    raise PrefixFault('Numerical', 'nonfinite Elementwise Copy tile')
                for offset in range(0, count, LANES):
                    yield from self._write(j.dst + (half * elements + base + offset) * 4,
                                           tile[offset:offset + LANES])

    def _finish(self, status=None, detail=None):
        self.status, self.detail = status, detail
        self.poison = self.poison or status is not None
        if self.scalar.client is self:
            self.scalar_counts = self.scalar.calls - self.scalar_baseline
            self.scalar.release(self)
        self.program, self.request, self.row_words = None, None, 0
        self.result = OwnerResult(self.job.tag, status, self.ack_bytes, self.clock - self.start_clock)
        self.state = 'finish'

    def _advance(self, response=None):
        try:
            address, data = self.program.send(response)
            if self.serial == 1 << 32:
                raise PrefixFault('Protocol', 'prefix request sequence exhausted')
            # Block read/write: Cat(epoch.pad(32),seq). KV copies use the
            # ElementwiseMemoryEngine tag described in _append above.
            self.request = MemoryRequest(address, (self.tag_prefix << 32) | self.serial,
                                         data is not None, data, FULL_MASK if data is not None else 0)
            self.serial += 1
            self.state = 'issue'
        except StopIteration:
            if self.ack_bytes != self.job.write_bytes:
                self._finish('Protocol', 'terminal before exact write ACK byte fence')
            else:
                self._finish()
        except PrefixFault as error:
            self._finish(error.status, error.detail)
        except ArithmeticFault as error:
            self._finish('Numerical', str(error))

    def tick(self, *, job=None, memory_ready=False, memory_response=None,
             response_ready=False, local_reset=False, reset=False):
        """One event edge. Reset cannot erase a previously accepted transaction.

        A local fault or reset during wait drains that response and returns one
        rejected owner result. Once quiescent, reset clears quarantine. Offered
        responses are consumed only while memory_response_ready was asserted.
        """
        p = self.ports()
        p.update(job_fire=False, memory_fire=False, memory_response_fire=False,
                 response_fire=False)
        self.clock += 1
        if reset and self.state in ('idle', 'finish', 'locked'):
            if self.scalar.client is self:
                self.scalar.release(self)
            self.__init__(self.scalar, hidden=self.hidden, kv=self.kv,
                          head_dim=self.head_dim, max_tokens=self.max_tokens)
            p['job_ready'] = False
            return p
        fault = local_reset or reset
        if fault:
            self.poison = True
            p['job_ready'] = False
            if self.state in ('wait', 'drain'):
                self.status, self.detail, self.state = 'Protocol', 'reset while active', 'drain'
            elif self.state == 'finish':
                self._finish('Protocol', 'reset before result acceptance')
                p['response'] = None
            elif self.state == 'idle':
                self.state = 'locked'
            elif self.state != 'locked':
                self._finish('Protocol', 'reset while active')
            # Suppress acceptance of an offered but not accepted memory request.
            p['memory'] = None
        if not fault and job is not None and p['job_ready']:
            p['job_fire'] = True
            self.job, self.start_clock = job, self.clock
            self.ack_bytes = self.serial = 0
            self.counts = Counter(job_fire=1)
            self.scalar_baseline = self.scalar.calls.copy()
            self.scalar_counts = Counter()
            self.tag_prefix = ((job.tag >> 16) << 16) | 16 if job.kind == 'KvAppend' else job.tag >> 16
            self.peak_row_words = self.peak_copy_words = 0
            try:
                self._validate(job)
                if not self.scalar.acquire(self):
                    raise PrefixFault('Protocol', 'shared scalar resource admission mismatch')
                self.program = {'Norm': self._norm, 'Bias': self._bias,
                                'Rope': self._rope, 'KvAppend': self._append}[job.kind](job)
                self._advance()
            except PrefixFault as error:
                self._finish(error.status, error.detail)
        if not fault and p['memory'] is not None and memory_ready:
            p['memory_fire'] = True
            self.counts['write_requests' if self.request.write else 'read_requests'] += 1
            self.state = 'wait'
        if p['memory_response_ready'] and memory_response is not None:
            p['memory_response_fire'] = True
            q, r = self.request, memory_response
            self.counts['memory_responses'] += 1
            status = 'Protocol' if r.tag != q.tag or r.nbytes != BEAT_BYTES else 'Memory' if r.error else None
            if status is None and q.write:
                self.ack_bytes += BEAT_BYTES
                self.counts['write_acks'] += 1
            if self.state == 'drain':
                self._finish(self.status, self.detail)
            elif status is not None:
                self._finish(status, 'memory response tag/error/byte count')
            elif q.write:
                self._advance()
            else:
                data = r.data
                if isinstance(data, bytes) and len(data) == BEAT_BYTES:
                    data = struct.unpack('<16I', data)
                if not isinstance(data, tuple) or len(data) != LANES or not all(uint(v, 32) for v in data):
                    self._finish('Protocol', 'read response must be exactly 16 FP32 words')
                else:
                    self.counts['read_responses'] += 1
                    self._advance(data)
        if p['response'] is not None and response_ready:
            p['response_fire'] = True
            self.counts['owner_results'] += 1
            self.state = 'locked' if self.poison else 'idle'
            self.result = None
        return p

    def report(self):
        return dict(kind=None if self.job is None else self.job.kind, status=self.status,
            accepted=dict(self.counts), acknowledged_write_bytes=self.ack_bytes,
            scalar_primitive_calls=dict(self.scalar_counts if self.state in ('finish', 'idle', 'locked')
                                        else self.scalar.calls - self.scalar_baseline),
            row_buffer_capacity_words=self.hidden, peak_row_buffer_words=self.peak_row_words,
            copy_tile_capacity_words=1024, peak_copy_tile_words=self.peak_copy_words,
            local_array_is_physical_bank_allocation_evidence=False,
            one_shared_scalar_software_service=True, hardware_instances_added=0,
            hardware_simulation=False, model_ticks_are_hardware_cycles=False,
            native_acceptance=NATIVE_ACCEPTANCE)
