#!/usr/bin/env bash
# Link only a diagnostic harness against an already-verified arithmetic DUT.
# Frozen generated RTL and retained libraries are never edited or regenerated.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
BASE=${1:?verified arithmetic gate directory};OUT=${2:?absolute NEW directory}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2;exit 2; }
[[ -d "$BASE" ]] || { echo BLOCKED_MISSING_ARITHMETIC_BUILD >&2;exit 77; }
BASE=$(cd "$BASE" && pwd)
[[ $(cat "$BASE/gate.exit") = 0 && $(cat "$BASE/simulation.exit") = 0 ]] || exit 2
mkdir -p "$(dirname "$OUT")";mkdir "$OUT";trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
LIBS=("$BASE/obj/VMatrix4096ArithmeticProbe__ALL.a" "$BASE/obj/Vqwen2_matrix_command_endpoint/libqwen2_matrix_command_endpoint.a" "$BASE/obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a" "$BASE/obj/verilated.o" "$BASE/obj/verilated_dpi.o" "$BASE/obj/verilated_threads.o")
for path in "${LIBS[@]}";do [[ -f "$path" ]] || { echo BLOCKED_MISSING_COMPILED_DUT >&2;exit 77; };done
python3 "$P/scripts/verify_matrix4096_arithmetic.py" "$BASE" --output "$OUT/ARITHMETIC_RECHECK.json" > "$OUT/arithmetic_recheck.log"
sha256sum "${LIBS[@]}" "$BASE/generated/Matrix4096ArithmeticProbe.sv" "$P/tests/matrix4096_arithmetic.cpp" "$P/tests/matrix4096_service_interval.cpp" > "$OUT/frozen_inputs.sha256"
g++ -O3 -std=c++17 -ffp-contract=off -fno-fast-math -I"$BASE/obj" -I"$VERILATOR_ROOT/include" -I"$VERILATOR_ROOT/include/vltstd" -I"$P/tests" "$P/tests/matrix4096_service_interval.cpp" "${LIBS[@]}" -pthread -latomic -o "$OUT/VServiceDiagnostic" > "$OUT/link.log" 2>&1
set +e
"$OUT/VServiceDiagnostic" "$OUT/outputs" > "$OUT/run.log" 2>&1
c=$?;set -e;echo "$c" > "$OUT/simulation.exit";cat "$OUT/run.log";((c==0))||exit "$c"
sha256sum -c "$OUT/frozen_inputs.sha256" > "$OUT/immutability.log"
python3 "$P/scripts/verify_matrix4096_service.py" "$OUT" --output "$OUT/RESULT.json" > "$OUT/verification.log"
cat "$OUT/verification.log"
