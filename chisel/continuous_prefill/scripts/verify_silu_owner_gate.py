#!/usr/bin/env python3
"""Validate the exact SiLU A/B case set. Never promote component cycles to model throughput."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def verify(root: Path) -> dict:
    raw = (root / "tests.log").read_text()
    text = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    require("All tests passed." in text and not re.search(r"\*\*\*|FAILED|ABORTED|Fatal|%Error", text), "failed/incomplete simulation")
    require("Tests: succeeded 4, failed 0, canceled 0, ignored 0, pending 0" in text, "incomplete ScalaTest run")
    for marker in ("SILU_OWNER_SUITE_PASS mode=baseline numeric_cases=13 fault_cases=0",
                   "SILU_OWNER_SUITE_PASS mode=overlap numeric_cases=17 fault_cases=6",
                   "SILU_OWNER_REJECT_PASS cases=7 memory_requests=0",
                   "SILU_VECTOR_EXACT_PASS checked_fp32=192 lanes=16"):
        require(text.count(marker) == 1, "missing/duplicate marker: " + marker)
    require("SOURCE_IMMUTABILITY_PASS" in (root / "source_verify.log").read_text(), "unverified source identity")
    pattern = re.compile(r"^SILU_OWNER_CASE mode=(baseline|overlap) elements=(\d+) seed=(\d+) fault=([a-z-]+) cycles=(\d+) checked_fp32=(\d+) read_beats=(\d+) write_ack_bytes=(\d+)$", re.M)
    rows = []
    for m in pattern.finditer(text):
        mode, count, seed, fault, cycles, checked, reads, written = m.groups()
        rows.append(dict(mode=mode, elements=int(count), seed=int(seed), fault=fault,
                         cycles=int(cycles), checked_fp32=int(checked), read_beats=int(reads), write_ack_bytes=int(written)))
    common = {(seed, (16, 32, 64, 256)[seed % 4]) for seed in range(1, 13)} | {(101, 1024)}
    expected = {(mode, n, seed, "none") for mode in ("baseline", "overlap") for seed, n in common}
    expected |= {("overlap", 32, seed, "none") for seed in range(220, 224)}
    faults = [(201, "numerical-late-store"), (202, "numerical-stalled-store"),
              (210, "read-gate"), (211, "read-up"), (212, "last-store"), (213, "tag")]
    expected |= {("overlap", 64, seed, fault) for seed, fault in faults}
    keys = [(r["mode"], r["elements"], r["seed"], r["fault"]) for r in rows]
    require(len(rows) == len(expected) and set(keys) == expected, "missing/duplicate/unexpected case")
    acks = re.findall(r"^SILU_OWNER_ACK_OBSERVED mode=(baseline|overlap) fault=([a-z-]+) acknowledged_bytes=(\d+) reported_bytes=(\d+) late_ack=(true|false)$", text, re.M)
    require(len(acks) == len(rows), "incomplete ACK observations")
    for row, (mode, fault, observed, reported, late) in zip(rows, acks):
        require(mode == row["mode"] and fault == row["fault"], "ACK observation order")
        require(int(observed) == int(reported) == row["write_ack_bytes"], "ACK accounting mismatch")
        if fault.startswith("numerical"):
            require(late == "true" and int(observed) > 0, "numerical/late-ACK race not covered")
        require(row["cycles"] > 0, "zero cycles")
        if fault == "none":
            require(row["checked_fp32"] == row["elements"], "partial numerical comparison")
            require(row["read_beats"] * 8 == row["elements"], "operand traffic changed")
            require(row["write_ack_bytes"] == row["elements"] * 4, "missing successful writes")
    lookup = {(r["mode"], r["seed"]): r for r in rows if r["fault"] == "none"}
    comparison = []
    for seed, n in sorted(common):
        base, candidate = lookup["baseline", seed], lookup["overlap", seed]
        comparison.append(dict(elements=n, seed=seed, baseline_cycles=base["cycles"],
                               overlap_cycles=candidate["cycles"], speedup=base["cycles"] / candidate["cycles"]))
    return {"status": "PASS_SILU_OWNER_COMPONENT", "scalatest_tests": 4,
            "numeric_owner_cases": 30, "fault_cases": 6, "rejected_jobs": 7,
            "checked_owner_fp32": sum(r["checked_fp32"] for r in rows),
            "checked_vector_fp32": 192, "comparison": comparison,
            "scope": {"actual_chisel_verilator": True, "memory_service_test_model": True,
                      "pinned_idma_in_this_test": False, "host_real16_two_layer": False,
                      "official_weights": False, "physical_timing_signoff": False,
                      "jitter": "same seeded algorithm; not a cycle-identical DRAM replay"},
            "tests_log_sha256": hashlib.sha256((root / "tests.log").read_bytes()).hexdigest()}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("evidence", type=Path)
    args = p.parse_args()
    result = verify(args.evidence)
    with (args.evidence / "RESULT.json").open("x") as f:
        json.dump(result, f, indent=2); f.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
