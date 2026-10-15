"""Default-off Dense raw -> official Bias candidate; finite data/ACK model.

No RTL, oracle-fed payload, or hardware timing. The producer supplies actual
FP32 words; debug observes only accepted words. SharedDMA models the existing
single-request contract, including competing X/W reads, not a free second bus.
"""
from collections import Counter, deque
from dataclasses import dataclass

from candidates.qwen2_exact_tree_scheduler.arithmetic import add, decode
from candidates.qwen2_exact_tree_scheduler.model import require


def bf16_container(word):
    decode(word)
    rounded = ((word + 0x7fff + ((word >> 16) & 1)) >> 16) & 0xffff
    require((rounded & 0x7f80) != 0x7f80, 'BF16 overflow outside finite domain')
    return rounded << 16


def bias_packet(raw, bias):
    require(len(raw) == len(bias) == 16, 'sixteen FP32 lanes')
    return tuple(bf16_container(add(x, y)) for x, y in zip(raw, bias))


@dataclass(frozen=True)
class Pair:
    epoch: int
    dense_tag: int
    bias_tag: int
    tensor: str
    width: int
    raw_base: int
    bias_base: int
    dst_base: int

    def validate(self):
        require(self.tensor in ('Q', 'K') and self.width == {'Q': 1536, 'K': 256}[self.tensor],
                'paired tensor/width identity')
        require(all(type(x) is int and 0 <= x < 1 << 64 for x in
                    (self.epoch, self.dense_tag, self.bias_tag, self.raw_base, self.bias_base, self.dst_base)),
                'unsigned paired identity/address')
        spans = [(self.raw_base, 128*self.width*4), (self.bias_base, self.width*4),
                 (self.dst_base, 128*self.width*4)]
        require(all(a % 64 == 0 and a+n <= 1 << 64 for a, n in spans), 'paired address span')
        require(all(a+n <= b or b+m <= a for i, (a, n) in enumerate(spans)
                    for b, m in spans[i+1:]), 'paired regions overlap')


@dataclass(frozen=True)
class TileTag:
    pair: Pair
    panel: int
    nbase: int


@dataclass(frozen=True)
class PacketTag:
    tile: TileTag
    packet: int
    address: int


@dataclass(frozen=True)
class Request:
    epoch: int
    sequence: int
    kind: str
    identity: object
    address: int
    words: tuple = ()


class SharedDMA:
    """Exactly one accepted 64B request, one common X/W/Bias/write port."""
    def __init__(self, epoch):
        self.epoch, self.sequence, self.pending = epoch, 0, None
        self.poisoned = False
        self.stats = Counter()

    def issue(self, kind, identity, address, words=()):
        require(not self.poisoned and self.pending is None, 'single shared DMA credit/poison')
        require(kind in ('x_read', 'w_read', 'bias_read', 'bias_write'), 'shared DMA kind')
        require(type(address) is int and 0 <= address <= (1 << 64)-64 and address % 64 == 0,
                '64B DMA address')
        require((kind == 'bias_write' and len(words) == 16) or
                (kind != 'bias_write' and not words), 'DMA write payload')
        req = Request(self.epoch, self.sequence, kind, identity, address, tuple(words))
        self.sequence += 1
        self.pending = req
        self.stats['issued:'+kind] += 1
        return req

    def complete(self, request, *, error=False):
        if request != self.pending or self.pending is None:
            self.poisoned = True
            raise ValueError('shared DMA response tag/epoch mismatch; original request must drain')
        self.pending = None
        if error:
            self.poisoned = True
        if not self.poisoned:
            self.stats['acked:'+request.kind] += 1

    def abort(self):
        self.poisoned = True  # accepted pending request is deliberately retained


@dataclass
class Tile:
    tag: TileTag
    words: tuple | None = None
    packet: int = 0


