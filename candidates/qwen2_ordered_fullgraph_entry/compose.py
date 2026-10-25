"""Compose pinned source only; never import or execute a target module.

CLI: python -B compose.py --source-root BASE/source --output NEW_DIRECTORY
The output contains source/ (exactly 316 files), SOURCE_MANIFEST.json, and
COMPOSE_RECEIPT.json. Existing outputs and overlapping paths are rejected.
Historical result files are inert pinned provenance, not candidate acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
EXPECTED_COUNT = 316
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024
HEADER_ONLY = "config/upstream/weight_headers/qwen2_1p5b/model.safetensors.header.bin"
SUFFIX = "candidates/qwen2_resident_matrix/ffn_public/fullgraph_execution.py"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HUNK = re.compile(rb"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\r\n]*\n\Z")


class ComposeError(ValueError):
    """Fail-closed source composition error."""


def require(condition, message):
    if not condition:
        raise ComposeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(data):
    try:
        return json.loads(data, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComposeError("invalid JSON") from error


def _canonical_relative(value):
    require(isinstance(value, str) and value and "\\" not in value,
            "invalid relative source path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value and
            all(part not in ("", ".", "..") for part in path.parts),
            "non-canonical relative source path: " + value)
    require(not any(ord(char) < 32 or ord(char) == 127 for char in value),
            "control character in source path")
    return path


def _read_regular(path, maximum, expected_size=None):
    """Reject links/special files and bound a read before allocation."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode), "not a regular source file: " + str(path))
            require(before.st_size <= maximum, "source file exceeds byte bound")
            if expected_size is not None:
                require(before.st_size == expected_size, "source byte-count mismatch: " + str(path))
            data = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
            require(len(data) == before.st_size and len(data) <= maximum,
                    "source changed during read: " + str(path))
            require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                     before.st_ctime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                     after.st_ctime_ns), "source changed during read: " + str(path))
            return data
    except OSError as error:
        raise ComposeError("cannot read regular file: " + str(path)) from error


def load_pins(path):
    raw = _read_regular(path, 256 * 1024)
    pins = read_json(raw)
    require(isinstance(pins, dict), "pins must be an object")
    files = pins.get("source_files")
    require(isinstance(files, dict) and len(files) == EXPECTED_COUNT and
            type(pins.get("source_file_count")) is int and
            pins["source_file_count"] == EXPECTED_COUNT, "source pin count must be 316")
    require(pins.get("suffix_relative") == SUFFIX, "unexpected suffix path")
    require(pins.get("default_enabled") is False, "candidate must remain default-disabled")
    require(pins.get("full_numeric_status") == "TEMP_NOT_EXECUTED", "execution status cannot be inherited")
    for field in ("suffix_pre_sha256", "suffix_post_sha256", "patch_sha256"):
        require(isinstance(pins.get(field), str) and HEX64.fullmatch(pins[field]),
                "missing or invalid " + field)
    total = 0
    for name, entry in files.items():
        _canonical_relative(name)
        require(isinstance(entry, dict) and set(entry) == {"bytes", "sha256"},
                "unexpected file pin fields: " + name)
        require(type(entry["bytes"]) is int and 0 <= entry["bytes"] <= MAX_FILE_BYTES,
                "invalid file byte pin: " + name)
        require(isinstance(entry["sha256"], str) and HEX64.fullmatch(entry["sha256"]),
                "invalid file hash pin: " + name)
        total += entry["bytes"]
    require(total <= MAX_TOTAL_BYTES, "total source byte bound exceeded")
    require(SUFFIX in files and files[SUFFIX]["sha256"] == pins["suffix_pre_sha256"],
            "suffix preimage pin is inconsistent")
    require(pins["suffix_pre_sha256"] != pins["suffix_post_sha256"], "suffix must change")
    return pins, raw


def _inventory(root):
    files, directories = set(), set()
    pending = [root]
    while pending:
        folder = pending.pop()
        with os.scandir(folder) as entries:
            for entry in entries:
                path = Path(entry.path)
                rel = path.relative_to(root).as_posix()
                require(not entry.is_symlink(), "symlink is forbidden: " + rel)
                if entry.is_dir(follow_symlinks=False):
                    directories.add(rel)
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files.add(rel)
                else:
                    raise ComposeError("special source file is forbidden: " + rel)
                require(len(files) <= EXPECTED_COUNT and len(directories) <= EXPECTED_COUNT * 10,
                        "source tree exceeds file-set bounds")
    return files, directories


def _expected_directories(names):
    return {parent.as_posix() for name in names for parent in PurePosixPath(name).parents
            if parent.as_posix() != "."}


