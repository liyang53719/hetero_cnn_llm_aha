#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise SystemExit(f"Q128_CONTRACT_FAIL {message}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    shape = contract["shape"]
    array = contract["physical_array"]
    steps = contract["matrix_steps"]
    work = contract["stream_work"]
    sequence = shape["sequence"]
    hidden = shape["hidden"]
    intermediate = shape["intermediate"]
    q_heads = shape["q_heads"]
    kv_heads = shape["kv_heads"]
    head_dim = shape["head_dim"]
    row_batches = (sequence + array["rows"] - 1) // array["rows"]
    kv_width = kv_heads * head_dim
    expected_steps = {
        "q": row_batches * hidden * (hidden // array["columns"]),
        "k": row_batches * hidden * (kv_width // array["columns"]),
        "v": row_batches * hidden * (kv_width // array["columns"]),
        "o": row_batches * hidden * (hidden // array["columns"]),
        "gate": row_batches * hidden * (intermediate // array["columns"]),
        "up": row_batches * hidden * (intermediate // array["columns"]),
        "down": row_batches * intermediate * (hidden // array["columns"]),
    }
    require(array["row_batches"] == row_batches == 8, "row batches")
    for name, expected in expected_steps.items():
        require(steps[name] == expected, f"matrix {name}")
    require(steps["total"] == sum(expected_steps.values()) == 11698176, "matrix total")
    causal_sum = sequence * (sequence + 1) // 2
    causal_updates = causal_sum * q_heads
    require(work["causal_tokens_per_head_sum"] == causal_sum == 8256, "causal sum")
    require(work["causal_head_token_updates"] == causal_updates == 99072, "causal updates")
    require(work["dot128_operations"] == causal_updates, "dot operations")
    require(work["online_updates"] == causal_updates, "online updates")
    require(work["reciprocals"] == sequence * q_heads == 1536, "reciprocals")
    require(work["normalization_chunks"] == sequence * q_heads * (head_dim // 16), "normalize")
    require(work["q_rope_pairs"] == sequence * q_heads * (head_dim // 2), "Q RoPE")
    require(work["k_rope_pairs"] == sequence * kv_heads * (head_dim // 2), "K RoPE")
    require(work["rope_pairs_total"] == work["q_rope_pairs"] + work["k_rope_pairs"], "RoPE total")
    require(work["input_rms_chunks"] == sequence * (hidden // 16), "input RMS")
    require(work["post_attention_rms_chunks"] == sequence * (hidden // 16), "norm2 RMS")
    require(work["silu_scalars"] == sequence * intermediate, "SiLU")
    require(work["product_chunks"] == sequence * (intermediate // 16), "product")
    require(contract["storage_policy"]["score_matrix_materialized"] is False, "score matrix")
    require(contract["cycle_policy"]["rtl_measured_cycles"] is None, "unmeasured cycles")
    result = {
        "stage": "L5",
        "subgate": "q128 prefill operation contract",
        "status": "PASS",
        "evidence_class": contract["evidence_class"],
        "row_batches": row_batches,
        "matrix_steps": steps["total"],
        "causal_head_token_updates": causal_updates,
        "score_matrix_materialized": False,
        "rtl_measured_cycles": None,
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2) + "\n")
    print(
        "L5_Q128_CONTRACT_PASS row_batches=8 matrix_steps=11698176 "
        "causal_updates=99072 measured_cycles=null"
    )


if __name__ == "__main__":
    main()
