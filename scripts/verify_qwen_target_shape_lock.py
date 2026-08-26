#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise SystemExit(f"QWEN_TARGET_SHAPE_LOCK_FAIL {message}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--license", type=Path, required=True)
    parser.add_argument("--modeling", type=Path, required=True)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    lock = json.loads(args.lock.read_text())
    provenance = lock["provenance"]
    observed_hashes = {
        "config_sha256": sha256(args.config),
        "license_sha256": sha256(args.license),
        "modeling_sha256": sha256(args.modeling),
        "configuration_sha256": sha256(args.configuration),
    }
    for name, observed in observed_hashes.items():
        require(observed == provenance[name], f"{name}={observed}")

    shape = lock["shape"]
    direct_fields = {
        "hidden_size": "hidden_size",
        "intermediate_size": "intermediate_size",
        "num_attention_heads": "num_attention_heads",
        "num_key_value_heads": "num_key_value_heads",
        "num_hidden_layers": "num_hidden_layers",
        "max_position_embeddings": "max_position_embeddings",
        "sliding_window": "sliding_window",
        "use_sliding_window": "use_sliding_window",
        "rms_norm_epsilon": "rms_norm_eps",
        "rope_theta": "rope_theta",
        "activation": "hidden_act",
        "dtype": "torch_dtype",
    }
    for lock_name, config_name in direct_fields.items():
        require(shape[lock_name] == config[config_name], f"field {lock_name}")

    hidden = config["hidden_size"]
    heads = config["num_attention_heads"]
    kv_heads = config["num_key_value_heads"]
    intermediate = config["intermediate_size"]
    require(hidden % heads == 0, "hidden not divisible by attention heads")
    require(heads % kv_heads == 0, "attention heads not divisible by KV heads")
    head_dim = hidden // heads
    groups = heads // kv_heads
    kv_width = kv_heads * head_dim
    require(shape["head_dim"] == head_dim, "head_dim")
    require(shape["num_key_value_groups"] == groups, "num_key_value_groups")
    require(shape["query_width"] == hidden, "query_width")
    require(shape["key_value_width"] == kv_width, "key_value_width")
    expected_mapping = [head // groups for head in range(heads)]
    require(lock["gqa_mapping"]["query_to_kv_head"] == expected_mapping, "GQA mapping")

    scale = struct.unpack("<f", struct.pack("<f", 1.0 / math.sqrt(head_dim)))[0]
    scale_bits = struct.unpack("<I", struct.pack("<f", scale))[0]
    require(shape["attention_scale_fp32_bits"] == f"0x{scale_bits:08x}", "attention scale bits")

    modeling = args.modeling.read_text()
    expected_bias = {
        "q_proj": True,
        "k_proj": True,
        "v_proj": True,
        "o_proj": False,
        "gate_proj": False,
        "up_proj": False,
        "down_proj": False,
    }
    for projection, bias in expected_bias.items():
        pattern = rf"self\.{projection}\s*=\s*nn\.Linear\([^\n]+bias={str(bias)}\)"
        require(re.search(pattern, modeling) is not None, f"source bias {projection}")
    require(lock["bias_policy"] == expected_bias, "bias policy lock")

    matrix_shapes = {
        "q": (hidden, hidden),
        "k": (hidden, kv_width),
        "v": (hidden, kv_width),
        "o": (hidden, hidden),
        "gate": (hidden, intermediate),
        "up": (hidden, intermediate),
        "down": (intermediate, hidden),
    }
    total_weights = 0
    total_steps = 0
    for name, (rows, columns) in matrix_shapes.items():
        require(columns % lock["physical_array"]["columns"] == 0, f"unaligned {name}")
        weights = rows * columns
        steps = rows * (columns // lock["physical_array"]["columns"])
        entry = lock["matrices"][name]
        require(entry == {
            "rows": rows,
            "columns": columns,
            "weights": weights,
            "array_steps_per_token": steps,
        }, f"matrix {name}")
        total_weights += weights
        total_steps += steps
    totals = lock["totals"]
    require(totals["weights"] == total_weights, "total weights")
    require(totals["bf16_weight_bytes"] == 2 * total_weights, "BF16 bytes")
    require(totals["single_token_array_steps"] == total_steps, "single-token steps")
    two_token_steps = total_steps + lock["matrices"]["k"]["array_steps_per_token"] + lock["matrices"]["v"]["array_steps_per_token"]
    require(totals["two_token_compact_array_steps"] == two_token_steps, "two-token steps")
    require(totals["serialized_four_cycle_schedule_projection"] == 4 * two_token_steps, "schedule projection")
    require("not_rtl_measured" in totals["projection_evidence_class"], "projection label")

    result = {
        "stage": "L5",
        "subgate": "Qwen target-shape lock",
        "status": "PASS",
        "model": lock["model"],
        "revision": lock["revision"],
        "license": lock["license"],
        "observed_hashes": observed_hashes,
        "shape": shape,
        "bias_policy": expected_bias,
        "gqa_query_to_kv_head": expected_mapping,
        "weights": total_weights,
        "bf16_weight_bytes": 2 * total_weights,
        "single_token_array_steps": total_steps,
        "two_token_compact_array_steps": two_token_steps,
        "rtl_cycles_measured": False,
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2) + "\n")
    print(
        "L5_QWEN_TARGET_SHAPE_LOCK_PASS "
        f"hidden={hidden} heads={heads} kv_heads={kv_heads} head_dim={head_dim} "
        f"intermediate={intermediate} two_token_steps={two_token_steps}"
    )


if __name__ == "__main__":
    main()
