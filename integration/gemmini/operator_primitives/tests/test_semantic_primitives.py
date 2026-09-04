from __future__ import annotations

from functools import cmp_to_key
import math
import random

import pytest

from reference.operator_primitives_reference import (
    COMPOSITE_LEAF_SEQUENCES,
    MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES,
    MODEL_REQUIRED_OPERATORS,
    OPERATOR_PHASE_COUNTS,
    TERMINAL_PRIMITIVE_BINDINGS,
    TERMINAL_PRIMITIVE_OWNERS,
    StateTransactionReference,
    bilinear_index,
    bits_fp32,
    block_pool_schedule,
    causal_conv_schedule,
    f32,
    fp32_bits,
    fp32_is_nan,
    fp32_order_key,
    gated_residual_schedule,
    gdn_recurrent_step,
    gdn_state_schedule,
    mrope_map,
    moe_route_merge,
    mtp_verify,
    norm_schedule,
    ple_hash_rows,
    pwl_segment,
    qsa_selected_tokens,
    ranked_better,
    restoring_divide,
    shift_add_multiply,
    stable_topk,
    tagged_gather_reorder,
    terminal_sequence,
    vision_patch3d_schedule,
    vision_patch_merge_schedule,
    vision_window_schedule,
)


def test_fp32_order_handles_nan_infinity_zero_and_ties() -> None:
    nan_a = 0x7FC00001
    nan_b = 0xFFC00002
    items = (
        (nan_a, 1),
        (fp32_bits(float("-inf")), 2),
        (fp32_bits(-0.0), 3),
        (fp32_bits(+0.0), 4),
        (fp32_bits(float("inf")), 5),
        (fp32_bits(1.0), 8),
        (fp32_bits(1.0), 7),
        (nan_b, 0),
    )
    ranked = stable_topk(items, len(items))
    assert [index for _, index in ranked] == [5, 7, 8, 3, 4, 2, 0, 1]
    assert all(not fp32_is_nan(score) for score, _ in ranked[:-2])


def test_random_stable_topk_matches_independent_comparator() -> None:
    rng = random.Random(0x35_38)

    def compare(left: tuple[int, int], right: tuple[int, int]) -> int:
        if ranked_better(left[0], left[1], right[0], right[1]):
            return -1
        if ranked_better(right[0], right[1], left[0], left[1]):
            return 1
        return 0

    for count in (1, 2, 7, 10, 31, 257):
        for _ in range(20):
            items = []
            for index in range(count):
                value = rng.choice([
                    rng.uniform(-100.0, 100.0),
                    -0.0,
                    +0.0,
                    float("inf"),
                    float("-inf"),
                ])
                items.append((fp32_bits(value), index))
            if count > 3:
                items[rng.randrange(count)] = (0x7FC00001, rng.randrange(count))
            k = rng.randint(1, count)
            expected = tuple(sorted(items, key=cmp_to_key(compare))[:k])
            assert stable_topk(tuple(items), k) == expected


def test_restoring_divide_random_and_zero() -> None:
    rng = random.Random(0xD1D1)
    for width in (8, 16, 32, 64):
        mask = (1 << width) - 1
        assert restoring_divide(17, 0, width) == (mask, 17)
        for _ in range(200):
            dividend = rng.getrandbits(width)
            divisor = rng.getrandbits(width) or 1
            quotient, remainder = restoring_divide(dividend, divisor, width)
            assert quotient == dividend // divisor
            assert remainder == dividend % divisor


def test_shift_add_multiply_random() -> None:
    rng = random.Random(0x800)
    for width in (8, 16, 32):
        mask = (1 << width) - 1
        product_mask = (1 << (2 * width)) - 1
        for _ in range(200):
            left = rng.getrandbits(width)
            right = rng.getrandbits(width)
            assert shift_add_multiply(left, right, width) == ((left & mask) * (right & mask)) & product_mask


