#!/usr/bin/env python3
"""Record the honest state of the resumable upstream clone."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        capture_output=True,
    ).stdout


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    upstream = root / "work" / "upstream"
    chipyard = upstream / "chipyard"
    status = git(chipyard, "submodule", "status", "--recursive") if (chipyard / ".git").exists() else ""
    uninitialized = [line.split(maxsplit=1)[1] for line in status.splitlines() if line.startswith("-")]
    non_exact = [line.split(maxsplit=1)[1] for line in status.splitlines() if line.startswith("+")]
    dirty = git(chipyard, "status", "--porcelain").splitlines() if (chipyard / ".git").exists() else []
    repos = {}
    for repo in sorted(upstream.iterdir()) if upstream.exists() else []:
        if (repo / ".git").exists():
            repos[repo.name] = {
                "commit": git(repo, "rev-parse", "HEAD").strip(),
                "dirty": bool(git(repo, "status", "--porcelain").strip()),
            }
    report = {
        "status": "PASS" if not uninitialized and not non_exact and not dirty and (upstream / "UPSTREAM_LOCK.json").exists() else "BLOCKED_PARTIAL_RECURSIVE_CLONE",
        "chipyard_commit": git(chipyard, "rev-parse", "HEAD").strip() if (chipyard / ".git").exists() else "",
        "uninitialized_submodules": uninitialized,
        "non_exact_submodules": non_exact,
        "chipyard_dirty_entries": dirty[:80],
        "top_level_repositories": repos,
        "upstream_lock_present": (upstream / "UPSTREAM_LOCK.json").exists(),
        "license_matrix_present": (root / "work" / "results" / "licenses" / "license_matrix.csv").exists(),
        "observed_blockers": [
            "recursive clone was interrupted after large nested FireSim/Chipyard dependencies",
            "sourceware newlib endpoint returned HTTP 429 during ARA nested clone",
            "llvm-project nested clone encountered a TLS EOF/index-pack failure",
        ],
    }
    out = root / "reports" / "upstream_progress.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "uninitialized": len(uninitialized), "output": str(out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
