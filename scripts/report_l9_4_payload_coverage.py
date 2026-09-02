#!/usr/bin/env python3
"""Generate source-derived coverage for the Qwen2 21-command payload canary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heteronpu.l9_payload_coverage import classify_layer0_payload_coverage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports/execution/L9_4_LAYER0_PAYLOAD_COVERAGE.json",
    )
    args = parser.parse_args()
    root = args.root
    kv_adapter = root / "rtl/integration/qwen2_kv_command_endpoint.sv"
    kv_primitive = root / "rtl/integration/kv_tensor_stream_endpoint.sv"
    kv_source = (kv_adapter if kv_adapter.exists() else kv_primitive).read_text(encoding="utf-8")
    report = classify_layer0_payload_coverage(
        sfu_endpoint_source=(root / "rtl/integration/qwen2_sfu_command_endpoint.sv").read_text(encoding="utf-8"),
        matrix_endpoint_source=(root / "rtl/integration/qwen2_matrix_command_endpoint.sv").read_text(encoding="utf-8"),
        kv_endpoint_source=kv_source,
    )
    report["source_paths"] = {
        "sfu": "rtl/integration/qwen2_sfu_command_endpoint.sv",
        "matrix": "rtl/integration/qwen2_matrix_command_endpoint.sv",
        "kv": str((kv_adapter if kv_adapter.exists() else kv_primitive).relative_to(root)),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
