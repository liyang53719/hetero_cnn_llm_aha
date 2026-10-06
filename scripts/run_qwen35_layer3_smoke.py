#!/usr/bin/env python3
"""Real weights + unmodified pinned official class, explicitly synthetic M128.

Requires optional CPU torch and the exact Transformers commit in the profile.
Never marks U00.2/U01, full-model input provenance, RTL or utilization complete.
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
from heteronpu.pinned_block_payload import load_payload
from heteronpu.qwen35_numpy_reference import compare, decode_bf16, forward, synthetic_input
from heteronpu.weight_header_contract import sha256


def run(root, payload, output):
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be fresh or empty")
    manifest, raw_weights = load_payload(root, payload)
    import torch
    import transformers
    from transformers.cache_utils import DynamicCache
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5TextConfig

    profile = load_json(root / "config/model_profiles/qwen3_5_0p8b.json")
    raw_config_path = root / "config/upstream/qwen3_5_0p8b/config.json"
    require(sha256(raw_config_path.read_bytes()) == profile["config_sha256"], "raw official model config drift")
    official_file = Path(inspect.getfile(official))
    require(sha256(official_file.read_bytes()) == profile["transformers_source"]["sha256"], "installed official forward source drift")
    config_file = Path(inspect.getfile(Qwen3_5TextConfig))
    expected_config = root / "config/upstream/qwen3_5_0p8b/configuration_qwen3_5.py"
    require(config_file.read_bytes() == expected_config.read_bytes(), "installed official configuration source drift")
    direct_url = json.loads(importlib.metadata.distribution("transformers").read_text("direct_url.json") or "{}")
    require(direct_url.get("url") == "https://github.com/huggingface/transformers/archive/" + profile["transformers_source"]["commit"] + ".zip",
            "Transformers package not installed from pinned commit")
    require(direct_url.get("archive_info", {}).get("hashes", {}).get("sha256") ==
            "15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d", "Transformers source archive digest drift")
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    config = Qwen3_5TextConfig.from_dict(load_json(raw_config_path)["text_config"])
    config._attn_implementation = "eager"
    weights = {r["local_name"]: decode_bf16(raw_weights[r["local_name"]], r["shape"]).copy() for r in manifest["tensors"]}
    artifacts = {f"synthetic_input_{case}_fp32": synthetic_input(offset) for case, offset in (("cold", 0), ("warm", 128))}
    checks, state_reports, diagnostic, continuity = [], [], [], []
    fp32_outputs = []
    for dtype in (torch.float32, torch.bfloat16):
        label = str(dtype).removeprefix("torch.")
        layer = official.Qwen3_5DecoderLayer(config, layer_idx=3).to(dtype=dtype).eval()
        result = layer.load_state_dict({k: torch.from_numpy(v).to(dtype) for k, v in weights.items()}, strict=True)
        require(not result.missing_keys and not result.unexpected_keys, "incomplete layer weights")
        rotary = official.Qwen3_5TextRotaryEmbedding(config)
        cache = DynamicCache(config=config)
        independent_past = None
        previous_kv = None
        for case, offset in (("cold", 0), ("warm", 128)):
            x_np = artifacts[f"synthetic_input_{case}_fp32"]
            x = torch.from_numpy(x_np).to(dtype)
            positions = torch.arange(offset, offset + 128).reshape(1, 128).expand(3, 1, 128)
            # Explicit additive causal mask supplied to the official layer.
            allowed = torch.arange(offset + 128)[None, :] <= torch.arange(offset, offset + 128)[:, None]
            mask = torch.where(allowed, 0.0, torch.finfo(dtype).min).to(dtype)[None, None]
            with torch.inference_mode():
                output_tensor = layer(x, position_embeddings=rotary(x, positions), attention_mask=mask,
                                      position_ids=positions, past_key_values=cache)
            y = output_tensor.float().numpy().copy()
            k = cache.layers[3].keys.float().numpy().copy()
            v = cache.layers[3].values.float().numpy().copy()
            if previous_kv is not None:
                prefix_match = np.array_equal(k[:, :, :128], previous_kv[0]) and np.array_equal(v[:, :, :128], previous_kv[1])
                new_values_differ = not np.array_equal(v[:, :, 128:], previous_kv[1])
                require(prefix_match and new_values_differ, "KV prefix changed or distinct warm input reused stale V")
                continuity.append({"dtype": label, "cold_prefix_bit_identical": prefix_match, "new_values_differ_from_cold": new_values_differ})
            previous_kv = (k.copy(), v.copy())
            for name, value in (("output", y), ("key", k), ("value", v)):
                require(np.isfinite(value).all(), "nonfinite official " + name)
                artifacts[f"{label}_{case}_{name}"] = value
                state_reports.append({"dtype": label, "case": case, "producer": name,
                    "shape": list(value.shape), "elements": value.size,
                    "fp32_encoding_sha256": sha256(value.astype("<f4").tobytes()),
                    "storage_dtype": label, "max_abs": float(np.abs(value).max())})
            if dtype == torch.float32:
                oracle_y, independent_past = forward(x_np, weights, independent_past, position_start=offset)
                for name, a, b in (("output", y, oracle_y), ("key", k, independent_past[0]), ("value", v, independent_past[1])):
                    checks.append({"case": case, "producer": name, **compare(a, b)})
                    artifacts[f"numpy_fp64_{case}_{name}"] = b
                fp32_outputs.append(y)
            else:
                delta = y.astype(np.float64) - fp32_outputs[len(diagnostic)].astype(np.float64)
                diagnostic.append({"case": case, "max_abs_vs_fp32": float(np.abs(delta).max()),
                    "rmse_vs_fp32": float(np.sqrt(np.mean(delta * delta))),
                    "acceptance_threshold": None, "scope": "diagnostic_only_not_BF16_dual_reference_acceptance"})
    require(all(c["mismatches"] == 0 for c in checks), "synthetic FP32 independent numerical mismatch")
    output.mkdir(parents=True, exist_ok=True)
    arrays = output / "all_outputs_and_states.npz"
    np.savez_compressed(arrays, **artifacts)
    packages = {name: importlib.metadata.version(name) for name in ("torch", "transformers", "numpy", "huggingface-hub", "tokenizers", "safetensors")}
    report = {"schema_version": 1, "status": "PASS_SYNTHETIC_LAYER_SMOKE_ONLY", "acquired_at": datetime.now(timezone.utc).isoformat(),
        "model_id": manifest["model_id"], "revision": manifest["revision"], "layer_id": 3,
        "framework_revision": profile["transformers_source"]["commit"], "official_source_sha256": sha256(official_file.read_bytes()),
        "payload_manifest_sha256": sha256((payload / "manifest.json").read_bytes()),
        "payload_bytes": manifest["payload_bytes"], "payload_tensor_sha256": {r["name"]: r["sha256"] for r in manifest["tensors"]},
        "input_origin": "deterministic_synthetic_hidden_state_not_official_upstream_activation",
        "input_formula": "reshape(((((arange(128*1024)+position_start*1024)*73+19)%1021)-510)/512, [1,128,1024])",
        "input_fp32_sha256": {case: sha256(artifacts[f"synthetic_input_{case}_fp32"].astype("<f4").tobytes()) for case in ("cold", "warm")}, "batch": 1, "query_tokens": 128,
        "cases": [{"name": "cold", "past_kv_tokens": 0, "position_start": 0}, {"name": "warm", "past_kv_tokens": 128, "position_start": 128}],
        "position_axes": "3 identical synthetic text axes", "mask": "explicit additive causal, masked=finfo(dtype).min",
        "initial_state": "empty official DynamicCache; warm uses this same run's cold K/V",
        "cold_warm_naming_scope": "empty/populated logical KV state only; no measured physical weight-cache or memory-traffic condition",
        "attention_backend": "eager", "dropout": 0, "training": False, "device": "cpu",
        "fp32_comparison": "official FP32 producers vs independent NumPy FP64 mathematical audit; every element",
        "comparison_formula": "abs(actual-reference) <= 1e-4 + 1e-4*abs(reference)",
        "comparisons": checks, "official_state_reports": state_reports, "bf16_diagnostic": diagnostic, "kv_continuity": continuity,
        "arrays": {"file": arrays.name, "bytes": arrays.stat().st_size, "sha256": sha256(arrays.read_bytes()), "scope": "materialized local outputs; reproducible with this script, not weight repository storage"},
        "environment": {"python": platform.python_version(), "packages": packages, "torch_threads": 2,
            "transformers_direct_url": direct_url, "torch_build_config": torch.__config__.show()},
        "runner_source_sha256": {name: sha256(path.read_bytes()) for name, path in (
            ("scripts/run_qwen35_layer3_smoke.py", Path(__file__)),
            ("src/heteronpu/qwen35_numpy_reference.py", Path(inspect.getfile(forward))),
            ("src/heteronpu/pinned_block_payload.py", Path(inspect.getfile(load_payload))))},
        "official_decoder_layer_executed": True, "official_full_model_executed": False,
        "upstream_activation_provenance_verified": False, "producer_precision_contract_frozen": False,
        "full_checkpoint_sha256_verified": False, "GDN_executed": False, "MoE_executed": False,
        "rtl_executed": False, "mac_utilization_measured": False, "U00_2_complete": False, "U01_complete": False}
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.root, args.payload, args.output)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("SYNTHETIC_SMOKE_REJECTED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result, indent=2))
