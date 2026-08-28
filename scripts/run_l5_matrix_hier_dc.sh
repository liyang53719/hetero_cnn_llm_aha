#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PHASE=${1:-}
DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db}
DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell}
R="$ROOT/scripts/run_memory_capped.sh"
GEN="$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
OUT="$ROOT/work/generated/l5_matrix_hier_dc"
RESULT="$ROOT/work/results/l5_matrix_hier_dc"
LEAVES=(HeteroBF16FmaPre HeteroBF16FmaMul HeteroBF16FmaPost HeteroBF16FmaRound)
mkdir -p "$OUT" "$RESULT"

usage() { echo "usage: $0 {leaf|lane|shell|array|contextparts|context}" >&2; exit 2; }
[[ "$PHASE" =~ ^(leaf|lane|shell|array|contextparts|context)$ ]] || usage
[[ -s "$DB" ]] || { echo "missing DB: $DB" >&2; exit 3; }
available_gib=$(df -Pk "$ROOT" | awk 'NR==2{printf "%.0f",$4/1048576}')
(( available_gib > 50 )) || { echo "disk guard: ${available_gib}GiB" >&2; exit 75; }

run_dc() {
  local limit=$1 out=$2 tcl=$3
  shift 3
  mkdir -p "$out"
  rm -f "$out/status.txt" "$out/dc.log" "$out/result.json"
  local start end rc
  start=$(date +%s)
  printf 'started_epoch=%s\naffinity=8-23\nmemory_high=24G\nmemory_max=30G\nlimit=%s\n' \
    "$start" "$limit" >"$out/run.meta"
  set +e
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
    "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" \
    env "$@" "$DC" -64bit -f "$tcl" >"$out/dc.log" 2>&1
  rc=$?
  set -e
  end=$(date +%s)
  printf 'ended_epoch=%s\nelapsed_seconds=%s\nexit_code=%s\n' \
    "$end" "$((end-start))" "$rc" >>"$out/run.meta"
  if (( rc == 124 || rc == 130 || rc == 137 )); then
    echo "BLOCKED_RUNTIME phase=$PHASE out=$out elapsed=$((end-start))" >&2
    return 75
  fi
  return "$rc"
}

if [[ "$PHASE" == leaf ]]; then
  "$ROOT/scripts/generate_all_hardfloat_primitives.sh"
  [[ ! -s "$ROOT/work/generated/l5_all_primitives/upstream.status" ]]
  for top in "${LEAVES[@]}"; do
    leaf_root="$RESULT/leaf/$top"
    normal="$leaf_root/normal"
    ddc="$OUT/leaf/$top/$top.ddc"
    mkdir -p "$(dirname "$ddc")"
    rm -f "$ddc"
    run_dc 10m "$normal" "$ROOT/dc/synth_l5_bf16_leaf.tcl" \
      TOP="$top" RTL_SV="$GEN" STD_CELL_DB="$DB" OUT_DIR="$normal" \
      DDC_OUT="$ddc" CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4 DC_TIMING_HIGH_EFFORT=0
    set +e
    taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" leaf "$normal" \
      --json-out "$normal/result.json"
    check_rc=$?
    set -e
    if (( check_rc == 10 )); then
      high="$leaf_root/high"
      rm -f "$ddc"
      run_dc 10m "$high" "$ROOT/dc/synth_l5_bf16_leaf.tcl" \
        TOP="$top" RTL_SV="$GEN" STD_CELL_DB="$DB" OUT_DIR="$high" \
        DDC_OUT="$ddc" CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4 DC_TIMING_HIGH_EFFORT=1
      taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" leaf "$high" \
        --json-out "$high/result.json"
    elif (( check_rc != 0 )); then
      exit "$check_rc"
    fi
    [[ -s "$ddc" ]]
    sha256sum "$ddc" >"$ddc.sha256"
  done
  echo L5_HIER_LEAVES_PASS
elif [[ "$PHASE" == lane ]]; then
  ddc_list=""
  for top in "${LEAVES[@]}"; do
    ddc="$OUT/leaf/$top/$top.ddc"
    [[ -s "$ddc" ]] || { echo "missing accepted leaf DDC: $ddc" >&2; exit 4; }
    ddc_list+="${ddc_list:+:}$ddc"
  done
  lane_out="$RESULT/lane"
  lane_ddc="$OUT/lane/bf16_fma_pipeline_lane.ddc"
  mkdir -p "$(dirname "$lane_ddc")"
  rm -f "$lane_ddc"
  run_dc 10m "$lane_out" "$ROOT/dc/synth_l5_bf16_lane_hier.tcl" \
    RTL_SV="$ROOT/rtl/matrix/bf16_fma_pipeline_lane.sv" LEAF_DDCS="$ddc_list" \
    STD_CELL_DB="$DB" OUT_DIR="$lane_out" DDC_OUT="$lane_ddc" \
    CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4
  taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" lane "$lane_out" \
    --json-out "$lane_out/result.json"
  [[ -s "$lane_ddc" ]]
  sha256sum "$lane_ddc" >"$lane_ddc.sha256"
  echo L5_HIER_LANE_PASS
