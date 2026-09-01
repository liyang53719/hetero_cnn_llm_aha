#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packed-records", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.packed_records.read_text().splitlines()]
    records.sort(key=lambda item: item["index"])
    first, last = records[0]["index"], records[-1]["index"]
    if first != 4096 or last - first + 1 != len(records) or len(records) != 6188:
        raise SystemExit(f"descriptor records are not compact: first={first} last={last} n={len(records)}")
    if first % 4 or (last + 1) % 4:
        raise SystemExit("descriptor image does not cover complete 512-bit beats")
    args.out.mkdir(parents=True, exist_ok=True)
    words = [int(item["word"], 16) for item in records]
    beats = [sum(words[offset + slot] << (128 * slot) for slot in range(4))
             for offset in range(0, len(words), 4)]
    (args.out / "records.memh").write_text("".join(f"{word:032x}\n" for word in words))
    (args.out / "beats.memh").write_text("".join(f"{beat:0128x}\n" for beat in beats))
    metadata = {"record_base": first, "record_count": len(words),
                "beat_base": first // 4, "beat_count": len(beats),
                "last_record": last}
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
