#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l3_command_fabric}
MACRO=${MACRO:-$ROOT/work/generated/l10_sram/ct_sp_4096x128wm_base_0p8v_tt25/ctsp4096x128wm.v}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
RUN="$ROOT/scripts/run_memory_capped.sh";mkdir -p "$OUT";test -f "$MACRO"
COMMON=(
  "$ROOT/rtl/memory/ct_sp4096x128_macro_wrapper.sv"
  "$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/top/command_dispatch.sv"
  "$ROOT/rtl/integration/command_event_scoreboard_sram.sv"
  "$ROOT/rtl/integration/command_event_frontend_sram.sv"
  "$ROOT/rtl/integration/engine_completion_rr_arbiter.sv"
  "$ROOT/rtl/fabric/shared_l2_client_arbiter.sv"
  "$ROOT/rtl/integration/hetero_l3_command_fabric.sv"
  "$ROOT/tb/tb_hetero_l3_command_fabric.sv"
)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$VERILATOR" --lint-only --timing -Wall --top-module tb_hetero_l3_command_fabric \
  "$ROOT/tb/ctsp4096x128wm_lint_stub.sv" "${COMMON[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$VERILATOR" --binary --timing --assert -Wall -Wno-fatal \
  -DARM_DISABLE_EMA_CHECK -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  -GTARGET=100000 --top-module tb_hetero_l3_command_fabric \
  --Mdir "$OUT/obj_100k" -o tb_100k "$MACRO" "${COMMON[@]}" \
  >"$OUT/verilator_100k_build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$OUT/obj_100k/tb_100k" | tee "$OUT/verilator_100k.log"
grep -q "HETERO_L3_COMMAND_FABRIC_PASS commands=100003 completions=100003 illegal=1" \
  "$OUT/verilator_100k.log"
echo L3_COMMAND_FABRIC_GATE_PASS
