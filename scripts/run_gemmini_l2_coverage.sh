#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
GROOT=${GEMMINI_TEST_ROOT:-$ROOT/work/upstream/chipyard_gemmini/generators/gemmini/software/gemmini-rocc-tests}
SIM_ROOT=${GEMMINI_SIM_ROOT:-$ROOT/work/upstream/chipyard_gemmini/sims/verilator}
TOOL_ROOT=${RISCV_TOOL_ROOT:-$ROOT/work/toolchain/apt-riscv/usr}
OUT=${OUT:-$ROOT/work/results/l2_gemmini_v2_coverage}
DASM=${SPIKE_DASM:-$ROOT/work/toolchain/riscv/bin/spike-dasm}
mkdir -p "$OUT"
[[ -x "$TOOL_ROOT/bin/riscv64-unknown-elf-gcc" ]] || { echo missing RISC-V GCC >&2;exit 2; }
[[ -x "$SIM_ROOT/simulator-chipyard.harness-GemminiRocketConfig" ]] || { echo missing Gemmini simulator >&2;exit 2; }
TMPBIN=$(mktemp -d);trap 'rm -rf "$TMPBIN"' EXIT
ln -s "$TOOL_ROOT/bin/riscv64-unknown-elf-as" "$TMPBIN/as"
ln -s "$TOOL_ROOT/bin/riscv64-unknown-elf-ld" "$TMPBIN/ld"
COMMON=$GROOT/riscv-tests/benchmarks/common
compile(){
  local source=$1 output=$2
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$ROOT/scripts/run_memory_capped.sh" \
    "$TOOL_ROOT/bin/riscv64-unknown-elf-gcc" -B"$TMPBIN/" \
    -isystem "$TOOL_ROOT/lib/picolibc/riscv64-unknown-elf/include" \
    -DPREALLOCATE=1 -DMULTITHREAD=1 -mcmodel=medany -std=gnu99 -O2 -ffast-math \
    -fno-common -fno-builtin-printf -fno-tree-loop-distribute-patterns \
    -march=rv64gc -Wa,-march=rv64gc -I"$GROOT/riscv-tests" -I"$GROOT/riscv-tests/env" \
    -I"$GROOT" -I"$COMMON" -DID_STRING=coverage -DPRINT_TILE=0 -nostdlib \
    -nostartfiles -static -T "$COMMON/test.ld" -DBAREMETAL=1 "$source" \
    "$COMMON"/*.c "$COMMON"/*.S -lgcc -o "$output"
}
run(){
  local elf=$1 name=$2
  local trace="$OUT/$name.trace" log="$OUT/$name.log"
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$ROOT/scripts/run_memory_capped.sh" \
    "$SIM_ROOT/simulator-chipyard.harness-GemminiRocketConfig" +permissive +dramsim \
    +dramsim_ini_dir="$ROOT/work/upstream/chipyard_gemmini/generators/testchipip/src/main/resources/dramsim2_ini" \
    +max-cycles=10000000 +loadmem="$elf" +verbose +permissive-off "$elf" \
    </dev/null 2> >("$DASM" >"$trace") | tee "$log"
}
compile "$ROOT/tests/gemmini_l2_no_bias_ws_equivalence.c" "$OUT/no_bias_ws-baremetal"
run "$OUT/no_bias_ws-baremetal" no_bias_ws
grep -q GEMMINI_L2_NO_BIAS_WS_PASS "$OUT/no_bias_ws.log"
compile "$ROOT/tests/gemmini_l2_conv1x1_equivalence.c" "$OUT/conv1x1-baremetal"
run "$OUT/conv1x1-baremetal" conv1x1
grep -q GEMMINI_L2_CONV1X1_PASS "$OUT/conv1x1.log"
PYTHONPATH="$ROOT/src" MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
  "$ROOT/scripts/run_memory_capped.sh" python3 "$ROOT/scripts/audit_gemmini_l2_v2_coverage.py" \
  --result-root "$OUT" --output "$OUT/result.json"
echo GEMMINI_L2_COVERAGE_PASS
