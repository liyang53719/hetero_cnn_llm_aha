"""Input/post RMSNorm recipe checks; no model payloads are stored in Git."""
from pathlib import Path
import importlib.util
import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/gdn_rmsnorm_reference.py'
spec = importlib.util.spec_from_file_location('gdn_rmsnorm_reference', SCRIPT)
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)


def test_zero_centered_original_bf16_weight_and_only_final_cast():
    hidden = ref.bf16(np.linspace(-1.73, 1.29, 1024, dtype='<f4')[None])
    weight = ref.bf16(np.linspace(-.73, 1.29, 1024, dtype='<f4'))
    out, stages = ref.recipe(hidden, weight)
    no_offset = ref.bf16(np.multiply(stages['normalized_fp32'], ref.fp(weight), dtype=np.float32))
    early_cast = ref.bf16(np.multiply(ref.fp(ref.bf16(stages['normalized_fp32'])),
                                     stages['one_plus_weight'], dtype=np.float32))
    assert np.count_nonzero(out != no_offset) > 0
    assert np.count_nonzero(out != early_cast) > 0
    np.testing.assert_array_equal(out, ref.bf16(stages['weighted_fp32']))


def test_ascending_fp32_reduction_and_separate_sqrt_reciprocal():
    hidden = np.full((1, 32), 0x3f80, dtype='<u2')
    out, stages = ref.recipe(hidden, np.zeros(32, dtype='<u2'))
    assert stages['mean'].item() == np.float32(1)
    np.testing.assert_array_equal(stages['root'], np.sqrt(stages['variance'], dtype=np.float32))
    np.testing.assert_array_equal(stages['inverse_rms'], np.divide(np.float32(1), stages['root'], dtype=np.float32))
    assert np.all(out == 0x3f80)


def test_ieee_subnormals_and_signed_zero_are_not_hidden():
    hidden = np.full((1, 32), 0x3f80, dtype='<u2')
    hidden[0, :4] = [0, 0x8000, 1, 0x8001]
    weight = np.zeros(32, dtype='<u2')
    out, _ = ref.recipe(hidden, weight)
    assert list(out[0, :4]) == [0, 0x8000, 1, 0x8001]
    # Gamma=-1 has an exactly +0 offset, preserving the multiply sign.
    out, _ = ref.recipe(hidden, np.full(32, 0xbf80, dtype='<u2'))
    assert list(out[0, :4]) == [0, 0x8000, 0, 0x8000]


def test_fail_closed_on_shape_storage_nonfinite_and_intermediate_overflow():
    hidden = np.full((1, 32), 0x3f80, dtype='<u2')
    weight = np.zeros(32, dtype='<u2')
    for bad in (0x7f80, 0xff80, 0x7fc0, 0x7f7f):
        with pytest.raises(ValueError):
            ref.recipe(np.full_like(hidden, bad), weight)
    for bad in (0x7f80, 0xff80, 0x7fc0):
        with pytest.raises(ValueError):
            ref.recipe(hidden, np.full_like(weight, bad))
    for bad in (weight.astype('<f4'), weight[:16]):
        with pytest.raises(ValueError):
            ref.recipe(hidden, bad)
    with pytest.raises(ValueError):
        ref.recipe(hidden[:, :31], weight[:31])


def test_diagnostics_separate_bits_numeric_and_signed_zero_without_acceptance():
    a = np.array([0x3f80, 0x8000], dtype='<u2')
    b = np.array([0x3f81, 0], dtype='<u2')
    report = ref.diagnostics(a, b)
    assert report['max_bf16_ulp'] == 1 and report['max_abs'] == 1 / 128
    assert report['bit_mismatches'] == 2 and report['numeric_mismatches'] == 1
    assert report['signed_zero_only_mismatches'] == 1
    assert report['official_acceptance'] == 'UNASSIGNED_DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN'
