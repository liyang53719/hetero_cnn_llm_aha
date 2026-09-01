#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
IDMA=${IDMA_ROOT:-$ROOT/work/upstream/idma}
VD=$IDMA/target/sim/vcs
OUT=${OUT:-$ROOT/work/results/qwen2_kv_append_pinned_idma_vcs}
RUN=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$OUT"
[[ $(git -C "$IDMA" rev-parse HEAD) == 2e0b0fe53b6f8823319e2428e2e9abc2db149b7d ]]
[[ -z $(git -C "$IDMA" status --porcelain) ]]
CTX=$ROOT/work/results/qwen2_kv_append_descriptor_v3_context
[[ -s "$CTX/kv_append_command.memh" && -s "$CTX/records.memh" ]]
AXI_INC=$(find "$IDMA/.bender/git/checkouts" -maxdepth 2 -path '*/axi-*/include' | head -n1)
cd "$VD"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@";}
S=("$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$ROOT/rtl/kv/qwen2_kv_append_descriptor_v3_context.sv" "$ROOT/rtl/kv/qwen2_kv_append_ddr_page_core.sv" "$ROOT/rtl/kv/qwen2_kv_append_ddr_stage_top.sv" "$ROOT/tb/tb_qwen2_kv_append_pinned_idma_vcs.sv")
run 600s vlogan -sverilog -full64 +define+USE_UPSTREAM_IDMA +incdir+../../../src/include +incdir+"$AXI_INC" +incdir+"$ROOT" "${S[@]}" >"$OUT/vlogan.log" 2>&1
run 600s vcs -full64 -top tb_qwen2_kv_append_pinned_idma_vcs -o simv_qwen2_kv_append >"$OUT/vcs.log" 2>&1
run 600s ./simv_qwen2_kv_append +COMMAND="$CTX/kv_append_command.memh" +RECORDS="$CTX/records.memh" | tee "$OUT/tb.log"
grep -q 'QWEN2_KV_APPEND_PINNED_IDMA_VCS_PASS commands=1 descriptor_fetches=13' "$OUT/tb.log"
