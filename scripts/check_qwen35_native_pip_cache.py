#!/usr/bin/env python3
"""Bounded test of existing verified pip cache semantics, never installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time
import zipfile

CANONICAL = "https://github.com/huggingface/transformers/archive/14e738b5d0cc69aa27a95dde272aea41fde44f2f.zip"
SHA = "15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition", type=Path, required=True)
    parser.add_argument("--existing-pip-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start = time.monotonic()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("30-second cache fixture budget")))
    signal.alarm(30)
    acquisition, output, existing = args.acquisition.resolve(), args.output.resolve(), args.existing_pip_root.resolve()
    if output.exists():
        raise RuntimeError("Fresh fixture output required")
    lock = json.loads((acquisition / "official_runtime.lock.json").read_bytes())
    archive = acquisition / lock["transformers"]["filename"]
    if digest(archive) != SHA or archive.stat().st_size != 28738230:
        raise RuntimeError("Original archive identity differs")
    pip_artifact = next(r for r in lock["artifacts"] if r["name"] == "pip")
    pip_wheel = acquisition / pip_artifact["relative_path"]
    if digest(pip_wheel) != pip_artifact["sha256"]:
        raise RuntimeError("Official pip wheel differs")
    # Existing tool sources only. No installation, backend, or downloaded code import.
    sys.path.insert(0, str(existing))
    import pip
    if pip.__version__ != "26.2.1" or not Path(pip.__file__).resolve().is_relative_to(existing):
        raise RuntimeError("Existing verified pip mismatch")
    output.mkdir(parents=True)
    counters = {"http_send": 0, "subprocess": 0, "downloader": 0, "socket_attempts": 0}
    def deny_audit(event, event_args):
        if event.startswith("socket."):
            counters["socket_attempts"] += 1
            raise RuntimeError("Fixture forbids all network")
    sys.addaudithook(deny_audit)
    def deny_process(*_args, **_kwargs):
        counters["subprocess"] += 1
        raise OSError("Fixture subprocess denied")
    subprocess.Popen = deny_process
    from pip._vendor.distro import distro as distro_impl
    distro_impl._distro = distro_impl.LinuxDistribution(include_lsb=False, include_uname=False, include_oslevel=False)
    if distro_impl.version.__globals__["_distro"] is not distro_impl._distro:
        raise RuntimeError("Distro policy mismatch")
    # PATH has no rustc. Do not weaken the child guard for user-agent probes.
    os.environ["PATH"] = "/usr/bin:/bin"
    if shutil.which("rustc"):
        raise RuntimeError("Unexpected Rust probe possibility")
    import socket
    connection_path = existing / "pip/_vendor/urllib3/util/connection.py"
    if digest(connection_path) != "2633bbdb69731e5ccb5cf4e4afd65605d86c7979cc5633126f50c92d5ad74a74":
        raise RuntimeError("Pinned urllib3 probe source changed")
    original_has_ipv6 = socket.has_ipv6
    try:
        socket.has_ipv6 = False
        import pip._vendor.urllib3.util.connection as urllib3_connection
    finally:
        socket.has_ipv6 = original_has_ipv6
    if urllib3_connection.HAS_IPV6 is not False or socket.has_ipv6 is not original_has_ipv6:
        raise RuntimeError("Probe suppression or stdlib flag restoration failed")
    from pip._internal.network.session import PipSession
    def deny_http(*_args, **_kwargs):
        counters["http_send"] += 1
        raise RuntimeError("Fixture HTTP forbidden")
    PipSession.send = deny_http
    session = PipSession(retries=0, resume_retries=0)
    session.close()
    if counters["subprocess"] or counters["http_send"] or counters["socket_attempts"]:
        raise RuntimeError("PipSession initialization tried an ancillary operation")
    from pip._internal.models.link import Link
    from pip._internal.operations.prepare import get_http_url
    from pip._internal.utils.hashes import Hashes
    from pip._internal.utils.temp_dir import global_tempdir_manager
    def deny_downloader(*_args, **_kwargs):
        counters["downloader"] += 1
        raise RuntimeError("Expected native missing/corrupt cache fallback denied")
    link = Link(CANONICAL + "#sha256=" + SHA)
    checks = {"pip_session_constructed_without_network_or_child": True}
    for case in ("correct", "missing", "corrupt"):
        directory = output / case
        directory.mkdir()
        target = directory / link.filename
        if case == "correct":
            shutil.copyfile(archive, target)
        elif case == "corrupt":
            target.write_bytes(b"known deliberately corrupt private test fixture\n")
        prior_calls = counters["downloader"]
        with global_tempdir_manager():
            try:
                result = get_http_url(link, deny_downloader, str(directory), Hashes({"sha256": [SHA]}))
            except RuntimeError as error:
                if case == "correct" or str(error) != "Expected native missing/corrupt cache fallback denied":
                    raise
                if counters["downloader"] != prior_calls + 1:
                    raise RuntimeError("Expected exactly one denied cache fallback")
                checks[case + "_cache_fails_closed"] = True
            else:
                if case != "correct" or counters["downloader"] != prior_calls or digest(result.path) != SHA:
                    raise RuntimeError("Cache hit did not preserve native verified bytes")
                checks["correct_cache_hit_zero_downloader_calls"] = True
    checks["original_acquisition_unchanged"] = digest(archive) == SHA
    checks["zero_http_socket_and_subprocess"] = counters["http_send"] == counters["subprocess"] == counters["socket_attempts"] == 0
    checks["ipv6_probe_suppressed_and_stdlib_flag_restored"] = socket.has_ipv6 is original_has_ipv6 and urllib3_connection.HAS_IPV6 is False
    sources = {}
    with zipfile.ZipFile(pip_wheel) as wheel:
        for name, module in sorted(sys.modules.items()):
            file = getattr(module, "__file__", None)
            if not name.startswith("pip") or not file:
                continue
            path = Path(file).resolve()
            if not path.is_relative_to(existing):
                raise RuntimeError("Pip module outside reviewed existing tool path")
            relative = str(path.relative_to(existing))
            raw = path.read_bytes()
            if raw != wheel.read(relative):
                raise RuntimeError("Imported existing pip source differs from official wheel: " + relative)
            sources[relative] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    result = {"schema": 1, "status": "PASS_NATIVE_PIP_CACHE_FIXTURE" if all(checks.values()) else "FAIL_CACHE_FIXTURE",
              "checks": checks, "counters": counters, "existing_pip_source_checks": sources,
              "source": {"bytes": Path(__file__).stat().st_size, "sha256": digest(__file__)},
              "official_pip_wheel_sha256": pip_artifact["sha256"], "archive_sha256": SHA,
              "limits": {"wall_seconds": 30, "cpu_seconds": 30, "address_space_bytes": 512 * 1024 * 1024, "cpus": 1},
              "elapsed_seconds": time.monotonic() - start, "installation_executed": False,
              "backend_executed": False, "model_executed": False, "network_executed": False}
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "checks", "counters", "elapsed_seconds")}))
    signal.alarm(0)


if __name__ == "__main__":
    main()
