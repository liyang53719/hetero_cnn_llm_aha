#!/usr/bin/env python3
"""Run every public-model test file in its own interpreter, without weakening pins."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE = Path("candidates/qwen2_resident_matrix/ffn_public")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_suite(root: Path, suite: Path, out: Path, timeout: int = 120) -> dict:
    if not 1 <= timeout <= 300:
        raise ValueError("per-file timeout must be in 1..300 seconds")
    root, suite, out = root.resolve(), suite.resolve(), out.resolve()
    suite.relative_to(root)
    files = sorted(suite.rglob("test_*.py"))
    if not files or any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError("nonempty regular test-file discovery required")
    inventory = [{"path": str(p.relative_to(root)), "sha256": digest(p)} for p in files]
    out.mkdir(parents=True, exist_ok=False)
    summary = {"schema": "isolated-public-tests-v1", "python": sys.executable,
               "discovery_pattern": "test_*.py", "inventory": inventory,
               "results": [], "total_tests": 0, "status": "RUNNING", "exit_code": None}

    def save():
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    save()
    for index, (path, identity) in enumerate(zip(files, inventory)):
        command = [sys.executable, "-m", "unittest", "discover", "-s", str(path.parent),
                   "-p", path.name, "-v"]
        logfile = out / f"{index:02d}-{path.stem}.log"
        start = time.monotonic()
        timed_out = False
        with logfile.open("w") as log:
            try:
                process = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                         timeout=timeout, check=False)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code, timed_out = 124, True
        output = logfile.read_text(errors="replace")
        counts = re.findall(r"^Ran (\d+) tests? in [^\n]+$", output, re.M)
        count = int(counts[0]) if len(counts) == 1 else None
        success = (code == 0 and count is not None and count > 0
                   and bool(re.search(r"^OK$", output, re.M))
                   and digest(path) == identity["sha256"])
        result = {**identity, "command": command, "test_count": count, "returncode": code,
                  "timed_out": timed_out, "passed": success,
                  "host_wall_seconds": time.monotonic() - start,
                  "log": logfile.name, "log_sha256": digest(logfile)}
        summary["results"].append(result)
        summary["total_tests"] += count or 0
        print(f"{identity['path']}: tests={count} exit={code} passed={success}", flush=True)
        save()
    after = [{"path": str(p.relative_to(root)), "sha256": digest(p)}
             for p in sorted(suite.rglob("test_*.py"))]
    summary["inventory_unchanged"] = after == inventory
    passed = summary["inventory_unchanged"] and all(r["passed"] for r in summary["results"])
    summary.update(status="PASS" if passed else "FAIL", exit_code=0 if passed else 1)
    save()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    return run_suite(ROOT, ROOT / SUITE, args.out, args.timeout)["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
