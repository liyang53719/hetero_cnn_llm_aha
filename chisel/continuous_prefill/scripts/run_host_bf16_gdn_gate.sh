#!/usr/bin/env bash
# Production GDN build only; profile is explicit and never implies numerical PASS.
# Same HostTop, StreamingDense, MatrixPipelineService and one pinned iDMA.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW build output};BURST=${2:-0};PROFILE=${3:-dense-conv}
[[ $# -le 3 ]] || exit 2
case "$PROFILE" in
 dense-conv) EMITTER=EmitHostBf16Gdn;DRIVER=host_bf16_gdn.cpp ;;
 core) EMITTER=EmitHostBf16GdnCore;DRIVER=host_bf16_gdn_core.cpp ;;
 block) EMITTER=EmitHostBf16GdnBlock;DRIVER=host_bf16_gdn_block.cpp ;;
 *) echo UNKNOWN_GDN_BUILD_PROFILE >&2;exit 2 ;;
esac
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" && "$BURST" =~ ^[01]$ ]] || exit 2
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA;exit 77; }
[[ ${BUILD_JOBS:-1} = 1 ]] || { echo SERIAL_BUILD_REQUIRED;exit 2; }
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 [[ -d "$OFFLINE_TOOLS/jars" ]] || { echo BLOCKED_PINNED_OFFLINE_TOOLS;exit 77; }
else
 command -v sbt >/dev/null || { echo BLOCKED_MISSING_SBT;exit 77; }
fi
record_verilator_elf() {
 python3 - "$P/scripts" "$1" <<'PY_TOOL'
from pathlib import Path
import json,os,shutil,sys
sys.path.insert(0,sys.argv[1])
from real2_ci import verilator_backend_identity
entry,backend=verilator_backend_identity(shutil.which('verilator'),Path(os.environ['VERILATOR_ROOT']))
Path(sys.argv[2]).write_text(json.dumps(dict(entrypoint=entry,actual_elf=backend),indent=2)+'\n')
PY_TOOL
}
mkdir -p "$OUT"
BUILD_PHASE=preflight
build_phase() {
 if [[ "$PROFILE" = block ]];then
  echo 0 >"$OUT/$BUILD_PHASE.exit"
  BUILD_PHASE=$1
  echo "$BUILD_PHASE" >"$OUT/build_phase.txt"
 fi
}
trap 'c=$?;echo "$c" >"$OUT/build.exit";if [[ "$PROFILE" = block ]];then echo "$c" >"$OUT/$BUILD_PHASE.exit";fi;exit "$c"' EXIT
if [[ -f "$ROOT/SNAPSHOT.json" ]];then cp "$ROOT/SNAPSHOT.json" "$OUT/source_snapshot.json";fi
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
elif [[ -z ${CHISEL_FIRTOOL_PATH:-} ]] && command -v firtool >/dev/null;then
 export CHISEL_FIRTOOL_PATH=$(dirname "$(command -v firtool)")
fi
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O0 OPT_SLOW=-O0"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare_hardfloat.log" 2>&1
export SOURCE_IDENTITY_SCOPE=full
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
# Add noncompiled serialization/build contracts to the same immutable map.
# Model capture/reference source identities are separately checked by the fixture verifier.
python3 - "$ROOT" "$OUT" "$PROFILE" <<'PY_IDENTITY'
from pathlib import Path
import hashlib,json,sys
root,out=map(Path,sys.argv[1:3]);profile=sys.argv[3];path=out/'sources.sha256.json';bound=json.loads(path.read_text())
if json.loads((out/'source_scope.json').read_text()).get('scope')!='full':raise ValueError('full GDN source scope required')
for name in ['run_host_bf16_gdn_gate.sh','host_bf16_gdn_descriptor.py','pack_host_bf16_gdn_fixture.py','verify_host_bf16_gdn_fixture.py']:
 if 'chisel/continuous_prefill/scripts/'+name not in bound:raise ValueError('missing GDN execution source: '+name)
if 'chisel/continuous_prefill/tests/host_bf16_gdn.cpp' not in bound:raise ValueError('missing actual GDN driver source')
extra=['chisel/continuous_prefill/config/host_bf16_gdn_descriptor_contract.json',
 'chisel/continuous_prefill/config/host_bf16_v_descriptor_contract.json',
 'chisel/continuous_prefill/build.sbt','chisel/continuous_prefill/project/build.properties',
 'src/heteronpu/abi_validation.py','src/heteronpu/command.py','src/heteronpu/descriptor_chain.py',
 'src/heteronpu/gemmini_descriptor_v2.py','src/heteronpu/gemmini_rocc_lowering.py']
