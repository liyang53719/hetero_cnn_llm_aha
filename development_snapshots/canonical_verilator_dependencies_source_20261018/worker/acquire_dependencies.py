#!/usr/bin/env python3
"""Fixed five opaque Debian packages. SOURCE candidate; no install or extraction.

This adapter projects reviewed primitives from an exact frozen acquire.py buffer.
The parent supplies the absolute deadline and owns WNOWAIT/resource supervision.
"""
import argparse
import ast
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
PUBLISHED = {"bytes": 19263, "sha256": "4807fc702edfeb98d7eab9b86e727fe6d0d116ae7230200be7babb5a2c5b9b69"}
PLAN_PIN = {'bytes': 2594, 'sha256': '80fcca670bc897602db187f8f8db7b0ff7e8c3ee496a5cbef24266a03085be7e'}
GROUP = "debian-build-dependencies5"
NAMES = ("AcquisitionError", "require", "relative_path", "positive_integer", "validate_plan",
         "Budget", "copy_verified", "NoRedirect", "default_opener", "check_response",
         "no_symlink_path", "checked_output_root", "open_regular", "write_json", "acquire", "verify")
REPOSITORY_SOURCE = "candidates/qwen2_resident_matrix/host93_source_recovery/acquisition/acquire.py"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def clean(path):
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.normpath(str(path)), "absolute normalized path required")
    require(all(not part.is_symlink() for part in (path, *path.parents)), "symlink path refused")
    return path


def checked(path, pin):
    path = clean(path)
    require(type(pin["bytes"]) is int and 0 < pin["bytes"] <= 2 * 1024 * 1024, "finite source cap")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        meta = os.fstat(source.fileno())
        require(stat.S_ISREG(meta.st_mode) and meta.st_size == pin["bytes"], "fixed source size")
        raw = source.read(pin["bytes"] + 1)
    require(digest(raw) == pin, "fixed source digest")
    return raw


@contextmanager
def safe_closing(handle):
    """Preserve the original read/pin/write exception if resource close also fails."""
    try:
        yield handle
    except BaseException as original:
        try:
            handle.close()
        except BaseException as cleanup_error:
            original.add_note("resource close error: " + type(cleanup_error).__name__)
        raise
    else:
        handle.close()


def project(raw):
    require(digest(raw) == PUBLISHED, "published source pin")
    tree = ast.parse(raw)
    lines = raw.splitlines(keepends=True)
    selected = {node.name: b"".join(lines[node.lineno - 1:node.end_lineno])
                for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in NAMES}
    require(tuple(selected) == NAMES, "reviewed projection inventory drift")
    replacements = {
        "Budget": [
            ('self.deadline = clock() + limits["elapsed_check_seconds"]',
             'self.deadline = min(clock() + limits["elapsed_check_seconds"], WORK_DEADLINE)')],
        "write_json": [("with handle:", "with safe_closing(handle):")],
        "acquire": [
            ("with closing(stream):", "with safe_closing(stream):"),
            ("with sink:", "with safe_closing(sink):"),
            ("            os.link(partial, dest)  # Exclusive publication; never replace a file.",
             "            budget.check()\n            os.link(partial, dest)  # Exclusive publication; never replace a file."),
            ('        cleanup_error = write_json(root / "ACQUISITION.json", receipt)',
             '        budget.check()\n        receipt["terminal_success"] = False\n'
             '        receipt["acceptance_requires"] = "outer exit0, cleanup, absolute-budget and fresh-byte postflight"\n'
             '        cleanup_error = write_json(root / "ACQUISITION.json", receipt)')],
    }
    changes = []
    for name, edits in replacements.items():
        before = selected[name].decode("utf-8")
        after = before
        for old, new in edits:
            require(after.count(old) == 1, "exact projection anchor: " + name)
            after = after.replace(old, new, 1)
        reversed_text = after
        for old, new in reversed(edits):
            require(reversed_text.count(new) == 1, "reverse projection anchor: " + name)
            reversed_text = reversed_text.replace(new, old, 1)
        require(reversed_text == before, "reverse projection differs")
        selected[name] = after.encode("utf-8")
        changes.append({"name": name, "before": digest(before.encode()), "after": digest(selected[name])})
    projection = b"\n\n".join(selected[name] for name in NAMES) + b"\n"
    return projection, changes


