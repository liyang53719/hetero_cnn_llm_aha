"""Software-only phase 5/6 contraction candidate, not a Chisel/RTL owner.

One shared 4096-lane Matrix is reused for separately rounded Mul and Add.
A 4096-word accumulator and product bank, plus two 1024-word input panels,
are explicit proposed storage (40960 bytes); they are NOT free existing SRAM.
The existing 16-lane Vector handles pair multiplication after all 128 K steps.
Memory calls are synchronous software obligations, not measured hardware ACKs.
"""
from dataclasses import dataclass
from candidates.qwen35_strict_fp32_lane import lane_model as fp

ROWS, K, LANES, VECTOR_LANES = 64, 128, 4096, 16


@dataclass(frozen=True)
class Matrix:
    base: int
    rows: int
    cols: int

    def __post_init__(self):
        if (type(self.base) is not int or self.base < 0 or self.base % 64 or
                self.rows <= 0 or self.cols <= 0 or self.cols % 16 or
                self.base + self.rows * self.cols * 4 > 1 << 56):
            raise ValueError('aligned finite 56-bit matrix span required')

    @property
    def end(self):
        return self.base + 4 * self.rows * self.cols

    def address(self, row, col):
        if not (0 <= row < self.rows and 0 <= col < self.cols and col % 16 == 0):
            raise ValueError('full beat index')
        return self.base + 4 * (row * self.cols + col)


class ArithmeticFault(ValueError):
    def __init__(self, stage, k, lane, word, flags):
        super().__init__(f'{stage}: K={k}, lane={lane}, word={word:08x}, flags={flags}')
        self.stage, self.k, self.lane, self.word, self.flags = stage, k, lane, word, flags


def validate_contraction(a, kt, pair, destination, phase):
    """Shared full-chunk geometry admission, independent of execution order."""
    if phase not in (5, 6):
        raise ValueError('only UtMatmul / IntraMatmul')
    if [(m.rows, m.cols) for m in (a, kt, pair, destination)] != [(64,128),(128,64),(64,64),(64,64)]:
        raise ValueError('complete chunk64 / K128 required')
    matrices = (a, kt, pair, destination)
    if any(x.base < y.end and y.base < x.end for i,x in enumerate(matrices) for y in matrices[:i]):
        raise ValueError('matrix spans must be disjoint')


class Contraction:
    """Run one full 64x128 @ 128x64 phase, never token-recurrent M1.

    read16(address) returns 16 FP32 raw words; write16(address, words) returns
    after a modeled successful write. Failure leaves no completion; earlier
    writes may exist, so callers must not publish the destination on failure.
    observe(stage, k, words, flags) is a synchronous diagnostic hook. Consumers
    must not mutate these lists and must copy data they retain. It sees every
    rounded product and accumulator.
    One instance owns two persistent banks and two persistent input panels.
    Calls reuse this workspace serially, starting with a cleared accumulator;
    callbacks must not recursively submit work to the same instance. There is
    no asynchronous transaction, chunk scheduler, or hardware ownership claim.
    """
    def __init__(self, read16, write16, observe=None):
        self.read16, self.write16, self.observe = read16, write16, observe
        self.counts = {}
        self._banks = ([0]*LANES, [0]*LANES)
        self._panels = ([0]*(ROWS*16), [0]*(16*ROWS))
        self._busy = False

    def _read(self, address):
        values = list(self.read16(address))
        if len(values) != 16 or any(type(x) is not int or not 0 <= x <= 0xffffffff or
                                    not fp.finite(x) for x in values):
            raise ValueError('finite FP32 read beat required')
        self.counts['read_beats'] += 1
        return values

    def _check(self, stage, k, values, flags):
        if self.observe:
            self.observe(stage, k, values, flags)
        for lane, (word, flag) in enumerate(zip(values, flags)):
            if flag & 30 or not fp.finite(word):
                raise ArithmeticFault(stage, k, lane, word, flag)

    def run(self, a, kt, pair, destination, *, phase):
        if self._busy:
            raise RuntimeError('contraction workspace already owned by an active run')
        validate_contraction(a, kt, pair, destination, phase)
        self._busy = True
        try:
            return self._run(a, kt, pair, destination, phase)
        finally:
            # Calls are synchronous. Even a failed callback has returned before
            # reuse; this does NOT roll back or publish any destination writes.
            self._busy = False

    def _run(self, a, kt, pair, destination, phase):
        self.counts = dict(phase=phase, read_beats=0, write_beats=0,
                           matrix_lane_passes=0, vector_lane_ops=0,
                           matrix_lanes=4096, vector_lanes=16,
                           proposed_storage_bytes=40960)
        acc, product = self._banks
        ap, bp = self._panels
        for lane in range(LANES):
            acc[lane] = 0
        for start in range(0, K, 16):
            # Explicit 4 KiB A and B panels; reused for sixteen ascending K steps.
            # A beat is installed only after _read validates all sixteen words.
            # Do not compute with a partially filled panel after a read failure.
            for r in range(ROWS):
                ap[r*16:(r+1)*16] = self._read(a.address(r,start))
            for offset in range(16):
                for c in range(0, ROWS, 16):
                    bp[offset*64+c:offset*64+c+16] = self._read(kt.address(start+offset,c))
            for offset in range(16):
                k = start + offset
                flags = [0]*LANES
                for r in range(ROWS):
                    for c in range(ROWS):
                        lane = r*64+c
                        product[lane], flags[lane] = fp.mul(ap[r*16+offset], bp[offset*64+c])
                self.counts['matrix_lane_passes'] += LANES
                self._check('mul', k, product, flags)
                # No accumulator update before the whole product plane is valid.
                flags = [0]*LANES
                for lane in range(LANES):
                    product[lane], flags[lane] = fp.add(product[lane], acc[lane])
                self.counts['matrix_lane_passes'] += LANES
                self._check('add', k, product, flags)
                acc, product = product, acc
        for r in range(ROWS):
            for c in range(0,ROWS,16):
                weights = self._read(pair.address(r,c))
                results = [fp.mul(acc[r*64+c+i], weights[i]) for i in range(16)]
                values, flags = map(list, zip(*results))
                self.counts['vector_lane_ops'] += 16
                self._check('pair', r*64+c, values, flags)
                self.write16(destination.address(r,c), values)
                self.counts['write_beats'] += 1
        return dict(self.counts)
