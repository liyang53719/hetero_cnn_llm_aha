#!/usr/bin/env python3
"""Pinned, opaque-byte acquisition candidate. Default command is offline plan.

No extraction, subprocess, compiler, class loader, package manager, credential
lookup, proxy override, alternate URL, redirect, or retry is implemented here.
Actual fetch requires separate authorization; its explicit switch is an accident
guard, not a grant of permission. Tests inject synthetic streams, never URLs.
"""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import urllib.parse
import urllib.request


HERE = Path(__file__).resolve().parent
SOURCE_CANDIDATE = HERE.parent
CHUNK_BYTES = 64 * 1024
GROUP_HASHES = {
    "jar87": "8d571b869c4ade3e2bc252c9d694dab0e61029cb611bce8cbfcd317584e08b5e",
    "hardfloat20": "3afa358e7e1ab0f58a5b8b140c707063aeb619ec475f438ccd1724b3532b7c73",
    "firtool": "249e9ad75a8049934b61e980bbcc61068bb1286b5dfdf69975cb803c9f4dea6a",
    "verilator": "dce545ae9c24a9c05d138edc113c9d72694d62152f8486c9dea6daab33958e6e",
    "idma": "10e063b860f0b5f28b028c3b4502dd7e3099212f5db34b7ac0c03dbef157ad9f",
}
GROUP_COUNTS = {"jar87": 87, "hardfloat20": 20, "firtool": 1, "verilator": 1, "idma": 1}
URL_PREFIXES = {
    "jar87": "https://repo.maven.apache.org/maven2/",
    "hardfloat20": "https://raw.githubusercontent.com/ucb-bar/berkeley-hardfloat/c1105e6ac6a0dd90fc80893efc4830ab609005d3/",
    "firtool": "https://repo.maven.apache.org/maven2/org/chipsalliance/llvm-firtool/1.62.1/",
    "verilator": "https://deb.debian.org/debian/pool/main/v/verilator/",
    "idma": "https://api.github.com/repos/liyang53719/hetero_cnn_llm_aha/actions/artifacts/12099239717/",
}


class AcquisitionError(Exception):
    """Fail closed; no alternate route or partial success is implied."""


def require(condition, message):
    if not condition:
        raise AcquisitionError(message)


def relative_path(value):
    require(isinstance(value, str) and value, "empty or non-string destination")
    require(not any(c in value for c in "\\\x00\r\n:"), "unsafe destination characters")
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(p not in ("", ".", "..") for p in value.split("/")),
            "destination must be normalized and relative")
    return path


def positive_integer(value):
    return type(value) is int and value > 0


def validate_plan(plan):
    require(plan.get("schema") == 1, "unsupported plan schema")
    group = plan.get("group")
    require(group in GROUP_HASHES, "unknown fixed acquisition group")
    expected_transport = "connector-materialized-only" if group == "idma" else "https-no-redirect"
    require(plan.get("transport") == expected_transport, "incorrect transport")
    artifacts = plan.get("artifacts")
    require(isinstance(artifacts, list) and len(artifacts) == plan.get("artifact_count"), "artifact count mismatch")
    require(artifacts, "empty plan")
    limits = plan.get("limits", {})
    for key in ("total_transfer_bytes", "socket_timeout_seconds", "elapsed_check_seconds"):
        require(positive_integer(limits.get(key)), "missing finite positive limit: " + key)
    destinations = set()
    for artifact in artifacts:
        dest = str(relative_path(artifact.get("relative_destination")))
        require(dest not in destinations, "duplicate destination")
        require(dest.split("/")[0] not in ("ACQUISITION.json", "FAILED.json"), "reserved destination")
        require(not dest.endswith(".part"), "reserved partial-file destination")
        require(not any(dest.startswith(p + "/") or p.startswith(dest + "/") for p in destinations),
                "destination file/directory collision")
        destinations.add(dest)
        require(isinstance(artifact.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]),
                "invalid SHA-256 pin")
        require(positive_integer(artifact.get("max_transfer_bytes")), "missing artifact transfer cap")
        size = artifact.get("known_size_bytes")
        require(size is None or (type(size) is int and 0 <= size < artifact["max_transfer_bytes"]),
                "known size must be below transfer cap")
        url = artifact.get("url", "")
        require(isinstance(url, str) and url.startswith(URL_PREFIXES[group]), "URL outside fixed official prefix")
        parsed = urllib.parse.urlsplit(url)
        require(parsed.scheme == "https" and not parsed.username and not parsed.password
                and parsed.port is None and not parsed.query and not parsed.fragment, "unsafe URL")
        require(not any(c in url for c in "\r\n\x00\\") and "%" not in url, "encoded or unsafe URL")
        require(all(p not in (".", "..") for p in parsed.path.split("/")), "URL traversal")
    return plan


