#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);R=$ROOT/scripts/run_memory_capped.sh
"$ROOT/scripts/run_l4_pool_residual_sfu.sh";"$ROOT/scripts/run_l4_pool_residual_canonical.sh"
"$ROOT/scripts/run_l4_matrix_trace_case.sh" tb_l4_pool_l3_trace "$ROOT/work/results/l4_pool_l3_trace"
"$ROOT/scripts/run_l4_matrix_trace_case.sh" tb_l4_residual_l3_trace "$ROOT/work/results/l4_residual_l3_trace"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$ROOT/work/toolchain/cnn_py312/bin/python" "$ROOT/scripts/audit_l4_pool_residual_complete.py" --rtl "$ROOT/reports/execution/l4_pool_residual_sfu_result.json" --canonical-log "$ROOT/work/results/l4_pool_residual_canonical/tb.log" --pool-log "$ROOT/work/results/l4_pool_l3_trace/tb.log" --residual-log "$ROOT/work/results/l4_residual_l3_trace/tb.log" --output "$ROOT/reports/execution/l4_pool_residual_result.json"
echo L4_POOL_RESIDUAL_COMPLETE_GATE_PASS
