from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

import numpy as np

from .dtypes import bf16_round, quantize_int8_symmetric


@dataclass
class PhysicalPage:
    k: np.ndarray
    v: np.ndarray
    k_scale: np.ndarray | None
    v_scale: np.ndarray | None
    refcount: int = 1


class KVPageEngine:
    """Paged KV-cache functional model with prefix sharing and copy-on-write."""

    def __init__(
        self,
        *,
        page_tokens: int,
        physical_pages: int,
        kv_heads: int,
        head_dim: int,
        storage_format: str = "bf16",
    ) -> None:
        if page_tokens <= 0 or physical_pages <= 0 or kv_heads <= 0 or head_dim <= 0:
            raise ValueError("all KV dimensions must be positive")
        if storage_format not in {"bf16", "int8"}:
            raise ValueError("storage_format must be 'bf16' or 'int8'")
        self.page_tokens = page_tokens
        self.physical_pages = physical_pages
        self.kv_heads = kv_heads
        self.head_dim = head_dim
        self.storage_format = storage_format
        self._free = list(range(physical_pages - 1, -1, -1))
        self._pages: Dict[int, PhysicalPage] = {}
        self._tables: Dict[Tuple[int, int], list[int]] = {}
        self._lengths: Dict[Tuple[int, int], int] = {}
        self.allocations = 0
        self.cow_copies = 0
        self.read_tokens = 0
        self.written_tokens = 0

    def _new_page(self) -> int:
        if not self._free:
            raise MemoryError("KV physical page pool exhausted")
        page_id = self._free.pop()
        if self.storage_format == "bf16":
            dtype = np.float32
            k_scale = None
            v_scale = None
        else:
            dtype = np.int8
            k_scale = np.ones((self.page_tokens, self.kv_heads, 1), dtype=np.float32)
            v_scale = np.ones((self.page_tokens, self.kv_heads, 1), dtype=np.float32)
        page = PhysicalPage(
            k=np.zeros((self.page_tokens, self.kv_heads, self.head_dim), dtype=dtype),
            v=np.zeros((self.page_tokens, self.kv_heads, self.head_dim), dtype=dtype),
            k_scale=k_scale,
            v_scale=v_scale,
        )
        self._pages[page_id] = page
        self.allocations += 1
        return page_id

    def _release_page(self, page_id: int) -> None:
        page = self._pages[page_id]
        page.refcount -= 1
        if page.refcount < 0:
            raise RuntimeError("negative KV page reference count")
        if page.refcount == 0:
            del self._pages[page_id]
            self._free.append(page_id)

    def _copy_page(self, page_id: int) -> int:
        source = self._pages[page_id]
        new_id = self._new_page()
        target = self._pages[new_id]
        target.k[...] = source.k
        target.v[...] = source.v
        if target.k_scale is not None and source.k_scale is not None:
            target.k_scale[...] = source.k_scale
            target.v_scale[...] = source.v_scale
        self._release_page(page_id)
        self.cow_copies += 1
        return new_id

    def append(
        self,
        sequence_id: int,
        layer_id: int,
        k: np.ndarray,
        v: np.ndarray,
    ) -> None:
        keys = np.asarray(k, dtype=np.float32)
        values = np.asarray(v, dtype=np.float32)
        if keys.shape == (self.kv_heads, self.head_dim):
            keys = keys[None, ...]
            values = values[None, ...]
        expected_tail = (self.kv_heads, self.head_dim)
        if keys.ndim != 3 or keys.shape[1:] != expected_tail or values.shape != keys.shape:
            raise ValueError(f"K and V must have shape [tokens,{self.kv_heads},{self.head_dim}]")
        key = (int(sequence_id), int(layer_id))
        table = self._tables.setdefault(key, [])
        length = self._lengths.get(key, 0)
        for token_k, token_v in zip(keys, values, strict=True):
            logical_page = length // self.page_tokens
            offset = length % self.page_tokens
            if logical_page == len(table):
                table.append(self._new_page())
            page_id = table[logical_page]
            if self._pages[page_id].refcount > 1:
                page_id = self._copy_page(page_id)
                table[logical_page] = page_id
            page = self._pages[page_id]
            if self.storage_format == "bf16":
                page.k[offset] = bf16_round(token_k)
                page.v[offset] = bf16_round(token_v)
            else:
                qk, sk = quantize_int8_symmetric(token_k, axis=1)
                qv, sv = quantize_int8_symmetric(token_v, axis=1)
                page.k[offset] = qk
                page.v[offset] = qv
                assert page.k_scale is not None and page.v_scale is not None
                page.k_scale[offset] = sk
                page.v_scale[offset] = sv
            length += 1
            self.written_tokens += 1
        self._lengths[key] = length

    def read(
        self,
        sequence_id: int,
        layer_id: int,
        *,
        upto: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        key = (int(sequence_id), int(layer_id))
        length = self._lengths.get(key, 0)
        count = length if upto is None else min(int(upto), length)
        if count < 0:
            raise ValueError("upto must be non-negative")
        out_k = np.empty((count, self.kv_heads, self.head_dim), dtype=np.float32)
        out_v = np.empty_like(out_k)
        table = self._tables.get(key, [])
        for token in range(count):
            page_id = table[token // self.page_tokens]
            offset = token % self.page_tokens
            page = self._pages[page_id]
            if self.storage_format == "bf16":
                out_k[token] = page.k[offset]
                out_v[token] = page.v[offset]
            else:
                assert page.k_scale is not None and page.v_scale is not None
                out_k[token] = page.k[offset].astype(np.float32) * page.k_scale[offset]
                out_v[token] = page.v[offset].astype(np.float32) * page.v_scale[offset]
        self.read_tokens += count
        return out_k, out_v

    def share_prefix(
        self,
        source_sequence: int,
        destination_sequence: int,
        layer_id: int,
        tokens: int,
    ) -> None:
        src_key = (int(source_sequence), int(layer_id))
        dst_key = (int(destination_sequence), int(layer_id))
        if dst_key in self._tables or dst_key in self._lengths:
            raise ValueError("destination sequence/layer is not empty")
        src_length = self._lengths.get(src_key, 0)
        if tokens < 0 or tokens > src_length:
            raise ValueError("requested shared prefix exceeds source length")
        full_pages, remainder = divmod(tokens, self.page_tokens)
        src_table = self._tables.get(src_key, [])
        dst_table: list[int] = []
        for index in range(full_pages):
            page_id = src_table[index]
            self._pages[page_id].refcount += 1
            dst_table.append(page_id)
        if remainder:
            src_id = src_table[full_pages]
            dst_id = self._new_page()
            src_page = self._pages[src_id]
            dst_page = self._pages[dst_id]
            dst_page.k[:remainder] = src_page.k[:remainder]
            dst_page.v[:remainder] = src_page.v[:remainder]
            if dst_page.k_scale is not None and src_page.k_scale is not None:
                dst_page.k_scale[:remainder] = src_page.k_scale[:remainder]
                dst_page.v_scale[:remainder] = src_page.v_scale[:remainder]
            dst_table.append(dst_id)
        self._tables[dst_key] = dst_table
        self._lengths[dst_key] = tokens

    def fork_sequence(
        self,
        source_sequence: int,
        destination_sequence: int,
        layer_id: int,
    ) -> None:
        """Share the complete current KV state, including a partial tail page.

        This models beam/request branching.  A later append to either branch
        invokes copy-on-write when the tail page is shared.
        """

        src_key = (int(source_sequence), int(layer_id))
        dst_key = (int(destination_sequence), int(layer_id))
        if dst_key in self._tables or dst_key in self._lengths:
            raise ValueError("destination sequence/layer is not empty")
        src_table = self._tables.get(src_key, [])
        for page_id in src_table:
            self._pages[page_id].refcount += 1
        self._tables[dst_key] = list(src_table)
        self._lengths[dst_key] = self._lengths.get(src_key, 0)

    def free_sequence(self, sequence_id: int, layer_ids: Iterable[int] | None = None) -> None:
        seq = int(sequence_id)
        keys = [key for key in self._tables if key[0] == seq]
        if layer_ids is not None:
            allowed = {int(x) for x in layer_ids}
            keys = [key for key in keys if key[1] in allowed]
        for key in keys:
            for page_id in self._tables.pop(key):
                self._release_page(page_id)
            self._lengths.pop(key, None)

    def block_table(self, sequence_id: int, layer_id: int) -> tuple[int, ...]:
        return tuple(self._tables.get((int(sequence_id), int(layer_id)), []))

    def length(self, sequence_id: int, layer_id: int) -> int:
        return self._lengths.get((int(sequence_id), int(layer_id)), 0)

    @property
    def pages_in_use(self) -> int:
        return len(self._pages)

    @property
    def free_pages(self) -> int:
        return len(self._free)

    def check_invariants(self) -> None:
        if len(set(self._free)) != len(self._free):
            raise AssertionError("duplicate page in free list")
        if set(self._free).intersection(self._pages):
            raise AssertionError("page appears in both free and allocated sets")
        if len(self._free) + len(self._pages) != self.physical_pages:
            raise AssertionError("physical page accounting mismatch")
        observed: Dict[int, int] = {page_id: 0 for page_id in self._pages}
        for table in self._tables.values():
            for page_id in table:
                if page_id not in observed:
                    raise AssertionError("block table references a free/nonexistent page")
                observed[page_id] += 1
        for page_id, page in self._pages.items():
            if observed[page_id] != page.refcount:
                raise AssertionError(
                    f"page {page_id} refcount mismatch: table={observed[page_id]} page={page.refcount}"
                )
