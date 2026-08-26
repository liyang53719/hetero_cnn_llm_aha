#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
GROOT=${GEMMINI_TEST_ROOT:-$ROOT/work/upstream/chipyard_gemmini/generators/gemmini/software/gemmini-rocc-tests}
SIM_ROOT=${GEMMINI_SIM_ROOT:-$ROOT/work/upstream/chipyard_gemmini/sims/verilator}
TOOL_ROOT=${RISCV_TOOL_ROOT:-$ROOT/work/toolchain/apt-riscv/usr}
PYTHON=${CNN_PYTHON:-$ROOT/work/toolchain/cnn_py312/bin/python}
DASM=${SPIKE_DASM:-$ROOT/work/toolchain/riscv/bin/spike-dasm}
OUT=${OUT:-$ROOT/work/results/l4_int8_gemm}
RUN="$ROOT/scripts/run_memory_capped.sh";mkdir -p "$OUT"
ELF="$OUT/int8_gemm-baremetal";TRACE="$OUT/int8_gemm.trace";LOG="$OUT/int8_gemm.log"
TMPBIN=$(mktemp -d);trap 'rm -rf "$TMPBIN"' EXIT
ln -s "$TOOL_ROOT/bin/riscv64-unknown-elf-as" "$TMPBIN/as"
ln -s "$TOOL_ROOT/bin/riscv64-unknown-elf-ld" "$TMPBIN/ld"
COMMON="$GROOT/riscv-tests/benchmarks/common"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$TOOL_ROOT/bin/riscv64-unknown-elf-gcc" -B"$TMPBIN/" \
  -isystem "$TOOL_ROOT/lib/picolibc/riscv64-unknown-elf/include" \
  -DPREALLOCATE=1 -DMULTITHREAD=1 -mcmodel=medany -std=gnu99 -O2 -ffast-math \
  -fno-common -fno-builtin-printf -fno-tree-loop-distribute-patterns \
  -march=rv64gc -Wa,-march=rv64gc -I"$GROOT/riscv-tests" -I"$GROOT/riscv-tests/env" \
  -I"$GROOT" -I"$COMMON" -I"$ROOT/tests" -DID_STRING=l4-int8-gemm -DPRINT_TILE=0 \
  -nostdlib -nostartfiles -static -T "$COMMON/test.ld" -DBAREMETAL=1 \
  "$ROOT/tests/gemmini_l4_int8_gemm.c" "$COMMON"/*.c "$COMMON"/*.S -lgcc -o "$ELF" \
  >"$OUT/compile.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$SIM_ROOT/simulator-chipyard.harness-GemminiRocketConfig" +permissive +dramsim \
  +dramsim_ini_dir="$ROOT/work/upstream/chipyard_gemmini/generators/testchipip/src/main/resources/dramsim2_ini" \
  +max-cycles=10000000 +loadmem="$ELF" +verbose +permissive-off "$ELF" \
  </dev/null 2> >("$DASM" >"$TRACE") | tee "$LOG"
grep -q GEMMINI_L4_INT8_GEMM_PASS "$LOG"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$PYTHON" "$ROOT/scripts/audit_l4_int8_gemm.py" --trace "$TRACE" \
  --run-log "$LOG" --elf "$ELF" --output "$OUT/payload_result.json"
echo L4_INT8_GEMM_PAYLOAD_GATE_PASS
