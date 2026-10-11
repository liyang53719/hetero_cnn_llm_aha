"""Bounded, resumable Qwen2 layer-0 and embedding-row checkpoint payload.

Observed tensor and segment digests bind the selected bytes; they do not verify
the advertised whole-checkpoint LFS digest or establish model/RTL correctness.
"""
from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from heteronpu.model_geometry import load_json, require
from heteronpu.pinned_block_payload import MAX_RANGE_BYTES, fetch_range
from heteronpu.pinned_gdn_payload import ranges
from heteronpu.weight_header_contract import BUNDLE_ROOT, PINS, decode_header, read_record, sha256, verify_bundle

KEY = "qwen2_1p5b"
PREFIX = "model.layers.0."
LAYER_BYTES = 93595648
EMBEDDING_BYTES = 786432
TOTAL_BYTES = LAYER_BYTES + EMBEDDING_BYTES
PIN_PATH = "config/payload_pins/qwen2_layer0.json"
PIN_SHA256 = "190e1fca0edff7c783c6981a6759f57162e63c4754ffc0f3481df64de9d06f88"
DEFAULT_OUTPUT = "work/qwen2_layer0_payload_20261011"
STATUS = "ACQUIRED_PINNED_QWEN2_LAYER0_AND_EMBEDDING_ROWS_ONLY"


