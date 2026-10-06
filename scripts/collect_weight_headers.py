#!/usr/bin/env python3
"""Re-fetch the reviewed pinned headers, without downloading tensor payloads.

Requires HTTPS/network. Offline validation uses validate_workload_evidence.py.
Server-advertised whole-file SHA256 values are never labelled locally verified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteronpu.model_geometry import load_json, require
from heteronpu.weight_header_contract import BUNDLE_ROOT, BUNDLE_SHA256, PINS, MAX_HEADER_BYTES, decode_header, sha256


def fetch_range(url: str, end: int, total: int, *, opener=urllib.request.urlopen) -> tuple[bytes, dict]:
    require(type(end) is int and 7 <= end < MAX_HEADER_BYTES + 8, "range exceeds header cap")
    require(type(total) is int and total > end, "invalid file total")
    request = urllib.request.Request(url, headers={"Range": f"bytes=0-{end}", "Accept-Encoding": "identity",
                                                   "User-Agent": "hetero-pinned-header-evidence/1.0"})
    with opener(request, timeout=90) as response:
        # Verify status and exact range BEFORE any read, even when the server
        # ignores Range and offers the complete 5GB shard.
        expected = f"bytes 0-{end}/{total}"
        require(response.status == 206 and response.headers.get("Content-Range") == expected,
                "server ignored/mismatched requested range; refused body")
        require(response.headers.get("Content-Encoding", "identity") == "identity", "encoded range refused")
        require(response.headers.get("Content-Length") == str(end + 1), "unexpected range Content-Length")
        raw = response.read(end + 2)
        require(len(raw) == end + 1, "range response body length mismatch")
        return raw, {"acquired_at": datetime.now(timezone.utc).isoformat(), "requested_url": url,
                     "request_range": f"bytes=0-{end}", "status": response.status, "content_range": expected,
                     "content_length": len(raw), "file_total_bytes": total, "body_sha256": sha256(raw)}


def collect(root: Path, output: Path, keys: list[str]) -> dict:
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())),
            "output must be a fresh or empty directory; stale evidence must not survive a failed retry")
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for key in keys:
        path = root / BUNDLE_ROOT / key / "manifest.json"
        require(sha256(path.read_bytes()) == BUNDLE_SHA256[key], "unreviewed acquisition manifest")
        bundle = load_json(path)
        directory = output / key
        directory.mkdir(exist_ok=True)
        for shard in bundle["shards"]:
            url, total = shard["url"], shard["file_bytes"]
            prefix, _ = fetch_range(url, 7, total)
            size = int.from_bytes(prefix, "little")
            require(1 < size <= MAX_HEADER_BYTES and size + 8 == shard["header"]["bytes"], "header length changed")
            raw, receipt = fetch_range(url, size + 7, total)
            require(raw[:8] == prefix and sha256(raw) == shard["header"]["sha256"], "pinned header bytes changed")
            tensors = decode_header(raw, total)
            path = directory / (shard["file"] + ".header.bin")
            path.write_bytes(raw)
            path.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
            reports.append({"model_key": key, "shard": shard["file"], "header_sha256": sha256(raw),
                            "header_bytes": len(raw), "tensor_count": len(tensors)})
    result = {"status": "PASS_PINNED_HEADERS_REACQUIRED_ONLY", "headers": reports,
              "tensor_payload_bytes_downloaded": 0, "tensor_content_verified": False,
              "official_forward_executed": False, "rtl_executed": False}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", choices=tuple(PINS), action="append")
    args = parser.parse_args()
    try:
        result = collect(args.root, args.output, args.model or list(PINS))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("HEADER_ACQUISITION_REJECTED: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