elif [[ "$PHASE" == shell ]]; then
  for top in bf16_outer_product_array_control512 bf16_outer_product_array_glue512; do
    component_out="$RESULT/shell/$top"
    component_ddc="$OUT/shell/$top.ddc"
    source="$ROOT/rtl/matrix/$top.sv"
    mkdir -p "$(dirname "$component_ddc")"
    rm -f "$component_ddc"
    clock_arg=()
    [[ "$top" == bf16_outer_product_array_control512 ]] && \
      clock_arg=(CLOCK_PORT=clk_i LANE_ENABLE_OUTPUT_DELAY_NS=0.30)
    run_dc 10m "$component_out" "$ROOT/dc/synth_l5_bf16_leaf.tcl" \
      TOP="$top" RTL_SV="$source" STD_CELL_DB="$DB" OUT_DIR="$component_out" \
      DDC_OUT="$component_ddc" CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4 \
      DC_TIMING_HIGH_EFFORT=0 "${clock_arg[@]}"
    taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" leaf "$component_out" \
      --json-out "$component_out/result.json"
    [[ -s "$component_ddc" ]]
    sha256sum "$component_ddc" >"$component_ddc.sha256"
  done
  echo L5_HIER_SHELL_PASS
elif [[ "$PHASE" == array ]]; then
  lane_ddc="$OUT/lane/bf16_fma_pipeline_lane.ddc"
  [[ -s "$lane_ddc" ]] || { echo "missing accepted lane DDC: $lane_ddc" >&2; exit 4; }
  control_ddc="$OUT/shell/bf16_outer_product_array_control512.ddc"
  glue_ddc="$OUT/shell/bf16_outer_product_array_glue512.ddc"
  [[ -s "$control_ddc" ]] || { echo "missing control DDC: $control_ddc" >&2; exit 4; }
  [[ -s "$glue_ddc" ]] || { echo "missing glue DDC: $glue_ddc" >&2; exit 4; }
  array_out="$RESULT/array_rev3"
  array_ddc="$OUT/array/bf16_outer_product_array_ROWS16_COLS32.ddc"
  mkdir -p "$(dirname "$array_ddc")"
  rm -f "$array_ddc"
  run_dc 10m "$array_out" "$ROOT/dc/synth_l5_bf16_array_hier.tcl" \
    RTL_SV="$ROOT/rtl/matrix/bf16_outer_product_array.sv" LANE_DDC="$lane_ddc" \
    CONTROL_DDC="$control_ddc" GLUE_DDC="$glue_ddc" \
    STD_CELL_DB="$DB" OUT_DIR="$array_out" DDC_OUT="$array_ddc" \
    CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=8
  taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" array "$array_out" \
    --json-out "$array_out/result.json"
  [[ -s "$array_ddc" ]]
  sha256sum "$array_ddc" >"$array_ddc.sha256"
  echo L5_HIER_ARRAY_PASS
