#!/usr/bin/env python3
"""Recover pinned historical RoPE bytes into a transient, ignored directory.

This is download/extraction, not model execution. The source is an existing
public commit; removing current index entries does not erase that Git history.
Never substitute a current CPU's native outputs for this historical evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "tests/fixtures/rope_rounding"
SOURCE_COMMIT = "27542342d546eae3e283463c25cc31211817bf16"
SOURCE_DIRECTORY = "tests/fixtures/rope_rounding"
SOURCE_BASE = ("https://raw.githubusercontent.com/liyang53719/hetero_cnn_llm_aha/"
               + SOURCE_COMMIT + "/" + SOURCE_DIRECTORY + "/")
# Keep these identical to the consuming runner's independently pinned hashes.
FIXTURE_PINS = {
    "local.npz": "36a68fd9573d5b9757283668cd635cce5bb2f9ed9a12ceb254ebde7e35140e32",
    "remote.npz": "e9526ac7b8084fadb200ab5c6d5b7bc909ec8f34408a4b63daa7af664c66ca6c",
    "provenance.json": "3573898549e7bae16d2c191b99c14e492dd94f38c9097513485747c26d4e6b4a",
    "historical_arithmetic.npy": "39a0b80418759549d02691d879db80b6fa53d29855349eb0119d7790fc0c4f8b",
}
FIXTURE_BYTES = {"local.npz": 2786810, "remote.npz": 2787206,
                 "provenance.json": 13439, "historical_arithmetic.npy": 33008}


def validate(name: str, raw: bytes) -> None:
    if len(raw) != FIXTURE_BYTES[name]:
        raise ValueError("historical fixture length drift: " + name)
    if hashlib.sha256(raw).hexdigest() != FIXTURE_PINS[name]:
        raise ValueError("historical fixture digest drift: " + name)


def fetch(name: str) -> bytes:
    request = urllib.request.Request(SOURCE_BASE + name, headers={
        "Accept-Encoding": "identity", "User-Agent": "hetero-frozen-rope-corpus/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        if response.status != 200:
            raise ValueError("historical download status: " + str(response.status))
        if response.headers.get("Content-Encoding", "identity") != "identity":
            raise ValueError("encoded historical download refused")
        # Bound even a server that sends a wrong/omitted Content-Length.
        raw = response.read(FIXTURE_BYTES[name] + 1)
    validate(name, raw)
    return raw


def extract_git(name: str) -> bytes:
    """Offline recovery requires the exact old commit already in this clone."""
    raw = subprocess.check_output([
        "git", "-C", str(ROOT), "show", SOURCE_COMMIT + ":" + SOURCE_DIRECTORY + "/" + name],
        stderr=subprocess.PIPE)
    validate(name, raw)
    return raw


def materialize(output: Path = DEFAULT_OUTPUT, *, from_git=False, verify_only=False) -> dict:
    output = Path(output)
    missing = []
    for name in FIXTURE_PINS:
        path = output / name
        if path.is_symlink():
            raise ValueError("fixture symlink refused: " + name)
        if path.exists():
            validate(name, path.read_bytes())
        else:
            missing.append(name)
    if missing and verify_only:
        raise ValueError("missing historical fixtures: " + ", ".join(missing)
                         + "; run scripts/materialize_rope_rounding_corpora.py")
    if missing:
        output.mkdir(parents=True, exist_ok=True)
        # Validate ALL missing files before publishing any. Do not silently repair
        # corrupt existing files or leave partial downloads at their final names.
        with tempfile.TemporaryDirectory(prefix=".materialize-", dir=output) as temp:
            staging = Path(temp)
            for name in missing:
                raw = extract_git(name) if from_git else fetch(name)
                validate(name, raw)
                (staging / name).write_bytes(raw)
            for name in missing:
                destination = output / name
                if destination.exists() or destination.is_symlink():
                    raise ValueError("fixture appeared during materialization: " + name)
                os.replace(staging / name, destination)
    for name in FIXTURE_PINS:
        validate(name, (output / name).read_bytes())
    return {"status": "PASS_PINNED_HISTORICAL_BYTES_MATERIALIZED",
            "source_commit": SOURCE_COMMIT, "fixture_sha256": FIXTURE_PINS,
            "materialized_files": missing, "arithmetic_recomputed": False,
            "model_native_expectations_regenerated": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--from-git", action="store_true", help="extract from the pinned commit already in the local clone")
    mode.add_argument("--verify-only", action="store_true", help="check existing bytes without downloading")
    args = parser.parse_args()
    try:
        result = materialize(args.output, from_git=args.from_git, verify_only=args.verify_only)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("HISTORICAL_FIXTURE_RECOVERY_REJECTED: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
