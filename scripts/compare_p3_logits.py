#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.logits_parity import LogitThresholds, compare_files
p = argparse.ArgumentParser()
p.add_argument("--actual", type=Path, required=True)
p.add_argument("--reference", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--relative-l2-max", type=float, default=1.0e-2)
p.add_argument("--cosine-min", type=float, default=0.9999)
a = p.parse_args()
r = compare_files(a.actual, a.reference, LogitThresholds(relative_l2_max=a.relative_l2_max, cosine_min=a.cosine_min))
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(r, indent=2, sort_keys=True))
raise SystemExit(0 if r["status"].startswith("PASS") else 1)
