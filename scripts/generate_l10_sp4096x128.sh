#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
COMPILER=${ARM_SP_COMPILER:-/home/yang/tools/arm/tsmc/cln22ul/sram_sp_uhde_svt_mvt/r1p0/bin/sram_sp_uhde_svt_mvt}
OUT=${OUT:-$ROOT/work/generated/l10_sram/ct_sp_4096x128wm_base_0p8v_tt25}
CORNER=tt_typical_0p80v_0p80v_25c
NAME=ctsp4096x128wm

mkdir -p "$OUT"

run_timing_or_model() {
  local generator=$1
  shift
  (
    cd "$OUT"
    MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=2G MEMORY_MAX=3G \
      "$ROOT/scripts/run_memory_capped.sh" "$COMPILER" "$generator" \
      -words 4096 -bits 128 -mux 8 -mvt BASE -corners "$CORNER" \
      -write_mask on -instname "$NAME" "$@"
  ) >"$OUT/${generator//-/_}.log" 2>&1
}

run_physical() {
  local generator=$1
  (
    cd "$OUT"
    MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=2G MEMORY_MAX=3G \
      "$ROOT/scripts/run_memory_capped.sh" "$COMPILER" "$generator" \
      -words 4096 -bits 128 -mux 8 -mvt BASE -write_mask on -instname "$NAME"
  ) >"$OUT/${generator//-/_}.log" 2>&1
}

run_timing_or_model liberty -libertyviewstyle nldm -libname ctsp4096x128wm
run_timing_or_model verilog
run_physical gds2
run_physical lef-fp

echo L10_SP4096X128_GENERATION_PASS
