#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);UP=$ROOT/work/upstream/llama_cpp;BUILD=$ROOT/work/results/llama_cpp_pinned_build/bin;INPUT=$ROOT/work/results/qwen2_q1024_full28_inputs;OUT=${OUT:-$ROOT/work/results/ggml_hetero_backend_smoke};RUN=$ROOT/scripts/run_memory_capped.sh;mkdir -p "$INPUT" "$OUT"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@";}
[[ $(git -C "$UP" rev-parse HEAD) == 0b5be7e4a25862bc2777d0c47eae18788a8c963a ]];[[ -z $(git -C "$UP" status --porcelain) ]]
run 600s python3 "$ROOT/scripts/generate_qwen2_q1024_group0_inputs.py" --start-layer 0 --end-layer 27 --out "$INPUT"|tee "$OUT/input.log"
run 600s /usr/bin/g++ -std=c++20 -O3 -march=native -fopenmp -ffp-contract=off -Wno-return-type -I"$ROOT/src" -I"$UP/ggml/include" -I"$UP/ggml/src" "$ROOT/src/hetero_qwen2_device_api.cpp" "$ROOT/src/ggml_hetero_backend.cpp" "$ROOT/cpp/ggml_hetero_backend_smoke.cpp" -L"$BUILD" -Wl,-rpath,"$BUILD" -lggml -lggml-base -lggml-cpu -pthread -ldl -o "$OUT/smoke"
run 600s env OMP_NUM_THREADS=8 OMP_PROC_BIND=true "$OUT/smoke" "$INPUT" "$OUT/payload"|tee "$OUT/run.log"
