#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l10_owner_hierarchy};R=$ROOT/scripts/run_memory_capped.sh;DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell};DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db};mkdir -p "$OUT";rm -f "$OUT/status.txt"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s env STD_CELL_DB="$DB" OUT_DIR="$OUT" MATRIX_DDC="$ROOT/work/generated/l5_matrix_rev8b_b/top/bf16_outer_product_context_array_rev8b_b_candidate.ddc" CONTROLLER_DDC="$ROOT/work/results/l5_blocked_attention_controller_dc/blocked_attention_stream_controller.ddc" TILE_DDC="$ROOT/work/results/l5_block32_tile16_bottomup_dc/fp32_block32_softmax_tile16_candidate.ddc" MERGE_DDC="$ROOT/work/results/l5_mlo_merge8_bottomup_dc_low/fp32_mlo_merge8_candidate.ddc" SILU_DDC="$ROOT/work/results/l5_silu_lut_dc/lanes1/bf16_silu_mul_lut_1lane.ddc" RSQRT_DDC="$ROOT/work/results/l5_fp32_rsqrt_nr2_dc/fp32_rsqrt_nr2.ddc" "$DC" -64bit -f "$ROOT/dc/l10_owner_hierarchy.tcl" >"$OUT/dc.log" 2>&1
taskset -c 8-23 python3 - "$OUT" <<'PY'
from pathlib import Path
import re,sys
d=Path(sys.argv[1]);s=dict(x.split('=',1)for x in(d/'status.txt').read_text().splitlines()if'='in x);q=(d/'qor.rpt').read_text(errors='replace');a=(d/'area_hier.rpt').read_text(errors='replace')
def n(k):
 m=re.search(rf'{re.escape(k)}\s*:\s*([0-9]+)',q);return int(m.group(1))if m else 0
am=re.search(r'Design Area:\s*([0-9.]+)',q);r={'wns_ns':float(s['WORST_SLACK_NS']),'area':float(am.group(1))if am else 0.0,'unmapped':int(s['UNMAPPED_CELLS']),'unresolved':int(s['UNRESOLVED_REFERENCES']),'blackboxes':int(s['BLACKBOX_CELLS']),'max_transition':n('Max Trans Violations'),'max_cap':n('Max Cap Violations'),'owners':int(s['OWNER_INSTANCES'])};print(r)
if r['wns_ns']<0 or any(r[k]for k in('unmapped','unresolved','blackboxes','max_transition','max_cap'))or r['owners']!=6:raise SystemExit(1)
PY
