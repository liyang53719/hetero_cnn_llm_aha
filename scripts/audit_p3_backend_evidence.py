#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.p3_backend_evidence import audit_repository
p = argparse.ArgumentParser()
p.add_argument("--root", type=Path, default=ROOT)
p.add_argument("--output", type=Path, default=ROOT / "reports/execution/REMOTE_AUDIT_11483E8.json")
p.add_argument("--audited-commit", default="11483e863b6d0f17885258aaab5e8cfd6e63b0dc")
a = p.parse_args()
r = audit_repository(a.root)
r["audited_commit"] = a.audited_commit
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(r, indent=2, sort_keys=True))
raise SystemExit(0 if r["status"].startswith("PASS") else 1)