def test_causal_conv_schedule_ring_and_validity() -> None:
    schedule = causal_conv_schedule(3, 2, 4, 2, initial_valid_tokens=3, initial_write_slot=1)
    assert len(schedule) == 3 * 2 * 4
    assert schedule[0].use_current and schedule[0].write_slot == 1
    assert [tap.history_valid for tap in schedule[:4]] == [True, True, False, False]
    assert schedule[-1].last
    per_token_slots = [schedule[token * 8].write_slot for token in range(3)]
    assert per_token_slots == [1, 2, 3]


def test_gdn_state_walker_has_four_complete_passes() -> None:
    schedule = gdn_state_schedule(2, 3, 4)
    assert len(schedule) == 4 * 2 * 3 * 4
    for pass_index, name in enumerate(("decay", "key_readout", "outer_update", "query_readout")):
        chunk = schedule[pass_index * 24 : (pass_index + 1) * 24]
        assert {entry[0] for entry in chunk} == {name}
        assert chunk[0][1:4] == (0, 0, 0)
        assert chunk[-1][1:4] == (1, 2, 3)
    assert all(entry[4] for entry in schedule[:24])
    assert not any(entry[4] for entry in schedule[24:48])


def test_norm_modes_and_variable_shapes() -> None:
    assert len(norm_schedule("rms", 1, 1536)) == 3072
    assert len(norm_schedule("group_rms", 4, 2560)) == 20480
    layer = norm_schedule("layer_norm", 2, 8)
    assert len(layer) == 48
    assert [entry[0] for entry in layer[::16]] == ["sum", "square_sum", "normalize"]
    assert len(norm_schedule("l2_norm", 32, 128)) == 8192


def test_gated_residual_address_coverage() -> None:
    schedule = gated_residual_schedule(4, 2560)
    assert len(schedule) == 10240
    assert schedule[0] == (0, 0)
    assert schedule[-1] == (3, 2559)


def test_state_transaction_commit_and_rollback() -> None:
    state = StateTransactionReference(16)
    assert state.begin(7) == ("begin", 7, 0, 0)
    state.mark_dirty(7, 2)
    state.mark_dirty(7, 5)
    assert state.finish(7, rollback=False) == ("commit", 7, 1, (1 << 2) | (1 << 5))
    assert state.begin(8) == ("begin", 8, 1, 0)
    state.mark_dirty(8, 1)
    assert state.finish(8, rollback=True) == ("rollback", 8, 2, 1 << 1)
    assert not state.protocol_error


def test_state_transaction_detects_protocol_errors() -> None:
    state = StateTransactionReference(4)
    state.mark_dirty(1, 0)
    assert state.protocol_error
    state = StateTransactionReference(4)
    state.begin(3)
    state.begin(4)
    assert state.protocol_error


def test_mtp_verify_prefix_semantics() -> None:
    assert mtp_verify([1, 2, 3], [1, 2, 3]) == {
        "accepted_count": 3,
        "mismatch_step": 3,
        "all_match": True,
        "rollback": False,
    }
    assert mtp_verify([1, 9, 3, 4], [1, 2, 3, 4]) == {
        "accepted_count": 1,
        "mismatch_step": 1,
        "all_match": False,
        "rollback": True,
    }


def test_ple_hash_exact_wraparound_xor_and_offsets() -> None:
    tokens = [3, 5, 7, 11]
    sizes = [17, 19, 23, 29]
    offsets = [0, 17, 36, 59]
    multipliers = [0xFFFF_FFFF_FFFF_FFF1, 13, 29]
    rows = ple_hash_rows(
        tokens,
        ngram_size=3,
        heads_per_ngram=2,
        sizes=sizes,
        offsets=offsets,
        multipliers=multipliers,
        sentinel=0,
    )
    assert len(rows) == len(tokens)
    assert all(len(row) == 4 for row in rows)
    for row in rows:
        for head, value in enumerate(row):
            assert offsets[head] <= value < offsets[head] + sizes[head]
    first_bigram_mix = (tokens[0] * multipliers[0]) & ((1 << 64) - 1)
    assert rows[0][0] == offsets[0] + first_bigram_mix % sizes[0]


