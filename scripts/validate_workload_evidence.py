#!/usr/bin/env python3
"""Offline pinned-header/preparation audit; --require-complete fails until U00.2 closes."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteronpu.workload_evidence import validate_preparation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        report = validate_preparation(args.root, require_complete=args.require_complete)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("WORKLOAD_EVIDENCE_REJECTED: " + str(exc), file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
