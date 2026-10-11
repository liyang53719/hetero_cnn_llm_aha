"""Small numerical and sealed-evidence tests; no checkpoint/model forward."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rms_rope_policy', ROOT / 'scripts/qwen2_rms_rope_policy_diagnostic.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def test_bf16_ties_are_even_in_both_signs():
    raw = np.array([0x3f808000, 0x3f818000, 0xbf808000, 0xbf818000], dtype='<u4')
    assert M.bf16(raw.view('<f4')).view('<u4').tolist() == [0x3f800000, 0x3f820000, 0xbf800000, 0xbf820000]


def test_direct_gamma_and_pre_gamma_materialization():
    x = M.bf16(np.linspace(-1, 1, 1536, dtype='<f4').reshape(1, 1, 1536))
    gamma = np.zeros(1536, dtype='<f4')
    assert np.count_nonzero(M.rms_recipe(x, gamma)['output']) == 0
    gamma[:] = np.float32(0.75)
    stages = M.rms_recipe(x, gamma)
    assert np.array_equal(stages['output'], M.bf16(M.bf16(stages['normalized']) * gamma))


def test_width1536_reduction_and_division_match_pinned_torch():
    torch = pytest.importorskip('torch')
    if torch.__version__ != '2.10.0+cpu' or torch.version.git_version != M.TORCH_COMMIT:
        pytest.skip('exact source-pinned CPU backend required')
    torch.set_num_threads(4)
    rng = np.random.default_rng(1205)
    x = M.bf16((rng.normal(size=(1, 16, 1536)) * np.exp2(rng.integers(-8, 4, size=(1, 16, 1536)))).astype('<f4'))
    stage = M.rms_recipe(x, np.ones(1536, dtype='<f4'))
    native = torch.from_numpy(x).pow(2)
    assert M.compare(stage['sum'], native.sum(-1, keepdim=True).numpy())['bit_exact']
    assert M.compare(stage['mean'], native.mean(-1, keepdim=True).numpy())['bit_exact']
    assert M.compare(stage['inverse'], torch.rsqrt(native.mean(-1, keepdim=True) + 1e-6).numpy())['bit_exact']
    assert not M.compare(stage['sum'] * np.float32(1 / 1536), stage['mean'])['bit_exact']


def test_independent_ordinary_c_checks_every_node(tmp_path):
    lib, _ = M.build_c(tmp_path)
    rng = np.random.default_rng(512)
    x = M.bf16(rng.normal(size=(1, 3, 1536)).astype('<f4'))
    gamma = M.bf16(rng.uniform(0.125, 1.5, size=1536).astype('<f4'))
    candidate = M.rms_recipe(x, gamma)
    independent = M.c_rms(lib, x, gamma)
    assert all(M.compare(candidate[name], independent[name])['bit_exact'] for name in candidate)
    result = M.check_scalar_rne(*(candidate[name] for name in ('variance', 'root', 'sum', 'mean', 'inverse')))
    assert result['rows'] == 3


def test_integer_midpoint_check_rejects_one_ulp_sqrt_error():
    x = np.ones((1, 1, 1536), dtype='<f4')
    stage = M.rms_recipe(x, np.ones(1536, dtype='<f4'))
    corrupt = np.nextafter(stage['root'], np.float32(np.inf), dtype=np.float32)
    with pytest.raises(ValueError, match='sqrt is not FP32 RNE'):
        M.check_scalar_rne(stage['variance'], corrupt, stage['sum'], stage['mean'], stage['inverse'])


@pytest.mark.parametrize('shape', [(1, 1, 1024), (1, 129, 1536), (2, 1, 1536)])
def test_rejects_out_of_scope_geometry(shape):
    with pytest.raises(ValueError, match='geometry'):
        M.rms_recipe(np.zeros(shape, dtype='<f4'), np.ones(1536, dtype='<f4'))


def test_rejects_non_bf16_or_nonfinite_inputs():
    x = np.ones((1, 1, 1536), dtype='<f4')
    gamma = np.ones(1536, dtype='<f4')
    x[0, 0, 0] = np.nextafter(np.float32(1), np.float32(2))
    with pytest.raises(ValueError, match='fixed BF16'):
        M.rms_recipe(x, gamma)
    x[0, 0, 0] = np.inf
    with pytest.raises(ValueError, match='nonfinite'):
        M.rms_recipe(x, gamma)


def test_sealed_evidence_detects_rewrite_and_symlink(tmp_path):
    path = tmp_path / 'tensor.f32le'
    values = np.array([1, 2], dtype='<f4')
    path.write_bytes(values.tobytes())
    evidence = M.Evidence(tmp_path)
    assert np.array_equal(evidence.tensor(path, (2,), M.sha(values.tobytes())), values)
    path.write_bytes(np.array([1, 3], dtype='<f4').tobytes())
    with pytest.raises(ValueError, match='consumed source changed'):
        evidence.verify()
    with pytest.raises(ValueError, match='digest mismatch'):
        evidence.tensor(path, (2,), M.sha(values.tobytes()))
    link = tmp_path / 'link'
    link.symlink_to(path)
    with pytest.raises(ValueError, match='symlink'):
        evidence.read(link)


def test_zero_rows_and_signed_zero_remain_finite():
    x = np.zeros((1, 1, 1536), dtype='<f4')
    x[0, 0, 1] = np.float32(-0.0)
    stages = M.rms_recipe(x, np.ones(1536, dtype='<f4'))
    assert stages['output'].view('<u4')[0, 0, 1] == 0x80000000
    M.check_scalar_rne(*(stages[name] for name in ('variance', 'root', 'sum', 'mean', 'inverse')))
