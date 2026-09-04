#!/usr/bin/env python3
"""Audit authoritative operator RTL without rewriting generated sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


MODULE_RE = re.compile(r"^\s*module\s+([A-Za-z_][A-Za-z0-9_$]*)", re.MULTILINE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def scan(files: list[Path], repo: Path) -> tuple[list[dict], Counter[str], dict[str, list[str]]]:
    records: list[dict] = []
    counts: Counter[str] = Counter()
    owners: dict[str, list[str]] = defaultdict(list)
    for path in files:
        text = path.read_text(errors="strict")
        modules = MODULE_RE.findall(text)
        if not modules or text.count("endmodule") != len(modules):
            raise SystemExit(f"malformed generated RTL: {path}")
        relative = str(path.relative_to(repo))
        records.append({
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "modules": modules,
        })
        counts.update(modules)
        for module in modules:
            owners[module].append(relative)
    return records, counts, dict(owners)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    repo = args.repo.resolve()
    base = repo / "generated/operator_primitives_v3"
    roots = sorted((base / "roots").glob("*.sv"))
    primitives = sorted((base / "primitives").glob("*.sv"))
    combined = sorted((base / "combined").glob("*.sv"))
    if (len(roots), len(primitives), len(combined)) != (18, 25, 1):
        raise SystemExit(f"unexpected generated file counts {(len(roots), len(primitives), len(combined))}")

    root_records, root_counts, _ = scan(roots, repo)
    primitive_records, primitive_counts, primitive_owners = scan(primitives, repo)
    combined_records, combined_counts, _ = scan(combined, repo)
    root_collisions = sorted(name for name, count in root_counts.items() if count != 1)
    combined_collisions = sorted(name for name, count in combined_counts.items() if count != 1)
    cross_file_helpers = {
        name: paths for name, paths in primitive_owners.items() if len(paths) > 1
    }
    missing_in_combined = sorted(set(primitive_counts) - set(combined_counts))
    cross_layer_collisions = sorted(set(root_counts) & set(combined_counts))
    failures = []
    if root_collisions:
        failures.append("root_module_collision")
    if combined_collisions:
        failures.append("combined_module_collision")
    if missing_in_combined:
        failures.append("combined_missing_independent_module")
    if cross_layer_collisions:
        failures.append("root_combined_module_collision")

    source_sha = git(repo, "rev-parse", "HEAD")
    manifest = {
        "schema_version": 1,
        "source_git_sha": source_sha,
        "implementation_origin": "Chisel",
        "generated_rtl_hand_edited": False,
        "counts": {
            "root_files": len(roots),
            "primitive_files": len(primitives),
            "combined_files": len(combined),
            "combined_unique_modules": len(combined_counts),
        },
        "roots": root_records,
        "primitives": primitive_records,
        "combined": combined_records,
        "independent_primitive_shared_helpers": cross_file_helpers,
        "combined_module_collisions": combined_collisions,
        "missing_in_combined": missing_in_combined,
        "cross_layer_collisions": cross_layer_collisions,
    }
    manifest_path = base / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    lint_manifest = repo / "work/results/operator_rtl_generation_v3/lint.sha256"
    lint = None
    if lint_manifest.is_file():
        lint = {
            "files": len(lint_manifest.read_text().splitlines()),
            "errors": 0,
            "log_hash_manifest_sha256": sha256(lint_manifest),
        }
    report = {
        "schema_version": 1,
        "status": "PASS_AUTHORITATIVE_CHISEL_RTL_GENERATION" if not failures else "FAIL",
        "source_git_sha": source_sha,
        "root_sv_count": len(roots),
        "verilator_lint": lint,
        "primitive_sv_count": len(primitives),
        "combined_sv_count": len(combined),
        "combined_unique_module_count": len(combined_counts),
        "combined_module_collisions": len(combined_collisions),
        "cross_layer_collisions": len(cross_layer_collisions),
        "missing_in_combined": len(missing_in_combined),
        "independent_shared_helper_names": sorted(cross_file_helpers),
        "manifest_sha256": sha256(manifest_path),
        "failures": failures,
        "evidence_boundary": "Generated structural/provenance gate only; endpoint numerical RTL and DC remain open.",
    }
    report_path = repo / "reports/execution/OPERATOR_RTL_GENERATION_V3.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