def test_tagged_gather_reorders_ooo_responses() -> None:
    requests = tuple((0x1000 + i * 64, 100 + i, 7, i == 7) for i in range(8))
    order = (4, 1, 7, 0, 6, 3, 5, 2)
    out = tagged_gather_reorder(requests, order)
    assert [entry[1] for entry in out] == list(range(100, 108))
    assert out[-1][-1]


def test_moe_merge_is_response_order_independent() -> None:
    rng = random.Random(88)
    weights = [f32(0.1), f32(0.2), f32(0.3), f32(0.4)]
    results = [[f32(rng.uniform(-1, 1)) for _ in range(16)] for _ in weights]
    baseline = moe_route_merge(weights, results, [0, 1, 2, 3])
    assert moe_route_merge(weights, results, [3, 1, 0, 2]) == baseline


def test_qsa_block_topk_expansion_and_tail() -> None:
    scores = [fp32_bits(x) for x in (1.0, 7.0, 3.0, 7.0)]
    selected = qsa_selected_tokens(scores, block_topk=2, compress_ratio=4, tail_count=3)
    # Equal 7.0 scores are ordered by lower block index.
    assert selected[:8] == tuple(range(4, 8)) + tuple(range(12, 16))
    assert selected[-3:] == (16, 17, 18)


def test_block_pool_order() -> None:
    schedule = block_pool_schedule(2, 4, 3)
    assert len(schedule) == 24
    assert schedule[:4] == ((0, 0, 0), (0, 1, 0), (0, 2, 0), (0, 3, 0))
    assert schedule[-1] == (1, 7, 2)


def test_mrope_interleaved_sections() -> None:
    mapping = mrope_map(32, 11, 10)
    height_positions = [pair for pair, axis, _ in mapping if axis == "height"]
    width_positions = [pair for pair, axis, _ in mapping if axis == "width"]
    assert height_positions == list(range(1, 32, 3))
    assert width_positions == list(range(2, 30, 3))
    assert mapping[31][1] == "height"


def test_vision_window_layout_emits_padding_explicitly() -> None:
    schedule = vision_window_schedule(1, 3, 5, 4, 8, 2, 4)
    assert len(schedule) == 32
    assert sum(padding for *_, padding in schedule) == 17
    assert schedule[0] == (0, 0, 0, False)
    assert schedule[-1] == (0, 3, 7, True)


def test_vision_patch_merge_partial_edge() -> None:
    schedule = vision_patch_merge_schedule(1, 3, 5, 2, 2)
    assert len(schedule) == 24
    assert max(entry[3] for entry in schedule) == 5
    assert sum(entry[4] for entry in schedule) == 15


def test_bilinear_index_align_corners() -> None:
    assert bilinear_index(0, 0, 14, 14, 27, 27)[:4] == (0, 1, 0, 1)
    y0, y1, x0, x1, yf, xf = bilinear_index(26, 26, 14, 14, 27, 27)
    assert (y0, y1, x0, x1) == (13, 13, 13, 13)
    assert yf == 0 and xf == 0
    assert bilinear_index(0, 0, 1, 1, 1, 1) == (0, 0, 0, 0, 0, 0)


