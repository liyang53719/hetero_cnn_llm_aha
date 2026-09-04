#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
IDMA=${IDMA_ROOT:-$ROOT/work/upstream/idma}
VCS_DIR=$IDMA/target/sim/vcs
OUT=$ROOT/work/results/operator_dma_pinned_idma_v3
R=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$OUT"
[[ $(git -C "$IDMA" rev-parse HEAD) == 2e0b0fe53b6f8823319e2428e2e9abc2db149b7d ]]
[[ -z $(git -C "$IDMA" status --porcelain) ]]
[[ -d "$VCS_DIR/AN.DB" ]]
AXI_INC=$(find "$IDMA/.bender/git/checkouts" -maxdepth 2 -path '*/axi-*/include'|head -n1)
cd "$VCS_DIR"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run 600s vlogan -sverilog -full64 +define+USE_UPSTREAM_IDMA +incdir+../../../src/include +incdir+"$AXI_INC" \
  "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" \
  "$ROOT/rtl/integration/qwen2_tile_idma_expand.sv" \
  "$ROOT/rtl/integration/operator_dma_endpoint_v3.sv" \
  "$ROOT/tb/tb_operator_dma_pinned_idma_v3.sv" >"$OUT/vlogan.log" 2>&1
run 600s vcs -full64 -top tb_operator_dma_pinned_idma_v3 -o simv_operator_dma_v3 >"$OUT/vcs.log" 2>&1
run 600s ./simv_operator_dma_v3 | tee "$OUT/test.log"
grep -q 'OPERATOR_DMA_PINNED_IDMA_V3_PASS' "$OUT/test.log"
