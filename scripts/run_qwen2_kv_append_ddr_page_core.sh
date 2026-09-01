#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/qwen2_kv_append_ddr_page_core}
RUN=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 iverilog -g2012 -s tb_qwen2_kv_append_ddr_page_core -o "$OUT/tb" "$ROOT/rtl/kv/qwen2_kv_append_ddr_page_core.sv" "$ROOT/tb/tb_qwen2_kv_append_ddr_page_core.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 "$OUT/tb" | tee "$OUT/tb.log"
grep -q 'QWEN2_KV_APPEND_DDR_PAGE_CORE_PASS pte_updates=65' "$OUT/tb.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 iverilog -g2012 -s tb_qwen2_kv_append_ddr_stage_top -o "$OUT/stage_tb" "$ROOT/rtl/kv/qwen2_kv_append_descriptor_v3_context.sv" "$ROOT/rtl/kv/qwen2_kv_append_ddr_page_core.sv" "$ROOT/rtl/kv/qwen2_kv_append_ddr_stage_top.sv" "$ROOT/tb/tb_qwen2_kv_append_ddr_stage_top.sv" >"$OUT/stage_build.log" 2>&1
CTX=$ROOT/work/results/qwen2_kv_append_descriptor_v3_context
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 "$OUT/stage_tb" +COMMAND="$CTX/kv_append_command.memh" +RECORDS="$CTX/records.memh" | tee "$OUT/stage_tb.log"
grep -q 'QWEN2_KV_APPEND_DDR_STAGE_TOP_PASS commands=1 descriptor_fetches=13' "$OUT/stage_tb.log"
