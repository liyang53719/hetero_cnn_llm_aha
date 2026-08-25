#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
STAMP=$(date +%Y%m%dT%H%M%S)
OUT_DIR="$ROOT/work/results/execution"
MANIFEST="$OUT_DIR/cleanup-$STAMP.json"
mkdir -p "$OUT_DIR"

targets=(
  /home/yang/.cache/pip
  /home/yang/.cache/bazel
  /home/yang/.cache/tracker3
  "$ROOT/work/upstream/chipyard"
  "$ROOT/work/results/spike_build"
)

# Do not remove this cache while its owning editor is alive.
if ! pgrep -f '/usr/share/code/code' >/dev/null 2>&1; then
  targets+=(/home/yang/.cache/vscode-cpptools)
fi

entries=()
for target in "${targets[@]}"; do
  if [[ -e "$target" ]]; then
    resolved=$(readlink -f "$target")
    bytes=$(du -sx --block-size=1 "$resolved" | awk '{print $1}')
    entries+=("$(jq -n --arg path "$resolved" --argjson bytes "$bytes" '{path:$path,bytes:$bytes}')")
  fi
done

printf '%s\n' "${entries[@]}" | jq -s --arg generated_at "$(date --iso-8601=seconds)" --arg mode "${1:---dry-run}" '{generated_at:$generated_at,mode:$mode,targets:.}' > "$MANIFEST"
jq . "$MANIFEST"

if [[ "${1:---dry-run}" != "--apply" ]]; then
  echo "Dry run only. Re-run with --apply to remove exactly the listed targets." >&2
  exit 0
fi

for target in "${targets[@]}"; do
  [[ -e "$target" ]] || continue
  resolved=$(readlink -f "$target")
  case "$resolved" in
    /home/yang/.cache/pip|/home/yang/.cache/bazel|/home/yang/.cache/tracker3|/home/yang/.cache/vscode-cpptools|"$ROOT"/work/upstream/chipyard|"$ROOT"/work/results/spike_build)
      rm -rf --one-file-system "$resolved"
      ;;
    *)
      echo "Refusing unexpected cleanup target: $resolved" >&2
      exit 3
      ;;
  esac
done

df -h "$ROOT"
