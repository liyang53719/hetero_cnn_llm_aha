#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);MODEL=${MODEL:-$ROOT/work/models/qwen2_1p5b_instruct_ba1cf184};GGUF=${GGUF:-$ROOT/work/models/gguf/qwen2-1.5b-instruct-ba1cf184-bf16.gguf};BUILD=${BUILD:-$ROOT/work/results/llama_cpp_pinned_build};OUT=${OUT:-$ROOT/work/results/llama_cpp_qwen2_baseline};R=$ROOT/scripts/run_memory_capped.sh;mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s python3 "$ROOT/scripts/generate_qwen2_llama_baseline_reference.py" --model "$MODEL" --out "$OUT"|tee "$OUT/pytorch.log"
taskset -c 8-23 /usr/bin/g++ -std=c++17 -O2 -Wall -Wextra -Werror "$ROOT/cpp/llama_qwen2_logits.cpp" -I"$ROOT/work/upstream/llama_cpp/include" -I"$ROOT/work/upstream/llama_cpp/ggml/include" -L"$BUILD/bin" -Wl,-rpath,"$BUILD/bin" -lllama -lggml -lggml-base -lggml-cpu -pthread -ldl -fopenmp -o "$OUT/llama_qwen2_logits"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$OUT/llama_qwen2_logits" "$GGUF" "$OUT/tokens.txt" "$OUT/llama_logits.bin" "$OUT/graph.tsv"|tee "$OUT/llama.log"
taskset -c 8-23 python3 "$ROOT/scripts/compare_qwen2_llama_logits.py" --reference "$OUT/pytorch_logits.bin" --llama "$OUT/llama_logits.bin" --output "$OUT/result.json"
