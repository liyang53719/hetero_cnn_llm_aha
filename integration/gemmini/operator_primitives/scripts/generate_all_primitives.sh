#!/usr/bin/env bash
set -euo pipefail
# Run in the repository's pinned standalone Chisel/CIRCT project. No branch is
# created, no generated file is edited, and canonical upstream stays read-only.
REPO_ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
PACKAGE="$REPO_ROOT/integration/gemmini/operator_primitives"
PROJECT_DIR=${PROJECT_DIR:-"$REPO_ROOT/chisel/operator_primitives_v3"}
PINNED_GEMMINI_DIR=${PINNED_GEMMINI_DIR:-"$REPO_ROOT/work/upstream/chipyard_gemmini/generators/gemmini"}
: "${SBT:=sbt}"
OUT="${1:-$REPO_ROOT/work/generated/operator_primitives_800mhz}"
LOG_DIR="$OUT/logs"
mkdir -p "$OUT" "$LOG_DIR"

test -f "$PROJECT_DIR/build.sbt"
test -f "$PROJECT_DIR/project/build.properties"
test -d "$PINNED_GEMMINI_DIR/.git" -o -f "$PINNED_GEMMINI_DIR/.git"
test -z "$(git -C "$PINNED_GEMMINI_DIR" status --porcelain)"
mapfile -t names < <(
  sed -n '/val names: Seq\[String\] = Seq(/,/^  )/s/^    "\([a-z0-9_]*\)",\{0,1\}$/\1/p' \
    "$PACKAGE/src/main/scala/gemmini/EmitHeteroOperatorPrimitiveCatalog.scala"
)
if [[ ${#names[@]} -eq 0 ]]; then
  echo "catalog extraction failed" >&2
  exit 2
fi
printf '%s\n' "${names[@]}" > "$OUT/catalog.txt"

{
  printf 'utc_started=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'repository_commit=%s\n' "$(git -C "$REPO_ROOT" rev-parse HEAD)"
  printf 'repository_branch=%s\n' "$(git -C "$REPO_ROOT" branch --show-current)"
  printf 'generation_project=%s\n' "${PROJECT_DIR#$REPO_ROOT/}"
  printf 'gemmini_commit=%s\n' "$(git -C "$PINNED_GEMMINI_DIR" rev-parse HEAD)"
  printf 'catalog_modules=%d\n' "${#names[@]}"
  printf 'clock_target_hz=800000000\nperiod_ns=1.25\n'
  printf 'java_version_begin\n'; java -version 2>&1; printf 'java_version_end\n'
  printf 'sbt_version_begin\n'; "$SBT" --version 2>&1; printf 'sbt_version_end\n'
} > "$OUT/tool_provenance.txt"

find "$PACKAGE/src/main/scala/gemmini" -maxdepth 1 -type f -name '*.scala' -print0 \
  | sort -z | xargs -0 sha256sum > "$OUT/chisel_source_sha256.txt"
sha256sum "$PACKAGE/operator_coverage_800mhz.yaml" \
  "$PACKAGE/terminal_primitive_bindings_800mhz.yaml" \
  "$REPO_ROOT/configs/global_clock_800mhz.yaml" \
  "$REPO_ROOT/dc/operator_primitives_800mhz.tcl" > "$OUT/contract_sha256.txt"

for name in "${names[@]}"; do
  log="$LOG_DIR/${name}.log"
  (
    cd "$PROJECT_DIR"
    "$SBT" -batch \
      "runMain gemmini.EmitHeteroOperatorPrimitiveCatalog $name $OUT/${name}.sv"
  ) >"$log" 2>&1
  test -s "$OUT/${name}.sv"
  grep -Eq '^[[:space:]]*module[[:space:]]+' "$OUT/${name}.sv"
done

sha256sum "$OUT"/*.sv > "$OUT/rtl_sha256.txt"
python3 "$PACKAGE/scripts/verify_generated_rtl.py" \
  --rtl-dir "$OUT" \
  --catalog "$PACKAGE/src/main/scala/gemmini/EmitHeteroOperatorPrimitiveCatalog.scala" \
  --output "$OUT/rtl_generation_audit.json" \
  > "$OUT/rtl_generation_audit.log"
printf 'utc_finished=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT/tool_provenance.txt"
printf 'generated_modules=%d\n' "${#names[@]}"
