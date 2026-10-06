"""Pinned dense Qwen3.5 compiler contracts; no weight or RTL execution claim."""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu import qwen_family_contracts as family
from heteronpu import qwen35_dense_contract as dense_contract
from heteronpu.model_geometry import (
    BlockGeometry,
    ModelContractError,
    load_profile,
    validate_profile,
)
from heteronpu.model_support import Level, ModelProfile

PROFILE_DIR = ROOT / "config/model_profiles"
DENSE_PATH = PROFILE_DIR / "qwen3_5_0p8b.json"
MOE_PATH = PROFILE_DIR / "qwen3_5_35b_a3b.json"
NEXT_PATH = PROFILE_DIR / "qwen3_8_flash_next.json"
DENSE_FAMILY = "qwen3_5_hybrid_gdn_full_attention_dense"
DENSE_FFN_OPS = (
    "dense_ffn_gate_up",
    "dense_ffn_silu_product",
    "dense_ffn_down",
)
LEGACY_REPORT_SHA256 = "938da9c38720fea7cbf6632f04f1550013f5a38ce78ff70ba3f9a159af5e2dd0"
MODEL_REVISION = "2fc06364715b967f1860aea9cf38778875588b17"
FORWARD_REVISION = "14e738b5d0cc69aa27a95dde272aea41fde44f2f"
SOURCE_RELATIVE = Path("config/upstream/qwen3_5_0p8b")
SOURCE_SHA256 = {
    "config.json": "b90b86f35c8e6925ef74ee04d0e758f0a845c83a42089ad82bbaa948de9b4204",
    "model.safetensors.index.json": "d8a08838a613b025eb7952ed9db11696213e57e76a375661ef5c12f9dd5dcf4e",
    "configuration_qwen3_5.py": "2f26c4bb911772d42a5f16e82bdea4b9ba1ac07872df527ec228622d35f3c30e",
    "modeling_qwen3_5.py": "aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18",
    "modular_qwen3_5.py": "ba423e1400fc253dce1cdbb215463675ea09c96df5a379b43e985d36c9e675c7",
}


@pytest.fixture
def dense_profile():
    return load_profile(DENSE_PATH)


def single_profile_entrypoints():
    return (
        validate_profile,
        BlockGeometry.from_profile,
        ModelProfile,
        family.inventory,
        family.states,
        family.schedule,
        family.summary,
        dense_contract.tensor_shapes,
        lambda profile: family.layer_ops(profile, 0),
    )


def assert_rejected_everywhere(profile):
    for entrypoint in single_profile_entrypoints():
        with pytest.raises(ModelContractError):
            entrypoint(deepcopy(profile))


def test_profile_pins_dense_hybrid_identity_and_complete_pattern(dense_profile):
    p = dense_profile
    assert p["architecture_family"] == DENSE_FAMILY
    assert p["ffn_architecture"] == "dense_swiglu"
    assert p["model_id"] == "Qwen/Qwen3.5-0.8B"
    assert p["revision"] == "2fc06364715b967f1860aea9cf38778875588b17"
    assert p["hf_model_type"] == "qwen3_5"
    assert p["text_model_type"] == "qwen3_5_text"
    assert p["residual_architecture"] == "single_stream_standard_residual"
    assert p["is_qwen3_dense_architecture"] is False
    assert p["attention_output_gate"] is True
    assert (p["hidden_size"], p["num_hidden_layers"]) == (1024, 24)
    assert p["layer_pattern"] == (["gated_deltanet"] * 3 + ["full_attention"]) * 6
    assert Counter(p["layer_pattern"]) == {"gated_deltanet": 18, "full_attention": 6}
    assert p["dense_ffn"] == {"intermediate_size": 3584, "hidden_act": "silu", "bias": False}
    assert p["gated_deltanet"]["state_dtype"] == "float32"
    assert p["full_attention"]["q_projection_packing"] == "per_head_query_gate"
    assert p["full_attention"]["bias"] is False
    assert all(key not in p for key in ("moe", "qsa", "ple", "gated_residual", "mtp"))
    for key, value in {"q_heads": 8, "kv_heads": 2, "head_dim": 256, "rotary_dim": 64}.items():
        assert p["full_attention"][key] == value
    for key, value in {"qk_heads": 16, "v_heads": 16, "key_dim": 128,
                       "value_dim": 128, "conv_kernel": 4, "chunk_size": 64}.items():
        assert p["gated_deltanet"][key] == value


