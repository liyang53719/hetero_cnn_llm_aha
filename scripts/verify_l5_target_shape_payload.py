#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise SystemExit(f"L5_TARGET_PAYLOAD_AUDIT_FAIL {message}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    names = [
        "qkv_segment", "rope_gqa", "mlo", "oproj", "norm2",
        "gate_up", "silu_product", "down",
    ]
    receipts = {
        name: json.loads((args.reports / f"l5_target_{name}_result.json").read_text())
        for name in names
    }
    for name, receipt in receipts.items():
        require(receipt["status"] == "PASS", f"status {name}")
        require(receipt.get("node_mismatches", 0) == 0, f"mismatch {name}")
        require(receipt.get("oom_events", 0) == 0, f"oom {name}")

    require(receipts["mlo"]["score_matrix_materialized"] is False, "score matrix")
    require(
        receipts["qkv_segment"]["q_biased_sha256"] ==
        "480793d57d47c2b9480bb7e4c874fda45f5f4da2ac33a0bc7fd81a174941880e",
        "Q receipt chain",
    )
    require(
        receipts["rope_gqa"]["q_rope_sha256"] ==
        "da6332ce70e15a4d10299ccc3b5dddede3f4c76feddb6c76f3399f301b4e5f22",
        "RoPE receipt chain",
    )
    require(
        receipts["mlo"]["attention_sha256"] ==
        "86c06c97e24153ce786b30f4e15fb7b76f48eacf2126adc33be94412837eb681",
        "attention receipt chain",
    )
    require(
        receipts["oproj"]["residual1_sha256"] ==
        "df2d5af8926229b7c3ea34aa7c0dfc1ad381fee5cd7149d86b5b01739f518671",
        "residual receipt chain",
    )
    require(
        receipts["norm2"]["norm2_sha256"] ==
        "bb884b8182e44eac53dc64f5c06cdbce752509a343fe9331e2ee8db433831385",
        "norm2 receipt chain",
    )
    require(
        receipts["gate_up"]["gate_output_sha256"] ==
        "ec204a74ad5bc7b68f34595ac7b24ffac5ca432de41077857476e92de6f1bcab" and
        receipts["gate_up"]["up_output_sha256"] ==
        "581709c8d740185c32f457470a1965102e648ac0dacedf14191fbb836a7a98ac",
        "gate/up receipt chain",
    )
    require(
        receipts["silu_product"]["product_sha256"] ==
        "5076748a33e3b316acc2647554cea7d193b50099d6fa40ebdb1dec67a716fb1c",
        "product receipt chain",
    )

    array_steps = (
        receipts["qkv_segment"]["array_steps"] +
        receipts["oproj"]["array_steps"] +
        receipts["gate_up"]["array_steps_total"] +
        receipts["down"]["array_steps"]
    )
    matrix_cycles = (
        receipts["qkv_segment"]["matrix_cycles"] +
        receipts["oproj"]["matrix_cycles"] +
        receipts["gate_up"]["cycles_total"] +
        receipts["down"]["matrix_cycles"]
    )
    segmented_cycles = (
        receipts["qkv_segment"]["total_cycles"] +
        receipts["rope_gqa"]["total_cycles"] +
        receipts["mlo"]["total_cycles"] +
        receipts["oproj"]["total_cycles"] +
        receipts["norm2"]["total_cycles"] +
        receipts["gate_up"]["cycles_total"] +
        receipts["silu_product"]["total_cycles"] +
        receipts["down"]["total_cycles"]
    )
    require(array_steps == 1486848, f"array steps {array_steps}")
    require(matrix_cycles == 5947392, f"matrix cycles {matrix_cycles}")
    require(segmented_cycles == 6036046, f"segmented cycles {segmented_cycles}")
    result = {
        "stage": "L5",
        "subgate": "target-shape segmented payload",
        "status": "PASS",
        "evidence_class": "segmented_rtl_payload_measured",
        "integrated_controller_trace_status": "PENDING",
        "tokens": 2,
        "hidden": 1536,
        "intermediate": 8960,
        "array_steps": array_steps,
        "matrix_cycles": matrix_cycles,
        "non_matrix_cycles": segmented_cycles - matrix_cycles,
        "segmented_total_cycles": segmented_cycles,
        "score_matrix_materialized": False,
        "final_sha256": receipts["down"]["final_sha256"],
        "receipts": names,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        "L5_TARGET_SHAPE_PAYLOAD_AUDIT_PASS "
        f"array_steps={array_steps} segmented_cycles={segmented_cycles} "
        "controller_trace=PENDING"
    )


if __name__ == "__main__":
    main()
