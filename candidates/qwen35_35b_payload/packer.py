"""Bounded original 35B input/QKV acquisition with immutable source metadata.

Run from the repository: PYTHONPATH=src:. python -m
candidates.qwen35_35b_payload.packer plan [--include-qkv].
Only the explicit ``collect`` command opens the network. Output must be outside
the checkout or under its ignored work/ directory. No model runtime is loaded.

The first fetch records observed tensor hashes. Keep the returned manifest
SHA256 independently: verify/reacquisition requires this digest and rejects
rewritten payloads even when their local manifest was rehashed. Neither a
range hash nor the pinned safetensors header verifies the whole LFS object.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import urllib.request

from heteronpu.model_geometry import load_json, require
from heteronpu.pinned_block_payload import MAX_RANGE_BYTES, fetch_range
from heteronpu.pinned_gdn_payload import ranges
from heteronpu.weight_header_contract import (
    DTYPE_BYTES, decode_header, read_record, sha256, verify_bundle,
)

KEY = "qwen3_5_35b_a3b"
MODEL = "Qwen/Qwen3.5-35B-A3B"
REVISION = "62704185bd97ad488cfc404e7caea797396b74dc"
FORWARD_REVISION = "42ca97014c85d71a88ad60d55f08cb9fb4d26e2c"
SOURCE_PATH = "candidates/qwen35_35b_payload/source_manifest.json"
SOURCE_SHA256 = "5e0845ecf47833d325de89208352cde5960059a35ccc0c634f85d46553e1c1a5"
INITIAL_BYTES = 1_052_672
WITH_QKV_BYTES = 34_607_104


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _same(observed: object, expected: object, label: str) -> None:
    # JSON distinguishes true from 1, including inside shapes/range lists.
    require(_json_bytes(observed) == _json_bytes(expected), label + " drift")


def _digest(value: str) -> None:
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            "expected SHA256 must be 64 lowercase hexadecimal characters")


def _spec_from_header(spec: dict, shard: dict, raw: bytes, header: dict) -> dict:
    """Validate full tensor extent before admitting a bounded leading row slab."""
    name = spec["name"]
    require(name in header, "selected tensor missing from shard")
    tensor = header[name]
    _same(tensor["dtype"], spec["dtype"], "source dtype")
    _same(tensor["shape"], spec["source_shape"], "source shape")
    lo, hi = tensor["data_offsets"]
    item_bytes = DTYPE_BYTES[tensor["dtype"]]
    require(hi - lo == math.prod(tensor["shape"]) * item_bytes, "full tensor extent mismatch")
    shape = spec["shape"]
    rows = spec["source_rows"]
    relative = 0
    if rows is None:
        _same(shape, tensor["shape"], "full tensor shape")
    else:
        require(len(tensor["shape"]) == 2 and isinstance(rows, list) and len(rows) == 2 and
                all(type(x) is int for x in rows) and 0 <= rows[0] < rows[1] <= tensor["shape"][0],
                "invalid source row interval")
        _same(shape, [rows[1] - rows[0], tensor["shape"][1]], "selected row shape")
        relative = rows[0] * tensor["shape"][1] * item_bytes
    size = math.prod(shape) * item_bytes
    start = len(raw) + lo + relative
    result = {**spec, "source_data_offsets": [lo, hi], "source_tensor_start": len(raw) + lo,
              "source_tensor_end": len(raw) + hi - 1, "source_tensor_bytes": hi - lo,
              "start": start, "end": start + size - 1, "bytes": size,
              "shard": shard["file"], "header_bytes": len(raw), "header_sha256": sha256(raw)}
    require(size > 0 and lo <= lo + relative < lo + relative + size <= hi,
            "selected range outside full tensor extent")
    _same(result, spec, "pinned tensor geometry")
    return result


def selection(root: Path, *, include_qkv: bool = False) -> dict:
    """Offline source lock verification, including all 14 headers and index."""
    require(type(include_qkv) is bool, "include_qkv must be boolean")
    root = Path(root)
    raw_source = (root / SOURCE_PATH).read_bytes()
    require(sha256(raw_source) == SOURCE_SHA256, "35B source manifest hash drift")
    source = load_json(root / SOURCE_PATH)
    _same([source["model_id"], source["revision"], source["forward_revision"]],
          [MODEL, REVISION, FORWARD_REVISION], "35B identity")
    verify_bundle(root, KEY)
    bundle = json.loads(read_record(root, source["bundle"]))
    _same(bundle["forward_revision"], FORWARD_REVISION, "forward revision")
    for key in ("config", "forward", "index", "profile"):
        _same(bundle[key], source[key], key + " identity")
        read_record(root, source[key])
    weights = load_json(root / source["index"]["path"])["weight_map"]
    shards = {s["file"]: s for s in bundle["shards"]}
    specs = deepcopy(source["tensors"][:3 if include_qkv else 2])
    selected_shards = {}
    for spec in specs:
        _same(weights[spec["name"]], spec["shard"], "index/shard mapping")
        shard = shards[spec["shard"]]
        header_raw = read_record(root, shard["header"])
        _spec_from_header(spec, shard, header_raw, decode_header(header_raw, shard["file_bytes"]))
        selected_shards[shard["file"]] = deepcopy(shard)
    _reject_aliases(specs)
    payload_bytes = sum(s["bytes"] for s in specs)
    require(payload_bytes == (WITH_QKV_BYTES if include_qkv else INITIAL_BYTES), "payload byte total drift")
    selected_shards = list(selected_shards.values())
    header_bytes = sum(s["header"]["bytes"] for s in selected_shards)
    return {"schema_version": 1, "model_id": MODEL, "revision": REVISION,
            "forward_revision": FORWARD_REVISION, "include_qkv": include_qkv,
            "source_manifest": {"path": SOURCE_PATH, "sha256": SOURCE_SHA256},
            "bundle": source["bundle"], "config": source["config"], "forward": source["forward"],
            "index": source["index"], "profile": source["profile"],
            "shards": selected_shards, "tensors": specs, "payload_bytes": payload_bytes,
            "header_preflight_bytes": header_bytes, "total_download_bytes": payload_bytes + header_bytes,
            "max_range_bytes": MAX_RANGE_BYTES, "semantics": source["semantics"],
            "claim_boundary": source["claim_boundary"]}


def _reject_aliases(specs: list[dict]) -> None:
    for key in ("name", "local_name", "file"):
        require(len({s[key] for s in specs}) == len(specs), "duplicate tensor/file alias")
    for spec in specs:
        require(spec["file"] == spec["local_name"] + ".bin" and
                Path(spec["file"]).name == spec["file"] and "\\" not in spec["file"], "unsafe payload filename")
    spans = sorted((s["shard"], s["start"], s["end"]) for s in specs)
    for left, right in zip(spans, spans[1:]):
        require(left[0] != right[0] or left[2] < right[1], "overlapping selected tensor alias")


def _check_receipt(receipt: dict, shard: dict, start: int, end: int, digest: str) -> None:
    require(isinstance(receipt, dict), "invalid HTTP receipt")
    expected = {"requested_url": shard["url"], "request_range": f"bytes={start}-{end}",
                "status": 206, "content_range": f'bytes {start}-{end}/{shard["file_bytes"]}',
                "bytes": end - start + 1, "sha256": digest}
    _same({k: receipt.get(k) for k in expected}, expected, "HTTP range receipt")


def _read_manifest(path: Path, expected_sha256: str, plan: dict) -> dict:
    _digest(expected_sha256)
    require(not path.is_symlink() and path.is_file() and path.stat().st_nlink == 1,
            "manifest symlink/hardlink/missing file")
    raw = path.read_bytes()
    require(sha256(raw) == expected_sha256, "observed manifest digest pin drift")
    manifest = load_json(path)
    _same(manifest.get("schema_version"), 1, "payload manifest schema")
    _same(manifest.get("plan"), plan, "payload source/selection")
    _same(manifest.get("status"), "ACQUIRED_OBSERVED_SELECTIVE_PAYLOAD_ONLY", "payload status")
    records = manifest.get("tensors")
    require(isinstance(records, list) and len(records) == len(plan["tensors"]), "payload inventory drift")
    for record, spec in zip(records, plan["tensors"], strict=True):
        _same({k: record.get(k) for k in spec}, spec, "payload tensor geometry/order")
        _digest(record.get("sha256"))
    header_receipts = manifest.get("header_http_ranges")
    require(isinstance(header_receipts, list) and len(header_receipts) == len(plan["shards"]),
            "header receipt inventory drift")
    for receipt, shard in zip(header_receipts, plan["shards"], strict=True):
        _check_receipt(receipt, shard, 0, shard["header"]["bytes"] - 1, shard["header"]["sha256"])
    _same(manifest.get("official_forward_executed"), False, "official forward claim")
    _same(manifest.get("full_checkpoint_sha256_verified"), False, "whole checkpoint claim")
    _same(manifest.get("rtl_executed"), False, "RTL claim")
    if manifest.get("prior_observed_manifest_sha256") is not None:
        _digest(manifest["prior_observed_manifest_sha256"])
    return manifest


def _output_directory(root: Path, output: Path) -> Path:
    root, resolved = root.resolve(), output.resolve()
    require(not output.is_symlink() and resolved == output.absolute(), "output symlink/alias refused")
    require(not resolved.is_relative_to(root) or resolved.is_relative_to(root / "work"),
            "payload output inside checkout must be under ignored work/")
    require(not resolved.exists(), "output must be fresh; stale/partial output refused")
    return resolved


def collect(root: Path, output: Path, *, include_qkv: bool = False,
            expected_manifest: Path | None = None, expected_manifest_sha256: str | None = None,
            opener=urllib.request.urlopen) -> dict:
    """Acquire exact original bytes; optionally bind to an earlier observed pin.

    Source shard headers are fetched and hash-checked before any payload body.
    Any failure leaves no success manifest. A partial output is never reused.
    """
    plan = selection(root, include_qkv=include_qkv)
    _reject_aliases(plan["tensors"])
    require((expected_manifest is None) == (expected_manifest_sha256 is None),
            "expected manifest path and SHA256 must be supplied together")
    prior = None if expected_manifest is None else _read_manifest(
        Path(expected_manifest), expected_manifest_sha256, plan)
    output = _output_directory(Path(root), Path(output))
    output.mkdir(parents=True, exist_ok=False)
    shards = {s["file"]: s for s in plan["shards"]}
    header_receipts = []
    for shard in plan["shards"]:
        raw, receipt = fetch_range(shard["url"], 0, shard["header"]["bytes"] - 1,
                                   shard["file_bytes"], opener=opener)
        require(sha256(raw) == shard["header"]["sha256"], "remote header hash drift")
        decode_header(raw, shard["file_bytes"])
        header_receipts.append(receipt)
    records = []
    for index, spec in enumerate(plan["tensors"]):
        shard = shards[spec["shard"]]
        chunks, receipts = [], []
        for start, end in ranges(spec):
            raw, receipt = fetch_range(shard["url"], start, end, shard["file_bytes"], opener=opener)
            chunks.append(raw)
            receipts.append(receipt)
        raw = b"".join(chunks)
        require(len(raw) == spec["bytes"], "assembled payload byte count mismatch")
        digest = sha256(raw)
        if prior is not None:
            require(digest == prior["tensors"][index]["sha256"], "payload differs from prior observed pin")
        # Exclusive creation plus a fresh non-symlink output prevents file aliasing.
        with (output / spec["file"]).open("xb") as handle:
            handle.write(raw)
        records.append({**spec, "sha256": digest, "http_ranges": receipts})
    manifest = {"schema_version": 1, "status": "ACQUIRED_OBSERVED_SELECTIVE_PAYLOAD_ONLY",
                "plan": plan, "header_http_ranges": header_receipts, "tensors": records,
                "prior_observed_manifest_sha256": expected_manifest_sha256,
                "full_checkpoint_sha256_verified": False, "official_forward_executed": False,
                "rtl_executed": False}
    with (output / "manifest.json").open("xb") as handle:
        handle.write(_json_bytes(manifest))
    return manifest


def load_payload(root: Path, directory: Path, *, manifest_sha256: str,
                 include_qkv: bool = False) -> tuple[dict, dict[str, bytes]]:
    """Reload against the caller's independently retained acquisition digest."""
    plan = selection(root, include_qkv=include_qkv)
    directory = Path(directory)
    require(not directory.is_symlink() and directory.resolve() == directory.absolute(),
            "payload directory symlink/alias refused")
    manifest = _read_manifest(directory / "manifest.json", manifest_sha256, plan)
    expected_files = {"manifest.json"} | {s["file"] for s in plan["tensors"]}
    require({p.name for p in directory.iterdir()} == expected_files, "unexpected payload files/aliases")
    shards = {s["file"]: s for s in plan["shards"]}
    values, inodes = {}, set()
    for spec, record in zip(plan["tensors"], manifest["tensors"], strict=True):
        path = directory / spec["file"]
        require(not path.is_symlink() and path.is_file() and path.resolve().parent == directory.resolve(),
                "payload path escape/symlink")
        stat = path.stat()
        identity = stat.st_dev, stat.st_ino
        require(identity not in inodes and stat.st_nlink == 1, "payload hardlink/file alias refused")
        inodes.add(identity)
        require(stat.st_size == spec["bytes"], "payload byte count mismatch")
        raw = path.read_bytes()
        require(sha256(raw) == record["sha256"], "payload hash mismatch")
        expected_ranges = list(ranges(spec))
        receipts = record.get("http_ranges")
        require(isinstance(receipts, list) and len(receipts) == len(expected_ranges), "payload range count drift")
        for (start, end), receipt in zip(expected_ranges, receipts, strict=True):
            chunk = raw[start - spec["start"]:end - spec["start"] + 1]
            _check_receipt(receipt, shards[spec["shard"]], start, end, sha256(chunk))
        values[spec["local_name"]] = raw
    return manifest, values