class Handoff:
    """3 existing output tiles, 128B bias cache, one held 64B output packet.

    Packet arithmetic is immediate Python integer evaluation; arithmetic cycles
    are NOT inferred. A hardware implementation needs explicit ALU/RNE latency.
    Both original owner modes must be idle at paired admission. The legacy mode
    remains default. No old raw DDR ACK/publication is synthesized.
    """
    def __init__(self, pair, dma, *, enabled=False, old_owners_idle=False, debug_sink=None):
        require(enabled and old_owners_idle, 'new paired mode and owner isolation required')
        pair.validate()
        require(dma.epoch == pair.epoch and dma.pending is None and not dma.poisoned,
                'paired DMA epoch/quiescence')
        self.pair, self.dma, self.debug_sink = pair, dma, debug_sink
        self.tiles = deque()
        self.producer_pending = set()  # <=3 accepted root operations, retained across abort
        self.next_panel = self.raw_packets = self.write_acks = 0
        self.cache_tag, self.bias = None, [None, None]
        self.output = self.request = None
        self.poisoned = False
        self.peak_tiles = 0

    @property
    def producer_done(self):
        return not self.poisoned and not self.dma.poisoned and self.raw_packets == self.pair.width*8

    @property
    def done(self):
        return (self.producer_done and self.write_acks == self.pair.width*8 and
                self.output is None and self.request is None and self.dma.pending is None)

    @property
    def drained(self):
        return self.dma.pending is None and self.request is None and not self.producer_pending

    def reserve(self, panel):
        require(not self.poisoned and not self.dma.poisoned, 'paired owner poisoned')
        require(type(panel) is int and panel == self.next_panel and panel < self.pair.width//32,
                'monotonic panel identity')
        require(len(self.tiles) < 3, 'three output tile credits exhausted')
        tag = TileTag(self.pair, panel, panel*32)
        self.tiles.append(Tile(tag))
        self.producer_pending.add(tag)
        self.next_panel += 1
        self.peak_tiles = max(self.peak_tiles, len(self.tiles))
        return tag

    def emit(self, tag, words, *, error=False):
        # reserve means the root operation was accepted, not a revocable hint.
        # A bad tag cannot acknowledge that outstanding operation. A matching
        # late return drains it even after abort, without publishing payload.
        if tag not in self.producer_pending:
            self.abort()
            raise ValueError('unreserved/duplicate producer return tag/epoch')
        self.producer_pending.remove(tag)
        if self.poisoned or self.dma.poisoned or error:
            self.abort()
            return
        tile = next((t for t in self.tiles if t.tag == tag), None)
        try:
            require(tile is not None and tile.words is None, 'unreserved/duplicate output tile')
            require(len(words) == 4096, 'one existing 16KiB output tile')
            for word in words:
                decode(word)
        except ValueError:
            self.abort()
            raise
        tile.words = tuple(words)  # logical row-major M128,N32, physically existing storage

    def poll_request(self):
        """Returns only newly accepted requests. The caller supplies real ACKs."""
        require(not self.poisoned and not self.dma.poisoned, 'paired owner poisoned')
        if self.request is not None or self.dma.pending is not None:
            return None
        if self.output is not None:
            identity, words = self.output
            self.request = self.dma.issue('bias_write', identity, identity.address, words)
        elif self.tiles and self.tiles[0].words is not None:
            tag = self.tiles[0].tag
            if self.cache_tag != tag:
                self.cache_tag, self.bias = tag, [None, None]
            half = next((i for i, words in enumerate(self.bias) if words is None), None)
            if half is not None:
                address = self.pair.bias_base + (tag.nbase+half*16)*4
                self.request = self.dma.issue('bias_read', (tag, half), address)
        return self.request

    def accept_raw(self):
        """One actual raw.fire; output must already be held before tile release."""
        require(not self.poisoned and not self.dma.poisoned, 'paired owner poisoned')
        if (self.output is not None or not self.tiles or self.tiles[0].words is None or
                self.cache_tag != self.tiles[0].tag or any(b is None for b in self.bias)):
            return None
        tile = self.tiles[0]
        row, half = divmod(tile.packet, 2)
        raw = tile.words[tile.packet*16:(tile.packet+1)*16]
        address = self.pair.dst_base + (row*self.pair.width+tile.tag.nbase+half*16)*4
        identity = PacketTag(tile.tag, tile.packet, address)
        try:
            words = bias_packet(raw, self.bias[half])
        except ValueError:
            self.abort()
            raise
        self.output = (identity, words)
        tile.packet += 1
        self.raw_packets += 1
        if tile.packet == 256:
            self.tiles.popleft()
        if self.debug_sink is not None:
            try:
                self.debug_sink(identity, raw)
            except Exception:
                self.abort()
                raise
        return identity

    def complete(self, request, *, words=(), error=False):
        if self.request != request or request is None:
            self.abort()
            raise ValueError('paired response identity; original pending request must drain')
        if request.kind == 'bias_read' and not error and not self.poisoned:
            try:
                require(len(words) == 16, 'bias DMA payload length')
                for word in words:
                    decode(word)
            except ValueError:
                self.abort()
                raise
        self.dma.complete(request, error=error)
        self.request = None
        if self.poisoned or self.dma.poisoned:
            self.abort()
            return
        if request.kind == 'bias_read':
            tag, half = request.identity
            require(tag == self.cache_tag and self.bias[half] is None, 'bias cache binding')
            self.bias[half] = tuple(words)
        else:
            require(self.output is not None and self.output[0] == request.identity and
                    self.output[1] == request.words, 'held write identity/payload')
            self.output = None
            self.write_acks += 1

    def abort(self):
        self.poisoned = True
        self.dma.abort()
        self.tiles.clear()
        self.output = None
        self.cache_tag, self.bias = None, [None, None]


def ledger(*, shared_x_lease=False, debug_raw_ddr=False):
    """Pure 512-bit transfer floors, not attainable schedule predictions."""
    useful, w, raw, bias = 56*1536, 56*1536, 56*256, 56*2
    x = 12288*(1 if shared_x_lease else 2)
    debug = raw if debug_raw_ddr else 0
    standalone = x+w+raw
    fused = x+w+bias+raw+debug
    unfused_cached = x+w+bias+3*raw
    return dict(status='COLD_FULL_BOUNDARY_NO_GO', useful_issue_equivalents=useful,
                x_read_beats=x, w_read_beats=w, bias_cached_read_beats=bias,
                bias_fp32_container_write_beats=raw, debug_export_beats=debug,
                standalone_projection_raw_ddr_floor=standalone,
                standalone_projection_ceiling=useful/standalone,
                internal_raw_consumed_transfer_floor=x+w,
                internal_raw_consumed_is_not_final_boundary=True,
                fused_through_final_bias_ack_floor=fused,
                fused_through_final_bias_ack_ceiling=useful/fused,
                unfused_with_same_bias_cache_floor=unfused_cached,
                saved_raw_write_and_bias_read_beats=2*raw,
                net_saved_beats=unfused_cached-fused,
                current_uncached_bias_extra_read_beats=raw-bias,
                shared_x_lease='NEW_UNIMPLEMENTED' if shared_x_lease else 'OFF_Q_K_RELOAD',
                warm_fullblock=None, warm_fullblock_status='BLOCKED_NO_UPSTREAM_RESIDENT_PROOF',
                hardware_cycles=None, hardware_utilization=None)


if __name__ == '__main__':
    import json
    print(json.dumps({'default': ledger(), 'new_shared_lease': ledger(shared_x_lease=True)}, indent=2))
