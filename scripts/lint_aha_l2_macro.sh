#!/usr/bin/env bash
# Compile-check the complete generated AHA macro closure with Verilator.
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-"$PROJECT_ROOT/work/generated/l2_aha_garnet_4x16"}
VERILATOR=${AHA_L2_VERILATOR:-"$PROJECT_ROOT/work/toolchain/conda/bin/verilator"}

test -f "$OUT/interconnect_port_manifest.json" || {
  echo "generate the AHA L2 macro before linting" >&2
  exit 2
}
test -f "$OUT/upstream_compile_closure.f" || {
  echo "generated AHA compile closure is missing" >&2
  exit 2
}
test -x "$VERILATOR" || { echo "Verilator is missing: $VERILATOR" >&2; exit 2; }

python3 "$PROJECT_ROOT/scripts/generate_sv_port_contract_tb.py" \
  "$OUT/interconnect_port_manifest.json" --output "$OUT/tb_interconnect_port_contract.sv"
(
  cd "$OUT"
  "$VERILATOR" --lint-only --timing -Wno-fatal \
    -Wno-PINMISSING -Wno-TIMESCALEMOD -Wno-WIDTHTRUNC \
    -f upstream_compile_closure.f tb_interconnect_port_contract.sv \
    --top-module tb_generated_port_contract
) > "$OUT/verilator_port_contract.log" 2>&1

python3 - "$OUT" <<'PY'
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
macro = json.loads((out / "result.json").read_text())
result = {
    "status": "PASS",
    "scope": "generated AHA Interconnect complete named-port and dependency-closure lint only",
    "module": macro["module"],
    "port_count": macro["port_count"],
    "rtl_sha256": macro["rtl_sha256"],
    "collateral_file_count": macro["collateral_file_count"],
    "tool": "Verilator lint-only",
}
(out / "port_contract_lint_result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, sort_keys=True))
PY

echo AHA_L2_PORT_CONTRACT_LINT_PASS
