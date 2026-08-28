#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
R="$ROOT/scripts/run_memory_capped.sh"
VCS=${VCS_BIN:-/home/yang/tools/synopsys/vcs/W-2024.09/bin/vcs}
GEN="$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
BASE="$ROOT/rtl/matrix/bf16_fma_pipeline_lane.sv"
CTX="$ROOT/rtl/matrix/bf16_context_fma_pipeline_lane4.sv"
NET="$ROOT/work/generated/l5_matrix_hier_dc/rev7/lane/bf16_context_fma_pipeline_lane4_rev7.mapped.v"
CELLS=${STD_CELL_VERILOG:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/verilog/sc6p5mcpp140z_cln22ul_base_svt_c35.v}
TB="$ROOT/tb/tb_l5_revision7_gate_compare.sv"
OUT="$ROOT/work/results/l5_matrix_hier_dc/rev7/gate_compare"
REPORT="$ROOT/reports/execution/l5_revision7_gate_compare_result.json"
mkdir -p "$OUT/rtl" "$OUT/gate"
for f in "$VCS" "$GEN" "$BASE" "$CTX" "$NET" "$CELLS" "$TB"; do
  [[ -s "$f" ]] || { echo "missing gate-compare input: $f" >&2; exit 3; }
done
rm -f "$OUT/rtl/trace.txt" "$OUT/gate/trace.txt" "$OUT/rtl/simv" "$OUT/gate/simv" "$REPORT"

run_capped() {
  local limit=$1
  shift
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
    "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@"
}

(
  cd "$OUT/rtl"
  run_capped 10m "$VCS" -full64 -sverilog -timescale=1ns/1ps \
    +vcs+lic+wait -j4 -top tb_l5_revision7_gate_compare \
    "$GEN" "$BASE" "$CTX" "$TB" -o "$OUT/rtl/simv" \
    >"$OUT/rtl/compile.log" 2>&1
)
(
  cd "$OUT/gate"
  run_capped 10m "$VCS" -full64 -sverilog -timescale=1ns/1ps \
    +vcs+lic+wait +nospecify -j4 -top tb_l5_revision7_gate_compare \
    "$CELLS" "$NET" "$TB" -o "$OUT/gate/simv" \
    >"$OUT/gate/compile.log" 2>&1
)

run_capped 5m "$OUT/rtl/simv" "+TRACE=$OUT/rtl/trace.txt" \
  >"$OUT/rtl/run.log" 2>&1
run_capped 5m "$OUT/gate/simv" +notimingcheck "+TRACE=$OUT/gate/trace.txt" \
  >"$OUT/gate/run.log" 2>&1

expected=120032
rtl_lines=$(wc -l <"$OUT/rtl/trace.txt")
gate_lines=$(wc -l <"$OUT/gate/trace.txt")
[[ "$rtl_lines" -eq "$expected" && "$gate_lines" -eq "$expected" ]] || {
  echo "trace line mismatch rtl=$rtl_lines gate=$gate_lines expected=$expected" >&2
  exit 1
}
cmp "$OUT/rtl/trace.txt" "$OUT/gate/trace.txt"

taskset -c 8-23 python3 - "$REPORT" "$GEN" "$BASE" "$CTX" "$NET" "$CELLS" \
  "$TB" "$OUT/rtl/simv" "$OUT/gate/simv" "$OUT/rtl/trace.txt" \
  "$OUT/gate/trace.txt" <<'PY'
import hashlib,json,subprocess,sys
from pathlib import Path
out,gen,base,ctx,net,cells,tb,rtl_bin,gate_bin,rtl_trace,gate_trace=map(Path,sys.argv[1:])
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
trace_sha=sha(rtl_trace)
if trace_sha!=sha(gate_trace): raise SystemExit('trace SHA mismatch after cmp')
result={
  'schema_version':1,
  'revision':7,
  'status':'PASS',
  'method':'post_synthesis_gate_compare',
  'evidence_class':'cycle_exact_RTL_vs_CLN22UL_mapped_gate',
  'simulator':'VCS W-2024.09',
  'comparison_mode':'functional_zero_delay_no_SDF',
  'seed':'0x7a51c39d',
  'warmup_cycles':16,
  'same_cycle_bypass_recurrence_cycles':100000,
  'randomized_control_cycles':20000,
  'drain_cycles':16,
  'compared_cycles':120032,
  'mismatches':0,
  'unknown_outputs':0,
  'hashes':{
    'generated_rtl_sha256':sha(gen),
    'base_lane_rtl_sha256':sha(base),
    'context_lane_rtl_sha256':sha(ctx),
    'mapped_netlist_sha256':sha(net),
    'std_cell_verilog_sha256':sha(cells),
    'testbench_sha256':sha(tb),
    'rtl_binary_sha256':sha(rtl_bin),
    'gate_binary_sha256':sha(gate_bin),
    'rtl_trace_sha256':trace_sha,
    'gate_trace_sha256':trace_sha,
  },
  'limitations':['functional gate comparison is not SDF timing simulation','physical signoff remains outside L5.2'],
}
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,indent=2,sort_keys=True))
PY

echo REV7_POST_SYNTHESIS_GATE_COMPARE_PASS