def load_plan(group):
    require(group in GROUP_HASHES, "unknown fixed acquisition group")
    raw = (HERE / "plans" / (group + ".json")).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == GROUP_HASHES[group], "fixed plan digest mismatch: " + group)
    plan = validate_plan(json.loads(raw))
    require(plan["group"] == group and len(plan["artifacts"]) == GROUP_COUNTS[group], "fixed group/count mismatch")
    return plan


class Budget:
    def __init__(self, limits, clock=time.monotonic):
        self.limit = limits["total_transfer_bytes"]
        self.bytes = 0
        self.clock = clock
        self.deadline = clock() + limits["elapsed_check_seconds"]

    def check(self):
        require(self.clock() < self.deadline, "elapsed acquisition budget exhausted")

    def allowance(self, artifact_remaining):
        self.check()
        available = min(CHUNK_BYTES, artifact_remaining, self.limit - self.bytes)
        require(available > 0, "transfer cap reached before EOF")
        return available


def copy_verified(stream, sink, artifact, budget):
    """Bound reads and writes, verify full stream, return fresh byte identity.

    Transfer caps include all bytes returned by read, including rejected data.
    Reaching a cap without observing EOF is a failure. Known-size artifacts have
    a one-byte larger transfer cap so trailing data can be detected safely.
    """
    digest = hashlib.sha256()
    count = 0
    read = getattr(stream, "read1", stream.read)
    while True:
        allowance = budget.allowance(artifact["max_transfer_bytes"] - count)
        chunk = read(allowance)
        require(isinstance(chunk, bytes), "stream violated bounded read contract")
        # Received bytes count even when this read crossed the deadline or its
        # stream violated the requested length. Rejected bytes are not written.
        count += len(chunk)
        budget.bytes += len(chunk)
        require(len(chunk) <= allowance, "stream violated bounded read contract")
        budget.check()
        if not chunk:
            break
        expected = artifact["known_size_bytes"]
        require(expected is None or count <= expected, "artifact exceeds pinned size")
        if sink is not None:
            sink.write(chunk)
        digest.update(chunk)
    require(artifact["known_size_bytes"] in (None, count), "artifact size mismatch")
    actual = digest.hexdigest()
    require(actual == artifact["sha256"], "artifact SHA-256 mismatch")
    return {"relative_destination": artifact["relative_destination"], "sha256": actual, "size_bytes": count}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AcquisitionError("redirect rejected; no fallback route")


def default_opener():
    # build_opener retains Python's platform TLS trust and inherited ProxyHandler.
    # Never pass ProxyHandler({}), disable certificates, inspect credentials, or
    # catch a failure to retry via a different host, URL, or transport.
    return urllib.request.build_opener(NoRedirect())


def check_response(response, artifact):
    require(response.status == 200, "only HTTP 200 is accepted")
    require(response.geturl() == artifact["url"], "response URL changed")
    require(response.headers.get("Content-Encoding", "identity").lower() == "identity", "encoded body rejected")
    values = response.headers.get_all("Content-Length", [])
    require(len(values) <= 1, "ambiguous Content-Length")
    if values:
        require(re.fullmatch(r"[0-9]+", values[0]) is not None, "invalid Content-Length")
        declared = int(values[0])
        require(declared < artifact["max_transfer_bytes"], "Content-Length reaches transfer cap")
        require(artifact["known_size_bytes"] in (None, declared), "Content-Length differs from pinned size")
        return declared
    return None


