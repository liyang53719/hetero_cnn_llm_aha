#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);UP=$ROOT/work/upstream/llama_cpp;BUILD=$ROOT/work/results/llama_cpp_pinned_build/bin;INPUT=$ROOT/work/results/qwen2_q1024_full28_inputs;GGUF=${GGUF:-$ROOT/work/models/gguf/qwen2-1.5b-instruct-ba1cf184-bf16.gguf};TOKENS=$ROOT/work/results/llama_cpp_qwen2_baseline/tokens.txt;OUT=${OUT:-$ROOT/work/results/llama_hetero_full_graph};RUN=$ROOT/scripts/run_memory_capped.sh;mkdir -p "$INPUT" "$OUT"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@";}
[[ $(git -C "$UP" rev-parse HEAD) == 0b5be7e4a25862bc2777d0c47eae18788a8c963a ]];[[ -z $(git -C "$UP" status --porcelain) ]]
run 600s python3 "$ROOT/scripts/generate_qwen2_q1024_group0_inputs.py" --start-layer 0 --end-layer 27 --out "$INPUT"|tee "$OUT/input.log"
run 600s /usr/bin/g++ -std=c++20 -O3 -march=native -fopenmp -ffp-contract=off -Wno-return-type -fPIC -shared -DGGML_BACKEND_DL -DGGML_BACKEND_BUILD -I"$ROOT/src" -I"$UP/ggml/include" -I"$UP/ggml/src" "$ROOT/src/hetero_qwen2_device_api.cpp" "$ROOT/src/ggml_hetero_backend.cpp" -L"$BUILD" -Wl,-rpath,"$BUILD" -lggml -lggml-base -lggml-cpu -pthread -ldl -o "$OUT/libggml-hetero.so"
run 600s /usr/bin/g++ -std=c++20 -O2 -I"$UP/include" -I"$UP/ggml/include" "$ROOT/cpp/llama_hetero_full_graph.cpp" -L"$BUILD" -Wl,-rpath,"$BUILD" -lllama -lggml -lggml-base -lggml-cpu -pthread -ldl -o "$OUT/full_graph"
run 600s env OMP_NUM_THREADS=8 OMP_PROC_BIND=true "$OUT/full_graph" "$OUT/libggml-hetero.so" "$GGUF" "$INPUT" "$OUT/payload" "$TOKENS" "$OUT/logits.bin"|tee "$OUT/run.log"
