#!/usr/bin/env bash
# Generate the exact AHA 4x16 macro used as an L2 wrapper input.  This script
# never mounts or edits the canonical upstream checkout; all generated RTL is
# deliberately placed below work/generated/.
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
AHA_ROOT=${AHA_ROOT:-"$PROJECT_ROOT/work/upstream/aha"}
AHA_IMAGE=${AHA_IMAGE:-stanfordaha/garnet@sha256:a8784f2cfe96609a7e4403c29f6a82bd00c882c8564ef747541f78be75fa2b2b}
AHA_WIDTH=${AHA_WIDTH:-4}
AHA_HEIGHT=${AHA_HEIGHT:-16}
AHA_CPUSET=${AHA_CPUSET:-8-23}
OUT=${OUT:-"$PROJECT_ROOT/work/generated/l2_aha_garnet_${AHA_WIDTH}x${AHA_HEIGHT}"}

command -v docker >/dev/null || { echo "Docker is required" >&2; exit 2; }
[[ "$AHA_IMAGE" == *@sha256:* ]] || { echo "AHA_IMAGE must be pinned by digest" >&2; exit 2; }
[[ -d "$AHA_ROOT/.git" ]] || { echo "AHA_ROOT is not a git checkout: $AHA_ROOT" >&2; exit 2; }
if [[ -n "$(git -C "$AHA_ROOT" status --porcelain)" ]]; then
  echo "AHA upstream checkout is dirty; refusing macro generation" >&2
  exit 3
fi

mkdir -p "$OUT"
host_commit=$(git -C "$AHA_ROOT" rev-parse HEAD)
image_commit=$(docker run --rm --entrypoint /bin/bash "$AHA_IMAGE" -lc 'git -C /aha rev-parse HEAD')
if [[ "$host_commit" != "$image_commit" ]]; then
  echo "AHA image/source commit mismatch: host=$host_commit image=$image_commit" >&2
  exit 4
fi

printf '%s\n' "$AHA_IMAGE" > "$OUT/image.ref"
docker image inspect "$AHA_IMAGE" --format '{{index .RepoDigests 0}}' > "$OUT/image.digest"
printf '%s\n' "$host_commit" > "$OUT/aha.commit"
git -C "$AHA_ROOT" submodule status --recursive > "$OUT/submodules.txt"

docker run --rm --cpuset-cpus "$AHA_CPUSET" \
  -v "$OUT:/out" -w /aha "$AHA_IMAGE" bash -lc "
    set -euo pipefail
    export PATH=/aha/bin:\$PATH
    rm -f garnet/garnet.v
    /aha/bin/aha garnet --width $AHA_WIDTH --height $AHA_HEIGHT --verilog --use_sim_sram --glb_tile_mem_size 128
    test -s garnet/garnet.v
    cp garnet/garnet.v /out/garnet.v
    sha256sum garnet/garnet.v > /out/garnet_rtl.sha256
    # garnet.v intentionally leaves global_controller external.  Preserve the
    # exact generated collateral closure required by the upstream simulator;
    # the canonical checkout itself stays clean and untouched.
    mkdir -p /out/collateral/global_buffer/header \\
      /out/collateral/global_buffer/systemRDL/output \\
      /out/collateral/global_controller/header \\
      /out/collateral/global_controller/systemRDL/output \\
      /out/collateral/matrix_unit/header /out/collateral/genesis_verif \\
      /out/collateral/CW
    cp garnet/global_buffer/header/global_buffer_param.svh \\
      garnet/global_buffer/header/glb.svh /out/collateral/global_buffer/header/
    cp garnet/global_controller/header/glc.svh /out/collateral/global_controller/header/
    cp garnet/matrix_unit/header/matrix_unit_param.svh \\
      garnet/matrix_unit/header/matrix_unit_regspace.svh /out/collateral/matrix_unit/header/
    cp garnet/global_buffer/systemRDL/output/glb_pio.sv \\
      garnet/global_buffer/systemRDL/output/glb_jrdl_decode.sv \\
      garnet/global_buffer/systemRDL/output/glb_jrdl_logic.sv \\
      /out/collateral/global_buffer/systemRDL/output/
    cp garnet/global_controller/systemRDL/output/glc_pio.sv \\
      garnet/global_controller/systemRDL/output/glc_jrdl_decode.sv \\
      garnet/global_controller/systemRDL/output/glc_jrdl_logic.sv \\
      /out/collateral/global_controller/systemRDL/output/
    cp garnet/genesis_verif/*.sv /out/collateral/genesis_verif/
    cp garnet/tests/test_app/CW/*.v /out/collateral/CW/
    (
      cd /out
      sha256sum garnet.v collateral/global_buffer/header/*.svh \\
        collateral/global_buffer/systemRDL/output/*.sv \\
        collateral/global_controller/header/*.svh \\
        collateral/global_controller/systemRDL/output/*.sv \\
        collateral/matrix_unit/header/*.svh collateral/genesis_verif/*.sv \\
        collateral/CW/*.v
    ) > /out/collateral.sha256
    cat > /out/upstream_compile_closure.f <<'EOF'
garnet.v
collateral/global_buffer/header/global_buffer_param.svh
collateral/global_buffer/header/glb.svh
collateral/global_controller/header/glc.svh
collateral/matrix_unit/header/matrix_unit_param.svh
collateral/matrix_unit/header/matrix_unit_regspace.svh
collateral/global_buffer/systemRDL/output/glb_pio.sv
collateral/global_buffer/systemRDL/output/glb_jrdl_decode.sv
collateral/global_buffer/systemRDL/output/glb_jrdl_logic.sv
collateral/global_controller/systemRDL/output/glc_pio.sv
collateral/global_controller/systemRDL/output/glc_jrdl_decode.sv
collateral/global_controller/systemRDL/output/glc_jrdl_logic.sv
EOF
    find /out/collateral/genesis_verif -maxdepth 1 -type f -name '*.sv' -printf 'collateral/genesis_verif/%f\\n' | sort >> /out/upstream_compile_closure.f
    find /out/collateral/CW -maxdepth 1 -type f -name '*.v' -printf 'collateral/CW/%f\\n' | sort >> /out/upstream_compile_closure.f
  " | tee "$OUT/docker.log"

python3 "$PROJECT_ROOT/scripts/extract_sv_module_port_manifest.py" \
  "$OUT/garnet.v" Interconnect --output "$OUT/interconnect_port_manifest.json"

python3 - "$OUT" <<'PY'
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
manifest = json.loads((out / "interconnect_port_manifest.json").read_text())
result = {
    "status": "PASS",
    "scope": "generated 4x16 Garnet macro boundary only; no wrapper equivalence claimed",
    "module": manifest["module"],
    "port_count": manifest["port_count"],
    "rtl_sha256": (out / "garnet_rtl.sha256").read_text().split()[0],
    "collateral_file_count": len((out / "collateral.sha256").read_text().splitlines()),
}
(out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
PY

echo AHA_L2_MACRO_GENERATION_PASS
