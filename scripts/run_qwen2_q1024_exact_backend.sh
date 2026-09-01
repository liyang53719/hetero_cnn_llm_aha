#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);IN=$ROOT/work/results/qwen2_q1024_backend_inputs;OUT=${OUT:-$ROOT/work/results/qwen2_q1024_exact_backend};RUN=$ROOT/scripts/run_memory_capped.sh;mkdir -p "$IN" "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_q1024_backend_inputs.py"|tee "$OUT/input.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 g++ -std=c++20 -O3 -march=native -fopenmp -ffp-contract=off "$ROOT/src/qwen2_q1024_exact_backend.cpp" -o "$OUT/backend"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 env OMP_NUM_THREADS=8 OMP_PROC_BIND=true "$OUT/backend" "$IN" "$OUT"|tee "$OUT/run.log"
taskset -c 8-23 python3 "$ROOT/scripts/collect_qwen2_q1024_exact_backend.py"