def namespace(raw, deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), "finite absolute work deadline")
    projection, changes = project(raw)
    scope = dict(globals())
    scope.update({"__name__": "reviewed_dependency_primitives", "WORK_DEADLINE": deadline,
                  "SOURCE_CANDIDATE": HERE, "CHUNK_BYTES": 64 * 1024,
                  "GROUP_HASHES": {GROUP: PLAN_PIN["sha256"]},
                  "GROUP_COUNTS": {GROUP: 5},
                  "URL_PREFIXES": {GROUP: "https://deb.debian.org/debian/pool/main/"}})
    exec(compile(projection, "pinned_acquire_function_projection", "exec", dont_inherit=True), scope)
    return scope, {"projection": digest(projection), "changes": changes}


def preflight(repo, deadline):
    repo = clean(repo)
    require(repo.is_dir() and (repo / ".git").exists(), "explicit existing repository root")
    raw = checked(HERE / "published_acquire.py", PUBLISHED)
    require(checked(repo / REPOSITORY_SOURCE, PUBLISHED) == raw, "published source identity differs")
    plan_raw = checked(HERE / "DEPENDENCY_PLAN.json", PLAN_PIN)
    plan = json.loads(plan_raw)
    engine, projection = namespace(raw, deadline)
    engine["validate_plan"](plan)
    require(plan["group"] == GROUP and plan["artifact_count"] == len(plan["artifacts"]) == 5, "fixed five-package plan")
    require(plan["limits"] == {"total_transfer_bytes": 4194304, "socket_timeout_seconds": 30,
                               "elapsed_check_seconds": 160}, "fixed shared worker limits")
    require(sum(item["known_size_bytes"] for item in plan["artifacts"]) == 2466616, "fixed total pinned bytes")
    require(all(item["known_size_bytes"] < item["max_transfer_bytes"] <= 2097152
                for item in plan["artifacts"]), "per-package transfer ceiling")
    return plan, engine, projection


def absolute_deadline(started, requested, entered):
    require(all(type(x) in (int, float) and math.isfinite(x) for x in (started, requested, entered)), "finite shared timestamps")
    require(0 <= started <= entered < started + 10, "preflight/worker admission must be within shared first 10s")
    require(entered < requested <= started + 170, "requested worker deadline exceeds shared latest170")
    return min(requested, entered + 160)


def main(argv=None):
    entered = time.monotonic()
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, "use python -I -S -B")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--shared-start-monotonic", type=float)
    parser.add_argument("--work-deadline-monotonic", type=float)
    parser.add_argument("--execute-reviewed-acquisition", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute_reviewed_acquisition:
        require(args.output is None and args.shared_start_monotonic is None and args.work_deadline_monotonic is None,
                "SOURCE preflight takes only --repo and creates no output")
        plan, _engine, projection = preflight(args.repo, entered + 10)
        result = {"status": "SOURCE_PREFLIGHT_ONLY", "plan": PLAN_PIN, "projection": projection,
                  "package_count": len(plan["artifacts"]), "pinned_total_bytes": 2466616,
                  "child_started": False, "network_started": False, "packages_executed": False}
    else:
        require(args.output is not None, "fresh output required")
        stop = absolute_deadline(args.shared_start_monotonic, args.work_deadline_monotonic, entered)
        plan, engine, _projection = preflight(args.repo, stop)
        require(time.monotonic() < min(args.shared_start_monotonic + 10, stop), "preflight exhausted shared first10")
        root = engine["checked_output_root"](args.output, args.repo, must_be_new=True)
        require(time.monotonic() < stop, "work deadline already exhausted")
        previous_umask = os.umask(0o077)
        try:
            result = engine["acquire"](plan, root)
        finally:
            os.umask(previous_umask)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
