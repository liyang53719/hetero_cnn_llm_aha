#!/usr/bin/env python3
"""Download only 36,705,280 bytes for the pinned 0.8B attention layer 3."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteronpu.pinned_block_payload import collect

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = collect(args.root, args.output)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("PAYLOAD_ACQUISITION_REJECTED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(report, indent=2))
