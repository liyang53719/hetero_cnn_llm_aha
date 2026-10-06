#!/usr/bin/env python3
"""Execute the real checkpoint embedding→official layers0..3 prefix at M128.

The fixed token IDs are an artificial test fixture, but hidden states are all
real official upstream results. A boundary hook stops the original TextModel
forward after layer3: later meta layers/final norm/lm_head are never executed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import importlib.metadata
import inspect
import json
from pathlib import Path
import platform
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteronpu.model_geometry import load_json, require
from heteronpu import pinned_block_payload, pinned_gdn_payload, pinned_prefix_payload
from heteronpu.qwen35_numpy_reference import compare, decode_bf16
from heteronpu.qwen35_prefix_reference import forward as independent_forward, verify_activation_links
from heteronpu.weight_header_contract import sha256


def decode(manifest, raw):
    return {r["local_name"]: (np.frombuffer(raw[r["local_name"]], dtype="<f4").reshape(r["shape"]).copy()
            if r["dtype"] == "F32" else decode_bf16(raw[r["local_name"]], r["shape"]).copy()) for r in manifest["tensors"]}


def run(root, payload0, payload3, payload_extra, output):
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be fresh or empty")
    manifests, decoded = {}, {}
    for name, module, path in (("layer0", pinned_gdn_payload, payload0), ("layer3", pinned_block_payload, payload3),
                                ("additional_prefix", pinned_prefix_payload, payload_extra)):
        manifest, raw = module.load_payload(root, path)
        manifests[name] = manifest
        decoded[name] = decode(manifest, raw)
    fixture = pinned_prefix_payload.token_fixture(root)
    tokens = np.asarray(fixture["token_ids"], dtype=np.int64).reshape(1, 256)
    embedding_rows = decoded["additional_prefix"]["embed_tokens.rows_0_255"]
    weights = {0: decoded["layer0"], 3: decoded["layer3"]}
    for layer in (1, 2):
        prefix = f"layers.{layer}."
        weights[layer] = {k.removeprefix(prefix): v for k, v in decoded["additional_prefix"].items() if k.startswith(prefix)}
    require(all(np.isfinite(v).all() for w in weights.values() for v in w.values()), "nonfinite real weight")
    import torch
    import transformers.cache_utils as cache_source
    import transformers.masking_utils as mask_source
    from transformers.cache_utils import DynamicCache
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5TextConfig

    profile = load_json(root / "config/model_profiles/qwen3_5_0p8b.json")
    config_path = root / "config/upstream/qwen3_5_0p8b/config.json"
    require(sha256(config_path.read_bytes()) == profile["config_sha256"], "official config drift")
    source_files = {"modeling": Path(inspect.getfile(official)), "cache": Path(inspect.getfile(cache_source)),
                    "masking": Path(inspect.getfile(mask_source)), "configuration": Path(inspect.getfile(Qwen3_5TextConfig))}
    expected_hashes = {"modeling": profile["transformers_source"]["sha256"],
        "cache": "abdcb0ae88aa5b924ef7d76879db680e9af8f3ec1dafbba7ce446ecb521a944b",
        "masking": "af3d84dfe82a0b57c40625c89fb32b2cd6bf7351432ee5e76a9e8eac4289575b",
        "configuration": sha256((root / "config/upstream/qwen3_5_0p8b/configuration_qwen3_5.py").read_bytes())}
    require(all(sha256(p.read_bytes()) == expected_hashes[k] for k, p in source_files.items()), "installed official source drift")
    direct_url = json.loads(importlib.metadata.distribution("transformers").read_text("direct_url.json") or "{}")
    require(direct_url.get("url") == "https://github.com/huggingface/transformers/archive/" + profile["transformers_source"]["commit"] + ".zip", "Transformers archive origin drift")
    require(direct_url.get("archive_info", {}).get("hashes", {}).get("sha256") == "15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d", "Transformers archive hash drift")
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    raw_config = load_json(config_path)["text_config"]
    config = Qwen3_5TextConfig.from_dict(raw_config)
    config._attn_implementation = "eager"
    require(config.num_hidden_layers == 24 and config.layer_types[:4] == ["linear_attention"] * 3 + ["full_attention"], "official prefix ordering drift")
    artifacts = {"token_ids": tokens, "decoded_embedding_rows_fp32": embedding_rows}
    comparisons, replay, influence, state_reports, parameters, links, diagnostics, kv_checks = [], [], [], [], [], [], [], []

    class PrefixComplete(Exception):
        """Stop only after the real official layer3 output is captured."""

    def cpu(t):
        return t.detach().float().cpu().numpy().copy()

    def build_model(mode, dtype):
        # Original config and exact original TextModel.forward. Meta only avoids
        # allocating weights for later layers that are outside this prefix.
        with torch.device("meta"):
            model = official.Qwen3_5TextModel(config)
        model.embed_tokens = torch.nn.Embedding.from_pretrained(torch.from_numpy(embedding_rows).to(dtype), freeze=True)
        model.rotary_emb = official.Qwen3_5TextRotaryEmbedding(config)
        for layer in range(4):
            values = {k: torch.from_numpy(v).to(torch.float32 if mode == "audit_fp32" or (layer < 3 and k in pinned_gdn_payload.F32_NAMES) else torch.bfloat16)
                      for k, v in weights[layer].items()}
            loaded = model.layers[layer].load_state_dict(values, strict=True, assign=True)
            require(not loaded.missing_keys and not loaded.unexpected_keys, "incomplete prefix parameters")
            require(all(not v.is_meta and v.device.type == "cpu" for v in model.layers[layer].parameters()), "prefix parameter is not real CPU data")
            actual = {k: str(v.dtype).removeprefix("torch.") for k, v in model.layers[layer].named_parameters()}
            require(actual == {k: str(v.dtype).removeprefix("torch.") for k, v in values.items()}, "source mixed dtype changed")
            parameters.append({"mode": mode, "layer": layer, "parameter_dtypes": actual})
        require(all(p.is_meta for layer in model.layers[4:] for p in layer.parameters()) and all(p.is_meta for p in model.norm.parameters()), "unused layers must remain unmaterialized")
        require(model.config._attn_implementation == "eager", "attention backend drift")
        model.eval()
        return model

    def execute(model, ids, cache, offset):
        require(ids.ndim == 2 and ids.shape[0] == 1 and np.all((ids >= 0) & (ids < 256)), "embedding row out of scope")
        records, embedded, handles, masks = [], [], [], {}
        def reject_unused(module, args):
            raise ValueError("out-of-prefix meta layer/final norm was reached")
        handles.append(model.layers[4].register_forward_pre_hook(reject_unused))
        handles.append(model.norm.register_forward_pre_hook(reject_unused))
        def capture_embedding(module, args, result):
            embedded.append(cpu(result))
        handles.append(model.embed_tokens.register_forward_hook(capture_embedding))
        for index in range(4):
            def capture(module, args, kwargs, result, i=index):
                require(len(records) == i, "official execution order drift")
                record = {"layer": i, "input": cpu(args[0]), "output": cpu(result)}
                slot = cache.layers[i]
                if i < 3:
                    state = {"conv_state": slot.conv_states[0], "recurrent_state": slot.recurrent_states[0]}
                    require(state["recurrent_state"].dtype == torch.float32, "official SSM must stay FP32")
                    require(state["conv_state"].dtype == args[0].dtype, "official conv dtype drift")
                    require(kwargs["attention_mask"] is None, "all-valid GDN mask should be absent")
                else:
                    state = {"key": slot.keys, "value": slot.values}
                    mask = kwargs["attention_mask"]
                    past_length = state["key"].shape[2] - ids.shape[1]
                    allowed = np.arange(past_length + ids.shape[1])[None] <= (np.arange(ids.shape[1])[:, None] + past_length)
                    expected = np.where(allowed, 0.0, torch.finfo(args[0].dtype).min).astype(np.float32)[None, None]
                    require(np.array_equal(cpu(mask), expected), "official causal mask disagrees with expected history")
                    masks["attention_mask"] = cpu(mask)
                    masks["rope_cos"], masks["rope_sin"] = map(cpu, kwargs["position_embeddings"])
                    masks["position_ids"] = kwargs["position_ids"].cpu().numpy().copy()
                    require(np.array_equal(masks["position_ids"], np.arange(offset, offset + ids.shape[1]).reshape(1, -1)), "official absolute position drift")
                record.update({name: cpu(value) for name, value in state.items()})
                record["storage_dtypes"] = {name: str(value.dtype).removeprefix("torch.") for name, value in state.items()}
                record["storage_dtypes"].update(input=str(args[0].dtype).removeprefix("torch."), output=str(result.dtype).removeprefix("torch."))
                records.append(record)
                if i == 3:
                    raise PrefixComplete()
            handles.append(model.layers[index].register_forward_hook(capture, with_kwargs=True))
        try:
            with torch.inference_mode():
                # Explicit positions preserve absolute offsets in reset-state tests.
                model(input_ids=torch.from_numpy(ids.copy()), attention_mask=torch.ones((1, offset + ids.shape[1]), dtype=torch.long),
                      position_ids=torch.arange(offset, offset + ids.shape[1]).reshape(1, -1),
                      past_key_values=cache, use_cache=True)
        except PrefixComplete:
            pass
        else:
            raise ValueError("official prefix boundary was not reached")
        finally:
            for handle in handles:
                handle.remove()
        require(len(embedded) == 1 and len(records) == 4, "incomplete official prefix capture")
        require(np.array_equal(embedded[0], embedding_rows[ids]), "official lookup differs from acquired original rows")
        verify_activation_links(embedded[0], records)
        return embedded[0], records, masks

    def save(mode, case, embedding, records, masks=None):
        artifacts[f"{mode}_{case}_embedding"] = embedding
        links.append({"mode": mode, "case": case, "embedding_to_layer0_and_all_layer_links_bit_exact": verify_activation_links(embedding, records)})
        for record in records:
            layer = record["layer"]
            for name in ("input", "output", "conv_state", "recurrent_state", "key", "value"):
                if name not in record:
                    continue
                value = record[name]
                require(np.isfinite(value).all(), "nonfinite " + name)
                artifacts[f"{mode}_{case}_layer{layer}_{name}"] = value
                state_reports.append({"mode": mode, "case": case, "layer": layer, "producer": name, "shape": list(value.shape),
                    "elements": value.size, "storage_dtype": record.get("storage_dtypes", {}).get(name, "float64_mathematical_reference"),
                    "array_dtype": str(value.dtype), "array_sha256": sha256(value.tobytes()), "max_abs": float(np.abs(value).max())})
        for name, value in (masks or {}).items():
            artifacts[f"{mode}_{case}_{name}"] = value

    for mode, dtype in (("audit_fp32", torch.float32), ("source_mixed_bf16", torch.bfloat16)):
        model = build_model(mode, dtype)
        cache, independent_past = DynamicCache(config=config), None
        results = {}
        cold_cache = None
        for case, offset in (("cold_m128", 0), ("carried_m128", 128)):
            embedding, records, masks = execute(model, tokens[:, offset:offset + 128], cache, offset)
            save(mode, case, embedding, records, masks)
            results[case] = records
            if offset == 0:
                cold_cache = deepcopy(cache)
            else:
                first, second = results["cold_m128"][3], records[3]
                prefix_equal = all(np.array_equal(second[n][:, :, :128], first[n]) for n in ("key", "value"))
                new_different = not np.array_equal(second["value"][:, :, 128:], first["value"])
                require(prefix_equal and new_different, "KV prefix lost or second chunk stale")
                kv_checks.append({"mode": mode, "past128_prefix_bit_exact": prefix_equal, "new_values_differ": new_different})
            if mode == "audit_fp32":
                oracle_embedding, oracle_records, independent_past = independent_forward(tokens[:, offset:offset + 128], embedding_rows, weights,
                                                                                         independent_past, position_start=offset, config=raw_config)
                save("numpy_fp64", case, oracle_embedding, oracle_records)
                for actual, expected in zip(records, oracle_records, strict=True):
                    for name in ("input", "output", "conv_state", "recurrent_state", "key", "value"):
                        if name in actual:
                            comparisons.append({"case": case, "layer": actual["layer"], "producer": name, **compare(actual[name], expected[name])})
            else:
                for record in records:
                    for name in ("output", "conv_state", "recurrent_state", "key", "value"):
                        if name in record:
                            delta = record[name].astype(np.float64) - artifacts[f"audit_fp32_{case}_layer{record['layer']}_{name}"].astype(np.float64)
                            diagnostics.append({"case": case, "layer": record["layer"], "producer": name,
                                "max_abs_vs_fp32": float(np.abs(delta).max()), "rmse_vs_fp32": float(np.sqrt(np.mean(delta * delta))), "acceptance_threshold": None})
        if mode == "audit_fp32":
            emb, whole, masks = execute(model, tokens, DynamicCache(config=config), 0)
            save(mode, "whole256_replay", emb, whole, masks)
            for record in whole:
                layer = record["layer"]
                for name in ("input", "output", "conv_state", "recurrent_state", "key", "value"):
                    if name in record:
                        first, second = results["cold_m128"][layer], results["carried_m128"][layer]
                        split = np.concatenate([first[name], second[name]], axis=1) if name in ("input", "output") else second[name]
                        replay.append({"layer": layer, "producer": name, **compare(split, record[name])})
            # Reset only one layer's history at a time, retaining all other
            # states and original absolute positions: proves each own state matters.
            for reset_layer in range(4):
                reset_cache = deepcopy(cold_cache)
                reset_cache.layers[reset_layer] = DynamicCache(config=config).layers[reset_layer]
                emb, reset, masks = execute(model, tokens[:, 128:], reset_cache, 128)
                save(mode, f"reset_layer{reset_layer}_carried", emb, reset, masks)
                target_delta = float(np.abs(reset[reset_layer]["output"] - results["carried_m128"][reset_layer]["output"]).max())
                final_delta = float(np.abs(reset[3]["output"] - results["carried_m128"][3]["output"]).max())
                require(target_delta > 1e-4 and final_delta > 1e-4, "layer state influence test is vacuous")
                influence.append({"reset_layer": reset_layer, "other_layer_initial_states_preserved": True,
                    "same_absolute_positions": True, "max_abs_target_output_delta": target_delta, "max_abs_layer3_output_delta": final_delta})
        del model
    require(all(c["mismatches"] == 0 for c in comparisons + replay), "real-prefix independent/partition comparison failed")
    output.mkdir(parents=True, exist_ok=True)
    arrays = output / "prefix_activations_and_states.npz"
    np.savez_compressed(arrays, **artifacts)
    report = {"schema_version": 1, "status": "PASS_REAL_EMBEDDING_OFFICIAL_PREFIX_CHAIN_U00_2_OPEN", "created_at": datetime.now(timezone.utc).isoformat(),
        "model_id": profile["model_id"], "revision": manifests["layer0"]["revision"], "framework_revision": profile["transformers_source"]["commit"],
        "official_source_sha256": expected_hashes, "payload_bytes_total": sum(m["payload_bytes"] for m in manifests.values()),
        "additional_payload_bytes": manifests["additional_prefix"]["payload_bytes"],
        "payload_manifests": {name: {"sha256": sha256(path.read_bytes()), "payload_bytes": manifests[name]["payload_bytes"]} for name, path in
            (("layer0", payload0 / "manifest.json"), ("layer3", payload3 / "manifest.json"), ("additional_prefix", payload_extra / "manifest.json"))},
        "fixture": {**fixture, "sha256": pinned_prefix_payload.FIXTURE_SHA256},
        "input_origin": "fixed_artificial_token_IDs_with_real_pinned_checkpoint_embedding_and_official_prefix_activations",
        "tokenizer_used": False, "natural_language_representativeness_claimed": False,
        "embedding_scope": "Only original rows0..255 acquired; original token IDs directly index those rows in standard torch.nn.Embedding. No row remapping or synthetic hidden states.",
        "forward_scope": "Unmodified original 24-layer-config TextModel.forward stops at layer3 output by non-mutating capture hook. Later meta layers, final norm, lm_head, vision not executed.",
        "batch": 1, "query_tokens": 128, "cases": [{"name": "cold_m128", "past_tokens": 0}, {"name": "carried_m128", "past_tokens": 128}],
        "position_scope": "Official TextModel expands explicit absolute text positions to 3 identical RoPE axes; official masks computed before loop.",
        "attention_backend": "eager", "device": "cpu", "state_scope": "Same-run official per-layer caches; NumPy uses its own full prefix and independent carried states. Logical cache only.",
        "comparison_formula": "abs(actual-reference) <= 1e-4 + 1e-4*abs(reference)",
        "comparison_scope": "FP32 official chain versus independent NumPy FP64 chain at every layer input/output and every conv/SSM/KV element",
        "comparisons": comparisons, "partition_replay_comparisons": replay, "isolated_state_influence": influence,
        "activation_links": links, "kv_continuity": kv_checks, "parameter_dtype_reports": parameters,
        "array_reports": state_reports, "mixed_bf16_diagnostic": diagnostics,
        "mixed_bf16_scope": "Original mixed F32/BF16 parameters, BF16 activations/conv/KV, FP32 SSM; FP32 differences diagnostic only, no producer-rounding comparator frozen.",
        "arrays": {"file": arrays.name, "bytes": arrays.stat().st_size, "sha256": sha256(arrays.read_bytes())},
        "environment": {"python": platform.python_version(), "packages": {n: importlib.metadata.version(n) for n in ("torch", "transformers", "numpy", "huggingface-hub", "tokenizers", "safetensors")},
                        "torch_threads": 2, "torch_build_config": torch.__config__.show(), "transformers_direct_url": direct_url},
        "runner_source_sha256": {name: sha256((root / name).read_bytes()) for name in ("scripts/run_qwen35_prefix_chain.py", "src/heteronpu/pinned_prefix_payload.py",
            "src/heteronpu/qwen35_prefix_reference.py", "src/heteronpu/qwen35_gdn_numpy_reference.py", "src/heteronpu/qwen35_numpy_reference.py",
            "src/heteronpu/pinned_gdn_payload.py", "src/heteronpu/pinned_block_payload.py")},
        "official_TextModel_prefix_executed": True, "official_full_model_executed": False,
        "upstream_activation_provenance_verified_for_layers_0_to_3": True, "producer_precision_contract_frozen": False,
        "full_checkpoint_sha256_verified": False, "physical_cache_conditions_frozen": False, "MoE_executed": False,
        "rtl_executed": False, "mac_utilization_measured": False, "U00_2_complete": False, "U01_complete": False}
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--payload-layer0", type=Path, required=True)
    parser.add_argument("--payload-layer3", type=Path, required=True)
    parser.add_argument("--payload-extra", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.root, args.payload_layer0, args.payload_layer3, args.payload_extra, args.output)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("PREFIX_CHAIN_REJECTED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(report, indent=2))