def _same(actual, expected) -> bool:
    """Equality that never accepts JSON booleans as integer dimensions/offsets."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return all(k in actual and _same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def selection(root: Path) -> tuple[dict, list[dict]]:
    verify_bundle(root, KEY)
    bundle = load_json(root / BUNDLE_ROOT / KEY / "manifest.json")
    require(len(bundle["shards"]) == 1, "unexpected shard count")
    shard = bundle["shards"][0]
    raw = read_record(root, shard["header"])
    require(len(raw) == 38536, "Qwen2 header length drift")
    header = decode_header(raw, shard["file_bytes"])
    name = "model.embed_tokens.weight"
    tensor = header[name]
    require(tensor["dtype"] == "BF16" and tensor["shape"] == [151936, 1536],
            "embedding dtype/geometry drift")
    lo, hi = tensor["data_offsets"]
    specs = [{"name": name, "local_name": "embed_tokens.rows_0_255", "dtype": "BF16",
              "shape": [256, 1536], "source_shape": tensor["shape"], "source_rows": [0, 256],
              "source_data_offsets": [lo, hi], "start": len(raw) + lo,
              "end": len(raw) + lo + EMBEDDING_BYTES - 1, "bytes": EMBEDDING_BYTES}]
    for name, tensor in sorted(header.items()):
        if name.startswith(PREFIX):
            lo, hi = tensor["data_offsets"]
            specs.append({"name": name, "local_name": name.removeprefix(PREFIX),
                          "dtype": tensor["dtype"], "shape": tensor["shape"],
                          "source_shape": tensor["shape"], "source_data_offsets": [lo, hi],
                          "start": len(raw) + lo, "end": len(raw) + hi - 1, "bytes": hi - lo})
    require(len(specs) == 13 and sum(s["bytes"] for s in specs[1:]) == LAYER_BYTES,
            "unexpected Qwen2 layer inventory")
    require(specs[1]["start"] == 466785928 and specs[-1]["end"] + 1 == 560381576,
            "Qwen2 layer span drift")
    require(all(s["dtype"] == "BF16" for s in specs), "Qwen2 storage dtype drift")
    return shard, specs


def _identity(shard: dict) -> dict:
    return {"schema_version": 1, "model_id": PINS[KEY][0], "revision": PINS[KEY][1],
            "layer_id": 0, "header_sha256": shard["header"]["sha256"],
            "payload_bytes": TOTAL_BYTES, "layer_bytes": LAYER_BYTES, "embedding_bytes": EMBEDDING_BYTES}


def _digest(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def payload_pin(root: Path, specs: list[dict], shard: dict | None = None) -> dict:
    raw = (root / PIN_PATH).read_bytes()
    require(sha256(raw) == PIN_SHA256, "Qwen2 payload digest pin drift")
    pin = json.loads(raw)
    if shard is None:
        shard, _ = selection(root)
    require(_same(pin, _identity(shard)), "Qwen2 payload pin identity drift")
    require(len(pin["tensors"]) == len(specs), "Qwen2 payload pin inventory drift")
    for spec, observed in zip(specs, pin["tensors"], strict=True):
        require(_same(observed, spec), "Qwen2 payload pin geometry drift")
        require(_digest(observed["sha256"]), "invalid tensor digest")
        spans = list(ranges(spec))
        require(len(observed["segments"]) == len(spans), "Qwen2 payload pin segment count drift")
        for segment, (start, end) in zip(observed["segments"], spans, strict=True):
            require(_same(segment, {"start": start, "end": end, "bytes": end - start + 1})
                    and _digest(segment["sha256"]), "Qwen2 payload pin segment drift")
    return {t["local_name"]: t for t in pin["tensors"]}


def validate_http(shard: dict, start: int, end: int, raw: bytes, receipt: dict, digest: str) -> None:
    expected = {"requested_url": shard["url"], "request_range": f"bytes={start}-{end}",
                "status": 206, "content_range": f'bytes {start}-{end}/{shard["file_bytes"]}',
                "bytes": end - start + 1, "sha256": digest}
    require(_same(receipt, expected), "Qwen2 payload HTTP receipt drift")
    require(len(raw) == end - start + 1 and sha256(raw) == digest,
            "Qwen2 segment bytes/hash mismatch")


def _path(directory: Path, filename: str) -> Path:
    path = directory / filename
    require(not path.is_symlink() and path.resolve().is_relative_to(directory.resolve()), "payload path escape")
    return path


def _segment_name(spec: dict, index: int) -> str:
    return f'{spec["local_name"]}.{index:03d}'


def _write(path: Path, raw: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    require(not temporary.exists() and not temporary.is_symlink(), "incomplete payload write; inspect before retry")
    temporary.write_bytes(raw)
    temporary.replace(path)


def _json(raw: dict) -> bytes:
    return (json.dumps(raw, indent=2) + "\n").encode()


def _check_cache(output: Path, specs: list[dict], pins: dict, shard: dict) -> None:
    """Validate every existing cache entry before issuing any network request."""
    allowed = {"segments", "manifest.json"} | {s["local_name"] + ".bin" for s in specs}
    require(all(p.name in allowed and not p.is_symlink() for p in output.iterdir()),
            "unknown or incomplete payload cache entry")
    segment_dir = _path(output, "segments")
    expected_names = set()
    for spec in specs:
        pin = pins[spec["local_name"]]
        filename = spec["local_name"] + ".bin"
        path = _path(output, filename)
        if path.exists():
            raw = path.read_bytes()
            require(len(raw) == spec["bytes"] and sha256(raw) == pin["sha256"], "cached tensor bytes/hash mismatch")
        for index, segment in enumerate(pin["segments"]):
            base = _segment_name(spec, index)
            expected_names.update((base + ".bin", base + ".json"))
            data = _path(segment_dir, base + ".bin")
            receipt = _path(segment_dir, base + ".json")
            require(data.exists() == receipt.exists(), "incomplete cached segment/receipt pair")
            if data.exists():
                validate_http(shard, segment["start"], segment["end"], data.read_bytes(),
                              load_json(receipt), segment["sha256"])
    require(all(p.name in expected_names and not p.is_symlink() for p in segment_dir.iterdir()),
            "unknown or incomplete segment cache entry")


def collect(root: Path, output: Path, *, opener=urllib.request.urlopen) -> dict:
    """Fetch only missing pinned segments; malformed or corrupt caches fail closed."""
    shard, specs = selection(root)
    pins = payload_pin(root, specs, shard)
    require(not output.is_symlink(), "payload output symlink refused")
    output.mkdir(parents=True, exist_ok=True)
    segment_dir = _path(output, "segments")
    segment_dir.mkdir(exist_ok=True)
    _check_cache(output, specs, pins, shard)
    if (output / "manifest.json").exists():
        return load_payload(root, output)[0]
    records = []
    for spec in specs:
        pin = pins[spec["local_name"]]
        chunks, receipts = [], []
        for index, segment in enumerate(pin["segments"]):
            base = _segment_name(spec, index)
            data = _path(segment_dir, base + ".bin")
            receipt_path = _path(segment_dir, base + ".json")
            start, end = segment["start"], segment["end"]
            if data.exists():
                raw, receipt = data.read_bytes(), load_json(receipt_path)
            else:
                raw, receipt = fetch_range(shard["url"], start, end, shard["file_bytes"], opener=opener)
                validate_http(shard, start, end, raw, receipt, segment["sha256"])
                _write(data, raw)
                _write(receipt_path, _json(receipt))
            validate_http(shard, start, end, raw, receipt, segment["sha256"])
            chunks.append(raw)
            receipts.append(receipt)
        raw = b"".join(chunks)
        require(len(raw) == spec["bytes"] and sha256(raw) == pin["sha256"],
                "acquired Qwen2 tensor differs from observed pin")
        filename = spec["local_name"] + ".bin"
        _write(_path(output, filename), raw)
        records.append({**spec, "file": filename, "sha256": pin["sha256"], "http_ranges": receipts})
    report = {**_identity(shard), "status": STATUS, "tensors": records,
              "full_checkpoint_sha256_verified": False,
              "advertised_full_checkpoint_sha256_unverified": shard["advertised_lfs_sha256_unverified"],
              "official_forward_executed": False, "rtl_executed": False}
    _write(output / "manifest.json", _json(report))
    return report


def load_payload(root: Path, directory: Path) -> tuple[dict, dict[str, bytes]]:
    """Return manifest and raw BF16 by layer-relative name, plus selected embeddings."""
    shard, specs = selection(root)
    pins = payload_pin(root, specs, shard)
    manifest = load_json(_path(directory, "manifest.json"))
    require(_same(manifest, {**_identity(shard), "status": STATUS,
                            "full_checkpoint_sha256_verified": False,
                            "advertised_full_checkpoint_sha256_unverified": shard["advertised_lfs_sha256_unverified"],
                            "official_forward_executed": False, "rtl_executed": False}),
            "Qwen2 payload manifest identity/scope drift")
    require(len(manifest["tensors"]) == len(specs), "Qwen2 payload inventory drift")
    values = {}
    for spec, record in zip(specs, manifest["tensors"], strict=True):
        pin = pins[spec["local_name"]]
        filename = spec["local_name"] + ".bin"
        require(_same(record, {**spec, "file": filename, "sha256": pin["sha256"]}),
                "Qwen2 payload geometry/order/digest drift")
        raw = _path(directory, filename).read_bytes()
        require(len(raw) == spec["bytes"] and sha256(raw) == pin["sha256"], "Qwen2 payload bytes/hash mismatch")
        require(len(record["http_ranges"]) == len(pin["segments"]), "Qwen2 HTTP range count drift")
        for segment, receipt in zip(pin["segments"], record["http_ranges"], strict=True):
            start, end = segment["start"], segment["end"]
            chunk = raw[start - spec["start"]:end - spec["start"] + 1]
            validate_http(shard, start, end, chunk, receipt, segment["sha256"])
        values[spec["local_name"]] = raw
    return manifest, values
