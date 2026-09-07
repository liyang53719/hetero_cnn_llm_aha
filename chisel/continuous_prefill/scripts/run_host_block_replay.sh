#!/usr/bin/env bash
# Replay NEW descriptor/data layouts against exactly the same generated DUT.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
BASE=${1:?previous completed build};OUT=${2:?absolute NEW output};TOKENS=${3:-17};RELOCATE=${4:-9467985920};SWAP=${5:-swap}
[[ -f "$BASE/obj/VHostBlockTop__ALL.a" && "$OUT" = /* && ! -e "$OUT" ]] || exit 2
mkdir -p "$OUT";trap 'code=$?;echo "$code" >"$OUT/gate.exit";exit "$code"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
python3 "$P/scripts/pack_owner_block_fixture.py" "$BASE/generated/owner_shape.h" "$OUT/fixture_initial" --tokens "$TOKENS" --relocate "$RELOCATE" >"$OUT/packing.log"
if [[ "$SWAP" = swap ]];then python3 "$P/scripts/swap_owner_fixture.py" "$OUT/fixture_initial" "$OUT/fixture";else cp -a "$OUT/fixture_initial" "$OUT/fixture";fi
mkdir "$OUT/generated";cp "$BASE/generated/owner_shape.h" "$BASE/generated/HostBlockTop.sv" "$BASE/generated/SCOPE.json" "$OUT/generated/"
cp "$BASE/sources.sha256.json" "$BASE/hardfloat.sha256.json" "$BASE/idma_identity.json" "$OUT/"
python3 - "$BASE" "$OUT" "$P" <<'PY'
from pathlib import Path
import hashlib,json,sys
base,out,p=map(Path,sys.argv[1:]);files=[base/'obj/VHostBlockTop__ALL.a',base/'obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a',base/'generated/HostBlockTop.sv',p/'tests/host_block_commands.cpp',out/'fixture/owner_fixture.h']
(out/'REPLAY_PROVENANCE.json').write_text(json.dumps({'same_generated_dut':True,'source_build':str(base),'files':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in files}},indent=2)+'\n')
PY
VR=${VERILATOR_ROOT:?}
g++ -O3 -std=c++17 -ffp-contract=off -fno-fast-math -I"$BASE/obj" -I"$VR/include" -I"$VR/include/vltstd" -I"$OUT/generated" -I"$OUT/fixture" \
 "$P/tests/host_block_commands.cpp" "$BASE/obj/VHostBlockTop__ALL.a" "$BASE/obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a" \
 "$BASE/obj/verilated.o" "$BASE/obj/verilated_dpi.o" "$BASE/obj/verilated_threads.o" -pthread -latomic -o "$OUT/VHostBlockTop" >"$OUT/link.log" 2>&1
set +e
"$OUT/VHostBlockTop" "$OUT/fixture" "$OUT/tensors" >"$OUT/run.log" 2>&1
c=$?;set -e;echo "$c" >"$OUT/simulation.exit";cat "$OUT/run.log";((c==0))||exit "$c"
python3 "$P/scripts/verify_host_block_gate.py" "$OUT" >"$OUT/verification.log";cat "$OUT/verification.log"
