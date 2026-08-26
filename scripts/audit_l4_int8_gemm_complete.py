#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

TRACE = re.compile(
    r"L4_INT8_GEMM_L3_TRACE_PASS cycles=(\d+) semantic_dma_bytes=(\d+) "
    r"physical_dma_bytes=(\d+) descriptor_bytes=(\d+) reads=(\d+) writes=(\d+) "
    r"conflicts=(\d+) rstall=(\d+) wstall=(\d+) promotions=(\d+)"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--trace-log", type=Path, required=True)
    parser.add_argument("--descriptor-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text())
    match = TRACE.search(args.trace_log.read_text(errors="replace"))
    if match is None:
        raise SystemExit("L4_INT8_GEMM_COMPLETE_FAIL trace marker")
    values = list(map(int, match.groups()))
    (cycles, semantic, physical, descriptor, reads, writes,
     conflicts, rstall, wstall, promotions) = values
    if (semantic, physical, descriptor, reads, writes) != (2195, 2368, 256, 36, 5):
        raise SystemExit("L4_INT8_GEMM_COMPLETE_FAIL trace accounting")
    if cycles <= 0 or conflicts <= 0 or promotions <= 0:
        raise SystemExit("L4_INT8_GEMM_COMPLETE_FAIL trace coverage")
    if "GEMMINI_DESCRIPTOR_V2_PIPELINE_PASS" not in args.descriptor_log.read_text(errors="replace"):
        raise SystemExit("L4_INT8_GEMM_COMPLETE_FAIL descriptor RTL")
    if payload["status"] != "PASS_PAYLOAD_RTL_PENDING_L3_TRACE":
        raise SystemExit("L4_INT8_GEMM_COMPLETE_FAIL payload status")
    result = dict(payload)
    result.update({
        "status": "PASS",
        "canonical_l3_trace_cycles": cycles,
        "physical_dma_bytes": physical,
        "descriptor_bytes": descriptor,
        "canonical_l3_reads": reads,
        "canonical_l3_writes": writes,
        "bank_conflicts": conflicts,
        "read_stalls": rstall,
        "write_stalls": wstall,
        "descriptor_promotions": promotions,
        "bank_conflicts_status": "RTL_MEASURED",
        "measurement_scope": {
            **payload["measurement_scope"],
            "canonical_l3_trace_cycles": "host Matrix dispatch through concurrent L2 trace and accepted completion",
            "bank_conflicts": "cycle-accurate physical Shared-L2 model behind canonical production arbiter",
            "physical_dma_bytes": "512-bit physical beats for weight, activation/bias and output traffic",
        },
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"L4_INT8_GEMM_COMPLETE_PASS payload_cycles={payload['rtl_payload_cycles']} "
          f"l3_cycles={cycles} conflicts={conflicts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
