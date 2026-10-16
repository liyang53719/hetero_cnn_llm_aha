"""Bounded observation storage for unchanged Attention arithmetic services.

Standard-library imports only. Observer factories never import or instantiate
an arithmetic service themselves. Hashes prove ordered observation equality,
not independent arithmetic correctness or hardware timing. All byte encodings
are versioned, little-endian, and reject noncanonical integer/boolean fields.
"""
import hashlib
import struct


VERSION = 'raw-kv-stream-v1'
OPS = {'add': 0, 'mul': 1, 'div': 2, 'sqrt': 3, 'bf': 4}
POLICIES = {'vector': 0, 'legacy_scalar': 1}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def uint(value, bits):
    return type(value) is int and 0 <= value < 1 << bits


class Digest:
    def __init__(self, kind):
        self.kind, self.count, self.byte_count = kind, 0, 0
        self._hash = hashlib.sha256((VERSION + ':' + kind + '\0').encode('ascii'))

    def _record(self, *parts):
        for part in parts:
            self._hash.update(part)
            self.byte_count += len(part)
        self.count += 1

    def __len__(self):
        return self.count

    def report(self):
        return dict(version=VERSION, kind=self.kind, count=self.count,
                    bytes=self.byte_count, sha256=self._hash.hexdigest())


class ScalarDigest(Digest):
    def __init__(self):
        super().__init__('scalar')

    def append(self, event):
        require(type(event) is tuple and len(event) == 5, 'scalar event tuple')
        operation, x, y, result, policy = event
        require(type(operation) is str and operation in OPS, 'scalar operation')
        require(type(policy) is str and policy in POLICIES, 'scalar policy')
        require(all(uint(v, 32) for v in (x, y, result)), 'scalar uint32 words')
        self._record(struct.pack('<BBIII', OPS[operation], POLICIES[policy], x, y, result))


class CoreDigest(Digest):
    """Append-compatible sink for (full tag, address, write) metadata."""
    def __init__(self):
        super().__init__('core-metadata')

    def append(self, event):
        require(type(event) is tuple and len(event) == 3, 'core metadata tuple')
        tag, address, write = event
        require(uint(tag, 64) and uint(address, 64) and type(write) is bool,
                'canonical core metadata')
        self._record(struct.pack('<QQB', tag, address, write))


class AddressDigest(Digest):
    def __init__(self):
        super().__init__('addresses')

    def append(self, address):
        require(uint(address, 64), 'canonical address')
        self._record(struct.pack('<Q', address))


class MemoryDigest(Digest):
    """Original Bus.trace sink, including every accepted write payload byte."""
    def __init__(self, *, write_callback=None):
        super().__init__('memory-requests')
        self.metadata = CoreDigest()
        self.write_callback = write_callback
        self.read_count = self.write_count = 0

    def append(self, request):
        tag, address, write = request.tag, request.address, request.write
        require(uint(tag, 64) and uint(address, 64) and address % 64 == 0 and
                type(write) is bool and uint(request.mask, 64), 'canonical memory request')
        if write:
            require(type(request.data) is bytes and len(request.data) == 64 and
                    request.mask == (1 << 64) - 1, 'complete write packet')
            payload = request.data
        else:
            require(request.data is None and request.mask == 0, 'payload-free read request')
            payload = b''
        self.metadata.append((tag, address, write))
        self._record(struct.pack('<QQBQB', tag, address, write, request.mask, len(payload)), payload)
        if write:
            self.write_count += 1
            if self.write_callback is not None:
                self.write_callback(request)
        else:
            self.read_count += 1

    def report(self):
        return dict(super().report(), reads=self.read_count, writes=self.write_count,
                    metadata=self.metadata.report())


class MatrixDigest(Digest):
    """All 4096 result words; transport tickets are validated by the service.

    Tickets/epochs are deliberately outside this equality hash because fresh
    direct/loan runs may have different monotonic transport identities.
    """
    def __init__(self):
        super().__init__('matrix-results')

    def append(self, raw, *, opcode, index, context, last, error):
        require(type(raw) is bytes and len(raw) == 16384, 'complete 16 KiB Matrix result')
        require(all(uint(v, 32) for v in (opcode, index, context)) and
                type(last) is bool and type(error) is bool, 'canonical Matrix metadata')
        self._record(struct.pack('<IIIBB', opcode, index, context, last, error), raw)


def make_observers(ScalarService, MatrixService):
    """Return subclasses that observe successful original calls unchanged.

    Callbacks run after the original operation and after the digest update;
    they are diagnostics only and must not mutate the owner or service. No
    result, reply, ACK, done, reset, or owner-release handshake is synthesized.
    """
    class StreamingScalar(ScalarService):
        def __init__(self, *args, observer_callback=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.stream = ScalarDigest()
            self.observer_callback = observer_callback
            self.observer_failures = 0

        def op(self, client, operation, x, y=0, *, policy='vector'):
            try:
                result = super().op(client, operation, x, y, policy=policy)
            except Exception:
                self.observer_failures += 1
                raise
            self.stream.append((operation, x, y, result, policy))
            if self.observer_callback is not None:
                self.observer_callback((operation, x, y, result, policy))
            return result

    class StreamingMatrix(MatrixService):
        def __init__(self, *args, observer_callback=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.stream = MatrixDigest()
            self.observer_callback = observer_callback
            self.observed_accepted_steps = 0

        def accept_step(self, owner, step):
            accepted = super().accept_step(owner, step)
            if accepted:
                self.observed_accepted_steps += 1
                result = self.result
                if result is not None:
                    self.stream.append(result.value.raw, opcode=self.group.opcode,
                                       index=step.index, context=result.context,
                                       last=result.last, error=result.error)
                    if self.observer_callback is not None:
                        self.observer_callback(owner, step, result)
            return accepted

    return StreamingScalar, StreamingMatrix


def profile(tokens):
    """Exact clean causal counts; scalar totals assume no exp cutoff at 80.

    The M4/M8/M128 fixture with |Q|,|K|<=1 meets that assumption. The event cap
    is a conservative handshake budget, never a cycle estimate or wall bound.
    """
    require(type(tokens) is int and 1 <= tokens <= 128, 'M1..128 profile')
    rows = 12 * tokens
    pairs = 12 * tokens * (tokens + 1) // 2
    packets = 16 * pairs
    groups = pairs + 8 * rows
    q_reads = writes = 8 * rows
    unique = 32 * tokens
    scalar = dict(bf=32 * packets + 2 * pairs + 128 * rows,
                  add=26 * pairs, mul=18 * pairs, div=rows)
    return dict(tokens=tokens, rows=rows, causal_pairs=pairs,
                q_reads=q_reads, kv_reads=packets, output_writes=writes,
                core_memory_requests=packets + q_reads + writes,
                unique_kv_lines=unique, kv_hits=packets - unique,
                loan_ddr_reads=q_reads + unique,
                matrix_packets=packets, matrix_groups=groups,
                useful_fmas=16 * packets, native_fmas=512 * packets,
                scalar_counts_no_cutoff=scalar, scalar_total_no_cutoff=sum(scalar.values()),
                matrix_snapshot_bytes=16384 * packets, group_clear_bytes=81920 * groups,
                model_event_cap=16 * packets + 8 * (q_reads + writes + unique + groups) + 1024,
                hardware_cycles=False)