def no_symlink_path(path):
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.normpath(str(path)), "path must be normalized and absolute")
    for part in (path, *path.parents):
        require(not part.is_symlink(), "symlink path component rejected")
    return path


def checked_output_root(value, repository, must_be_new):
    """Explicit checkout boundary: relocation must never change the exclusion."""
    root = no_symlink_path(value)
    checkout = no_symlink_path(repository).resolve()
    require(checkout.is_dir() and (checkout / ".git").exists(), "--repository must name an existing checkout root")
    resolved = root.resolve()
    for protected in (checkout, SOURCE_CANDIDATE):
        require(resolved != protected and protected not in resolved.parents,
                "artifact directory must be outside repository and source candidate")
    require(root.parent.is_dir(), "output parent directory must already exist")
    if must_be_new:
        require(not root.exists(), "output directory already exists; never merge or overwrite")
    else:
        require(root.is_dir(), "artifact directory must already exist")
    return root


def open_regular(path):
    path = no_symlink_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "materialized input must be a regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def write_json(path, value):
    temporary = path.with_name(path.name + ".part")
    owned = False
    try:
        handle = temporary.open("x", encoding="utf-8")
        owned = True
        with handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # link is atomic and, unlike rename, refuses to replace an existing file.
        os.link(temporary, path)
    except BaseException as error:
        if owned:
            try:
                temporary.unlink(missing_ok=True)
            except BaseException as cleanup_error:
                error.add_note("receipt cleanup error: " + type(cleanup_error).__name__)
        raise
    # The link above is the commit point. Cleanup cannot revoke a committed
    # receipt or turn it into a second, contradictory terminal state.
    try:
        temporary.unlink()
    except BaseException as cleanup_error:
        return {"path": temporary.name, "error_type": type(cleanup_error).__name__}
    return None


def acquire(plan, root, materialized_idma=None, opener=None):
    """Internal engine; CLI accepts only immutable built-in plans. No extraction."""
    validate_plan(plan)
    require((plan["group"] == "idma") == (materialized_idma is not None),
            "idma requires one separately connector-materialized local file; other groups reject it")
    budget = Budget(plan["limits"])
    root.mkdir(mode=0o700)  # Must be new. The CLI also rejects repository outputs.
    records = []
    partial = None
    partial_owned = False
    try:
        for artifact in plan["artifacts"]:
            budget.check()
            dest = root.joinpath(*relative_path(artifact["relative_destination"]).parts)
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            partial = dest.with_name(dest.name + ".part")
            declared = None
            if plan["transport"] == "connector-materialized-only":
                stream = open_regular(materialized_idma)
            else:
                if opener is None:
                    opener = default_opener()
                request = urllib.request.Request(artifact["url"], headers={"Accept-Encoding": "identity"})
                timeout = min(plan["limits"]["socket_timeout_seconds"], max(0.001, budget.deadline - budget.clock()))
                stream = opener.open(request, timeout=timeout)
            with closing(stream):
                if plan["transport"] == "https-no-redirect":
                    declared = check_response(stream, artifact)
                else:
                    require(os.fstat(stream.fileno()).st_size == artifact["known_size_bytes"], "materialized archive size mismatch")
                sink = partial.open("xb")
                partial_owned = True
                with sink:
                    record = copy_verified(stream, sink, artifact, budget)
                require(declared in (None, record["size_bytes"]), "body differs from Content-Length")
            os.link(partial, dest)  # Exclusive publication; never replace a file.
            records.append(record | {"origin_url": artifact["url"], "transport": plan["transport"]})
            partial.unlink()
            partial = None
            partial_owned = False
        receipt = {
            "schema": 1, "status": "VERIFIED_OPAQUE_BYTES_ONLY", "group": plan["group"],
            "fixed_plan_sha256": GROUP_HASHES[plan["group"]],
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "artifacts": records, "received_bytes": budget.bytes,
            "extracted": False, "installed": False, "executed": False,
            "host_compilation_or_rtl_evidence": False,
        }
        cleanup_error = write_json(root / "ACQUISITION.json", receipt)
        if cleanup_error is not None:
            # Nonterminal warning, also returned to the caller's bounded log.
            warning = {"status": "COMMITTED_ACQUISITION_CLEANUP_WARNING", "cleanup_error": cleanup_error}
            receipt["post_commit_cleanup_warning"] = warning
            try:
                warning_cleanup = write_json(root / "CLEANUP_WARNING.json", warning)
                if warning_cleanup is not None:
                    receipt["warning_receipt_cleanup_error"] = warning_cleanup
            except BaseException as warning_error:
                receipt["warning_receipt_error_type"] = type(warning_error).__name__
        return receipt
    except BaseException as error:
        cleanup_errors = []
        if partial_owned and partial is not None:
            try:
                partial.unlink(missing_ok=True)
            except BaseException as cleanup_error:
                cleanup_errors.append({"path": partial.name, "error_type": type(cleanup_error).__name__})
                error.add_note("artifact cleanup error: " + type(cleanup_error).__name__)
        failure = {
            "status": "INCOMPLETE_NO_ACQUISITION_SUCCESS", "group": plan["group"],
            "verified_partial_artifacts": records, "received_bytes": budget.bytes,
            "error_type": type(error).__name__, "no_fallback_attempted": True,
            "cleanup_errors": cleanup_errors,
        }
        try:
            receipt_cleanup = write_json(root / "FAILED.json", failure)
            if receipt_cleanup is not None:
                error.add_note("failure receipt cleanup error: " + receipt_cleanup["error_type"])
        except BaseException as receipt_error:
            error.add_note("failure receipt publication error: " + type(receipt_error).__name__)
        raise