def _check_file_set(root, entries):
    actual_files, actual_dirs = _inventory(root)
    expected = set(entries)
    require(actual_files == expected,
            "source file-set mismatch; missing=" + repr(sorted(expected - actual_files)[:5]) +
            "; extra=" + repr(sorted(actual_files - expected)[:5]))
    require(actual_dirs == _expected_directories(expected), "unexpected or missing source directories")


def _check_source_content(name, data):
    require(not data.startswith(b"\x7fELF"), "ELF input is forbidden")
    if name == HEADER_ONLY:
        require(len(data) >= 8 and int.from_bytes(data[:8], "little") == len(data) - 8,
                "safetensors input must be header-only, without tensor payload")
        require(isinstance(read_json(data[8:]), dict), "invalid safetensors header-only JSON")
    else:
        require(PurePosixPath(name).suffix.lower() not in
                {".bin", ".npy", ".npz", ".safetensors", ".pt", ".pth", ".so", ".o", ".elf", ".pyc"},
                "non-source payload extension is forbidden: " + name)
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ComposeError("non-text source input: " + name) from error
        require(b"\x00" not in data, "binary payload is forbidden: " + name)


def apply_patch_exact(before, patch, relative=SUFFIX):
    """Apply this one-file unified diff without fuzz, offset, tools, or imports."""
    lines = patch.splitlines(keepends=True)
    expected_headers = [("--- a/" + relative + "\n").encode(),
                        ("+++ b/" + relative + "\n").encode()]
    require(lines[:2] == expected_headers, "patch must target only the pinned suffix")
    source = before.splitlines(keepends=True)
    output = []
    src_index, patch_index, hunks = 0, 2, 0
    while patch_index < len(lines):
        match = HUNK.fullmatch(lines[patch_index])
        require(match is not None, "invalid or additional-file patch header")
        old_start, old_count, new_start, new_count = match.groups()
        old_start = int(old_start)
        new_start = int(new_start)
        old_count = int(old_count) if old_count is not None else 1
        new_count = int(new_count) if new_count is not None else 1
        require(old_start >= 1 and new_start >= 1 and old_count > 0 and new_count > 0,
                "unsupported empty or zero-start hunk")
        target = old_start - 1
        require(src_index <= target <= len(source), "overlapping or out-of-range hunk")
        output.extend(source[src_index:target])
        src_index = target
        require(len(output) == new_start - 1, "new hunk line offset mismatch")
        patch_index += 1
        seen_old, seen_new = 0, 0
        while patch_index < len(lines) and not lines[patch_index].startswith(b"@@"):
            line = lines[patch_index]
            require(line[:1] in (b" ", b"-", b"+") and line.endswith(b"\n"),
                    "unsupported patch line")
            marker, payload = line[:1], line[1:]
            if marker in (b" ", b"-"):
                require(src_index < len(source) and source[src_index] == payload,
                        "patch preimage context mismatch")
                src_index += 1
                seen_old += 1
            if marker in (b" ", b"+"):
                output.append(payload)
                seen_new += 1
            patch_index += 1
        require((seen_old, seen_new) == (old_count, new_count), "hunk line-count mismatch")
        hunks += 1
    require(hunks == 3, "dispatch patch must contain exactly three hunks")
    output.extend(source[src_index:])
    return b"".join(output)


def _safe_paths(source_root, output):
    source_abs = Path(os.path.abspath(source_root))
    output_abs = Path(os.path.abspath(output))
    require(source_abs == source_abs.resolve() and output_abs == output_abs.resolve(),
            "symlink path aliases are forbidden")
    require(source_abs.is_dir(), "source root must exist and be a directory")
    require(source_abs != output_abs and source_abs not in output_abs.parents and
            output_abs not in source_abs.parents, "source and output must not overlap")
    require(not os.path.lexists(output_abs), "output already exists; refusing overwrite or duplicate apply")
    require(output_abs.parent.is_dir(), "output parent directory must already exist")
    return source_abs, output_abs


