#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/operator_dc_800mhz/endpoints/SfuOwnerFlatChildren;R=$ROOT/scripts/run_memory_capped.sh;DC=/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell;DB=/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db
mkdir -p "$OUT"
specs=(
 "operator_sfu_vector_endpoint_v3:$ROOT/work/results/operator_dc_800mhz/endpoints/SfuVector/operator_sfu_vector_endpoint_v3.ddc"
 "operator_sfu_scalar_endpoint_v3:$ROOT/work/results/operator_dc_800mhz/endpoints/SfuScalarFlat/operator_sfu_scalar_endpoint_v3.ddc"
 "operator_sfu_norm_endpoint_v3:$ROOT/work/results/operator_dc_800mhz/endpoints/SfuNorm/operator_sfu_norm_endpoint_v3.ddc"
 "operator_sfu_rope_endpoint_v3:$ROOT/work/results/operator_dc_800mhz/endpoints/SfuRope/operator_sfu_rope_endpoint_v3.ddc"
 "operator_sfu_online_softmax_endpoint_v3:$ROOT/work/results/operator_dc_800mhz/endpoints/SfuOnlineSoftmax/operator_sfu_online_softmax_endpoint_v3.ddc"
 "operator_sfu_gate_endpoint_v3:$ROOT/work/results/operator_dc_800mhz/endpoints/SfuGateBottomUp/operator_sfu_gate_endpoint_v3.ddc"
 "operator_sfu_pwl_endpoint_v3:$ROOT/work/results/operator_dc_800mhz/endpoints/SfuPwl/operator_sfu_pwl_endpoint_v3.ddc"
)
for spec in "${specs[@]}";do top=${spec%%:*};input=${spec#*:};dir=$OUT/$top;mkdir -p "$dir";MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s env TOP="$top" CHILD_DDC="$input" OUT_DDC="$dir/$top.flat.ddc" OUT_REPORT="$dir/status.txt" STD_CELL_DB="$DB" "$DC" -64bit -f "$ROOT/dc/flatten_operator_child_ddc.tcl" >"$dir/dc.log" 2>&1;grep -q '^HIERARCHICAL_CELLS=0$' "$dir/status.txt";grep -q '^UNMAPPED_CELLS=0$' "$dir/status.txt";done
echo SFU_CHILD_DDC_FLATTEN_PASS children=7
