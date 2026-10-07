#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Standalone synthesis-capable emission of the production HardFloat arithmetic.
# Nothing is installed system-wide; upstream sources and binaries stay in work/.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PROJECT="$ROOT/chisel/rope_hardware_oracle"
WORK="$ROOT/work/rope_hardware_oracle"
OUT=${OUT:-"$ROOT/work/generated/rope_hardware_oracle"}
PYTHON_BIN=${PYTHON_BIN:-python3}
JAVA_BIN=${JAVA_BIN:-java}
HARDFLOAT_COMMIT=c1105e6ac6a0dd90fc80893efc4830ab609005d3
HARDFLOAT_SHA256=55f9c47f73c5a0ff347ff0ff4fc72b6966ffaa6b6d29998a00b3956dce512de7
FIRTOOL_SHA256=63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039
SBT_SHA256=cdd6963b622f42690cb2e3154bde3f3257a03839f216e1b5d7420000d6a71817
VERILATOR_SHA256=238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2
mkdir -p "$WORK/downloads" "$WORK/deps" "$WORK/bin" "$WORK/home" "$WORK/run" "$OUT"
OUT=$(cd "$OUT" && pwd)

fetch() {
  local url=$1 path=$2 digest=$3
  if [[ ! -f "$path" ]]; then
    curl --fail --location --retry 3 --connect-timeout 30 "$url" -o "$path.part"
    printf '%s  %s\n' "$digest" "$path.part" | sha256sum --check --status
    mv "$path.part" "$path"
  fi
  printf '%s  %s\n' "$digest" "$path" | sha256sum --check --status
}
fetch "https://codeload.github.com/ucb-bar/berkeley-hardfloat/tar.gz/$HARDFLOAT_COMMIT" \
  "$WORK/downloads/hardfloat.tar.gz" "$HARDFLOAT_SHA256"
fetch 'https://repo.maven.apache.org/maven2/org/scala-sbt/sbt-launch/1.10.2/sbt-launch-1.10.2.jar' \
  "$WORK/downloads/sbt-launch-1.10.2.jar" "$SBT_SHA256"
fetch 'https://repo.maven.apache.org/maven2/org/chipsalliance/llvm-firtool/1.62.1/llvm-firtool-1.62.1-linux-x64.jar' \
  "$WORK/downloads/llvm-firtool-1.62.1-linux-x64.jar" "$FIRTOOL_SHA256"
"$PYTHON_BIN" - "$WORK/downloads/llvm-firtool-1.62.1-linux-x64.jar" "$WORK/deps/firtool" <<'PYTHON'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    archive.extractall(sys.argv[2])
PYTHON
export CHISEL_FIRTOOL_PATH="$WORK/deps/firtool/org.chipsalliance/llvm-firtool/linux-x64/bin"
chmod +x "$CHISEL_FIRTOOL_PATH/firtool"
export ROPE_HARDFLOAT_SOURCE="$WORK/deps/berkeley-hardfloat-$HARDFLOAT_COMMIT"
if [[ ! -d "$ROPE_HARDFLOAT_SOURCE" ]]; then
  tar -xzf "$WORK/downloads/hardfloat.tar.gz" -C "$WORK/deps"
fi
# Compare all upstream Scala files with the hash-verified archive, refusing edits
# and extra Scala sources. manifest.py also rejects every extra file/symlink in
# the actual HardFloat compiler source directory, including Java. The pinned
# archive retains upstream copyright/license files.
"$PYTHON_BIN" - "$WORK/downloads/hardfloat.tar.gz" "$ROPE_HARDFLOAT_SOURCE" <<'PY'
import pathlib, sys, tarfile
archive, source = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
with tarfile.open(archive) as tf:
    expected = {}
    for member in tf.getmembers():
        parts = pathlib.PurePosixPath(member.name).parts
        if member.isfile() and len(parts) > 1:
            relative = pathlib.Path(*parts[1:])
            if relative.suffix == '.scala' or relative.name.lower().startswith(('license', 'copying')):
                expected[relative] = tf.extractfile(member).read()
    actual_scala = {p.relative_to(source) for p in source.rglob('*.scala')}
    if actual_scala != {p for p in expected if p.suffix == '.scala'}:
        raise SystemExit('HardFloat source list changed')
    for relative, data in expected.items():
        if (source / relative).read_bytes() != data:
            raise SystemExit(f'HardFloat modified: {relative}')
PY

