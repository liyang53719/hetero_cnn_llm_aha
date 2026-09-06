#!/usr/bin/env bash
# Actual Chisel block regression. No generated RTL is edited or mixed with stale files.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(python3 -c 'from pathlib import Path;import sys;print(Path(sys.argv[1]).resolve())' "${1:?fresh OUT directory}")
PROFILE=${2:-tiny}; TOKENS=${3:-2}; BACKEND=${4:-retained}
[[ $PROFILE == tiny || $PROFILE == real ]] || { echo 'PROFILE must be tiny or real' >&2; exit 2; }
[[ $BACKEND == retained || $BACKEND == functional ]] || { echo 'BACKEND must be retained or functional' >&2; exit 2; }
[[ ! -e $OUT ]] || { echo "Refusing to overwrite $OUT" >&2; exit 2; };mkdir -p "$OUT"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
bash "$ROOT/chisel/continuous_prefill/scripts/prepare_hardfloat.sh" > "$OUT/hardfloat.log"
cd "$ROOT/chisel/continuous_prefill"
export MAKEFLAGS="${MAKEFLAGS:-} CFG_CXXFLAGS_PCH_I=-include"
git -C "$ROOT" rev-parse HEAD > "$OUT/source_commit.txt"
find src ../p0_safety/src/main/scala -type f -name '*.scala' -print0 | sort -z | xargs -0 sha256sum > "$OUT/sources.sha256"
sha256sum ../../integration/gemmini/EmitHeteroBF16Fma.scala ../../integration/gemmini/EmitHeteroFP32Alu.scala tests/qwen2_block.cpp build.sbt >> "$OUT/sources.sha256"
sbt -batch compile Test/compile 2>&1 | tee "$OUT/compile.log"
sbt -batch test 2>&1 | tee "$OUT/chiseltest.log"
PYTHONPATH="$ROOT/src" python3 -m pytest -q tests/test_memory_plan.py tests/test_pack_qwen2_block.py tests/test_block_summary.py | tee "$OUT/pytest.log"
OPTIONS=''; [[ $PROFILE != tiny ]] || OPTIONS='--tiny'
RETAINED_SOURCES=()
if [[ $BACKEND == retained ]]; then
 OPTIONS="$OPTIONS --retained"
 source scripts/retained_sources.sh
 sha256sum "${RETAINED_SOURCES[@]}" > "$OUT/retained_rtl.sha256"
fi
sbt -batch "runMain heteronpu.continuous.EmitQwenBlock $OUT/generated $OPTIONS" 2>&1 | tee "$OUT/emission.log"
verilator --version > "$OUT/verilator.txt"
verilator --cc --exe --build --assert -Wno-fatal --top-module Qwen2AxiBlockTop \
 -CFLAGS "-O2 -std=c++17 -ffp-contract=off -DBLOCK_AXI -I$OUT/generated" \
 -j "${BUILD_JOBS:-2}" --Mdir "$OUT/obj" "$OUT/generated/Qwen2AxiBlockTop.sv" "${RETAINED_SOURCES[@]}" "$PWD/tests/qwen2_block.cpp" \
 > "$OUT/verilator_build.log" 2>&1
BIN=$OUT/obj/VQwen2AxiBlockTop
if [[ $PROFILE == tiny ]]; then
 for count in ${BLOCK_SMOKE_COUNTS:-1 2 17 33}; do timeout "${RUN_TIMEOUT_SECONDS:-36000}" "$BIN" "$count" synthetic | tee "$OUT/tokens_${count}.log"; done
 for mode in repeat recover-write recover-tag bad-count bad-base; do timeout "${RUN_TIMEOUT_SECONDS:-36000}" "$BIN" 2 "$mode" | tee "$OUT/${mode}.log"; done
else
 timeout "${RUN_TIMEOUT_SECONDS:-86400}" "$BIN" "$TOKENS" synthetic | tee "$OUT/tokens_${TOKENS}.log"
fi
sha256sum --check "$OUT/sources.sha256" > "$OUT/source_immutability.log"
[[ $BACKEND != retained ]] || sha256sum --check "$OUT/retained_rtl.sha256" > "$OUT/retained_immutability.log"
python3 scripts/summarize_block_gate.py "$OUT" > "$OUT/SUMMARY.json"
cat "$OUT/SUMMARY.json"
