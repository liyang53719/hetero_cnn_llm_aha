#!/usr/bin/env python3
"""Acquire 94,382,080 pinned bytes for Qwen2 L0 and embedding rows 0..255."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qwen2_layer0_payload import DEFAULT_OUTPUT, collect


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="Ignored payload directory; resumes verified complete segments")
    args = parser.parse_args()
    try:
        report = collect(args.root, args.output or args.root / DEFAULT_OUTPUT)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("PAYLOAD_ACQUISITION_REJECTED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(report, indent=2))
