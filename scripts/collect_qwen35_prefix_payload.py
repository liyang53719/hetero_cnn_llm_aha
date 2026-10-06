#!/usr/bin/env python3
"""Download only 86,746,304 additional bytes for embedding rows and layers 1/2."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteronpu.pinned_prefix_payload import collect

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
