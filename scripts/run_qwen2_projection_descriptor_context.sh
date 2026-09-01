#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/qwen2_projection_descriptor_context};R=$ROOT/scripts/run_memory_capped.sh;V=${HETERO_VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT"
taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_descriptor_macro_vectors.py" --packed-records "$ROOT/work/generated/qwen2_q1024_descriptor_image/packed_records.jsonl" --out "$OUT"
taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_projection_context_vectors.py" --manifest "$ROOT/reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl" --chains "$ROOT/work/generated/qwen2_q1024_symbolic_descriptors/descriptor_chains.jsonl" --out "$OUT"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run 600s "$V" --binary --timing --assert -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH -Wno-SYNCASYNCNET -Wno-PROCASSINIT -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_qwen2_projection_descriptor_context --Mdir "$OUT/obj" -o tb "$ROOT/rtl/fabric/shared_l2_fabric.sv" "$ROOT/rtl/fabric/shared_l2_descriptor_port.sv" "$ROOT/rtl/integration/qwen2_projection_descriptor_context.sv" "$ROOT/tb/tb_qwen2_projection_descriptor_context.sv" >"$OUT/build.log" 2>&1
cd "$ROOT";run 600s "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'QWEN2_PROJECTION_DESCRIPTOR_CONTEXT_PASS commands=3' "$OUT/tb.log"