if [[ -z ${VERILATOR_BIN:-} ]]; then
  if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    echo 'Set VERILATOR_BIN to an installed Verilator on this platform.' >&2; exit 2
  fi
  fetch 'https://deb.debian.org/debian/pool/main/v/verilator/verilator_5.032-1+b2_amd64.deb' \
    "$WORK/downloads/verilator_5.032-1+b2_amd64.deb" "$VERILATOR_SHA256"
  # Re-extract only this verified tool package, preserving no local binary changes.
  dpkg-deb -x "$WORK/downloads/verilator_5.032-1+b2_amd64.deb" "$WORK/deps/verilator_debian"
  cat > "$WORK/bin/verilator" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
BASE=$(cd "$(dirname "$0")/../deps/verilator_debian" && pwd)
export VERILATOR_ROOT="$BASE/usr/share/verilator"
unset VERILATOR_BIN
exec "$BASE/usr/bin/verilator" "$@"
WRAPPER
  chmod +x "$WORK/bin/verilator"
  VERILATOR_BIN="$WORK/bin/verilator"
fi
"$VERILATOR_BIN" --version
export COURSIER_CACHE="$WORK/coursier"
export COURSIER_REPOSITORIES='https://repo.maven.apache.org/maven2'
export XDG_CACHE_HOME="$WORK/cache" XDG_RUNTIME_DIR="$WORK/run"
JAVA_OPTIONS=(-Xmx4G -XX:ActiveProcessorCount=4 "-Duser.home=$WORK/home"
  -Dsbt.server.forcestart=true -Dsbt.server.autostart=false
  "-Dsbt.global.base=$WORK/sbt/global" "-Dsbt.boot.directory=$WORK/sbt/boot"
  "-Dsbt.ivy.home=$WORK/sbt/ivy" "-Dsbt.repository.config=$PROJECT/repositories"
  -Dsbt.override.build.repos=true -Dsbt.color=never -Dsbt.supershell=false)
# sbt/Coursier do not consistently honor shell proxy variables. Respect an HTTP
# proxy supplied by the execution environment; never hard-code its transient port.
proxy=${https_proxy:-${HTTPS_PROXY:-}}
if [[ -n "$proxy" ]]; then
  read -r host port < <("$PYTHON_BIN" - "$proxy" <<'PY'
import sys, urllib.parse
p = urllib.parse.urlparse(sys.argv[1])
if p.scheme != 'http' or not p.hostname or p.username:
    raise SystemExit('Expected a credential-free HTTP CONNECT proxy in HTTPS_PROXY')
print(p.hostname, p.port or 80)
PY
  )
  JAVA_OPTIONS+=("-Dhttp.proxyHost=$host" "-Dhttp.proxyPort=$port"
    "-Dhttps.proxyHost=$host" "-Dhttps.proxyPort=$port")
fi
unset ftp_proxy FTP_PROXY
"$PYTHON_BIN" "$PROJECT/manifest.py" verify-cache "$ROOT"
# An emission failure must never leave a success manifest attached to old RTL.
rm -f "$OUT/manifest.json"
(
  cd "$PROJECT"
  "$JAVA_BIN" "${JAVA_OPTIONS[@]}" -jar "$WORK/downloads/sbt-launch-1.10.2.jar" clean compile \
    "runMain gemmini.EmitRoPEHardwarePrimitives $OUT/HeteroRoPEHardwarePrimitives.sv"
) > "$OUT/generate.log" 2>&1 || { tail -80 "$OUT/generate.log" >&2; exit 1; }
"$PYTHON_BIN" "$PROJECT/manifest.py" verify-cache "$ROOT" --complete
for module in HeteroFP32Alu HeteroFP32MulPipeTag12 HeteroFP32AddPipeTag12 HeteroFP32MulPipeBit1 HeteroFP32AddPipeBit1; do
  grep -q "^module $module(" "$OUT/HeteroRoPEHardwarePrimitives.sv"
done
"$VERILATOR_BIN" --lint-only --top-module RoPEHardwarePrimitives -Wno-fatal \
  "$OUT/HeteroRoPEHardwarePrimitives.sv" > "$OUT/lint.log" 2>&1
"$PYTHON_BIN" "$PROJECT/manifest.py" write "$ROOT" "$OUT" "$JAVA_BIN" "$VERILATOR_BIN"
echo "ROPE_HARDWARE_PRIMITIVES_PASS manifest=$OUT/manifest.json"
