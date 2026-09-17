"""Byte-preserving transport for sandbox-tested patches; no test result is inferred."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zlib


def apply(bundle: Path) -> str:
    data = json.loads(bundle.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("message"), str):
        raise ValueError("invalid bundle schema")
    if "\n" in data["message"] or not 1 <= len(data["message"]) <= 180:
        raise ValueError("invalid commit message")
    entries = data["files"]
    paths = [entry["path"] for entry in entries]
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("empty or duplicate patch paths")
    for entry in entries:
        name = entry["path"]
        if (not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
                or ".." in Path(name).parts
                or not name.startswith(("src/heteronpu/", "tests/", "scripts/", "doc/", "reports/execution/"))):
            raise ValueError("unapproved patch path")
        p = Path(name)
        if p.is_symlink() or not p.resolve().is_relative_to(Path.cwd().resolve()):
            raise ValueError("symlink/outside patch path")
        before = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        if before != entry["before"]:
            raise ValueError(f"preimage changed: {name}")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["after"]):
            raise ValueError("invalid postimage digest")
    decoder = zlib.decompressobj()
    patch = decoder.decompress(base64.b64decode(data["patch_zlib_base64"], validate=True), 16_000_001)
    if len(patch) > 16_000_000 or not decoder.eof or decoder.unused_data:
        raise ValueError("invalid or oversized patch")
    subprocess.run(["git", "diff", "--cached", "--exit-code"], check=True)
    subprocess.run(["git", "apply", "--check", "-"], input=patch, check=True)
    subprocess.run(["git", "apply", "--index", "-"], input=patch, check=True)
    changed = subprocess.check_output(["git", "diff", "--cached", "--name-only", "-z"]).decode().split("\0")[:-1]
    if set(changed) != set(paths):
        raise ValueError("patch modified unlisted files")
    for entry in entries:
        p = Path(entry["path"])
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != entry["after"]:
            raise ValueError(f"postimage mismatch: {p}")
    subprocess.run(["git", "diff", "--cached", "--check"], check=True)
    subprocess.run([sys.executable, "scripts/block_checklist.py", "validate"], check=True)
    rendered = subprocess.check_output([sys.executable, "scripts/block_checklist.py", "render"])
    if rendered != Path("doc/BLOCK_CHECKLIST.md").read_bytes():
        raise ValueError("stale rendered checklist")
    return data["message"]


if __name__ == "__main__":
    message = apply(Path(sys.argv[1]))
    if len(sys.argv) == 3 and sys.argv[2] == "--commit":
        subprocess.run(["git", "commit", "-m", message], check=True)
