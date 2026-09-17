"""Compiler contract tests, not RTL or official checkpoint inference."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu import qwen_family_contracts as family
from heteronpu.model_geometry import BlockGeometry, ModelContractError, load_profile, validate_profile


def profiles():
    return [load_profile(ROOT / 'config/model_profiles' / name)
            for name in ('qwen3_5_35b_a3b.json', 'qwen3_8_flash_next.json')]


@pytest.mark.parametrize('i', [0, 1])
@pytest.mark.parametrize('key,value', [('model_id', 'WRONG/MODEL'), ('architecture_family', 'typo'),
    ('revision', 'main'), ('hidden_size', True), ('num_hidden_layers', 0),
    ('is_qwen3_dense_architecture', True), ('hf_model_type', 'qwen3')])
def test_reject_identity_at_all_entrypoints(i, key, value):
    a, b = profiles(); p = deepcopy((a, b)[i]); p[key] = value
    for fn in (validate_profile, family.inventory, family.states, family.schedule, family.summary,
               lambda p: family.layer_ops(p, 0), BlockGeometry.from_profile):
        with pytest.raises(ModelContractError):
            fn(p)
    with pytest.raises(ModelContractError):
        family.validate(p, b) if i == 0 else family.validate(a, p)


@pytest.mark.parametrize('section,key,value', [
    ('full_attention', 'q_heads', 8), ('full_attention', 'head_dim', 0),
    ('full_attention', 'kv_heads', True), ('full_attention', 'rotary_dim', 65),
    ('gated_deltanet', 'v_heads', 31), ('gated_deltanet', 'key_dim', '128'),
    ('gated_deltanet', 'chunk_size', -1), ('moe', 'top_k', 257),
    ('moe', 'intermediate_size', 65536), ('moe', 'norm_topk_prob', 1)])
def test_reject_shape_and_semantics(section, key, value):
    p = profiles()[0]; p[section][key] = value
    with pytest.raises(ModelContractError): validate_profile(p)


@pytest.mark.parametrize('i,kind', [(0, 'missing'), (0, 'unknown'), (0, 'qsa'), (1, 'duplicate_ple'),
                                   (1, 'top512'), (1, 'branches')])
def test_reject_pattern_and_cross_family(i, kind):
    p = profiles()[i]
    if kind == 'missing': p['layer_pattern'].pop()
    elif kind == 'unknown': p['layer_pattern'][0] = 'unsupported'
    elif kind == 'qsa': p['qsa'] = {'block_budget': 512}
    elif kind == 'duplicate_ple': p['ple']['layer_ids'] = [2, 2]
    elif kind == 'top512': p['qsa']['block_budget'] = 1024
    else: p['gated_residual']['branches'] = 1
    with pytest.raises(ModelContractError): validate_profile(p)


@pytest.mark.parametrize('i', [-1, 40, True, 0.5])
def test_no_negative_index_wrap(i):
    with pytest.raises(ModelContractError): family.layer_ops(profiles()[0], i)


def test_preserve_existing_ple_layer_index_convention():
    p = profiles()[1]
    assert 'ple_ngram_hash' not in family.layer_ops(p, 0)
    assert 'ple_ngram_hash' in family.layer_ops(p, 1)
    assert 'ple_ngram_hash' not in family.layer_ops(p, 2)


def test_geometry_independent_widths_and_large_budget():
    a, b = [BlockGeometry.from_profile(p).report(1024, 4096) for p in profiles()]
    assert (a['hidden'], a['q_width'], a['kv_width']) == (2048, 4096, 512)
    assert (b['hidden'], b['q_width'], b['kv_width']) == (2560, 6144, 512)
    assert a['gdn_state_fp32_bytes'] == 2097152 and b['gdn_state_fp32_bytes'] == 3145728
    assert a['routed_expert_three_matrices_bf16_bytes'] == 1610612736
    assert b['routed_expert_three_matrices_bf16_bytes'] == 5033164800  # greater than 32-bit
    assert b['residual_fp32_bytes_assuming_materialization'] == 41943040
    assert b['dense_shapes_MNK']['attention_output'] == [1024, 2560, 6144]
    assert not b['rtl_execution'] and not b['official_source_reverified']


@pytest.mark.parametrize('tokens,kv', [(0, 1), (1025, 2048), (True, 1), (16, 15), (16, 0), (16, 2**32)])
def test_length_limits_not_square_attention(tokens, kv):
    with pytest.raises(ModelContractError): BlockGeometry.from_profile(profiles()[0]).report(tokens, kv)


@pytest.mark.parametrize('raw', ['{"x": 1, "x": 2}', '{"x": NaN}', '{"x": Infinity}'])
def test_json_not_silently_overridden_or_nonfinite(tmp_path, raw):
    p = tmp_path / 'bad.json'; p.write_text(raw)
    with pytest.raises(ModelContractError): load_profile(p)


@pytest.mark.parametrize('optimized', [False, True])
def test_real_python_interpreter_rejects_corruption(optimized):
    code = '''import json,sys
sys.path.insert(0,'src')
from heteronpu.qwen_family_contracts import *
a=load_profile('config/model_profiles/qwen3_5_35b_a3b.json');b=load_profile('config/model_profiles/qwen3_8_flash_next.json')
a['model_id']='WRONG/MODEL'
try: validate(a,b)
except ValueError: print('REJECTED_WRONG_MODEL')
else: raise SystemExit(7)
a['architecture_family']='unknown'
try: inventory(a)
except ValueError: print('REJECTED_UNKNOWN_FAMILY')
else: raise SystemExit(8)
'''
    result = subprocess.run([sys.executable] + (['-O'] if optimized else []) + ['-c', code],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ['REJECTED_WRONG_MODEL', 'REJECTED_UNKNOWN_FAMILY']


def test_legal_report_digest_is_unchanged_from_pre_fix():
    result = family.family_contract_report(ROOT / 'config/model_profiles/qwen3_5_35b_a3b.json',
                                          ROOT / 'config/model_profiles/qwen3_8_flash_next.json')
    assert result['sha256'] == '938da9c38720fea7cbf6632f04f1550013f5a38ce78ff70ba3f9a159af5e2dd0'


@pytest.mark.parametrize('field,value', [('q_heads', 3), ('value_heads', 17), ('top_k', 300), ('head_dim', 65535), ('hidden', False)])
def test_direct_geometry_does_not_truncate_or_accept_bad_groups(field, value):
    from dataclasses import replace
    with pytest.raises(ModelContractError): replace(BlockGeometry.from_profile(profiles()[0]), **{field: value})
