#!/usr/bin/env python3
"""Partition Chisel suites by immutable fixture kind, never by test order."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

FIXTURE_SUITES = {
    "tiny": "heteronpu.continuous.HostBlockCommandsSpec",
    "real": "heteronpu.continuous.HostBlockCommandsRealLayersSpec",
    "native": "heteronpu.continuous.HostBlockCommandsNativeWeightsSpec",
}

# Explicit external-data suite: never construct it with the tiny synthetic
# OWNER_FIXTURE. The dedicated register-loan runner selects it only with pinned
# real producer manifests; absent manifests remain a hard error there.
EXTERNAL_FIXTURE_SUITES = {
    "frozen_actual_rms_epilogue": "heteronpu.continuous.ElementwiseRegisterLoanReplaySpec",
    "frozen_actual_h2048_rms": "heteronpu.continuous.GdnRmsNormFixedBankReplaySpec",
}

RUN_GROUPS = ("general", "tiny", "real", "native")

def plan(project: Path) -> dict[str, list[str]]:
    directory = project / "src/test/scala/heteronpu/continuous"
    names = sorted("heteronpu.continuous." + path.stem for path in directory.glob("*Spec.scala"))
    classified = set(FIXTURE_SUITES.values()) | set(EXTERNAL_FIXTURE_SUITES.values())
    missing = classified - set(names)
    if missing:
        raise ValueError("MISSING_FIXTURE_SUITE:" + ",".join(sorted(missing)))
    result = {"general": [name for name in names if name not in classified]}
    result.update({group: [name] for group, name in FIXTURE_SUITES.items()})
    result.update({group: [name] for group, name in EXTERNAL_FIXTURE_SUITES.items()})
    flat = [name for group in result.values() for name in group]
    if sorted(flat) != names or len(flat) != len(set(flat)):
        raise ValueError("SUITE_COVERAGE_MISMATCH")
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = plan(args.project.resolve())
    with args.output.open("x") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
