#!/usr/bin/env python3
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
inventory_path = ROOT / "config/operator_endpoint_inventory_v3.json"
contract_path = ROOT / "integration/gemmini/operator_primitives/terminal_primitive_bindings_800mhz.yaml"
output_path = ROOT / "reports/execution/OPERATOR_ENDPOINT_AUDIT_V3.json"

inventory = json.loads(inventory_path.read_text())
contract = yaml.safe_load(contract_path.read_text())
expected = {
    owner: set(provider["opcodes"])
    for owner, provider in contract["providers"].items()
}
actual = {
    owner: set(provider["opcodes"])
    for owner, provider in inventory["owners"].items()
}
failures = []
if expected != actual:
    failures.append("owner_opcode_inventory_mismatch")

missing_sources = []
for owner, provider in inventory["owners"].items():
    for source in provider["candidate_sources"]:
        path = ROOT / source
        if not path.exists():
            missing_sources.append({"owner": owner, "source": source})
if missing_sources:
    failures.append("missing_candidate_source")

opcode_count = sum(len(opcodes) for opcodes in actual.values())
bound = sum(
    len(provider["opcodes"])
    for provider in inventory["owners"].values()
    if provider["v3_endpoint_adapter"] is not None
)
source_text = "\n".join(
    path.read_text(errors="ignore")
    for path in ROOT.glob("rtl/**/*.sv")
)
immediate_patterns = len(re.findall(r"completion_valid[^\n]*=\s*(?:1'b1|cmd_valid)", source_text))
report = {
    "schema_version": 1,
    "status": "PASS_AUDIT_REAL_ENDPOINT_BINDING_OPEN" if not failures else "FAIL",
    "terminal_opcode_contract": opcode_count,
    "candidate_source_coverage": opcode_count if not missing_sources else 0,
    "real_v3_endpoint_bindings": bound,
    "open_v3_endpoint_bindings": opcode_count - bound,
    "owners_with_real_v3_adapter": [
        owner for owner, provider in inventory["owners"].items()
        if provider["v3_endpoint_adapter"] is not None
    ],
    "owners_open": [
        owner for owner, provider in inventory["owners"].items()
        if provider["v3_endpoint_adapter"] is None
    ],
    "missing_candidate_sources": missing_sources,
    "legacy_immediate_completion_patterns_for_manual_review": immediate_patterns,
    "failures": failures,
    "claim_boundary": f"All {opcode_count} opcodes have candidate source roots; {bound} have a canonical V3 request/completion adapter. Candidate source coverage is not endpoint binding."
}
output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
print(json.dumps(report, indent=2, sort_keys=True))
raise SystemExit(1 if failures else 0)