def test_dense_geometry_has_independent_widths_and_exact_memory_budgets(dense_profile):
    geometry = BlockGeometry.from_profile(dense_profile)
    assert (geometry.hidden, geometry.dense_ffn, geometry.branches) == (1024, 3584, 1)
    assert (geometry.expert_ffn, geometry.experts, geometry.top_k) == (0, 0, 0)
    assert (geometry.q_width, geometry.kv_width) == (2048, 512)
    assert (geometry.gdn_value_width, geometry.gdn_conv_channels) == (2048, 6144)

    report = geometry.report()
    assert (report["query_tokens"], report["kv_tokens"]) == (128, 128)
    assert report["dense_ffn"] == 3584
    assert report["gdn_state_fp32_bytes"] == 1048576
    assert report["routed_expert_three_matrices_bf16_bytes"] == 0
    assert report["dense_ffn_three_matrices_bf16_bytes"] == 22020096
    assert report["residual_fp32_bytes_assuming_materialization"] == 524288
    assert report["kv_bf16_bytes"] == 262144
    shapes = report["dense_shapes_MNK"]
    assert shapes["dense_ffn_gate_up_each"] == [128, 3584, 1024]
    assert shapes["dense_ffn_down"] == [128, 1024, 3584]
    assert shapes["attention_q"] == [128, 2048, 1024]
    assert shapes["attention_query_and_gate"] == [128, 4096, 1024]
    assert shapes["attention_kv_each"] == [128, 512, 1024]
    assert shapes["attention_output"] == [128, 1024, 2048]
    assert shapes["gdn_output"] == [128, 1024, 2048]
    assert not any("router" in key or "expert" in key for key in shapes)
    assert report["evidence_class"] == "repository_profile_geometry_E0"
    assert report["rtl_execution"] is False
    assert report["official_source_reverified"] is False


def test_dense_report_separates_prefill_and_kv_lengths(dense_profile):
    report = BlockGeometry.from_profile(dense_profile).report(1024, 4096)
    assert report["query_tokens"] == 1024
    assert report["kv_tokens"] == 4096
    assert report["kv_bf16_bytes"] == 8388608
    assert report["dense_shapes_MNK"]["dense_ffn_gate_up_each"] == [1024, 3584, 1024]
    assert report["dense_shapes_MNK"]["attention_query_and_gate"] == [1024, 4096, 1024]
    assert report["dense_ffn_three_matrices_bf16_bytes"] == 22020096


def test_dense_family_inventory_states_and_schedule_are_isolated(dense_profile):
    operators = {op.name: op for op in family.inventory(dense_profile)}
    assert set(DENSE_FFN_OPS) <= operators.keys()
    assert {"dense_full_attention_qkv", "dense_full_attention_mlo", "gdn_projection",
            "gdn_recurrent_update", "standard_residual_add"} <= operators.keys()
    assert not any(name.startswith(("moe_", "qsa_", "ple_", "gated_residual_"))
                   or name in {"group_rmsnorm", "mtp_state_transaction"} for name in operators)

    states = set(family.states(dense_profile))
    assert {"dense_kv_cache", "gdn_recurrent_matrix", "gdn_causal_conv_history"} <= states
    assert "moe_weight_cache_metadata" not in states
    assert not any(name.startswith(("moe_", "qsa_", "ple_", "mtp_"))
                   or "hyper_residual" in name for name in states)

    scheduled = family.schedule(dense_profile)
    assert [item["op_id"] for item in scheduled] == list(range(len(scheduled)))
    assert {item["layer"] for item in scheduled} == set(range(24))
    assert all(item["operator"] in operators for item in scheduled)
    counts = Counter(item["operator"] for item in scheduled)
    assert all(counts[op] == 24 for op in DENSE_FFN_OPS)
    assert counts["gdn_recurrent_update"] == 18
    assert counts["dense_full_attention_mlo"] == 6
    for layer in range(24):
        ops = family.layer_ops(dense_profile, layer)
        assert ops[-4:] == (*DENSE_FFN_OPS, "standard_residual_add")
        assert "moe_router_topk" not in ops
        assert ("dense_full_attention_mlo" in ops) == (layer % 4 == 3)
        assert ("gdn_recurrent_update" in ops) == (layer % 4 != 3)
        layer_schedule = [item for item in scheduled if item["layer"] == layer]
        assert tuple(item["operator"] for item in layer_schedule) == ops
        assert all(item["layer_type"] == dense_profile["layer_pattern"][layer]
                   and item["owner"] == operators[item["operator"]].owner for item in layer_schedule)

    summary = family.summary(dense_profile)
    assert summary["architecture_family"] == DENSE_FAMILY
    assert summary["layers"] == 24
    assert summary["layer_type_counts"] == {"gated_deltanet": 18, "full_attention": 6}
    assert summary["schedule_operator_counts"] == dict(counts)
    assert summary["schedule_ops"] == len(scheduled)
    assert set(summary["state_domains"]) == states
    assert family.schedule(deepcopy(dense_profile)) == scheduled