def compose(source_root, output, *, pins_path=None, patch_path=None):
    """Copy the exact verified closure into a fresh directory and apply one patch."""
    source, destination = _safe_paths(source_root, output)
    pins, raw_pins = load_pins(Path(pins_path) if pins_path else HERE / "SOURCE_PINS.json")
    patch = _read_regular(Path(patch_path) if patch_path else HERE / "suffix_dispatch.patch", 64 * 1024)
    require(digest(patch) == pins["patch_sha256"], "dispatch patch hash mismatch")
    _check_file_set(source, pins["source_files"])
    contents = {}
    for name, entry in sorted(pins["source_files"].items()):
        data = _read_regular(source / name, MAX_FILE_BYTES, entry["bytes"])
        require(digest(data) == entry["sha256"], "source hash mismatch: " + name)
        _check_source_content(name, data)
        contents[name] = data
    before = contents[SUFFIX]
    require(digest(before) == pins["suffix_pre_sha256"], "suffix preimage hash mismatch")
    after = apply_patch_exact(before, patch)
    require(digest(after) == pins["suffix_post_sha256"], "suffix postimage hash mismatch")
    contents[SUFFIX] = after
    # Recheck the complete source set before creating any output. The copied bytes
    # are the already pinned snapshot above, not a second unverified source read.
    _check_file_set(source, pins["source_files"])
    entries = {name: {"bytes": len(data), "sha256": digest(data)}
               for name, data in sorted(contents.items())}
    changed = [name for name in entries if entries[name] != pins["source_files"][name]]
    require(changed == [SUFFIX], "composition must change only the suffix")
    destination.mkdir(mode=0o755, exist_ok=False)
    source_out = destination / "source"
    source_out.mkdir()
    for name, data in contents.items():
        target = source_out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    _check_file_set(source_out, entries)
    for name, entry in entries.items():
        data = _read_regular(source_out / name, MAX_FILE_BYTES, entry["bytes"])
        require(digest(data) == entry["sha256"], "written source hash mismatch: " + name)
    manifest = {
        "schema": "qwen2-ordered-fullgraph-source-manifest-v1",
        "source_subdirectory": "source",
        "source_file_count": EXPECTED_COUNT,
        "source_files": entries,
        "source_pins_sha256": digest(raw_pins),
        "patch_sha256": digest(patch),
        "changed_relative_paths": changed,
        "default_enabled": False,
        "full_numeric_status": "TEMP_NOT_EXECUTED",
        "inherited_runtime_pass": False,
    }
    manifest_data = json_bytes(manifest)
    manifest_path = destination / "SOURCE_MANIFEST.json"
    with manifest_path.open("xb") as stream:
        stream.write(manifest_data)
    receipt = {
        "schema": "qwen2-ordered-fullgraph-compose-receipt-v1",
        "composition_status": "SOURCE_ONLY_COMPOSED",
        "source_root": str(source),
        "output_source_root": str(source_out),
        "source_file_count": EXPECTED_COUNT,
        "source_total_bytes_before": sum(item["bytes"] for item in pins["source_files"].values()),
        "source_total_bytes_after": sum(item["bytes"] for item in entries.values()),
        "source_manifest_relative": "SOURCE_MANIFEST.json",
        "source_manifest_sha256": digest(manifest_data),
        "source_pins_sha256": digest(raw_pins),
        "composer_sha256": digest(_read_regular(Path(__file__), MAX_FILE_BYTES)),
        "patch_sha256": digest(patch),
        "suffix_relative": SUFFIX,
        "suffix_pre_sha256": digest(before),
        "suffix_post_sha256": digest(after),
        "changed_relative_paths": changed,
        "default_enabled": False,
        "full_numeric_status": "TEMP_NOT_EXECUTED",
        "inherited_runtime_pass": False,
        "historical_receipts": "Copied only as pinned inert provenance; no M16/PV2 acceptance is inherited.",
        "execution": {"target_modules_imported": False, "native_build_or_run": False,
                      "numpy_imported": False, "rtl_executed": False},
        "payload_policy": "No tensor payloads, ELF, or user data. One exact header-only safetensors metadata file is pinned.",
    }
    with (destination / "COMPOSE_RECEIPT.json").open("xb") as stream:
        stream.write(json_bytes(receipt))
    return receipt


def set_resource_limits():
    """Bound the CLI and standalone cold tests to 1 CPU / 256 MiB / 20 CPU s / 25 wall s."""
    import resource
    for resource_id, requested in ((resource.RLIMIT_AS, 256 * 1024 * 1024),
                                   (resource.RLIMIT_CPU, 20)):
        soft, hard = resource.getrlimit(resource_id)
        finite = [requested] + [item for item in (soft, hard) if item != resource.RLIM_INFINITY]
        limit = min(finite)
        resource.setrlimit(resource_id, (limit, limit))
    if hasattr(os, "sched_getaffinity"):
        allowed = os.sched_getaffinity(0)
        require(bool(allowed), "no CPU affinity available")
        os.sched_setaffinity(0, {min(allowed)})
    def timed_out(_signum, _frame):
        raise ComposeError("25-second wall-clock composition limit exceeded")
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(25)


def main(argv=None):
    set_resource_limits()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = compose(args.source_root, args.output)
    except (ComposeError, OSError) as error:
        print("SOURCE_COMPOSE_REJECTED: " + str(error), file=sys.stderr)
        return 2
    print(json.dumps({key: receipt[key] for key in
                      ("composition_status", "output_source_root", "source_file_count",
                       "source_manifest_sha256", "suffix_post_sha256", "full_numeric_status")},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
