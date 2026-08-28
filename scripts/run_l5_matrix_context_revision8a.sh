#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PHASE=${1:-all}
[[ "$PHASE" =~ ^(validate|compare|e1|adversarial|lane|equiv|cluster|front|top|summarize|all)$ ]] || {
  echo "usage: $0 {validate|compare|e1|adversarial|lane|equiv|cluster|front|top|summarize|all}" >&2; exit 2;
}
DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db}
DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell}
FM=${FORMALITY_SHELL:-/home/yang/tools/synopsys/formality/T-2022.03-SP5/bin/fm_shell}
R="$ROOT/scripts/run_memory_capped.sh"
GEN="$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
CAND="$ROOT/rtl/matrix/candidates/rev8"
OUT="$ROOT/work/generated/l5_matrix_rev8a"
RES="$ROOT/work/results/l5_matrix_rev8a"
mkdir -p "$OUT/lane" "$OUT/cluster16" "$OUT/front" "$OUT/top" "$RES"

run_dc() {
  local limit=$1 out=$2 tcl=$3; shift 3
  mkdir -p "$out"; rm -f "$out/status.txt" "$out/dc.log"
  local start rc
  start=$(date +%s); set +e
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
    timeout --foreground --signal=INT --kill-after=30s "$limit" \
    env "$@" "$DC" -64bit -f "$tcl" >"$out/dc.log" 2>&1
  rc=$?; set -e
  printf 'elapsed_seconds=%s\nexit_code=%s\n' "$(( $(date +%s)-start ))" "$rc" >"$out/run.meta"
  if (( rc==124 || rc==130 || rc==137 )); then echo "BLOCKED_RUNTIME out=$out" >&2; return 75; fi
  return "$rc"
}

check_status() {
  local path=$1 phase=$2 expected_instances=${3:-}
  python3 - "$path" "$phase" "$expected_instances" <<'PY'
import sys
p,phase,expected=sys.argv[1:]
f=dict(line.strip().split('=',1) for line in open(p) if '=' in line)
for k,v in {'LINK_STATUS':'1','UNMAPPED_CELLS':'0','UNRESOLVED_REFERENCES':'0'}.items():
    if f.get(k)!=v: raise SystemExit(f'{phase}: {k}={f.get(k)} expected {v}')
w=float(f['WORST_SLACK_NS'])
if expected:
    key={'cluster':'LANE_INSTANCES','top':'CLUSTER16_INSTANCES'}[phase]
    if int(f.get(key,'-1'))!=int(expected): raise SystemExit(f'{phase}: {key}={f.get(key)}')
print(f'REV8A_{phase.upper()} WNS={w} AREA={f.get("CELL_AREA")}')
raise SystemExit(0 if w>=0 else 10)
PY
}

map_retry() {
  local kind=$1 normal=$2 high=$3 tcl=$4; shift 4
  run_dc 600s "$normal" "$tcl" "$@" OUT_DIR="$normal" DC_TIMING_HIGH_EFFORT=0
  set +e; check_status "$normal/status.txt" "$kind" "${EXPECTED_INSTANCES:-}"; local rc=$?; set -e
  if (( rc==10 )); then
    run_dc 600s "$high" "$tcl" "$@" OUT_DIR="$high" DC_TIMING_HIGH_EFFORT=1
    check_status "$high/status.txt" "$kind" "${EXPECTED_INSTANCES:-}"
    CHOSEN_DIR="$high"
  elif (( rc==0 )); then
    CHOSEN_DIR="$normal"
  else
    exit "$rc"
  fi
}

validate() {
  taskset -c 8-23 env PYTHONPATH="$ROOT/src" python3 "$ROOT/scripts/validate_l5_revision8a_contract.py" --operations 100000
  "$ROOT/scripts/generate_all_hardfloat_primitives.sh"
  python3 - "$ROOT/config/l5_revision8a_policy.json" "$GEN" <<'PY'
import hashlib,json,sys
p=json.load(open(sys.argv[1])); actual=hashlib.sha256(open(sys.argv[2],'rb').read()).hexdigest(); expected=p['generated_rtl_sha256']
if actual!=expected: raise SystemExit(f'generated RTL SHA mismatch {actual} != {expected}')
print(f'REV8A_GENERATED_RTL_PIN_PASS sha256={actual}')
PY
}

