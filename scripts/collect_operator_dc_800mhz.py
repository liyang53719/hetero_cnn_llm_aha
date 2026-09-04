#!/usr/bin/env python3
import hashlib
import json
import re
import sys
from pathlib import Path


group, source_dir, output = sys.argv[1:4]
source = Path(source_dir)
runs = []
for status_path in sorted(source.glob("*/status.txt")):
    fields = {}
    for line in status_path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value
    log = status_path.with_name("dc.log")
    if not fields.get("TOTAL_AREA"):
        area_report = status_path.with_name("area_hier.rpt")
        match = re.search(r"^Total cell area:\s+([0-9.]+)", area_report.read_text(), re.MULTILINE)
        fields["TOTAL_AREA"] = match.group(1) if match else None
    fields["STATUS_SHA256"] = hashlib.sha256(status_path.read_bytes()).hexdigest()
    fields["LOG_SHA256"] = hashlib.sha256(log.read_bytes()).hexdigest() if log.exists() else None
    runs.append(fields)
passed = sum(run.get("STATUS") == "PASS" for run in runs)
wns_values = [float(run["WORST_SLACK_NS"]) for run in runs if run.get("WORST_SLACK_NS") not in (None, "NA")]
area_values = [float(run["TOTAL_AREA"]) for run in runs if run.get("TOTAL_AREA")]
payload = {
    "schema_version": 1,
    "status": "PASS" if runs and passed == len(runs) else "FAIL",
    "group": group,
    "clock_period_ns": 1.25,
    "library": "CLN22UL base SVT TT 0.8V 25C",
    "runs": len(runs),
    "passed": passed,
    "minimum_wns_ns": min(wns_values) if wns_values else None,
    "summed_independent_cell_area": sum(area_values) if area_values else None,
    "results": runs,
    "evidence_boundary": "Per-module pre-layout DC; not endpoint-bound combined shell or post-route signoff."
}
Path(output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(json.dumps(payload, indent=2, sort_keys=True))
