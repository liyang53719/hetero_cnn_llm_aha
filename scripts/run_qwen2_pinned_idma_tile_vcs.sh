#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);IDMA=${IDMA_ROOT:-$ROOT/work/upstream/idma};VCS_DIR=$IDMA/target/sim/vcs
OUT=${OUT:-$ROOT/work/results/qwen2_pinned_idma_tile};R=$ROOT/scripts/run_memory_capped.sh;mkdir -p "$OUT"
[[ $(git -C "$IDMA" rev-parse HEAD) == 2e0b0fe53b6f8823319e2428e2e9abc2db149b7d ]];[[ -z $(git -C "$IDMA" status --porcelain) ]];[[ -d "$VCS_DIR/AN.DB" ]]
taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_descriptor_context_vectors.py" --manifest "$ROOT/reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl" --chains "$ROOT/work/generated/qwen2_q1024_symbolic_descriptors/descriptor_chains.jsonl" --out "$OUT"
AXI_INC=$(find "$IDMA/.bender/git/checkouts" -maxdepth 2 -path '*/axi-*/include'|head -n1);cd "$VCS_DIR"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@";}
run 600s vlogan -sverilog -full64 +define+USE_UPSTREAM_IDMA +incdir+../../../src/include +incdir+"$AXI_INC" "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$ROOT/rtl/integration/qwen2_tile_idma_expand.sv" "$ROOT/tb/tb_qwen2_tile_idma_expand.sv" >"$OUT/vlogan.log" 2>&1
run 600s vcs -full64 -top tb_qwen2_tile_idma_expand -o simv_qwen2_tile >"$OUT/vcs.log" 2>&1
run 600s ./simv_qwen2_tile +ADDR_MEM="$OUT/addresses.memh"|tee "$OUT/tb.log"
grep -q 'QWEN2_PINNED_IDMA_TILE_PASS abstract_requests=4 flat_requests=1539' "$OUT/tb.log"