lane() {
  validate
  rm -f "$OUT/lane/accepted" "$OUT/lane/equivalence.accepted"
  map_retry lane "$RES/lane/normal" "$RES/lane/high" "$ROOT/dc/synth_l5_bf16_context_lane_rev8a.tcl" \
    GENERATED_SV="$GEN" LANE_RTL="$CAND/bf16_context_fma_pipeline_lane4_rev8_candidate.sv" \
    STD_CELL_DB="$DB" \
    DDC_OUT="$OUT/lane/bf16_context_fma_pipeline_lane4_rev8_candidate.ddc" \
    NETLIST_OUT="$OUT/lane/bf16_context_fma_pipeline_lane4_rev8_candidate.mapped.v" \
    SDC_OUT="$OUT/lane/bf16_context_fma_pipeline_lane4_rev8_candidate.sdc" \
    SVF_OUT="$OUT/lane/bf16_context_fma_pipeline_lane4_rev8_candidate.svf" \
    CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4
  cp "$CHOSEN_DIR/status.txt" "$RES/lane/accepted_status.txt"
  printf 'accepted=1\n' >"$OUT/lane/accepted"
}

equiv() {
  [[ -s "$OUT/lane/accepted" ]] || { echo "run lane first" >&2; exit 4; }
  rm -f "$OUT/lane/equivalence.accepted"
  if [[ -x "$FM" ]]; then
    mkdir -p "$RES/equivalence"
    env GENERATED_SV="$GEN" LANE_RTL="$CAND/bf16_context_fma_pipeline_lane4_rev8_candidate.sv" \
      IMPL_NETLIST="$OUT/lane/bf16_context_fma_pipeline_lane4_rev8_candidate.mapped.v" \
      STD_CELL_DB="$DB" SVF_FILE="$OUT/lane/bf16_context_fma_pipeline_lane4_rev8_candidate.svf" \
      OUT_DIR="$RES/equivalence" "$FM" -f "$ROOT/dc/formality_l5_context_lane_rev8a.tcl" \
      >"$RES/equivalence/formality.log" 2>&1
    grep -Eqi 'Verification[[:space:]]+(SUCCEEDED|PASS)' "$RES/equivalence/formality.log"
    printf '{"schema_version":1,"revision":"8A","status":"PASS","method":"Formality"}\n' >"$ROOT/reports/execution/l5_revision8a_gate_compare_result.json"
  else
    "$ROOT/scripts/run_l5_revision8a_gate_compare.sh"
  fi
  printf 'accepted=1\n' >"$OUT/lane/equivalence.accepted"
}

cluster() {
  [[ -s "$OUT/lane/accepted" ]] || { echo "run lane first" >&2; exit 4; }
  EXPECTED_INSTANCES=16 map_retry cluster "$RES/cluster16/normal" "$RES/cluster16/high" \
    "$ROOT/dc/synth_l5_bf16_context_cluster16_rev8a.tcl" \
    GENERATED_SV="$GEN" LANE_RTL="$CAND/bf16_context_fma_pipeline_lane4_rev8_candidate.sv" \
    CLUSTER_RTL="$CAND/bf16_context_lane_cluster16_rev8_candidate.sv" \
    STD_CELL_DB="$DB" \
    DDC_OUT="$OUT/cluster16/bf16_context_lane_cluster16_rev8_candidate.ddc" \
    NETLIST_OUT="$OUT/cluster16/bf16_context_lane_cluster16_rev8_candidate.mapped.v" \
    SDC_OUT="$OUT/cluster16/bf16_context_lane_cluster16_rev8_candidate.sdc" \
    SVF_OUT="$OUT/cluster16/bf16_context_lane_cluster16_rev8_candidate.svf" \
    CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=8
  cp "$CHOSEN_DIR/status.txt" "$RES/cluster16/accepted_status.txt"
  printf 'accepted=1\n' >"$OUT/cluster16/accepted"
}

