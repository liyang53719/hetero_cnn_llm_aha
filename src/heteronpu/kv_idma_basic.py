"""Single-sequence BF16 KV staging and iDMA request reference for L2."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class IdmaTransfer:
    src_addr: int
    dst_addr: int
    length: int


class KvIdmaBasicModel:
    def __init__(self, *, staging_base: int = 0x10_0000, staging_bytes: int = 512 * 1024):
        if staging_bytes <= 0 or staging_bytes % 2:
            raise ValueError("KV staging size must be positive and even")
        self.base = staging_base
        self.half = staging_bytes // 2
        self.allocated = False
        self.length = 0
        self.head_dim = 0

    def alloc(self, *, sequence_id: int, layer_id: int, head_dim: int) -> tuple[IdmaTransfer, ...]:
        if sequence_id != 0 or layer_id != 0 or self.allocated or not 1 <= head_dim <= 256:
            raise ValueError("L2 basic KV supports one empty sequence/layer and head_dim 1..256")
        self.allocated = True; self.length = 0; self.head_dim = head_dim
        return ()

    def append(self, *, token_start: int, token_count: int,
               k_addr: int, v_addr: int) -> tuple[IdmaTransfer, ...]:
        if not self.allocated or token_start != self.length or token_count <= 0:
            raise ValueError("KV append is unallocated, non-contiguous or empty")
        byte_count = token_count * self.head_dim * 2
        offset = token_start * self.head_dim * 2
        if offset + byte_count > self.half:
            raise MemoryError("KV BF16 staging overflow")
        self.length += token_count
        return (IdmaTransfer(k_addr, self.base + offset, byte_count),
                IdmaTransfer(v_addr, self.base + self.half + offset, byte_count))

    def gather(self, *, token_start: int, token_count: int,
               output_addr: int) -> tuple[IdmaTransfer, ...]:
        if not self.allocated:
            raise ValueError("KV sequence is not allocated")
        if token_count <= 0 or token_start + token_count > self.length:
            raise ValueError("KV gather range is invalid")
        byte_count = token_count * self.head_dim * 2
        offset = token_start * self.head_dim * 2
        return (IdmaTransfer(self.base + offset, output_addr, byte_count),
                IdmaTransfer(self.base + self.half + offset, output_addr + byte_count, byte_count))

    def free(self) -> tuple[IdmaTransfer, ...]:
        if not self.allocated:
            raise ValueError("KV sequence is not allocated")
        self.allocated = False; self.length = 0; self.head_dim = 0
        return ()
