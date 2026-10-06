"""Small-geometry mathematical checks; no torch, checkpoints, or RTL claim."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.qwen35_gdn_numpy_reference import (
    GDNConfig, causal_conv1d, forward, l2_normalize, recurrent_gated_delta_rule,
)


def small_case(tokens=11, seed=72):
    cfg = GDNConfig(hidden_size=4, intermediate_size=7, linear_num_key_heads=1,
                    linear_num_value_heads=2, linear_key_head_dim=3,
                    linear_value_head_dim=2, linear_conv_kernel_dim=4)
    rng = np.random.default_rng(seed)
    shapes = {
        "input_layernorm.weight": (4,),
        "post_attention_layernorm.weight": (4,),
        "linear_attn.in_proj_qkv.weight": (10, 4),
        "linear_attn.in_proj_z.weight": (4, 4),
        "linear_attn.in_proj_b.weight": (2, 4),
        "linear_attn.in_proj_a.weight": (2, 4),
        "linear_attn.conv1d.weight": (10, 1, 4),
        "linear_attn.A_log": (2,),
        "linear_attn.dt_bias": (2,),
        "linear_attn.norm.weight": (2,),
        "linear_attn.out_proj.weight": (4, 4),
        "mlp.gate_proj.weight": (7, 4),
        "mlp.up_proj.weight": (7, 4),
        "mlp.down_proj.weight": (4, 7),
    }
    weights = {name: (rng.standard_normal(shape) * .3).astype(np.float32) for name, shape in shapes.items()}
    weights["linear_attn.norm.weight"] += 1
    x = rng.standard_normal((1, tokens, 4)).astype(np.float32)
    return cfg, x, weights


def silu(x):
    return x / (1 + np.exp(-x))


def test_default_config_matches_exact_pinned_geometry():
    config = json.loads((ROOT / "config/upstream/qwen3_5_0p8b/config.json").read_text())["text_config"]
    for name, value in asdict(GDNConfig()).items():
        assert config[name] == value
    assert config["layer_types"][0] == "linear_attention"
    assert GDNConfig().conv_channels == 6144
    assert GDNConfig().value_width == 2048


def test_l2_epsilon_is_added_to_sum_not_norm_or_clamped():
    x = np.array([[0., 0.], [3., 4.], [1e-8, -2e-8]])
    expected = x / np.sqrt(np.sum(x * x, axis=-1, keepdims=True) + 1e-6)
    np.testing.assert_array_equal(l2_normalize(x), expected)
    assert np.linalg.norm(l2_normalize(x)[-1]) < 1e-4


def test_scalar_recurrence_decay_happens_before_prediction_and_read_after_update():
    q = k = np.ones((1, 2, 1, 1))
    v = np.array([2., 4.]).reshape(1, 2, 1, 1)
    # No Q/K L2 in this hand calculation: S0=10, D1=5, S1=5+.25*(2-5)=4.25.
    # D2=1.0625, S2=1.0625+.5*(4-1.0625)=2.53125.
    g = np.log(np.array([.5, .25])).reshape(1, 2, 1)
    beta = np.array([.25, .5]).reshape(1, 2, 1)
    initial = np.full((1, 1, 1, 1), 10.)
    y, state = recurrent_gated_delta_rule(q, k, v, g, beta, initial, normalize_qk=False)
    np.testing.assert_allclose(y.ravel(), [4.25, 2.53125], atol=1e-15, rtol=0)
    np.testing.assert_allclose(state, 2.53125, atol=1e-15, rtol=0)
    np.testing.assert_array_equal(initial, 10.)


def test_recurrence_matches_explicit_matrix_transition_with_repeated_heads():
    rng = np.random.default_rng(923)
    q, k = [rng.standard_normal((1, 9, 1, 3)) for _ in range(2)]
    v = rng.standard_normal((1, 9, 2, 2))
    g = -rng.random((1, 9, 2))
    beta = rng.random((1, 9, 2))
    initial = rng.standard_normal((1, 2, 3, 2))
    y, state = recurrent_gated_delta_rule(q, k, v, g, beta, initial)
    expected = np.empty_like(y)
    expected_state = initial.copy()
    for token in range(9):
        for head in range(2):
            qt = q[0, token, 0] / np.sqrt(np.dot(q[0, token, 0], q[0, token, 0]) + 1e-6) / np.sqrt(3)
            kt = k[0, token, 0] / np.sqrt(np.dot(k[0, token, 0], k[0, token, 0]) + 1e-6)
            transition = np.eye(3) - beta[0, token, head] * np.outer(kt, kt)
            expected_state[0, head] = np.exp(g[0, token, head]) * transition @ expected_state[0, head] + beta[0, token, head] * np.outer(kt, v[0, token, head])
            expected[0, token, head] = qt @ expected_state[0, head]
    np.testing.assert_allclose(y, expected, atol=2e-15, rtol=2e-15)
    np.testing.assert_allclose(state, expected_state, atol=2e-15, rtol=2e-15)


def test_zero_beta_preserves_only_decay_and_zero_keys_do_not_update():
    q = np.array([[[[1., 0.]], [[0., 1.]]]])
    k = np.zeros_like(q)
    initial = np.arange(4.).reshape(1, 1, 2, 2)
    _, state = recurrent_gated_delta_rule(q, k, np.ones_like(q), np.full((1, 2, 1), -.5), np.ones((1, 2, 1)), initial)
    np.testing.assert_allclose(state, initial * np.exp(-1), atol=1e-15, rtol=1e-15)
    _, state = recurrent_gated_delta_rule(q, q, np.ones_like(q), np.zeros((1, 2, 1)), np.zeros((1, 2, 1)), initial)
    np.testing.assert_array_equal(state, initial)


def test_causal_conv_uses_kernel_order_and_raw_four_sample_state():
    x = np.array([1., 2., 3., 4., 5.]).reshape(1, 1, 5)
    w = np.array([[.001, .01, .1, 1.]])
    y, state = causal_conv1d(x, w)
    np.testing.assert_allclose(y.ravel(), silu(np.array([1., 2.1, 3.21, 4.321, 5.432])), atol=1e-15, rtol=1e-15)
    np.testing.assert_array_equal(state, np.array([2., 3., 4., 5.]).reshape(1, 1, 4))
    short_y, short_state = causal_conv1d(x[..., :1], w)
    np.testing.assert_array_equal(short_state, np.array([0., 0., 0., 1.]).reshape(1, 1, 4))
    np.testing.assert_array_equal(short_y, y[..., :1])


def test_carried_convolution_oldest_column_is_not_used_and_inputs_are_immutable():
    projected = np.array([[[.25, -.5]]])
    weight = np.array([[1., 2., 3., 4.]])
    past = np.array([[[1e10, .1, .2, .3]]])
    saved = past.copy()
    y, new_state = causal_conv1d(projected, weight[:, None, :], past)
    np.testing.assert_allclose(y.ravel(), silu(np.array([.1 + .4 + .9 + 1., .2 + .6 + .75 - 2.])), atol=1e-15)
    np.testing.assert_array_equal(new_state, np.array([[[.2, .3, .25, -.5]]]))
    np.testing.assert_array_equal(past, saved)
    changed = past.copy()
    changed[..., 0] = -1e10
    np.testing.assert_array_equal(causal_conv1d(projected, weight, changed)[0], y)


@pytest.mark.parametrize("kernel", [1, 2, 4])
def test_convolution_partition_equivalence(kernel):
    rng = np.random.default_rng(18)
    x = rng.standard_normal((1, 5, 13))
    w = rng.standard_normal((5, kernel))
    full, state = causal_conv1d(x, w)
    carried = None
    parts = []
    for start, stop in [(0, 1), (1, 4), (4, 5), (5, 13)]:
        y, carried = causal_conv1d(x[..., start:stop], w, carried)
        parts.append(y)
    np.testing.assert_array_equal(np.concatenate(parts, axis=-1), full)
    np.testing.assert_array_equal(carried, state)


def test_decoder_m128_cold_then_m128_carried_equals_whole_stream():
    cfg, x, w = small_case(tokens=256)
    full, state = forward(x, w, config=cfg)
    cold, cold_state = forward(x[:, :128], w, config=cfg)
    saved_cold_state = tuple(s.copy() for s in cold_state)
    warm, warm_state = forward(x[:, 128:], w, cold_state, config=cfg)
    np.testing.assert_allclose(np.concatenate((cold, warm), axis=1), full, atol=2e-14, rtol=2e-14)
    for actual, expected in zip(warm_state, state):
        np.testing.assert_allclose(actual, expected, atol=2e-14, rtol=2e-14)
    for actual, expected in zip(cold_state, saved_cold_state):
        np.testing.assert_array_equal(actual, expected)
    reset, _ = forward(x[:, 128:], w, config=cfg)
    assert not np.array_equal(warm, reset)
    assert all(s.dtype == np.float64 for s in warm_state)
    assert warm.dtype == np.float64


def test_decoder_arbitrary_partitions_and_single_token_cache_agree():
    cfg, x, w = small_case()
    full, state = forward(x, w, config=cfg)
    outputs = []
    carried = None
    for start, stop in [(0, 1), (1, 3), (3, 7), (7, 8), (8, 11)]:
        y, carried = forward(x[:, start:stop], w, carried, config=cfg)
        outputs.append(y)
    np.testing.assert_allclose(np.concatenate(outputs, axis=1), full, atol=2e-14, rtol=2e-14)
    for actual, expected in zip(carried, state):
        np.testing.assert_allclose(actual, expected, atol=2e-14, rtol=2e-14)


def test_stage_diagnostics_cover_norm_gate_residual_and_dense_ffn():
    cfg, x, w = small_case()
    y, state, s = forward(x, w, config={"text_config": asdict(cfg)}, return_stages=True)
    np.testing.assert_allclose(s["input_norm"], x.astype(np.float64) / np.sqrt(np.mean(x.astype(np.float64) ** 2, axis=-1, keepdims=True) + cfg.rms_norm_eps) * (1 + w["input_layernorm.weight"].astype(np.float64)))
    expected_gated = s["core_attn_out"] / np.sqrt(np.mean(s["core_attn_out"] ** 2, axis=-1, keepdims=True) + cfg.rms_norm_eps) * w["linear_attn.norm.weight"] * silu(s["z_projection"])
    np.testing.assert_allclose(s["gated_norm"], expected_gated, atol=2e-15, rtol=2e-15)
    np.testing.assert_array_equal(s["post_attention_residual"], x + s["attention_output"])
    np.testing.assert_allclose(s["ffn_product"], silu(s["ffn_gate"]) * s["ffn_up"], atol=2e-15, rtol=2e-15)
    np.testing.assert_array_equal(y, s["post_attention_residual"] + s["ffn_output"])
    assert len(s) == 21
    assert state[0].shape == (1, cfg.conv_channels, cfg.linear_conv_kernel_dim)
    assert state[1].shape == (1, cfg.linear_num_value_heads, cfg.linear_key_head_dim, cfg.linear_value_head_dim)


def test_gated_norm_weight_is_not_zero_centered_and_forward_does_not_mutate():
    cfg, x, w = small_case()
    w["linear_attn.norm.weight"].fill(0)
    originals = {name: value.copy() for name, value in w.items()}
    saved_x = x.copy()
    _, _, s = forward(x, w, config=cfg, return_stages=True)
    np.testing.assert_array_equal(s["attention_output"], 0.)
    for name, saved in originals.items():
        np.testing.assert_array_equal(w[name], saved)
    np.testing.assert_array_equal(x, saved_x)


def test_decoded_fp32_parameter_precision_is_not_silently_bf16_rounded():
    cfg, x, w = small_case()
    w["linear_attn.A_log"] = np.array([1.0001, -1.0001], dtype=np.float32)
    _, _, s = forward(x, w, config=cfg, return_stages=True)
    expected = -np.exp(w["linear_attn.A_log"].astype(np.float64)) * np.logaddexp(0, s["a_projection"] + w["linear_attn.dt_bias"].astype(np.float64))
    np.testing.assert_array_equal(s["g"], expected)
    rounded = dict(w)
    rounded["linear_attn.A_log"] = np.array([1., -1.], dtype=np.float32)
    _, _, rounded_s = forward(x, rounded, config=cfg, return_stages=True)
    assert not np.array_equal(s["g"], rounded_s["g"])


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_nonfinite_input_weight_and_state_rejected(bad):
    cfg, x, w = small_case()
    damaged = x.copy()
    damaged[0, 0, 0] = bad
    with pytest.raises(ValueError, match="nonfinite"):
        forward(damaged, w, config=cfg)
    bad_w = dict(w)
    bad_w["linear_attn.A_log"] = np.array([bad, 0.])
    with pytest.raises(ValueError, match="nonfinite"):
        forward(x, bad_w, config=cfg)
    _, past = forward(x, w, config=cfg)
    for index in (0, 1):
        states = [a.copy() for a in past]
        states[index].flat[0] = bad
        with pytest.raises(ValueError, match="nonfinite"):
            forward(x, w, states, config=cfg)


@pytest.mark.parametrize("change", [
    {"hidden_size": 0}, {"linear_conv_kernel_dim": True}, {"intermediate_size": 2.5},
    {"linear_num_key_heads": 3}, {"rms_norm_eps": 0}, {"rms_norm_eps": np.nan},
])
def test_invalid_geometry_rejected(change):
    with pytest.raises(ValueError):
        replace(GDNConfig(), **change)


def test_invalid_shapes_missing_weights_and_half_initialized_state_rejected():
    cfg, x, w = small_case()
    for invalid_x in (x[0], np.repeat(x, 2, axis=0), x[:, :0], x[..., :3]):
        with pytest.raises(ValueError, match="hidden states"):
            forward(invalid_x, w, config=cfg)
    bad_w = dict(w)
    bad_w.pop("linear_attn.dt_bias")
    with pytest.raises(ValueError, match="missing weights"):
        forward(x, bad_w, config=cfg)
    bad_w["linear_attn.dt_bias"] = np.zeros(3)
    with pytest.raises(ValueError, match="shape"):
        forward(x, bad_w, config=cfg)
    for past in ((None, None), (np.zeros(1),), (np.zeros(1), np.zeros(1))):
        with pytest.raises(ValueError):
            forward(x, w, past, config=cfg)


def test_recurrent_invalid_gate_range_nonfinite_and_shapes_rejected():
    q = k = v = np.ones((1, 2, 1, 2))
    g = np.zeros((1, 2, 1))
    beta = np.ones_like(g)
    with pytest.raises(ValueError, match="log decay"):
        recurrent_gated_delta_rule(q, k, v, g + .1, beta)
    with pytest.raises(ValueError, match="beta"):
        recurrent_gated_delta_rule(q, k, v, g, beta + .1)
    with pytest.raises(ValueError, match="nonfinite"):
        recurrent_gated_delta_rule(q, k, v, g, beta * np.nan)
    with pytest.raises(ValueError, match="query and key"):
        recurrent_gated_delta_rule(q, k[..., :1], v, g, beta)
    with pytest.raises(ValueError, match="recurrent state shape"):
        recurrent_gated_delta_rule(q, k, v, g, beta, np.zeros((1, 1, 2, 3)))


def test_unsupported_activation_and_ssm_contract_rejected():
    cfg, x, w = small_case()
    for override in ({"hidden_act": "gelu"}, {"mamba_ssm_dtype": "bfloat16"}):
        with pytest.raises(ValueError):
            forward(x, w, config={**asdict(cfg), **override})


def test_nonfinite_decay_intermediate_fails_closed():
    cfg, x, w = small_case()
    w["linear_attn.A_log"] = np.full(2, 10000.)
    with pytest.raises(ValueError, match="g contains nonfinite"):
        forward(x, w, config=cfg)
