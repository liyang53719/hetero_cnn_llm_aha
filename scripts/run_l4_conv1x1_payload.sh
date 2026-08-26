#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd);OUT=${OUT:-$ROOT/work/results/l4_conv1x1};mkdir -p "$OUT"
GROOT=$ROOT/work/upstream/chipyard_gemmini/generators/gemmini/software/gemmini-rocc-tests
SIM=$ROOT/work/upstream/chipyard_gemmini/sims/verilator/simulator-chipyard.harness-GemminiRocketConfig
TOOLS=$ROOT/work/toolchain/apt-riscv/usr;DASM=$ROOT/work/toolchain/riscv/bin/spike-dasm
RUN=$ROOT/scripts/run_memory_capped.sh;PY=$ROOT/work/toolchain/cnn_py312/bin/python
ELF=$OUT/conv1x1-baremetal;TRACE=$OUT/conv1x1.trace;LOG=$OUT/conv1x1.log
TMP=$(mktemp -d);trap 'rm -rf "$TMP"' EXIT;ln -s "$TOOLS/bin/riscv64-unknown-elf-as" "$TMP/as";ln -s "$TOOLS/bin/riscv64-unknown-elf-ld" "$TMP/ld"
COMMON=$GROOT/riscv-tests/benchmarks/common
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" "$TOOLS/bin/riscv64-unknown-elf-gcc" -B"$TMP/" \
 -isystem "$TOOLS/lib/picolibc/riscv64-unknown-elf/include" -DPREALLOCATE=1 -DMULTITHREAD=1 -mcmodel=medany -std=gnu99 -O2 -ffast-math \
 -fno-common -fno-builtin-printf -fno-tree-loop-distribute-patterns -march=rv64gc -Wa,-march=rv64gc \
 -I"$GROOT/riscv-tests" -I"$GROOT/riscv-tests/env" -I"$GROOT" -I"$COMMON" -I"$ROOT/tests" -DID_STRING=l4-conv1x1 -DPRINT_TILE=0 \
 -nostdlib -nostartfiles -static -T "$COMMON/test.ld" -DBAREMETAL=1 "$ROOT/tests/gemmini_l4_conv1x1.c" "$COMMON"/*.c "$COMMON"/*.S -lgcc -o "$ELF" >"$OUT/compile.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" "$SIM" +permissive +dramsim \
 +dramsim_ini_dir="$ROOT/work/upstream/chipyard_gemmini/generators/testchipip/src/main/resources/dramsim2_ini" \
 +max-cycles=10000000 +loadmem="$ELF" +verbose +permissive-off "$ELF" </dev/null 2> >("$DASM" >"$TRACE") | tee "$LOG"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" "$PY" "$ROOT/scripts/audit_l4_conv1x1_payload.py" \
 --trace "$TRACE" --run-log "$LOG" --elf "$ELF" --vectors "$ROOT/tests/vectors/gemmini_descriptor_v2_programs.json" \
 --output "$OUT/payload_result.json"
echo L4_CONV1X1_PAYLOAD_GATE_PASS
