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


class Contraction:
    """Run one full 64x128 @ 128x64 phase, never token-recurrent M1.

    read16(address) returns 16 FP32 raw words; write16(address, words) returns
    after a modeled successful write. Failure leaves no completion; earlier
    writes may exist, so callers must not publish the destination on failure.
    observe(stage, k, words, flags) is a synchronous diagnostic hook. Consumers
    must copy data they retain. It sees every rounded product and accumulator.
    """
    def __init__(self, read16, write16, observe=None):
        self.read16, self.write16, self.observe = read16, write16, observe
        self.counts = {}

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
        if phase not in (5, 6):
            raise ValueError('only UtMatmul / IntraMatmul')
        if [(m.rows, m.cols) for m in (a, kt, pair, destination)] != [(64,128),(128,64),(64,64),(64,64)]:
            raise ValueError('complete chunk64 / K128 required')
        matrices = (a, kt, pair, destination)
        if any(x.base < y.end and y.base < x.end for i,x in enumerate(matrices) for y in matrices[:i]):
            raise ValueError('matrix spans must be disjoint')
        self.counts = dict(phase=phase, read_beats=0, write_beats=0,
                           matrix_lane_passes=0, vector_lane_ops=0,
                           matrix_lanes=4096, vector_lanes=16,
                           proposed_storage_bytes=40960)
        acc, product = [0]*LANES, [0]*LANES
        for start in range(0, K, 16):
            # Explicit 4 KiB A and B panels; reused for sixteen ascending K steps.
            ap = [self._read(a.address(r,start)) for r in range(ROWS)]
            bp = [sum((self._read(kt.address(start+k,c)) for c in range(0,64,16)), []) for k in range(16)]
            for offset in range(16):
                k = start + offset
                flags = [0]*LANES
                for r in range(ROWS):
                    for c in range(ROWS):
                        lane = r*64+c
                        product[lane], flags[lane] = fp.mul(ap[r][offset], bp[offset][c])
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
