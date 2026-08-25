#!/usr/bin/env bash
set -euo pipefail

ROOT=${1:-"$PWD/work/upstream"}
mkdir -p "$ROOT"

clone_repo() {
  local name=$1 url=$2 ref=$3 recursive=${4:-0}
  local dst="$ROOT/$name"
  if [[ ! -d "$dst/.git" ]]; then
    if [[ "$recursive" == 1 ]]; then
      git clone --recursive "$url" "$dst"
    else
      git clone "$url" "$dst"
    fi
  fi
  git -C "$dst" fetch --tags --prune origin
  git -C "$dst" checkout "$ref"
  if [[ "$recursive" == 1 ]]; then
    git -C "$dst" submodule sync --recursive
    git -C "$dst" submodule update --init --recursive
  fi
  git -C "$dst" status --short
  printf '%s %s\n' "$name" "$(git -C "$dst" rev-parse HEAD)"
}

{
  clone_repo chipyard https://github.com/ucb-bar/chipyard.git main 1
  clone_repo gemmini_audit https://github.com/ucb-bar/gemmini.git master 1
  clone_repo aha https://github.com/StanfordAHA/aha.git master 1
  clone_repo idma https://github.com/pulp-platform/iDMA.git master 1
  clone_repo pulp_axi https://github.com/pulp-platform/axi.git master 1
  clone_repo common_cells https://github.com/pulp-platform/common_cells.git master 1
  clone_repo imax3_llm https://github.com/Takuto-Ando/IMAX3-LLM.git main 1
} | tee "$ROOT/UPSTREAM_COMMITS.txt"

python3 - "$ROOT" <<'PY'
import json, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
repos = {}
for path in sorted(root.iterdir()):
    if not (path / ".git").exists():
        continue
    def git(*args):
        return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()
    repos[path.name] = {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "origin": git("remote", "get-url", "origin"),
        "dirty": bool(git("status", "--porcelain")),
    }
(root / "UPSTREAM_LOCK.json").write_text(json.dumps(repos, indent=2, sort_keys=True)+"\n")
PY

printf 'UPSTREAM_CLONE_PASS root=%s\n' "$ROOT"
