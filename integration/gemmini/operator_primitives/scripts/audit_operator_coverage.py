#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import yaml

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[2]
SCALA = PACKAGE / "src" / "main" / "scala" / "gemmini"
sys.path.insert(0, str(PACKAGE))
from reference.operator_primitives_reference import (  # noqa: E402
    MODEL_REQUIRED_OPERATORS,
    OPERATOR_PHASE_COUNTS,
    TERMINAL_PRIMITIVE_BINDINGS,
    TERMINAL_PRIMITIVE_OWNERS,
    terminal_sequence,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "reports/execution/operator_primitive_coverage_800mhz.json")
    args = parser.parse_args()

    manifest_path = PACKAGE / "operator_coverage_800mhz.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    protocol = (SCALA / "HeteroOperatorPrimitiveProtocol.scala").read_text()
    sequencer = (SCALA / "HeteroModelOperatorSequencer.scala").read_text()
    catalog = (SCALA / "EmitHeteroOperatorPrimitiveCatalog.scala").read_text()
    capability = (SCALA / "HeteroPrimitiveCapability.scala").read_text()
    binding_path = PACKAGE / "terminal_primitive_bindings_800mhz.yaml"
    binding = yaml.safe_load(binding_path.read_text())

    id_block = protocol.split("object HeteroModelOperatorId", 1)[1].split("class HeteroOperatorCommand", 1)[0]
    ids = sorted(set(re.findall(r"val\s+([A-Za-z0-9_]+)\s*=", id_block)) - {"width"})
    parsed_counts = {
        name: int(count)
        for name, count in re.findall(
            r"is\(HeteroModelOperatorId\.([A-Za-z0-9_]+)\)\s*\{\s*count\s*:=\s*(\d+)\.U",
            sequencer,
        )
    }
    catalog_names = sorted(set(re.findall(r'^\s*"([a-z0-9_]+)",?\s*$', catalog, re.MULTILINE)))

    model_results = {}
    failures = []
    for model, required in MODEL_REQUIRED_OPERATORS.items():
        missing = sorted(set(required) - set(ids))
        manifest_missing = manifest["models"][model]["missing"]
        if missing or manifest_missing:
            failures.append(f"{model}: missing={missing}, manifest_missing={manifest_missing}")
        terminal_ops = tuple(
            opcode
            for operator in required
            for opcode in terminal_sequence(operator)
        )
        model_results[model] = {
            "required": len(required),
            "missing": missing,
            "phase_micro_ops": sum(parsed_counts.get(name, 0) for name in required),
            "terminal_micro_ops": len(terminal_ops),
            "unique_terminal_opcodes": len(set(terminal_ops)),
            "unbound_terminal_opcodes": sorted(set(terminal_ops) - TERMINAL_PRIMITIVE_BINDINGS),
            "coverage": "complete" if not missing else "incomplete",
        }

    if set(ids) != set(OPERATOR_PHASE_COUNTS):
        failures.append("model operator id set differs from reference")
    if parsed_counts != OPERATOR_PHASE_COUNTS:
        failures.append("sequencer phase counts differ from reference")
    if manifest["clock"]["target_hz"] != 800_000_000 or manifest["clock"]["period_ns"] != 1.25:
        failures.append("manifest clock is not 800MHz/1.25ns")
    flattened_bindings = {}
    for owner, provider in binding["providers"].items():
        for opcode in provider["opcodes"]:
            if opcode in flattened_bindings:
                failures.append(f"duplicate terminal binding: {opcode}")
            flattened_bindings[opcode] = owner
    if flattened_bindings != TERMINAL_PRIMITIVE_OWNERS:
        failures.append("terminal binding manifest differs from reference owner map")
    if len(catalog_names) != 25:
        failures.append(f"catalog module count is {len(catalog_names)}, expected 25")
    for opcode, owner in TERMINAL_PRIMITIVE_OWNERS.items():
        if f"HeteroPrimitiveOpcode.{opcode}" not in capability:
            failures.append(f"capability registry missing opcode {opcode}")
        if f"HeteroPrimitiveOwner.{owner}" not in capability:
            failures.append(f"capability registry missing owner {owner}")
    for model, result in model_results.items():
        if result["unbound_terminal_opcodes"]:
            failures.append(f"{model}: unbound terminals={result['unbound_terminal_opcodes']}")
    for path in SCALA.glob("*.scala"):
        if re.search(r"\b(?:TODO|FIXME)\b|\?\?\?", path.read_text()):
            failures.append(f"incomplete marker in {path.name}")

    source_files = sorted(SCALA.glob("*.scala"))
    result = {
        "schema_version": 1,
        "status": "PASS_OPERATOR_PRIMITIVE_COVERAGE" if not failures else "FAIL_OPERATOR_PRIMITIVE_COVERAGE",
        "clock": {"target_hz": 800_000_000, "period_ns": 1.25},
        "operator_ids": len(ids),
        "catalog_modules": len(catalog_names),
        "terminal_binding_count": len(flattened_bindings),
        "terminal_owner_counts": {
            owner: sum(1 for bound_owner in flattened_bindings.values() if bound_owner == owner)
            for owner in sorted(set(flattened_bindings.values()))
        },
        "models": model_results,
        "failures": failures,
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in source_files},
        "manifest_sha256": sha256(manifest_path),
        "terminal_binding_manifest_sha256": sha256(binding_path),
        "claim_boundary": "Chisel operator primitive source/semantic/static closure; generated RTL, RTL simulation and DC remain local-agent gates.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
