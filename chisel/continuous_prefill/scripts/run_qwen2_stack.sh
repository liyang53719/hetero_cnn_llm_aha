#!/usr/bin/env bash
set -euo pipefail
if (( $# < 2 || $# > 4 )); then echo 'usage: run_qwen2_stack.sh tiny|real NEW_OUTPUT [TOKENS] [LAYERS]' >&2; exit 2; fi
MODE=$1
case "$MODE" in tiny) TOKENS=${3:-17}; LAYERS=${4:-4};; real) TOKENS=${3:-1}; LAYERS=${4:-2};; *) echo 'mode must be tiny or real' >&2; exit 2;; esac
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
PROJECT="$ROOT/chisel/continuous_prefill"
OUT=$(realpath -m "$2")
[[ ! -e "$OUT" ]] || { echo 'refuse to overwrite prior evidence' >&2; exit 2; }
[[ "$TOKENS" =~ ^[0-9]+$ && "$LAYERS" =~ ^[0-9]+$ ]] || exit 2
(( TOKENS > 0 && LAYERS > 0 && LAYERS <= 28 )) || exit 2
if [[ "$MODE" = tiny ]]; then (( TOKENS <= 33 )) || exit 2; else (( TOKENS <= 1024 )) || exit 2; fi
for tool in java sbt verilator g++ python3; do command -v "$tool" >/dev/null || { echo "BLOCKED: missing $tool" >&2; exit 77; }; done
mkdir -p "$OUT"
trap 'code=$?; printf "%s\n" "$code" > "$OUT/exit_code.txt"' EXIT
export JVM_OPTS=${JVM_OPTS:--Xmx5G -Xss4M -XX:ActiveProcessorCount=4}
export MAKEFLAGS="${MAKEFLAGS:-} OPT_FAST=-O1 OPT_SLOW=-O1"
bash "$PROJECT/scripts/prepare_hardfloat.sh"
git -C "$ROOT" rev-parse HEAD > "$OUT/source_commit.txt"
git -C "$ROOT" status --porcelain > "$OUT/worktree_status.txt"
(cd "$ROOT"; git ls-files -z chisel/continuous_prefill chisel/p0_safety/src/main/scala integration/gemmini/EmitHeteroFP32Alu.scala integration/gemmini/EmitHeteroBF16Fma.scala | xargs -0 sha256sum) > "$OUT/sources.sha256"
verilator --version > "$OUT/verilator.txt"
cd "$PROJECT"
sbt -batch compile Test/compile 2>&1 | tee "$OUT/compile.log"
ARGS="--layers=$LAYERS"; [[ "$MODE" != tiny ]] || ARGS="$ARGS --tiny"
sbt -batch "runMain heteronpu.continuous.EmitQwenStack $OUT/generated $ARGS" 2>&1 | tee "$OUT/emit.log"
python3 scripts/generate_stack_harness.py "$OUT/qwen2_stack.cpp"
verilator --cc --exe --build --assert -Wno-fatal --top-module Qwen2LayerStack \
  -CFLAGS "-O2 -std=c++17 -ffp-contract=off -I$OUT/generated" -j "${JOBS:-4}" \
  --Mdir "$OUT/obj" "$OUT/generated/Qwen2LayerStack.sv" "$OUT/qwen2_stack.cpp" 2>&1 | tee "$OUT/build.log"
"$OUT/obj/VQwen2LayerStack" "$TOKENS" 2>&1 | tee "$OUT/simulation.log"
(cd "$ROOT"; sha256sum --check "$OUT/sources.sha256") > "$OUT/source_recheck.log"
python3 - "$OUT" "$MODE" "$TOKENS" "$LAYERS" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
out=Path(sys.argv[1]);mode=sys.argv[2];tokens=int(sys.argv[3]);layers=int(sys.argv[4]);text=(out/'simulation.log').read_text()
markers=re.findall(r'^CONTINUOUS_QWEN2_STACK_PASS (.*)$',text,re.M)
if len(markers)!=1 or re.search(r'(^|\n)(FAIL|MISMATCH|%Error)',text):raise RuntimeError('missing/duplicate success or failure log')
r=dict(re.findall(r'(\w+)=([^\s]+)',markers[0]))
expected={'tokens':tokens,'layers':layers,'stages':15*layers,'hidden':64 if mode=='tiny' else 1536,'ffn':128 if mode=='tiny' else 8960,'checked_fp32':tokens*layers*(1056 if mode=='tiny' else 41472),'bit_diffs':0,'host_intermediate_writes':0,'canonical_512_array':0}
for key,value in expected.items():
    if int(r.get(key,'-1'))!=value:raise RuntimeError('counter mismatch: '+key)
if int(r['cycles'])<=0 or (layers>1 and int(r['previous_layer_read_bytes'])<=0):raise RuntimeError('invalid execution/dependency counts')
r.update(status='PASS_CONTINUOUS_SYNTHETIC_STACK_NOT_PRODUCTION_NPU',source_commit=(out/'source_commit.txt').read_text().strip(),official_weights=False,official_forward=False,pinned_idma=False,dc=False,clock_target_hz=800000000)
r['artifacts']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['simulation.log','compile.log','generated/Qwen2LayerStack.sv','generated/block_layout.h','qwen2_stack.cpp','sources.sha256']}
(out/'RESULT.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
PY
