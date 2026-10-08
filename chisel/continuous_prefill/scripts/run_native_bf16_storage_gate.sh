#!/usr/bin/env bash
# Actual Dense controller/SRAMs with injected DDR and Matrix results.
# Source/protocol/storage proof only. No retained-iDMA or arithmetic signoff.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output directory}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || exit 2
[[ ${BUILD_JOBS:-1} =~ ^[12]$ ]] || { echo 'BUILD_JOBS must be 1 or 2'; exit 2; }
for t in java python3 g++ make; do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$t";exit 77; }; done
mkdir -p "$OUT"
trap 'code=$?;echo "$code" >"$OUT/gate.exit";exit "$code"' EXIT
CACHE=${TOOL_CACHE:-$ROOT/work/rope_hardware_oracle}
export CHISEL_FIRTOOL_PATH=${CHISEL_FIRTOOL_PATH:-$CACHE/deps/firtool/org.chipsalliance/llvm-firtool/linux-x64/bin}
VERILATOR=${VERILATOR:-$CACHE/bin/verilator}
[[ -x "$CHISEL_FIRTOOL_PATH/firtool" && -x "$VERILATOR" ]] || { echo BLOCKED_LOCAL_TOOL_CACHE;exit 77; }
# A precompiled production catalog is optional. Validate every production source
# digest before using it; the fallback compiles current source, without downloads.
if [[ -n ${PRODUCTION_CATALOG:-} ]]; then
 python3 - "$ROOT" "$PRODUCTION_CATALOG" <<'PY'
import hashlib,json,pathlib,sys
root,cat=map(pathlib.Path,sys.argv[1:])
for name,digest in json.loads((cat/'sources.sha256.json').read_text()).items():
    p=pathlib.Path(name)
    if not p.is_absolute(): p=root/p
    if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise SystemExit('SOURCE_CHANGED: '+str(p))
PY
 CLASSES="$PRODUCTION_CATALOG/classes";CP=$(cat "$PRODUCTION_CATALOG/classpath.txt")
else
 export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$CACHE/deps/berkeley-hardfloat-c1105e6ac6a0dd90fc80893efc4830ab609005d3}
 python3 - "$ROOT" "$OUT" "$CACHE" "$HARDFLOAT_SOURCE" <<'PY'
import hashlib,json,pathlib,sys
root,out,cache,hf=map(pathlib.Path,sys.argv[1:])
sys.path.insert(0,str(root/'chisel/continuous_prefill/scripts'))
from production_source_identity import sources
jars=sorted((cache/'coursier/https/repo.maven.apache.org/maven2').rglob('*.jar'))
jars=[p for p in jars if '_2.12' not in p.name and not p.name.startswith(('scala-library-2.12','scala-reflect-2.12','scala-compiler-2.12'))]
if not any(p.name=='scala-compiler-2.13.16.jar' for p in jars):raise SystemExit('BLOCKED_COMPILER_CACHE')
(out/'classpath.txt').write_text(':'.join(map(str,jars)))
files=sources(root,hf)
(out/'main_sources.txt').write_text(''.join(str(p)+'\n' for p in files))
(out/'sources.sha256.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2)+'\n')
PY
 CP=$(cat "$OUT/classpath.txt");CLASSES="$OUT/classes";mkdir "$CLASSES"
 PLUGIN=$(find "$CACHE/coursier" -name chisel-plugin_2.13.16-6.7.0.jar -print -quit)
 java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$CP" scala.tools.nsc.Main -classpath "$CP" -Xplugin:"$PLUGIN" -language:reflectiveCalls -d "$CLASSES" @"$OUT/main_sources.txt" >"$OUT/compile.log" 2>&1
fi
PLUGIN=$(find "$CACHE/coursier" -name chisel-plugin_2.13.16-6.7.0.jar -print -quit)
python3 - "$P" "$OUT" <<'PY'
import hashlib,json,pathlib,sys
p,out=map(pathlib.Path,sys.argv[1:])
files=[p/'src/main/scala/heteronpu/continuous'/n for n in ['StreamingDense.scala','DenseReadPlanner.scala','QwenOwnerProtocol.scala','BurstProtocol.scala','Protocol.scala']]
files += [p/'src/test/scala/heteronpu/continuous/NativeBf16StorageProbe.scala',p/'tests/native_bf16_storage.cpp',p/'scripts/run_native_bf16_storage_gate.sh']
(out/'tested_sources.sha256.json').write_text(json.dumps({str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in files},indent=2)+'\n')
PY
mkdir "$OUT/testclasses"
java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$CP" scala.tools.nsc.Main -classpath "$CLASSES:$CP" -Xplugin:"$PLUGIN" -language:reflectiveCalls -d "$OUT/testclasses" "$P/src/test/scala/heteronpu/continuous/NativeBf16StorageProbe.scala" >"$OUT/test_compile.log" 2>&1
# Bound expression depth in generated C++; the hardware/RTL stays unchanged.
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O0 OPT_SLOW=-O0"
for mode in 0 1; do
 M="$OUT/mode$mode";mkdir "$M"
 java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$OUT/testclasses:$CLASSES:$CP" heteronpu.continuous.EmitNativeBf16StorageProbe "$M/generated" "$mode" >"$M/emit.log" 2>&1
 "$VERILATOR" --comp-limit-parens 16 --cc --exe --build --assert -Wno-fatal --top-module NativeBf16StorageProbe --output-split 3000 --output-split-cfuncs 200 -CFLAGS '-O0 -std=c++17' -j "${BUILD_JOBS:-1}" --Mdir "$M/obj" "$M/generated/NativeBf16StorageProbe.sv" "$P/tests/native_bf16_storage.cpp" >"$M/build.log" 2>&1
 set +e
 "$M/obj/VNativeBf16StorageProbe" "$mode" >"$M/run.log" 2>&1
 code=$?;set -e;echo "$code" >"$M/simulation.exit";cat "$M/run.log";((code==0))||exit "$code"
done
python3 - "$OUT" <<'PY'
import hashlib,json,pathlib,sys
out=pathlib.Path(sys.argv[1])
for name,digest in json.loads((out/'tested_sources.sha256.json').read_text()).items():
 if hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()!=digest:raise SystemExit('SOURCE_CHANGED: '+name)
for mode in (0,1):
 text=(out/f'mode{mode}/run.log').read_text()
 if text.count('NATIVE_BF16_STORAGE_CASE_PASS')!=46 or f'NATIVE_BF16_STORAGE_PROTOCOL_PASS burst={mode} cases=46 faults=19' not in text:raise SystemExit('MISSING_COVERAGE')
result=dict(passed=True,scalar_and_burst=True,cases=92,actual_controller=True,
    injected_matrix_results=True,real_idma=False,arithmetic_signoff=False,
    sources=json.loads((out/'tested_sources.sha256.json').read_text()),
    logs={f'mode{m}/run.log':hashlib.sha256((out/f'mode{m}/run.log').read_bytes()).hexdigest() for m in (0,1)})
(out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
print('NATIVE_BF16_STORAGE_GATE_PASS scalar_and_burst=1 cases=92 arithmetic_signoff=0 real_idma=0')
PY