if profile in ('core','block'):
 extra += ['chisel/continuous_prefill/config/host_bf16_gdn_core_descriptor_contract.json']
 for name in ['scripts/host_bf16_gdn_core_descriptor.py','scripts/pack_host_bf16_gdn_core_fixture.py','scripts/host_bf16_gdn_core_execution.py','tests/host_bf16_gdn_core.cpp']:
  if 'chisel/continuous_prefill/'+name not in bound:raise ValueError('missing GDN core execution source: '+name)
if profile=='block':
 extra += ['chisel/continuous_prefill/config/host_bf16_gdn_block_descriptor_contract.json',
  'chisel/continuous_prefill/scripts/gdn_dense_reference.c','scripts/matrix_norm_rope_reference.c']
 for name in ['scripts/host_bf16_gdn_block_descriptor.py','scripts/pack_host_bf16_gdn_block_fixture.py',
              'scripts/host_bf16_gdn_block_execution.py','scripts/gdn_dense_reference.py',
              'scripts/gdn_rmsnorm_reference.py','scripts/gdn_elementwise_reference.py',
              'scripts/host_bf16_qkv_reference.py','tests/host_bf16_gdn_block.cpp','tests/host_bf16_gdn_core.cpp']:
  if 'chisel/continuous_prefill/'+name not in bound:raise ValueError('missing GDN block execution source: '+name)
for name in extra:
 file=root/name
 if not file.is_file() or file.is_symlink():raise ValueError('missing exact source contract: '+name)
 bound[name]=hashlib.sha256(file.read_bytes()).hexdigest()
path.write_text(json.dumps(dict(sorted(bound.items())),indent=2)+'\n')
PY_IDENTITY
python3 "$P/scripts/host_bf16_v_toolchain.py" before "$OUT/toolchain_before.json"
record_verilator_elf "$OUT/actual_verilator_before.json"
git -C "$ROOT" rev-parse HEAD > "$OUT/source_base_commit.txt"
git -C "$ROOT" status --porcelain > "$OUT/worktree_before.txt"
# Own compilation recipe retains the pinned catalog and uses the workspace cap.
if [[ -n ${OFFLINE_TOOLS:-} ]];then
build_phase scala_compile
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
build_phase rtl_emit
java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$OUT/classes:$CP" "heteronpu.continuous.$EMITTER" "$OUT/generated" "$BURST" >"$OUT/emit.log" 2>&1
else
 # A fresh task-local cache must never add test/compiler dependencies to the
 # separately locked arithmetic/candidate Maven cache.
 export COURSIER_CACHE="$OUT/maven"
 build_phase scala_compile_rtl_emit
 (cd "$P";sbt -batch -J-Xmx1500m -J-XX:ActiveProcessorCount=2 \
   "-Dsbt.global.base=$OUT/sbt/global" "-Dsbt.boot.directory=$OUT/sbt/boot" \
   "-Dsbt.ivy.home=$OUT/sbt/ivy" compile \
   "runMain heteronpu.continuous.$EMITTER $OUT/generated $BURST") >"$OUT/compile_emit.log" 2>&1
 python3 - "$OUT" <<'PY_DEPS'
