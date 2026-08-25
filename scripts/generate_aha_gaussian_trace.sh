#!/usr/bin/env bash
# Export pinned AHA Gaussian map/PnR artifacts for L2 wrapper trace analysis.
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
AHA_ROOT=${AHA_ROOT:-"$PROJECT_ROOT/work/upstream/aha"}
AHA_IMAGE=${AHA_IMAGE:-stanfordaha/garnet@sha256:a8784f2cfe96609a7e4403c29f6a82bd00c882c8564ef747541f78be75fa2b2b}
AHA_WIDTH=${AHA_WIDTH:-4}
AHA_HEIGHT=${AHA_HEIGHT:-16}
AHA_CPUSET=${AHA_CPUSET:-8-23}
OUT=${OUT:-"$PROJECT_ROOT/work/generated/l2_aha_gaussian_trace"}

command -v docker >/dev/null || { echo "Docker is required" >&2; exit 2; }
[[ "$AHA_IMAGE" == *@sha256:* ]] || { echo "AHA_IMAGE must be digest-pinned" >&2; exit 2; }
[[ -d "$AHA_ROOT/.git" ]] || { echo "AHA_ROOT is not a git checkout" >&2; exit 2; }
[[ -z "$(git -C "$AHA_ROOT" status --porcelain)" ]] || { echo "AHA tree is dirty" >&2; exit 3; }

mkdir -p "$OUT"
python3 "$PROJECT_ROOT/scripts/convert_aha_svh_to_h.py" \
  --source-root "$PROJECT_ROOT/work/generated/l2_aha_garnet_4x16/collateral" \
  --output-dir "$OUT/control_headers"
host_commit=$(git -C "$AHA_ROOT" rev-parse HEAD)
image_commit=$(docker run --rm --entrypoint /bin/bash "$AHA_IMAGE" -lc 'git -C /aha rev-parse HEAD')
[[ "$host_commit" == "$image_commit" ]] || {
  echo "AHA image/source commit mismatch: host=$host_commit image=$image_commit" >&2
  exit 4
}
printf '%s\n' "$AHA_IMAGE" > "$OUT/image.ref"
docker image inspect "$AHA_IMAGE" --format '{{index .RepoDigests 0}}' > "$OUT/image.digest"
printf '%s\n' "$host_commit" > "$OUT/aha.commit"

docker run --rm --cpuset-cpus "$AHA_CPUSET" \
  -v "$OUT:/out" -v "$OUT/control_headers:/control_headers:ro" \
  -v "$PROJECT_ROOT/scripts/aha_dump_control.c:/aha_dump_control.c:ro" \
  -w /aha "$AHA_IMAGE" bash -lc "
  set -euo pipefail
  export PATH=/aha/bin:\$PATH
  /aha/bin/python -m pip install --disable-pip-version-check psutil==7.2.2
  app=/aha/Halide-to-Hardware/apps/hardware_benchmarks/apps/gaussian
  /aha/bin/aha map apps/gaussian | tee /out/gaussian_map.log
  /aha/bin/aha pnr apps/gaussian --width $AHA_WIDTH --height $AHA_HEIGHT | tee /out/gaussian_pnr.log
  gcc -std=c11 /aha_dump_control.c /aha/garnet/tests/test_app/lib/*.c \
    -I/aha/garnet/tests/test_app/lib \
    -I/control_headers -o /tmp/aha_dump_control 2>&1 | tee /out/control_compile.log
  /tmp/aha_dump_control \$app/bin/design_meta.json $AHA_WIDTH 2>&1 | tee /out/control_dump.log
  sed -n 's/^AHA_CONTROL_JSON=//p' /out/control_dump.log | tail -n 1 > /out/control_table.json
  test -s /out/control_table.json
  test -d \$app/bin
  rm -rf /out/app_bin
  mkdir -p /out/app_bin
  tar -C \$app/bin -cf - . | tar -C /out/app_bin -xf -
  cd /out
  find app_bin -type f -print0 | sort -z | xargs -0 sha256sum > app_bin.sha256
  find app_bin -type f -printf '%p\\n' | sort > app_bin.files
" | tee "$OUT/docker.log"

python3 - "$OUT" <<'PY'
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
files = [line for line in (out / "app_bin.files").read_text().splitlines() if line]
needles = ("bitstream", ".bs", "design", "meta", "placement")
interesting = [name for name in files if any(token in name.lower() for token in needles)]
result = {
    "status": "PASS",
    "scope": "official Gaussian map/PnR artifact export only; wrapper equivalence remains open",
    "file_count": len(files),
    "interesting_files": interesting,
    "control_table": json.loads((out / "control_table.json").read_text()),
}
(out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, sort_keys=True))
PY

echo AHA_L2_GAUSSIAN_TRACE_EXPORT_PASS
