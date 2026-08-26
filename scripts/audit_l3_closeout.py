#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        raise SystemExit(f"L3_CLOSEOUT_FAIL missing={path}")
    return target.read_text(errors="replace")


checks = {
    "combined": "HETERO_L3_PRODUCTION_TOP_COMBINED_PASS commands=100003 l2=100002 reads=51313 writes=48689 responses=51313 streams=10000 matrix=15000 aha=5000 kv=5000 promotions=1099 conflicts=8524 rstall=4084 wstall=4440"
    in text("work/results/l3_combined/verilator_100k.log"),
    "command_fabric": "HETERO_L3_COMMAND_FABRIC_PASS commands=100003 completions=100003 illegal=1"
    in text("work/results/l3_command_fabric/verilator_100k.log"),
    "stream_complex": "HETERO_L3_STREAM_COMPLEX_100K_PASS transfers=100000 matrix=150000 aha=50000 kv=50000"
    in text("work/results/l3_stream_complex/verilator_100k.log"),
    "completion_rr": "ENGINE_COMPLETION_RR_100K_PASS grants=100000"
    in text("work/results/l3_completion_rr/verilator_100k.log"),
    "event_real_sram": "COMMAND_EVENT_SCOREBOARD_SRAM_100K_PASS commands=100000 success=100000 errors=23"
    in text("work/results/l3_event_scoreboard_sram/tb.log"),
    "shared_l2_real_macros": "TB_SHARED_L2_100K_PASS transactions=100000 reads=47346 writes=52654"
    in text("work/results/l3_macro_fabric/tb.log"),
    "pinned_gemmini": "GEMMINI_PINNED_SPAD_GATEWAY_PASS transfers=100000"
    in text("work/results/l3_spad_gateway/pinned_100k.log"),
    "aha_kv_endpoints": "AHA_KV_TENSOR_ENDPOINTS_100K_PASS transfers=100000"
    in text("work/results/l3_aha_kv_endpoints/tb_100k.log"),
    "strict_lint": "Warning" not in text("work/results/l3_combined/verilator_lint.log")
    and "%Error" not in text("work/results/l3_combined/verilator_lint.log"),
}

result = json.loads(text("reports/execution/l3_closeout_result.json"))
ledger = json.loads(text("reports/execution/MASTER_LEDGER.json"))
checks["result_status"] = result["status"] == "PASS"
checks["ledger_status"] = ledger["stages"]["L3"]["status"] == "PASS"
checks["dependency"] = ledger["stages"]["L2"]["status"] == "PASS"
checks["remaining_empty"] = ledger["stages"]["L3"]["remaining_gates"] == []

failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise SystemExit("L3_CLOSEOUT_FAIL checks=" + ",".join(failed))
print(f"L3_CLOSEOUT_AUDIT_PASS checks={len(checks)}")
