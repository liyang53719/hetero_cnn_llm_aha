#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Provision only the bounded Chisel/Verilator unit-test toolchain.
# Run inside this repository; optional TOOL_ROOT is relative to repository root
# or an absolute path strictly below repository-root/work/.
# Requires Linux x86_64, host Java 21 with JNI headers, Python with tarfile's
# data filter (e.g. Python 3.12), curl, tar, dpkg-deb, Perl, g++, make and git.
# No system installation, RTL generation, source compilation or tests here.
set -euo pipefail
[[ $# -le 1 ]] || { echo "Usage: $0 [TOOL_ROOT]" >&2; exit 2; }
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || {
  echo 'This pinned toolchain requires Linux x86_64.' >&2; exit 2;
}
for cmd in git python3 curl tar dpkg-deb perl g++ make sha256sum; do
  command -v "$cmd" >/dev/null || { echo "Missing prerequisite: $cmd" >&2; exit 2; }
done
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_ROOT=$(cd "$REPO_ROOT" && pwd -P)
TOOL_ROOT=$(python3 - "$REPO_ROOT" "${1:-work/chisel_toolchain}" <<'PY'
import os, pathlib, sys, tarfile
if not hasattr(tarfile, 'data_filter'):
    raise SystemExit('Python with tarfile.data_filter is required, e.g. Python 3.12')
root = pathlib.Path(sys.argv[1])
p = pathlib.Path(sys.argv[2])
if not p.is_absolute():
    p = root / p
p = pathlib.Path(os.path.normpath(str(p)))
work = root / 'work'
try:
    relative = p.relative_to(work)
except ValueError:
    raise SystemExit('TOOL_ROOT must be strictly below repository-root/work/')
if not relative.parts:
    raise SystemExit('Use a dedicated subdirectory below work/, not work/ itself')
for ancestor in [p, *p.parents]:
    if ancestor == root:
        break
    if ancestor.is_symlink():
        raise SystemExit('TOOL_ROOT and its ancestors must not be symlinks')
if p.exists() and not p.is_dir():
    raise SystemExit('TOOL_ROOT exists and is not a directory')
print(p)
PY
)
JAVA_BIN=${JAVA_BIN:-$(command -v java)}
[[ -x "$JAVA_BIN" ]] || { echo 'Set JAVA_BIN to the host Java 21 executable.' >&2; exit 2; }
JAVA_SETTINGS=$("$JAVA_BIN" -XshowSettings:properties -version 2>&1)
JAVA_SPEC=$(printf '%s\n' "$JAVA_SETTINGS" | sed -n 's/^[[:space:]]*java.specification.version = //p')
JAVA_HOME_ACTUAL=$(printf '%s\n' "$JAVA_SETTINGS" | sed -n 's/^[[:space:]]*java.home = //p')
[[ $JAVA_SPEC == 21 ]] || { echo 'Host Java 21 is required; no JDK will be installed.' >&2; exit 2; }
[[ -f "$JAVA_HOME_ACTUAL/include/jni.h" && -f "$JAVA_HOME_ACTUAL/include/linux/jni_md.h" ]] || {
  echo 'Host Java 21 must include Linux JNI headers for Chiseltest.' >&2; exit 2;
}
export JAVA_BIN
HARDFLOAT_COMMIT=c1105e6ac6a0dd90fc80893efc4830ab609005d3
HARDFLOAT_SHA256=55f9c47f73c5a0ff347ff0ff4fc72b6966ffaa6b6d29998a00b3956dce512de7
SBT_SHA256=cdd6963b622f42690cb2e3154bde3f3257a03839f216e1b5d7420000d6a71817
FIRTOOL_SHA256=63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039
VERILATOR_SHA256=238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2
HF_HASHES="$REPO_ROOT/reports/execution/QWEN2_REAL16_B91BBE3/hardfloat.sha256.json"
MAVEN_LOCK="$REPO_ROOT/chisel/rope_hardware_oracle/maven-lock.json"
[[ -f "$HF_HASHES" && -f "$MAVEN_LOCK" ]] || {
  echo 'Required existing repository checksum inventories are missing.' >&2; exit 2;
}
# Reject preexisting internal symlinks for every path this script writes.
python3 - "$TOOL_ROOT" <<'PY'
from pathlib import Path
import sys
base = Path(sys.argv[1])
for rel in ('downloads','deps','bin','home','run','cache','coursier','sbt','logs',
            'bootstrap_project','bootstrap_project/project','env.sh','repositories',
            'bin/sbt','bin/sbt-chiseltest','bin/verilator',
            'bootstrap_project/build.sbt','bootstrap_project/project/build.properties'):
    p = base / rel
    while p != base:
        if p.is_symlink():
            raise SystemExit('Refuse symlink at provisioning path: '+str(p))
        p = p.parent
PY
mkdir -p "$TOOL_ROOT"/{downloads,deps,bin,home,run,cache,coursier,sbt,logs,bootstrap_project/project}
download_tmp=''
trap '[[ -z "$download_tmp" ]] || rm -f -- "$download_tmp"' EXIT
fetch() {
  local url=$1 name=$2 digest=$3 path="$TOOL_ROOT/downloads/$2"
  [[ ! -L "$path" ]] || { echo "Refuse download symlink: $name" >&2; exit 2; }
  if [[ ! -f "$path" ]]; then
    download_tmp=$(mktemp "$path.part.XXXXXX")
    # No retries or alternate route on denied access. Only official HTTPS.
    curl --fail --location --proto '=https' --proto-redir '=https' \
      --connect-timeout 15 --max-time 180 --silent --show-error \
      "$url" -o "$download_tmp"
    printf '%s  %s\n' "$digest" "$download_tmp" | sha256sum --check --status
    mv -- "$download_tmp" "$path"
    download_tmp=''
  fi
  printf '%s  %s\n' "$digest" "$path" | sha256sum --check
}
fetch "https://codeload.github.com/ucb-bar/berkeley-hardfloat/tar.gz/$HARDFLOAT_COMMIT" \
  hardfloat.tar.gz "$HARDFLOAT_SHA256"
fetch 'https://repo.maven.apache.org/maven2/org/scala-sbt/sbt-launch/1.10.2/sbt-launch-1.10.2.jar' \
  sbt-launch-1.10.2.jar "$SBT_SHA256"
fetch 'https://repo.maven.apache.org/maven2/org/chipsalliance/llvm-firtool/1.62.1/llvm-firtool-1.62.1-linux-x64.jar' \
  llvm-firtool-1.62.1-linux-x64.jar "$FIRTOOL_SHA256"
fetch 'https://deb.debian.org/debian/pool/main/v/verilator/verilator_5.032-1+b2_amd64.deb' \
  verilator_5.032-1+b2_amd64.deb "$VERILATOR_SHA256"

python3 - "$TOOL_ROOT" "$HF_HASHES" "$HARDFLOAT_COMMIT" <<'PY'
import hashlib, json, pathlib, sys, tarfile, zipfile
base, hashes = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
name = 'berkeley-hardfloat-' + sys.argv[3]
hf = base/'deps'/name
if hf.is_symlink():
    raise SystemExit('HardFloat source root must not be a symlink')
with tarfile.open(base/'downloads/hardfloat.tar.gz') as tf:
    if any(not pathlib.PurePosixPath(m.name).parts or pathlib.PurePosixPath(m.name).parts[0] != name for m in tf.getmembers()):
        raise SystemExit('Unexpected HardFloat archive root')
    if not hf.exists():
        tf.extractall(base/'deps', filter='data')
    expected = {}
    for member in tf.getmembers():
        rel = pathlib.Path(*pathlib.PurePosixPath(member.name).parts[1:])
        if member.isfile() and rel.parts[:4] == ('hardfloat','src','main','scala'):
            expected[str(rel)] = hashlib.sha256(tf.extractfile(member).read()).hexdigest()
    license_member = tf.getmember(name+'/LICENSE')
    if (hf/'LICENSE').read_bytes() != tf.extractfile(license_member).read():
        raise SystemExit('HardFloat LICENSE mismatch')
actual = {}
source_root = hf/'hardfloat/src/main/scala'
for ancestor in [source_root, *source_root.parents]:
    if ancestor == base:
        break
    if ancestor.is_symlink():
        raise SystemExit('HardFloat compilation source path contains a symlink')
for p in source_root.rglob('*'):
    if p.is_symlink():
        raise SystemExit('HardFloat compilation source contains a symlink')
    if p.is_file():
        actual[str(p.relative_to(hf))] = hashlib.sha256(p.read_bytes()).hexdigest()
pinned = json.loads(hashes.read_text())
if len(pinned) != 20 or actual != expected or actual != pinned:
    raise SystemExit('HardFloat compilation inventory differs from archive or 20 repository pins')
(base/'logs/hardfloat_inventory.json').write_text(json.dumps({
    'commit':sys.argv[3], 'compile_source_files':20, 'sha256':actual}, indent=2)+'\n')
firtool_root = base/'deps/firtool'
if firtool_root.is_symlink():
    raise SystemExit('firtool extraction root must not be a symlink')
with zipfile.ZipFile(base/'downloads/llvm-firtool-1.62.1-linux-x64.jar') as z:
    for member in z.infolist():
        parts = pathlib.PurePosixPath(member.filename).parts
        if member.filename.startswith('/') or '..' in parts:
            raise SystemExit('Unsafe firtool archive member')
        target = firtool_root.joinpath(*parts)
        for p in [target, *target.parents]:
            if p == base:
                break
            if p.is_symlink():
                raise SystemExit('firtool extraction path contains a symlink')
    z.extractall(firtool_root)
PY
# Extract the hash-verified Debian tool locally. This does not install packages
# or execute Debian package-maintainer scripts, and makes no vendor patches.
[[ ! -L "$TOOL_ROOT/deps/verilator_debian" ]] || { echo 'Refuse Verilator extraction symlink.' >&2; exit 2; }
dpkg-deb -x "$TOOL_ROOT/downloads/verilator_5.032-1+b2_amd64.deb" "$TOOL_ROOT/deps/verilator_debian"
cat > "$TOOL_ROOT/repositories" <<'TXT'
[repositories]
maven-central: https://repo.maven.apache.org/maven2
TXT
cat > "$TOOL_ROOT/env.sh" <<'ENV'
# Source from Bash. All tool/cache paths are derived from this file's location.
CHISEL_TOOLCHAIN=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
export CHISEL_TOOLCHAIN
export JAVA_BIN="${JAVA_BIN:-$(command -v java)}"
export HARDFLOAT_SOURCE="$CHISEL_TOOLCHAIN/deps/berkeley-hardfloat-c1105e6ac6a0dd90fc80893efc4830ab609005d3"
export CHISEL_FIRTOOL_PATH="$CHISEL_TOOLCHAIN/deps/firtool/org.chipsalliance/llvm-firtool/linux-x64/bin"
export SBT_LAUNCH_JAR="$CHISEL_TOOLCHAIN/downloads/sbt-launch-1.10.2.jar"
export COURSIER_CACHE="$CHISEL_TOOLCHAIN/coursier"
export COURSIER_REPOSITORIES='https://repo.maven.apache.org/maven2'
export XDG_CACHE_HOME="$CHISEL_TOOLCHAIN/cache" XDG_RUNTIME_DIR="$CHISEL_TOOLCHAIN/run"
export VERILATOR="$CHISEL_TOOLCHAIN/bin/verilator" HETERO_VERILATOR="$CHISEL_TOOLCHAIN/bin/verilator"
export PATH="$CHISEL_TOOLCHAIN/bin:$CHISEL_FIRTOOL_PATH:$PATH"
ENV
cat > "$TOOL_ROOT/bin/verilator" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
BASE=$(cd "$(dirname "$0")/../deps/verilator_debian" && pwd -P)
export VERILATOR_ROOT="$BASE/usr/share/verilator"
unset VERILATOR_BIN
exec "$BASE/usr/bin/verilator" "$@"
WRAPPER
cat > "$TOOL_ROOT/bin/sbt" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
BASE=$(cd "$(dirname "$0")/.." && pwd -P)
source "$BASE/env.sh"
JAVA_OPTIONS=(-Xmx2G -XX:ActiveProcessorCount=2 "-Duser.home=$BASE/home"
  -Dsbt.server.forcestart=true -Dsbt.server.autostart=false
  "-Dsbt.global.base=$BASE/sbt/global" "-Dsbt.boot.directory=$BASE/sbt/boot"
  "-Dsbt.ivy.home=$BASE/sbt/ivy" "-Dsbt.repository.config=$BASE/repositories"
  -Dsbt.override.build.repos=true -Dsbt.color=never -Dsbt.supershell=false)
# Honor a supplied credential-free HTTP CONNECT proxy; do not modify it.
if [[ -n ${https_proxy:-${HTTPS_PROXY:-}} ]]; then
  read -r host port < <(python3 - <<'PY'
import os, urllib.parse
p = urllib.parse.urlparse(os.environ.get('https_proxy') or os.environ.get('HTTPS_PROXY',''))
if p.scheme != 'http' or not p.hostname or p.username is not None or p.password is not None:
    raise SystemExit('Expected a credential-free HTTP CONNECT proxy')
print(p.hostname, p.port or 80)
PY
  )
  JAVA_OPTIONS+=("-Dhttp.proxyHost=$host" "-Dhttp.proxyPort=$port" "-Dhttps.proxyHost=$host" "-Dhttps.proxyPort=$port")
fi
exec "$JAVA_BIN" "${JAVA_OPTIONS[@]}" -jar "$SBT_LAUNCH_JAR" "$@"
WRAPPER
cat > "$TOOL_ROOT/bin/sbt-chiseltest" <<'WRAPPER'
#!/usr/bin/env bash
# Chiseltest 6 force-includes V<top>.h before Verilator 5.032's PCH. GCC cannot
# use a PCH after C++ tokens. This supported Verilator make setting uses the
# combined-source build without PCH; generated RTL and simulator stay unchanged.
# Limit this opt-in wrapper to the authorized small unit tests.
set -euo pipefail
BASE=$(cd "$(dirname "$0")/.." && pwd -P)
export MAKEFLAGS="${MAKEFLAGS:-} VM_PARALLEL_BUILDS=0"
exec "$BASE/bin/sbt" "$@"
WRAPPER
chmod +x "$TOOL_ROOT/bin/"{sbt,sbt-chiseltest,verilator} \
  "$TOOL_ROOT/deps/firtool/org.chipsalliance/llvm-firtool/linux-x64/bin/firtool"
cat > "$TOOL_ROOT/bootstrap_project/build.sbt" <<'SBT'
ThisBuild / scalaVersion := "2.13.16"
ThisBuild / organization := "org.heteronpu"
ThisBuild / version := "0.1.0"
lazy val root = (project in file(".")).settings(
  name := "heteronpu-toolchain-dependency-check",
  libraryDependencies ++= Seq("org.chipsalliance" %% "chisel" % "6.7.0", "edu.berkeley.cs" %% "chiseltest" % "6.0.0" % Test, "org.scalatest" %% "scalatest" % "3.2.19" % Test),
  addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % "6.7.0" cross CrossVersion.full)
)
SBT
printf 'sbt.version=1.10.2\n' > "$TOOL_ROOT/bootstrap_project/project/build.properties"
source "$TOOL_ROOT/env.sh"
{ "$JAVA_BIN" -version; firtool --version; verilator --version; g++ --version; make --version; } \
  > "$TOOL_ROOT/logs/tool_versions.log" 2>&1
# Resolve dependencies in an empty project. No Chisel/DUT compilation or tests.
(
  cd "$TOOL_ROOT/bootstrap_project"
  sbt 'show sbtVersion' 'show scalaVersion' update
) > "$TOOL_ROOT/logs/sbt_dependency_update.log" 2>&1 || {
  tail -80 "$TOOL_ROOT/logs/sbt_dependency_update.log" >&2; exit 1;
}
# The existing production lock does not cover chiseltest/ScalaTest. Verify
# overlapping artifacts and sbt boot copies; report extra observed hashes
# distinctly rather than claiming they are preexisting vendor checksum pins.
python3 - "$TOOL_ROOT" "$MAVEN_LOCK" <<'PY'
import hashlib, json, pathlib, sys
base = pathlib.Path(sys.argv[1])
lock = json.loads(pathlib.Path(sys.argv[2]).read_text())['artifacts']
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
cache = base/'coursier/https/repo.maven.apache.org/maven2'
actual = {str(p.relative_to(cache)):sha(p) for p in sorted(cache.rglob('*'))
          if p.is_file() and p.suffix in ('.jar','.pom')}
matched = {n:d for n,d in actual.items() if n in lock}
for n,d in matched.items():
    if lock[n] != d:
        raise SystemExit('Pinned Maven checksum mismatch: '+n)
known_jars = {d for n,d in lock.items() if n.endswith('.jar')}
boot = list((base/'sbt/boot').rglob('*.jar'))
for p in boot:
    if sha(p) not in known_jars:
        raise SystemExit('Pinned sbt boot JAR mismatch: '+str(p))
if not matched or not boot:
    raise SystemExit('Expected resolved Maven dependencies and sbt boot JARs')
report = {
  'maven_artifacts_matching_existing_lock':len(matched),
  'sbt_boot_jars_matching_existing_lock':len(boot),
  'additional_official_maven_artifacts_observed_sha256':{n:d for n,d in actual.items() if n not in lock},
  'note':'Extra artifact hashes are observed from this resolution, not preexisting repository/vendor checksum pins.'
}
(base/'logs/dependency_inventory.json').write_text(json.dumps(report,indent=2)+'\n')
print('Verified existing Maven lock matches:',len(matched),'and sbt boot JARs:',len(boot))
print('Additional version-pinned official Maven artifacts with observed hashes:',len(actual)-len(matched))
PY
cat "$TOOL_ROOT/logs/tool_versions.log"
printf '\nToolchain ready. Source from Bash:\n  source %q\n' "$TOOL_ROOT/env.sh"
printf 'For small Chiseltest unit tests, use sbt-chiseltest in chisel/continuous_prefill.\n'
printf 'No tests or RTL emission were run by this provisioning script.\n'
