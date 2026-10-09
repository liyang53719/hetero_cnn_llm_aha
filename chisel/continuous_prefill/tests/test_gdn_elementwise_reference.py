"""Independent elementwise recipe boundaries; no weights/fixtures stored in Git."""
from pathlib import Path
import importlib.util
import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/gdn_elementwise_reference.py'
spec = importlib.util.spec_from_file_location('gdn_elementwise_reference', SCRIPT)
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)


def test_silu_is_bf16_before_up_multiplication():
    a = ref.bf16(np.linspace(-9, 9, 3584, dtype=np.float32))
    b = ref.bf16(np.linspace(-4, 7, 3584, dtype=np.float32))
    out, stages = ref.recipe('silu_mul', a, b)
    np.testing.assert_array_equal(out, ref.bf16(ref.fp(stages['silu_bf16']) * ref.fp(b)))
    fused = ref.bf16(stages['silu_f32'] * ref.fp(b))
    assert np.count_nonzero(fused != out) > 300


def test_residual_add_preserves_rne_and_signed_zero():
    a = np.array([0x3f80, 0x3f81, 0, 0x8000, 1, 0x8001], dtype='<u2')
    b = np.array([0x3b80, 0x3b80, 0x8000, 0x8000, 1, 0x8001], dtype='<u2')
    out, _ = ref.recipe('add', a, b)
    assert list(out) == [0x3f80, 0x3f82, 0, 0x8000, 2, 0x8002]


def test_silu_ieee_underflow_signed_zero_and_positive_saturation():
    a = np.array([0, 0x8000, 1, 0x8001, ref.bf16(np.float32(80)).item()], dtype='<u2')
    b = np.full_like(a, 0x3f80)
    out, stages = ref.recipe('silu_mul', a, b)
    assert list(out) == [0, 0x8000, 0, 0x8000, a[-1]]
    assert stages['silu_f32'][2] != 0 and out[2] == 0
    edge = ref.bf16(np.array([-79.5], dtype=np.float32))
    out, _ = ref.recipe('silu_mul', edge, np.array([0x3f80], dtype='<u2'))
    assert out[0] == 0x8945  # Supported negative edge is nonzero, not saturation.


def test_fail_closed_domains_and_nonfinite():
    a = np.full(37, 0x3f80, dtype='<u2')
    for bad in (ref.bf16(np.float32(-80)).item(), ref.bf16(np.float32(-100)).item()):
        with pytest.raises(ValueError, match='legal negative SiLU'):
            ref.recipe('silu_mul', np.full_like(a, bad), a)
    for op in ('add', 'silu_mul'):
        for bad in (0x7f80, 0xff80, 0x7fc0):
            with pytest.raises(ValueError, match='nonfinite'):
                ref.recipe(op, a, np.full_like(a, bad))
    with pytest.raises(ValueError, match='BF16 storage'):
        ref.recipe('add', a.astype(np.uint32), a.astype(np.uint32))
    with pytest.raises(ValueError):
        ref.recipe('unknown', a, a)
    with np.errstate(over='ignore'):
        with pytest.raises(ValueError, match='nonfinite'):
            ref.recipe('silu_mul', np.full_like(a, 0x7f7f), np.full_like(a, 0x7f7f))
    with pytest.raises(ValueError, match='nonfinite rounded sum'):
        ref.recipe('add', np.array([0x7f7f], dtype='<u2'), np.array([0x7b00], dtype='<u2'))


def test_diagnostics_do_not_grant_official_acceptance():
    a = np.array([0x3f80, 0x8000], dtype='<u2')
    b = np.array([0x3f81, 0], dtype='<u2')
    metric = ref.diagnostics(a, b)
    assert metric['bit_mismatches'] == 2 and metric['numeric_mismatches'] == 1
    assert metric['max_bf16_ulp'] == 1 and metric['max_abs'] == 1 / 128
    assert metric['official_acceptance'] == 'UNASSIGNED_DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN'
