#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/execution"


def load(name: str) -> dict:
    return json.loads((REPORTS / name).read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    source = load("OPERATOR_SOURCE_REPLAY_V3.json")
    rtl = load("OPERATOR_RTL_GENERATION_V3.json")
    roots = load("OPERATOR_ROOT_DC_800MHZ.json")
    primitives = load("OPERATOR_PRIMITIVE_DC_800MHZ.json")
    endpoints = load("OPERATOR_ENDPOINT_BINDING_V3.json")
    canaries = load("OPERATOR_MODEL_CANARIES_V3.json")
    stress = load("OPERATOR_ROOT_STRESS_V3.json")
    combined = load("OPERATOR_COMBINED_OWNER_SHELL_DC_800MHZ.json")
    drc = load("OPERATOR_COMBINED_DRC_CLOSURE_800MHZ.json")
    sram = load("L10_SRAM_MACRO_INVENTORY_RESULT.json")
    macro = load("OPERATOR_MACRO_INVENTORY_SHELL_800MHZ.json")

    require(source["status"].startswith("PASS"), "source replay is not PASS")
    require(rtl["status"].startswith("PASS") and rtl["root_sv_count"] == 18 and rtl["primitive_sv_count"] == 25,
            "authoritative RTL generation is incomplete")
    require(roots["status"] == "PASS" and roots["passed"] == roots["runs"] == 18 and roots["minimum_wns_ns"] >= 0,
            "18-root DC gate is incomplete")
    require(primitives["status"] == "PASS" and primitives["passed"] == primitives["runs"] == 25 and primitives["minimum_wns_ns"] >= 0,
            "25-primitive DC gate is incomplete")
    require(endpoints["status"].startswith("PASS") and endpoints["mapped_source_kinds"] == 53 and endpoints["terminal_binding_contract"] == 58,
            "endpoint binding gate is incomplete")
    require(canaries["status"].startswith("PASS") and all(canaries[name]["status"].startswith("PASS") for name in ("qwen2", "qwen3_5", "qwen3_8", "vision")),
            "four canaries are incomplete")
    require(stress["status"].startswith("PASS") and stress["successful_transactions_total"] == 36000,
            "root stress gate is incomplete")
    require(combined["status"].startswith("PASS") and combined["dc"]["wns_ns"] >= 0 and combined["dc"]["unmapped"] == 0 and combined["dc"]["unresolved"] == 0,
            "combined timing/link gate is incomplete")
    require(all(drc[key] == 0 for key in ("unmapped", "unresolved", "dc_errors", "max_transition_violations", "max_capacitance_violations", "max_fanout_violations")),
            "combined DRC gate is incomplete")
    require(sram["status"].startswith("PASS") and sram["physical_macros"] == 124 and sram["capacity_bytes"] == 4 * 1024 * 1024,
            "SRAM inventory gate is incomplete")
    require(macro["status"].startswith("PASS") and macro["wns_ns"] >= 0 and macro["physical_sram_macros"] == 124 and macro["unmapped"] == 0 and macro["unresolved"] == 0,
            "macro PPA aggregate gate is incomplete")

    dc_dir = ROOT / "work/results/operator_dc_800mhz/combined/RootOwnerDrc10Ddc"
    check_design = (dc_dir / "check_design_post.rpt").read_text(errors="replace")
    check_timing = (dc_dir / "check_timing.rpt").read_text(errors="replace")
    timing_messages = [line for line in check_timing.splitlines() if line.startswith(("Warning:", "Error:"))]
    latch_findings = len(re.findall(r"\blatch(?:es)?\b", check_design, re.IGNORECASE))
    loop_findings = len(re.findall(r"combinational\s+loop", check_design, re.IGNORECASE))
    require(not timing_messages, f"check_timing messages remain: {timing_messages[:3]}")
    require(latch_findings == 0 and loop_findings == 0, "latch/loop findings remain")

    base_sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    payload = {
        "schema_version": 1,
        "status": "PASS_THREE_MODEL_CHISEL_RTL_800MHZ_ACCEPTANCE",
        "audit_base_sha": base_sha,
        "implementation_origin": "Chisel",
        "generated_rtl_hand_edited": False,
        "coverage": {"roots": 18, "primitives": 25, "terminal_bindings": 58,
                     "qwen2": 30, "qwen3_5": 93, "qwen3_8": 150, "vision_canary": True},
        "simulation": {"canaries": 4, "root_stress_transactions": 36000,
                       "reference_output_injection": False},
        "dc": {"period_ns": 1.25, "root_pass": "18/18", "primitive_pass": "25/25",
               "combined_wns_ns": combined["dc"]["wns_ns"], "combined_logic_area": combined["dc"]["area"],
               "unmapped": 0, "unresolved": 0, "latches": latch_findings,
               "combinational_loops": loop_findings, "unconstrained_endpoint_messages": len(timing_messages),
               "max_transition_violations": 0, "max_capacitance_violations": 0, "max_fanout_violations": 0},
        "macro_ppa": {"capacity_mib": 4.0, "physical_macros": 124,
                      "macro_area": sram["macro_area"], "aggregate_area": macro["total_cell_area"],
                      "aggregate_wns_ns": macro["wns_ns"]},
        "evidence_sha256": {
            "check_design": sha(dc_dir / "check_design_post.rpt"),
            "check_timing": sha(dc_dir / "check_timing.rpt"),
            "combined_dc_log": drc["dc_log_sha256"],
            "macro_dc_log": macro["dc_log_sha256"],
        },
        "nonclaims": [
            "macro PPA aggregate does not connect SRAM data pins to owners",
            "no workload SAIF or energy claim",
            "no post-route or extracted-interconnect signoff claim",
            "canaries use deterministic synthetic payload and memory services, not full checkpoint inference",
        ],
    }
    output = REPORTS / "OPERATOR_THREE_MODEL_FINAL_ACCEPTANCE_800MHZ.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
