"""Bounded real embedding rows and GDN layers 1/2 for the pinned 0.8B prefix.

Layer0 and layer3 use the previously independently pinned payload modules.
Only observed tensor/range hashes are verified, not the whole checkpoint LFS hash.
"""
from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from .model_geometry import load_json, require
from .pinned_block_payload import KEY, fetch_range
from .pinned_gdn_payload import F32_NAMES, ranges
from .weight_header_contract import BUNDLE_ROOT, PINS, decode_header, read_record, sha256, verify_bundle

TOTAL_BYTES = 2 * 43111008 + 256 * 1024 * 2
PIN_PATH = "config/upstream/qwen3_5_0p8b/prefix_payload_pin.json"
PIN_SHA256 = "1abdfec9e51e2fe77be685a9e2a5e3f3894162daa9b63e7c336b28ae399b104c"
FIXTURE_PATH = "config/upstream/qwen3_5_0p8b/prefix_token_fixture.json"
FIXTURE_SHA256 = "7aa77ba8b89001738c5b3a9a04b6f27a59118cbeebd01cffe82e42954b85f7b1"


def token_fixture(root: Path) -> dict:
    raw = (root / FIXTURE_PATH).read_bytes()
    require(sha256(raw) == FIXTURE_SHA256, "prefix token fixture drift")
    fixture = json.loads(raw)
    require(fixture["token_ids"] == [(73 * i + 19) % 256 for i in range(256)], "prefix token ID sequence drift")
    require(all(type(i) is int for i in fixture["token_ids"]), "token IDs must be integers")
    require(fixture["tokenizer_used"] is False and fixture["query_tokens"] == 128, "fixture scope drift")
    return fixture


def selection(root: Path) -> tuple[dict, list[dict]]:
    verify_bundle(root, KEY)
    bundle = load_json(root / BUNDLE_ROOT / KEY / "manifest.json")
    require(len(bundle["shards"]) == 1, "unexpected shard count")
    shard = bundle["shards"][0]
    raw = read_record(root, shard["header"])
    header = decode_header(raw, shard["file_bytes"])
    name = "model.language_model.embed_tokens.weight"
    tensor = header[name]
    require(tensor["dtype"] == "BF16" and tensor["shape"] == [248320, 1024], "embedding dtype/geometry drift")
    lo, hi = tensor["data_offsets"]
    require(hi - lo == 248320 * 1024 * 2, "embedding byte geometry drift")
    specs = [{"name": name, "local_name": "embed_tokens.rows_0_255", "dtype": "BF16",
              "shape": [256, 1024], "source_shape": tensor["shape"], "source_rows": [0, 256], "source_data_offsets": tensor["data_offsets"],
              "start": len(raw) + lo, "end": len(raw) + lo + 256 * 1024 * 2 - 1, "bytes": 256 * 1024 * 2}]
    for layer in (1, 2):
        prefix = f"model.language_model.layers.{layer}."
        selected = []
        for name, tensor in sorted(header.items()):
            if name.startswith(prefix):
                lo, hi = tensor["data_offsets"]
                local = name.removeprefix(prefix)
                require(tensor["dtype"] == ("F32" if local in F32_NAMES else "BF16"), "prefix GDN storage dtype drift")
                selected.append({"name": name, "local_name": f"layers.{layer}." + local, "dtype": tensor["dtype"],
                    "shape": tensor["shape"], "start": len(raw) + lo, "end": len(raw) + hi - 1, "bytes": hi - lo})
        require(len(selected) == 14 and sum(s["bytes"] for s in selected) == 43111008, "unexpected prefix GDN inventory")
        specs.extend(selected)
    require(len(specs) == 29 and sum(s["bytes"] for s in specs) == TOTAL_BYTES, "unexpected prefix payload inventory")
    return shard, specs


def payload_pin(root: Path, specs: list[dict]) -> dict:
    raw = (root / PIN_PATH).read_bytes()
    require(sha256(raw) == PIN_SHA256, "prefix payload digest pin drift")
    pin = json.loads(raw)
    require((pin["model_id"], pin["revision"]) == PINS[KEY], "prefix pin identity drift")
    require(len(pin["tensors"]) == len(specs), "prefix pin inventory drift")
    for spec, observed in zip(specs, pin["tensors"], strict=True):
        require(all(observed[k] == v and type(observed[k]) is type(v) for k, v in spec.items()), "prefix pin geometry drift")
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
        require(sha256(raw) == expected_hashes[spec["local_name"]], "acquired prefix payload differs from observed pin")
        filename = spec["local_name"] + ".bin"
        (output / filename).write_bytes(raw)
        records.append({**spec, "file": filename, "sha256": sha256(raw), "http_ranges": receipts})
    report = {"schema_version": 1, "model_id": PINS[KEY][0], "revision": PINS[KEY][1],
              "header_sha256": shard["header"]["sha256"], "status": "ACQUIRED_PINNED_PREFIX_ADDITIONAL_PAYLOAD_ONLY",
              "payload_bytes": TOTAL_BYTES, "tensors": records, "full_checkpoint_sha256_verified": False,
              "advertised_full_checkpoint_sha256_unverified": shard["advertised_lfs_sha256_unverified"],
              "official_forward_executed": False, "rtl_executed": False, "U00_2_complete": False}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def load_payload(root: Path, directory: Path) -> tuple[dict, dict]:
    shard, specs = selection(root)
    expected_hashes = payload_pin(root, specs)
    manifest = load_json(directory / "manifest.json")
    require((manifest["model_id"], manifest["revision"]) == PINS[KEY], "prefix checkpoint identity drift")
    require(manifest["header_sha256"] == shard["header"]["sha256"], "prefix header drift")
    require(type(manifest["payload_bytes"]) is int and manifest["payload_bytes"] == TOTAL_BYTES, "prefix byte total drift")
    require(len(manifest["tensors"]) == len(specs), "prefix inventory size drift")
    values = {}
    for expected, record in zip(specs, manifest["tensors"], strict=True):
        require(all(record[k] == v and type(record[k]) is type(v) for k, v in expected.items()), "prefix geometry/order drift")
        filename = expected["local_name"] + ".bin"
        require(record["file"] == filename, "prefix filename drift")
        path = (directory / filename).resolve()
        require(path.is_relative_to(directory.resolve()), "prefix path escape")
        raw = path.read_bytes()
        require(record["sha256"] == expected_hashes[expected["local_name"]], "prefix digest differs from observed pin")
        require(len(raw) == expected["bytes"] and sha256(raw) == record["sha256"], "prefix bytes/hash mismatch")
        expected_ranges = list(ranges(expected))
        require(len(record["http_ranges"]) == len(expected_ranges), "prefix HTTP range count drift")
        for (start, end), http in zip(expected_ranges, record["http_ranges"], strict=True):
            chunk = raw[start - expected["start"]:end - expected["start"] + 1]
            require(http["requested_url"] == shard["url"] and http["status"] == 206 and
                    http["request_range"] == f"bytes={start}-{end}" and
                    http["content_range"] == f'bytes {start}-{end}/{shard["file_bytes"]}' and
                    http["bytes"] == len(chunk) and http["sha256"] == sha256(chunk), "prefix HTTP receipt drift")
        values[expected["local_name"]] = raw
    return manifest, values