elif [[ "$PHASE" == contextparts ]]; then
  for top in bf16_context_scheduler4 bf16_context_control_broadcast512; do
    component_out="$RESULT/contextparts/$top"
    component_ddc="$OUT/contextparts/$top.ddc"
    source="$ROOT/rtl/matrix/$top.sv"
    mkdir -p "$(dirname "$component_ddc")"
    rm -f "$component_ddc"
    clock_arg=()
    [[ "$top" == bf16_context_scheduler4 ]] && clock_arg=(CLOCK_PORT=clk_i)
    run_dc 10m "$component_out" "$ROOT/dc/synth_l5_bf16_leaf.tcl" \
      TOP="$top" RTL_SV="$source" STD_CELL_DB="$DB" OUT_DIR="$component_out" \
      DDC_OUT="$component_ddc" CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4 \
      DC_TIMING_HIGH_EFFORT=0 "${clock_arg[@]}"
    taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" leaf "$component_out" \
      --json-out "$component_out/result.json"
    [[ -s "$component_ddc" ]]
    sha256sum "$component_ddc" >"$component_ddc.sha256"
  done
  leaf_ddcs=""
  for top in "${LEAVES[@]}"; do
    ddc="$OUT/leaf/$top/$top.ddc"
    [[ -s "$ddc" ]] || { echo "missing leaf DDC: $ddc" >&2; exit 4; }
    leaf_ddcs+="${leaf_ddcs:+:}$ddc"
  done
  context_lane_root="$RESULT/contextparts/bf16_context_fma_pipeline_lane4_joint"
  context_lane_out="$context_lane_root/normal"
  context_lane_ddc="$OUT/contextparts/bf16_context_fma_pipeline_lane4.ddc"
  context_lane_accepted="$context_lane_ddc.accepted"
  rm -f "$context_lane_ddc" "$context_lane_accepted" "$context_lane_ddc.sha256"
  run_dc 10m "$context_lane_out" "$ROOT/dc/synth_l5_bf16_context_lane_hier.tcl" \
    BASE_LANE_RTL="$ROOT/rtl/matrix/bf16_fma_pipeline_lane.sv" \
    CONTEXT_RTL="$ROOT/rtl/matrix/bf16_context_fma_pipeline_lane4.sv" \
    LEAF_DDCS="$leaf_ddcs" STD_CELL_DB="$DB" OUT_DIR="$context_lane_out" \
    DDC_OUT="$context_lane_ddc" CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4 \
    DC_TIMING_HIGH_EFFORT=0
  set +e
  taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" leaf "$context_lane_out" \
    --json-out "$context_lane_out/result.json"
  check_rc=$?
  set -e
  if (( check_rc == 10 )); then
    context_lane_out="$context_lane_root/high"
    rm -f "$context_lane_ddc"
    run_dc 10m "$context_lane_out" "$ROOT/dc/synth_l5_bf16_context_lane_hier.tcl" \
      BASE_LANE_RTL="$ROOT/rtl/matrix/bf16_fma_pipeline_lane.sv" \
      CONTEXT_RTL="$ROOT/rtl/matrix/bf16_context_fma_pipeline_lane4.sv" \
      LEAF_DDCS="$leaf_ddcs" STD_CELL_DB="$DB" OUT_DIR="$context_lane_out" \
      DDC_OUT="$context_lane_ddc" CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4 \
      DC_TIMING_HIGH_EFFORT=1
    taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" leaf "$context_lane_out" \
      --json-out "$context_lane_out/result.json"
  elif (( check_rc != 0 )); then
    exit "$check_rc"
  fi
  [[ -s "$context_lane_ddc" ]]
  sha256sum "$context_lane_ddc" >"$context_lane_ddc.sha256"
  printf 'accepted=1\n' >"$context_lane_accepted"
  echo L5_HIER_CONTEXT_PARTS_PASS
else
  context_lane_ddc="$OUT/contextparts/bf16_context_fma_pipeline_lane4.ddc"
  context_lane_accepted="$context_lane_ddc.accepted"
  scheduler_ddc="$OUT/contextparts/bf16_context_scheduler4.ddc"
  broadcast_ddc="$OUT/contextparts/bf16_context_control_broadcast512.ddc"
  control_ddc="$OUT/shell/bf16_outer_product_array_control512.ddc"
  glue_ddc="$OUT/shell/bf16_outer_product_array_glue512.ddc"
  [[ -s "$context_lane_accepted" ]] || { echo "context lane DDC is not accepted" >&2; exit 4; }
  for ddc in "$context_lane_ddc" "$scheduler_ddc" "$broadcast_ddc" "$control_ddc" "$glue_ddc"; do
    [[ -s "$ddc" ]] || { echo "missing context component DDC: $ddc" >&2; exit 4; }
  done
  context_out="$RESULT/context_rev5"
  context_ddc="$OUT/context/bf16_outer_product_context_array.ddc"
  mkdir -p "$(dirname "$context_ddc")"
  rm -f "$context_ddc"
  run_dc 10m "$context_out" "$ROOT/dc/synth_l5_bf16_context_hier.tcl" \
    RTL_SV="$ROOT/rtl/matrix/bf16_outer_product_context_array.sv" \
    CONTEXT_LANE_DDC="$context_lane_ddc" SCHEDULER_DDC="$scheduler_ddc" \
    BROADCAST_DDC="$broadcast_ddc" CONTROL_DDC="$control_ddc" GLUE_DDC="$glue_ddc" \
    STD_CELL_DB="$DB" OUT_DIR="$context_out" \
    DDC_OUT="$context_ddc" CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=8
  taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" context "$context_out" \
    --json-out "$context_out/result.json"
  [[ -s "$context_ddc" ]]
  sha256sum "$context_ddc" >"$context_ddc.sha256"
  echo L5_HIER_CONTEXT_PASS
fi
