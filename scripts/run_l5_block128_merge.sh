#!/usr/bin/env bash
set -euo pipefail
: "${HETERONPU_FP_FILELIST:?set generated FP primitive filelist}"
command -v verilator >/dev/null || { echo WAIT_LOCAL_AGENT_PUSH:Verilator >&2; exit 42; }
verilator --binary --timing -Wall -Wno-fatal -f "$HETERONPU_FP_FILELIST" \
 rtl/sfu/fp32_mlo_merge_coeff.sv rtl/sfu/fp32_mlo_merge_beat.sv \
 rtl/sfu/fp32_mlo_summary_merge_stream.sv tb/tb_fp32_mlo_summary_merge_stream.sv \
 --top-module tb_fp32_mlo_summary_merge_stream -Mdir work/generated/block128
work/generated/block128/Vtb_fp32_mlo_summary_merge_stream