@pytest.mark.parametrize("key,value", [
    ("model_id", "Qwen/Qwen3.5-35B-A3B"),
    ("revision", "main"),
    ("config_sha256", "wrong-config-digest"),
    ("architecture_family", "qwen3_5_hybrid_gdn_full_attention_moe"),
    ("architecture_family", "qwen4_exp_flash_next"),
    ("architecture_family", "unknown"),
    ("ffn_architecture", "moe"),
    ("ffn_architecture", None),
    ("hf_model_type", "qwen3_5_moe"),
    ("text_model_type", "qwen3_5_moe_text"),
    ("residual_architecture", "four_branch_gated_residual"),
    ("is_qwen3_dense_architecture", True),
    ("is_qwen3_dense_architecture", 0),
    ("attention_output_gate", False),
    ("attention_output_gate", 1),
])
def test_dense_identity_and_boolean_corruption_rejected_everywhere(dense_profile, key, value):
    dense_profile[key] = value
    assert_rejected_everywhere(dense_profile)


@pytest.mark.parametrize("section,key,value", [
    (None, "hidden_size", 2048),
    (None, "hidden_size", True),
    (None, "hidden_size", 1024.0),
    (None, "num_hidden_layers", 23),
    (None, "num_hidden_layers", 0),
    (None, "vocab_size", 248321),
    (None, "vocab_size", True),
    (None, "context_length", 32768),
    (None, "context_length", 262144.0),
    ("full_attention", "q_heads", 16),
    ("full_attention", "q_heads", True),
    ("full_attention", "kv_heads", 1),
    ("full_attention", "head_dim", 128),
    ("full_attention", "rotary_dim", 65),
    ("full_attention", "q_projection_packing", "query_only"),
    ("full_attention", "bias", 0),
    ("full_attention", "attention_kind", "sparse_gqa"),
    ("full_attention", "block_tokens", 64),
    ("full_attention", "block_tokens", 128.0),
    ("gated_deltanet", "qk_heads", 8),
    ("gated_deltanet", "v_heads", 32),
    ("gated_deltanet", "key_dim", "128"),
    ("gated_deltanet", "value_dim", 64),
    ("gated_deltanet", "conv_kernel", 3),
    ("gated_deltanet", "chunk_size", 0),
    ("gated_deltanet", "chunk_size", False),
    ("gated_deltanet", "state_dtype", "bfloat16"),
    ("dense_ffn", "intermediate_size", 512),
    ("dense_ffn", "intermediate_size", 3584.0),
    ("dense_ffn", "intermediate_size", "3584"),
    ("dense_ffn", "intermediate_size", True),
    ("dense_ffn", "intermediate_size", 0),
    ("dense_ffn", "intermediate_size", -1),
    ("dense_ffn", "hidden_act", "gelu"),
    ("dense_ffn", "hidden_act", None),
    ("dense_ffn", "bias", True),
    ("dense_ffn", "bias", 0),
    ("dense_ffn", "bias", None),
    ("normalization", "rms_norm_eps", 1e-5),
    ("normalization", "decoder_qk_weight", "weight"),
    ("normalization", "gdn_gated_weight", "1+weight"),
    ("normalization", "gdn_gate_activation", "sigmoid"),
    ("rope", "partial_rotary_factor", 0.5),
    ("rope", "theta", 10000),
    ("rope", "mrope_interleaved", False),
    ("rope", "mrope_interleaved", 1),
    ("rope", "mrope_section", [10, 11, 11]),
    ("transformers_source", "repository", "untrusted/transformers"),
    ("transformers_source", "commit", "main"),
    ("transformers_source", "sha256", "0" * 64),
    ("transformers_source", "module", "src/transformers/models/qwen3_5_moe/modeling_qwen3_5_moe.py"),
])
def test_dense_shape_and_ffn_semantics_rejected_everywhere(dense_profile, section, key, value):
    target = dense_profile if section is None else dense_profile[section]
    target[key] = value
    assert_rejected_everywhere(dense_profile)


