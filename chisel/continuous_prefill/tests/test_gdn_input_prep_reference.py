from pathlib import Path
import importlib.util
import json
import numpy as np
import pytest

PATH = Path(__file__).resolve().parents[1] / 'scripts/gdn_input_prep_reference.py'
spec = importlib.util.spec_from_file_location('input_prep_reference', PATH)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def case():
    random = np.random.default_rng(350128)
    q, k, v = [r.bf16(random.uniform(-1, 1, (2, 128)).astype('<f4')) for _ in range(3)]
    return q, k, v, r.bf16(np.array([-2, 1], '<f4')), r.bf16(np.array([-.25, .75], '<f4')), np.array([.23123, -.13983], '<f4'), r.bf16(np.array([-.7, -.2], '<f4'))


def test_checkpoint_dtype_and_order_are_frozen():
    root = PATH.parents[3]
    pin = json.loads((root / 'config/upstream/qwen3_5_0p8b/layer0_payload_pin.json').read_text())
    tensors = {x['local_name']: x for x in pin['tensors']}
    assert tensors['linear_attn.A_log']['dtype'] == 'F32'
    assert tensors['linear_attn.dt_bias']['dtype'] == 'BF16'
    source = (root / 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py').read_text()
    assert 'beta = b.sigmoid()' in source
    assert 'g = -self.A_log.float().exp() * F.softplus(a.float() + self.dt_bias)' in source
    assert 'query = query * scaling' in source and 'query = query / (query.shape[-1] ** 0.5)' in source


def test_fp32_outputs_bf16_beta_and_explicit_scaling_policy():
    inputs = case()
    cold = r.recipe(*inputs, recurrent_mode=False)
    warm = r.recipe(*inputs, recurrent_mode=True)
    assert all(x.dtype == np.dtype('<f4') for x in cold)
    assert cold[3].shape == (2, 16)
    assert np.count_nonzero(cold[3][:, 2:]) == 0
    assert np.count_nonzero(cold[0].view('<u4') != warm[0].view('<u4')) > 0
    for x, y in zip(cold[1:], warm[1:]): np.testing.assert_array_equal(x, y)
    np.testing.assert_array_equal(cold[2], r.fp(inputs[2]))
    np.testing.assert_array_equal(cold[3][:, 1], r.fp(r.bf16(cold[3][:, 1])))
    assert np.all(cold[3][:, 0] <= 0)


def test_l2_epsilon_placement_and_signed_zero():
    xs = list(case())
    xs[0][:] = 0
    xs[0][0, 0] = 0x8000
    out = r.recipe(*xs, recurrent_mode=False)
    assert out[0].view('<u4')[0, 0] == 0x80000000
    assert np.count_nonzero(out[0]) == 0


def test_softplus_stable_range():
    x = np.array([-79, -40, -20, -5, -1, 0, 1, 5, 20, 20.01, 100], dtype='<f4')
    actual = r.softplus(x)
    expected = np.logaddexp(0, x.astype(np.float64))
    np.testing.assert_allclose(actual, expected, rtol=2e-6, atol=0)
    assert actual[-1] == x[-1]
    for bad in (-80, -100, np.inf, np.nan):
        with pytest.raises(ValueError): r.softplus(np.array([bad], dtype='<f4'))


def test_wrong_dtype_and_domain_fail_closed():
    xs = list(case())
    xs[6] = r.fp(xs[6])
    with pytest.raises(ValueError, match='BF16'): r.recipe(*xs, recurrent_mode=False)
    xs = list(case()); xs[4][0] = r.bf16(np.array(-80, '<f4'))
    with pytest.raises(ValueError, match='domain'): r.recipe(*xs, recurrent_mode=False)
    with pytest.raises(ValueError, match='explicit'): r.recipe(*case(), recurrent_mode=None)