def raw_nk_to_kn(raw: bytes, n: int, k: int) -> bytes:
    """Bit-exact little-endian BF16 C-order transpose: KN[k,n] = NK[n,k].

    QKV uses n=8192, k=2048. This does no arithmetic, rounding, head splitting,
    row remapping, or official forward execution. Original acquisition stays NK.
    """
    require(type(n) is int and type(k) is int and n > 0 and k > 0, "invalid NK dimensions")
    require(isinstance(raw, bytes) and len(raw) == n * k * 2, "NK BF16 byte count mismatch")
    import numpy as np
    return np.frombuffer(raw, dtype="<u2").reshape(n, k).T.copy(order="C").tobytes(order="C")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "collect", "verify"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--include-qkv", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest-sha256", help="Independently retained digest required for verify")
    parser.add_argument("--expected-manifest", type=Path, help="Prior manifest for pinned reacquisition")
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args(argv)
    if args.command == "plan":
        require(args.output is None and args.manifest_sha256 is None and args.expected_manifest is None and
                args.expected_manifest_sha256 is None, "plan does not accept acquisition/verification arguments")
        result = {"status": "METADATA_PLAN_ONLY_NO_DOWNLOAD", **selection(args.root, include_qkv=args.include_qkv)}
    else:
        require(args.output is not None, "--output is required")
        if args.command == "collect":
            require(args.manifest_sha256 is None, "collect uses --expected-manifest-sha256 for prior pins")
            manifest = collect(args.root, args.output, include_qkv=args.include_qkv,
                               expected_manifest=args.expected_manifest,
                               expected_manifest_sha256=args.expected_manifest_sha256)
        else:
            require(args.manifest_sha256 is not None, "--manifest-sha256 is required")
            require(args.expected_manifest is None and args.expected_manifest_sha256 is None,
                    "verify does not accept reacquisition arguments")
            manifest, _ = load_payload(args.root, args.output, manifest_sha256=args.manifest_sha256,
                                       include_qkv=args.include_qkv)
        result = {"status": manifest["status"] if args.command == "collect" else "VERIFIED_OBSERVED_PAYLOAD_ONLY",
                  "output": str(args.output.resolve()), "payload_bytes": manifest["plan"]["payload_bytes"],
                  "manifest_sha256": sha256((args.output / "manifest.json").read_bytes()),
                  "official_forward_executed": False, "full_checkpoint_sha256_verified": False}
    print(_json_bytes(result).decode(), end="")


if __name__ == "__main__":
    main()
