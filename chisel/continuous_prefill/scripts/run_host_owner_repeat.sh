#!/usr/bin/env bash
# Two independent cold requests, one unchanged DUT, no reset between requests.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
BASE=${1:?verified tiny16 build};OUT=${2:?absolute NEW output}
BASE=$(cd "$BASE" && pwd)
[[ "$OUT" = /* && ! -e "$OUT" && $(cat "$BASE/gate.exit") = 0 ]] || exit 2
mkdir -p "$OUT";trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
python3 - "$BASE" "$P" "$OUT" <<'PY'
from pathlib import Path
import hashlib,json,sys
base,p,out=map(Path,sys.argv[1:]);fixture=json.loads((base/'fixture/manifest.json').read_text())
if (fixture['shape']['H'],fixture['shape']['F'],fixture['tokens'])!=(64,128,16):raise SystemExit('tiny16 build required')
paths=[base/'obj/VHostBlockTop__ALL.a',base/'obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a',base/'generated/HostBlockTop.sv',base/'generated/owner_shape.h',base/'fixture/owner_fixture.h',base/'fixture/host_commands.bin',base/'fixture/host_descriptors.bin',p/'tests/host_block_commands.cpp',p/'tests/host_owner_repeat.cpp']
sources=json.loads((base/'sources.sha256.json').read_text())
harness=p/'tests/host_block_commands.cpp'
if hashlib.sha256(harness.read_bytes()).hexdigest()!=sources['chisel/continuous_prefill/tests/host_block_commands.cpp']:raise SystemExit('baseline harness changed')
(out/'INPUTS_SHA256.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in paths},indent=2)+'\n')
PY
VR=${VERILATOR_ROOT:?}
g++ -O3 -std=c++17 -ffp-contract=off -fno-fast-math \
 -I"$BASE/obj" -I"$VR/include" -I"$VR/include/vltstd" -I"$BASE/generated" -I"$BASE/fixture" -I"$P/tests" \
 "$P/tests/host_owner_repeat.cpp" "$BASE/obj/VHostBlockTop__ALL.a" \
 "$BASE/obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a" \
 "$BASE/obj/verilated.o" "$BASE/obj/verilated_dpi.o" "$BASE/obj/verilated_threads.o" \
 -pthread -latomic -o "$OUT/VHostOwnerRepeat" >"$OUT/build.log" 2>&1
set +e
"$OUT/VHostOwnerRepeat" "$BASE/fixture" "$OUT/tensors" >"$OUT/run.log" 2>&1
code=$?;set -e;echo "$code" >"$OUT/simulation.exit";cat "$OUT/run.log";((code==0)) || exit "$code"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import hashlib,json,re,struct,sys
base,out=map(Path,sys.argv[1:]);text=(out/'run.log').read_text()
expected='HOST_OWNER_REPEAT_PASS requests=2 epochs=2 host_commands=42 owner_jobs=38 checked_fp32=39936 bit_differences=0 reset_between_requests=0 changed_input=1 '
if sum(line.startswith(expected) for line in text.splitlines())!=1 or re.search('HOST_OWNER_REPEAT_FAIL|HOST_BLOCK_FAIL|%Error|Fatal',text):raise SystemExit('repeat receipt rejected')
pcs=[int(x) for x in re.findall(r'^OWNER_COMPLETION pc=(\d+) ',text,re.M)]
if pcs!=list(range(21))*2:raise SystemExit('incomplete request completions')
fixture=json.loads((base/'fixture/manifest.json').read_text());values=0;outputs={}
for request in ['first','second']:
    root=out/'tensors'/request
    for op in fixture['schedule']:
        for name in op['outputs']:
            a=root/(name+'_actual.f32le');b=root/(name+'_reference.f32le');raw=a.read_bytes()
            if len(raw)!=fixture['tensors'][name]['words']*4 or raw!=b.read_bytes():raise SystemExit('repeat binary mismatch')
            import math
            if not all(math.isfinite(v[0]) for v in struct.iter_unpack('<f',raw)):raise SystemExit('nonfinite repeat output')
            values+=len(raw)//4;outputs[str(a.relative_to(out))]=hashlib.sha256(raw).hexdigest()
if values!=39936:raise SystemExit('repeat element count')
for name in ['input_x.f32le','y_actual.f32le']:
    if (out/'tensors/first'/name).read_bytes()==(out/'tensors/second'/name).read_bytes():raise SystemExit('unchanged second request')
for path,digest in json.loads((out/'INPUTS_SHA256.json').read_text()).items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise SystemExit('input changed during repeat')
report={'status':'PASS_TWO_COLD_HOST_OWNER_REQUESTS_NO_RESET','requests':2,'host_commands':42,'checked_fp32':values,'bit_differences':0,'reset_between_requests':0,'changed_input':True,'actual_sha256':outputs,'scope':'tiny16; not two layers, cache persistence, official weights, or real16 signoff'}
with (out/'RESULT.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
print(json.dumps(report,indent=2))
PY
