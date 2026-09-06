#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Chisel is the source of truth. Never patch the emitted SystemVerilog.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
PROJECT="$ROOT/chisel/continuous_prefill"
MODE=${1:-tiny}
OUT=${2:?usage: run_qwen2_block_verified.sh tiny|real OUTPUT_DIRECTORY [TOKENS] [READONLY_ARENA]}
TOKENS=${3:-16}
ARENA=${4:-synthetic}
case "$MODE" in tiny|real) ;; *) echo 'invalid mode' >&2; exit 2;; esac
[[ "$TOKENS" =~ ^[0-9]+$ ]] && (( TOKENS >= 1 && TOKENS <= 1024 )) || { echo 'tokens must be 1..1024' >&2; exit 2; }
[[ ! -e "$OUT" ]] || { echo 'refuse to overwrite an earlier verification directory' >&2; exit 2; }
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
for tool in java sbt verilator g++ python3; do command -v "$tool" > /dev/null || { echo "BLOCKED: missing $tool" >&2; exit 77; }; done
if [[ "$ARENA" != synthetic ]]; then
  [[ -f "$ARENA" ]] || { echo 'readonly arena not found' >&2; exit 2; }
  ARENA=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$ARENA")
fi
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
bash "$PROJECT/scripts/prepare_hardfloat.sh" > "$OUT/prepare.log" 2>&1
export MAKEFLAGS="${MAKEFLAGS:-} CFG_CXXFLAGS_PCH_I=-include"
export JVM_OPTS=${JVM_OPTS:--Xmx5G -Xss4M -XX:ActiveProcessorCount=4}
export SBT_OPTS=${SBT_OPTS:--Dsbt.supershell=false -Dsbt.task.cpus=4}
git -C "$ROOT" rev-parse HEAD > "$OUT/source_commit.txt"
git -C "$ROOT" status --porcelain > "$OUT/worktree_before.txt"
(cd "$ROOT"; git ls-files -z chisel/continuous_prefill chisel/p0_safety/src/main/scala integration/gemmini/EmitHeteroBF16Fma.scala integration/gemmini/EmitHeteroFP32Alu.scala | xargs -0 sha256sum) > "$OUT/sources.sha256"
verilator --version > "$OUT/verilator.txt"
java -version 2> "$OUT/java.txt"
cd "$PROJECT"
sbt -batch compile Test/compile test 2>&1 | tee "$OUT/chisel_tests.log"
EXTRA=''; [[ "$MODE" != tiny ]] || EXTRA=' --tiny'
sbt -batch "runMain heteronpu.continuous.EmitQwenBlock $OUT/generated$EXTRA" 2>&1 | tee "$OUT/emit.log"
[[ -s "$OUT/generated/Qwen2ContinuousBlock.sv" && -s "$OUT/generated/block_layout.h" && -s "$OUT/generated/layout.json" ]]
verilator --cc --exe --build --assert -Wno-fatal --top-module Qwen2ContinuousBlock \
  -CFLAGS "-O2 -std=c++17 -ffp-contract=off -I$OUT/generated" -j 3 \
  --Mdir "$OUT/obj" "$OUT/generated/Qwen2ContinuousBlock.sv" \
  "$PROJECT/tests/qwen2_block.cpp" 2>&1 | tee "$OUT/build.log"
EXE="$OUT/obj/VQwen2ContinuousBlock"
if [[ "$MODE" == tiny ]]; then
  for n in 1 2 17 33; do "$EXE" "$n" synthetic 2>&1 | tee "$OUT/block_${n}.log"; done
  for check in repeat write-error tag-error; do "$EXE" 2 "$check" 2>&1 | tee "$OUT/${check}.log"; done
else
  "$EXE" "$TOKENS" "$ARENA" 2>&1 | tee "$OUT/block_${TOKENS}.log"
fi
(cd "$ROOT"; sha256sum -c "$OUT/sources.sha256") > "$OUT/source_immutability.log"
python3 - "$OUT" "$MODE" "$TOKENS" "$ARENA" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
out=Path(sys.argv[1]); mode=sys.argv[2]; n=int(sys.argv[3]); arena=sys.argv[4]
runs={}
for p in sorted(out.glob('block_*.log')):
    text=p.read_text(); phases=[int(x) for x in re.findall(r'STAGE_CHECK phase=(\d+)',text)]
    if phases!=list(range(15)):
        raise RuntimeError(f'{p.name}: incomplete or duplicate stage coverage {phases}')
    runs[p.name]={'phases':phases,'log_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
if not runs: raise RuntimeError('no numerical block runs')
r={'status':'PASS_CONTINUOUS_FUNCTIONAL_QWEN2_BLOCK','source_commit':(out/'source_commit.txt').read_text().strip(),
   'mode':mode,'tokens':n if mode=='real' else [1,2,17,33], 'runs':runs,
   'source_of_truth':'Chisel','data_continuity':'DUT writes committed on memory response; consumers read actual output',
   'weights':'synthetic' if arena=='synthetic' else 'supplied readonly packed arena; provenance requires separate manifest',
   'matrix_lanes':16,'canonical_512_mac_path':False,'command128_integrated':False,'pinned_idma_axi_integrated':False,
   'full_network':False,'dc_timing_pass':False,'target_clock_hz':800000000,
   'generated_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'generated').iterdir() if p.is_file()}}
(out/'RESULT.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
PY
