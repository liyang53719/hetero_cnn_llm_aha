#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/qwen2_kv_append_descriptor_v3_context}
RUN=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$OUT"
taskset -c 8-23 python3 "$ROOT/scripts/validate_qwen2_kv_ddr_layout.py" | tee "$OUT/layout.log"
taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_descriptor_macro_vectors.py" --packed-records "$ROOT/work/generated/qwen2_q1024_descriptor_image/packed_records.jsonl" --out "$OUT"
taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_kv_append_context_vectors.py" --manifest "$ROOT/reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl" --out "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 iverilog -g2012 -s tb_qwen2_kv_append_descriptor_v3_context -o "$OUT/tb" "$ROOT/rtl/kv/qwen2_kv_append_descriptor_v3_context.sv" "$ROOT/tb/tb_qwen2_kv_append_descriptor_v3_context.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 "$OUT/tb" +COMMAND="$OUT/kv_append_command.memh" +RECORDS="$OUT/records.memh" | tee "$OUT/tb.log"
grep -q 'QWEN2_KV_APPEND_DESCRIPTOR_V3_CONTEXT_PASS valid_fetches=13' "$OUT/tb.log"
