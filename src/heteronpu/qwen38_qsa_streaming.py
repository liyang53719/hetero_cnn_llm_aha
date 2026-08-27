"""Hardware-oriented QSA block-summary and streaming-selection reference.

The official eager path recomputes a mean key for every complete compressed
block at each query.  The equivalent hardware path stores the normalized,
rotated block summary when the block closes, then scans those summaries with a
bounded top-k selector.  No full score vector is materialized.

This is E0 numerical/state semantics, not an RTL or performance claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import math
import random
import struct
from typing import Callable, Sequence

Vector = tuple[float, ...]
CastFn = Callable[[float], float]


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def dot_f32(lhs: Sequence[float], rhs: Sequence[float]) -> float:
    if len(lhs) != len(rhs):
        raise ValueError("dot width mismatch")
    acc = 0.0
    for x, y in zip(lhs, rhs, strict=True):
        acc = f32(acc + f32(f32(x) * f32(y)))
    return acc


def l2norm_f32(values: Sequence[float], eps: float = 1e-6) -> Vector:
    if not values:
        raise ValueError("empty vector")
    acc = 0.0
    for value in values:
        acc = f32(acc + f32(f32(value) * f32(value)))
    inv = f32(1.0 / math.sqrt(max(acc, eps)))
    return tuple(f32(f32(value) * inv) for value in values)


def rope_f32(values: Sequence[float], position: int, rotary_dim: int, theta: float = 1_000_000.0) -> Vector:
    vector = tuple(f32(value) for value in values)
    if rotary_dim == 0:
        return vector
    if rotary_dim < 0 or rotary_dim > len(vector) or rotary_dim % 2:
        raise ValueError("invalid rotary dimension")
    head = vector[:rotary_dim]
    half = rotary_dim // 2
    rotated = tuple(-value for value in head[half:]) + head[:half]
    cosine: list[float] = []
    sine: list[float] = []
    for index in range(half):
        frequency = 1.0 / (theta ** (2.0 * index / rotary_dim))
        angle = position * frequency
        cosine.append(f32(math.cos(angle)))
        sine.append(f32(math.sin(angle)))
    cosine += cosine
    sine += sine
    result = [
        f32(f32(x) * c + f32(y) * s)
        for x, y, c, s in zip(head, rotated, cosine, sine, strict=True)
    ]
    return tuple(result) + vector[rotary_dim:]


@dataclass(frozen=True)
class QSAIndexConfig:
    index_head_dim: int = 128
    index_query_heads: int = 4
    compress_ratio: int = 4
    token_budget: int = 2048
    rotary_dim: int = 64
    page_tokens: int = 16

    def __post_init__(self) -> None:
        if self.index_head_dim <= 0 or self.index_query_heads <= 0:
            raise ValueError("invalid index geometry")
        if self.compress_ratio <= 0:
            raise ValueError("compress_ratio")
        if self.token_budget <= 0 or self.token_budget % self.compress_ratio:
            raise ValueError("token budget must be a positive multiple of compression ratio")
        if self.rotary_dim < 0 or self.rotary_dim > self.index_head_dim or self.rotary_dim % 2:
            raise ValueError("rotary_dim")
        if self.page_tokens <= 0:
            raise ValueError("page_tokens")

    @property
    def block_topk(self) -> int:
        return self.token_budget // self.compress_ratio


@dataclass(frozen=True)
class BlockKey:
    block_id: int
    first_token: int
    key: Vector


@dataclass
class BlockKeyStore:
    config: QSAIndexConfig
    storage_cast: CastFn = f32
    complete_blocks: list[BlockKey] = field(default_factory=list)
    tail_raw_keys: list[Vector] = field(default_factory=list)
    token_count: int = 0

    def append(self, raw_key: Sequence[float]) -> BlockKey | None:
        cfg = self.config
        if len(raw_key) != cfg.index_head_dim:
            raise ValueError("raw index-key width")
        self.tail_raw_keys.append(tuple(self.storage_cast(f32(value)) for value in raw_key))
        self.token_count += 1
        if len(self.tail_raw_keys) < cfg.compress_ratio:
            return None
        if len(self.tail_raw_keys) != cfg.compress_ratio:
            raise AssertionError("tail overflow")

        first = self.token_count - cfg.compress_ratio
        pooled: list[float] = []
        for dim in range(cfg.index_head_dim):
            acc = 0.0
            for key in self.tail_raw_keys:
                acc = f32(acc + f32(key[dim]))
            pooled.append(self.storage_cast(f32(acc / cfg.compress_ratio)))
        key = rope_f32(l2norm_f32(pooled), first, cfg.rotary_dim)
        block = BlockKey(len(self.complete_blocks), first, key)
        self.complete_blocks.append(block)
        self.tail_raw_keys.clear()
        return block


@dataclass
class StreamingTopK:
    """Deterministic bounded top-k: high score wins, low block ID wins ties."""

    capacity: int
    _heap: list[tuple[float, int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.capacity < 0:
            raise ValueError("capacity")

    def offer(self, score: float, block_id: int) -> None:
        if self.capacity == 0:
            return
        # heap root is the current worst winner.  For equal score, a larger
        # block ID is worse, represented by a smaller -block_id.
        item = (f32(score), -int(block_id), int(block_id))
        if len(self._heap) < self.capacity:
            heapq.heappush(self._heap, item)
        elif item[:2] > self._heap[0][:2]:
            heapq.heapreplace(self._heap, item)

    def winners(self) -> tuple[tuple[float, int], ...]:
        return tuple((score, block_id) for score, _, block_id in sorted(self._heap, key=lambda item: (-item[0], item[2])))


@dataclass(frozen=True)
class GatherBurst:
    first_page: int
    page_count: int
    tokens: tuple[int, ...]


@dataclass(frozen=True)
class GatherPlan:
    selected_tokens: tuple[int, ...]
    memory_order_tokens: tuple[int, ...]
    restore_indices: tuple[int, ...]
    bursts: tuple[GatherBurst, ...]

    def restore(self, values: Sequence[object]) -> tuple[object, ...]:
        if len(values) != len(self.memory_order_tokens):
            raise ValueError("gather result length")
        return tuple(values[index] for index in self.restore_indices)


def coalesce_selected_tokens(selected_tokens: Sequence[int], page_tokens: int = 16) -> GatherPlan:
    selected = tuple(int(token) for token in selected_tokens)
    if page_tokens <= 0 or any(token < 0 for token in selected):
        raise ValueError("invalid sparse gather")
    if len(set(selected)) != len(selected):
        raise ValueError("duplicate selected token")

    indexed = sorted(enumerate(selected), key=lambda pair: (pair[1] // page_tokens, pair[1] % page_tokens))
    memory_order = tuple(token for _, token in indexed)
    original_to_memory = {original: memory for memory, (original, _) in enumerate(indexed)}
    restore = tuple(original_to_memory[index] for index in range(len(selected)))

    page_groups: list[tuple[int, list[int]]] = []
    for token in memory_order:
        page = token // page_tokens
        if not page_groups or page_groups[-1][0] != page:
            page_groups.append((page, [token]))
        else:
            page_groups[-1][1].append(token)
    bursts: list[GatherBurst] = []
    cursor = 0
    while cursor < len(page_groups):
        first_page = page_groups[cursor][0]
        end = cursor
        tokens: list[int] = []
        while end < len(page_groups) and page_groups[end][0] == first_page + (end - cursor):
            tokens.extend(page_groups[end][1])
            end += 1
        bursts.append(GatherBurst(first_page, end - cursor, tuple(tokens)))
        cursor = end
    return GatherPlan(selected, memory_order, restore, tuple(bursts))


@dataclass(frozen=True)
class SelectionResult:
    selected_tokens: tuple[int, ...]
    ranked_blocks: tuple[tuple[float, int], ...]
    gather: GatherPlan
    blocks_scanned: int
    score_materialization_bytes: int = 0


@dataclass
class QSAStreamingSelector:
    config: QSAIndexConfig
    store: BlockKeyStore | None = None

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = BlockKeyStore(self.config)
        elif self.store.config != self.config:
            raise ValueError("store/config mismatch")

    def append(self, raw_key: Sequence[float]) -> BlockKey | None:
        assert self.store is not None
        return self.store.append(raw_key)

    def select(self, index_queries: Sequence[Sequence[float]], position: int) -> SelectionResult:
        cfg = self.config
        store = self.store
        assert store is not None
        if position != store.token_count - 1:
            raise ValueError("position must be the most recently appended token")
        if len(index_queries) != cfg.index_query_heads:
            raise ValueError("index query-head count")

        queries = tuple(rope_f32(l2norm_f32(query), position, cfg.rotary_dim) for query in index_queries)
        selector = StreamingTopK(min(cfg.block_topk, len(store.complete_blocks)))
        inv_sqrt = f32(1.0 / math.sqrt(cfg.index_head_dim))
        for block in store.complete_blocks:
            score = 0.0
            for query in queries:
                score = f32(score + max(0.0, dot_f32(query, block.key)))
            selector.offer(f32(score * inv_sqrt), block.block_id)

        ranked = selector.winners()
        selected: list[int] = []
        for _, block_id in ranked:
            start = block_id * cfg.compress_ratio
            selected.extend(range(start, start + cfg.compress_ratio))
        complete_tokens = len(store.complete_blocks) * cfg.compress_ratio
        selected.extend(range(complete_tokens, store.token_count))
        selected_tuple = tuple(selected)
        return SelectionResult(
            selected_tuple,
            ranked,
            coalesce_selected_tokens(selected_tuple, cfg.page_tokens),
            len(store.complete_blocks),
        )


def reference_select(
    config: QSAIndexConfig,
    index_queries: Sequence[Sequence[float]],
    raw_keys: Sequence[Sequence[float]],
    position: int,
    storage_cast: CastFn = f32,
) -> tuple[int, ...]:
    """Raw-key recomputation oracle matching the official eager order."""

    if position != len(raw_keys) - 1:
        raise ValueError("position/raw-key mismatch")
    visible = tuple(range(position + 1))
    complete = len(visible) // config.compress_ratio
    queries = tuple(rope_f32(l2norm_f32(query), position, config.rotary_dim) for query in index_queries)
    inv_sqrt = f32(1.0 / math.sqrt(config.index_head_dim))
    scored: list[tuple[float, int]] = []
    for block_id in range(complete):
        token_ids = visible[block_id * config.compress_ratio : (block_id + 1) * config.compress_ratio]
        pooled: list[float] = []
        for dim in range(config.index_head_dim):
            acc = 0.0
            for token in token_ids:
                acc = f32(acc + f32(raw_keys[token][dim]))
            pooled.append(storage_cast(f32(acc / config.compress_ratio)))
        key = rope_f32(l2norm_f32(pooled), token_ids[0], config.rotary_dim)
        score = 0.0
        for query in queries:
            score = f32(score + max(0.0, dot_f32(query, key)))
        scored.append((f32(score * inv_sqrt), block_id))

    ranked = sorted(scored, key=lambda item: (-item[0], item[1]))[: min(config.block_topk, complete)]
    selected: list[int] = []
    for _, block_id in ranked:
        selected.extend(visible[block_id * config.compress_ratio : (block_id + 1) * config.compress_ratio])
    selected.extend(visible[complete * config.compress_ratio :])
    return tuple(selected)


def run_random_parity(cases: int = 200, seed: int = 3803) -> dict[str, int | str]:
    rng = random.Random(seed)
    comparisons = 0
    max_blocks = 0
    for _ in range(cases):
        dim = rng.choice((2, 4, 8, 16))
        ratio = rng.choice((2, 4))
        heads = rng.choice((1, 2, 4))
        budget = ratio * rng.choice((1, 2, 4, 8))
        rotary = min(dim, 4 if dim >= 4 else dim)
        config = QSAIndexConfig(dim, heads, ratio, budget, rotary, 16)
        streaming = QSAStreamingSelector(config)
        raw_keys: list[Vector] = []
        for position in range(rng.randint(1, 128)):
            key = tuple(f32(rng.uniform(-2.0, 2.0)) for _ in range(dim))
            raw_keys.append(key)
            streaming.append(key)
            queries = tuple(tuple(f32(rng.uniform(-2.0, 2.0)) for _ in range(dim)) for _ in range(heads))
            expected = reference_select(config, queries, raw_keys, position)
            actual = streaming.select(queries, position)
            if actual.selected_tokens != expected:
                raise AssertionError(f"selection mismatch at position {position}")
            if actual.gather.restore(actual.gather.memory_order_tokens) != actual.selected_tokens:
                raise AssertionError("gather restore mismatch")
            if actual.score_materialization_bytes != 0:
                raise AssertionError("score materialization")
            comparisons += 1
            max_blocks = max(max_blocks, actual.blocks_scanned)
    return {
        "schema_version": 1,
        "status": "PASS",
        "cases": cases,
        "comparisons": comparisons,
        "max_blocks_scanned": max_blocks,
        "score_materialization_bytes": 0,
    }
