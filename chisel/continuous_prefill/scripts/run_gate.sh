#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:?use a fresh evidence directory}
if [[ -e $OUT ]]; then echo 'Refusing to overwrite an earlier evidence directory' >&2; exit 2; fi
mkdir -p "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} CFG_CXXFLAGS_PCH_I=-include"
sbt -batch compile Test/compile | tee "$OUT/compile.log"
sbt -batch test | tee "$OUT/test.log"
sbt -batch "runMain heteronpu.continuous.EmitContinuous $OUT/generated_ci" | tee "$OUT/emit.log"
verilator --cc --exe --build --assert -Wno-fatal --top-module ContinuousElementwiseTop \
  -CFLAGS '-O2 -std=c++17 -ffp-contract=off' -j 4 --Mdir "$PWD/$OUT/obj" \
  "$OUT/generated_ci/ContinuousElementwiseTop.sv" "$PWD/tests/continuous_memory.cpp" > "$OUT/verilator_build.log" 2>&1
for count in 1 17 33 1025 32768 1572864 2097152 2621440;do
  timeout 600 "$OUT/obj/VContinuousElementwiseTop" "$count" | tee "$OUT/n${count}.log"
done
timeout 120 "$OUT/obj/VContinuousElementwiseTop" 1025 fail | tee "$OUT/memory_failure.log"
