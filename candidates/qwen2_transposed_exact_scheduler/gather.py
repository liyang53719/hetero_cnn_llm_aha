"""NEW bounded transpose-ingress control; no SRAM/RTL implementation.

Two buffers each hold 16 rows x 16 BF16 values = 512 bytes. The model retains
only their row-valid masks/identities, not a fictional additional tensor store.
FP32->BF16 conversion remains the existing owner conversion, outside this
integer-only model. One accepted DMA segment and one bulk commit may be live.
"""
from dataclasses import dataclass
from candidates.qwen2_exact_tree_scheduler.model import require


@dataclass
class Buffer:
    block: int
    mask: int = 0
    writing: bool = False


def segment_address(block, row):
    require(0 <= block < 768 and 0 <= row < 16, 'gather segment bounds')
    q, group = divmod(block, 8)
    return ((group*16+row)*1536 + q*16)*4


def destination(block, row, k_lane):
    require(0 <= block < 768 and 0 <= row < 16 and 0 <= k_lane < 16, 'gather destination bounds')
    return k_lane ^ (block % 8), block, row


class Gather:
    def __init__(self):
        self.buffers = [None, None]
        self.dma = self.write = None
        self.allocated = self.committed = 0
        self.poisoned = False
        self.peak_buffers = 0

    @property
    def ready(self):
        return not self.poisoned and self.committed == 768 and self.dma is None and self.write is None

    def issue_segment(self, tag, block, row, address):
        require(not self.poisoned and self.dma is None, 'gather DMA credit/poison')
        require(address == segment_address(block, row), 'gather source address mismatch')
        index = block % 2
        buf = self.buffers[index]
        if buf is None:
            require(block == self.allocated, 'gather allocation order')
            buf = self.buffers[index] = Buffer(block)
            self.allocated += 1
        require(buf.block == block and not buf.writing and not (buf.mask >> row & 1),
                'gather buffer reuse/duplicate row')
        self.dma = tag, index, row
        self.peak_buffers = max(self.peak_buffers, sum(b is not None for b in self.buffers))

    def accept_segment(self, tag, *, success=True):
        require(self.dma is not None and self.dma[0] == tag, 'gather DMA response identity')
        _, index, row = self.dma
        self.dma = None
        if not success:
            self.abort()
        if not self.poisoned:
            self.buffers[index].mask |= 1 << row

    def issue_commit(self, tag, block):
        require(not self.poisoned and self.write is None, 'gather write credit/poison')
        index = block % 2
        buf = self.buffers[index]
        require(buf is not None and buf.block == block and buf.mask == 0xffff and not buf.writing,
                'gather commit before all16 successful segments')
        require(block == self.committed, 'gather commit order')
        buf.writing = True
        self.write = tag, index, block

    def accept_commit(self, tag, *, success=True):
        require(self.write is not None and self.write[0] == tag, 'gather write ACK identity')
        _, index, block = self.write
        self.write = None
        if not success:
            self.abort()
        self.buffers[index] = None
        if not self.poisoned:
            self.committed += 1

    def abort(self):
        self.poisoned = True
        # Accepted DMA/write still drain; no forged credit or ready publication.
