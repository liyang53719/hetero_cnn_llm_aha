#!/usr/bin/env python3
"""Generate committed command-envelope reports from frozen example segments."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from heteronpu.segment_compiler import load_and_compile


ROOT = Path(__file__).resolve().parents[1]
MAPPINGS = (
    ("examples/cnn_segment.yaml", "reports/cnn_segment_commands.json"),
    ("examples/llm_prefill_segment.yaml", "reports/llm_prefill_segment_commands.json"),
    ("examples/llm_decode_segment.yaml", "reports/llm_decode_segment_commands.json"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for source, destination in MAPPINGS:
        output = ROOT / destination
        rendered = json.dumps(load_and_compile(ROOT / source).to_dict(), indent=2,
                              sort_keys=True) + "\n"
        if args.check:
            if not output.exists() or output.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"segment command report is stale: {destination}")
        else:
            output.write_text(rendered, encoding="utf-8")
    marker = "CHECK_PASS" if args.check else "GENERATED"
    print(f"SEGMENT_COMMAND_REPORTS_{marker} count={len(MAPPINGS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
