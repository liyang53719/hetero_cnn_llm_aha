#!/usr/bin/env bash
# Public, hash-pinned Host verification tools. No model payload is downloaded.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=${1:?absolute NEW tool directory}
[[ "$OUT" = /* && ! -e "$OUT" ]] || exit 2
mkdir -p "$OUT/downloads" "$OUT/verilator" "$OUT/firtool"
fetch() {
  local url=$1 target=$2 expected=$3
  curl --fail --location --retry 2 --connect-timeout 30 "$url" -o "$target"
  printf '%s  %s\n' "$expected" "$target" | sha256sum --check
}
fetch https://deb.debian.org/debian/pool/main/v/verilator/verilator_5.032-1+b2_amd64.deb \
  "$OUT/downloads/verilator.deb" 238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2
dpkg-deb -x "$OUT/downloads/verilator.deb" "$OUT/verilator"
fetch https://repo.maven.apache.org/maven2/org/chipsalliance/llvm-firtool/1.62.1/llvm-firtool-1.62.1-linux-x64.jar \
  "$OUT/downloads/firtool.jar" 63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039
python3 -m zipfile -e "$OUT/downloads/firtool.jar" "$OUT/firtool"
export CHISEL_FIRTOOL_PATH="$OUT/firtool/org.chipsalliance/llvm-firtool/linux-x64/bin"
chmod +x "$CHISEL_FIRTOOL_PATH/firtool"
export PATH="$OUT/verilator/usr/bin:$PATH"
export VERILATOR_ROOT="$OUT/verilator/usr/share/verilator"
source "$ROOT/chisel/continuous_prefill/scripts/prepare_verilator_runtime.sh" "$OUT"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
bash "$ROOT/chisel/continuous_prefill/scripts/prepare_hardfloat.sh"
verilator --version > "$OUT/verilator_version.txt"
"$CHISEL_FIRTOOL_PATH/firtool" --version > "$OUT/firtool_version.txt"
if [[ -n ${GITHUB_ENV:-} && -n ${GITHUB_PATH:-} ]];then
  printf '%s\n' "$OUT/verilator/usr/bin" >> "$GITHUB_PATH"
  printf 'VERILATOR_ROOT=%s\nCHISEL_FIRTOOL_PATH=%s\nHARDFLOAT_SOURCE=%s\n' \
    "$VERILATOR_ROOT" "$CHISEL_FIRTOOL_PATH" "$HARDFLOAT_SOURCE" >> "$GITHUB_ENV"
fi
