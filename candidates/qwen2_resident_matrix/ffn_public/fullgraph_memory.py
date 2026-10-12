"""Names-only FFN views and versioned workspace in the public address index.

No operand, output, or prefix copy is installed here. Destination views share
PhysicalMemory's exact bytearray. Workspace storage is registered once in that
same index; its transport has a mutable, ACK/read/seed lifecycle instead of the
ordinary output publication lifecycle. ``raw``/``read64`` on its region view
are explicitly forensic driver audits, never accepted port reads.
"""
from collections import Counter
import hashlib
import struct

BEAT_BYTES = GUARD_BYTES = 64
CONTEXT_BYTES = 16384
FULL_MASK = (1 << 64) - 1
SENTINEL = struct.pack('<I', 0xa5963cc3)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SharedDestination:
    """DestinationMemory-compatible act sink, with no independent allocation."""
    def __init__(self, physical, name='act'):
        self.physical_memory, self.name = physical, name
        r = physical.regions[name]
        require(not r['readonly'] and not r['virtual'] and r['dtype'] == 7,
                'shared act must be a physical FP32 writable allocation')
        self.base, self.extent = r['base'], r['extent']
        self.data = r['data']
        self.rows, self.width = physical.fixture.allocations[name].shape
        self.initial = SENTINEL * ((self.extent + 2 * GUARD_BYTES) // 4)
        self.descriptors = self.acks = 0
        self.last_tag = None

    @property
    def region(self):
        name, r = self.physical_memory.region(self.base, self.extent)
        require(name == self.name and r['data'] is self.data, 'shared act allocation replaced')
        return r

    @property
    def pending(self):
        pending = self.physical_memory.pending
        return pending[1] if pending is not None and pending[0] == self.name else None

    @property
    def next_beat(self):
        return self.physical_memory.pending[2] if self.pending is not None else 0

    @property
    def data_bytes(self):
        return len(self.region['written']) * BEAT_BYTES

    @property
    def ack_bytes(self):
        return len(self.region['acked']) * BEAT_BYTES

    @property
    def write_addresses(self):
        return self.region['written']

    @property
    def awaiting_ack(self):
        return self.pending is not None and self.next_beat == self.pending.beats

    def accept_command(self, command):
        name, r = self.physical_memory.region(command.address, command.beats * BEAT_BYTES)
        require(name == self.name and r is self.region, 'act descriptor escaped shared act allocation')
        require(type(command.tag) is int and 0 <= command.tag < 1 << 64 and
                (self.last_tag is None or command.tag == self.last_tag + 1),
                'act write sequence/tag discontinuity')
        self.physical_memory.write_event('command', command)
        self.last_tag = command.tag
        self.descriptors += 1

    def accept_data(self, beat):
        require(self.pending is not None, 'act data without accepted command')
        address = self.pending.address + self.next_beat * BEAT_BYTES
        self.physical_memory.write_event('data', beat)
        return address

    def accept_ack(self, ack):
        require(self.awaiting_ack, 'act ACK before all write data')
        self.physical_memory.write_event('ack', ack)
        self.acks += 1

    def read64(self, address):
        name, words = self.physical_memory.read64(address)
        require(name == self.name, 'act read escaped shared act allocation')
        return words

    def validate_full(self):
        """Audit actual ACK-written bytes; this does not publish port access."""
        r = self.region
        require(self.physical_memory.pending is None and self.acks == self.descriptors and
                self.data_bytes == self.ack_bytes == self.extent and
                r['written'] == r['acked'] == set(range(self.base, self.base + self.extent, 64)),
                'shared act final exactly-once ACK/byte fence')
        require(self.data[:64] == self.data[-64:] == SENTINEL * 16, 'shared act guard corruption')
        raw = self.physical_memory.raw(self.base, self.extent)
        return raw, dict(bytes=self.extent, ack_bytes=self.ack_bytes, descriptors=self.descriptors,
                         acks=self.acks, unique_write_beats=len(self.write_addresses),
                         canaries_exact=True, sha256=sha(raw))


class WorkspaceRegion:
    """Active-prefix audit view into the full shared workspace allocation.

    ``data`` includes both guards and the inactive tail. The tail is not a
    second allocation or an active-view guard. Actual transport uses the
    owning SharedWorkspace methods, not these forensic reads.
    """
    def __init__(self, workspace, extent):
        self.workspace, self.base, self.extent = workspace, workspace.base, extent
        self.data, self.guard = workspace.data, SENTINEL * 16
        self.initial_sha256 = sha(self.raw())

    def contains(self, address, size=64):
        return (type(address) is int and type(size) is int and size > 0 and
                self.base <= address and address + size <= self.base + self.extent)

    def offset(self, address):
        require(self.contains(address) and address % 64 == 0, 'workspace audit outside active span')
        self.workspace._region(address)
        return 64 + address - self.base

    def read64(self, address):
        """Audit only: may inspect data before ACK; never a port publication."""
        return struct.unpack_from('<16I', self.data, self.offset(address))

    def raw(self):
        self.workspace._region(self.base, max(self.extent, 64))
        return bytes(self.data[64:64 + self.extent])

    def write64(self, address, words):
        raise ValueError('workspace mutation requires accepted command/data/ACK transport')

    def check_guards(self):
        self.workspace.check_guards()


class SharedWorkspace:
    """One reusable physical prefix span with actual per-version obligations.

    A job lease is tied to the public epoch/generation and physical reservation.
    New versions need actual write data and ACK. Accepted reads and seed beats
    must consume that version exactly once; every seed ACK in the current
    Matrix group must retire before its bytes may be overwritten. A fault
    invalidates read/admission authority immediately while preserving accepted
    transactions for draining. An invalidated lease cannot be reused.
    """
    def __init__(self, physical):
        self.physical_memory = physical
        config = physical.fixture.config
        config.validate()
        reservation = config.regions[3]
        require(reservation.read and reservation.write, 'public workspace must be readable and writable')
        self.base, self.extent, self.epoch = reservation.base, reservation.limit - reservation.base, config.epoch
        require(self.extent > 0 and self.extent % 64 == 0, 'public workspace extent/alignment')
        require('workspace' not in physical.regions, 'workspace already registered in physical address index')
        require(all(self.base + self.extent <= r['base'] or
                    r['base'] + r['reserved'] <= self.base for r in physical.regions.values()),
                'public workspace overlaps physical allocation or metadata')
        self.data = bytearray(SENTINEL * ((self.extent + 128) // 4))
        self.region = dict(base=self.base, extent=self.extent, reserved=self.extent, dtype=7,
            readonly=False, virtual=False, provider=None, data=self.data, written=set(), acked=set(),
            records=[], terminal=False, published=False, workspace_transport=self)
        physical.regions['workspace'] = self.region
        self.job = self.reservation = self.view = self.group = None
        self.invalidated = None
        self.finished = False
        self.pending_read = None
        self.seeds = {}
        self.seed_commits = set()
        self.versions, self.data_versions = {}, {}
        self.read_versions, self.seed_versions = set(), set()
        self.counts = Counter()

    def _identity(self):
        config = self.physical_memory.fixture.config
        require(config.epoch == self.epoch and config.regions[3].base == self.base and
                config.regions[3].limit == self.base + self.extent and config.transposed_down and
                config.regions[3].read and config.regions[3].write,
                'public workspace configuration epoch/reservation changed')
        if self.reservation is not None:
            require(self.reservation.base == self.base and self.reservation.extent == self.extent and
                    self.reservation.generation == self.epoch + 1,
                    'workspace generation/reservation changed')

    def _region(self, address, size=64):
        name, r = self.physical_memory.region(address, size)
        require(name == 'workspace' and r is self.region and r['data'] is self.data,
                'shared workspace allocation replaced or address escaped')
        return r

    def _live(self):
        self._identity()
        require(self.job is not None and not self.finished and self.invalidated is None,
                'workspace lease is inactive, finished or invalidated')

    def begin(self, job, reservation):
        self._identity()
        require(self.job is None and self.invalidated is None and self.physical_memory.pending is None,
                'workspace lease already used or physical transaction outstanding')
        reservation.validate(job)
        require(reservation.base == self.base and reservation.extent == self.extent and
                reservation.generation == self.epoch + 1,
                'workspace differs from full public reservation/epoch generation')
        require(job.n > 0 and job.n % 32 == 0 and job.k > 0, 'workspace Dense geometry')
        self.final_chunk = (job.k - 1) // reservation.split_k
        active_extent = job.n // 32 * CONTEXT_BYTES if self.final_chunk else 0
        require(active_extent <= self.extent, 'workspace active prefix exceeds public reservation')
        self.job, self.reservation = job, reservation
        self.view = WorkspaceRegion(self, active_extent)
        self.versions = {address: 0 for address in range(self.base, self.base + active_extent, 64)}
        self.data_versions = dict(self.versions)
        self.check_guards()
        require(self.data[64:-64] == SENTINEL * (self.extent // 4), 'initial public workspace not pristine')
        return self.view if active_extent else None

    def accept_group(self, chunk_index, n_base, contexts, sequence):
        self._live()
        require(self.drained and type(chunk_index) is int and 0 <= chunk_index <= self.final_chunk and
                n_base % 32 == 0 and 1 <= contexts <= 5 and n_base + contexts * 32 <= self.job.n,
                'workspace group geometry or outstanding transaction')
        if self.group is None:
            require(chunk_index == 0 and n_base == 0, 'workspace first group order')
        else:
            old_chunk, old_n, old_contexts, old_sequence = self.group
            next_n = old_n + old_contexts * 32
            expected = (old_chunk, next_n) if next_n < self.job.n else (old_chunk + 1, 0)
            require((chunk_index, n_base) == expected and sequence == old_sequence + 1,
                    'workspace group/chunk sequence discontinuity')
            if old_chunk < self.final_chunk:
                addresses = range(self.base + old_n // 32 * CONTEXT_BYTES,
                                  self.base + next_n // 32 * CONTEXT_BYTES, 64)
                require(all(self.versions[a] == self.data_versions[a] == old_chunk + 1 for a in addresses),
                        'workspace next group before prior group ACK coverage')
        if chunk_index and n_base == 0:
            require(all(v == chunk_index for v in self.versions.values()) and
                    self.versions == self.data_versions, 'workspace next sweep before complete version ACKs')
        self.group = chunk_index, n_base, contexts, sequence
        self.check_guards()
        self.counts['groups'] += 1

    @property
    def drained(self):
        pending = self.physical_memory.pending
        return (not (pending is not None and pending[0] == 'workspace') and
                self.pending_read is None and not self.seeds)

    def _context(self, address):
        require(self.view is not None and self.view.contains(address) and address % 64 == 0,
                'workspace transport outside active aligned span')
        self._region(address)
        require(self.group is not None, 'workspace transport before accepted group')
        context = (address - self.base) // CONTEXT_BYTES
        chunk, n_base, contexts, _ = self.group
        require(n_base // 32 <= context < n_base // 32 + contexts,
                'workspace address outside accepted Matrix group')
        return chunk, context

    def write_event(self, kind, value):
        """Consume accepted wire objects using PhysicalMemory's shared slot."""
        physical = self.physical_memory
        if kind == 'command':
            self._live()
            command = value
            require(physical.pending is None and command.beats == 1 and command.address % 64 == 0 and
                    type(command.tag) is int and 0 <= command.tag < 1 << 64,
                    'workspace command overlap/shape/tag')
            chunk, context = self._context(command.address)
            require(chunk < self.final_chunk and command.tag >> 32 == self.job.tag,
                    'workspace write after final chunk or wrong job tag')
            version = chunk + 1
            require(self.versions[command.address] == self.data_versions[command.address] == version - 1,
                    'workspace duplicate or skipped version write')
            if chunk:
                _, n_base, contexts, _ = self.group
                require(all((chunk, c) in self.seed_commits
                            for c in range(n_base // 32, n_base // 32 + contexts)) and
                        (command.address, chunk) in self.read_versions and
                        (command.address, chunk) in self.seed_versions,
                        'workspace overwrite before actual read and all group seed ACKs')
            physical.pending = ['workspace', command, 0]
            physical.counts['write_commands'] += 1
        elif kind == 'data':
            if self.invalidated is None:
                self._identity()
            pending = physical.pending
            require(pending is not None and pending[0] == 'workspace', 'workspace data without accepted command')
            _, command, index = pending
            from . import execute_numeric as execution
            implicit = type(value) is execution.numeric.model.down.WriteBeat
            mask = FULL_MASK if implicit else getattr(value, 'mask', None)
            require(index == 0 and mask == FULL_MASK and value.last is True and len(value.words) == 16 and
                    all(type(w) is int and 0 <= w < 1 << 32 for w in value.words),
                    'workspace write data mask/last/width')
            self._region(command.address)
            struct.pack_into('<16I', self.data, 64 + command.address - self.base, *value.words)
            self.data_versions[command.address] = self.group[0] + 1
            self.region['written'].add(command.address)
            physical.pending[2] = 1
            physical.counts['write_data_bytes'] += 64
            self.counts['write_data_bytes'] += 64
        elif kind == 'ack':
            pending = physical.pending
            require(pending is not None and pending[0] == 'workspace', 'workspace ACK without accepted command')
            _, command, index = pending
            require(index == 1 and value.tag == command.tag and value.nbytes == 64,
                    'workspace ACK identity/byte/data fence')
            require(not value.error or self.invalidated is not None, 'workspace error ACK requires invalidation')
            if self.invalidated is None:
                self._identity()
                self.versions[command.address] = self.data_versions[command.address]
                self.region['acked'].add(command.address)
                self.counts['valid_ack_bytes'] += 64
            self.region['records'].append((command, value))
            physical.pending = None
            physical.counts['write_ack_bytes'] += 64
            physical.counts['write_acks'] += 1
            self.counts['drained_ack_bytes'] += 64
        else:
            raise ValueError('unknown workspace write event')

    def accept_read(self, command):
        self._live()
        chunk, _ = self._context(command.address)
        require(command.beats == 1 and command.kind == 'prefix' and command.tag >> 32 == self.job.tag and
                self.pending_read is None and chunk > 0 and
                self.versions[command.address] == self.data_versions[command.address] == chunk and
                (command.address, chunk) not in self.read_versions,
                'workspace read before matching ACK version or duplicate accepted read')
        # Group zero is admitted only after the entire preceding sweep ACKs.
        words = self.view.read64(command.address)
        self.pending_read = command, chunk, words
        self.physical_memory.counts['read_bytes'] += 64
        self.physical_memory.read_regions['workspace'] += 64
        self.counts['read_commands'] += 1
        return words

    def retire_read(self, command, words):
        require(self.pending_read is not None and self.pending_read[0] == command and
                tuple(words) == self.pending_read[2], 'workspace read response identity/payload')
        _, version, _ = self.pending_read
        require(self.view.read64(command.address) == tuple(words), 'workspace changed before accepted read response')
        if self.invalidated is None:
            self._identity()
            self.read_versions.add((command.address, version))
        self.pending_read = None
        self.counts['read_responses'] += 1

    def _seed_context(self, request):
        require(self.group is not None, 'workspace seed before group')
        chunk, n_base, contexts, sequence = self.group
        require(chunk > 0 and request.tag == self.job.tag and request.sequence == sequence and
                request.generation == self.epoch + 1 and request.slice_mask == 255 and
                0 <= request.context < contexts, 'workspace seed identity/generation/context')
        return chunk, n_base // 32 + request.context

    def seed_begin(self, request):
        self._live()
        key = self._seed_context(request)
        require(key not in self.seed_commits and key not in self.seeds, 'duplicate workspace seed begin')
        self.seeds[key] = [request, set()]

    def seed_beat(self, address, request, words):
        self._live()
        key = self._seed_context(request)
        chunk, context = self._context(address)
        require(key == (chunk, context) and key in self.seeds and self.seeds[key][0] == request and
                address not in self.seeds[key][1] and (address, chunk) in self.read_versions and
                self.versions[address] == self.data_versions[address] == chunk and
                self.view.read64(address) == tuple(words),
                'workspace seed lacks exact actual read/version/payload')
        self.seeds[key][1].add(address)
        self.seed_versions.add((address, chunk))

    def seed_ack(self, ack):
        key = self._seed_context(ack.request)
        require(key in self.seeds and self.seeds[key][0] == ack.request,
                'workspace unsolicited or duplicate seed ACK')
        if self.invalidated is None:
            self._identity()
            start = self.base + key[1] * CONTEXT_BYTES
            require(not ack.error and self.seeds[key][1] == set(range(start, start + CONTEXT_BYTES, 64)),
                    'workspace seed ACK before all actual read/seed beats')
            self.seed_commits.add(key)
        del self.seeds[key]
        self.counts['seed_acks'] += 1

    def check_guards(self):
        self._region(self.base, self.extent)
        require(self.data[:64] == self.data[-64:] == SENTINEL * 16,
                'full public workspace guard corruption')
        active = self.view.extent if self.view is not None else 0
        require(self.data[64 + active:-64] == SENTINEL * ((self.extent - active) // 4),
                'inactive public workspace tail changed')

    def finish(self):
        self._live()
        require(self.drained and self.physical_memory.pending is None and self.group is not None and
                self.group[0] == self.final_chunk and self.group[1] + self.group[2] * 32 == self.job.n,
                'workspace finish before final group or accepted obligations drained')
        if self.final_chunk:
            expected = {(version, context) for version in range(1, self.final_chunk + 1)
                        for context in range(self.job.n // 32)}
            require(self.seed_commits == expected, 'workspace finish before all seed ACK versions')
        self.check_guards()
        self.finished = True

    def invalidate(self, reason):
        require(isinstance(reason, str) and bool(reason), 'workspace invalidation needs a reason')
        self.invalidated = reason
        # Accepted write/read/seed obligations retain their identity for drain;
        # no new read/group/command can use any previous version after this.
        self.region['published'] = self.region['terminal'] = False


class FullGraphMemory:
    """Compatibility labels only; every operand resolves the same physical map."""
    LABELS = {'wg': 'gate_weight', 'wu': 'up_weight', 'wd': 'down_weight'}

    def __init__(self, physical):
        self.physical_memory = physical
        self.act = SharedDestination(physical)
        self.workspace = SharedWorkspace(physical)
        self.virtual_hashes = {name: sha(physical.regions[name]['data']) for name in ('gate', 'up')}
        self.spans = [(r['base'], r['base'] + r['reserved'], name) for name, r in physical.regions.items()]

    def read64(self, address):
        name, words = self.physical_memory.read64(address)
        return self.LABELS.get(name, name), words

    def check_virtual(self):
        physical = self.physical_memory
        require(all(not physical.regions[name]['written'] and not physical.regions[name]['acked'] and
                    sha(physical.regions[name]['data']) == digest
                    for name, digest in self.virtual_hashes.items()), 'virtual Gate/Up DDR changed')
        return dict(initial_and_final_sha256=dict(self.virtual_hashes),
                    bytes_each=physical.regions['gate']['extent'], unchanged=True, physical_writes=0)
