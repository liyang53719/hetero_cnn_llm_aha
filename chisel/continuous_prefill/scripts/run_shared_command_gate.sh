#!/usr/bin/env bash
# Real original iDMA, actual SFU and existing Command128/typed records.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd); P="$ROOT/chisel/continuous_prefill"
PROFILE=${1:?usage: run_shared_command_gate.sh commands|tiny|tail|real /absolute/new/output [tokens]}
OUT=${2:?absolute new output}; TOKENS=${3:-16}
[[ "$PROFILE" = commands || "$PROFILE" = tiny || "$PROFILE" = tail || "$PROFILE" = real ]] || exit 2
[[ "$OUT" = /* && ! -e "$OUT" && "$TOKENS" =~ ^[0-9]+$ && "$TOKENS" -ge 1 && "$TOKENS" -le 1024 ]] || exit 2
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA >&2; exit 77; }
for t in java g++ python3 git; do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL: $t" >&2; exit 77; }; done
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
  export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin" VERILATOR_ROOT="$OFFLINE_TOOLS/share/verilator" PATH="$OFFLINE_TOOLS/bin:$PATH"
else
  command -v sbt >/dev/null || { echo BLOCKED_MISSING_SBT >&2; exit 77; }
fi
command -v verilator >/dev/null || { echo BLOCKED_MISSING_VERILATOR >&2; exit 77; }
mkdir -p "$OUT"
trap 'code=$?; printf "%s\n" "$code" >"$OUT/gate.exit"; exit "$code"' EXIT
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare_hardfloat.log" 2>&1
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
git -C "$ROOT" rev-parse HEAD >"$OUT/source_base_commit.txt"
git -C "$ROOT" status --porcelain >"$OUT/worktree_before.txt"
verilator --version >"$OUT/verilator.txt";java -version 2>"$OUT/java.txt";g++ --version >"$OUT/cxx.txt"
# Portable across Verilator packages whose exported PCH was configured with a
# different compiler. Disable inclusion of PCH; do not edit generated C++ or SV.
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O3"
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
  python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
  java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$OUT/classes:$(cat "$OUT/classpath.txt")" heteronpu.continuous.EmitSharedProductionGate "$OUT/generated" "$PROFILE" >"$OUT/emit.log" 2>&1
else
  (cd "$P"; sbt -batch compile "runMain heteronpu.continuous.EmitSharedProductionGate $OUT/generated $PROFILE") >"$OUT/compile_emit.log" 2>&1
fi
if [[ "$PROFILE" = commands ]]; then
  TOP=HostResidualIdmaTop; CPP="$P/tests/host_command_idma.cpp"; EXTRA=(); FLAGS=""
else
  TOP=Qwen2SharedProductionTop; CPP="$P/tests/shared_production_commands.cpp"
  export RETAINED_SKIP_CLOCK=0; source "$P/scripts/retained_sources.sh"
  EXTRA=(--hierarchical "$P/tests/retained_hierarchy.vlt" "${RETAINED_SOURCES[@]}")
  FLAGS="-DBLOCK_COMMON -DBLOCK_AXI -DBLOCK_IDMA"
fi
verilator --cc --exe --build --assert -Wno-fatal --top-module "$TOP" \
  -CFLAGS "-O3 -std=c++17 -ffp-contract=off -fno-fast-math $FLAGS -I$OUT/generated -I$P/tests" \
  -j "${BUILD_JOBS:-3}" --Mdir "$OUT/obj" "${EXTRA[@]}" -f "$OUT/idma.f" \
  "$OUT/generated/$TOP.sv" "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$CPP" >"$OUT/build.log" 2>&1
set +e
PRODUCTION_EVIDENCE_DIR="$OUT/tensors" "$OUT/obj/V$TOP" "$TOKENS" >"$OUT/run.log" 2>&1
code=$?;set -e
printf '%s\n' "$code" >"$OUT/simulation.exit";cat "$OUT/run.log";((code==0)) || exit "$code"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
# Full numerical and source-identity evidence is independently admitted by the
# companion verifier, never by a substring-only PASS decision.
python3 "$P/scripts/verify_shared_command_gate.py" "$OUT" "$PROFILE" --tokens "$TOKENS" >"$OUT/verification.log"
cat "$OUT/verification.log"
