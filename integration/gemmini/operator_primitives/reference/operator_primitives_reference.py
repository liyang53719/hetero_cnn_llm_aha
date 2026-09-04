"""Pure-Python reference models for HeteroNPU operator primitives.

These models intentionally describe ordering, address generation and state
semantics rather than RTL timing.  They are used in the sandbox where the
pinned Chisel/CIRCT toolchain is unavailable; the local agent reruns the same
vectors against generated RTL.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct
from typing import Iterable, Sequence

MASK64 = (1 << 64) - 1


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def fp32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", f32(value)))[0]


def bits_fp32(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits & 0xFFFF_FFFF))[0]


def fp32_is_nan(bits: int) -> bool:
    return ((bits >> 23) & 0xFF) == 0xFF and (bits & 0x7F_FFFF) != 0


def fp32_order_key(bits: int) -> int:
    bits &= 0xFFFF_FFFF
    # IEEE-754 compares -0.0 and +0.0 equal. Canonicalize both encodings so
    # the deterministic ordering rule falls through to ascending item index.
    if bits & 0x7FFF_FFFF == 0:
        bits = 0
    return (~bits & 0xFFFF_FFFF) if (bits >> 31) else (bits ^ 0x8000_0000)


def ranked_better(a_score: int, a_index: int, b_score: int, b_index: int) -> bool:
    a_nan = fp32_is_nan(a_score)
    b_nan = fp32_is_nan(b_score)
    if a_nan != b_nan:
        return not a_nan
    if not a_nan:
        a_key = fp32_order_key(a_score)
        b_key = fp32_order_key(b_score)
        if a_key != b_key:
            return a_key > b_key
    return a_index < b_index


def stable_topk(items: Sequence[tuple[int, int]], k: int) -> tuple[tuple[int, int], ...]:
    if not 0 < k <= len(items):
        raise ValueError("invalid k")
    result: list[tuple[int, int]] = []
    for candidate in items:
        insert_at = len(result)
        for rank, resident in enumerate(result):
            if ranked_better(candidate[0], candidate[1], resident[0], resident[1]):
                insert_at = rank
                break
        result.insert(insert_at, candidate)
        if len(result) > k:
            result.pop()
    return tuple(result)


def restoring_divide(dividend: int, divisor: int, width: int = 64) -> tuple[int, int]:
    if width <= 1:
        raise ValueError("width")
    mask = (1 << width) - 1
    dividend &= mask
    divisor &= mask
    if divisor == 0:
        return mask, dividend
    quotient = 0
    remainder = 0
    for bit in range(width - 1, -1, -1):
        remainder = (remainder << 1) | ((dividend >> bit) & 1)
        quotient <<= 1
        if remainder >= divisor:
            remainder -= divisor
            quotient |= 1
    return quotient & mask, remainder & mask


def shift_add_multiply(left: int, right: int, width: int = 32) -> int:
    mask = (1 << width) - 1
    product_mask = (1 << (2 * width)) - 1
    multiplicand = left & mask
    multiplier = right & mask
    accumulator = 0
    for _ in range(width):
        if multiplier & 1:
            accumulator = (accumulator + multiplicand) & product_mask
        multiplicand = (multiplicand << 1) & product_mask
        multiplier >>= 1
    return accumulator


@dataclass(frozen=True)
class CausalConvTap:
    token: int
    channel: int
    tap: int
    use_current: bool
    history_valid: bool
    read_slot: int
    write_slot: int
    last: bool


def causal_conv_schedule(
    token_count: int,
    channels: int,
    kernel: int,
    dilation: int,
    initial_valid_tokens: int = 0,
    initial_write_slot: int = 0,
) -> tuple[CausalConvTap, ...]:
    if min(token_count, channels, dilation) <= 0 or kernel < 2:
        raise ValueError("invalid causal-conv geometry")
    depth = (kernel - 1) * dilation
    if not 0 <= initial_write_slot < depth:
        raise ValueError("write slot")
    slot = initial_write_slot
    out: list[CausalConvTap] = []
    for token in range(token_count):
        available = min(depth, initial_valid_tokens + token)
        for channel in range(channels):
            for tap in range(kernel):
                past = tap * dilation
                read_slot = (slot - past) % depth
                out.append(
                    CausalConvTap(
                        token,
                        channel,
                        tap,
                        tap == 0,
                        tap == 0 or past <= available,
                        read_slot,
                        slot,
                        token == token_count - 1
                        and channel == channels - 1
                        and tap == kernel - 1,
                    )
                )
        slot = (slot + 1) % depth
    return tuple(out)


GDN_PASSES = ("decay", "key_readout", "outer_update", "query_readout")


def gdn_state_schedule(heads: int, key_dim: int, value_dim: int) -> tuple[tuple[str, int, int, int, bool], ...]:
    if min(heads, key_dim, value_dim) <= 0:
        raise ValueError("invalid GDN geometry")
    out = []
    for pass_name in GDN_PASSES:
        for head in range(heads):
            for key in range(key_dim):
                for value in range(value_dim):
                    out.append((pass_name, head, key, value, pass_name in {"decay", "outer_update"}))
    return tuple(out)


NORM_PASSES = {
    "rms": ("square_sum", "normalize"),
    "group_rms": ("square_sum", "normalize"),
    "layer_norm": ("sum", "square_sum", "normalize"),
    "l2_norm": ("square_sum", "normalize"),
}


def norm_schedule(mode: str, groups: int, elements_per_group: int) -> tuple[tuple[str, int, int], ...]:
    if mode not in NORM_PASSES or groups <= 0 or elements_per_group <= 0:
        raise ValueError("invalid norm")
    return tuple(
        (pass_name, group, element)
        for pass_name in NORM_PASSES[mode]
        for group in range(groups)
        for element in range(elements_per_group)
    )


def gated_residual_schedule(branches: int, hidden: int) -> tuple[tuple[int, int], ...]:
    if branches <= 0 or hidden <= 0:
        raise ValueError("invalid gated residual")
    return tuple((branch, dim) for branch in range(branches) for dim in range(hidden))


@dataclass
class StateTransactionReference:
    domain_count: int = 16
    active: bool = False
    transaction: int = 0
    generation: int = 0
    dirty_mask: int = 0
    protocol_error: bool = False

    def begin(self, transaction: int) -> tuple[str, int, int, int] | None:
        if self.active:
            self.protocol_error = True
            return None
        self.active = True
        self.transaction = transaction
        self.dirty_mask = 0
        return ("begin", transaction, self.generation, 0)

    def mark_dirty(self, transaction: int, domain: int) -> None:
        if not self.active or transaction != self.transaction or not 0 <= domain < self.domain_count:
            self.protocol_error = True
            return
        self.dirty_mask |= 1 << domain

    def finish(self, transaction: int, rollback: bool) -> tuple[str, int, int, int] | None:
        if not self.active or transaction != self.transaction:
            self.protocol_error = True
            return None
        mask = self.dirty_mask
        self.generation += 1
        self.active = False
        self.dirty_mask = 0
        return ("rollback" if rollback else "commit", transaction, self.generation, mask)


def mtp_verify(draft: Sequence[int], target: Sequence[int]) -> dict[str, int | bool]:
    if len(draft) != len(target) or not draft:
        raise ValueError("MTP vectors")
    accepted = 0
    mismatch = len(draft)
    for step, (a, b) in enumerate(zip(draft, target, strict=True)):
        if mismatch == len(draft) and a == b:
            accepted += 1
        elif mismatch == len(draft):
            mismatch = step
    return {
        "accepted_count": accepted,
        "mismatch_step": mismatch,
        "all_match": mismatch == len(draft),
        "rollback": mismatch != len(draft),
    }


def ple_hash_rows(
    tokens: Sequence[int],
    *,
    ngram_size: int,
    heads_per_ngram: int,
    sizes: Sequence[int],
    offsets: Sequence[int],
    multipliers: Sequence[int],
    sentinel: int = 0,
) -> tuple[tuple[int, ...], ...]:
    head_count = (ngram_size - 1) * heads_per_ngram
    if ngram_size < 2 or len(sizes) != head_count or len(offsets) != head_count:
        raise ValueError("PLE geometry")
    if any(size <= 0 for size in sizes):
        raise ValueError("PLE size")
    out = []
    for position in range(len(tokens)):
        rows = []
        for n in range(2, ngram_size + 1):
            mixed = 0
            for shift in range(n):
                token = sentinel if position - shift < 0 else int(tokens[position - shift])
                term = (token * int(multipliers[shift])) & MASK64
                mixed = term if shift == 0 else mixed ^ term
            start = (n - 2) * heads_per_ngram
            for head in range(start, start + heads_per_ngram):
                rows.append(int(offsets[head]) + mixed % int(sizes[head]))
        out.append(tuple(rows))
    return tuple(out)


def tagged_gather_reorder(
    requests: Sequence[tuple[int, int, int, bool]],
    response_order: Sequence[int],
) -> tuple[tuple[int, int, int, bool], ...]:
    if sorted(response_order) != list(range(len(requests))):
        raise ValueError("response permutation")
    response_data = {slot: (requests[slot][0] ^ 0x5A5A_5A5A) for slot in response_order}
    return tuple(
        (response_data[slot], request[1], request[2], request[3])
        for slot, request in enumerate(requests)
    )


def moe_route_merge(
    weights: Sequence[float],
    results: Sequence[Sequence[float]],
    response_order: Sequence[int],
) -> tuple[float, ...]:
    if len(weights) != len(results) or sorted(response_order) != list(range(len(results))):
        raise ValueError("MoE routes")
    returned = {route: tuple(map(f32, results[route])) for route in response_order}
    width = len(results[0])
    accumulator = [0.0] * width
    for route, weight in enumerate(weights):
        for dim in range(width):
            accumulator[dim] = f32(accumulator[dim] + f32(f32(weight) * returned[route][dim]))
    return tuple(accumulator)


def qsa_selected_tokens(
    block_scores: Sequence[int],
    *,
    block_topk: int,
    compress_ratio: int,
    tail_count: int,
) -> tuple[int, ...]:
    if compress_ratio <= 0 or not 0 <= tail_count < compress_ratio:
        raise ValueError("QSA geometry")
    complete_blocks = len(block_scores)
    selected: list[int] = []
    if complete_blocks:
        ranked = stable_topk(tuple((score, index) for index, score in enumerate(block_scores)), min(block_topk, complete_blocks))
        for _, block in ranked:
            selected.extend(range(block * compress_ratio, (block + 1) * compress_ratio))
    selected.extend(range(complete_blocks * compress_ratio, complete_blocks * compress_ratio + tail_count))
    return tuple(selected)


def block_pool_schedule(blocks: int, ratio: int, dimensions: int) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        (block, block * ratio + within, dim)
        for block in range(blocks)
        for dim in range(dimensions)
        for within in range(ratio)
    )


def mrope_map(pair_count: int, height_pairs: int, width_pairs: int) -> tuple[tuple[int, str, int], ...]:
    if pair_count <= 0 or height_pairs > pair_count or width_pairs > pair_count:
        raise ValueError("MRoPE geometry")
    height_used = 0
    width_used = 0
    out = []
    for pair in range(pair_count):
        phase = pair % 3
        if phase == 1 and height_used < height_pairs:
            out.append((pair, "height", height_used))
            height_used += 1
        elif phase == 2 and width_used < width_pairs:
            out.append((pair, "width", width_used))
            width_used += 1
        else:
            out.append((pair, "temporal", pair))
    return tuple(out)


def vision_window_schedule(
    temporal: int,
    height: int,
    width: int,
    padded_height: int,
    padded_width: int,
    window_height: int,
    window_width: int,
) -> tuple[tuple[int, int, int, bool], ...]:
    if min(temporal, height, width, window_height, window_width) <= 0:
        raise ValueError("window geometry")
    out = []
    for t in range(temporal):
        for base_y in range(0, padded_height, window_height):
            for base_x in range(0, padded_width, window_width):
                for in_y in range(window_height):
                    for in_x in range(window_width):
                        y = base_y + in_y
                        x = base_x + in_x
                        out.append((t, y, x, y >= height or x >= width))
    return tuple(out)


def vision_patch_merge_schedule(
    temporal: int,
    height: int,
    width: int,
    merge_height: int,
    merge_width: int,
) -> tuple[tuple[int, int, int, int, bool], ...]:
    out = []
    output_patch = 0
    for t in range(temporal):
        for base_y in range(0, height, merge_height):
            for base_x in range(0, width, merge_width):
                for in_y in range(merge_height):
                    for in_x in range(merge_width):
                        y = base_y + in_y
                        x = base_x + in_x
                        out.append((t, y, x, output_patch, y < height and x < width))
                output_patch += 1
    return tuple(out)


def bilinear_index(
    destination_y: int,
    destination_x: int,
    source_height: int,
    source_width: int,
    destination_height: int,
    destination_width: int,
    fraction_bits: int = 16,
) -> tuple[int, int, int, int, int, int]:
    if min(source_height, source_width, destination_height, destination_width) <= 0:
        raise ValueError("bilinear geometry")
    y_fixed = 0 if destination_height <= 1 else (
        destination_y * (source_height - 1) << fraction_bits
    ) // (destination_height - 1)
    x_fixed = 0 if destination_width <= 1 else (
        destination_x * (source_width - 1) << fraction_bits
    ) // (destination_width - 1)
    y0 = y_fixed >> fraction_bits
    x0 = x_fixed >> fraction_bits
    y1 = min(y0 + 1, source_height - 1)
    x1 = min(x0 + 1, source_width - 1)
    mask = (1 << fraction_bits) - 1
    return y0, y1, x0, x1, y_fixed & mask, x_fixed & mask


def vision_patch3d_schedule(
    output_temporal: int,
    output_height: int,
    output_width: int,
    channels: int,
    kernel_temporal: int,
    kernel_height: int,
    kernel_width: int,
    stride_temporal: int,
    stride_height: int,
    stride_width: int,
) -> tuple[tuple[int, ...], ...]:
    out = []
    for ot in range(output_temporal):
        for oy in range(output_height):
            for ox in range(output_width):
                for channel in range(channels):
                    for kt in range(kernel_temporal):
                        for ky in range(kernel_height):
                            for kx in range(kernel_width):
                                out.append((
                                    ot, oy, ox,
                                    ot * stride_temporal + kt,
                                    oy * stride_height + ky,
                                    ox * stride_width + kx,
                                    channel, kt, ky, kx,
                                ))
    return tuple(out)


def pwl_segment(input_bits: int, breakpoint_bits: Sequence[int]) -> int:
    if len(breakpoint_bits) < 1:
        raise ValueError("breakpoints")
    if fp32_is_nan(input_bits):
        return len(breakpoint_bits)
    key = fp32_order_key(input_bits)
    for index, breakpoint in enumerate(breakpoint_bits):
        if key < fp32_order_key(breakpoint):
            return index
    return len(breakpoint_bits)


def sigmoid(value: float) -> float:
    x = f32(value)
    z = f32(math.exp(-abs(x)))
    reciprocal = f32(1.0 / f32(1.0 + z))
    return reciprocal if x >= 0.0 else f32(z * reciprocal)


def softplus(value: float) -> float:
    x = f32(value)
    if x > 20.0:
        return x
    if x < -20.0:
        return f32(math.exp(x))
    return f32(math.log1p(math.exp(x)))


def l2norm(vector: Sequence[float], epsilon: float = 1e-6) -> tuple[float, ...]:
    total = 0.0
    for value in vector:
        total = f32(total + f32(f32(value) * f32(value)))
    inv = f32(1.0 / math.sqrt(f32(total + epsilon)))
    return tuple(f32(f32(value) * inv) for value in vector)


def dot(left: Sequence[float], right: Sequence[float]) -> float:
    total = 0.0
    for a, b in zip(left, right, strict=True):
        total = f32(total + f32(f32(a) * f32(b)))
    return total


def gdn_recurrent_step(
    matrix: Sequence[Sequence[float]],
    query: Sequence[float],
    key: Sequence[float],
    value: Sequence[float],
    a: float,
    b: float,
    a_log: float,
    dt_bias: float,
) -> tuple[tuple[float, ...], tuple[tuple[float, ...], ...]]:
    key_dim = len(key)
    value_dim = len(value)
    if len(matrix) != key_dim or any(len(row) != value_dim for row in matrix):
        raise ValueError("GDN matrix")
    q = tuple(f32(x / math.sqrt(key_dim)) for x in l2norm(query))
    k = l2norm(key)
    beta = sigmoid(b)
    decay = f32(math.exp(f32(-f32(math.exp(f32(a_log))) * softplus(f32(a + dt_bias)))))
    state = [[f32(f32(x) * decay) for x in row] for row in matrix]
    memory = [dot([state[i][j] for i in range(key_dim)], k) for j in range(value_dim)]
    delta = [f32(f32(value[j] - memory[j]) * beta) for j in range(value_dim)]
    for i in range(key_dim):
        for j in range(value_dim):
            state[i][j] = f32(state[i][j] + f32(k[i] * delta[j]))
    output = tuple(dot([state[i][j] for i in range(key_dim)], q) for j in range(value_dim))
    return output, tuple(tuple(row) for row in state)


COMPOSITE_LEAF_SEQUENCES: dict[str, tuple[str, ...]] = {
    "SfuExp": ("SfuMul", "SfuExp2"),
    "SfuSigmoid": (
        "SfuAbs", "SfuNegate", "SfuMul", "SfuExp2",
        "SfuAdd", "SfuReciprocal", "SfuMul", "SfuCompareSelect",
    ),
    "SfuSoftplus": ("SfuPwl",),
    "SfuSilu": (
        "SfuAbs", "SfuNegate", "SfuMul", "SfuExp2",
        "SfuAdd", "SfuReciprocal", "SfuMul", "SfuCompareSelect", "SfuMul",
    ),
    "SfuGelu": ("SfuPwl",),
}

# Exact root-opcode inventory emitted by HeteroModelOperatorSequencer.  The
# StateCommitOrRollback token denotes a flag-selected terminal alternative.
MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES: dict[str, tuple[str, ...]] = {
    "TokenEmbedding": ("DmaGather",),
    "RmsNorm": ("SfuRmsNorm",),
    "DenseProjection": ("MatrixGemm",),
    "QkvBias": ("SfuAdd",),
    "PartialRope": ("SfuRope",),
    "GqaBroadcast": ("SfuBroadcast",),
    "DenseAttention": ("MatrixQk", "SfuCausalMask", "SfuOnlineSoftmax", "MatrixPv"),
    "AttentionOutputGate": ("SfuSigmoid", "SfuMul"),
    "ResidualAdd": ("SfuAdd",),
    "SiluTimesUp": ("SfuSilu", "SfuMul"),
    "KvAppend": ("KvAppend",),
    "KvGather": ("KvGather",),
    "LmHead": ("MatrixGemv",),
    "MultimodalRope": ("VisionMropeMap", "SfuRope"),
    "LogitsTopK": ("SelectTopK",),
    "PaddingMask": ("SfuGate",),
    "TensorView": ("Barrier",),
    "GdnProjection": ("MatrixGemm",),
    "GdnCausalConv": ("StateConvWindow", "SfuMul", "SfuReduceSum", "SfuSilu"),
    "GdnRecurrentUpdate": (
        "SfuAdd", "SfuSoftplus", "SfuExp", "SfuMul", "SfuExp", "SfuSigmoid",
        "SfuL2Norm", "SfuScale", "SfuL2Norm", "StateRead", "SfuMul", "StateWrite",
        "StateRead", "MatrixGemv", "SfuSub", "SfuMul", "MatrixOuter", "StateWrite",
        "StateRead", "MatrixGemv",
    ),
    "GdnGatedNormOutput": ("SfuRmsNorm", "SfuSilu", "SfuMul", "MatrixGemm"),
    "MoeRouterTopK": (
        "MatrixGemv", "SfuReduceMax", "SfuSub", "SfuScale", "SfuExp2", "SfuReduceSum",
        "SfuReciprocal", "SfuMul", "SelectTopK", "SfuReduceSum", "SfuReciprocal", "SfuMul",
    ),
    "MoeDispatch": ("SelectRoute", "DmaGather"),
    "MoeRoutedExperts": ("MatrixGemm", "SfuSilu", "SfuMul", "MatrixGemm", "SfuScale"),
    "MoeSharedExpert": (
        "MatrixGemm", "SfuSilu", "SfuMul", "MatrixGemm", "MatrixGemv", "SfuSigmoid", "SfuMul",
    ),
    "MoeRouteReduce": ("SelectMerge", "SfuAdd"),
    "MtpStateTransaction": ("StateBegin", "SelectMtpVerify", "StateCommitOrRollback", "Barrier"),
    "GatedResidualRead": (
        "SfuGroupRmsNorm", "MatrixLowRank", "SfuScale", "SfuSilu", "MatrixLowRank",
        "SfuSigmoid", "SfuMul", "SfuReduceSum", "SfuScale", "MatrixGemv", "SfuScale",
        "SfuSigmoid", "SfuScale",
    ),
    "GatedResidualWrite": ("SfuMul", "SfuAdd"),
    "GroupRmsNorm": ("SfuGroupRmsNorm",),
    "PleNgramHash": ("PleHash",),
    "PleSparseRowFetch": ("DmaGather",),
    "PleProjectionDwConv": (
        "MatrixGemm", "MatrixGemm", "SfuGroupRmsNorm", "SfuGroupRmsNorm", "MatrixQk",
        "SfuScale", "SfuAbs", "SfuMax", "SfuRsqrt", "SfuMul", "SfuCompareSelect",
        "SfuSigmoid", "SfuMul", "SfuGroupRmsNorm", "StateConvWindow", "SfuMul",
        "SfuReduceSum", "SfuSilu", "SfuAdd",
    ),
    "QsaIndexProjection": ("MatrixGemm",),
    "QsaBlockSummary": (
        "SfuL2Norm", "SelectBlockPool", "SfuScale", "SfuL2Norm", "SfuRope",
        "SfuRope", "MatrixQk", "SfuMax", "SfuReduceSum", "SfuScale",
    ),
    "QsaStreamingTopK": ("SelectTopK", "SelectExpand"),
    "QsaSparseKvGather": ("KvGather",),
    "QsaSparseAttention": (
        "MatrixGemm", "SfuRmsNorm", "SfuRope", "MatrixGemm", "SfuRmsNorm", "SfuRope",
        "MatrixGemm", "KvAppend", "MatrixQk", "SfuCausalMask", "SfuOnlineSoftmax",
        "MatrixPv", "SfuSigmoid", "SfuMul", "MatrixGemm",
    ),
    "VisionPatchEmbed": ("VisionPatch3d", "MatrixConv", "SfuAdd"),
    "VisionPosition": (
        "VisionPosInterp", "DmaGather", "DmaGather", "DmaGather", "DmaGather",
        "SfuMul", "SfuReduceSum",
    ),
    "VisionLayerNorm": ("SfuLayerNorm",),
    "VisionAttention": (
        "MatrixGemm", "SfuAdd", "VisionMropeMap", "SfuRope", "MatrixQk", "SfuScale",
        "SfuOnlineSoftmax", "MatrixPv", "MatrixGemm", "SfuAdd",
    ),
    "VisionMlpGelu": ("MatrixGemm", "SfuAdd", "SfuGelu", "MatrixGemm", "SfuAdd"),
    "VisionPatchMerge": (
        "VisionPatchMerge", "SfuLayerNorm", "MatrixGemm", "SfuAdd", "SfuGelu",
        "MatrixGemm", "SfuAdd",
    ),
    "VisionProject": ("MatrixGemm", "SfuAdd"),
    "VisionWindowLayout": ("VisionWindow",),
    "VisionDeepstackInject": ("DmaGather", "SfuAdd"),
    "VisionTokenScatter": ("DmaScatter",),
}

TERMINAL_PRIMITIVE_BINDINGS: frozenset[str] = frozenset({
    "Barrier",
    "DmaRead", "DmaWrite", "DmaGather", "DmaScatter",
    "MatrixGemm", "MatrixGemv", "MatrixQk", "MatrixPv", "MatrixOuter", "MatrixConv", "MatrixLowRank",
    "SfuAdd", "SfuSub", "SfuMul", "SfuScale", "SfuReduceSum", "SfuReduceMax",
    "SfuRsqrt", "SfuReciprocal", "SfuExp2", "SfuRmsNorm", "SfuGroupRmsNorm", "SfuRope",
    "SfuOnlineSoftmax", "SfuGate", "SfuL2Norm", "SfuAbs", "SfuMax", "SfuCompareSelect",
    "SfuNegate", "SfuPwl", "SfuBroadcast", "SfuCausalMask", "SfuLayerNorm",
    "KvAppend", "KvGather", "KvAlloc", "KvFree",
    "StateRead", "StateWrite", "StateDecay", "StateConvWindow", "StateBegin", "StateCommit", "StateRollback",
    "SelectTopK", "SelectExpand", "SelectRoute", "SelectMerge", "SelectBlockPool", "SelectMtpVerify",
    "VisionWindow", "VisionPatchMerge", "VisionPosInterp", "PleHash", "VisionPatch3d", "VisionMropeMap",
})

TERMINAL_PRIMITIVE_OWNERS: dict[str, str] = {
    **{name: "Control" for name in ("Barrier",)},
    **{name: "Dma" for name in ("DmaRead", "DmaWrite", "DmaGather", "DmaScatter")},
    **{name: "Matrix" for name in (
        "MatrixGemm", "MatrixGemv", "MatrixQk", "MatrixPv",
        "MatrixOuter", "MatrixConv", "MatrixLowRank",
    )},
    **{name: "Sfu" for name in (
        "SfuAdd", "SfuSub", "SfuMul", "SfuScale", "SfuReduceSum",
        "SfuReduceMax", "SfuRsqrt", "SfuReciprocal", "SfuExp2",
        "SfuRmsNorm", "SfuGroupRmsNorm", "SfuRope", "SfuOnlineSoftmax",
        "SfuGate", "SfuL2Norm", "SfuAbs", "SfuMax", "SfuCompareSelect",
        "SfuNegate", "SfuPwl", "SfuBroadcast", "SfuCausalMask",
        "SfuLayerNorm",
    )},
    **{name: "KvMemory" for name in ("KvAppend", "KvGather", "KvAlloc", "KvFree")},
    **{name: "State" for name in (
        "StateRead", "StateWrite", "StateDecay", "StateConvWindow",
        "StateBegin", "StateCommit", "StateRollback",
    )},
    **{name: "Selection" for name in (
        "SelectTopK", "SelectExpand", "SelectRoute", "SelectMerge",
        "SelectBlockPool", "SelectMtpVerify",
    )},
    **{name: "Vision" for name in (
        "VisionWindow", "VisionPatchMerge", "VisionPosInterp", "PleHash",
        "VisionPatch3d", "VisionMropeMap",
    )},
}
assert set(TERMINAL_PRIMITIVE_OWNERS) == TERMINAL_PRIMITIVE_BINDINGS


def expand_root_opcode(opcode: str) -> tuple[str, ...]:
    if opcode == "StateCommitOrRollback":
        # Both alternatives are bound and selected by command flags.
        return ("StateCommit", "StateRollback")
    return COMPOSITE_LEAF_SEQUENCES.get(opcode, (opcode,))


def terminal_sequence(operator: str) -> tuple[str, ...]:
    root = MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES[operator]
    out: list[str] = []
    for opcode in root:
        out.extend(expand_root_opcode(opcode))
    return tuple(out)


OPERATOR_PHASE_COUNTS: dict[str, int] = {
    "TokenEmbedding": 1, "RmsNorm": 1, "DenseProjection": 1, "QkvBias": 1,
    "PartialRope": 1, "GqaBroadcast": 1, "DenseAttention": 4,
    "AttentionOutputGate": 2, "ResidualAdd": 1, "SiluTimesUp": 2,
    "KvAppend": 1, "KvGather": 1, "LmHead": 1, "MultimodalRope": 2,
    "LogitsTopK": 1, "PaddingMask": 1, "TensorView": 1,
    "GdnProjection": 1, "GdnCausalConv": 4, "GdnRecurrentUpdate": 20,
    "GdnGatedNormOutput": 4, "MoeRouterTopK": 12, "MoeDispatch": 2,
    "MoeRoutedExperts": 5, "MoeSharedExpert": 7, "MoeRouteReduce": 2,
    "MtpStateTransaction": 4, "GatedResidualRead": 13,
    "GatedResidualWrite": 2, "GroupRmsNorm": 1, "PleNgramHash": 1,
    "PleSparseRowFetch": 1, "PleProjectionDwConv": 19,
    "QsaIndexProjection": 1, "QsaBlockSummary": 10,
    "QsaStreamingTopK": 2, "QsaSparseKvGather": 1,
    "QsaSparseAttention": 15, "VisionPatchEmbed": 3, "VisionPosition": 7,
    "VisionLayerNorm": 1, "VisionAttention": 10, "VisionMlpGelu": 5,
    "VisionPatchMerge": 7, "VisionProject": 2, "VisionWindowLayout": 1,
    "VisionDeepstackInject": 2, "VisionTokenScatter": 1,
}

MODEL_REQUIRED_OPERATORS: dict[str, tuple[str, ...]] = {
    "qwen2_1p5b": (
        "TokenEmbedding", "RmsNorm", "DenseProjection", "QkvBias",
        "PartialRope", "GqaBroadcast", "DenseAttention", "ResidualAdd",
        "SiluTimesUp", "KvAppend", "KvGather", "LmHead", "LogitsTopK",
        "PaddingMask", "TensorView",
    ),
    "qwen3_5_35b_a3b": (
        "TokenEmbedding", "RmsNorm", "DenseProjection", "PartialRope",
        "MultimodalRope", "GqaBroadcast", "DenseAttention",
        "AttentionOutputGate", "ResidualAdd", "SiluTimesUp", "KvAppend",
        "KvGather", "GdnProjection", "GdnCausalConv",
        "GdnRecurrentUpdate", "GdnGatedNormOutput", "MoeRouterTopK",
        "MoeDispatch", "MoeRoutedExperts", "MoeSharedExpert",
        "MoeRouteReduce", "MtpStateTransaction", "LmHead", "LogitsTopK",
        "PaddingMask", "TensorView", "VisionPatchEmbed", "VisionPosition",
        "VisionLayerNorm", "VisionAttention", "VisionMlpGelu",
        "VisionPatchMerge", "VisionProject", "VisionWindowLayout",
        "VisionDeepstackInject", "VisionTokenScatter",
    ),
    "qwen3_8_flash_next": (
        "TokenEmbedding", "RmsNorm", "DenseProjection", "PartialRope",
        "MultimodalRope", "GqaBroadcast", "AttentionOutputGate",
        "GdnProjection", "GdnCausalConv", "GdnRecurrentUpdate",
        "GdnGatedNormOutput", "GatedResidualRead", "GatedResidualWrite",
        "GroupRmsNorm", "PleNgramHash", "PleSparseRowFetch",
        "PleProjectionDwConv", "QsaIndexProjection", "QsaBlockSummary",
        "QsaStreamingTopK", "QsaSparseKvGather", "QsaSparseAttention",
        "MoeRouterTopK", "MoeDispatch", "MoeRoutedExperts",
        "MoeSharedExpert", "MoeRouteReduce", "MtpStateTransaction",
        "LmHead", "LogitsTopK", "PaddingMask", "TensorView",
        "VisionPatchEmbed", "VisionPosition", "VisionLayerNorm",
        "VisionAttention", "VisionMlpGelu", "VisionPatchMerge",
        "VisionProject", "VisionWindowLayout", "VisionDeepstackInject",
        "VisionTokenScatter",
    ),
}
