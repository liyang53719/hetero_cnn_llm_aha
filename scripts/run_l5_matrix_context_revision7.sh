#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PHASE=${1:-all}
[[ "$PHASE" =~ ^(validate|lane|equiv|e1|prepare|top|all)$ ]] || { echo "usage: $0 {validate|lane|equiv|e1|prepare|top|all}" >&2; exit 2; }
DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db}
DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell}
FM=${FORMALITY_SHELL:-/home/yang/tools/synopsys/formality/T-2022.03-SP5/bin/fm_shell}
R="$ROOT/scripts/run_memory_capped.sh"
GEN="$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
BASE="$ROOT/rtl/matrix/bf16_fma_pipeline_lane.sv"
CTX="$ROOT/rtl/matrix/bf16_context_fma_pipeline_lane4.sv"
OUT="$ROOT/work/generated/l5_matrix_hier_dc/rev7"
RES="$ROOT/work/results/l5_matrix_hier_dc/rev7"
POLICY="$ROOT/config/l5_revision7_policy.json"
mkdir -p "$OUT/lane" "$RES/lane" "$RES/equivalence" "$RES/context"

validate() {
  taskset -c 8-23 env PYTHONPATH="$ROOT/src" python3 "$ROOT/scripts/validate_l5_revision7_contract.py"
  "$ROOT/scripts/generate_all_hardfloat_primitives.sh"
  python3 - "$POLICY" "$GEN" <<'PY'
import hashlib,json,sys
policy=json.load(open(sys.argv[1])); actual=hashlib.sha256(open(sys.argv[2],'rb').read()).hexdigest(); expected=policy['generated_rtl_sha256']
if actual!=expected: raise SystemExit(f'generated RTL SHA mismatch {actual} != {expected}')
print(f'REV7_GENERATED_RTL_PIN_PASS sha256={actual}')
PY
}
run_dc() {
  local effort=$1 out=$2
  mkdir -p "$out"; rm -f "$out/status.txt" "$out/dc.log"
  local start=$(date +%s) rc
  set +e
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
    timeout --foreground --signal=INT --kill-after=30s 600s \
    env GENERATED_SV="$GEN" BASE_LANE_RTL="$BASE" CONTEXT_RTL="$CTX" \
      STD_CELL_DB="$DB" OUT_DIR="$out" DDC_OUT="$OUT/lane/bf16_context_fma_pipeline_lane4_rev7.ddc" \
      NETLIST_OUT="$OUT/lane/bf16_context_fma_pipeline_lane4_rev7.mapped.v" \
      SDC_OUT="$OUT/lane/bf16_context_fma_pipeline_lane4_rev7.sdc" \
      SVF_OUT="$OUT/lane/bf16_context_fma_pipeline_lane4_rev7.svf" \
      CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4 DC_TIMING_HIGH_EFFORT="$effort" \
      "$DC" -64bit -f "$ROOT/dc/synth_l5_bf16_context_lane_rev7.tcl" >"$out/dc.log" 2>&1
  rc=$?; set -e
  printf 'elapsed_seconds=%s\nexit_code=%s\n' "$(( $(date +%s)-start ))" "$rc" >"$out/run.meta"
  if ((rc==124||rc==130||rc==137)); then echo REV7_BLOCKED_RUNTIME >&2; return 75; fi
  return "$rc"
}
check_lane() {
  local dir=$1
  python3 - "$dir/status.txt" <<'PY'
import sys
f=dict(x.strip().split('=',1) for x in open(sys.argv[1]) if '=' in x)
required={'REVISION':'7','SOURCE_REMAP':'1','LEAF_DDCS_READ':'0','RETIMING_AUTHORIZED':'0','CONTEXTS':'4','FEEDBACK_LATENCY_CYCLES':'4','LINK_STATUS':'1','UNMAPPED_CELLS':'0','UNRESOLVED_REFERENCES':'0'}
for k,v in required.items():
 if f.get(k)!=v: raise SystemExit(f'{k}={f.get(k)} expected {v}')
w=float(f['WORST_SLACK_NS']); print(f'REV7_LANE WNS={w} AREA={f.get("CELL_AREA")}')
raise SystemExit(0 if w>=0 else 10)
PY
}
map_leaf_component() {
  local top=$1 source=$2 clock_port=${3:-}
  local out="$RES/prereq/$top" ddc="$ROOT/work/generated/l5_matrix_hier_dc/contextparts/${top}.ddc"
  mkdir -p "$out" "$(dirname "$ddc")"
  if [[ -s "$ddc" ]]; then return 0; fi
  local clock_args=()
  if [[ -n "$clock_port" ]]; then clock_args=(CLOCK_PORT="$clock_port"); fi
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
    timeout --foreground --signal=INT --kill-after=30s 600s \
    env TOP="$top" RTL_SV="$source" STD_CELL_DB="$DB" OUT_DIR="$out" \
      DDC_OUT="$ddc" CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=4 DC_TIMING_HIGH_EFFORT=0 \
      "${clock_args[@]}" "$DC" -64bit -f "$ROOT/dc/synth_l5_bf16_leaf.tcl" >"$out/dc.log" 2>&1
  taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" leaf "$out" --json-out "$out/result.json"
}
prepare() {
  local base="$ROOT/work/generated/l5_matrix_hier_dc"
  if [[ ! -s "$base/shell/bf16_outer_product_array_control512.ddc" || ! -s "$base/shell/bf16_outer_product_array_glue512.ddc" ]]; then
    "$ROOT/scripts/run_l5_matrix_hier_dc.sh" shell
  fi
  map_leaf_component bf16_context_scheduler4 "$ROOT/rtl/matrix/bf16_context_scheduler4.sv" clk_i
  map_leaf_component bf16_context_control_broadcast512 "$ROOT/rtl/matrix/bf16_context_control_broadcast512.sv"
  for d in \
    "$base/contextparts/bf16_context_scheduler4.ddc" \
    "$base/contextparts/bf16_context_control_broadcast512.ddc" \
    "$base/shell/bf16_outer_product_array_control512.ddc" \
    "$base/shell/bf16_outer_product_array_glue512.ddc"; do
    [[ -s "$d" ]] || { echo "missing prerequisite DDC: $d" >&2; exit 4; }
  done
  echo REV7_PREREQUISITES_PASS
}
lane() {
  validate
  rm -f "$OUT/lane/rev7_lane.accepted" "$OUT/lane/rev7_equivalence.accepted"
  run_dc 0 "$RES/lane/normal"
  set +e; check_lane "$RES/lane/normal"; rc=$?; set -e
  if ((rc==10)); then
    run_dc 1 "$RES/lane/high"
    check_lane "$RES/lane/high"
    chosen="$RES/lane/high"
  elif ((rc==0)); then chosen="$RES/lane/normal"; else exit "$rc"; fi
  python3 - "$chosen/status.txt" <<'PY'
import sys
f=dict(x.strip().split('=',1) for x in open(sys.argv[1]) if '=' in x); w=float(f['WORST_SLACK_NS'])
print('REV7_LANE_CLASS=' + ('PASS_PREFERRED_MARGIN' if w>=.02 else 'PASS_MARGINAL_PROCEED_TO_H3_NOT_SIGNOFF'))
PY
  printf 'accepted=1\n' >"$OUT/lane/rev7_lane.accepted"
}
equiv() {
  [[ -s "$OUT/lane/rev7_lane.accepted" ]] || { echo run lane first >&2; exit 4; }
  rm -f "$OUT/lane/rev7_equivalence.accepted"
  if [[ -x "$FM" ]]; then
    set +e
    env GENERATED_SV="$GEN" BASE_LANE_RTL="$BASE" CONTEXT_RTL="$CTX" \
      IMPL_NETLIST="$OUT/lane/bf16_context_fma_pipeline_lane4_rev7.mapped.v" \
      STD_CELL_DB="$DB" SVF_FILE="$OUT/lane/bf16_context_fma_pipeline_lane4_rev7.svf" \
      OUT_DIR="$RES/equivalence" "$FM" -f "$ROOT/dc/formality_l5_context_lane_rev7.tcl" >"$RES/equivalence/formality.log" 2>&1
    rc=$?; set -e
    if ((rc!=0)) || ! grep -Eqi 'Verification[[:space:]]+(SUCCEEDED|PASS)' "$RES/equivalence/formality.log"; then
      echo REV7_EQUIVALENCE_FAIL >&2; exit 1
    fi
    printf '{"schema_version":1,"status":"PASS","method":"Formality","svf":true}\n' >"$RES/equivalence/result.json"
  elif [[ -n "${REV7_EQUIVALENCE_EVIDENCE:-}" && -s "${REV7_EQUIVALENCE_EVIDENCE}" ]]; then
    python3 - "$REV7_EQUIVALENCE_EVIDENCE" "$RES/equivalence/result.json" <<'PY'
import json,shutil,sys
x=json.load(open(sys.argv[1]));
if x.get('status')!='PASS' or x.get('method') not in {'Formality','post_synthesis_gate_compare'}: raise SystemExit('invalid equivalence evidence')
shutil.copyfile(sys.argv[1],sys.argv[2])
PY
  else
    echo 'BLOCKED_EQUIVALENCE_TOOL: provide FORMALITY_SHELL or REV7_EQUIVALENCE_EVIDENCE' >&2; exit 75
  fi
  printf 'accepted=1\n' >"$OUT/lane/rev7_equivalence.accepted"
}
e1() { "$ROOT/scripts/run_l5_matrix_context_array.sh"; }
top() {
  prepare
  [[ -s "$OUT/lane/rev7_lane.accepted" && -s "$OUT/lane/rev7_equivalence.accepted" ]] || { echo lane/equivalence not accepted >&2; exit 4; }
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
    timeout --foreground --signal=INT --kill-after=30s 600s \
    env RTL_SV="$ROOT/rtl/matrix/bf16_outer_product_context_array.sv" \
      CONTEXT_LANE_DDC="$OUT/lane/bf16_context_fma_pipeline_lane4_rev7.ddc" \
      SCHEDULER_DDC="$ROOT/work/generated/l5_matrix_hier_dc/contextparts/bf16_context_scheduler4.ddc" \
      BROADCAST_DDC="$ROOT/work/generated/l5_matrix_hier_dc/contextparts/bf16_context_control_broadcast512.ddc" \
      CONTROL_DDC="$ROOT/work/generated/l5_matrix_hier_dc/shell/bf16_outer_product_array_control512.ddc" \
      GLUE_DDC="$ROOT/work/generated/l5_matrix_hier_dc/shell/bf16_outer_product_array_glue512.ddc" \
      STD_CELL_DB="$DB" OUT_DIR="$RES/context" DDC_OUT="$OUT/bf16_outer_product_context_array_rev7.ddc" \
      CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=8 "$DC" -64bit -f "$ROOT/dc/synth_l5_bf16_context_hier.tcl" >"$RES/context/dc.log" 2>&1
  taskset -c 8-23 python3 "$ROOT/scripts/check_l5_hier_dc.py" context "$RES/context" --json-out "$RES/context/result.json"
}
case "$PHASE" in
 validate) validate;; lane) lane;; equiv) equiv;; e1) e1;; prepare) prepare;; top) top;;
 all) lane; equiv; e1; prepare; top; e1; python3 "$ROOT/scripts/summarize_l5_revision7.py";;
esac
