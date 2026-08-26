#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l4_conv3x3_relu_requant_l3_trace;R=$ROOT/scripts/run_memory_capped.sh
"$ROOT/scripts/run_l4_conv3x3_relu_requant_payload.sh"
"$ROOT/scripts/run_l4_matrix_trace_case.sh" tb_l4_conv3x3_requant_relu_l3_trace "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$ROOT/work/toolchain/cnn_py312/bin/python" "$ROOT/scripts/audit_l4_conv3x3_relu_requant_complete.py" --payload "$ROOT/work/results/l4_conv3x3_relu_requant/payload_result.json" --trace-log "$OUT/tb.log" --descriptor-log "$OUT/descriptor.log" --output "$ROOT/reports/execution/l4_conv3x3_relu_requant_result.json"
echo L4_CONV3X3_REQUANT_RELU_COMPLETE_GATE_PASS
