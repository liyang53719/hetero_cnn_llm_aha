"""Isolated recipe checks. No source model weights or generated fixtures stored."""
from pathlib import Path
import importlib.util
import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/gdn_gated_norm_reference.py'
spec = importlib.util.spec_from_file_location('gdn_gated_norm_reference', SCRIPT)
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)


def test_original_fp32_gamma_and_pre_weight_bf16_boundary():
    x = ref.bf16(np.linspace(-1.7, 1.2, 128, dtype=np.float32)[None])
    z = ref.bf16(np.linspace(-2, 3, 128, dtype=np.float32)[None])
    gamma = np.linspace(.130017, 1.718137, 128, dtype=np.float32)
    output, stages = ref.recipe(x, z, gamma)
    rounded_gamma_output, _ = ref.recipe(x, z, ref.fp(ref.bf16(gamma)))
    zero_centered_output, _ = ref.recipe(x, z, np.add(gamma, np.float32(1), dtype=np.float32))
    assert np.count_nonzero(output != rounded_gamma_output) > 0
    assert np.count_nonzero(output != zero_centered_output) > 0
    np.testing.assert_array_equal(output, ref.bf16(np.multiply(stages['weighted'], stages['silu'], dtype=np.float32)))
    no_boundary = ref.bf16(ref.fp(x) * stages['inverse_rms'] * gamma * stages['silu'])
    assert np.count_nonzero(output != no_boundary) > 0


def test_ieee_underflow_and_signed_zero_remain_visible():
    core = np.full((1, 128), 0x3f80, dtype='<u2')
    gate = np.full_like(core, 0x3f80)
    core[0, :4] = [0, 0x8000, 1, 0x8001]
    gate[0, :4] = [0x8000, 0, 1, 0x8001]
    out, _ = ref.recipe(core, gate, np.ones(128, dtype='<f4'))
    assert list(out[0, :4]) == [0x8000, 0x8000, 0, 0]
    metric = ref.diagnostics(np.array([0x8000], dtype='<u2'), np.array([0], dtype='<u2'))
    assert metric['bit_mismatches'] == 1 and metric['numeric_mismatches'] == 0


def test_fail_closed_domains_and_dtype():
    x = np.full((1, 128), 0x3f80, dtype='<u2')
    w = np.ones(128, dtype='<f4')
    for bad in [ref.bf16(np.float32(-80)).item(), 0x7fc0, 0x7f80]:
        with pytest.raises(ValueError):
            ref.recipe(x, np.full_like(x, bad), w)
    with pytest.raises(ValueError):
        ref.recipe(x, x, w.astype('<f8'))
    # Existing exp's documented positive saturation rounds sigmoid to one.
    out, _ = ref.recipe(x, np.full_like(x, ref.bf16(np.float32(80)).item()), w)
    assert np.all(out == ref.bf16(np.float32(80)))


def test_diagnostics_cannot_assign_new_official_acceptance():
    a = np.array([0x3f80, 0x8000], dtype='<u2')
    b = np.array([0x3f81, 0], dtype='<u2')
    report = ref.diagnostics(a, b)
    assert report['max_bf16_ulp'] == 1 and report['max_abs'] == 1 / 128
    assert report['bit_mismatches'] == 2 and report['numeric_mismatches'] == 1
    assert report['official_acceptance'] == 'UNASSIGNED_DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN'
