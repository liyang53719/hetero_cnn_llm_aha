#!/usr/bin/env bash
set -euo pipefail

IMAX_ROOT=${IMAX_ROOT:?set IMAX_ROOT to the cloned IMAX3-LLM directory}
OUT=${OUT:-"$PWD/work/results/imax3_audit"}
RUN_BUILD=${RUN_BUILD:-0}
mkdir -p "$OUT"

git -C "$IMAX_ROOT" rev-parse HEAD > "$OUT/commit.txt"
find "$IMAX_ROOT" -type f \( -name '*.v' -o -name '*.sv' -o -name '*.vhd' -o -name '*.scala' \) \
  -not -path '*/.git/*' | sort > "$OUT/hardware_sources.txt"
find "$IMAX_ROOT" -type f \( -name '*.o' -o -name '*.a' -o -name '*.so' -o -name '*.bin' \) \
  -not -path '*/.git/*' | sort > "$OUT/prebuilt_artifacts.txt"
grep -RInE 'GGML_OP_MUL_MAT|SwiGLU|Qwen|IMAX' "$IMAX_ROOT" \
  --exclude-dir=.git --include='*.c' --include='*.cpp' --include='*.h' --include='*.md' \
  > "$OUT/kernel_inventory.txt" || true

if [[ "$RUN_BUILD" == 1 ]]; then
  cmake -S "$IMAX_ROOT" -B "$OUT/build" -DCMAKE_BUILD_TYPE=Release
  cmake --build "$OUT/build" -j"$(nproc)"
fi

python3 - "$OUT" <<'PY'
import json, pathlib, sys
out=pathlib.Path(sys.argv[1])
def lines(name):
    p=out/name
    return len([x for x in p.read_text(errors='ignore').splitlines() if x.strip()])
result={
  "status":"PASS",
  "hardware_source_files":lines("hardware_sources.txt"),
  "prebuilt_artifacts":lines("prebuilt_artifacts.txt"),
  "kernel_inventory_hits":lines("kernel_inventory.txt"),
  "decision":"reuse software offload/kernel mapping only unless hardware_sources.txt proves otherwise"
}
(out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
PY
