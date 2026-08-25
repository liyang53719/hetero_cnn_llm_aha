#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from heteronpu.segment_compiler import load_and_compile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--output", required=True)
    parser.add_argument("--binary", default="")
    args = parser.parse_args()
    segment = load_and_compile(args.input)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(segment.to_dict(), indent=2, sort_keys=True) + "\n")
    if args.binary:
        binary = Path(args.binary)
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"".join(item.command.to_bytes() for item in segment.commands))
    print(json.dumps({"status": "PASS", "segment": segment.name, "commands": len(segment.commands)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
