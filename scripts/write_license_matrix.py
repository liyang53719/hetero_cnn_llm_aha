#!/usr/bin/env python3
"""Generate a provenance-oriented license matrix for the pinned L1 closure."""
from __future__ import annotations

import csv
import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    entries = [
        ("chipyard_gemmini", "work/upstream/chipyard_gemmini", "LICENSE", "BSD-3-Clause", "official baseline and generated-artifact audit"),
        ("aha", "work/upstream/aha", "", "NO_TOP_LEVEL_LICENSE_FILE", "official baseline only; preserve each submodule license"),
        ("idma", "work/upstream/idma", "LICENSE", "Solderpad-0.51 / Apache-2.0 option", "external transport baseline and wrapper integration"),
        ("pulp_axi", "work/upstream/pulp_axi", "LICENSE", "Solderpad-0.51 / Apache-2.0 option", "external AXI primitive baseline and wrapper integration"),
        ("common_cells", "work/upstream/common_cells", "LICENSE", "Solderpad-0.51 / Apache-2.0 option", "external primitive baseline and wrapper integration"),
        ("imax3_llm", "work/upstream/imax3_llm", "LICENSE", "MIT", "software kernel/offload audit only; not RTL source"),
    ]
    rows = []
    for name, relative, license_file, license_name, role in entries:
        repo = root / relative
        evidence = str(Path(relative) / license_file) if license_file else "top-level license absent; component review required"
        rows.append({
            "repo": name,
            "commit": git(repo, "rev-parse", "HEAD"),
            "license": license_name,
            "license_evidence": evidence,
            "allowed_in_project": role,
            "delivery_rule": "do not vendor third-party source; retain notices and license provenance",
        })

    out_dir = root / "work" / "results" / "licenses"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "license_matrix.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    report = root / "reports" / "execution" / "LICENSE_MATRIX.md"
    lines = ["# L1 license matrix", "", "Third-party source remains external to this delivery.", "", "| Repo | Commit | License evidence | Use boundary |", "|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['repo']} | `{row['commit']}` | {row['license']} ({row['license_evidence']}) | {row['allowed_in_project']} |")
    lines += ["", "AHA has no top-level LICENSE file in this pinned umbrella checkout; its individual submodule licenses must be retained before any source redistribution."]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(csv_path)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
