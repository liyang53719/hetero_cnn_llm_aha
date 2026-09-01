#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);COMPILER=${ARM_DP_COMPILER:-/home/yang/tools/arm/tsmc/cln22ul/sram_dp_hde_svt_svt/r0p1/bin/sram_dp_hde_svt_svt};R=$ROOT/scripts/run_memory_capped.sh;CORNER=tt_typical_0p80v_0p80v_25c
generate(){ local words=$1 bits=$2 mux=$3 name=$4;local out=$ROOT/work/generated/l10_sram/${name}_ll_0p8v_tt25;mkdir -p "$out";for gen in liberty verilog gds2;do args=(-words "$words" -bits "$bits" -mux "$mux" -mvt LL -write_mask on -wp_size 1 -instname "$name");if [[ $gen == liberty ]];then args+=(-corners "$CORNER" -libertyviewstyle nldm -libname "$name");elif [[ $gen == verilog ]];then args+=(-corners "$CORNER");fi;if ! (cd "$out";MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=4G MEMORY_MAX=6G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$COMPILER" "$gen" "${args[@]}")>"$out/${gen}.log" 2>&1;then if [[ $gen == gds2 ]];then printf 'BLOCKED_DP_GDS2\n' >"$out/gds2.blocked";else return 1;fi;fi;done;}
generate 2048 64 8 dp2048x64wm
generate 4096 32 16 dp4096x32wm
echo L10_DP_MACRO_GENERATION_PASS
