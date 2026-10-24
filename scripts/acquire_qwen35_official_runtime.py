#!/usr/bin/env python3
"""Recover exact locked official artifacts; never install or execute downloads.

The retained Torch wheel is mandatory and is never downloaded. Other verified
local artifacts may be reused. Downloads use only official locked HTTPS URLs,
explicit checked redirects, exact byte/SHA pins, 60 seconds per request, a
300-second acquisition window and a cumulative 512 MiB body limit. No retry is
automatic. A failed fresh output remains inspectable; use a new output for any
separately authorized retry. The published lock is historical pin evidence, not
a claim that any new runtime is installed or qualified.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

LOCK_SHA256 = "806f6a7f409e85965261bf864fcc8de4558aaedf9f3da26759323625ca131497"
ALLOWED_HOSTS = {"github.com", "codeload.github.com", "files.pythonhosted.org"}
TOTAL_BODY_LIMIT = 512 * 1024 * 1024
ARCHIVE_LIMIT = 128 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def encoded(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"


def verify(path, record):
    return (path.is_file() and not path.is_symlink() and path.stat().st_size == record["bytes"]
            and sha(path) == record["sha256"])


def checked_url(url):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS and
            parsed.port in (None, 443) and not parsed.username and not parsed.password and
            not parsed.query and not parsed.fragment, "URL outside exact official HTTPS acquisition scope")
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BoundedAcquisition:
    def __init__(self, output, *, opener=None, clock=time.monotonic):
        self.output = Path(output)
        self.clock = clock
        self.started = clock()
        self.total = 0
        self.opener = opener or urllib.request.build_opener(NoRedirect)

    def event(self, item):
        with (self.output / "network.jsonl").open("ab") as stream:
            stream.write(json.dumps(item, sort_keys=True).encode() + b"\n")

    def fetch(self, url, target, record):
        canonical = checked_url(url)
        current = canonical
        deadline = min(self.started + 300, self.clock() + 60)
        require(record["bytes"] <= ARCHIVE_LIMIT, "Single artifact exceeds acquisition limit")
        partial = target.with_name(target.name + ".partial")
        require(not target.exists() and not partial.exists(), "Never overwrite acquisition evidence")
        for hop in range(4):
            checked_url(current)
            remaining = deadline - self.clock()
            require(remaining > 0, "Acquisition request/window time budget exhausted")
            signal.alarm(max(1, int(remaining)))
            entry = {"canonical_url": canonical, "url": current, "hop": hop,
                     "started_utc": datetime.now(timezone.utc).isoformat()}
            try:
                request = urllib.request.Request(current, headers={"Accept-Encoding": "identity", "User-Agent": "qwen35-locked-recovery/1"})
                try:
                    response = self.opener.open(request, timeout=min(60, remaining))
                except urllib.error.HTTPError as error:
                    if error.code not in (301, 302, 303, 307, 308):
                        raise
                    response = error
                with response:
                    entry["status"] = response.status
                    if response.status in (301, 302, 303, 307, 308):
                        current = checked_url(urllib.parse.urljoin(current, response.headers["Location"]))
                        entry["redirect"] = current
                        self.event(entry)
                        continue
                    require(response.status == 200, "Unexpected HTTP status")
                    require(response.headers.get("Content-Encoding", "identity") == "identity", "Unexpected body encoding")
                    declared = response.headers.get("Content-Length")
                    require(declared is None or int(declared) == record["bytes"], "Declared size differs from exact lock")
                    measured = 0
                    digest = hashlib.sha256()
                    with partial.open("xb") as stream:
                        while True:
                            amount = min(1024 * 1024, record["bytes"] + 1 - measured,
                                         TOTAL_BODY_LIMIT + 1 - self.total)
                            chunk = response.read(amount)
                            if not chunk:
                                break
                            measured += len(chunk)
                            self.total += len(chunk)
                            require(measured <= record["bytes"] and self.total <= TOTAL_BODY_LIMIT,
                                    "Exact artifact/cumulative body budget exceeded")
                            stream.write(chunk)
                            digest.update(chunk)
                    entry.update(bytes=measured, sha256=digest.hexdigest(), cumulative_bytes=self.total)
                    require(measured == record["bytes"] and digest.hexdigest() == record["sha256"], "Downloaded identity differs from lock")
                    partial.rename(target)
                    self.event(entry)
                    return
            except BaseException as error:
                entry.update(status="FAILED", error_type=type(error).__name__, error=str(error), cumulative_bytes=self.total)
                self.event(entry)
                raise
            finally:
                signal.alarm(0)
        raise ValueError("More than three redirects; stop without fallback")


def verify_metadata(path, record):
    """The whole wheel hash must pass before reading its recorded METADATA."""
    require(verify(path, record), "Wheel identity mismatch before metadata read")
    with zipfile.ZipFile(path) as wheel:
        names = [n for n in wheel.namelist() if n.count("/") == 1 and n.endswith(".dist-info/METADATA")]
        require(len(names) == 1, "Ambiguous wheel metadata")
        raw = wheel.read(names[0])
        expected = record["wheel_metadata"]
        require(len(raw) == expected["bytes"] and hashlib.sha256(raw).hexdigest() == expected["sha256"]
                and names[0] == expected["member"], "Locked wheel METADATA differs")
        metadata = BytesParser().parsebytes(raw)
        normalize = lambda value: value.lower().replace("_", "-").replace(".", "-")
        require(normalize(metadata["Name"]) == record["name"] and metadata["Version"] == record["version"], "Wheel name/version differs")
        require(metadata.get_all("Requires-Dist", []) == record["wheel_requires_dist"], "Actual dependency metadata differs")


def recover(lock_path, output, torch_wheel, reuse, offline_only=False):
    require(sys.version_info[:2] == (3, 12) and sys.platform == "linux" and platform.machine() == "x86_64",
            "Lock is scoped to CPython3.12 Linux x86_64")
    require(sha(lock_path) == LOCK_SHA256, "Reviewed public dependency lock changed")
    lock = json.loads(lock_path.read_bytes())
    require(not output.exists(), "Fresh nonexistent acquisition output required")
    torch = next(r for r in lock["artifacts"] if r["name"] == "torch")
    require(verify(torch_wheel, torch), "Verified retained Torch wheel required; never redownload")
    output.mkdir(parents=True)
    (output / "wheels").mkdir()
    (output / "network.jsonl").touch()
    collector = BoundedAcquisition(output)
    previous_alarm = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("Bounded acquisition deadline")))
    result = json.loads(json.dumps(lock))
    try:
        for item in result["artifacts"]:
            target = output / item["relative_path"]
            require(target.parent == output / "wheels", "Wheel destination escape")
            candidates = [torch_wheel] if item["name"] == "torch" else [directory / item["filename"] for directory in reuse]
            source = next((p for p in candidates if verify(p, item)), None)
            if source is not None:
                shutil.copyfile(source, target)
                item["acquisition"] = "fresh_verified_local_copy"
            else:
                require(not offline_only and item["name"] != "torch", "Required artifact unavailable offline")
                collector.fetch(item["url"], target, item)
                item["acquisition"] = "fresh_bounded_official_download"
            verify_metadata(target, item)
        archive_record = result["transformers"]
        archive = output / archive_record["filename"]
        require(archive.parent == output, "Archive destination escape")
        source = next((p / archive.name for p in reuse if verify(p / archive.name, archive_record)), None)
        if source is not None:
            shutil.copyfile(source, archive)
        else:
            require(not offline_only, "Pinned archive unavailable offline")
            collector.fetch(archive_record["url"], archive, archive_record)
        require(verify(archive, archive_record), "Archive identity mismatch before source inspection")
        with zipfile.ZipFile(archive) as source_zip:
            for entry in result["source_checks"].values():
                info = source_zip.getinfo(entry["archive_member"])
                require(info.file_size == entry["bytes"], "Official member size drift")
                raw = source_zip.read(info)
                require(hashlib.sha256(raw).hexdigest() == entry["sha256"], "Official source member drift")
        result.update(status="VERIFIED_ARTIFACTS_READY_NOT_INSTALLED", network_acquired_bytes=collector.total,
                      additional_300_second_window_used=False, elapsed_second_window_seconds=None,
                      elapsed_since_first_network_seconds=collector.clock() - collector.started,
                      wheel_metadata_closure_checked=True, installation_executed=False,
                      public_pin_source_sha256=LOCK_SHA256,
                      metadata_closure_basis="Exact reviewed wheel and METADATA bytes, same fixed CPython3.12 Linux x86_64 profile; independent fresh runtime qualifier still required")
        (output / "official_runtime.lock.json").write_bytes(encoded(result))
        (output / "window_extension.json").write_bytes(encoded({"additional_window_used": False, "limit_seconds": 300,
                 "cumulative_body_limit": TOTAL_BODY_LIMIT, "installation_executed": False}))
        print(json.dumps({"status": result["status"], "network_bytes": collector.total,
                          "fresh_lock_sha256": sha(output / "official_runtime.lock.json"), "runtime_ready": False}))
    except BaseException as error:
        (output / "acquisition_failure.json").write_bytes(encoded({"status": "FAILED_ACQUISITION", "error_type": type(error).__name__,
                  "error": str(error), "network_bytes": collector.total, "partial_outputs_preserved": True, "runtime_ready": False}))
        raise
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_alarm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--torch-wheel", required=True, type=Path)
    parser.add_argument("--reuse-directory", action="append", type=Path, default=[])
    parser.add_argument("--offline-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    require(args.execute, "Inspect/review source before explicitly executing acquisition")
    recover(args.lock.resolve(), args.output.resolve(), args.torch_wheel.resolve(),
            [p.resolve() for p in args.reuse_directory], args.offline_only)


if __name__ == "__main__":
    main()
