#!/usr/bin/env python3
"""Pinned pip driver: native verified-download cache, never edited provenance.

This is an installation program, not a qualifier. It is called only by the
reviewed outer installer after every retained input has been SHA256 checked.
The sole pip preparation hook sets download_dir; the canonical Link, native
hash checking, extraction, wheel building, install report, and PEP 610 writer
remain pip's own code. HTTP fallback is forbidden, not synthesized.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess

CANONICAL = "https://github.com/huggingface/transformers/archive/14e738b5d0cc69aa27a95dde272aea41fde44f2f.zip"
ARCHIVE_SHA256 = "15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d"
PREPARE_SHA256 = "ccb9153120eef5c511d0a9c39b76d9dd0bc879a12b8492abaf5d3d5320cc94a4"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--mode", choices=("wheels", "transformers"), required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    if sys.version_info[:2] != (3, 12) or not sys.flags.no_site or not sys.dont_write_bytecode:
        raise RuntimeError("Python 3.12 with -S is required")
    # No installed host packages. stdlib and interpreter remain measured host trust.
    if any(("site-packages" in p or "dist-packages" in p) and Path(p).resolve() != runtime / "site-packages" for p in sys.path):
        raise RuntimeError("Unexpected ambient site-packages before bootstrap")
    bootstrap, site = runtime / "bootstrap-pip", runtime / "site-packages"
    sys.path[:0] = [str(runtime / "guard"), str(bootstrap), str(site)]
    os.environ["QWEN35_PARENT_GUARD_PID"] = str(os.getpid())
    import sitecustomize  # reviewed Python-level guard, also loaded in PEP517 children
    if not sitecustomize.GUARD_ACTIVE:
        raise RuntimeError("Driver audit guard did not activate")
    sitecustomize.SELF_TEST = True
    try:
        import socket
        try:
            socket.socket()
        except PermissionError:
            sitecustomize.record("socket_guard_self_test", True, "Python socket creation denied before any network")
        else:
            raise RuntimeError("Socket guard self-test failed")
    finally:
        sitecustomize.SELF_TEST = False
    # Only a validated native PEP517 helper invocation gets the explicit runner.
    original_popen = subprocess.Popen
    def explicit_backend_popen(command, *positional, **kwargs):
        helper = bootstrap / "pip/_vendor/pyproject_hooks/_in_process/_in_process.py"
        if not (isinstance(command, (list, tuple)) and len(command) == 4
                and Path(command[0]).resolve() == Path(sys.executable).resolve()
                and Path(command[1]).resolve() == helper.resolve()
                and command[2] in sitecustomize.HOOKS):
            raise RuntimeError("Unexpected subprocess before backend launcher")
        wrapped = [command[0], "-I", "-S", "-B", str(runtime / "provenance/qwen35_backend_runner.py"), *command[1:]]
        process = original_popen(wrapped, *positional, **kwargs)
        sitecustomize.record("backend_spawned", True, str(process.pid))
        return process
    subprocess.Popen = explicit_backend_popen
    import pip
    if pip.__version__ != "26.2.1" or not Path(pip.__file__).resolve().is_relative_to(bootstrap):
        raise RuntimeError("Pinned bootstrap pip identity mismatch")
    # User-agent OS probes are unnecessary in an entirely offline installer.
    from pip._vendor.distro import distro as distro_impl
    distro_impl._distro = distro_impl.LinuxDistribution(include_lsb=False, include_uname=False, include_oslevel=False)
    if distro_impl.version.__globals__["_distro"] is not distro_impl._distro:
        raise RuntimeError("Distro no-probe policy not active")
    import shutil
    if shutil.which("rustc") is not None:
        raise RuntimeError("Unexpected rustc on minimal installer PATH; do not run ancillary probes")
    sitecustomize.record("ancillary_probes_disabled", True, "distro lsb_release/uname/oslevel and rustc subprocess probes suppressed")
    # urllib3's import-time IPv6 loopback probe is irrelevant offline. Suppress
    # only that capability probe; keep every socket audit denial installed.
    connection_path = bootstrap / "pip/_vendor/urllib3/util/connection.py"
    if hashlib.sha256(connection_path.read_bytes()).hexdigest() != "2633bbdb69731e5ccb5cf4e4afd65605d86c7979cc5633126f50c92d5ad74a74":
        raise RuntimeError("Pinned urllib3 capability-probe source changed")
    original_has_ipv6 = socket.has_ipv6
    try:
        socket.has_ipv6 = False
        import pip._vendor.urllib3.util.connection as urllib3_connection
    finally:
        socket.has_ipv6 = original_has_ipv6
    if urllib3_connection.HAS_IPV6 is not False or socket.has_ipv6 is not original_has_ipv6:
        raise RuntimeError("Offline-only IPv6 capability-probe suppression failed")
    sitecustomize.record("ipv6_ancillary_probe_suppressed", True,
                        "Pinned urllib3 imported without IPv6 socket probe; stdlib flag restored; guard unchanged")
    from pip._internal.cli.main import main as pip_main
    from pip._internal.network.session import PipSession
    from pip._internal.operations import prepare
    prepare_path = Path(prepare.__file__)
    if hashlib.sha256(prepare_path.read_bytes()).hexdigest() != PREPARE_SHA256:
        raise RuntimeError("Reviewed pip preparer source differs")

    def forbid_send(self, request, **kwargs):
        raise RuntimeError("Offline installation forbids all pip HTTP transport")
    PipSession.send = forbid_send
    try:
        PipSession.send(None, None)
    except RuntimeError:
        sitecustomize.record("pip_transport_self_test", True, "All HTTP send paths denied without a request")
    else:
        raise RuntimeError("Pip transport self-test failed")
    original_init = prepare.RequirementPreparer.__init__
    if args.mode == "transformers":
        cache = runtime / "verified-downloads"
        archive = cache / (CANONICAL.rsplit("/", 1)[1])
        if archive.stat().st_size != 28738230 or hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
            raise RuntimeError("Verified native-download cache archive differs")
        def with_verified_download_dir(self, **kwargs):
            if kwargs.get("download_dir") is not None:
                raise RuntimeError("Unexpected pre-existing pip download directory")
            kwargs["download_dir"] = str(cache)
            return original_init(self, **kwargs)
        prepare.RequirementPreparer.__init__ = with_verified_download_dir
    common = ["--isolated", "--disable-pip-version-check", "--no-input", "--no-cache-dir",
              "--retries", "0", "--resume-retries", "0", "install", "--no-index", "--no-deps",
              "--require-hashes", "--no-compile", "--no-warn-script-location", "--no-clean",
              "--target", str(site if args.mode == "wheels" else runtime / "transformers-stage")]
    if args.mode == "wheels":
        command = common + ["--only-binary", ":all:", "--report", str(runtime / "install_wheels.json"),
                            "-r", str(runtime / "local_wheels.lock.txt")]
    else:
        command = common + ["--no-build-isolation", "--report", str(runtime / "install_transformers.json"),
                            CANONICAL + "#sha256=" + ARCHIVE_SHA256]
    (runtime / ("pip_" + args.mode + "_argv.json")).write_text(json.dumps(command, indent=2) + "\n")
    return pip_main(command)


if __name__ == "__main__":
    raise SystemExit(main())
