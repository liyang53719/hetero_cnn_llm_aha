#!/usr/bin/env python3
"""Verify immutable local upstream checkouts and generated macro artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, text=True,
        capture_output=True).stdout.strip()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_file(checks: dict[str, bool], name: str, path: Path,
               expected: str) -> None:
    checks[f"{name}_present"] = path.is_file()
    checks[f"{name}_sha256"] = path.is_file() and sha(path) == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ROOT / "reports/execution/local_upstream_integrity.json")
    args = parser.parse_args()
    closure = load("reports/execution/upstream_closure.json")
    gemmini = load("reports/execution/gemmini_macro_contract_lock.json")
    aha = load("reports/execution/aha_macro_contract_lock.json")
    idma = load("reports/execution/idma_backend_contract_lock.json")
    checks: dict[str, bool] = {}
    observed: dict[str, object] = {}

    for name, locked in closure["repositories"].items():
        repo = ROOT / locked["path"]
        present = (repo / ".git").exists()
        checks[f"{name}_present"] = present
        if not present:
            continue
        head = git(repo, "rev-parse", "HEAD")
        origin = git(repo, "remote", "get-url", "origin")
        status = git(repo, "status", "--porcelain", "--untracked-files=all",
                     "--ignore-submodules=none")
        live_modules: dict[str, tuple[str, str]] = {}
        for line in git(repo, "submodule", "status", "--recursive").splitlines():
            if line:
                fields = line[1:].strip().split(maxsplit=2)
                if len(fields) >= 2:
                    live_modules[fields[1]] = (line[0], fields[0])
        checks[f"{name}_commit"] = head == locked["commit"]
        checks[f"{name}_origin"] = origin == locked["origin"]
        checks[f"{name}_clean"] = status == ""
        for path, expected in locked["required_submodules"].items():
            live = live_modules.get(path)
            checks[f"{name}_submodule_{path}"] = (
                live is not None and live[0] == " "
                and live[1] == expected["commit"])
        observed[name] = {
            "commit": head, "origin": origin, "clean": status == "",
            "required_submodules": len(locked["required_submodules"]),
        }

    gemmini_path = ROOT / (
        "work/upstream/chipyard_gemmini/sims/verilator/generated-src/"
        "chipyard.harness.TestHarness.GemminiRocketConfig/gen-collateral/Gemmini.sv")
    check_file(checks, "gemmini_generated_rtl", gemmini_path,
               gemmini["gemmini_sv_sha256"])
    aha_path = ROOT / aha["generated_rtl"]
    check_file(checks, "aha_generated_rtl", aha_path,
               aha["generated_rtl_sha256"])
    aha_commit_file = ROOT / "work/generated/l2_aha_garnet_4x16/aha.commit"
    image_file = ROOT / "work/generated/l2_aha_garnet_4x16/image.ref"
    checks["aha_artifact_commit"] = (
        aha_commit_file.is_file()
        and aha_commit_file.read_text().strip() == aha["aha_commit"])
    checks["aha_artifact_image"] = (
        image_file.is_file()
        and image_file.read_text().strip() == aha["docker_image"])
    check_file(checks, "idma_backend",
               ROOT / "work/upstream/idma/target/rtl/idma_backend_rw_axi.sv",
               idma["module_sha256"])
    check_file(checks, "idma_typedef",
               ROOT / "work/upstream/idma/src/include/idma/typedef.svh",
               idma["typedef_sha256"])

    failures = sorted(name for name, passed in checks.items() if not passed)
    result = {
        "schema_version": 1,
        "status": "PASS" if not failures else "FAIL",
        "policy": "canonical upstream and generated macros are immutable",
        "upstream_source_edits": 0 if not failures else None,
        "checks": checks,
        "failures": failures,
        "observed": observed,
        "generated_artifacts": {
            "Gemmini.sv": gemmini["gemmini_sv_sha256"],
            "garnet.v": aha["generated_rtl_sha256"],
            "idma_backend_rw_axi.sv": idma["module_sha256"],
        },
        "excluded_noncanonical_checkout": "work/upstream/chipyard",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "failures": failures,
                      "output": str(args.output)}, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
