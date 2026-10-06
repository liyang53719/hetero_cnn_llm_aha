"""Bounded payload acquisition for the pinned 0.8B attention layer 3.

This is a real checkpoint slice, not a whole-file LFS hash verification or a
workload-admission gate. The existing three-model OPEN gate is not modified.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.request

from .model_geometry import load_json, require
from .weight_header_contract import BUNDLE_ROOT, PINS, decode_header, read_record, sha256, verify_bundle

KEY = "qwen3_5_0p8b"
PREFIX = "model.language_model.layers.3."
MAX_RANGE_BYTES = 8 * 1024 * 1024
TOTAL_BYTES = 36705280
PIN_PATH = "config/upstream/qwen3_5_0p8b/layer3_payload_pin.json"
PIN_SHA256 = "ab9735a92f3b3377737288621019bccd855a5696bd4d02b2d8257cbf24a5b0ac"


def payload_pin(root: Path, specs: list[dict]) -> dict:
    raw = (root / PIN_PATH).read_bytes()
    require(sha256(raw) == PIN_SHA256, "payload digest pin drift")
    pin = load_json(root / PIN_PATH)
    require((pin["model_id"], pin["revision"]) == PINS[KEY] and pin["layer_id"] == 3,
            "payload digest pin identity drift")
    require(len(pin["tensors"]) == len(specs), "payload digest pin inventory drift")
    for spec, observed in zip(specs, pin["tensors"], strict=True):
        require(all(observed[k] == v for k, v in spec.items()), "payload digest pin geometry drift")
    return {t["local_name"]: t["sha256"] for t in pin["tensors"]}


def selection(root: Path) -> tuple[dict, list[dict]]:
    verify_bundle(root, KEY)
    bundle = load_json(root / BUNDLE_ROOT / KEY / "manifest.json")
    require(len(bundle["shards"]) == 1, "unexpected shard count")
    shard = bundle["shards"][0]
    raw = read_record(root, shard["header"])
    header = decode_header(raw, shard["file_bytes"])
    specs = []
    for name, tensor in sorted(header.items()):
        if name.startswith(PREFIX):
            lo, hi = tensor["data_offsets"]
            specs.append({"name": name, "local_name": name.removeprefix(PREFIX),
                          "dtype": tensor["dtype"], "shape": tensor["shape"],
                          "start": len(raw) + lo, "end": len(raw) + hi - 1,
                          "bytes": hi - lo})
    require(len(specs) == 11 and sum(s["bytes"] for s in specs) == TOTAL_BYTES,
            "unexpected layer payload inventory")
    require(all(s["dtype"] == "BF16" and 0 < s["bytes"] <= MAX_RANGE_BYTES for s in specs),
            "unsupported layer storage dtype or unbounded range")
    return shard, specs


def fetch_range(url: str, start: int, end: int, total: int, *, opener=urllib.request.urlopen):
    require(all(type(x) is int for x in (start, end, total)), "range fields must be integers")
    require(0 <= start <= end < total and end - start + 1 <= MAX_RANGE_BYTES, "unbounded payload range")
    size = end - start + 1
    request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}",
        "Accept-Encoding": "identity", "User-Agent": "hetero-pinned-payload/1.0"})
    with opener(request, timeout=90) as response:
        expected = f"bytes {start}-{end}/{total}"
        require(response.status == 206 and response.headers.get("Content-Range") == expected,
                "server ignored/mismatched range; body refused")
        require(response.headers.get("Content-Length") == str(size), "range Content-Length mismatch")
        require(response.headers.get("Content-Encoding", "identity") == "identity", "encoded range refused")
        raw = response.read(size + 1)
        require(len(raw) == size, "payload body length mismatch")
    return raw, {"acquired_at": datetime.now(timezone.utc).isoformat(), "requested_url": url,
                 "request_range": f"bytes={start}-{end}", "status": 206,
                 "content_range": expected, "bytes": size, "sha256": sha256(raw)}


def collect(root: Path, output: Path, *, opener=urllib.request.urlopen) -> dict:
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())),
            "output must be fresh or empty; stale PASS must not survive failure")
    shard, specs = selection(root)
    expected_hashes = payload_pin(root, specs)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for spec in specs:
        raw, receipt = fetch_range(shard["url"], spec["start"], spec["end"], shard["file_bytes"], opener=opener)
        require(sha256(raw) == expected_hashes[spec["local_name"]], "acquired payload digest differs from observed pin")
        filename = spec["local_name"] + ".bin"
        (output / filename).write_bytes(raw)
        records.append({**spec, "file": filename, "sha256": sha256(raw), "http": receipt})
    report = {"schema_version": 1, "model_id": PINS[KEY][0], "revision": PINS[KEY][1],
              "layer_id": 3, "header_sha256": shard["header"]["sha256"],
              "status": "ACQUIRED_PINNED_LAYER_PAYLOAD_ONLY", "payload_bytes": TOTAL_BYTES,
              "tensors": records, "full_checkpoint_sha256_verified": False,
              "advertised_full_checkpoint_sha256_unverified": shard["advertised_lfs_sha256_unverified"],
              "official_forward_executed": False, "rtl_executed": False, "U00_2_complete": False}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def load_payload(root: Path, directory: Path) -> tuple[dict, dict]:
    """Validate local bytes against pinned geometry and the acquisition receipt.

    First acquisition hashes record observed bytes, not independent authenticity.
    The later checked-in numerical report binds those observed per-tensor hashes.
    """
    shard, specs = selection(root)
    expected_hashes = payload_pin(root, specs)
    manifest = load_json(directory / "manifest.json")
    require((manifest["model_id"], manifest["revision"]) == PINS[KEY], "payload checkpoint identity drift")
    require(type(manifest["layer_id"]) is int and manifest["layer_id"] == 3, "payload layer drift")
    require(manifest["header_sha256"] == shard["header"]["sha256"], "payload header drift")
    require(type(manifest["payload_bytes"]) is int and manifest["payload_bytes"] == TOTAL_BYTES,
            "payload byte total drift")
    require(len(manifest["tensors"]) == len(specs), "payload inventory size drift")
    values = {}
    for expected, record in zip(specs, manifest["tensors"], strict=True):
        require(all(record[k] == v and type(record[k]) is type(v) for k, v in expected.items()), "payload geometry/order drift")
        filename = expected["local_name"] + ".bin"
        require(record["file"] == filename, "payload filename drift")
        path = (directory / filename).resolve()
        require(path.is_relative_to(directory.resolve()), "payload path escape")
        raw = path.read_bytes()
        require(record["sha256"] == expected_hashes[expected["local_name"]], "payload digest differs from observed pin")
        require(len(raw) == expected["bytes"] and sha256(raw) == record["sha256"], "payload bytes/hash mismatch")
        http = record["http"]
        require(http["requested_url"] == shard["url"] and http["status"] == 206 and
                http["request_range"] == f'bytes={expected["start"]}-{expected["end"]}' and
                http["content_range"] == f'bytes {expected["start"]}-{expected["end"]}/{shard["file_bytes"]}' and
                http["bytes"] == len(raw) and http["sha256"] == sha256(raw), "payload HTTP receipt drift")
        values[expected["local_name"]] = raw
    return manifest, values
