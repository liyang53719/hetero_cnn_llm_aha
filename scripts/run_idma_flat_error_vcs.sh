#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
IDMA=$ROOT/work/upstream/idma
OUT=$ROOT/work/results/idma_flat_error
test "$(df --output=avail -k "$ROOT" | tail -1)" -gt 52428800
[[ $(git -C "$IDMA" rev-parse HEAD) == 2e0b0fe53b6f8823319e2428e2e9abc2db149b7d ]]
[[ -z $(git -C "$IDMA" status --porcelain) ]]
AXI_INC=$(find "$IDMA/.bender/git/checkouts" -maxdepth 2 -path '*/axi-*/include' | head -n1)
mkdir -p "$OUT"
cd "$IDMA/target/sim/vcs"
run() { MIN_AVAILABLE_KIB=10485760 "$ROOT/scripts/run_memory_capped.sh" timeout 600 "$@"; }
run vlogan -sverilog -full64 +incdir+../../../src/include +incdir+"$AXI_INC" \
 "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$ROOT/tb/tb_idma_flat_error.sv" >"$OUT/vlogan.log" 2>&1
run vcs -full64 -top tb_idma_flat_error -o simv_flat_error >"$OUT/vcs.log" 2>&1
run ./simv_flat_error | tee "$OUT/test.log"
grep -q 'IDMA_FLAT_ERROR_PASS' "$OUT/test.log"
