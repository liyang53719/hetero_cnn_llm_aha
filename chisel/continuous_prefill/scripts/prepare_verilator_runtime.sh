#!/usr/bin/env bash
# Source this file. Debian separates /usr/bin/verilator_bin from its data root;
# hierarchical child invocations nevertheless use VERILATOR_ROOT/verilator_bin.
# Repair the runtime layout with NEW user-owned symlinks, never sudo or edits to
# the installed tools, generated C++, or SystemVerilog.
_prepare_verilator_runtime() {
  local out=${1:?new acceptance output directory}
  local tool root binary original_tools=${OFFLINE_TOOLS:-}
  if [[ -n "$original_tools" ]]; then
    export PATH="$original_tools/bin:$PATH"
    root="$original_tools/share/verilator"
  else
    tool=$(command -v verilator) || { echo BLOCKED_MISSING_VERILATOR >&2;return 77; }
    root=${VERILATOR_ROOT:-}
    if [[ -z "$root" ]]; then
      root=$("$tool" -V | awk '$1=="VERILATOR_ROOT" && $2=="=" && NF>=3 {print $3;exit}')
    fi
  fi
  [[ -d "$root/include" ]] || { echo BLOCKED_VERILATOR_RUNTIME_ROOT >&2;return 77; }
  if [[ -x "$root/verilator_bin" || -x "$root/bin/verilator_bin" ]]; then
    export VERILATOR_ROOT="$root"
    return 0
  fi
  tool=$(command -v verilator) || return 77
  binary=$(command -v verilator_bin || true)
  [[ -n "$binary" ]] || binary="$(dirname "$tool")/verilator_bin"
  [[ -x "$binary" ]] || { echo BLOCKED_VERILATOR_BACKEND >&2;return 77; }
  [[ ! -e "$out/verilator-runtime" ]] || { echo EXISTING_VERILATOR_RUNTIME >&2;return 2; }
  python3 - "$root" "$binary" "$out" "$original_tools" <<'PY'
from pathlib import Path
import hashlib,json,sys
root,binary,out=map(lambda s:Path(s).resolve(),sys.argv[1:4])
original=sys.argv[4]
runtime=out/'verilator-runtime';runtime.mkdir()
for entry in root.iterdir():
    if entry.name!='verilator_bin':(runtime/entry.name).symlink_to(entry)
(runtime/'verilator_bin').symlink_to(binary)
if original:
    tools=out/'offline-tools-runtime';tools.mkdir();(tools/'share').mkdir()
    for name in ('bin','jars'):(tools/name).symlink_to(Path(original).resolve()/name)
    (tools/'share/verilator').symlink_to(runtime)
(out/'verilator_runtime.json').write_text(json.dumps(dict(original_root=str(root),backend=str(binary),
    backend_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),runtime_root=str(runtime),
    installed_files_modified=False),indent=2)+'\n')
PY
  export VERILATOR_ROOT="$out/verilator-runtime"
  if [[ -n "$original_tools" ]]; then
    export OFFLINE_TOOLS="$out/offline-tools-runtime"
    export PATH="$OFFLINE_TOOLS/bin:$PATH"
    export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
  fi
}
_prepare_verilator_runtime "$@"
