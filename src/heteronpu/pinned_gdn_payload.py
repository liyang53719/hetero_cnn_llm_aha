"""Bounded, immutable mixed-dtype checkpoint slice for 0.8B layer 0 GDN.

Whole-checkpoint LFS integrity and full workload admission remain unverified.
"""
from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from .model_geometry import load_json, require
from .pinned_block_payload import KEY, MAX_RANGE_BYTES, fetch_range
from .weight_header_contract import BUNDLE_ROOT, PINS, decode_header, read_record, sha256, verify_bundle

PREFIX = "model.language_model.layers.0."
TOTAL_BYTES = 43111008
PIN_PATH = "config/upstream/qwen3_5_0p8b/layer0_payload_pin.json"
PIN_SHA256 = "80352cc5df45472a8867a4e1d346f60dc888e6f89ee191ec35457b484770d9c4"
F32_NAMES = {"linear_attn.A_log", "linear_attn.norm.weight"}


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
            local = name.removeprefix(PREFIX)
            require(tensor["dtype"] == ("F32" if local in F32_NAMES else "BF16"), "GDN storage dtype drift")
            specs.append({"name": name, "local_name": local, "dtype": tensor["dtype"],
                          "shape": tensor["shape"], "start": len(raw) + lo,
                          "end": len(raw) + hi - 1, "bytes": hi - lo})
    require(len(specs) == 14 and sum(s["bytes"] for s in specs) == TOTAL_BYTES,
            "unexpected GDN payload inventory")
    return shard, specs


def ranges(spec: dict):
    require(type(spec["start"]) is int and type(spec["end"]) is int and 0 <= spec["start"] <= spec["end"],
            "invalid tensor range")
    for start in range(spec["start"], spec["end"] + 1, MAX_RANGE_BYTES):
        yield start, min(start + MAX_RANGE_BYTES - 1, spec["end"])


def payload_pin(root: Path, specs: list[dict]) -> dict:
    raw = (root / PIN_PATH).read_bytes()
    require(sha256(raw) == PIN_SHA256, "GDN payload digest pin drift")
    pin = load_json(root / PIN_PATH)
    require((pin["model_id"], pin["revision"]) == PINS[KEY] and type(pin["layer_id"]) is int and pin["layer_id"] == 0,
            "GDN payload digest pin identity drift")
    require(len(pin["tensors"]) == len(specs), "GDN payload digest pin inventory drift")
    for spec, observed in zip(specs, pin["tensors"], strict=True):
        require(all(observed[k] == v and type(observed[k]) is type(v) for k, v in spec.items()), "GDN payload digest pin geometry drift")
    return {t["local_name"]: t["sha256"] for t in pin["tensors"]}


def collect(root: Path, output: Path, *, opener=urllib.request.urlopen) -> dict:
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be fresh or empty")
    shard, specs = selection(root)
    expected_hashes = payload_pin(root, specs)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for spec in specs:
        chunks, receipts = [], []
        for start, end in ranges(spec):
            raw, receipt = fetch_range(shard["url"], start, end, shard["file_bytes"], opener=opener)
            chunks.append(raw)
            receipts.append(receipt)
        raw = b"".join(chunks)
        require(sha256(raw) == expected_hashes[spec["local_name"]], "acquired GDN payload digest differs from observed pin")
        filename = spec["local_name"] + ".bin"
        (output / filename).write_bytes(raw)
        records.append({**spec, "file": filename, "sha256": sha256(raw), "http_ranges": receipts})
    report = {"schema_version": 1, "model_id": PINS[KEY][0], "revision": PINS[KEY][1],
              "layer_id": 0, "header_sha256": shard["header"]["sha256"],
              "status": "ACQUIRED_PINNED_LAYER_PAYLOAD_ONLY", "payload_bytes": TOTAL_BYTES,
              "tensors": records, "full_checkpoint_sha256_verified": False,
              "advertised_full_checkpoint_sha256_unverified": shard["advertised_lfs_sha256_unverified"],
              "official_forward_executed": False, "rtl_executed": False, "U00_2_complete": False}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def load_payload(root: Path, directory: Path) -> tuple[dict, dict]:
    shard, specs = selection(root)
    expected_hashes = payload_pin(root, specs)
    manifest = load_json(directory / "manifest.json")
    require((manifest["model_id"], manifest["revision"]) == PINS[KEY], "GDN checkpoint identity drift")
    require(type(manifest["layer_id"]) is int and manifest["layer_id"] == 0, "GDN payload layer drift")
    require(manifest["header_sha256"] == shard["header"]["sha256"], "GDN payload header drift")
    require(type(manifest["payload_bytes"]) is int and manifest["payload_bytes"] == TOTAL_BYTES, "GDN byte total drift")
    require(len(manifest["tensors"]) == len(specs), "GDN payload inventory size drift")
    values = {}
    for expected, record in zip(specs, manifest["tensors"], strict=True):
        require(all(record[k] == v and type(record[k]) is type(v) for k, v in expected.items()), "GDN geometry/order drift")
        filename = expected["local_name"] + ".bin"
        require(record["file"] == filename, "GDN payload filename drift")
        path = (directory / filename).resolve()
        require(path.is_relative_to(directory.resolve()), "GDN payload path escape")
        raw = path.read_bytes()
        require(record["sha256"] == expected_hashes[expected["local_name"]], "GDN payload digest differs from observed pin")
        require(len(raw) == expected["bytes"] and sha256(raw) == record["sha256"], "GDN bytes/hash mismatch")
        expected_ranges = list(ranges(expected))
        require(len(record["http_ranges"]) == len(expected_ranges), "GDN HTTP range count drift")
        for (start, end), http in zip(expected_ranges, record["http_ranges"], strict=True):
            chunk = raw[start - expected["start"]:end - expected["start"] + 1]
            require(http["requested_url"] == shard["url"] and http["status"] == 206 and
                    http["request_range"] == f"bytes={start}-{end}" and
                    http["content_range"] == f'bytes {start}-{end}/{shard["file_bytes"]}' and
                    http["bytes"] == len(chunk) and http["sha256"] == sha256(chunk), "GDN HTTP receipt drift")
        values[expected["local_name"]] = raw
    return manifest, values
