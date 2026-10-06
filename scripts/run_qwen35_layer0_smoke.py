#!/usr/bin/env python3
"""Execute pinned mixed-dtype layer0 GDN on synthetic inputs and audit state.

This is CPU numerical evidence, not official upstream activations, RTL, a frozen
BF16 producer comparator, physical cache conditions, or utilization acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import inspect
import json
import platform
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteronpu.model_geometry import load_json, require
from heteronpu.pinned_gdn_payload import load_payload, F32_NAMES
from heteronpu.pinned_block_payload import fetch_range
from heteronpu.qwen35_numpy_reference import compare, decode_bf16, synthetic_input
from heteronpu.qwen35_gdn_numpy_reference import forward
from heteronpu.weight_header_contract import sha256

CASES = (("cold_m128", 0, 128), ("carried_m128", 128, 128), ("carried_decode1", 256, 1))


def decode_weights(manifest, raw_weights):
    return {r["local_name"]: (np.frombuffer(raw_weights[r["local_name"]], dtype="<f4").reshape(r["shape"]).copy()
            if r["dtype"] == "F32" else decode_bf16(raw_weights[r["local_name"]], r["shape"]).copy())
            for r in manifest["tensors"]}


def run(root, payload, output):
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be fresh or empty")
    manifest, raw_weights = load_payload(root, payload)
    import torch
    import transformers.cache_utils as cache_source
    from transformers.cache_utils import DynamicCache
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5TextConfig

    profile = load_json(root / "config/model_profiles/qwen3_5_0p8b.json")
    raw_config = root / "config/upstream/qwen3_5_0p8b/config.json"
    require(sha256(raw_config.read_bytes()) == profile["config_sha256"], "raw official config drift")
    official_file = Path(inspect.getfile(official))
    require(sha256(official_file.read_bytes()) == profile["transformers_source"]["sha256"], "installed official forward drift")
    config_file = Path(inspect.getfile(Qwen3_5TextConfig))
    require(config_file.read_bytes() == (root / "config/upstream/qwen3_5_0p8b/configuration_qwen3_5.py").read_bytes(), "official configuration drift")
    direct_url = json.loads(importlib.metadata.distribution("transformers").read_text("direct_url.json") or "{}")
    require(direct_url.get("url") == "https://github.com/huggingface/transformers/archive/" + profile["transformers_source"]["commit"] + ".zip",
            "Transformers is not installed from pinned archive")
    require(direct_url.get("archive_info", {}).get("hashes", {}).get("sha256") ==
            "15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d", "Transformers archive hash drift")
    cache_file = Path(inspect.getfile(cache_source))
    require(sha256(cache_file.read_bytes()) == "abdcb0ae88aa5b924ef7d76879db680e9af8f3ec1dafbba7ce446ecb521a944b", "installed official cache source drift")
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    raw_text_config = load_json(raw_config)["text_config"]
    config = Qwen3_5TextConfig.from_dict(raw_text_config)
    weights = decode_weights(manifest, raw_weights)
    require(all(np.isfinite(w).all() for w in weights.values()), "nonfinite checkpoint tensor")
    artifacts = {"synthetic_" + case + "_fp32": synthetic_input(offset)[:, :length].copy() for case, offset, length in CASES}
    checks, state_reports, diagnostic, parameter_reports, replay_checks, influence_checks = [], [], [], [], [], []

    def execute(layer, x, cache):
        # Linear attention does not consume position_embeddings. All tokens are real (no padding).
        with torch.inference_mode():
            y = layer(x, position_embeddings=None, attention_mask=torch.ones(x.shape[:2], dtype=torch.bool), past_key_values=cache)
        conv, recurrent = cache.layers[0].conv_states[0], cache.layers[0].recurrent_states[0]
        require(recurrent.dtype == torch.float32, "official recurrent state stopped being FP32")
        require(conv.dtype == x.dtype, "official conv state dtype drift")
        return {"output": y, "conv_state": conv, "recurrent_state": recurrent}

    for mode, dtype in (("audit_fp32", torch.float32), ("source_mixed_bf16", torch.bfloat16)):
        layer = official.Qwen3_5DecoderLayer(config, layer_idx=0).eval()
        load_values = {k: torch.from_numpy(v).to(torch.float32 if mode == "audit_fp32" or k in F32_NAMES else torch.bfloat16)
                       for k, v in weights.items()}
        # assign=True retains actual source dtype for each tensor; blanket .to(BF16) is forbidden here.
        result = layer.load_state_dict(load_values, strict=True, assign=True)
        require(not result.missing_keys and not result.unexpected_keys, "incomplete GDN layer weights")
        actual_dtypes = {k: str(v.dtype).removeprefix("torch.") for k, v in layer.named_parameters()}
        require(actual_dtypes == {k: str(v.dtype).removeprefix("torch.") for k, v in load_values.items()}, "parameter dtype was altered")
        parameter_reports.append({"mode": mode, "parameter_dtypes": actual_dtypes})
        cache = DynamicCache(config=config)
        independent_past = None
        mode_results = {}
        for case, offset, length in CASES:
            x_np = artifacts["synthetic_" + case + "_fp32"]
            producers = execute(layer, torch.from_numpy(x_np).to(dtype), cache)
            decoded = {}
            for name, tensor in producers.items():
                value = tensor.float().numpy().copy()
                require(np.isfinite(value).all(), "nonfinite official " + name)
                decoded[name] = value
                artifacts[f"{mode}_{case}_{name}"] = value
                state_reports.append({"mode": mode, "case": case, "producer": name,
                    "shape": list(value.shape), "elements": value.size, "storage_dtype": str(tensor.dtype).removeprefix("torch."),
                    "fp32_encoding_sha256": sha256(value.astype("<f4").tobytes()), "max_abs": float(np.abs(value).max())})
            mode_results[case] = decoded
            if mode == "audit_fp32":
                oracle_y, independent_past = forward(x_np, weights, independent_past, config=raw_text_config)
                for name, reference in zip(("output", "conv_state", "recurrent_state"), (oracle_y, *independent_past), strict=True):
                    checks.append({"case": case, "producer": name, **compare(decoded[name], reference)})
                    artifacts[f"numpy_fp64_{case}_{name}"] = reference
            else:
                for name, value in decoded.items():
                    delta = value.astype(np.float64) - artifacts[f"audit_fp32_{case}_{name}"].astype(np.float64)
                    diagnostic.append({"case": case, "producer": name, "max_abs_vs_fp32": float(np.abs(delta).max()),
                        "rmse_vs_fp32": float(np.sqrt(np.mean(delta * delta))), "acceptance_threshold": None,
                        "scope": "diagnostic_only_not_BF16_dual_reference_acceptance"})
        if mode == "audit_fp32":
            # A separate 256-token replay detects state reset/drop and checks M128 partition continuity.
            full_input = np.concatenate([artifacts["synthetic_cold_m128_fp32"], artifacts["synthetic_carried_m128_fp32"]], axis=1)
            whole = execute(layer, torch.from_numpy(full_input), DynamicCache(config=config))
            for name, tensor in whole.items():
                value = tensor.float().numpy().copy()
                split = np.concatenate([mode_results["cold_m128"][name], mode_results["carried_m128"][name]], axis=1) if name == "output" else mode_results["carried_m128"][name]
                replay_checks.append({"producer": name, **compare(split, value)})
                artifacts["audit_fp32_whole256_" + name] = value
            # Counterfactual state resets must materially change output; these are diagnostics, not reference substitutions.
            reset = execute(layer, torch.from_numpy(artifacts["synthetic_carried_m128_fp32"]), DynamicCache(config=config))
            for name in ("output", "recurrent_state"):
                value = reset[name].float().numpy().copy()
                delta = float(np.abs(value - mode_results["carried_m128"][name]).max())
                influence_checks.append({"producer": name, "max_abs_carried_vs_reset": delta})
                artifacts["audit_fp32_reset_carried_input_" + name] = value
            require(influence_checks[0]["max_abs_carried_vs_reset"] > 1e-4, "state continuity test is vacuous")
    require(all(c["mismatches"] == 0 for c in checks + replay_checks), "synthetic FP32 independent/state-replay mismatch")
    output.mkdir(parents=True, exist_ok=True)
    arrays = output / "all_outputs_and_states.npz"
    np.savez_compressed(arrays, **artifacts)
    report = {"schema_version": 1, "status": "PASS_SYNTHETIC_GDN_LAYER_SMOKE_ONLY",
        "created_at": datetime.now(timezone.utc).isoformat(), "model_id": manifest["model_id"], "revision": manifest["revision"], "layer_id": 0,
        "framework_revision": profile["transformers_source"]["commit"], "official_source_sha256": sha256(official_file.read_bytes()),
        "official_cache_source_sha256": sha256(Path(inspect.getfile(cache_source)).read_bytes()),
        "payload_manifest_sha256": sha256((payload / "manifest.json").read_bytes()), "payload_bytes": manifest["payload_bytes"],
        "payload_tensor_sha256": {r["name"]: r["sha256"] for r in manifest["tensors"]},
        "source_storage_dtypes": {r["local_name"]: r["dtype"] for r in manifest["tensors"]},
        "parameter_dtype_reports": parameter_reports,
        "input_origin": "deterministic_synthetic_hidden_state_not_official_upstream_activation",
        "input_formula": "reshape(((((arange(M*1024)+position_start*1024)*73+19)%1021)-510)/512,[1,M,1024])",
        "input_fp32_sha256": {case: sha256(artifacts["synthetic_" + case + "_fp32"].astype("<f4").tobytes()) for case, _, _ in CASES},
        "batch": 1, "cases": [{"name": c, "past_tokens": p, "query_tokens": m} for c, p, m in CASES],
        "initial_state": "empty official DynamicCache, then same-run conv and FP32 recurrent state",
        "logical_state_scope": "cold/carried logical states only, not physical weight-cache or traffic/performance conditions",
        "mask": "all-valid 2D boolean mask; no padding", "device": "cpu", "training": False,
        "gdn_backend": "official torch chunk rule (M128) and recurrent rule (supplemental cached decode1), no custom kernel registration",
        "comparison_formula": "abs(actual-reference) <= 1e-4 + 1e-4*abs(reference)",
        "comparison_scope": "official FP32 output/conv/SSM vs independently sequential NumPy FP64 mathematical reference, every element",
        "comparisons": checks, "partition_replay_comparisons": replay_checks, "state_influence": influence_checks,
        "official_state_reports": state_reports, "mixed_bf16_diagnostic": diagnostic,
        "arrays": {"file": arrays.name, "bytes": arrays.stat().st_size, "sha256": sha256(arrays.read_bytes())},
        "environment": {"python": platform.python_version(), "packages": {n: importlib.metadata.version(n) for n in ("torch", "transformers", "numpy", "huggingface-hub", "tokenizers", "safetensors")},
            "torch_threads": 2, "torch_build_config": torch.__config__.show(), "transformers_direct_url": direct_url},
        "runner_source_sha256": {name: sha256(path.read_bytes()) for name, path in (
            ("scripts/run_qwen35_layer0_smoke.py", Path(__file__)),
            ("src/heteronpu/qwen35_gdn_numpy_reference.py", Path(inspect.getfile(forward))),
            ("src/heteronpu/pinned_gdn_payload.py", Path(inspect.getfile(load_payload))),
            ("src/heteronpu/qwen35_numpy_reference.py", Path(inspect.getfile(compare))),
            ("src/heteronpu/pinned_block_payload.py", Path(inspect.getfile(fetch_range))))},
        "official_decoder_layer_executed": True, "GDN_executed": True, "official_full_model_executed": False,
        "upstream_activation_provenance_verified": False, "producer_precision_contract_frozen": False,
        "full_checkpoint_sha256_verified": False, "MoE_executed": False, "rtl_executed": False,
        "mac_utilization_measured": False, "U00_2_complete": False, "U01_complete": False}
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.root, args.payload, args.output)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("SYNTHETIC_GDN_SMOKE_REJECTED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(report, indent=2))
