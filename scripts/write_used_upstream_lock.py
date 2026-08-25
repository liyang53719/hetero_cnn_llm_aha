#!/usr/bin/env python3
"""Write a lock for the exact third-party dependency closure used by this project."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def submodules(repo: Path) -> dict[str, dict[str, str]]:
    values: dict[str, dict[str, str]] = {}
    for line in git(repo, "submodule", "status", "--recursive").splitlines():
        if not line:
            continue
        marker = line[0]
        fields = line[1:].strip().split(maxsplit=2)
        if len(fields) < 2:
            continue
        values[fields[1]] = {"marker": marker, "commit": fields[0]}
    return values


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    closure = json.loads((root / "third_party" / "used_upstream_closure.json").read_text())
    repos: dict[str, object] = {}
    failures: list[str] = []

    for name, spec in closure["repositories"].items():
        repo = root / spec["path"]
        if not (repo / ".git").exists():
            failures.append(f"{name}: repository missing")
            continue
        status = git(repo, "status", "--porcelain")
        module_map = submodules(repo)
        required = {}
        for path in spec["required_submodules"]:
            entry = module_map.get(path)
            if entry is None:
                failures.append(f"{name}: required submodule absent from status: {path}")
                continue
            required[path] = entry
            if entry["marker"] != " ":
                failures.append(f"{name}: required submodule not exact: {path} ({entry['marker']})")
        if status:
            failures.append(f"{name}: worktree dirty")
        repos[name] = {
            "path": spec["path"],
            "commit": git(repo, "rev-parse", "HEAD"),
            "origin": git(repo, "remote", "get-url", "origin"),
            "dirty": bool(status),
            "required_submodules": required,
        }

    lock = {
        "schema_version": 1,
        "closure_config": "third_party/used_upstream_closure.json",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "repositories": repos,
    }
    for path in (root / "work" / "upstream" / "UPSTREAM_LOCK.json", root / "reports" / "execution" / "upstream_closure.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": lock["status"], "failures": failures}, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
