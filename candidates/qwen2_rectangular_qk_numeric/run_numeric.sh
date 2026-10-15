#!/usr/bin/env bash
# Real 4096-MAC RTL, bounded synthetic partials only. No Host/iDMA/full block.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
HERE="$ROOT/candidates/qwen2_rectangular_qk_numeric"
P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output directory}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2; exit 2; }
for t in java sbt verilator g++ git curl timeout sha256sum python3; do command -v "$t" >/dev/null || { echo "MISSING_TOOL:$t" >&2; exit 77; }; done
[[ -x /usr/bin/time ]] || { echo MISSING_GNU_TIME >&2; exit 77; }
mkdir -p "$OUT"
printf 'stage\telapsed_seconds\tmax_child_rss_kib_not_aggregate\texit_status\n' > "$OUT/stages.tsv"
printf 'ACTUAL_MATRIX_RTL; fixed3tests/4subcases/89steps; B is an 80KiB single-ACK testbench fixture.\n' > "$OUT/summary.txt"
START=$SECONDS
trap 'rc=$?; printf "runner_exit=%s\n" "$rc" >> "$OUT/summary.txt"; exit "$rc"' EXIT
# GNU timeout owns one process group per active stage. Track it independently
# of the outer runner timeout, which cannot signal nested groups itself.
ACTIVE_PID='' ACTIVE_NAME='' LAUNCHING=0 STOP_RC=0
record_stage() {
  local name=$1 rc=$2 elapsed=NA rss=NA last=''
  if [[ -f "$OUT/$name.time" ]]; then
    last=$(tail -1 "$OUT/$name.time")
    if [[ "$last" =~ ^[0-9]+([.][0-9]+)?[[:space:]][0-9]+$ ]]; then
      read -r elapsed rss <<< "$last"
    fi
  fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$elapsed" "$rss" "$rc" >> "$OUT/stages.tsv"
  [[ ! -f "$OUT/$name.log" ]] || tail -80 "$OUT/$name.log"
}
stop_stage() {
  local rc=$1 pid=$ACTIVE_PID name=$ACTIVE_NAME
  # A signal between background launch and $! assignment must not lose the job.
  if ((LAUNCHING)); then
    ((STOP_RC!=0)) || STOP_RC=$rc
    return
  fi
  trap '' TERM INT HUP
  if [[ -n "$pid" ]]; then
    # The PID fallback covers a signal arriving before timeout establishes PGID.
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for ((i=0;i<50;i++)); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    # A leader can exit before its descendants. Kill the residual group too.
    kill -KILL -- "-$pid" 2>/dev/null || true
    kill -KILL "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    record_stage "$name" "$rc"
    ACTIVE_PID='' ACTIVE_NAME=''
  fi
  exit "$rc"
}
trap 'stop_stage 143' TERM
trap 'stop_stage 130' INT
trap 'stop_stage 129' HUP
stage() {
  local name=$1 cap=$2; shift 2
  local remaining=$((1500-(SECONDS-START))) rc
  ((remaining>0)) || { echo TOTAL_1500_SECOND_BUDGET_EXHAUSTED >&2; return 124; }
  ((cap<=remaining)) || cap=$remaining
  LAUNCHING=1
  ACTIVE_NAME=$name
  set +e
  timeout --signal=TERM --kill-after=10 "$cap" /usr/bin/time -f '%e %M' -o "$OUT/$name.time" "$@" > "$OUT/$name.log" 2>&1 &
  ACTIVE_PID=$!
  LAUNCHING=0
  ((STOP_RC==0)) || stop_stage "$STOP_RC"
  wait "$ACTIVE_PID"
  rc=$?
  # A timed-out leader may leave TERM-resistant descendants in its group.
  kill -KILL -- "-$ACTIVE_PID" 2>/dev/null || true
  ACTIVE_PID='' ACTIVE_NAME=''
  set -e
  record_stage "$name" "$rc"
  return "$rc"
}

