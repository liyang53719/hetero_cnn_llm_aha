#!/usr/bin/env bash
# Full original 21-op sequence, not a block launch followed by test Adds.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
PROFILE=${1:?tiny|real};OUT=${2:?absolute new directory};TOKENS=${3:-16};RELOCATE=${4:-0};LAYERS=${5:-1};MATRIX_MACS=${MATRIX_MACS:-4096};WEIGHT_READ_BEATS=${WEIGHT_READ_BEATS:-1};PIPELINED_OWNER=${PIPELINED_OWNER:-0}
[[ "$MATRIX_MACS" = 512 || "$MATRIX_MACS" = 4096 ]] || exit 2
[[ "$WEIGHT_READ_BEATS" = 1 || "$WEIGHT_READ_BEATS" = 16 ]] || exit 2
[[ "$PIPELINED_OWNER" = 0 || "$PIPELINED_OWNER" = 1 ]] || exit 2
[[ "$PIPELINED_OWNER" = 0 || ( "$MATRIX_MACS" = 4096 && "$WEIGHT_READ_BEATS" = 16 ) ]] || exit 2
[[ "$PROFILE" = tiny || "$PROFILE" = real ]] || exit 2
[[ "$LAYERS" =~ ^[123]$ && "$TOKENS" =~ ^[1-9][0-9]{0,3}$ && "$RELOCATE" =~ ^[0-9]{1,17}$ ]] || exit 2
((10#$TOKENS<=1024)) || exit 2
[[ "$OUT" = /* && ! -e "$OUT" ]] || exit 2
for t in java g++ python3 git;do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$t";exit 77; };done
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA;exit 77; }
mkdir -p "$OUT";trap 'code=$?;echo "$code" >"$OUT/gate.exit";exit "$code"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O3"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/hardfloat_prepare.log" 2>&1
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
git -C "$ROOT" rev-parse HEAD >"$OUT/source_base_commit.txt"
if [[ -n ${OFFLINE_TOOLS:-} ]];then
  export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
  python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
  java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$OUT/classes:$(cat "$OUT/classpath.txt")" heteronpu.continuous.EmitHostBlock "$OUT/generated" "$PROFILE" "$MATRIX_MACS" "$WEIGHT_READ_BEATS" "$PIPELINED_OWNER" >"$OUT/emit.log" 2>&1
else
  (cd "$P";sbt -batch compile "runMain heteronpu.continuous.EmitHostBlock $OUT/generated $PROFILE $MATRIX_MACS $WEIGHT_READ_BEATS $PIPELINED_OWNER") >"$OUT/compile_emit.log" 2>&1
fi
if [[ "$LAYERS" = 1 ]];then
  python3 "$P/scripts/pack_owner_block_fixture.py" "$OUT/generated/owner_shape.h" "$OUT/fixture" --tokens "$TOKENS" --relocate "$RELOCATE" >"$OUT/packing.log"
else
  python3 "$P/scripts/pack_owner_multilayer_fixture.py" "$OUT/generated/owner_shape.h" "$OUT/fixture" --tokens "$TOKENS" --layers "$LAYERS" --relocate "$RELOCATE" >"$OUT/packing.log"
fi
HIERARCHY="$P/tests/retained_hierarchy.vlt"
if [[ "$MATRIX_MACS" = 4096 ]];then HIERARCHY="$P/tests/matrix4096_hierarchy.vlt";fi
export RETAINED_SKIP_CLOCK=0;source "$P/scripts/retained_sources.sh"
verilator --cc --exe --build --assert -Wno-fatal --top-module HostBlockTop \
 -CFLAGS "-O3 -std=c++17 -ffp-contract=off -fno-fast-math -I$OUT/generated -I$OUT/fixture" \
 -j "${BUILD_JOBS:-3}" --Mdir "$OUT/obj" --hierarchical "$HIERARCHY" \
 "${RETAINED_SOURCES[@]}" -f "$OUT/idma.f" "$OUT/generated/HostBlockTop.sv" \
 "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$P/tests/host_block_commands.cpp" >"$OUT/build.log" 2>&1
set +e
"$OUT/obj/VHostBlockTop" "$OUT/fixture" "$OUT/tensors" >"$OUT/run.log" 2>&1
code=$?;set -e;echo "$code" >"$OUT/simulation.exit";cat "$OUT/run.log";((code==0))||exit "$code"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 "$P/scripts/verify_host_block_gate.py" "$OUT" >"$OUT/verification.log"
cat "$OUT/verification.log"