from pathlib import Path
import hashlib,json,sys
out=Path(sys.argv[1]);jars=sorted((out/'maven').rglob('*.jar'))
if not jars:raise ValueError('missing isolated SBT compiler dependency receipt')
(out/'compiler_jars.sha256.json').write_text(json.dumps({str(p.relative_to(out/'maven')):hashlib.sha256(p.read_bytes()).hexdigest() for p in jars},indent=2)+'\n')
PY_DEPS
fi
build_phase idma_prepare
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"
export RETAINED_SKIP_CLOCK=0;source "$P/scripts/retained_sources.sh"
# Verilator 5.032 hierarchy child argument files omit options nested in -f.
# Repeat the verified filelist's include/define options explicitly, unchanged.
mapfile -t IDMA_OPTIONS < <(grep -E '^\+(incdir|define)\+' "$OUT/idma.f" | sort -u)
JOBS=${BUILD_JOBS:-1};((JOBS>=1&&JOBS<=2))||exit 2
# Plan only, then release the initial elaborator before child Verilation.
# Keep the original Verilator argv and generated child argument files intact.
build_phase hierarchy_plan
set +e
env -u MFLAGS -u GNUMAKEFLAGS MAKEFLAGS=-n verilator --cc --exe --assert --comp-limit-parens 16 --output-split 3000 --output-split-cfuncs 200 -Wno-fatal --top-module HostBlockTop -CFLAGS '-O2 -std=c++17 -ffp-contract=off -fno-fast-math' -j "$JOBS" --Mdir "$OUT/obj" --hierarchical "$P/tests/native_weight_hierarchy.vlt" "${RETAINED_SOURCES[@]}" "${IDMA_OPTIONS[@]}" -f "$OUT/idma.f" "$OUT/generated/HostBlockTop.sv" "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$P/tests/$DRIVER" >"$OUT/build.log" 2>&1
code=$?;set -e;echo "$code" >"$OUT/initial_verilation.exit"
((code==0)) || exit "$code"
[[ -s "$OUT/obj/VHostBlockTop_hier.mk" && ! -e "$OUT/obj/VHostBlockTop.mk" ]] || { echo INVALID_HIERARCHY_PLAN >&2;exit 2; }
# Reject any child/top C++: phase 1 must have produced planning files only.
child_cpp=$(find "$OUT/obj" -name '*.cpp' -print -quit) || exit 2
[[ -z "$child_cpp" ]] || { echo UNEXPECTED_PLANNING_CPP >&2;exit 2; }
build_phase hierarchy_verilation
env -u MAKEFLAGS -u MFLAGS -u GNUMAKEFLAGS make -C "$OUT/obj" -f VHostBlockTop_hier.mk -j1 hier_verilation >"$OUT/hierarchy_verilation.log" 2>&1
build_phase native_compile
python3 "$P/scripts/build_host_hierarchy_bounded.py" "$OUT" --reserve-bytes "${BUILD_RESERVE_BYTES:-1073741824}" >"$OUT/make.log" 2>&1
build_phase receipt_verify
python3 "$P/scripts/host_bf16_v_toolchain.py" after "$OUT"
record_verilator_elf "$OUT/actual_verilator_after.json"
cmp "$OUT/actual_verilator_before.json" "$OUT/actual_verilator_after.json"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" >"$OUT/build_source_verification.log"
python3 - "$OUT" "$HARDFLOAT_SOURCE" "$PROFILE" <<'PY_BUILD'
from pathlib import Path
import hashlib,json,sys
out,hf=map(Path,sys.argv[1:3]);profile=sys.argv[3];core=profile in ('core','block');block=profile=='block';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
scope=json.loads((out/'generated/SCOPE.json').read_text())
if scope.get('experimental_bf16_gdn') is not True:raise ValueError('not a production GDN profile')
expected_scope='GDN_LAYER0_BLOCK_M1' if block else 'GDN_CORE_M1_BEFORE_OUTPUT_PROJECTION' if core else 'DENSE_QKV_CONV4_SILU_ONLY'
if scope.get('scope')!=expected_scope or scope.get('policy_version')!=(3 if block else 2 if core else 1):raise ValueError('GDN build profile/scope mismatch')
if bool(scope.get('experimental_gdn_core',False))!=core:raise ValueError('GDN core profile mismatch')
if bool(scope.get('experimental_gdn_block',False))!=block:raise ValueError('GDN block profile mismatch')
report=dict(status=('BUILT_HOST_GDN_BLOCK_ONLY_NOT_NUMERICAL_PASS' if block else 'BUILT_HOST_GDN_CORE_ONLY_NOT_NUMERICAL_PASS' if core else 'BUILT_HOST_GDN_DENSE_CONV_ONLY_NOT_NUMERICAL_PASS'),numerical_pass=False,build_profile=profile,
 binary_sha256=sha(out/'obj/VHostBlockTop'),rtl_sha256=sha(out/'generated/HostBlockTop.sv'),
 source_base_commit=(out/'source_base_commit.txt').read_text().strip(),
 source_manifest_sha256=sha(out/'sources.sha256.json'),hardfloat_source=str(hf.resolve()),
 actual_verilator=json.loads((out/'actual_verilator_after.json').read_text()),
 initial_verilation_exit=int((out/'initial_verilation.exit').read_text()),
 source_snapshot_manifest_sha256=sha(out/'source_snapshot.json') if (out/'source_snapshot.json').is_file() else None,
 experimental_default_off=True,operations=(['dense_qkv','dense_z','dense_ab','conv4_silu','input_prep','recurrent_fp32','gated_norm','state_fence'] if core else ['dense_qkv','conv4_silu']),
 recurrent_state_supported=core,gated_norm_supported=core,full_block_supported=block,scalar_service_shared=True)
if block:
 report.update(operations=['input_norm','dense_qkv','dense_z','dense_ab','conv4_silu','input_prep',
  'recurrent_fp32','gated_norm','dense_o','residual1','post_norm','dense_gate','dense_up','silu_mul',
  'dense_down','residual2','state_fence'],input_norm_dut=True,o_projection_dut=True,residual_dut=True,ffn_dut=True)
(out/'build_ready.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
PY_BUILD