cd "$ROOT"
sha256sum -c "$HERE/frozen.sha256" > "$OUT/source-check.log"
{ git rev-parse HEAD; cat "$HERE/frozen.sha256"; } > "$OUT/source-sha256.txt"
# Only the official clock file is required, not a regenerated iDMA export.
CLOCK_PIN=3a3de73632a06826b1bd9c65a0a2e92b32016845
CLOCK_SHA=93e9747504fa1da6473560341febbfae6c5e917768633a84fc9ef12299293207
stage clock_download 60 curl --fail --location --connect-timeout 15 --max-time 50 \
 "https://raw.githubusercontent.com/pulp-platform/tech_cells_generic/$CLOCK_PIN/src/rtl/tc_clk.sv" -o "$OUT/tc_clk.sv"
printf '%s  %s\n' "$CLOCK_SHA" "$OUT/tc_clk.sv" | sha256sum -c -
export RETAINED_CLOCK_SOURCE="$OUT/tc_clk.sv" RETAINED_SKIP_CLOCK=0
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
stage hardfloat 120 bash "$P/scripts/prepare_hardfloat.sh"
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
source "$P/scripts/retained_sources.sh"
export MAKEFLAGS='-j2 VM_PARALLEL_BUILDS=0 VK_PCH_I_FAST= VK_PCH_I_SLOW='
export JVM_OPTS='-Xmx3G -Xss4M -XX:ActiveProcessorCount=2'
export SBT_OPTS='-Dsbt.supershell=false -Dsbt.color=false -Dsbt.task.cpus=2'
SCALA_SETTINGS=(
 "set Compile / unmanagedSources += file(\"$ROOT/candidates/qwen2_rectangular_qk_profile/src/main/scala/heteronpu/continuous/QkRectangularProfile.scala\")"
 "set Test / unmanagedSources := Seq(file(\"$HERE/QkNumericProbe.scala\"),file(\"$P/src/test/scala/heteronpu/continuous/MatrixPipelineProbe.scala\"))"
)
cd "$P"
stage scala_compile 180 sbt -batch "${SCALA_SETTINGS[@]}" 'Test / compile'
stage rtl_emit 120 sbt -batch "${SCALA_SETTINGS[@]}" "Test / runMain heteronpu.continuous.EmitQkNumericProbe $OUT/generated"
[[ -s "$OUT/generated/QkNumericProbe.sv" ]] || { echo MISSING_RTL >&2; exit 3; }
sha256sum "$OUT/generated/QkNumericProbe.sv" > "$OUT/rtl-sha256.txt"
# Preserve the proven hierarchy boundary. Do not compile the unrelated iDMA packages.
stage verilator_generate 300 verilator --cc --exe --assert -Wno-fatal --top-module QkNumericProbe \
 -CFLAGS "-O2 -std=c++17 -ffp-contract=off -fno-fast-math -I$HERE" -j 2 --Mdir "$OUT/obj" \
 --hierarchical "$P/tests/matrix4096_hierarchy.vlt" "${RETAINED_SOURCES[@]}" \
 "$OUT/generated/QkNumericProbe.sv" "$HERE/qk_numeric.cpp"
stage cpp_compile_link 600 make -C "$OUT/obj" -f VQkNumericProbe_hier.mk -j 2
stage real_numeric_simulation 60 "$OUT/obj/VQkNumericProbe"
# Exact positive receipts prevent successful empty runs or a substituted control-only test.
[[ $(grep -c '^QK_NUMERIC_SUBCASE_PASS case=' "$OUT/real_numeric_simulation.log") == 4 ]]
[[ $(grep -c '^QK_ACTUAL_MATRIX_NUMERIC_PASS tests=3 subcases=4 actual_steps=89 b_write_acks=704 ' "$OUT/real_numeric_simulation.log") == 1 ]]
for case in 0 1 2 3; do [[ $(grep -c "^QK_NUMERIC_SUBCASE_PASS case=$case " "$OUT/real_numeric_simulation.log") == 1 ]]; done
[[ -s "$OUT/rtl-sha256.txt" ]]
cd "$ROOT";sha256sum -c "$HERE/frozen.sha256" >> "$OUT/source-check.log"
cat "$OUT/real_numeric_simulation.log" >> "$OUT/summary.txt"
printf 'PASS_FIXED_QK_PARTIAL_RTL_ONLY; fold=NOT_RUN softmax=NOT_RUN A_DMA=NOT_RUN B_SRAM_RTL=NOT_RUN\n' >> "$OUT/summary.txt"
