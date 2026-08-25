#!/usr/bin/env bash
set -euo pipefail

AHA_ROOT=${AHA_ROOT:?set AHA_ROOT to the cloned StanfordAHA/aha directory}
PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-"$PWD/work/results/aha_baseline"}
IMAGE=${AHA_IMAGE:?set AHA_IMAGE to an immutable stanfordaha/garnet@sha256 digest}
WIDTH=${AHA_WIDTH:-4}
HEIGHT=${AHA_HEIGHT:-16}
CPUSET=${AHA_CPUSET:-8-23}
SIM_TOOL=${AHA_TOOL:-VERILATOR}
VERILATOR_ROOT=${VERILATOR_ROOT:-"$PROJECT_ROOT/work/toolchain/conda"}
VCS_ROOT=${VCS_ROOT:-/home/yang/tools/synopsys/vcs/W-2024.09}
VCS_LICENSE=${VCS_LICENSE:-2700@host.docker.internal}
mkdir -p "$OUT"

command -v docker >/dev/null || { echo "Docker is required" >&2; exit 2; }
[[ "$IMAGE" == *@sha256:* ]] || { echo "AHA_IMAGE must be pinned by digest, not a mutable tag: $IMAGE" >&2; exit 2; }
case "$SIM_TOOL" in
  VERILATOR)
    test -x "$VERILATOR_ROOT/bin/verilator" || { echo "VERILATOR_ROOT must provide bin/verilator: $VERILATOR_ROOT" >&2; exit 2; }
    ;;
  VCS)
    test -x "$VCS_ROOT/bin/vcs" || { echo "VCS_ROOT must provide bin/vcs: $VCS_ROOT" >&2; exit 2; }
    ;;
  *)
    echo "AHA_TOOL must be VERILATOR or VCS, got: $SIM_TOOL" >&2
    exit 2
    ;;
esac
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker pull "$IMAGE"
fi
docker image inspect "$IMAGE" --format '{{index .RepoDigests 0}}' | tee "$OUT/image.digest"
git -C "$AHA_ROOT" rev-parse HEAD | tee "$OUT/aha.commit"
git -C "$AHA_ROOT" submodule status --recursive | tee "$OUT/submodules.txt"
if [[ -n "$(git -C "$AHA_ROOT" status --porcelain)" ]]; then
  echo "AHA tree is dirty before baseline reproduction" >&2
  exit 3
fi

# The pinned image contains the official compiler environment and generated
# Python build artifacts. Verify that its source commit exactly matches the
# clean host checkout, then run the image source in place; mounting over /aha
# would hide required tool/runtime artifacts and makes the baseline invalid.
image_commit=$(docker run --rm --entrypoint /bin/bash "$IMAGE" -lc 'git -C /aha rev-parse HEAD')
host_commit=$(git -C "$AHA_ROOT" rev-parse HEAD)
if [[ "$image_commit" != "$host_commit" ]]; then
  echo "AHA image/source commit mismatch: image=$image_commit host=$host_commit" >&2
  exit 4
fi
printf '%s\n' "$image_commit" | tee "$OUT/image_aha.commit"
docker run --rm --entrypoint /bin/bash "$IMAGE" -lc 'git -C /aha submodule status --recursive || true' > "$OUT/image_submodules.txt"

docker_args=(
  --rm
  --cpuset-cpus "$CPUSET"
  -e "TOOL=$SIM_TOOL"
  -v "$OUT:/out"
  -w /aha
)
if [[ "$SIM_TOOL" == VERILATOR ]]; then
  docker_args+=(
    -e "PATH=/host-verilator/bin:/aha/bin:/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    -e "LD_LIBRARY_PATH=/host-verilator/lib"
    -v "$VERILATOR_ROOT:/host-verilator:ro"
  )
else
  docker_args+=(
    --add-host=host.docker.internal:host-gateway
    -e VCS_ARCH_OVERRIDE=linux
    -e VCS_HOME=/host-vcs
    -e "SNPSLMD_LICENSE_FILE=$VCS_LICENSE"
    -e "PATH=/host-vcs/bin:/aha/bin:/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    -e "LD_LIBRARY_PATH=/host-vcs/linux/lib"
    -v "$VCS_ROOT:/host-vcs:ro"
  )
fi

docker run "${docker_args[@]}" \
  "$IMAGE" bash -lc "
    set -euo pipefail
    export PATH=/aha/bin:\$PATH
    if [[ \"$SIM_TOOL\" == VCS ]]; then
      dpkg --add-architecture i386
      apt-get update
      DEBIAN_FRONTEND=noninteractive apt-get install -y libelf1:i386
    fi
    # The image's entrypoint installs psutil with the system pip, while
    # garnet.py runs /aha/bin/python. Install it into that exact venv.
    /aha/bin/python -m pip install --disable-pip-version-check psutil==7.2.2
    rm -f garnet/garnet.v
    /aha/bin/aha garnet --width $WIDTH --height $HEIGHT --verilog --use_sim_sram --glb_tile_mem_size 128
    test -s garnet/garnet.v
    sha256sum garnet/garnet.v | tee /out/garnet_rtl.sha256
    /aha/bin/aha map apps/gaussian | tee /out/gaussian_map.log
    /aha/bin/aha pnr apps/gaussian --width $WIDTH --height $HEIGHT | tee /out/gaussian_pnr.log
    /aha/bin/aha test apps/gaussian | tee /out/gaussian_test.log
  " | tee "$OUT/docker.log"

python3 - "$OUT" "$SIM_TOOL" <<'PY'
import json, pathlib, sys
out=pathlib.Path(sys.argv[1])
tool=sys.argv[2]
required=["garnet_rtl.sha256","gaussian_map.log","gaussian_pnr.log","gaussian_test.log"]
missing=[x for x in required if not (out/x).exists() or (out/x).stat().st_size == 0]
status={"status":"PASS" if not missing else "FAIL","tool":tool,"missing":missing}
(out/"result.json").write_text(json.dumps(status,indent=2)+"\n")
if missing: raise SystemExit(1)
PY

echo AHA_BASELINE_PASS
