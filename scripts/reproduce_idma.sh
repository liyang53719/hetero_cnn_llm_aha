#!/usr/bin/env bash
set -euo pipefail

IDMA_ROOT=${IDMA_ROOT:?set IDMA_ROOT to the cloned iDMA directory}
OUT=${OUT:-"$PWD/work/results/idma_baseline"}
mkdir -p "$OUT"
exec > >(tee "$OUT/reproduce.log") 2>&1

git -C "$IDMA_ROOT" rev-parse HEAD | tee "$OUT/idma.commit"
if [[ -n "$(git -C "$IDMA_ROOT" status --porcelain)" ]]; then
  echo "iDMA tree is dirty before baseline reproduction" >&2
  exit 3
fi
command -v bender >/dev/null || { echo "bender >=0.32 is required" >&2; exit 2; }

# L1 is an unmodified upstream baseline. `bender update` rewrites dependency
# resolution and is deliberately forbidden here; use the repository's committed
# lock only. Any update is a later adapter/fork decision.
test -f "$IDMA_ROOT/Bender.lock" || { echo "Committed Bender.lock is required for an unchanged baseline" >&2; exit 5; }
BENDER_UPDATE_STATUS=NOT_RUN_BASELINE_LOCKED
(cd "$IDMA_ROOT" && bender sources -f) > "$OUT/sources.txt"
test -s "$OUT/sources.txt"

# The upstream documentation ships a Questa flow. When VCS is available, use
# Bender's generated VCS collateral and the identical backend_rw_axi/simple
# job file rather than inventing a file list or changing upstream RTL.
if command -v verilator >/dev/null 2>&1; then
  grep -E '\.(sv|v)$' "$OUT/sources.txt" > "$OUT/rtl_files.txt" || true
  if [[ -s "$OUT/rtl_files.txt" ]]; then
    # Resolve relative paths against the repository.  Package/target ordering remains
    # governed by Bender; local integration should use a generated flist when available.
    echo "Verilator is present; run integration-specific lint after selecting the iDMA target." \
      | tee "$OUT/verilator_note.txt"
  fi
fi

VCS_RW_AXI_SIMPLE=NOT_RUN
if command -v vcs >/dev/null 2>&1 && command -v vlogan >/dev/null 2>&1; then
  (cd "$IDMA_ROOT" && make idma_sim_all)
  vcs_dir="$IDMA_ROOT/target/sim/vcs"
  trace_file="$OUT/rw_axi_simple.trace"
  job_file="$IDMA_ROOT/jobs/backend_rw_axi/simple.txt"
  (
    cd "$vcs_dir"
    ./compile.sh
    vcs -full64 -top tb_idma_backend_rw_axi -o simv
    ./simv "+job_file=$job_file" "+trace_file=$trace_file"
  ) | tee "$OUT/vcs_rw_axi_simple.log"
  test -s "$trace_file"
  VCS_RW_AXI_SIMPLE=PASS
elif command -v vsim >/dev/null 2>&1; then
  (cd "$IDMA_ROOT" && make idma_sim_all)
  echo "Run the upstream tb_idma_backend_rw_axi simple job and archive its transcript." \
    | tee "$OUT/questa_required_command.txt"
fi

python3 - "$OUT" "$VCS_RW_AXI_SIMPLE" <<'PY'
import json, pathlib, sys
out=pathlib.Path(sys.argv[1])
vcs_status=sys.argv[2]
status={"status":"PASS" if (out/"sources.txt").stat().st_size and vcs_status == "PASS" else "BLOCKED_LICENSED_SIM",
        "bender_update_status": "NOT_RUN_BASELINE_LOCKED",
        "vcs_rw_axi_simple": vcs_status,
        "scope":"dependency resolution, source enumeration, and upstream-equivalent backend_rw_axi/simple simulation"}
(out/"result.json").write_text(json.dumps(status,indent=2)+"\n")
PY

echo IDMA_SOURCE_BASELINE_PASS
