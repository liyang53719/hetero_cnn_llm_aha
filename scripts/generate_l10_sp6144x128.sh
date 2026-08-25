#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
COMPILER=${ARM_SP_COMPILER:-/home/yang/tools/arm/tsmc/cln22ul/sram_sp_uhde_svt_mvt/r1p0/bin/sram_sp_uhde_svt_mvt}
OUT=${OUT:-$ROOT/work/generated/l10_sram/l2_sp_6144x128_base_0p8v_tt25}
CORNER=tt_typical_0p80v_0p80v_25c
NAME=l2sp6144x128

mkdir -p "$OUT"

run_generator() {
  local generator=$1
  shift
  (
    cd "$OUT"
    MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=2G MEMORY_MAX=3G \
      "$ROOT/scripts/run_memory_capped.sh" "$COMPILER" "$generator" \
      -words 6144 -bits 128 -mux 8 -mvt BASE -corners "$CORNER" \
      -instname "$NAME" "$@"
  ) >"$OUT/${generator//-/_}.log" 2>&1
}

run_generator liberty -libertyviewstyle nldm -libname l2sp6144x128
run_generator verilog
# Physical views do not depend on the timing corner.
(
  cd "$OUT"
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=2G MEMORY_MAX=3G \
    "$ROOT/scripts/run_memory_capped.sh" "$COMPILER" gds2 \
    -words 6144 -bits 128 -mux 8 -mvt BASE -instname "$NAME"
) >"$OUT/gds2.log" 2>&1
# LEF has no timing corner, but keeps the same BASE physical selection.
(
  cd "$OUT"
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=2G MEMORY_MAX=3G \
    "$ROOT/scripts/run_memory_capped.sh" "$COMPILER" lef-fp \
    -words 6144 -bits 128 -mux 8 -mvt BASE -instname "$NAME"
) >"$OUT/lef_fp.log" 2>&1

printf 'L10_SP6144X128_GENERATION_PASS\n'
