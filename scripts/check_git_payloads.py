#!/usr/bin/env python3
"""Fail if rebuildable model payloads enter the Git index, even with git add -f.

Policy is scoped: other small purpose-built NPZ fixtures and command/descriptor
BIN evidence are allowed. Inspect indexed bytes, never the working-tree version.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TRANSIENT_ROOTS = {"models", "weights", "checkpoints", "work", "artifacts"}
CHECKPOINT_SUFFIXES = {".safetensors", ".gguf", ".ggml", ".ckpt", ".pt", ".pth"}
TENSOR_SUFFIXES = {".npz", ".npy", ".bin", ".mem", ".memh", ".hex"}
# Exact historical blobs must not be reintroduced under innocent filenames.
FROZEN_BLOBS = {
    "4b95de5b6030ec149d0faf70d6eab4e9017a4d17",
    "d0ae1caca47ba021cb2fe68e5a827eff5331a383",
    "dd89e74519fd389b8c1ad1a8dfdbddb785160752",
}
HEADER_PREFIX = "config/upstream/weight_headers/"
MAX_HEADER_BYTES = 16 * 1024 * 1024


def forbidden_reason(name: str, blob: str = "") -> str | None:
    path = PurePosixPath(name)
    lower = path.name.lower()
    suffix = path.suffix.lower()
    if blob in FROZEN_BLOBS:
        return "historical RoPE payload (including renamed copies)"
    if path.parts[0].lower() in TRANSIENT_ROOTS:
        return "transient download/build directory"
    if name.startswith(("tests/fixtures/rope_rounding/", "tests/fixtures/qk_norm256/")) and suffix in {".npz", ".npy"}:
        return "transient RoPE/QK corpus"
    if suffix in CHECKPOINT_SUFFIXES:
        return "full model checkpoint"
    if suffix in TENSOR_SUFFIXES and "weight" in lower:
        return "downloadable/converted tensor weights"
    if suffix == ".bin" and re.match(r"(?:pytorch_model|model)(?:[.\-_0-9]|$)", lower):
        return "full model checkpoint"
    return None


def validate_header(raw: bytes) -> None:
    if len(raw) < 10 or len(raw) > MAX_HEADER_BYTES + 8:
        raise ValueError("invalid header-only size")
    length = int.from_bytes(raw[:8], "little")
    if length != len(raw) - 8:
        raise ValueError("header-only file contains trailing tensor bytes or is truncated")
    header = json.loads(raw[8:])
    if not isinstance(header, dict) or not header:
        raise ValueError("header-only JSON must be a nonempty object")
    for name, entry in header.items():
        if name != "__metadata__" and (not isinstance(entry, dict)
                or not all(k in entry for k in ("dtype", "shape", "data_offsets"))):
            raise ValueError("invalid tensor header entry")


def check_index(root: Path = ROOT) -> list[str]:
    data = subprocess.check_output(["git", "-C", str(root), "ls-files", "--stage", "-z"])
    problems = []
    for entry in data.split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, blob, stage = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8", "surrogateescape")
        if stage != "0":
            problems.append(name + ": unresolved index stage")
            continue
        is_header = name.startswith(HEADER_PREFIX) and name.endswith(".safetensors.header.bin")
        if is_header:
            if mode not in {"100644", "100755"}:
                problems.append(name + ": header evidence must be a regular file")
                continue
            try:
                size = int(subprocess.check_output(["git", "-C", str(root), "cat-file", "-s", blob]))
                if size > MAX_HEADER_BYTES + 8:
                    raise ValueError("header-only size cap exceeded")
                raw = subprocess.check_output(["git", "-C", str(root), "cat-file", "blob", blob])
                validate_header(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                problems.append(name + ": " + str(exc))
            continue
        reason = forbidden_reason(name, blob)
        if reason:
            problems.append(name + ": " + reason)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        problems = check_index(args.root)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("GIT_PAYLOAD_CHECK_REJECTED: " + str(exc), file=sys.stderr)
        return 2
    if problems:
        print("GIT_PAYLOAD_CHECK_REJECTED:\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print("PASS: no scoped rebuildable payloads in the Git index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
