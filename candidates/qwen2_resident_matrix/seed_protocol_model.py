"""Executable CONTROL REFERENCE ONLY; not Chisel/RTL or a numerical oracle.

Uses the source's actual 16-bank A/C address equation. No sealed manifest,
private Host encoding, or replacement FMA is introduced. Source and controller
checks are deliberately separate, matching their proposed trusted boundaries.
"""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Request:
    group_tag: int = 0x10001
    group_sequence: int = 1
    source_generation: int = 1
    context: int = 0
    slice_mask: int = 0xFF


@dataclass(frozen=True)
class Beat:
    group_tag: int
    group_sequence: int
    source_generation: int
    context: int
    index: int
    words: tuple[int, ...]
    last: bool
    error: bool = False

    @classmethod
    def make(cls, req, index, words, last=False, error=False):
        return cls(req.group_tag, req.group_sequence, req.source_generation,
                   req.context, index, tuple(words), last, error)


@dataclass(frozen=True)
class Ack:
    group_tag: int
    group_sequence: int
    source_generation: int
    context: int
    error: bool = False

    @classmethod
    def make(cls, req, error=False):
        return cls(req.group_tag, req.group_sequence, req.source_generation,
                   req.context, error)


@dataclass(frozen=True)
class SourceLease:
    request: Request
    slot: int
    tile_row: int
    rows: int
    cols: int
    n_base: int
    prefix_k: int


def finite(word):
    return 0 <= word <= 0xFFFFFFFF and (word >> 23) & 255 != 255


def route(mask):
    return [(s, c) for s in range(8) if mask & (1 << s) for c in range(32)]


