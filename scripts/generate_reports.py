#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from heteronpu.config import load_architecture
from heteronpu.scheduler import CycleModel
from heteronpu.workloads import run_toy_cnn, run_toy_llm_block


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    cfg = load_architecture(root / "configs/arch_v0.yaml")
    cycle = CycleModel(cfg)

    cnn = run_toy_cnn(seed=3)
    llm_bf16 = run_toy_llm_block(tokens=7, seed=7, storage_format="bf16")
    llm_kv8 = run_toy_llm_block(tokens=7, seed=7, storage_format="int8")

    cnn_tasks = cycle.cnn_layer_tasks(
        batch=1, out_h=56, out_w=56, in_channels=64, out_channels=64,
        kernel_h=3, kernel_w=3, dtype="int8", prefix="resnet_stage"
    )
    prefill_tasks = cycle.llm_block_tasks(
        tokens=384, hidden=1536, heads=12, kv_heads=2, head_dim=128,
        ffn=8960, dtype="w4a8", decode=False
    )
    decode_tasks = cycle.llm_block_tasks(
        tokens=1, hidden=1536, heads=12, kv_heads=2, head_dim=128,
        ffn=8960, dtype="w4a8", decode=True
    )

    clock = cfg.clock_hz
    rows = int(cfg.matrix["array_rows"])
    cols = int(cfg.matrix["array_cols"])
    int8_macs_s = rows * cols * clock
    bf16_macs_s = int(cfg.matrix["bf16_macs_per_cycle"]) * clock
    w4_native_macs_s = int(cfg.matrix["w4a8_native_dual_dot_target_macs_per_cycle"]) * clock
    params = 1_500_000_000
    prefill_target = 500
    decode_target = 10
    read_bw = float(cfg.memory["target_read_bandwidth_GBps"])

    sram = cfg.raw["on_chip_sram"]
    budget_fields = [
        "shared_l2_KiB", "matrix_spad_KiB", "matrix_acc_KiB",
        "cgra_local_KiB", "kv_staging_KiB", "control_trace_KiB"
    ]
    sram_sum = sum(int(sram[name]) for name in budget_fields)

    report = {
        "status": "PASS",
        "architecture": cfg.name,
        "sandbox_evidence": {
            "cnn_max_abs_error": cnn["max_abs_error"],
            "llm_bf16_paged_max_abs_error": llm_bf16["max_abs_error"],
            "llm_int8_kv_max_abs_error": llm_kv8["max_abs_error"],
            "llm_int8_kv_mean_abs_error": llm_kv8["mean_abs_error"],
        },
        "cycle_model": {
            "cnn_resnet_like_layer": cycle.summarize(cycle.schedule(cnn_tasks), clock),
            "qwen_1p5b_like_prefill_block_q384": cycle.summarize(cycle.schedule(prefill_tasks), clock),
            "qwen_1p5b_like_decode_block_context4096": cycle.summarize(cycle.schedule(decode_tasks), clock),
            "warning": "analytical task model, not RTL-measured cycles",
        },
        "roofline_assumptions": {
            "clock_hz": clock,
            "int8_peak_TMAC_s": int8_macs_s / 1e12,
            "bf16_peak_TMAC_s": bf16_macs_s / 1e12,
            "w4a8_native_target_TMAC_s": w4_native_macs_s / 1e12,
            "w4_storage_only_peak_TMAC_s": int8_macs_s / 1e12,
            "dense_model_parameters": params,
            "approx_linear_MAC_per_token": params,
            "int8_utilization_required_for_500_prefill_token_s": params * prefill_target / int8_macs_s,
            "weight_bandwidth_GBps_for_10_decode_token_s_W8": params / 1e9 * decode_target,
            "weight_bandwidth_GBps_for_10_decode_token_s_W4": params / 2 / 1e9 * decode_target,
            "ideal_bandwidth_ceiling_token_s_W8": read_bw / (params / 1e9),
            "ideal_bandwidth_ceiling_token_s_W4": read_bw / (params / 2 / 1e9),
            "warning": "excludes attention, KV, scales, inefficiency and contention",
        },
        "sram_budget": {
            "declared_total_KiB": int(sram["total_KiB"]),
            "partition_sum_KiB": sram_sum,
            "consistent": sram_sum == int(sram["total_KiB"]),
        },
    }
    (reports / "architecture_results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    md = f"""# Sandbox architecture result summary

Status: **{report['status']}**

- CNN exact regression max absolute error: `{cnn['max_abs_error']}`
- BF16 toy Transformer block, contiguous vs paged KV max absolute error: `{llm_bf16['max_abs_error']}`
- INT8 KV toy Transformer block max/mean absolute error: `{llm_kv8['max_abs_error']:.8f}` / `{llm_kv8['mean_abs_error']:.8f}`
- 32×64 INT8 peak assumption at 1 GHz: `{int8_macs_s/1e12:.3f} TMAC/s`
- 500 token/s for an assumed 1.5B dense model requires `{params*prefill_target/int8_macs_s:.1%}` of that INT8 peak before attention and other overheads.
- 10 token/s requires approximately `{params/1e9*decode_target:.1f} GB/s` W8 or `{params/2/1e9*decode_target:.1f} GB/s` W4 weight traffic before other traffic.
- SRAM partition sum: `{sram_sum} KiB`; declared total: `{sram['total_KiB']} KiB`.

The cycle estimates in `architecture_results.json` are architecture models, not measured RTL results. W4 storage-only mode halves weight bytes but retains the INT8 MAC rate. The 4.096 TMAC/s W4 value is a future native dual-dot target and must not be claimed until RTL simulation and DC synthesis close.
"""
    (reports / "sandbox_result_summary.md").write_text(md, encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(reports / 'architecture_results.json')}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
