"""Pinned raw inputs for the 0.8B L0 cold128/carried128 software profile.

This owns ONE embedding slice, not the existing 29-tensor prefix package.
Layer0 parameters stay at their original external payload path and storage
dtypes. No model, arithmetic, state, intermediate tensor or RTL is executed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu import pinned_gdn_payload as gdn
from heteronpu import pinned_prefix_payload as prefix
from heteronpu.model_geometry import require
from heteronpu.pinned_block_payload import KEY, fetch_range
from heteronpu.weight_header_contract import PINS, sha256

NAME = "embed_tokens.rows_0_255"
FILENAME = NAME + ".bin"
EMBEDDING_BYTES = 256 * 1024 * 2
EMBEDDING_SCOPE = "PINNED_EMBEDDING_ROWS_0_255_ONLY"
FIXTURE_SCOPE = "QWEN35_0P8B_L0_COLD128_CARRIED128_RAW_INPUTS_ONLY"
SOURCE_FILES = (
    "candidates/qwen35_gdn_prefill/input_fixture.py",
    "src/heteronpu/pinned_prefix_payload.py", "src/heteronpu/pinned_gdn_payload.py",
    "src/heteronpu/pinned_block_payload.py", "src/heteronpu/weight_header_contract.py",
    "config/upstream/qwen3_5_0p8b/prefix_payload_pin.json",
    "config/upstream/qwen3_5_0p8b/layer0_payload_pin.json",
    "config/upstream/qwen3_5_0p8b/prefix_token_fixture.json",
)


def _encoded(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"


def _fresh(directory):
    directory = Path(directory)
    require(not directory.exists() and not directory.is_symlink(), "fresh nonexistent output required")
    return directory


def _read(directory, filename):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "payload directory must be a real directory")
    require(type(filename) is str and Path(filename).name == filename, "payload path escape")
    path = directory / filename
    require(not path.is_symlink() and path.is_file() and path.resolve().parent == directory.resolve(),
            "payload path escape or nonfile")
    return path.read_bytes()


def _inventory(directory, names):
    require({p.name for p in Path(directory).iterdir()} == set(names), "unexpected payload file inventory")


def embedding_spec(root=ROOT):
    """Reuse and verify the complete pinned metadata, then select only embedding."""
    root = Path(root)
    shard, specs = prefix.selection(root)
    pins = prefix.payload_pin(root, specs)
    selected = [s for s in specs if s["local_name"] == NAME]
    require(len(selected) == 1, "one pinned embedding slice required")
    spec = selected[0]
    require(spec["dtype"] == "BF16" and spec["shape"] == [256, 1024] and
            spec["source_shape"] == [248320, 1024] and spec["source_rows"] == [0, 256] and
            type(spec["bytes"]) is int and spec["bytes"] == EMBEDDING_BYTES and
            type(spec["start"]) is int and type(spec["end"]) is int and
            0 <= spec["start"] <= spec["end"] < shard["file_bytes"] and
            spec["end"] - spec["start"] + 1 == EMBEDDING_BYTES, "embedding slice domain drift")
    return shard, spec, pins[NAME]


def _embedding_manifest(shard, spec, digest, receipt):
    return dict(schema_version=1, scope=EMBEDDING_SCOPE,
                model_id=PINS[KEY][0], revision=PINS[KEY][1],
                header_sha256=shard["header"]["sha256"], payload_bytes=EMBEDDING_BYTES,
                tensors=[dict(spec, file=FILENAME, sha256=digest, http=receipt)],
                complete_prefix_payload=False, full_checkpoint_sha256_verified=False,
                official_forward_executed=False, rtl_executed=False)


def collect_embedding(root, output, *, opener=urllib.request.urlopen):
    """Fetch exactly 524288 pinned bytes; caller explicitly invokes networking."""
    output = _fresh(output)
    shard, spec, digest = embedding_spec(root)
    raw, receipt = fetch_range(shard["url"], spec["start"], spec["end"], shard["file_bytes"], opener=opener)
    require(len(raw) == EMBEDDING_BYTES and sha256(raw) == digest, "embedding bytes differ from observed pin")
    manifest = _embedding_manifest(shard, spec, digest, receipt)
    output.mkdir(parents=True)
    (output / FILENAME).write_bytes(raw)
    (output / "manifest.json").write_bytes(_encoded(manifest))
    return manifest


def load_embedding(root, directory):
    shard, spec, digest = embedding_spec(root)
    manifest = json.loads(_read(directory, "manifest.json"))
    _inventory(directory, (FILENAME, "manifest.json"))
    tensors = manifest.get("tensors")
    require(type(tensors) is list and len(tensors) == 1 and type(tensors[0]) is dict,
            "one embedding record required; complete prefix manifests are unsupported")
    record = tensors[0]
    receipt = record.get("http")
    require(type(receipt) is dict and type(receipt.get("acquired_at")) is str,
            "embedding HTTP receipt missing")
    expected_http = dict(requested_url=shard["url"], status=206,
        request_range=f'bytes={spec["start"]}-{spec["end"]}',
        content_range=f'bytes {spec["start"]}-{spec["end"]}/{shard["file_bytes"]}',
        bytes=EMBEDDING_BYTES, sha256=digest, acquired_at=receipt["acquired_at"])
    require(_encoded(receipt) == _encoded(expected_http), "embedding HTTP receipt drift")
    expected = _embedding_manifest(shard, spec, digest, receipt)
    # JSON equality would accept True in place of 1; canonical bytes do not.
    require(_encoded(manifest) == _encoded(expected), "embedding manifest identity/geometry drift")
    raw = _read(directory, record["file"])
    require(len(raw) == EMBEDDING_BYTES and sha256(raw) == digest, "embedding bytes/hash mismatch")
    return manifest, raw


def hidden_inputs(root, embedding):
    """Copy pinned token rows as raw BF16 words, without float conversion."""
    require(type(embedding) is bytes and len(embedding) == EMBEDDING_BYTES, "raw BF16 embedding byte domain")
    fixture = prefix.token_fixture(Path(root))
    ids = fixture["token_ids"]
    require(type(ids) is list and len(ids) == 256 and
            all(type(i) is int and 0 <= i < 256 for i in ids) and
            ids == [(73 * i + 19) % 256 for i in range(256)], "fixed token ID domain/order drift")
    rows = [embedding[token * 2048:(token + 1) * 2048] for token in ids]
    return ids.copy(), {"cold128.hidden.bf16le": b"".join(rows[:128]),
                        "carried128.hidden.bf16le": b"".join(rows[128:]),
                        "token_ids.u32le": struct.pack("<256I", *ids)}


def _assemble(root, embedding_directory, layer0_directory):
    root = Path(root)
    em, embedding = load_embedding(root, embedding_directory)
    gm, weights = gdn.load_payload(root, Path(layer0_directory))
    require((gm["model_id"], gm["revision"]) == (em["model_id"], em["revision"]), "input checkpoint mismatch")
    require(type(gm["layer_id"]) is int and gm["layer_id"] == 0 and len(gm["tensors"]) == 14 and
            set(weights) == {r["local_name"] for r in gm["tensors"]}, "complete layer0 payload required")
    require({r["local_name"] for r in gm["tensors"] if r["dtype"] == "F32"} == gdn.F32_NAMES and
            all(r["dtype"] == ("F32" if r["local_name"] in gdn.F32_NAMES else "BF16") for r in gm["tensors"]),
            "original layer0 mixed storage dtypes required")
    # load_payload already verifies every byte, size, source range and pin.
    # No weight cast or rewritten/duplicated parameter payload is produced.
    del weights
    ids, files = hidden_inputs(root, embedding)
    manifest = dict(schema_version=1, scope=FIXTURE_SCOPE, model_id=em["model_id"], revision=em["revision"],
        layer_id=0, batch=1, query_tokens=128, hidden_size=1024, token_ids=ids,
        cases=[dict(name="cold128", token_slice=[0, 128], past_tokens=0,
                    input_file="cold128.hidden.bf16le", dtype="BF16", shape=[1, 128, 1024]),
               dict(name="carried128", token_slice=[128, 256], past_tokens=128,
                    input_file="carried128.hidden.bf16le", dtype="BF16", shape=[1, 128, 1024])],
        source_sha256={name: sha256((root / name).read_bytes()) for name in SOURCE_FILES},
        sources=dict(embedding_directory=str(Path(embedding_directory).resolve()),
                     embedding_manifest_sha256=sha256(_read(embedding_directory, "manifest.json")),
                     embedding_tensor_sha256=em["tensors"][0]["sha256"],
                     layer0_directory=str(Path(layer0_directory).resolve()),
                     layer0_manifest_sha256=sha256(_read(layer0_directory, "manifest.json")),
                     layer0_tensors=[{k: r[k] for k in ("local_name", "dtype", "shape", "bytes", "sha256")} for r in gm["tensors"]]),
        files={name: dict(bytes=len(raw), sha256=sha256(raw)) for name, raw in files.items()},
        raw_hidden_origin="pinned checkpoint embedding rows indexed by the unchanged fixed token fixture",
        intermediate_tensors_generated=False, state_generated=False,
        official_forward_executed=False, software_execution_executed=False, rtl_executed=False)
    return manifest, files


def build_fixture(root, embedding_directory, layer0_directory, output):
    """Validate existing original payloads and publish only two raw hidden batches."""
    output = _fresh(output)
    manifest, files = _assemble(root, embedding_directory, layer0_directory)
    output.mkdir(parents=True)
    for name, raw in files.items():
        (output / name).write_bytes(raw)
    (output / "manifest.json").write_bytes(_encoded(manifest))
    return manifest


def load_fixture(root, directory):
    """Revalidate external pinned sources, source code and all raw input bytes."""
    manifest = json.loads(_read(directory, "manifest.json"))
    sources = manifest["sources"]
    expected, files = _assemble(root, sources["embedding_directory"], sources["layer0_directory"])
    require(_encoded(manifest) == _encoded(expected), "raw input fixture manifest drift")
    _inventory(directory, (*files, "manifest.json"))
    for name, raw in files.items():
        require(_read(directory, name) == raw, "raw input fixture bytes drift: " + name)
    return manifest, files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="operation", required=True)
    collect = commands.add_parser("collect-embedding")
    collect.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify-embedding")
    verify.add_argument("--embedding", type=Path, required=True)
    build = commands.add_parser("build")
    build.add_argument("--embedding", type=Path, required=True)
    build.add_argument("--layer0-payload", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    verify_inputs = commands.add_parser("verify-fixture")
    verify_inputs.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.operation == "collect-embedding":
        result = collect_embedding(args.root, args.output)
    elif args.operation == "verify-embedding":
        result, _ = load_embedding(args.root, args.embedding)
    elif args.operation == "build":
        result = build_fixture(args.root, args.embedding, args.layer0_payload, args.output)
    else:
        result, _ = load_fixture(args.root, args.fixture)
    print(json.dumps({k: result[k] for k in ("scope", "model_id", "revision")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
