#!/usr/bin/env python3
"""Collect the reproducible q1024 composed-RTL E3 service curve.

The evidence is deliberately split at stable RTL boundaries: the production
Attention controller supplies service/queue counters, pinned upstream iDMA
supplies bus efficiency, and the production L3 top supplies SRAM conflict
counters at the complete q1024 traffic volume.  This is not a monolithic
payload numerical simulation; numerical closure remains in the L5.3/L5.4
component reports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.service_curve_importer import import_report  # noqa: E402


def text(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"missing evidence log: {path}")
    return path.read_text(errors="replace")


def one(pattern: str, body: str, label: str) -> tuple[int, ...]:
    hits = re.findall(pattern, body)
    if len(hits) != 1:
        raise SystemExit(f"expected one {label} record, found {len(hits)}")
    hit = hits[0]
    return tuple(int(v) for v in (hit if isinstance(hit, tuple) else (hit,)))


def sha256_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "reports/execution")
    args = parser.parse_args()

    controller_log = ROOT / "work/results/l5_q1024_8x8_performance_trace/tb.log"
    idma_log = ROOT / "work/results/l5_idma_e3_efficiency/tb.log"
    fabric_log = ROOT / "work/results/l5_q1024_l3_e3/verilator_100k.log"
    component_report = ROOT / "reports/execution/l5_5_balanced_8x8_local_result.json"

    controller = one(
        r"L5_Q1024_8X8_PERFORMANCE_TRACE_PASS total_cycles=(\d+) "
        r"matrix_active_cycles=(\d+) sfu_active_cycles=(\d+) "
        r"matrix_queue_bubbles=(\d+) sfu_queue_bubbles=(\d+) "
        r"tasks=(\d+) merge_rows=(\d+) score_DDR_bytes=(\d+) "
        r"probability_DDR_bytes=(\d+)",
        text(controller_log), "controller PASS")
    idma = one(
        r"IDMA_E3_EFFICIENCY_PASS length=(\d+) total_cycles=(\d+) "
        r"r_beats=(\d+) r_span=(\d+) w_beats=(\d+) w_span=(\d+) "
        r"read_eff_ppm=(\d+) write_eff_ppm=(\d+)",
        text(idma_log), "iDMA PASS")
    fabric = one(
        r"HETERO_L3_PRODUCTION_TOP_COMBINED_PASS commands=(\d+) l2=(\d+) "
        r"reads=(\d+) writes=(\d+) responses=(\d+) streams=(\d+) "
        r"matrix=(\d+) aha=(\d+) kv=(\d+) promotions=(\d+) "
        r"conflicts=(\d+) rstall=(\d+) wstall=(\d+)",
        text(fabric_log), "fabric PASS")

    (total_cycles, matrix_cycles, sfu_cycles, matrix_bubbles, sfu_bubbles,
     tasks, merge_rows, score_bytes, probability_bytes) = controller
    (dma_length, _dma_cycles, r_beats, r_span, w_beats, w_span,
     read_ppm, write_ppm) = idma
    (commands, l2_transactions, reads, writes, responses, streams,
     matrix_streams, aha_streams, kv_streams, promotions, conflicts,
     read_stalls, write_stalls) = fabric

    expected_l2 = 93_585_408 // 64 + 1_048_576 // 64
    checks = {
        "controller_tasks_12672": tasks == 12_672,
        "controller_merge_rows_43008": merge_rows == 43_008,
        "score_probability_ddr_zero": score_bytes == probability_bytes == 0,
        "idma_one_mib": dma_length == 1_048_576,
        "idma_read_no_bubbles": r_beats == r_span and read_ppm == 1_000_000,
        "idma_write_no_bubbles": w_beats == w_span and write_ppm == 1_000_000,
        "fabric_q1024_volume": l2_transactions >= expected_l2,
        "fabric_responses_match_reads": responses == reads,
        "fabric_stream_coverage": streams == 10_000 and matrix_streams > 0
        and aha_streams > 0 and kv_streams > 0,
    }
    if not all(checks.values()):
        raise SystemExit(f"E3 evidence check failed: {checks}")

    source_paths = [
        ROOT / "rtl/attention/blocked_attention_stream_controller.sv",
        ROOT / "rtl/attention/fp32_block32_softmax_tile16_candidate.sv",
        ROOT / "rtl/attention/fp32_mlo_merge8_candidate.sv",
        ROOT / "rtl/integration/idma_backend_rw_axi_flat_wrap.sv",
        ROOT / "rtl/integration/hetero_l3_production_top.sv",
        ROOT / "tb/tb_l5_q1024_8x8_performance_trace.sv",
        ROOT / "tb/tb_idma_e3_efficiency.sv",
    ]
    source_sha = sha256_files(source_paths)
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()

    # The measured iDMA path is 64 B/cycle.  Against the frozen external DDR
    # limits this is 64/100 read efficiency and a saturated 40/40 write path.
    curve = {
        "commit": commit,
        "source_sha256": source_sha,
        "sequence": 1024,
        "clock_hz": 1_000_000_000,
        "attention_matrix_cycles": matrix_cycles,
        "attention_sfu_cycles": sfu_cycles,
        "silu_cycles": 9_175_040,
        "matrix_producer_stall_cycles": 0,
        "matrix_queue_bubble_cycles": matrix_bubbles,
        "sram_bank_conflict_cycles": conflicts,
        "event_wait_signal_cycles": sfu_bubbles,
        "ddr_read_bytes": 93_585_408,
        "ddr_write_bytes": 1_048_576,
        "ddr_read_efficiency": 0.64,
        "ddr_write_efficiency": 1.0,
        "score_ddr_bytes": score_bytes,
        "probability_ddr_bytes": probability_bytes,
        "evidence_class": "E3_INTEGRATED",
    }
    imported = import_report(curve)
    result = {
        "schema_version": 1,
        "status": "PASS" if imported["status"] == "PASS_REVIEW" else "FAIL",
        "evidence_class": "composed_real_RTL_E3",
        "boundary": "production controller + production L3 fabric + pinned upstream iDMA",
        "non_claim": "not a monolithic payload numerical RTL simulation",
        "checks": checks,
        "measured": {
            "controller_total_cycles": total_cycles,
            "controller_tasks": tasks,
            "merge_rows": merge_rows,
            "fabric_commands": commands,
            "fabric_l2_transactions": l2_transactions,
            "fabric_reads": reads,
            "fabric_writes": writes,
            "fabric_promotions": promotions,
            "fabric_read_stalls": read_stalls,
            "fabric_write_stalls": write_stalls,
            "idma_read_efficiency_on_512b_bus": read_ppm / 1_000_000,
            "idma_write_efficiency_on_512b_bus": write_ppm / 1_000_000,
        },
        "curve": curve,
        "imported": imported,
        "provenance": {
            "controller_log_sha256": hashlib.sha256(controller_log.read_bytes()).hexdigest(),
            "idma_log_sha256": hashlib.sha256(idma_log.read_bytes()).hexdigest(),
            "fabric_log_sha256": hashlib.sha256(fabric_log.read_bytes()).hexdigest(),
            "balanced_8x8_report_sha256": hashlib.sha256(component_report.read_bytes()).hexdigest(),
            "source_files_sha256": source_sha,
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = args.output_dir / "l5_5_q1024_e3_curve.json"
    imported_path = args.output_dir / "l5_5_q1024_e3_imported.json"
    result_path = args.output_dir / "l5_5_q1024_e3_result.json"
    raw_path.write_text(json.dumps(curve, indent=2, sort_keys=True) + "\n")
    imported_path.write_text(json.dumps(imported, indent=2, sort_keys=True) + "\n")
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": result["status"],
        "import_status": imported["status"],
        "full_model_cycles": imported["calibration"]["full_model_cycles"],
        "tokens_per_second": imported["calibration"]["tokens_per_second"],
        "result": str(result_path.relative_to(ROOT)),
    }, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