@pytest.mark.parametrize("key", ["ffn_architecture", "dense_ffn", "full_attention", "gated_deltanet"])
def test_dense_required_sections_and_discriminator_cannot_be_missing(dense_profile, key):
    del dense_profile[key]
    assert_rejected_everywhere(dense_profile)


@pytest.mark.parametrize("value", [None, {}, [], 0, False,
                                  {"num_experts": 1, "top_k": 1, "intermediate_size": 3584}])
def test_dense_rejects_moe_key_even_when_empty_or_false(dense_profile, value):
    dense_profile["moe"] = value
    assert_rejected_everywhere(dense_profile)


@pytest.mark.parametrize("key,value", [
    ("qsa", {"block_budget": 512}),
    ("ple", {"layer_ids": [2]}),
    ("gated_residual", {"branches": 4}),
    ("qsa", {}),
    ("ple", None),
    ("gated_residual", {}),
    ("mtp", {"layers": 1}),
    ("mtp", None),
])
def test_dense_text_blocks_cannot_acquire_qwen38_or_mtp_features(dense_profile, key, value):
    dense_profile[key] = value
    assert_rejected_everywhere(dense_profile)


@pytest.mark.parametrize("kind", ["missing", "extra", "wrong_order", "unknown", "qsa", "legacy_linear"])
def test_dense_requires_exact_complete_layer_pattern(dense_profile, kind):
    pattern = dense_profile["layer_pattern"]
    if kind == "missing":
        pattern.pop()
    elif kind == "extra":
        pattern.append("gated_deltanet")
    elif kind == "wrong_order":
        pattern[0], pattern[3] = pattern[3], pattern[0]
    else:
        pattern[0] = {"unknown": "unsupported", "qsa": "qwen_sparse_attention",
                      "legacy_linear": "linear_attention"}[kind]
    assert_rejected_everywhere(dense_profile)


@pytest.mark.parametrize("layer", [-1, 24, True, 0.0, "0"])
def test_dense_layer_index_never_wraps_or_coerces(dense_profile, layer):
    with pytest.raises(ModelContractError):
        family.layer_ops(dense_profile, layer)


@pytest.mark.parametrize("tokens,kv_tokens", [(0, None), (1025, None), (True, None),
                                            (128.0, None), (16, 15), (16, 0),
                                            (16, True), (16, 32.0), (16, 2**32)])
def test_dense_report_rejects_invalid_lengths(dense_profile, tokens, kv_tokens):
    with pytest.raises(ModelContractError):
        BlockGeometry.from_profile(dense_profile).report(tokens, kv_tokens)


@pytest.mark.parametrize("updates", [
    {"dense_ffn": 0},
    {"dense_ffn": -1},
    {"dense_ffn": True},
    {"dense_ffn": 3584.0},
    {"dense_ffn": 65536},
    {"expert_ffn": 512},
    {"experts": 256},
    {"top_k": 8},
    {"expert_ffn": False},
    {"experts": 0.0},
    {"top_k": False},
    {"expert_ffn": 512, "experts": 256, "top_k": 8},
    {"hidden": False},
    {"q_heads": 3},
    {"q_heads": 128},  # Q width fits uint16, but the fused query/gate width does not.
    {"value_heads": 17},
    {"head_dim": 65535},
    {"branches": False},
])
def test_direct_dense_geometry_rejects_invalid_or_mixed_ffn_modes(dense_profile, updates):
    with pytest.raises(ModelContractError):
        replace(BlockGeometry.from_profile(dense_profile), **updates)


def test_direct_moe_geometry_cannot_acquire_dense_ffn():
    for path in (MOE_PATH, NEXT_PATH):
        geometry = BlockGeometry.from_profile(load_profile(path))
        with pytest.raises(ModelContractError):
            replace(geometry, dense_ffn=3584)
        with pytest.raises(ModelContractError):
            replace(geometry, expert_ffn=0, experts=0, top_k=0)


