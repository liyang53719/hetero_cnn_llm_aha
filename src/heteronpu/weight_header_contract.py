"""Pinned safetensors metadata only. Never reads or validates tensor payloads.

Offline verification is byte-exact; bounded HTTPS acquisition is a separate CLI.
An index supplies names, a header supplies storage geometry, and neither proves
weights/content, official numerical semantics, DUT execution or utilization.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from .model_geometry import ModelContractError, _nonfinite, _unique_pairs, load_json, require
from .qwen35_dense_contract import tensor_shapes

BUNDLE_ROOT = "config/upstream/weight_headers"
# Filled from independently acquired raw bytes; revisions are never mutable main.
PINS = {
    "qwen2_1p5b": ("Qwen/Qwen2-1.5B-Instruct", "ba1cf1846d7df0a0591d6c00649f57e798519da8"),
    "qwen3_5_0p8b": ("Qwen/Qwen3.5-0.8B", "2fc06364715b967f1860aea9cf38778875588b17"),
    "qwen3_5_35b_a3b": ("Qwen/Qwen3.5-35B-A3B", "62704185bd97ad488cfc404e7caea797396b74dc"),
}
BUNDLE_SHA256 = {'qwen2_1p5b': '46818a6fde79b4bff4615abc38cca7d8cb9386cdd0298bc07c403cb3d2ceab25', 'qwen3_5_0p8b': 'b10d1c78df5ef0e5535cb4eb04b45f73ef935e0867a21f3a48dd98e5a89afca5', 'qwen3_5_35b_a3b': 'ca44aa87cfedd5d302b62c02d77ce64624009998edb78fe0bd025c42beaa4c8e'}
DTYPE_BYTES = {"BOOL": 1, "U8": 1, "I8": 1, "I16": 2, "U16": 2, "I32": 4,
               "U32": 4, "I64": 8, "U64": 8, "F16": 2, "BF16": 2, "F32": 4, "F64": 8,
               "F8_E4M3": 1, "F8_E5M2": 1}
MAX_HEADER_BYTES = 16 * 1024 * 1024


def integer(x: Any, label: str, minimum: int = 0) -> int:
    require(type(x) is int and minimum <= x <= 2**63 - 1, "invalid integer: " + label)
    return x


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def decode_header(raw: bytes, total_file_bytes: int) -> dict:
    """Validate exact 8-byte prefix + JSON, offsets and complete file geometry.

    total_file_bytes is observed HTTP range/API metadata, NOT a local payload.
    """
    integer(total_file_bytes, "total file bytes", 9)
    require(isinstance(raw, bytes) and len(raw) >= 10, "truncated safetensors header")
    size = int.from_bytes(raw[:8], "little")
    require(1 < size <= MAX_HEADER_BYTES and size + 8 == len(raw), "header prefix/length mismatch")
    require(raw[8:9] == b"{", "safetensors header must begin with '{'")
    require(total_file_bytes >= len(raw), "header larger than file")
    try:
        header = json.loads(raw[8:].decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=_nonfinite)
    except (ValueError, UnicodeError) as exc:
        raise ModelContractError("invalid safetensors JSON: " + str(exc)) from exc
    require(isinstance(header, dict), "header must be a mapping")
    metadata = header.pop("__metadata__", {})
    require(isinstance(metadata, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()),
            "metadata must map strings to strings")
    require(bool(header), "empty tensor header")
    spans = []
    for name, entry in header.items():
        require(isinstance(name, str) and bool(name) and isinstance(entry, dict), "invalid tensor entry")
        require(set(entry) == {"dtype", "shape", "data_offsets"}, "invalid tensor fields: " + name)
        dtype = entry["dtype"]
        require(isinstance(dtype, str) and dtype in DTYPE_BYTES, "unsupported dtype: " + name)
        shape = entry["shape"]
        require(isinstance(shape, list), "shape must be a list: " + name)
        for d in shape:
            integer(d, "shape dimension")
        offsets = entry["data_offsets"]
        require(isinstance(offsets, list) and len(offsets) == 2, "invalid data_offsets: " + name)
        lo, hi = (integer(x, "data offset") for x in offsets)
        require(hi >= lo and hi - lo == math.prod(shape) * DTYPE_BYTES[dtype], "shape/dtype byte span mismatch: " + name)
        require(hi <= total_file_bytes - len(raw), "tensor outside file: " + name)
        spans.append((lo, hi, name))
    cursor = 0
    for lo, hi, name in sorted(spans):
        require(lo == cursor, "gap/overlap in tensor data offsets: " + name)
        cursor = hi
    require(cursor == total_file_bytes - len(raw), "unindexed trailing payload bytes")
    return header


def read_record(root: Path, record: Any) -> bytes:
    require(isinstance(record, dict) and set(record) >= {"path", "sha256", "bytes"}, "invalid file record")
    name = record["path"]
    require(isinstance(name, str) and bool(name) and "\\" not in name, "invalid file path")
    p = Path(name)
    require(not p.is_absolute() and ".." not in p.parts, "unsafe file path")
    target = (root / p).resolve()
    require(target.is_relative_to(root.resolve()) and target.is_file(), "missing/outside repository artifact")
    raw = target.read_bytes()
    require(integer(record["bytes"], "artifact bytes") == len(raw), "artifact byte length mismatch: " + name)
    require(record["sha256"] == sha256(raw), "artifact SHA256 mismatch: " + name)
    return raw


def expected_text_shapes(root: Path, key: str) -> dict[str, list[int]]:
    if key == "qwen3_5_0p8b":
        return tensor_shapes(load_json(root / "config/model_profiles/qwen3_5_0p8b.json"))
    if key == "qwen2_1p5b":
        p = load_json(root / "config/qwen2_1p5b_target_shape.json")
        require((p["model"], p["revision"]) == PINS[key], "Qwen2 profile identity drift")
        h, f, layers, vocab, q, kv = 1536, 8960, 28, 151936, 1536, 256
        prefix = "model."
    else:
        p = load_json(root / "config/model_profiles/qwen3_5_35b_a3b.json")
        from .model_geometry import validate_profile
        validate_profile(p)
        h, f, layers, vocab, q, kv = 2048, 512, 40, 248320, 4096, 512
        prefix = "model.language_model."
    result = {prefix + "embed_tokens.weight": [vocab, h], prefix + "norm.weight": [h]}
    for layer in range(layers):
        shapes = {"input_layernorm.weight": [h], "post_attention_layernorm.weight": [h]}
        if key == "qwen2_1p5b":
            shapes.update({"mlp.gate_proj.weight": [f, h], "mlp.up_proj.weight": [f, h], "mlp.down_proj.weight": [h, f]})
        else:
            shapes.update({"mlp.experts.gate_up_proj": [256, 2 * f, h], "mlp.experts.down_proj": [256, h, f],
                           "mlp.gate.weight": [256, h], "mlp.shared_expert_gate.weight": [1, h],
                           "mlp.shared_expert.gate_proj.weight": [f, h], "mlp.shared_expert.up_proj.weight": [f, h],
                           "mlp.shared_expert.down_proj.weight": [h, f]})
        if key == "qwen2_1p5b" or layer % 4 == 3:
            shapes.update({"self_attn.q_proj.weight": [q if key == "qwen2_1p5b" else 2*q, h],
                           "self_attn.k_proj.weight": [kv, h], "self_attn.v_proj.weight": [kv, h],
                           "self_attn.o_proj.weight": [h, q]})
            if key == "qwen2_1p5b":
                shapes.update({"self_attn.q_proj.bias": [q], "self_attn.k_proj.bias": [kv], "self_attn.v_proj.bias": [kv]})
            else:
                shapes.update({"self_attn.q_norm.weight": [256], "self_attn.k_norm.weight": [256]})
        else:
            shapes.update({"linear_attn.in_proj_qkv.weight": [8192, h], "linear_attn.in_proj_z.weight": [4096, h],
                           "linear_attn.in_proj_b.weight": [32, h], "linear_attn.in_proj_a.weight": [32, h],
                           "linear_attn.conv1d.weight": [8192, 1, 4], "linear_attn.dt_bias": [32],
                           "linear_attn.A_log": [32], "linear_attn.norm.weight": [128], "linear_attn.out_proj.weight": [h, 4096]})
        result.update({f"{prefix}layers.{layer}.{name}": shape for name, shape in shapes.items()})
    return result


def verify_bundle(root: str | Path, key: str) -> dict:
    root = Path(root)
    require(key in PINS and key in BUNDLE_SHA256, "unknown/unpinned weight bundle")
    path = root / BUNDLE_ROOT / key / "manifest.json"
    require(sha256(path.read_bytes()) == BUNDLE_SHA256[key], "weight bundle manifest drift")
    manifest = load_json(path)
    require(manifest["schema_version"] == 1 and type(manifest["schema_version"]) is int, "invalid bundle schema")
    require((manifest["model_id"], manifest["revision"]) == PINS[key], "weight bundle identity drift")
    records = manifest["files"]
    require(isinstance(records, list) and len({r["path"] for r in records}) == len(records), "duplicate bundle files")
    for r in records:
        read_record(root, r)
    for field in ("config", "api", "forward", "profile"):
        require(manifest[field] in records, "source not included in pinned file inventory")
    require(manifest["index"] is None or manifest["index"] in records, "index not in file inventory")
    api = load_json(root / manifest["api"]["path"])
    require(api["sha"] == PINS[key][1] and api["id"] == PINS[key][0], "API checkpoint identity mismatch")
    advertised = {x["rfilename"]: x for x in api["siblings"] if x["rfilename"].endswith(".safetensors")}
    require(set(advertised) == {s["file"] for s in manifest["shards"]}, "API/shard inventory mismatch")
    config = load_json(root / manifest["config"]["path"])
    text = config if key == "qwen2_1p5b" else config["text_config"]
    profile = load_json(root / manifest["profile"]["path"])
    geometry = profile["shape"] if key == "qwen2_1p5b" else profile
    for field in ("hidden_size", "num_hidden_layers"):
        require(geometry[field] == text[field], "raw config/profile geometry drift: " + field)
    if key == "qwen2_1p5b":
        for field in ("intermediate_size", "num_attention_heads", "num_key_value_heads"):
            require(geometry[field] == text[field], "raw Qwen2 config/profile drift: " + field)
        require(text["vocab_size"] == 151936, "raw Qwen2 vocabulary drift")
    else:
        require(profile["vocab_size"] == text["vocab_size"], "raw config/profile vocabulary drift")
        require(profile["layer_pattern"] == ["gated_deltanet" if kind == "linear_attention" else kind
                                              for kind in text["layer_types"]], "raw config/profile layer pattern drift")
        for local, upstream in (("q_heads", "num_attention_heads"), ("kv_heads", "num_key_value_heads"), ("head_dim", "head_dim")):
            require(profile["full_attention"][local] == text[upstream], "raw attention geometry drift")
        for local, upstream in (("qk_heads", "linear_num_key_heads"), ("v_heads", "linear_num_value_heads"),
                                ("key_dim", "linear_key_head_dim"), ("value_dim", "linear_value_head_dim"),
                                ("conv_kernel", "linear_conv_kernel_dim")):
            require(profile["gated_deltanet"][local] == text[upstream], "raw GDN geometry drift")
        if key == "qwen3_5_0p8b":
            require(profile["dense_ffn"]["intermediate_size"] == text["intermediate_size"], "raw dense FFN geometry drift")
        else:
            for local, upstream in (("num_experts", "num_experts"), ("top_k", "num_experts_per_tok"), ("intermediate_size", "moe_intermediate_size")):
                require(profile["moe"][local] == text[upstream], "raw MoE geometry drift")
            require(text["shared_expert_intermediate_size"] == text["moe_intermediate_size"], "shared expert geometry drift")
    headers = {}
    bytes_count = 0
    for shard in manifest["shards"]:
        name = shard["file"]
        require(shard["url"] == f"https://huggingface.co/{PINS[key][0]}/resolve/{PINS[key][1]}/{name}", "unpinned shard URL")
        require(shard["header"] in records and shard["http_receipt"] in records, "shard not in pinned file inventory")
        lfs = advertised[name]["lfs"]
        require(integer(shard["file_bytes"], "file bytes", 9) == integer(lfs["size"], "LFS size", 9) == advertised[name]["size"],
                "API/LFS/file total mismatch")
        require(lfs["sha256"] == shard["advertised_lfs_sha256_unverified"], "advertised LFS digest mismatch")
        raw = read_record(root, shard["header"])
        receipt = load_json(root / shard["http_receipt"]["path"])
        require(type(receipt["status"]) is int and receipt["status"] == 206, "HTTP range was not honored")
        require(receipt["requested_url"] == shard["url"] and
                receipt["request_range"] == f"bytes=0-{len(raw)-1}" and
                receipt["content_range"] == f"bytes 0-{len(raw)-1}/{shard['file_bytes']}", "HTTP range/source mismatch")
        require(integer(receipt["content_length"], "HTTP content length") == len(raw) and
                integer(receipt["file_total_bytes"], "HTTP total") == shard["file_bytes"] and
                receipt["body_sha256"] == sha256(raw), "HTTP body/total mismatch")
        tensors = decode_header(raw, shard["file_bytes"])
        require(not (set(tensors) & set(headers)), "duplicate cross-shard tensor")
        for tensor, entry in tensors.items():
            headers[tensor] = dict(entry, shard=name)
            bytes_count += entry["data_offsets"][1] - entry["data_offsets"][0]
    require(len({s["file"] for s in manifest["shards"]}) == len(manifest["shards"]), "duplicate shard")
    index = manifest["index"]
    if index is not None:
        weights = load_json(root / index["path"])
        read_record(root, index)
        require(weights["weight_map"] == {k: v["shard"] for k, v in headers.items()}, "index/header tensor or shard mismatch")
        require(weights["metadata"]["total_size"] == bytes_count, "index/header total byte mismatch")
    else:
        require(len(manifest["shards"]) == 1, "index required for sharded checkpoint")
    expected = expected_text_shapes(root, key)
    prefix = "model." if key == "qwen2_1p5b" else "model.language_model."
    require(set(expected) == {k for k in headers if k.startswith(prefix)}, "main-text tensor inventory mismatch")
    for name, shape in expected.items():
        require(headers[name]["shape"] == shape, "header/config geometry mismatch: " + name)
    representative = [0] if key == "qwen2_1p5b" else [0, 3]
    selected = {k: v for k, v in headers.items() if any(k.startswith(f"{prefix}layers.{i}.") for i in representative)}
    return {"model_key": key, "model_id": PINS[key][0], "model_revision": PINS[key][1],
            "status": "PASS_PINNED_HEADER_GEOMETRY_ONLY", "bundle_sha256": BUNDLE_SHA256[key],
            "shards": len(manifest["shards"]), "header_bytes_verified": sum(s["header"]["bytes"] for s in manifest["shards"]),
            "tensor_count": len(headers), "main_text_shapes_verified": len(expected), "tensor_payload_bytes_advertised": bytes_count,
            "storage_dtype_counts": dict(sorted(Counter(v["dtype"] for v in headers.values()).items())),
            "representative_layers": representative, "representative_tensor_headers": selected,
            "tensor_payload_bytes_downloaded": 0, "tensor_content_verified": False, "official_forward_executed": False,
            "rtl_executed": False, "mac_utilization_measured": False}