def test_patch3d_coordinate_order() -> None:
    schedule = vision_patch3d_schedule(2, 2, 2, 3, 2, 2, 2, 2, 2, 2)
    assert len(schedule) == 2 * 2 * 2 * 3 * 2 * 2 * 2
    assert schedule[0] == (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    assert schedule[-1] == (1, 1, 1, 3, 3, 3, 2, 1, 1, 1)


def test_pwl_segment_order_and_nan() -> None:
    breakpoints = [fp32_bits(x) for x in (-2.0, 0.0, 2.0)]
    assert pwl_segment(fp32_bits(-3.0), breakpoints) == 0
    assert pwl_segment(fp32_bits(-1.0), breakpoints) == 1
    assert pwl_segment(fp32_bits(1.0), breakpoints) == 2
    assert pwl_segment(fp32_bits(3.0), breakpoints) == 3
    assert pwl_segment(0x7FC00001, breakpoints) == 3


def test_gdn_recurrent_scalar_known_result() -> None:
    output, state = gdn_recurrent_step(
        ((0.25,),),
        (2.0,),
        (3.0,),
        (0.75,),
        a=-0.5,
        b=0.25,
        a_log=math.log(0.75),
        dt_bias=0.125,
    )
    q = f32(2.0 / math.sqrt(f32(4.0 + 1e-6)))
    k = f32(3.0 / math.sqrt(f32(9.0 + 1e-6)))
    beta = f32(1.0 / (1.0 + math.exp(-0.25)))
    decay = f32(math.exp(f32(-f32(0.75) * f32(math.log1p(math.exp(-0.375))))))
    decayed = f32(0.25 * decay)
    memory = f32(decayed * k)
    delta = f32(f32(0.75 - memory) * beta)
    expected_state = f32(decayed + f32(k * delta))
    expected_output = f32(expected_state * q)
    assert fp32_bits(state[0][0]) == fp32_bits(expected_state)
    assert fp32_bits(output[0]) == fp32_bits(expected_output)


def test_all_required_model_operators_have_phase_counts() -> None:
    assert len(OPERATOR_PHASE_COUNTS) == 48
    for model, operators in MODEL_REQUIRED_OPERATORS.items():
        assert operators, model
        missing = sorted(set(operators) - OPERATOR_PHASE_COUNTS.keys())
        assert missing == [], (model, missing)
        assert all(OPERATOR_PHASE_COUNTS[name] > 0 for name in operators)


def test_reference_bit_roundtrip() -> None:
    for value in (-math.inf, -3.5, -0.0, 0.0, 1.25, math.inf):
        assert fp32_bits(bits_fp32(fp32_bits(value))) == fp32_bits(value)
        assert 0 <= fp32_order_key(fp32_bits(value)) <= 0xFFFF_FFFF


def test_composite_activation_leaf_sequences_are_terminal() -> None:
    assert {name: len(sequence) for name, sequence in COMPOSITE_LEAF_SEQUENCES.items()} == {
        "SfuExp": 2,
        "SfuSigmoid": 8,
        "SfuSoftplus": 1,
        "SfuSilu": 9,
        "SfuGelu": 1,
    }
    for sequence in COMPOSITE_LEAF_SEQUENCES.values():
        assert sequence
        assert set(sequence) <= TERMINAL_PRIMITIVE_BINDINGS
        assert not (set(sequence) & COMPOSITE_LEAF_SEQUENCES.keys())


def test_every_model_operator_expands_to_registered_terminal_primitives() -> None:
    assert set(MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES) == set(OPERATOR_PHASE_COUNTS)
    for operator, sequence in MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES.items():
        assert len(sequence) == OPERATOR_PHASE_COUNTS[operator]
        terminal = terminal_sequence(operator)
        assert terminal, operator
        assert set(terminal) <= TERMINAL_PRIMITIVE_BINDINGS, (operator, set(terminal) - TERMINAL_PRIMITIVE_BINDINGS)
        assert not (set(terminal) & COMPOSITE_LEAF_SEQUENCES.keys()), operator


def test_multimodal_sequences_include_official_bias_and_scale_steps() -> None:
    assert MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES["VisionPatchEmbed"] == (
        "VisionPatch3d", "MatrixConv", "SfuAdd"
    )
    assert MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES["VisionAttention"] == (
        "MatrixGemm", "SfuAdd", "VisionMropeMap", "SfuRope", "MatrixQk",
        "SfuScale", "SfuOnlineSoftmax", "MatrixPv", "MatrixGemm", "SfuAdd",
    )
    assert MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES["VisionMlpGelu"].count("SfuAdd") == 2
    assert MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES["VisionPatchMerge"] == (
        "VisionPatchMerge", "SfuLayerNorm", "MatrixGemm", "SfuAdd",
        "SfuGelu", "MatrixGemm", "SfuAdd",
    )


def test_qsa_official_maximum_topk_and_tail_geometry() -> None:
    # Qwen3.8 uses block_topk=512 and compress_ratio=4. Exercise the full
    # selector capacity with repeated scores, including stable index ties.
    block_scores = tuple(fp32_bits(float(index % 23)) for index in range(1024))
    selected = qsa_selected_tokens(
        block_scores, block_topk=512, compress_ratio=4, tail_count=3
    )
    assert len(selected) == 512 * 4 + 3
    assert selected[-3:] == (4096, 4097, 4098)
    selected_blocks = tuple(selected[index] // 4 for index in range(0, 512 * 4, 4))
    expected = tuple(index for _, index in stable_topk(
        tuple((score, index) for index, score in enumerate(block_scores)), 512
    ))
    assert selected_blocks == expected
    for base in range(0, 512 * 4, 4):
        assert selected[base:base + 4] == tuple(range(selected[base], selected[base] + 4))


def test_ple_official_sixteen_head_randomized_reference() -> None:
    rng = random.Random(0x504C45)
    tokens = tuple(rng.getrandbits(32) for _ in range(17))
    sizes = tuple(97 + 2 * index for index in range(16))
    offsets = tuple(sum(sizes[:index]) for index in range(16))
    multipliers = (0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9)
    rows = ple_hash_rows(
        tokens, ngram_size=3, heads_per_ngram=8, sizes=sizes,
        offsets=offsets, multipliers=multipliers, sentinel=0,
    )
    assert len(rows) == len(tokens)
    assert all(len(token_rows) == 16 for token_rows in rows)
    for position, token_rows in enumerate(rows):
        for head, row in enumerate(token_rows):
            ngram = 2 if head < 8 else 3
            mixed = 0
            for shift in range(ngram):
                token = 0 if position < shift else tokens[position - shift]
                term = (token * multipliers[shift]) & ((1 << 64) - 1)
                mixed = term if shift == 0 else mixed ^ term
            assert row == offsets[head] + mixed % sizes[head]


def test_moe_top10_plus_shared_route_order_independent() -> None:
    rng = random.Random(0x4D4F45)
    weights = [f32(rng.uniform(0.01, 1.0)) for _ in range(11)]
    total = f32(sum(weights))
    weights = [f32(weight / total) for weight in weights]
    results = [[f32(rng.uniform(-3.0, 3.0)) for _ in range(32)] for _ in weights]
    baseline = moe_route_merge(weights, results, list(range(11)))
    for _ in range(20):
        order = list(range(11))
        rng.shuffle(order)
        assert moe_route_merge(weights, results, order) == baseline


def test_mtp_every_first_mismatch_position() -> None:
    target = tuple(range(32))
    assert mtp_verify(target, target)["accepted_count"] == 32
    for mismatch in range(32):
        draft = list(target)
        draft[mismatch] ^= 0x1000
        result = mtp_verify(draft, target)
        assert result == {
            "accepted_count": mismatch,
            "mismatch_step": mismatch,
            "all_match": False,
            "rollback": True,
        }


def test_terminal_owner_registry_is_exact_and_all_models_reach_it() -> None:
    assert set(TERMINAL_PRIMITIVE_OWNERS) == TERMINAL_PRIMITIVE_BINDINGS
    assert set(TERMINAL_PRIMITIVE_OWNERS.values()) == {
        "Control", "Dma", "Matrix", "Sfu", "KvMemory", "State",
        "Selection", "Vision",
    }
    for operators in MODEL_REQUIRED_OPERATORS.values():
        for operator in operators:
            assert all(opcode in TERMINAL_PRIMITIVE_OWNERS for opcode in terminal_sequence(operator))


def test_terminal_micro_op_expansion_totals_are_frozen() -> None:
    assert {
        model: sum(len(terminal_sequence(operator)) for operator in operators)
        for model, operators in MODEL_REQUIRED_OPERATORS.items()
    } == {
        "qwen2_1p5b": 27,
        "qwen3_5_35b_a3b": 186,
        "qwen3_8_flash_next": 279,
    }