class ResidentPrefixOwner:
    """Existing numerical-model layout, plus required real owner metadata.

    generations and leases are proposed control state, not existing hardware.
    Each source word holds eight raw FP32 values in sixteen BF16 halfword slots.
    """
    def __init__(self, m=128, n=256, k=1792):
        if not (0 < m <= 128 and 0 < n < 65536 and 0 < k < 65536 and n % 16 == k % 16 == 0):
            raise ValueError("shape")
        self.m, self.n, self.k = m, n, k
        self.a_depth = k if k <= 1536 else 256
        self.c_base = self.a_depth // 2
        self.slots = 1 if k <= 1536 else 3
        assert self.c_base + self.slots * 256 <= 1024
        self.scratch = bytearray(768 * 1024)  # A/C 512 KiB + B 256 KiB
        self.prefix = [[-1] * 8 for _ in range(3)]
        self.owner_n = [[-1] * 8 for _ in range(3)]
        self.generation = [[0] * 8 for _ in range(3)]
        self.leases = {}
        self.quarantined = set()
        self.read_words = 0

    def address(self, slot, row, col, c_base=None):
        base = self.c_base if c_base is None else c_base
        if base != self.c_base or not (0 <= slot < self.slots and 0 <= row < 128 and 0 <= col < 256):
            raise ValueError("slot/shape/alias")
        bank = row % 16
        word = base + slot * 256 + (row // 16) * 32 + col // 8
        lane = 2 * (col % 8)
        if not (self.c_base <= word < 1024):
            raise ValueError("A/C alias")
        return (bank * 1024 + word) * 32 + lane * 2

    def store(self, slot, tile_row, n_base, prefix_k, words, acknowledged=True):
        if (slot, tile_row) in self.leases:
            raise ValueError("source generation pinned")
        rows = min(16, self.m - tile_row * 16)
        cols = min(256, self.n - n_base)
        if not (0 <= slot < self.slots and 0 <= tile_row < 8 and rows > 0 and cols > 0 and
                n_base >= 0 and n_base % 256 == 0 and 0 < prefix_k < self.k and prefix_k % 256 == 0):
            raise ValueError("source shape")
        if len(words) != rows * cols or not all(finite(w) for w in words):
            raise ValueError("source finite domain")
        if self.generation[slot][tile_row] == 0xFFFFFFFF:
            raise ValueError("generation wrap requires drain/reset")
        for row in range(rows):
            for col in range(cols):
                address = self.address(slot, tile_row * 16 + row, col)
                self.scratch[address:address + 4] = words[row * cols + col].to_bytes(4, 'little')
        # Partial or failed stores are not advertised as a reusable prefix.
        self.prefix[slot][tile_row] = prefix_k if acknowledged else -1
        self.owner_n[slot][tile_row] = n_base if acknowledged else -1
        if acknowledged:
            self.generation[slot][tile_row] += 1

    def open_restore(self, req, slot, tile_row, n_base, prefix_k, rows, cols, c_base=None):
        if not (0 <= slot < self.slots and 0 <= tile_row < 8):
            raise ValueError("source slot/tile")
        expected_rows = min(16, self.m - tile_row * 16)
        expected_cols = min(256, self.n - n_base)
        if rows != expected_rows or cols != expected_cols or rows <= 0 or cols <= 0:
            raise ValueError("M/N shape")
        if prefix_k != self.prefix[slot][tile_row] or n_base != self.owner_n[slot][tile_row]:
            raise ValueError("prefix/ownerN")
        if not (0 < prefix_k < self.k and prefix_k % 256 == 0):
            raise ValueError("K prefix")
        if req.source_generation != self.generation[slot][tile_row]:
            raise ValueError("generation")
        if req.slice_mask != (1 << ((cols + 31) // 32)) - 1:
            raise ValueError("source selected slices")
        self.address(slot, tile_row * 16, 0, c_base)
        if (slot, tile_row) in self.leases:
            raise ValueError("duplicate source lease")
        lease = SourceLease(req, slot, tile_row, rows, cols, n_base, prefix_k)
        self.leases[(slot, tile_row)] = lease
        return lease

    def check_lease(self, req, lease):
        key = (lease.slot, lease.tile_row)
        if key in self.quarantined or self.leases.get(key) != lease or req != lease.request:
            raise ValueError("inactive, failed, or wrong-identity lease")
        if (self.generation[lease.slot][lease.tile_row] != req.source_generation or
                self.prefix[lease.slot][lease.tile_row] != lease.prefix_k or
                self.owner_n[lease.slot][lease.tile_row] != lease.n_base):
            raise ValueError("source metadata changed while pinned")

    def beats(self, req, lease):
        slot, tile_row, rows, cols = lease.slot, lease.tile_row, lease.rows, lease.cols
        routes = route(req.slice_mask)
        for index, (slice_id, cluster) in enumerate(routes):
            self.check_lease(req, lease)
            row, half = divmod(cluster, 2)
            first_col = slice_id * 32 + half * 16
            data = []
            if row < rows and first_col < cols:
                self.read_words += 2  # same row bank, two 256-bit source words
            for lane in range(16):
                col = first_col + lane
                if row >= rows or col >= cols:
                    data.append(0)
                else:
                    address = self.address(slot, tile_row * 16 + row, col)
                    data.append(int.from_bytes(self.scratch[address:address + 4], 'little'))
            yield Beat.make(req, index, data, index == len(routes) - 1)

    def release(self, lease, success):
        self.check_lease(lease.request, lease)
        key = (lease.slot, lease.tile_row)
        if not success:
            self.quarantined.add(key)
            return  # failure stays quarantined until coordinated reset
        del self.leases[key]


class SeedControllerModel:
    """Handshake-level model of the candidate Chisel control and bank effects.

    It does not claim cycle correspondence, an actual mapped SRAM rate, or FMA
    numerical validation. Bank snapshots used by tests are observers only.
    """
    def __init__(self, group_tag=0x10001, group_sequence=1, slice_mask=0xFF):
        self.group_tag, self.group_sequence, self.slice_mask = group_tag, group_sequence, slice_mask
        self.group_active = self.quiescent = True
        self.seen = self.closed = self.seeded = 0
        self.state = 'idle'
        self.poison = self.reserved = self.response_error = False
        self.req = None
        self.next_beat = self.acknowledged = 0
        self.banks = [[0x3F000000] * 4096 for _ in range(5)]
        self.leaf_valid = [[False] * 8 for _ in range(5)]
        self.writes = self.commit_events = self.responses = 0

    def fault(self):
        self.poison = True
        if self.state != 'reply':
            self.response_error = True
            self.state = 'reply'
        if self.reserved:
            for s in range(8):
                if self.req.slice_mask & (1 << s):
                    self.leaf_valid[self.req.context][s] = False

    def identity_ok(self):
        return self.group_active and self.req.group_tag == self.group_tag and self.req.group_sequence == self.group_sequence and self.req.slice_mask == self.slice_mask

    def observe(self, abort=False):
        if self.state not in ('idle', 'locked') and (abort or not self.identity_ok() or not self.quiescent):
            self.fault()

    def unexpected_ack(self):
        if self.state == 'idle':
            self.poison = True
            self.state = 'locked'
        elif self.state not in ('collect', 'locked'):
            self.fault()

    def begin(self, req):
        if self.state != 'idle' or self.poison:
            return False
        self.req = req
        self.next_beat = self.acknowledged = 0
        self.reserved = self.response_error = False
        free = not ((self.seen | self.closed | self.seeded) & (1 << req.context)) if 0 <= req.context < 5 else False
        if not (self.identity_ok() and self.quiescent and free and 0 < req.slice_mask < 256):
            self.fault()
        else:
            self.state = 'reserve'
        return True

    def reserve(self, ready=True):
        self.observe()
        if self.state != 'reserve' or not ready:
            return False
        self.reserved = True
        for s in range(8):
            if self.req.slice_mask & (1 << s):
                self.leaf_valid[self.req.context][s] = False
        self.state = 'stream'
        return True

    def beat(self, b, ready=True):
        self.observe()
        if self.state != 'stream':
            return False
        routes = route(self.req.slice_mask)
        legal = (b.group_tag, b.group_sequence, b.source_generation, b.context) == (self.req.group_tag, self.req.group_sequence, self.req.source_generation, self.req.context)
        legal = legal and b.index == self.next_beat and b.last == (self.next_beat + 1 == len(routes))
        legal = legal and not b.error and len(b.words) == 16 and all(finite(w) for w in b.words)
        if not legal:
            self.fault()
            return True
        if not ready:
            return False
        slice_id, cluster = routes[self.next_beat]
        row, half = divmod(cluster, 2)
        offset = row * 256 + slice_id * 32 + half * 16
        self.banks[self.req.context][offset:offset + 16] = b.words
        self.writes += 1
        self.next_beat += 1
        if b.last:
            self.state = 'commit'
        return True

    def commit(self, ready=True):
        self.observe()
        if self.state != 'commit' or not ready:
            return False
        for s in range(8):
            if self.req.slice_mask & (1 << s):
                self.leaf_valid[self.req.context][s] = True
        self.state = 'collect'
        return True

    def leaf_ack(self, slice_id, ack):
        self.observe()
        if self.state != 'collect':
            self.unexpected_ack()
            return False
        mask = 1 << slice_id
        if not self.req.slice_mask & mask or self.acknowledged & mask or ack != Ack.make(self.req):
            self.fault()
        else:
            self.acknowledged |= mask
            if self.acknowledged == self.req.slice_mask:
                self.state = 'reply'
        return True

    def response(self):
        return Ack.make(self.req, self.response_error) if self.state == 'reply' else None

    def take_response(self, ready=True, abort=False):
        self.observe(abort)
        if self.state != 'reply' or not ready:
            return False
        success = not self.poison and not self.response_error and not abort and self.identity_ok() and self.quiescent
        self.responses += 1
        if success:
            self.seeded |= 1 << self.req.context
            self.commit_events += 1
            self.reserved = False
        self.state = 'idle' if success else 'locked'
        return True

    def first_step(self, context, clear):
        if self.state != 'idle' or self.poison or not 0 <= context < 5:
            return False
        mask = 1 << context
        legal = not self.closed & mask and clear == (not (self.seen | self.seeded) & mask)
        if legal:
            self.seen |= mask
        return legal
