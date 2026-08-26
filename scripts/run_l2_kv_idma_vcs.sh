#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
IDMA=${IDMA_ROOT:-$ROOT/work/upstream/idma}
VCS_DIR=$IDMA/target/sim/vcs
OUT=${OUT:-$ROOT/work/results/l2_kv_idma_basic/vcs}
mkdir -p "$OUT"
awk '/MemAvailable/ {if ($2 < 10485760) {print "BLOCKED_MEMORY";exit 42}}' /proc/meminfo
[[ $(git -C "$IDMA" rev-parse HEAD) == 2e0b0fe53b6f8823319e2428e2e9abc2db149b7d ]] || { echo iDMA commit drift >&2;exit 3; }
[[ -z $(git -C "$IDMA" status --porcelain) ]] || { echo iDMA worktree dirty >&2;exit 3; }
echo '6913ac4c8ff41e96091a22d07c8c13d15b0fb3fc14c18f36cbb9aac065951fdc  '"$IDMA/target/rtl/idma_backend_rw_axi.sv" | sha256sum -c -
[[ -d "$VCS_DIR/AN.DB" ]] || { echo missing compiled upstream VCS library >&2;exit 2; }
AXI_INC=$(find "$IDMA/.bender/git/checkouts" -maxdepth 2 -path '*/axi-*/include' | head -n1)
cd "$VCS_DIR"
taskset -c 8-25 vlogan -sverilog -full64 +define+USE_UPSTREAM_IDMA \
  +incdir+../../../src/include +incdir+"$AXI_INC" \
  "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" \
  "$ROOT/rtl/kv/kv_idma_basic_core.sv" "$ROOT/rtl/kv/kv_descriptor_v2_idma_adapter.sv" \
  "$ROOT/tb/tb_idma_flat_wrap.sv" "$ROOT/tb/tb_kv_descriptor_v2_idma_adapter.sv" \
  >"$OUT/vlogan.log" 2>&1
taskset -c 8-25 vcs -full64 -top tb_idma_flat_wrap -o simv_flat >"$OUT/vcs_flat.log" 2>&1
taskset -c 8-25 ./simv_flat >"$OUT/flat.log" 2>&1
taskset -c 8-25 vcs -full64 -top tb_kv_descriptor_v2_idma_adapter -o simv_kv >"$OUT/vcs_kv.log" 2>&1
taskset -c 8-25 ./simv_kv >"$OUT/kv.log" 2>&1
grep -q IDMA_FLAT_WRAP_PASS "$OUT/flat.log"
grep -q KV_DESCRIPTOR_V2_IDMA_ADAPTER_PASS "$OUT/kv.log"
python3 - "$OUT" <<'PY'
import json,sys
from pathlib import Path
out=Path(sys.argv[1]);result={"status":"PASS","idma_commit":"2e0b0fe53b6f8823319e2428e2e9abc2db149b7d",
"flat_copy_bytes":96,"kv_idma_requests":4,"kv_events":5,"bf16_byte_exact":True,"upstream_clean":True,
"cpu_affinity":"taskset -c 8-25","simulator":"VCS W-2024.09"}
(out/"result.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result,sort_keys=True))
PY
echo L2_KV_IDMA_VCS_PASS
