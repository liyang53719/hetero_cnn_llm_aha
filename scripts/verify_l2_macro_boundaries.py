#!/usr/bin/env python3
"""Verify immutable L2 macro boundaries without pretending to integrate them.

The check proves that the generated Gemmini artifact is still the exact L1
artifact and that its official RocketTile context is present.  It deliberately
does not compile a standalone Gemmini: tying off PTW or TileLink would create a
non-equivalent macro test and is forbidden by the L2 contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GEMMINI_DIR = ROOT / "work/upstream/chipyard_gemmini/sims/verilator/generated-src/chipyard.harness.TestHarness.GemminiRocketConfig/gen-collateral"
EXPECTED_FAMILIES = {
    "lifecycle": 4,
    "ptw": 80,
    "rocc_cmd": 49,
    "rocc_resp": 4,
    "tilelink_spad": 20,
}


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ROOT / "work/results/l2_wrapper_freeze/gemmini_boundary_result.json")
    args = parser.parse_args()

    lock = json.loads((ROOT / "reports/execution/gemmini_macro_contract_lock.json").read_text())
    manifest = json.loads((ROOT / "reports/execution/gemmini_port_manifest.json").read_text())
    gemmini_sv = GEMMINI_DIR / "Gemmini.sv"
    rocket_tile_sv = GEMMINI_DIR / "RocketTile.sv"
    if not gemmini_sv.is_file() or not rocket_tile_sv.is_file():
        fail("canonical generated Gemmini/RocketTile collateral is missing")

    source_hash = hashlib.sha256(gemmini_sv.read_bytes()).hexdigest()
    if source_hash != lock["gemmini_sv_sha256"]:
        fail(f"Gemmini.sv hash drift: got {source_hash}, expected {lock['gemmini_sv_sha256']}")
    if manifest["module"] != "Gemmini" or manifest["port_count"] != 157:
        fail("Gemmini port manifest no longer identifies the expected 157-port macro")
    if manifest["family_counts"] != EXPECTED_FAMILIES:
        fail(f"Gemmini port families drifted: {manifest['family_counts']}")

    rocket = rocket_tile_sv.read_text(encoding="utf-8")
    required = [
        "Gemmini gemmini (",
        ".io_cmd_valid                    (_cmdRouter_io_out_0_valid)",
        ".io_ptw_0_req_valid",
        ".auto_spad_id_out_a_valid",
        ".io_resp_valid",
    ]
    missing = [token for token in required if token not in rocket]
    if missing:
        fail(f"RocketTile no longer supplies required Gemmini context: {missing}")

    legacy_adapter = (ROOT / "rtl/integration/gemmini_rocc_command_adapter.sv").read_text(encoding="utf-8")
    if "does not instantiate" not in legacy_adapter or "RocketTile" not in legacy_adapter:
        fail("legacy clean-room adapter lost its non-macro scope marker")
    if re.search(r"\bGemmini\s+[A-Za-z_][A-Za-z0-9_$]*\s*\(", legacy_adapter):
        fail("legacy adapter must not instantiate generated Gemmini without its RocketTile context")
    program_adapter = (ROOT / "rtl/integration/gemmini_rocc_program_adapter.sv").read_text(encoding="utf-8")
    for token in ("CUSTOM_3", "rocc_busy_i", "S_WAIT_BUSY_CLEAR", "op_legal_i"):
        if token not in program_adapter:
            fail(f"program adapter lost required macro-boundary behavior: {token}")
    if "rocc_resp" in program_adapter:
        fail("program adapter must not treat Gemmini response as generic completion")
    production = (ROOT / "rtl/integration/hetero_npu_gemmini_rocc_integration_v0.sv").read_text(encoding="utf-8")
    for token in ("gemmini_descriptor_sequencer", "gemmini_rocc_program_adapter",
                  "descriptor_req_index_o", "descriptor_rsp_error_i"):
        if token not in production:
            fail(f"production integration lost approved descriptor path: {token}")
    if "gemmini_rocc_command_adapter u_gemmini_rocc" in production:
        fail("production integration regressed to the legacy CUSTOM_0 adapter")
    sequencer = (ROOT / "rtl/integration/gemmini_descriptor_sequencer.sv").read_text(encoding="utf-8")
    for token in ("NULL_INDEX", "MAX_RECORDS", "duplicate_index",
                  "descriptor_req_byte_addr_o", "S_VALIDATE"):
        if token not in sequencer:
            fail(f"descriptor sequencer lost approved pre-issue behavior: {token}")

    result = {
        "status": "PASS",
        "scope": "Gemmini macro boundary freeze plus approved typed-descriptor/CUSTOM_3 production path",
        "chipyard_commit": lock["chipyard_commit"],
        "gemmini_commit": lock["gemmini_commit"],
        "gemmini_sv_sha256": source_hash,
        "port_count": manifest["port_count"],
        "family_counts": manifest["family_counts"],
        "rocket_context": "cmdRouter + PTW + TileLink + response arbiter present",
        "program_completion": "last command accepted, busy asserted, then busy cleared",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