front() {
  local files="$ROOT/rtl/matrix/bf16_context_scheduler4.sv:$CAND/bf16_outer_product_array_control_rev8_candidate.sv:$CAND/bf16_context_tag_pipeline4_rev8_candidate.sv:$CAND/bf16_context_front_control_rev8_candidate.sv"
  map_retry front "$RES/front/normal" "$RES/front/high" "$ROOT/dc/synth_l5_bf16_front_control_rev8a.tcl" \
    RTL_FILES="$files" STD_CELL_DB="$DB" \
    DDC_OUT="$OUT/front/bf16_context_front_control_rev8_candidate.ddc" \
    NETLIST_OUT="$OUT/front/bf16_context_front_control_rev8_candidate.mapped.v" \
    SDC_OUT="$OUT/front/bf16_context_front_control_rev8_candidate.sdc" \
    SVF_OUT="$OUT/front/bf16_context_front_control_rev8_candidate.svf" \
    CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4
  cp "$CHOSEN_DIR/status.txt" "$RES/front/accepted_status.txt"
  printf 'accepted=1\n' >"$OUT/front/accepted"
}

prepare_glue() {
  local ddc="$ROOT/work/generated/l5_matrix_hier_dc/shell/bf16_outer_product_array_glue512.ddc"
  if [[ ! -s "$ddc" ]]; then "$ROOT/scripts/run_l5_matrix_hier_dc.sh" shell; fi
  [[ -s "$ddc" ]] || { echo "missing glue DDC: $ddc" >&2; exit 4; }
}

top() {
  [[ -s "$OUT/cluster16/accepted" && -s "$OUT/front/accepted" && -s "$OUT/lane/equivalence.accepted" ]] || { echo "lane/equiv/cluster/front not accepted" >&2; exit 4; }
  prepare_glue
  local glue="$ROOT/work/generated/l5_matrix_hier_dc/shell/bf16_outer_product_array_glue512.ddc"
  run_dc 600s "$RES/top" "$ROOT/dc/synth_l5_bf16_context_top_rev8a.tcl" \
    TOP_RTL="$CAND/bf16_outer_product_context_array_rev8_candidate.sv" \
    FRONT_DDC="$OUT/front/bf16_context_front_control_rev8_candidate.ddc" \
    CLUSTER_DDC="$OUT/cluster16/bf16_context_lane_cluster16_rev8_candidate.ddc" \
    GLUE_DDC="$glue" STD_CELL_DB="$DB" OUT_DIR="$RES/top" \
    DDC_OUT="$OUT/top/bf16_outer_product_context_array_rev8_candidate.ddc" \
    CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=8
  EXPECTED_INSTANCES=32 check_status "$RES/top/status.txt" top 32
}

summarize() { taskset -c 8-23 python3 "$ROOT/scripts/summarize_l5_revision8a.py"; }

case "$PHASE" in
  validate) validate;;
  compare) "$ROOT/scripts/run_l5_matrix_context_revision8a_compare.sh";;
  e1) "$ROOT/scripts/run_l5_matrix_context_revision8a_e1.sh";;
  adversarial) "$ROOT/scripts/run_l5_matrix_context_revision8a_adversarial_e1.sh";;
  lane) lane;;
  equiv) equiv;;
  cluster) cluster;;
  front) front;;
  top) top;;
  summarize) summarize;;
  all)
    validate
    "$ROOT/scripts/run_l5_matrix_context_revision8a_compare.sh"
    "$ROOT/scripts/run_l5_matrix_context_revision8a_e1.sh"
    "$ROOT/scripts/run_l5_matrix_context_revision8a_adversarial_e1.sh"
    lane; equiv; cluster; front; top
    "$ROOT/scripts/run_l5_matrix_context_revision8a_e1.sh"
    "$ROOT/scripts/run_l5_matrix_context_revision8a_adversarial_e1.sh"
    summarize
    ;;
esac
