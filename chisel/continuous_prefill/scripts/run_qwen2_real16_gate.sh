#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Fixed target, not a model/shape sweep. No generated SystemVerilog is modified.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
PROJECT="$ROOT/chisel/continuous_prefill"
OUT=${1:?usage: run_qwen2_real16_gate.sh /absolute/new/output/directory}
[[ "$OUT" = /* && ! -e "$OUT" ]] || { echo 'output must be an absolute new directory' >&2; exit 2; }
for t in java sbt verilator g++ python3 git; do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL: $t" >&2; exit 77; }; done
mkdir -p "$OUT"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
bash "$PROJECT/scripts/prepare_hardfloat.sh" >"$OUT/prepare.log" 2>&1
export MAKEFLAGS="${MAKEFLAGS:-} CFG_CXXFLAGS_PCH_I=-include"
export JVM_OPTS=${JVM_OPTS:--Xmx3G -Xss4M -XX:ActiveProcessorCount=3}
git -C "$ROOT" rev-parse HEAD >"$OUT/source_commit.txt"
git -C "$ROOT" status --porcelain >"$OUT/worktree_before.txt"
python3 - "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" <<'PY'
from pathlib import Path
import hashlib,json,sys
root,out,hf=map(Path,sys.argv[1:])
paths=[]
for folder in ['chisel/continuous_prefill/src','chisel/continuous_prefill/scripts','chisel/continuous_prefill/tests','chisel/p0_safety/src/main/scala']:
    paths.extend(p for p in (root/folder).rglob('*') if p.is_file() and p.suffix in {'.scala','.cpp','.py','.sh'})
paths.extend(root/'integration/gemmini'/n for n in ['EmitHeteroBF16Fma.scala','EmitHeteroFP32Alu.scala'])
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
(out/'sources.sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
(out/'hardfloat.sha256.json').write_text(json.dumps({str(p.relative_to(hf)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((hf/'hardfloat/src/main/scala').glob('*.scala'))},indent=2)+'\n')
PY
java -version 2>"$OUT/java.txt"; verilator --version >"$OUT/verilator.txt"; g++ --version >"$OUT/cxx.txt"
python3 - "$PROJECT" "$HARDFLOAT_SOURCE" "$OUT" <<'PYLIST'
from pathlib import Path
import sys
project,hf,out=map(Path,sys.argv[1:])
names='TensorProgram RetainedMatrix Protocol ElementwiseMemoryEngine BlockFloat BlockAxiAdapter EmitQwenBlock MemoryToAxi Qwen2Block EmitContinuous DenseTileCursor BlockWritebackFence'.split()
main=[project/'src/main/scala/heteronpu/continuous'/f'{n}.scala' for n in names]
main+=sorted((project.parent/'p0_safety/src/main/scala').rglob('*.scala'))
main+=sorted((hf/'hardfloat/src/main/scala').glob('*.scala'))
main+=[project.parents[1]/'integration/gemmini'/n for n in ['EmitHeteroFP32Alu.scala','EmitHeteroBF16Fma.scala']]
suites='BlockWritebackFenceSpec TensorProgramSpec DenseTileCursorSpec BlockScalarFloatSpec BlockAxiAdapterSpec QwenBlockLayoutSpec'.split()
tests=[project/'src/test/scala/heteronpu/continuous'/f'{n}.scala' for n in suites]
for name,files in [('main_sources.txt',main),('test_sources.txt',tests)]:
    if any(not f.is_file() for f in files):raise SystemExit('Missing scoped source')
    (out/name).write_text(''.join(str(f.resolve())+'\n' for f in files))
PYLIST
cd "$PROJECT"
MAIN_SETTING="set Compile / unmanagedSources := IO.readLines(file(\"$OUT/main_sources.txt\")).map(file)"
TEST_SETTING="set Test / unmanagedSources := IO.readLines(file(\"$OUT/test_sources.txt\")).map(file)"
sbt -batch "$MAIN_SETTING" "$TEST_SETTING" compile Test/compile 'testOnly heteronpu.continuous.BlockWritebackFenceSpec heteronpu.continuous.TensorProgramSpec heteronpu.continuous.DenseTileCursorSpec heteronpu.continuous.BlockScalarFloatSpec heteronpu.continuous.BlockAxiAdapterSpec heteronpu.continuous.QwenBlockLayoutSpec' 2>&1 | tee "$OUT/chisel_tests.log"
sbt -batch "$MAIN_SETTING" "runMain heteronpu.continuous.EmitQwenBlock $OUT/generated" 2>&1 | tee "$OUT/emit.log"
verilator --cc --exe --build --assert -Wno-fatal --top-module Qwen2ContinuousBlock \
  -CFLAGS "-O3 -std=c++17 -ffp-contract=off -fno-fast-math -I$OUT/generated" -j 3 \
  --Mdir "$OUT/obj" "$OUT/generated/Qwen2ContinuousBlock.sv" "$PROJECT/tests/qwen2_block_proof.cpp" 2>&1 | tee "$OUT/build.log"
set +e
QWEN_BLOCK_EVIDENCE_DIR="$OUT/tensors" "$OUT/obj/VQwen2ContinuousBlock" 16 synthetic 20260906 >"$OUT/run.log" 2>&1
code=$?
set -e
printf '%s\n' "$code" >"$OUT/simulation.exit"
cat "$OUT/run.log"
(( code == 0 )) || exit "$code"
python3 - "$ROOT" "$OUT" <<'PY'
from pathlib import Path
import hashlib,json,sys
root,out=map(Path,sys.argv[1:])
for path,digest in json.loads((out/'sources.sha256.json').read_text()).items():
    if hashlib.sha256((root/path).read_bytes()).hexdigest()!=digest:raise SystemExit('SOURCE_CHANGED: '+path)
PY
python3 "$PROJECT/scripts/verify_qwen2_real16.py" "$OUT" | tee "$OUT/verification.log"
