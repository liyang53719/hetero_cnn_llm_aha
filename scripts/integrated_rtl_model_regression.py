#!/usr/bin/env python3
"""Run the L11 clean-room numerical/cycle integration gate.

The model cases cover the requested context sizes.  The RTL case drives the
same deterministic kernel vectors through one integrated Matrix/SFU/KV shell
with concurrent traffic and deterministic ready/valid backpressure.  The
report keeps functional model results, RTL functional results, and measured
RTL cycles separate.  It does not claim official Gemmini/AHA equivalence.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from heteronpu.cgra_sfu import CgraSfuModel
from heteronpu.kv_engine import KVPageEngine
from heteronpu.matrix_engine import MatrixEngineModel
from heteronpu.workloads import (
    ToyLlmConfig,
    _attention_token,
    _bf16_gemm,
    make_toy_llm,
    run_toy_llm_block,
)
from heteronpu.dtypes import bf16_round


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "work" / "results" / "l11_integrated_rtl_model_regression"


def decode_context4096_model() -> dict[str, object]:
    """Compare contiguous and paged attention for two decode tokens."""
    context = 4096
    cfg = ToyLlmConfig()
    weights = make_toy_llm(92, cfg)
    rng = np.random.default_rng(93)
    x = bf16_round(rng.normal(0.0, 0.5, size=(context + 2, cfg.hidden)).astype(np.float32))
    normed = CgraSfuModel.rmsnorm(x, weights.norm1)
    q = bf16_round(_bf16_gemm(normed, weights.wq)).reshape(-1, cfg.heads, cfg.head_dim)
    k = bf16_round(_bf16_gemm(normed, weights.wk)).reshape(-1, cfg.kv_heads, cfg.head_dim)
    v = bf16_round(_bf16_gemm(normed, weights.wv)).reshape(-1, cfg.kv_heads, cfg.head_dim)
    q = CgraSfuModel.rope(q)
    k = CgraSfuModel.rope(k)
    v = CgraSfuModel.rope(v)

    kv = KVPageEngine(
        page_tokens=4,
        physical_pages=(context + 3) // 4 + 8,
        kv_heads=cfg.kv_heads,
        head_dim=cfg.head_dim,
        storage_format="bf16",
    )
    kv.append(0, 0, k[:context], v[:context])
    errors: list[float] = []
    for token in (context, context + 1):
        kv.append(0, 0, k[token], v[token])
        gathered_k, gathered_v = kv.read(0, 0)
        reference = _attention_token(q[token], k[: token + 1], v[: token + 1], cfg)
        output = _attention_token(q[token], gathered_k, gathered_v, cfg)
        errors.append(float(np.max(np.abs(reference - output))))
    kv.check_invariants()
    return {
        "status": "PASS" if max(errors, default=1.0) == 0.0 else "FAIL",
        "context_tokens": context,
        "decode_tokens_checked": 2,
        "max_abs_error": max(errors, default=1.0),
        "pages_in_use": kv.pages_in_use,
        "read_tokens": kv.read_tokens,
    }


def continuous_request_model() -> dict[str, object]:
    """Exercise two interleaved requests plus a fork/COW continuation."""
    rng = np.random.default_rng(94)
    kv = KVPageEngine(page_tokens=4, physical_pages=128, kv_heads=2, head_dim=4)
    expected: dict[int, list[np.ndarray]] = {0: [], 1: []}
    for step in range(24):
        sequence = step % 2
        token = rng.normal(0.0, 0.2, size=(2, 4)).astype(np.float32)
        expected[sequence].append(bf16_round(token))
        kv.append(sequence, 0, token, -token)
        got_k, got_v = kv.read(sequence, 0)
        if not np.array_equal(got_k, np.asarray(expected[sequence], dtype=np.float32)):
            return {"status": "FAIL", "reason": "interleaved request K mismatch"}
        if not np.array_equal(got_v, bf16_round(-np.asarray(expected[sequence], dtype=np.float32))):
            return {"status": "FAIL", "reason": "interleaved request V mismatch"}
    source_before, _ = kv.read(0, 0)
    kv.fork_sequence(0, 2, 0)
    extra = rng.normal(0.0, 0.2, size=(2, 4)).astype(np.float32)
    kv.append(2, 0, extra, -extra)
    source_after, _ = kv.read(0, 0)
    passed = np.array_equal(source_before, source_after)
    kv.free_sequence(0)
    kv.free_sequence(1)
    kv.free_sequence(2)
    kv.check_invariants()
    return {
        "status": "PASS" if passed and kv.pages_in_use == 0 else "FAIL",
        "interleaved_steps": 24,
        "cow_source_unchanged": passed,
        "pages_in_use_after_free": kv.pages_in_use,
    }


def run_model_cases() -> dict[str, object]:
    cases: dict[str, object] = {}
    for tokens in (128, 384):
        result = run_toy_llm_block(tokens=tokens, storage_format="bf16")
        cases[f"q{tokens}_prefill"] = {
            "status": "PASS" if result["max_abs_error"] == 0 else "FAIL",
            "max_abs_error": result["max_abs_error"],
            "mean_abs_error": result["mean_abs_error"],
            "pages_in_use": result["kv_stats"]["pages_in_use"],
        }
    cases["decode_context4096"] = decode_context4096_model()
    cases["continuous_requests"] = continuous_request_model()
    return {
        "status": "PASS" if all(case["status"] == "PASS" for case in cases.values()) else "FAIL",
        "cases": cases,
        "scope": "functional Python model only",
    }


def run_rtl_case() -> dict[str, object]:
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    binary = RESULT_ROOT / "tb_hetero_npu_numerical_integration_v0"
    compile_log = RESULT_ROOT / "iverilog_compile.log"
    run_log = RESULT_ROOT / "iverilog_run.log"
    sources = [
        ROOT / "rtl/integration/hetero_npu_numerical_integration_v0.sv",
        ROOT / "rtl/matrix/matrix_engine_int8_tile.sv",
        ROOT / "rtl/sfu/cgra_sfu_vector.sv",
        ROOT / "rtl/kv/kv_cache_engine.sv",
        ROOT / "tb/tb_hetero_npu_numerical_integration_v0.sv",
    ]
    compile_cmd = [
        "taskset",
        "-c",
        "8-25",
        "iverilog",
        "-g2012",
        "-s",
        "tb_hetero_npu_numerical_integration_v0",
        "-o",
        str(binary),
        *(str(path) for path in sources),
    ]
    compiled = subprocess.run(compile_cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    compile_log.write_text(compiled.stdout, encoding="utf-8")
    if compiled.returncode != 0:
        return {"status": "FAIL", "phase": "compile", "returncode": compiled.returncode}
    run_cmd = ["taskset", "-c", "8-25", "vvp", str(binary)]
    ran = subprocess.run(run_cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    run_log.write_text(ran.stdout, encoding="utf-8")
    if ran.returncode != 0:
        return {"status": "FAIL", "phase": "simulate", "returncode": ran.returncode, "log": str(run_log)}

    matrix_match = re.search(r"RTL_MATRIX_RESULT count=(\d+) v0=(-?\d+) v1=(-?\d+) v2=(-?\d+) v3=(-?\d+)", ran.stdout)
    sfu_matches = re.findall(r"RTL_SFU_RESULT op=(\d+) l0=(-?\d+) l1=(-?\d+) l2=(-?\d+) l3=(-?\d+)", ran.stdout)
    kv_matches = re.findall(r"RTL_KV_RESULT op=(\d+) status=(\d+) length=(\d+) k=([0-9a-fA-F]+) v=([0-9a-fA-F]+)", ran.stdout)
    cycle_match = re.search(r"RTL_NUMERICAL_INTEGRATION_PASS cycles=(\d+)", ran.stdout)
    expected_sfu = {
        0: [6, 0, 4, 5],
        3: [1, 2, 0, 4],
        5: [4, 0, 0, 0],
    }
    matrix_ok = bool(matrix_match) and [int(x) for x in matrix_match.groups()] == [4, 12, 2, 2, 21]
    sfu_ok = len(sfu_matches) == 3 and all(
        expected_sfu[int(op)] == [int(l0), int(l1), int(l2), int(l3)]
        for op, l0, l1, l2, l3 in sfu_matches
    )
    kv_ok = (
        len(kv_matches) == 2
        and kv_matches[0][:3] == ("1", "0", "5")
        and int(kv_matches[0][3], 16) == 0x104
        and int(kv_matches[0][4], 16) == 0x204
        and kv_matches[1][:3] == ("3", "0", "0")
    )
    marker_ok = "RTL_NUMERICAL_INTEGRATION_PASS" in ran.stdout
    return {
        "status": "PASS" if matrix_ok and sfu_ok and kv_ok and marker_ok else "FAIL",
        "functional_pass": matrix_ok and sfu_ok and kv_ok,
        "cycle_accurate_pass": marker_ok,
        "measured_cycles": int(cycle_match.group(1)) if cycle_match else None,
        "backpressure": "deterministic concurrent ready/valid stalls",
        "artifacts": {"compile_log": str(compile_log), "run_log": str(run_log)},
        "stdout_tail": ran.stdout.splitlines()[-12:],
        "scope": "clean-room Matrix/SFU/KV integrated numerical kernel",
    }


def run_rocc_wrapper_case() -> dict[str, object]:
    """Run the shell-level command-scoreboard to RoCC wrapper contract."""
    binary = RESULT_ROOT / "tb_hetero_npu_gemmini_rocc_integration_v0"
    compile_log = RESULT_ROOT / "rocc_wrapper_compile.log"
    run_log = RESULT_ROOT / "rocc_wrapper_run.log"
    sources = [
        ROOT / "rtl/common/rv_fifo.sv",
        ROOT / "rtl/top/command_dispatch.sv",
        ROOT / "rtl/top/hetero_npu_shell.sv",
        ROOT / "rtl/integration/command_event_scoreboard.sv",
        ROOT / "rtl/integration/engine_contract_adapter.sv",
        ROOT / "rtl/integration/matrix_descriptor_v2_snapshot.sv",
        ROOT / "rtl/integration/matrix_descriptor_v2_decode.sv",
        ROOT / "rtl/integration/gemmini_descriptor_v2_emitter.sv",
        ROOT / "rtl/integration/gemmini_rocc_program_adapter.sv",
        ROOT / "rtl/integration/gemmini_descriptor_v2_pipeline.sv",
        ROOT / "rtl/kv/kv_idma_basic_core.sv",
        ROOT / "rtl/kv/kv_descriptor_v2_idma_adapter.sv",
        ROOT / "rtl/integration/hetero_npu_gemmini_rocc_integration_v0.sv",
        ROOT / "tb/tb_hetero_npu_gemmini_rocc_integration_v0.sv",
    ]
    compile_cmd = [
        "taskset", "-c", "8-25", "iverilog", "-g2012", "-s",
        "tb_hetero_npu_gemmini_rocc_integration_v0", "-o", str(binary),
        *(str(path) for path in sources),
    ]
    compiled = subprocess.run(compile_cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    compile_log.write_text(compiled.stdout, encoding="utf-8")
    if compiled.returncode != 0:
        return {"status": "FAIL_COMPILE", "returncode": compiled.returncode}
    ran = subprocess.run(["taskset", "-c", "8-25", "vvp", str(binary)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    run_log.write_text(ran.stdout, encoding="utf-8")
    passed = ran.returncode == 0 and "GEMMINI_ROCC_INTEGRATION_PASS" in ran.stdout
    cycles = re.search(r"GEMMINI_ROCC_INTEGRATION_PASS cycles=(\d+)", ran.stdout)
    return {
        "status": "PASS" if passed else "FAIL_SIMULATION",
        "functional_pass": passed,
        "cycle_accurate_pass": passed,
        "measured_cycles": int(cycles.group(1)) if cycles else None,
        "scope": "hetero shell/command scoreboard to wrapper-only Gemmini RoCC boundary",
        "artifacts": {"compile_log": str(compile_log), "run_log": str(run_log)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/l11_integrated_rtl_model_regression.json")
    args = parser.parse_args()
    model = run_model_cases()
    rtl = run_rtl_case()
    rocc_wrapper = run_rocc_wrapper_case()
    rtl["rocc_wrapper"] = rocc_wrapper
    rtl_status = rtl["status"] == "PASS" and rocc_wrapper["status"] == "PASS"
    rtl["status"] = "PASS" if rtl_status else "FAIL"
    report = {
        "status": "PASS" if model["status"] == "PASS" and rtl["status"] == "PASS" else "FAIL",
        "functional": {"model": model, "rtl": rtl},
        "cycle_accurate": {
            "status": bool(rtl.get("cycle_accurate_pass", False) and rocc_wrapper.get("cycle_accurate_pass", False)),
            "measured_cycles": {
                "numerical_kernel": rtl.get("measured_cycles"),
                "rocc_wrapper": rocc_wrapper.get("measured_cycles"),
            },
            "scope": "RTL kernel integration only; not a full-chip performance result",
        },
        "performance_estimate": {"status": "NOT_CLAIMED", "reason": "no full-chip measured workload"},
        "rtl_measured_performance": {"status": "PARTIAL", "cycles": rtl.get("measured_cycles")},
        "claims": {
            "q128_prefill_functional": model["cases"]["q128_prefill"]["status"] == "PASS",
            "q384_prefill_functional": model["cases"]["q384_prefill"]["status"] == "PASS",
            "decode_context4096_functional": model["cases"]["decode_context4096"]["status"] == "PASS",
            "continuous_request_functional": model["cases"]["continuous_requests"]["status"] == "PASS",
            "full_official_gemmini_aha_equivalence": False,
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(out)}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
