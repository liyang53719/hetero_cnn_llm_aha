#!/usr/bin/env bash
# Actual default-off Host V -> StreamingDense -> retained Matrix -> pinned iDMA.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
BUILD_ONLY=0
if [[ ${1:-} == --build-only ]];then
 BUILD_ONLY=1;shift;OUT=${1:?absolute NEW build output};BURST=${2:-0};FIXTURE=
else
 OUT=${1:?absolute NEW output};FIXTURE=${2:?source-authenticated fixture};BURST=${3:-0}
 [[ -f "$FIXTURE/manifest.json" ]] || exit 2
fi
[[ "$OUT" = /* && ! -e "$OUT" && "$BURST" =~ ^[01]$ ]] || exit 2
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA;exit 77; }
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 [[ -d "$OFFLINE_TOOLS/jars" ]] || { echo BLOCKED_PINNED_OFFLINE_TOOLS;exit 77; }
else
 command -v sbt >/dev/null || { echo BLOCKED_MISSING_SBT;exit 77; }
fi
mkdir -p "$OUT";trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
elif [[ -z ${CHISEL_FIRTOOL_PATH:-} ]] && command -v firtool >/dev/null;then
 export CHISEL_FIRTOOL_PATH=$(dirname "$(command -v firtool)")
fi
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O0 OPT_SLOW=-O0"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare_hardfloat.log" 2>&1
if (( ! BUILD_ONLY ));then python3 "$P/scripts/verify_host_bf16_v_fixture.py" "$FIXTURE" >"$OUT/fixture_admission.json";fi
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
if (( BUILD_ONLY ));then python3 "$P/scripts/host_bf16_v_toolchain.py" before "$OUT/toolchain_before.json";fi
# Own compilation recipe retains the pinned catalog and uses the workspace cap.
if [[ -n ${OFFLINE_TOOLS:-} ]];then
python3 - "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS" <<'PY'
import hashlib,json,subprocess,sys
from pathlib import Path
root,out,hf,tools=map(lambda s:Path(s).resolve(),sys.argv[1:])
sys.path.insert(0,str(root/'chisel/continuous_prefill/scripts'))
from production_source_identity import sources
jars=[p for p in sorted((tools/'jars').glob('*.jar')) if '_2.12' not in p.name and not p.name.startswith(('scala-library-2.12','scala-reflect-2.12','scala-compiler-2.12'))]
cp=':'.join(map(str,jars));(out/'classpath.txt').write_text(cp)
(out/'compiler_jars.sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in jars},indent=2)+'\n')
(out/'main_sources.txt').write_text('\n'.join(map(str,sources(root,hf)))+'\n');(out/'classes').mkdir()
cmd=['java','-Xmx1500m','-XX:ActiveProcessorCount=2','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+str(tools/'jars/chisel-plugin_2.13.16-6.7.0.jar'),'-language:reflectiveCalls','-d',str(out/'classes'),'@'+str(out/'main_sources.txt')]
with (out/'compile.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
PY
CP=$(cat "$OUT/classpath.txt")
java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$OUT/classes:$CP" heteronpu.continuous.EmitHostBf16V "$OUT/generated" "$BURST" >"$OUT/emit.log" 2>&1
else
 # A fresh task-local cache must never add test/compiler dependencies to the
 # separately locked arithmetic/candidate Maven cache.
 export COURSIER_CACHE="$OUT/maven"
 (cd "$P";sbt -batch -J-Xmx1500m -J-XX:ActiveProcessorCount=2 \
   "-Dsbt.global.base=$OUT/sbt/global" "-Dsbt.boot.directory=$OUT/sbt/boot" \
   "-Dsbt.ivy.home=$OUT/sbt/ivy" compile \
   "runMain heteronpu.continuous.EmitHostBf16V $OUT/generated $BURST") >"$OUT/compile_emit.log" 2>&1
 python3 - "$OUT" <<'PY_DEPS'
from pathlib import Path
import hashlib,json,sys
out=Path(sys.argv[1]);jars=sorted((out/'maven').rglob('*.jar'))
if not jars:raise ValueError('missing isolated SBT compiler dependency receipt')
(out/'compiler_jars.sha256.json').write_text(json.dumps({str(p.relative_to(out/'maven')):hashlib.sha256(p.read_bytes()).hexdigest() for p in jars},indent=2)+'\n')
PY_DEPS
fi
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"
export RETAINED_SKIP_CLOCK=0;source "$P/scripts/retained_sources.sh"
# Verilator 5.032 hierarchy child argument files omit options nested in -f.
# Repeat the verified filelist's include/define options explicitly, unchanged.
mapfile -t IDMA_OPTIONS < <(grep -E '^\+(incdir|define)\+' "$OUT/idma.f" | sort -u)
JOBS=${BUILD_JOBS:-1};((JOBS>=1&&JOBS<=2))||exit 2
set +e
verilator --cc --exe --assert --comp-limit-parens 16 --output-split 3000 --output-split-cfuncs 200 -Wno-fatal --top-module HostBlockTop -CFLAGS '-O2 -std=c++17 -ffp-contract=off -fno-fast-math' -j "$JOBS" --Mdir "$OUT/obj" --hierarchical "$P/tests/native_weight_hierarchy.vlt" "${RETAINED_SOURCES[@]}" "${IDMA_OPTIONS[@]}" -f "$OUT/idma.f" "$OUT/generated/HostBlockTop.sv" "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$P/tests/host_bf16_v.cpp" >"$OUT/build.log" 2>&1
code=$?;set -e;echo "$code" >"$OUT/initial_verilation.exit"
if ((code));then
 # Recover only the observed resource failure after the parent elaborator
 # exits. Existing generated child arguments/RTL remain untouched.
 if grep -q 'Verilator threw signal 9' "$OUT/build.log" && [[ -s "$OUT/obj/VHostBlockTop_hier.mk" ]];then
  make -C "$OUT/obj" -f VHostBlockTop_hier.mk -j1 hier_verilation >"$OUT/recovery_verilation.log" 2>&1
 else
  exit "$code"
 fi
fi
make -C "$OUT/obj" -f VHostBlockTop_hier.mk -j "$JOBS" hier_build >"$OUT/make.log" 2>&1
if (( BUILD_ONLY ));then
 python3 "$P/scripts/host_bf16_v_toolchain.py" after "$OUT"
 python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" >"$OUT/build_source_verification.log"
 python3 - "$OUT" "$HARDFLOAT_SOURCE" <<'PY_BUILD'
from pathlib import Path
import hashlib,json,sys
out,hf=map(Path,sys.argv[1:]);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=dict(status='BUILT_HOST_V_ONLY_NOT_NUMERICAL_PASS',numerical_pass=False,
 binary_sha256=sha(out/'obj/VHostBlockTop'),rtl_sha256=sha(out/'generated/HostBlockTop.sv'),
 hardfloat_source=str(hf.resolve()),initial_verilation_exit=int((out/'initial_verilation.exit').read_text()))
(out/'build_ready.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
PY_BUILD
 exit 0
fi
for MODE in pass last-write-error activation-read-error;do
 "$OUT/obj/VHostBlockTop" "$FIXTURE" "$OUT/$MODE" "$MODE" >"$OUT/$MODE.log" 2>&1
 cat "$OUT/$MODE.log"
done
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 "$P/scripts/verify_host_bf16_v_fixture.py" "$FIXTURE" >"$OUT/fixture_final_verification.json"
python3 - "$OUT" "$FIXTURE" <<'PY'
from pathlib import Path
import hashlib,json,sys
out,fixture=map(Path,sys.argv[1:]);source=json.loads((fixture/'manifest.json').read_text())
for name,entry in source['files'].items():
 data=(fixture/name).read_bytes()
 if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('fixture drift '+name)
actual=(out/'pass/actual.bf16le').read_bytes();reference=(out/'pass/reference.bf16le').read_bytes()
if actual!=reference or len(actual)!=source['token_count']*1024:raise ValueError('numerical output mismatch')
line=next((x for x in (out/'pass.log').read_text().splitlines() if x.startswith('HOST_BF16_V_PASS ')),None)
if line is None:raise ValueError('missing numerical completion')
metrics=dict(x.split('=',1) for x in line.split()[1:])
if metrics['native_operator_gate']!='PASS' or metrics['canonical_bit_differences']!='0':raise ValueError('numerical gate failed')
for mode in ('last-write-error','activation-read-error'):
 if 'HOST_BF16_V_FAULT_PASS' not in (out/(mode+'.log')).read_text():raise ValueError('missing fault completion')
report=dict(status='PASS_PRODUCTION_HOST_V_ONLY',fixture_sha256=hashlib.sha256((fixture/'manifest.json').read_bytes()).hexdigest(),
 token_count=source['token_count'],token_base=source['token_base'],variant=source['variant'],phase=source['phase'],
 canonical_bit_differences=0,native_operator_gate_pass=True,native_bit_differences=int(metrics['native_bit_differences']),
 native_max_abs=float(metrics['native_max_abs']),native_mean_abs=float(metrics['native_mean_abs']),
 binary_sha256=hashlib.sha256((out/'obj/VHostBlockTop').read_bytes()).hexdigest(),
 rtl_sha256=hashlib.sha256((out/'generated/HostBlockTop.sv').read_bytes()).hexdigest(),
 source_immutability_verified=True,initial_verilation_exit=int((out/'initial_verilation.exit').read_text()),actual_sha256=hashlib.sha256(actual).hexdigest(),
 native_full_block_gate_pass=source['native_full_block_gate_pass'],
 official_manifest_sha256=source['official_manifest_sha256'],cross_host_byte_equivalence_claimed=False,
 fresh_official_executions=source['fresh_official_executions'],reused_official_executions=source['reused_official_executions'],
 experimental_default_off=True,q_k_supported=False,full_block_supported=False,
 actual_host_root=True,logical_matrix_engines=1,physical_matrix_slices=8,pinned_idma_instances=1)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
PY