def verify(plan, root):
    """Fresh read-only byte verification; does not trust historical receipts."""
    budget = Budget(plan["limits"])
    records = []
    for artifact in plan["artifacts"]:
        path = root.joinpath(*relative_path(artifact["relative_destination"]).parts)
        with open_regular(path) as source:
            records.append(copy_verified(source, None, artifact, budget))
    return {"status": "FRESH_BYTE_VERIFICATION_ONLY", "group": plan["group"], "artifacts": records,
            "host_compilation_or_rtl_evidence": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    show = commands.add_parser("plan", help="offline validation and summary (default)")
    show.add_argument("group", nargs="?", choices=GROUP_HASHES)
    fetch = commands.add_parser("fetch", help="future authorized opaque-byte acquisition only")
    fetch.add_argument("group", choices=GROUP_HASHES)
    fetch.add_argument("--repository", required=True, help="explicit checkout root excluded from acquisition output")
    fetch.add_argument("--output-root", required=True)
    fetch.add_argument("--execute-acquisition", action="store_true", help="accident guard, not authorization")
    fetch.add_argument("--materialized-idma", help="local file from separately authorized connector materialization")
    check = commands.add_parser("verify", help="read-only local byte verification")
    check.add_argument("group", choices=GROUP_HASHES)
    check.add_argument("--repository", required=True, help="explicit checkout root excluded from artifact storage")
    check.add_argument("--output-root", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in (None, "plan"):
            groups = [args.group] if getattr(args, "group", None) else GROUP_HASHES
            result = [{"group": group, "artifacts": len((plan := load_plan(group))["artifacts"]),
                       "transport": plan["transport"], "total_transfer_cap_bytes": plan["limits"]["total_transfer_bytes"],
                       "unknown_size_count": sum(a["known_size_bytes"] is None for a in plan["artifacts"]),
                       "status": "VALIDATED_PLAN_ONLY_NO_ACQUISITION"} for group in groups]
        else:
            plan = load_plan(args.group)
            if args.command == "verify":
                result = verify(plan, checked_output_root(args.output_root, args.repository, must_be_new=False))
            else:
                require(args.execute_acquisition, "fetch is disabled without --execute-acquisition; separate approval is still required")
                root = checked_output_root(args.output_root, args.repository, must_be_new=True)
                if args.materialized_idma is not None:
                    no_symlink_path(args.materialized_idma)
                result = acquire(plan, root, args.materialized_idma)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (AcquisitionError, OSError, ValueError) as error:
        # Never expose URLs returned by a service (they may contain signed tokens).
        print("Acquisition stopped: " + (str(error) if isinstance(error, AcquisitionError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
