#!/usr/bin/env bash
set -euo pipefail

AHA_ROOT=${AHA_ROOT:?set AHA_ROOT to the cloned StanfordAHA/aha directory}
OUT=${OUT:-"$PWD/work/results/aha_baseline"}
IMAGE=${AHA_IMAGE:?set AHA_IMAGE to an immutable stanfordaha/garnet@sha256 digest}
WIDTH=${AHA_WIDTH:-4}
HEIGHT=${AHA_HEIGHT:-16}
CPUSET=${AHA_CPUSET:-8-23}
mkdir -p "$OUT"

command -v docker >/dev/null || { echo "Docker is required" >&2; exit 2; }
[[ "$IMAGE" == *@sha256:* ]] || { echo "AHA_IMAGE must be pinned by digest, not a mutable tag: $IMAGE" >&2; exit 2; }
docker pull "$IMAGE"
docker image inspect "$IMAGE" --format '{{index .RepoDigests 0}}' | tee "$OUT/image.digest"
git -C "$AHA_ROOT" rev-parse HEAD | tee "$OUT/aha.commit"
git -C "$AHA_ROOT" submodule status --recursive | tee "$OUT/submodules.txt"
if [[ -n "$(git -C "$AHA_ROOT" status --porcelain)" ]]; then
  echo "AHA tree is dirty before baseline reproduction" >&2
  exit 3
fi

# Mount the pinned checkout over /aha so the Docker image supplies tools, not source.
docker run --rm \
  --cpuset-cpus "$CPUSET" \
  -e TOOL=VERILATOR \
  -v "$AHA_ROOT:/aha" \
  -v "$OUT:/out" \
  -w /aha \
  "$IMAGE" bash -lc "
    set -euo pipefail
    rm -f garnet/garnet.v
    aha garnet --width $WIDTH --height $HEIGHT --verilog --use_sim_sram --glb_tile_mem_size 128
    test -s garnet/garnet.v
    sha256sum garnet/garnet.v | tee /out/garnet_rtl.sha256
    aha map apps/gaussian | tee /out/gaussian_map.log
    aha pnr apps/gaussian --width $WIDTH --height $HEIGHT | tee /out/gaussian_pnr.log
    aha test apps/gaussian | tee /out/gaussian_test.log
  " | tee "$OUT/docker.log"

python3 - "$OUT" <<'PY'
import json, pathlib, sys
out=pathlib.Path(sys.argv[1])
required=["garnet_rtl.sha256","gaussian_map.log","gaussian_pnr.log","gaussian_test.log"]
missing=[x for x in required if not (out/x).exists() or (out/x).stat().st_size == 0]
status={"status":"PASS" if not missing else "FAIL","missing":missing}
(out/"result.json").write_text(json.dumps(status,indent=2)+"\n")
if missing: raise SystemExit(1)
PY

echo AHA_BASELINE_PASS
