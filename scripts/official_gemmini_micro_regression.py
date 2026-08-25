#!/usr/bin/env python3
"""Exercise an independently generated official Gemmini primitive.

This is deliberately narrower than a RocketTile/RoCC regression: the
generated MacUnit is a combinational official Gemmini artifact that can be
verified without fabricating PTW/TileLink endpoints.  The full generated
Gemmini boundary is audited separately in OFFICIAL_GEMMINI_INTERFACE_AUDIT.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "work/upstream/chipyard_gemmini/sims/verilator/generated-src/chipyard.harness.TestHarness.GemminiRocketConfig/gen-collateral"
OUT = ROOT / "work/results/official_gemmini_micro_regression"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/official_gemmini_micro_regression.json")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    dut = GEN / "MacUnit.sv"
    binary = OUT / "tb_official_gemmini_mac_unit"
    compile_log = OUT / "compile.log"
    run_log = OUT / "run.log"
    result: dict[str, object] = {
        "status": "BLOCKED_MISSING_GENERATED_COLLATERAL",
        "dut": str(dut),
        "scope": "official generated Gemmini MacUnit exhaustive int8/int8/20-bit accumulator smoke",
    }
    if not dut.exists():
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
        return 1

    compile_cmd = [
        "taskset", "-c", "8-25", "iverilog", "-g2012", "-s",
        "tb_official_gemmini_mac_unit", "-o", str(binary),
        str(ROOT / "tb/tb_official_gemmini_mac_unit.sv"), str(dut),
    ]
    compiled = subprocess.run(compile_cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    compile_log.write_text(compiled.stdout, encoding="utf-8")
    if compiled.returncode != 0:
        result.update({"status": "FAIL_COMPILE", "returncode": compiled.returncode})
    else:
        ran = subprocess.run(["taskset", "-c", "8-25", "vvp", str(binary)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        run_log.write_text(ran.stdout, encoding="utf-8")
        result.update({
            "status": "PASS" if ran.returncode == 0 and "OFFICIAL_GEMMINI_MACUNIT_PASS checks=327680" in ran.stdout else "FAIL_SIMULATION",
            "returncode": ran.returncode,
            "checks": 327680 if "OFFICIAL_GEMMINI_MACUNIT_PASS checks=327680" in ran.stdout else 0,
        })
    result["artifacts"] = {"compile_log": str(compile_log), "run_log": str(run_log)}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
