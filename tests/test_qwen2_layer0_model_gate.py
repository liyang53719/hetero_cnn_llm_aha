"""Boundary/coverage regressions; no download, full model, RTL, or large GEMM."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('qwen2_layer0_model_gate', ROOT / 'scripts/qwen2_layer0_model_gate.py')
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def test_bf16_ties_even_signed_and_overflow():
    words = np.array([0x3f808000, 0x3f818000, 0xbf808000, 0xbf818000, 0x00000000, 0x80000000], dtype=np.uint32)
    expected = [0x3f800000, 0x3f820000, 0xbf800000, 0xbf820000, 0x00000000, 0x80000000]
    assert GATE.bf16(words.view(np.float32)).view(np.uint32).tolist() == expected
    with pytest.raises(ValueError, match='nonfinite'):
        GATE.bf16(np.array([np.nan], np.float32))
    with pytest.raises(ValueError, match='overflow'):
        GATE.bf16(np.array([np.finfo(np.float32).max], np.float32))


def test_causal_mask_carries_prefix_with_exact_storage_minimum():
    mask = GATE.causal_mask(3, 2, 'bf16')
    assert mask.shape == (1, 1, 3, 5)
    assert (mask != 0)[0, 0].tolist() == [[False, False, False, True, True], [False, False, False, False, True], [False, False, False, False, False]]
    assert np.unique(mask.view(np.uint32)).tolist() == [0, 0xff7f0000]
    assert GATE.causal_mask(2, 0, 'fp32').view(np.uint32)[0, 0, 0, 1] == 0xff7fffff


def test_stage_failure_cannot_hide_behind_final_output_and_fp32_has_no_budget():
    policy = GATE.load_policy(ROOT)
    okay = GATE.compare(np.array([1], np.float32), np.array([1], np.float32))
    bad = GATE.compare(np.array([1.04], np.float32), np.array([1], np.float32))
    assert GATE.stage_verdict('y', okay, 'bf16', policy)['passed'] is True
    assert GATE.stage_verdict('gate', bad, 'bf16', policy)['passed'] is False
    assert GATE.stage_verdict('y', bad, 'fp32', policy)['passed'] is None
    assert GATE.stage_verdict('mask', bad, 'bf16', policy)['passed'] is False
    with pytest.raises(ValueError, match='nonfinite'):
        GATE.compare(np.array([np.inf]), np.array([1]))
    with pytest.raises(ValueError, match='shape'):
        GATE.compare(np.zeros((1, 2)), np.zeros((2, 1)))


def test_qk_export_restores_token_major_order():
    head_major = np.arange(24, dtype=np.float32).reshape(1, 2, 3, 4)
    exported = GATE.export_value(head_major, 'q')
    assert exported.shape == (1, 3, 8)
    np.testing.assert_array_equal(exported[0, 1], [4, 5, 6, 7, 16, 17, 18, 19])


@pytest.mark.parametrize('mode', ['bf16', 'fp32'])
def test_complete_frozen_official_layer_observation_and_independent_carried_cache(mode):
    torch = pytest.importorskip('torch')
    transformers = pytest.importorskip('transformers')
    if transformers.__version__ != '4.40.1':
        pytest.skip('exact frozen Transformers 4.40.1 needed for official-source test')
    module, identity = GATE.runtime_identity(ROOT)
    assert identity['installed_sources_verified_exact']
    torch.set_num_threads(1)
    config = module.Qwen2Config(hidden_size=8, intermediate_size=12, num_attention_heads=2,
                               num_key_value_heads=1, num_hidden_layers=1, max_position_embeddings=16,
                               attention_dropout=0.0, rope_theta=1000000.0, rms_norm_eps=1e-6)
    config._attn_implementation = 'eager'
    dtype = torch.bfloat16 if mode == 'bf16' else torch.float32
    layer = module.Qwen2DecoderLayer(config, 0)
    rng = np.random.default_rng(217)
    weights = {name: GATE.bf16(rng.normal(0, .12, tuple(value.shape)).astype(np.float32))
               for name, value in layer.state_dict().items()}
    for name in ('input_layernorm.weight', 'post_attention_layernorm.weight'):
        weights[name] = GATE.bf16(1 + weights[name])
    layer.load_state_dict({name: torch.from_numpy(value).to(dtype) for name, value in weights.items()}, assign=True)
    layer.to(dtype).eval()
    native_cache = independent_cache = None
    previous = None
    for phase in range(2):
        x = GATE.bf16(rng.normal(0, .3, (1, 4, 8)).astype(np.float32))
        native, native_cache = GATE.native_forward(module, layer, torch.from_numpy(x).to(dtype), mode, native_cache)
        independent, independent_cache = GATE.independent_forward(weights, x, config.to_dict(), mode, independent_cache)
        assert set(native) == set(independent) == GATE.REQUIRED_STAGES
        for name in GATE.REQUIRED_STAGES:
            metrics = GATE.compare(native[name].float().numpy(), independent[name])
            verdict = GATE.stage_verdict(name, metrics, mode, GATE.load_policy(ROOT))
            assert verdict['passed'] is not False, (name, metrics)
        assert native_cache.key_cache[0].shape[-2] == (phase + 1) * 4
        if previous is not None:
            np.testing.assert_array_equal(independent_cache[0][..., :4, :], previous)
        previous = independent_cache[0].copy()
        future = np.broadcast_to(independent['mask'] != 0, independent['prob'].shape)
        assert np.all(independent['prob'][future] == 0)


def test_cache_storage_equality_rejects_signed_zero():
    torch = pytest.importorskip('torch')
    for dtype in (torch.bfloat16, torch.float32):
        positive, negative = torch.tensor([0.], dtype=dtype), torch.tensor([-0.], dtype=dtype)
        assert torch.equal(positive, negative)
        assert not GATE.torch_storage_equal(positive, negative)
        assert GATE.torch_storage_equal(positive, positive.clone())


@pytest.fixture
def small_evidence(tmp_path):
    import json
    import os
    config = {'hidden_size': 8, 'intermediate_size': 12, 'num_attention_heads': 2,
              'num_key_value_heads': 1, 'rope_theta': 1000000., 'rms_norm_eps': 1e-6}
    rng = np.random.default_rng(174)
    weights = {'input_layernorm.weight': np.ones(8, np.float32), 'post_attention_layernorm.weight': np.ones(8, np.float32)}
    for name, out, source in [('self_attn.q_proj', 8, 8), ('self_attn.k_proj', 4, 8),
                              ('self_attn.v_proj', 4, 8), ('self_attn.o_proj', 8, 8),
                              ('mlp.gate_proj', 12, 8), ('mlp.up_proj', 12, 8), ('mlp.down_proj', 8, 12)]:
        weights[name + '.weight'] = GATE.bf16(rng.normal(0, .1, (out, source)).astype(np.float32))
        if name in ('self_attn.q_proj', 'self_attn.k_proj', 'self_attn.v_proj'):
            weights[name + '.bias'] = GATE.bf16(rng.normal(0, .1, out).astype(np.float32))
    embeddings = GATE.bf16(rng.normal(0, .1, (256, 8)).astype(np.float32))
    policy, identity = GATE.load_policy(ROOT), {'runner_sha256': 'fixture'}
    report = {'schema_version': 1, 'tokens': 16, 'carried': False, 'layer': 0,
              'status': 'PASS_BF16_STAGE_BUDGET', 'model_id': 'Qwen/Qwen2-1.5B-Instruct',
              'identity': identity.copy(), 'payload_manifest_sha256': 'payload', 'policy': policy,
              'torch_threads': 4, 'blas_environment': {key: os.environ.get(key) for key in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS')},
              'official_framework_forward': True, 'rtl_execution': False, 'modes': {}}
    for mode in ('bf16', 'fp32'):
        values, _ = GATE.independent_forward(weights, embeddings[:16][None], config, mode)
        phase = {'phase': 0, 'past_tokens': 0, 'token_ids': list(range(16)), 'position_ids': list(range(16)),
                 'failed_stages': [], 'status': 'PASS_BF16_STAGE_BUDGET' if mode == 'bf16' else 'DIAGNOSTIC_FP32',
                 'all_semantics_exact': True, 'semantics': GATE.audit_semantics(values, None, config, mode), 'stages': {}}
        for name, value in values.items():
            entry = GATE.compare(value, value)
            entry.update(GATE.stage_verdict(name, entry, mode, policy))
            is_bf16 = mode == 'bf16' and name != 'softmax_fp32'
            storage = (value.view(np.uint32) >> 16).astype('<u2') if is_bf16 else value
            entry['actual_storage_dtype'] = 'torch.bfloat16' if is_bf16 else 'torch.float32'
            entry['actual_storage_sha256'] = GATE.digest_array(storage)
            for kind in ('native', 'independent'):
                relative = f'{mode}/phase_0/{kind}_{name}.f32le'
                path = tmp_path / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                exported = GATE.export_value(value, name)
                exported.tofile(path)
                entry[kind + '_file'] = relative
                entry[kind + '_file_sha256'] = GATE.sha(path)
                entry[kind + '_export_shape'] = list(exported.shape)
            phase['stages'][name] = entry
        report['modes'][mode] = {'phases': [phase]}
    path = tmp_path / 'RESULT.json'
    path.write_text(json.dumps(report))
    args = (path, identity, 'payload', policy, config, embeddings, False, 4)
    return report, args


def test_full_small_evidence_is_recomputed(small_evidence):
    _, args = small_evidence
    GATE.validate_small_gate(*args)


@pytest.mark.parametrize('mutation', ['abbreviated', 'runner', 'payload', 'policy', 'mode', 'stage', 'file', 'metric', 'carried', 'embedding'])
def test_small_gate_rejects_forgery_drift_and_missing_evidence(small_evidence, mutation):
    import json
    import copy
    report, args = small_evidence
    report = copy.deepcopy(report)
    if mutation == 'abbreviated':
        report = {'tokens': 16, 'status': 'PASS_BF16_STAGE_BUDGET', 'identity': report['identity']}
    elif mutation == 'runner':
        report['identity']['runner_sha256'] = 'old'
    elif mutation == 'payload':
        report['payload_manifest_sha256'] = 'wrong'
    elif mutation == 'policy':
        report['policy']['operator']['max_abs'] = 100.
    elif mutation == 'mode':
        del report['modes']['fp32']
    elif mutation == 'stage':
        del report['modes']['bf16']['phases'][0]['stages']['gate']
    elif mutation == 'file':
        (args[0].parent / 'bf16/phase_0/native_gate.f32le').write_bytes(b'corrupt')
    elif mutation == 'metric':
        report['modes']['bf16']['phases'][0]['stages']['gate']['max_abs'] = .001
    elif mutation == 'carried':
        args = args[:-2] + (True, args[-1])
    elif mutation == 'embedding':
        embeddings = args[5].copy()
        embeddings[0, 0] += 1
        args = args[:5] + (embeddings,) + args[6:]
    args[0].write_text(json.dumps(report))
    with pytest.raises(ValueError, match='M16|evidence'):
        GATE.validate_small_gate(*args)