@pytest.mark.parametrize("optimized", [False, True])
def test_dense_contracts_fail_closed_in_real_interpreter(optimized):
    code = r'''
from copy import deepcopy
from dataclasses import replace
import sys
sys.path.insert(0, 'src')
from heteronpu import qwen_family_contracts as family
from heteronpu.model_geometry import BlockGeometry, ModelContractError, load_profile, validate_profile
p = load_profile('config/model_profiles/qwen3_5_0p8b.json')
entrypoints = (validate_profile, BlockGeometry.from_profile, family.inventory,
               family.states, family.schedule, family.summary,
               lambda profile: family.layer_ops(profile, 0))
bad_profiles = []
for key, value in (('moe', None), ('ffn_architecture', 'moe'), ('hidden_size', True)):
    bad = deepcopy(p)
    bad[key] = value
    bad_profiles.append(bad)
bad = deepcopy(p)
bad['dense_ffn']['bias'] = 0
bad_profiles.append(bad)
rejected = 0
for bad in bad_profiles:
    for entrypoint in entrypoints:
        try:
            entrypoint(bad)
        except ModelContractError:
            rejected += 1
        else:
            raise SystemExit('invalid dense profile was accepted')
geometry = BlockGeometry.from_profile(p)
for operation in (lambda: replace(geometry, dense_ffn=0),
                  lambda: replace(geometry, expert_ffn=512, experts=256, top_k=8),
                  lambda: geometry.report(True),
                  lambda: family.layer_ops(p, -1)):
    try:
        operation()
    except ModelContractError:
        rejected += 1
    else:
        raise SystemExit('invalid dense geometry was accepted')
if rejected != 32:
    raise SystemExit('not all rejection paths executed')
print('REJECTED_32_DENSE_CONTRACT_VIOLATIONS')
'''
    result = subprocess.run(
        [sys.executable] + (["-O"] if optimized else []) + ["-c", code],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == ["REJECTED_32_DENSE_CONTRACT_VIOLATIONS"]


def test_dense_addition_preserves_legacy_two_model_report():
    report = family.family_contract_report(MOE_PATH, NEXT_PATH)
    assert report["status"] == "PASS"
    assert report["sha256"] == LEGACY_REPORT_SHA256
    with pytest.raises(ModelContractError):
        family.validate(load_profile(DENSE_PATH), load_profile(NEXT_PATH))


@pytest.fixture
def copied_source_root(tmp_path):
    """Copy only contract inputs; never mutate the repository's pinned evidence."""
    shutil.copytree(ROOT / SOURCE_RELATIVE, tmp_path / SOURCE_RELATIVE)
    profile_dir = tmp_path / "config/model_profiles"
    profile_dir.mkdir(parents=True)
    shutil.copyfile(DENSE_PATH, profile_dir / DENSE_PATH.name)
    return tmp_path


def test_source_bundle_verifies_independent_config_and_forward_pins():
    manifest, config, index = dense_contract.source_bundle(ROOT)
    assert manifest["model_id"] == "Qwen/Qwen3.5-0.8B"
    assert manifest["model_revision"] == MODEL_REVISION
    assert manifest["modeling_repository"] == "huggingface/transformers"
    assert manifest["modeling_revision"] == FORWARD_REVISION
    assert len(manifest["files"]) == 5
    assert {item["file"] for item in manifest["files"]} == set(SOURCE_SHA256)
    for item in manifest["files"]:
        filename = item["file"]
        raw = (ROOT / SOURCE_RELATIVE / filename).read_bytes()
        assert item["sha256"] == SOURCE_SHA256[filename] == hashlib.sha256(raw).hexdigest()
        assert type(item["bytes"]) is int and item["bytes"] == len(raw)
        if filename.endswith(".py"):
            assert item["revision"] == FORWARD_REVISION
            expected_url = ("https://raw.githubusercontent.com/huggingface/transformers/"
                            f"{FORWARD_REVISION}/src/transformers/models/qwen3_5/{filename}")
        else:
            assert item["revision"] == MODEL_REVISION
            expected_url = f"https://huggingface.co/Qwen/Qwen3.5-0.8B/resolve/{MODEL_REVISION}/{filename}"
        assert item["url"] == expected_url
    assert config["text_config"]["hidden_size"] == 1024
    assert config["text_config"]["intermediate_size"] == 3584
    assert sum(key.startswith("model.language_model.") for key in index["weight_map"]) == 320


def test_tensor_shapes_match_all_320_official_text_index_keys(dense_profile):
    _, _, index = dense_contract.source_bundle(ROOT)
    shapes = dense_contract.tensor_shapes(dense_profile)
    text_keys = {key for key in index["weight_map"] if key.startswith("model.language_model.")}
    assert len(shapes) == 320
    assert set(shapes) == text_keys
    assert shapes["model.language_model.embed_tokens.weight"] == [248320, 1024]
    assert shapes["model.language_model.norm.weight"] == [1024]
    assert all(all(type(dim) is int and dim > 0 for dim in shape) for shape in shapes.values())
    assert not any(".experts." in key or ".mtp." in key or ".visual." in key for key in shapes)


@pytest.mark.parametrize("layer,attention_shapes", [
    (0, {
        "linear_attn.in_proj_qkv.weight": [6144, 1024],
        "linear_attn.in_proj_z.weight": [2048, 1024],
        "linear_attn.in_proj_b.weight": [16, 1024],
        "linear_attn.in_proj_a.weight": [16, 1024],
        "linear_attn.conv1d.weight": [6144, 1, 4],
        "linear_attn.dt_bias": [16],
        "linear_attn.A_log": [16],
        "linear_attn.norm.weight": [128],
        "linear_attn.out_proj.weight": [1024, 2048],
    }),
    (3, {
        "self_attn.q_proj.weight": [4096, 1024],
        "self_attn.k_proj.weight": [512, 1024],
        "self_attn.v_proj.weight": [512, 1024],
        "self_attn.o_proj.weight": [1024, 2048],
        "self_attn.q_norm.weight": [256],
        "self_attn.k_norm.weight": [256],
    }),
])
def test_typical_gdn_and_full_attention_block_tensor_shapes(dense_profile, layer, attention_shapes):
    prefix = f"model.language_model.layers.{layer}."
    actual = {key[len(prefix):]: shape for key, shape in dense_contract.tensor_shapes(dense_profile).items()
              if key.startswith(prefix)}
    expected = {
        "input_layernorm.weight": [1024],
        "post_attention_layernorm.weight": [1024],
        "mlp.gate_proj.weight": [3584, 1024],
        "mlp.up_proj.weight": [3584, 1024],
        "mlp.down_proj.weight": [1024, 3584],
        **attention_shapes,
    }
    assert actual == expected


@pytest.mark.parametrize("path", [MOE_PATH, NEXT_PATH])
def test_dense_tensor_shape_entrypoint_rejects_other_supported_families(path):
    with pytest.raises(ModelContractError):
        dense_contract.tensor_shapes(load_profile(path))


def test_contract_report_verifies_names_without_claiming_execution_or_u00_closure(dense_profile):
    report = dense_contract.contract_report(ROOT)
    _, _, index = dense_contract.source_bundle(ROOT)
    assert report["status"] == "PASS_PINNED_GEOMETRY_E0_ONLY"
    assert report["model_id"] == "Qwen/Qwen3.5-0.8B"
    assert report["model_revision"] == MODEL_REVISION
    assert report["profile_sha256"] == hashlib.sha256(DENSE_PATH.read_bytes()).hexdigest()
    assert report["index_names_verified"] is True
    assert report["main_text_tensor_count"] == 320
    assert report["index_total_tensor_count"] == len(index["weight_map"])
    assert report["tensor_shapes_derived_not_weight_header_verified"] == dense_contract.tensor_shapes(dense_profile)
    assert report["geometry_M128"] == BlockGeometry.from_profile(dense_profile).report(128)
    assert report["family"] == family.summary(dense_profile)
    assert report["query_gate_packing"] == {
        "projected_shape": [128, 8, 512],
        "query_slice_per_head": [0, 256],
        "gate_slice_per_head": [256, 512],
        "gate_activation_before_output_projection": "sigmoid",
    }
    assert report["typical_block_geometry"] == [
        {"block_type": "B35_08_GDN_DENSE", "layer_id_zero_based": 0,
         "operators": family.layer_ops(dense_profile, 0)},
        {"block_type": "B35_08_ATTN_DENSE", "layer_id_zero_based": 3,
         "operators": family.layer_ops(dense_profile, 3)},
    ]
    for key in ("weights_loaded", "numerical_execution", "rtl_execution",
                "mac_utilization_measured", "full_U00_complete"):
        assert report[key] is False
    assert "checkpoint weight bytes/shape headers" in report["unresolved_gates"]
    assert any("precision" in gate for gate in report["unresolved_gates"])
    assert any("workload" in gate for gate in report["unresolved_gates"])
    assert any("RTL" in gate and "MAC" in gate for gate in report["unresolved_gates"])
    assert dense_contract.contract_report(ROOT) == report


@pytest.mark.parametrize("filename", list(SOURCE_SHA256))
def test_source_bundle_and_report_reject_one_byte_raw_file_corruption(copied_source_root, filename):
    path = copied_source_root / SOURCE_RELATIVE / filename
    original = path.read_bytes()
    corrupted = original[:-1] + bytes([original[-1] ^ 1])
    assert len(corrupted) == len(original)
    assert sum(a != b for a, b in zip(original, corrupted)) == 1
    path.write_bytes(corrupted)
    for entrypoint in (dense_contract.source_bundle, dense_contract.contract_report):
        with pytest.raises(ModelContractError, match="SHA256"):
            entrypoint(copied_source_root)


def test_contract_report_rejects_one_byte_profile_revision_corruption(copied_source_root):
    path = copied_source_root / "config/model_profiles" / DENSE_PATH.name
    original = path.read_bytes()
    corrupted = original.replace(MODEL_REVISION.encode(), ("3" + MODEL_REVISION[1:]).encode(), 1)
    assert sum(a != b for a, b in zip(original, corrupted)) == 1
    path.write_bytes(corrupted)
    with pytest.raises(ModelContractError, match="revision"):
        dense_contract.contract_report(copied_source_root)


@pytest.mark.parametrize("key,value", [
    ("model_id", "Qwen/Qwen3.5-35B-A3B"),
    ("model_revision", "main"),
    ("modeling_repository", "untrusted/transformers"),
    ("modeling_revision", "main"),
])
def test_source_manifest_rejects_changed_top_level_identity(copied_source_root, key, value):
    path = copied_source_root / SOURCE_RELATIVE / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest[key] = value
    path.write_text(json.dumps(manifest))
    for entrypoint in (dense_contract.source_bundle, dense_contract.contract_report):
        with pytest.raises(ModelContractError):
            entrypoint(copied_source_root)


@pytest.mark.parametrize("filename", ["config.json", "modeling_qwen3_5.py"])
@pytest.mark.parametrize("field,value", [
    ("sha256", "0" * 64),
    ("url", "https://untrusted.invalid/config.json"),
    ("revision", "main"),
    ("bytes", 0),
    ("bytes", True),
])
def test_source_manifest_rejects_false_file_metadata(copied_source_root, filename, field, value):
    path = copied_source_root / SOURCE_RELATIVE / "manifest.json"
    manifest = json.loads(path.read_text())
    record = next(item for item in manifest["files"] if item["file"] == filename)
    record[field] = value
    path.write_text(json.dumps(manifest))
    for entrypoint in (dense_contract.source_bundle, dense_contract.contract_report):
        with pytest.raises(ModelContractError):
            entrypoint(copied_source_root)


@pytest.mark.parametrize("kind", ["append_duplicate", "replace_with_duplicate", "missing", "unknown"])
def test_source_manifest_rejects_duplicate_or_changed_file_inventory(copied_source_root, kind):
    path = copied_source_root / SOURCE_RELATIVE / "manifest.json"
    manifest = json.loads(path.read_text())
    if kind == "append_duplicate":
        manifest["files"].append(deepcopy(manifest["files"][0]))
    elif kind == "replace_with_duplicate":
        manifest["files"][-1] = deepcopy(manifest["files"][0])
    elif kind == "missing":
        manifest["files"].pop()
    else:
        manifest["files"][0]["file"] = "unrecognized.json"
    path.write_text(json.dumps(manifest))
    for entrypoint in (dense_contract.source_bundle, dense_contract.contract_report):
        with pytest.raises(ModelContractError):
            entrypoint(copied_source_root)


def test_changing_raw_file_and_manifest_hash_together_cannot_repin_source(copied_source_root):
    directory = copied_source_root / SOURCE_RELATIVE
    config_path = directory / "config.json"
    original = config_path.read_bytes()
    corrupted = original[:-1] + bytes([original[-1] ^ 1])
    config_path.write_bytes(corrupted)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    record = next(item for item in manifest["files"] if item["file"] == "config.json")
    record["sha256"] = hashlib.sha256(corrupted).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    for entrypoint in (dense_contract.source_bundle, dense_contract.contract_report):
        with pytest.raises(ModelContractError, match="SHA256"):
            entrypoint(copied_source_root)


def test_model_support_requires_dense_ffn_and_gate_without_moe_or_mtp_policy():
    profile = ModelProfile.load(DENSE_PATH)
    required = set(profile.required())
    assert {"dense_swiglu_ffn", "attention_output_gate", "dense_bf16_gemm",
            "gated_deltanet_recurrent", "gated_deltanet_prefill", "causal_conv1d"} <= required
    assert not any(name.startswith(("moe_", "mtp_", "qsa_", "ple_", "qwen38_"))
                   or name == "gated_residual" for name in required)
    support = profile.support()
    assert set(support) == required
    assert support["dense_swiglu_ffn"] == Level.ANALYSIS.value
    assert support["attention_output_gate"] == Level.EXECUTABLE_E0.value
    assert support["vision_encoder"] == Level.UNSUPPORTED.value
    policies = profile.policies()
    assert {"attention_op", "delta_policy"} <= policies.keys()
    assert not any(name.startswith(("moe_", "mtp_", "qsa_", "ple_", "gated_residual_"))
                   for name in policies)
    assert profile.runtime_schedule() is None


@pytest.mark.parametrize("key,value", [
    ("model_id", "Qwen/Qwen3.5-35B-A3B"),
    ("ffn_architecture", "moe"),
    ("moe", {}),
])
def test_model_support_constructor_and_loader_reject_corrupt_dense_profile(dense_profile, tmp_path, key, value):
    dense_profile[key] = value
    with pytest.raises(ModelContractError):
        ModelProfile(dense_profile)
    path = tmp_path / "corrupt_dense_profile.json"
    path.write_text(json.dumps(dense_profile))
    with pytest.raises(ModelContractError):
        ModelProfile.load(path)


@pytest.mark.parametrize("duplicate", ["model_id", "intermediate_size"])
def test_model_support_loader_rejects_duplicate_json_keys(dense_profile, tmp_path, duplicate):
    raw = json.dumps(dense_profile)
    if duplicate == "model_id":
        raw = '{"model_id": "WRONG/MODEL", ' + raw[1:]
    else:
        raw = raw.replace('"intermediate_size": 3584',
                          '"intermediate_size": 512, "intermediate_size": 3584', 1)
    path = tmp_path / "duplicate_dense_profile.json"
    path.write_text(raw)
    with pytest.raises(ModelContractError, match="duplicate JSON key"):
        ModelProfile.load(path)


@pytest.mark.parametrize("method", ["required", "support", "policies", "runtime_schedule", "footprint",
                                    "layer_pattern"])
@pytest.mark.parametrize("kind", ["identity", "moe", "shape"])
def test_model_support_revalidates_mutable_raw_profile(dense_profile, method, kind):
    profile = ModelProfile(dense_profile)
    if kind == "identity":
        profile.raw["model_id"] = "WRONG/MODEL"
    elif kind == "moe":
        profile.raw["moe"] = {}
    else:
        profile.raw["dense_ffn"]["intermediate_size"] = 512
    with pytest.raises(ModelContractError):
        if method == "layer_pattern":
            _ = profile.layer_pattern
        else:
            getattr(profile, method)()


@pytest.mark.parametrize("kind", ["duplicate_model", "duplicate_file_key", "nonfinite", "not_mapping"])
def test_source_manifest_rejects_ambiguous_json(copied_source_root, kind):
    path = copied_source_root / SOURCE_RELATIVE / "manifest.json"
    raw = path.read_text()
    if kind == "duplicate_model":
        raw = '{"model_id": "WRONG/MODEL", ' + raw.lstrip()[1:]
    elif kind == "duplicate_file_key":
        raw = raw.replace('"file": "config.json"', '"file": "other.json", "file": "config.json"', 1)
    elif kind == "nonfinite":
        raw = '{"unused": NaN, ' + raw.lstrip()[1:]
    else:
        raw = '[]'
    path.write_text(raw)
    with pytest.raises(ModelContractError):
        dense_contract.source_bundle(copied_source_root)
