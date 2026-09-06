#!/usr/bin/env bash
# Chisel -> original Matrix/pinned iDMA -> AXI DDR -> continuous block proof.
# No generated or retained SystemVerilog is modified. Preserve every output.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill"
PROFILE=${1:?usage: run_production_chain_gate.sh tiny|tail|real /absolute/new/output [tokens]}
OUT=${2:?absolute new output directory required}
TOKENS=${3:-16}
[[ "$PROFILE" = tiny || "$PROFILE" = tail || "$PROFILE" = real ]] || { echo 'invalid profile' >&2; exit 2; }
[[ "$OUT" = /* && ! -e "$OUT" && "$TOKENS" =~ ^[0-9]+$ && "$TOKENS" -ge 1 && "$TOKENS" -le 1024 ]] || { echo 'invalid output/token count' >&2; exit 2; }
: "${IDMA_EXPORT:?set IDMA_EXPORT to the verified pinned idma_export directory}"
for t in java g++ python3 git; do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL: $t" >&2; exit 77; }; done
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
  export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin" VERILATOR_ROOT="$OFFLINE_TOOLS/share/verilator"
  export PATH="$OFFLINE_TOOLS/bin:$PATH"
else
  command -v sbt >/dev/null || { echo BLOCKED_MISSING_SBT >&2; exit 77; }
fi
command -v verilator >/dev/null || { echo BLOCKED_MISSING_VERILATOR >&2; exit 77; }
mkdir -p "$OUT"
trap 'code=$?; printf "%s\n" "$code" >"$OUT/gate.exit"; exit "$code"' EXIT
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
if [[ ! -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]]; then bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare_hardfloat.log" 2>&1; fi
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/prepare_idma.log"
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
git -C "$ROOT" rev-parse HEAD >"$OUT/source_base_commit.txt"
git -C "$ROOT" status --porcelain >"$OUT/worktree_before.txt"
java -version 2>"$OUT/java.txt";verilator --version >"$OUT/verilator.txt";g++ --version >"$OUT/cxx.txt"
export MAKEFLAGS="${MAKEFLAGS:-} CFG_CXXFLAGS_PCH_I=-include OPT_FAST=-O3"
export JVM_OPTS=${JVM_OPTS:--Xmx3G -Xss4M -XX:ActiveProcessorCount=3}
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
  python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
  CP=$(cat "$OUT/classpath.txt")
  java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$OUT/classes:$CP" heteronpu.continuous.EmitProductionGate "$OUT/generated" "$PROFILE" >"$OUT/emit.log" 2>&1
else
  (cd "$P"; sbt -batch compile) >"$OUT/compile.log" 2>&1
  printf '0\n' >"$OUT/compile.exit"
  (cd "$P"; sbt -batch "runMain heteronpu.continuous.EmitProductionGate $OUT/generated $PROFILE") >"$OUT/emit.log" 2>&1
fi
printf '0\n' >"$OUT/emit.exit"
# The Bender ASIC list omits tc_clk.sv; retained_sources.sh adds its pinned ICG.
export RETAINED_SKIP_CLOCK=0
source "$P/scripts/retained_sources.sh"
verilator --cc --exe --build --assert --hierarchical -Wno-fatal --top-module Qwen2IdmaBlockTop \
  -CFLAGS "-O3 -std=c++17 -ffp-contract=off -fno-fast-math -DBLOCK_AXI -DBLOCK_IDMA -I$OUT/generated" \
  -j "${BUILD_JOBS:-3}" --Mdir "$OUT/obj" "$P/tests/retained_hierarchy.vlt" -f "$OUT/idma.f" \
  "$OUT/generated/Qwen2IdmaBlockTop.sv" "${RETAINED_SOURCES[@]}" \
  "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$P/tests/qwen2_block.cpp" >"$OUT/build.log" 2>&1
printf '0\n' >"$OUT/build.exit"
set +e
PRODUCTION_EVIDENCE_DIR="$OUT/tensors" "$OUT/obj/VQwen2IdmaBlockTop" "$TOKENS" synthetic 20260906 >"$OUT/run.log" 2>&1
code=$?
set -e
printf '%s\n' "$code" >"$OUT/simulation.exit";cat "$OUT/run.log"
((code==0)) || exit "$code"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 "$P/scripts/verify_production_chain.py" "$OUT" "$PROFILE" --tokens "$TOKENS" >"$OUT/verification.log"
cat "$OUT/verification.log"
