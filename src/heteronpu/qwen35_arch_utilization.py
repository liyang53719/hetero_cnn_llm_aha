"""Source-pinned Qwen3.5 layer0 M1 architectural bounds, never RTL measurements.

Run: PYTHONPATH=src python -m heteronpu.qwen35_arch_utilization --repo .
A lower bound on cycles is NOT a cycle estimate. This first pre-RTL gate
quantifies structural impossibility before spending time on RTL generation.
It does not claim M128/chunk throughput, frequency closure, or total MAC use
across differently capable Matrix and Scalar units.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

AUDITED_COMMIT = "aa9ac8277217c20c10652aa639f329e44184d6b2"
SOURCE_BASE = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/"
SOURCE_PINS = {
    "GdnRecurrentOwner.scala": "42286b5f9757d7c3b1c349f632bc7d3f7047080bd12e665c8980d9aaec7b4250",
    "BlockFloat.scala": "9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5",
    "StreamingDense.scala": "18d99633b57e5f394f99c242231a5ee009dcf125c03c8940674a01a7965ee789",
    "MatrixPipeline.scala": "dd1f3859ac65fa4d4839105cf166cb5d3a1f4d2d786991eb0f22749ad4ceca3d",
    "HostBlockCommands.scala": "68749c376fffeaed47a2b2965ec7e3af594b5409c7cd08d31c16535d75073757",
}
DENSE_SHAPES = (
    ("qkv", 1024, 6144), ("z", 1024, 2048), ("ab", 1024, 32),
    ("o", 2048, 1024), ("gate", 1024, 3584), ("up", 1024, 3584),
    ("down", 3584, 1024),
)
MATRIX_MACS_PER_CYCLE = 8 * 512  # Never reduce for idle/masked/clock-gated slices.


def verify_sources(repo: Path) -> dict[str, str]:
    observed = {}
    for name, expected in SOURCE_PINS.items():
        relative = SOURCE_BASE + name
        actual = hashlib.sha256((repo / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"source changed; re-audit scheduling assumptions: {relative}")
        observed[relative] = actual
    return observed


def report(*, tokens: int = 1, repo: Path | None = None) -> dict:
    if type(tokens) is not int or tokens != 1:
        raise ValueError("only one M1 launch is modeled; M128/chunk requires a separate schedule")
    pins = verify_sources(repo) if repo is not None else None
    dense = []
    for name, k, n in DENSE_SHAPES:
        useful = k * n
        wide_issues = k * ((n + 255) // 256)
        # All these N values are exact multiples of a physical 32-column slice.
        executed = k * ((n + 31) // 32) * 512
        dense.append({"name": name, "m": 1, "k": k, "n": n,
                      "useful_macs": useful, "wide_issue_cycles_lower_bound": wide_issues,
                      "issued_physical_lane_macs": executed,
                      "geometry_utilization_upper_bound": useful / (4096 * wide_issues)})
    useful = sum(x["useful_macs"] for x in dense)
    issue_min = sum(x["wide_issue_cycles_lower_bound"] for x in dense)
    cells = 16 * 128 * 128
    vectors = 16 * 128
    # Per state cell: decay/predict/rank/output multiply; predict/update/output add.
    # Per value: subtract and beta multiply. Exp is deliberately excluded below.
    mul = 4 * cells + vectors
    add = 3 * cells + vectors
    basic = mul + add
    # Scalar request at E0 (idle), normal at E1, result at E2 (done), next
    # request no earlier than E3. Recurrent owner cannot overlap requests.
    # Job start/end and memory/control work cover the final request boundary;
    # excluding exp and those positive costs leaves this conservative bound.
    scalar_min = 3 * basic
    wall_min = scalar_min + issue_min  # Host waits for each owner before next command.
    upper = Fraction(useful, MATRIX_MACS_PER_CYCLE * wall_min)
    return {
        "schema_version": 1,
        "evidence_kind": "architectural_source_derived_lower_bound",
        "scope": "Qwen3.5-0.8B layer0 full GDN, one cold or carried M1 launch",
        "audited_commit": AUDITED_COMMIT,
        "source_pins_verified": pins is not None,
        "source_hashes": pins,
        "physical_matrix_macs_per_cycle": MATRIX_MACS_PER_CYCLE,
        "mac_definition": "one useful multiply-accumulate is one MAC, not two FLOPs",
        "denominator": "4096 * launch_accept_to_terminal_result_wall_cycles; includes idle, Scalar, DDR and clock gating",
        "dense": dense,
        "useful_matrix_macs": useful,
        "issued_physical_lane_macs": sum(x["issued_physical_lane_macs"] for x in dense),
        "dense_issue_cycles_lower_bound": issue_min,
        "dense_geometry_utilization_upper_bound": useful / (4096 * issue_min),
        "scalar_recurrence": {"state_cells": cells, "multiply_requests": mul,
                              "add_requests": add, "basic_requests": basic,
                              "additional_exp_requests_excluded": 16,
                              "basic_request_minimum_ii": 3,
                              "cycles_lower_bound": scalar_min,
                              "measured_utilization": None,
                              "mac_equivalence": None},
        "lower_bound_cycles": wall_min,
        "upper_bound_utilization": float(upper),
        "upper_bound_utilization_exact": {"numerator": upper.numerator, "denominator": upper.denominator},
        "predicted_cycles": None,
        "predicted_utilization": None,
        "rtl_measured_cycles": None,
        "rtl_measured_utilization": None,
        "warning": "Optimistic bound only, not a calibrated cycle prediction or RTL utilization measurement.",
        "omitted_positive_costs": ["recurrence exp", "all other Scalar owners", "memory transfer and ACK waits",
                                   "Matrix feedback stalls", "command/descriptor and Fence overhead"],
        "calibration_required": ["source/RTL/binary/fixture identity", "launch accept and terminal result ticks",
                                 "per-command owner start/end and cycles", "Matrix wideSteps and acceptedSteps",
                                 "Dense useful/executed MACs and seven exclusive cycle buckets",
                                 "Scalar opcode request/result ticks", "AXI read/write-ACK beats and waits"],
        "restrictions": ["M1 only; do not multiply by 128 to predict M128", "no overlap between Host owners",
                         "one in-flight Scalar operation", "FP32 state and separate-rounding dependencies unchanged",
                         "Scalar operations are not Matrix MACs", "nominal frequency is not timing signoff"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--tokens", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(report(tokens=args.tokens, repo=args.repo), indent=2))


if __name__ == "__main__":
    main()
