#!/usr/bin/env python3
"""Install a fresh, fully locked official runtime without network access.

Requires explicit --execute after independent source review. Does not qualify
runtime readiness, run a model, edit a historical receipt, or alter PEP 610.
Uses pip's native verified-download cache and preserves its canonical Link.
Python-level network auditing is defense in depth, not a native OS sandbox.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import stat
import subprocess
import sys
import time
import traceback
import venv
import zipfile

CANONICAL = "https://github.com/huggingface/transformers/archive/42ca97014c85d71a88ad60d55f08cb9fb4d26e2c.zip"
ARCHIVE_SHA256 = "69273c7d563dd207ad4d6ada4ab16105e7c21366ac4142be1e5f53649b23c5e9"
ARCHIVE_PREFIX = "transformers-42ca97014c85d71a88ad60d55f08cb9fb4d26e2c/"
LINKS = {"AGENTS.md": b".ai/AGENTS.md", "CLAUDE.md": b".ai/AGENTS.md",
         "docs/source/en/contributing.md": b"../../../CONTRIBUTING.md",
         "docs/source/en/notebooks.md": b"../../../notebooks/README.md"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path, root):
    path = Path(path).resolve()
    require(path.is_relative_to(root), "Provenance artifact outside current repository")
    return {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": digest(path)}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def verify(path, expected):
    require(not path.is_symlink() and path.is_file(), "Missing or symlinked retained artifact: " + path.name)
    require(path.stat().st_size == expected["bytes"] and digest(path) == expected["sha256"],
            "Retained artifact size/hash mismatch: " + path.name)


def zip_inventory(path, *, official_archive=False):
    """Bound paths, duplicates, special types and uncompressed bytes before use."""
    total = 0
    seen = set()
    links_seen = {}
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        require(len(infos) <= (12000 if official_archive else 16000), "ZIP member count exceeded")
        for info in infos:
            name = info.filename
            require("\\" not in name and "\x00" not in name and not name.startswith("/"), "Unsafe ZIP member")
            parts = PurePosixPath(name).parts
            require(parts and all(p not in {".", "..", ""} for p in parts), "ZIP traversal")
            normalized = "/".join(parts)
            require(normalized not in seen, "Normalized ZIP duplicate")
            seen.add(normalized)
            require(not info.flag_bits & 1, "Encrypted ZIP entry")
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode):
                require(official_archive and name.startswith(ARCHIVE_PREFIX), "Unexpected ZIP symlink")
                relative = name[len(ARCHIVE_PREFIX):]
                require(relative in LINKS and info.file_size == len(LINKS[relative]), "Unexpected upstream link")
                body = archive.read(info)
                require(body == LINKS[relative], "Upstream link payload differs")
                links_seen[relative] = body.decode()
            else:
                require(kind in {0, stat.S_IFREG, stat.S_IFDIR}, "Unexpected ZIP special entry")
            if official_archive:
                require(name.startswith(ARCHIVE_PREFIX), "Unexpected archive root")
                require(info.file_size <= 1024 * 1024, "Unexpected large archive entry")
            total += info.file_size
            require(total <= (128 * 1024 * 1024 if official_archive else 1024 * 1024 * 1024),
                    "ZIP uncompressed size exceeded")
        if official_archive:
            require(links_seen == {k: v.decode() for k, v in LINKS.items()}, "Archive link inventory differs")
            require(len(infos) == 7694 and total == 94957044, "Pinned archive inventory differs")
        return {"members": len(infos), "uncompressed_bytes": total, "allowed_link_mode_entries": links_seen,
                "link_handling": "Pinned pip unzip_file writes these entries as regular files, not symlinks"}


def wrapper_text(python, root):
    # Values inserted through JSON are valid quoted shell strings for these paths.
    import shlex
    return ("#!/usr/bin/env bash\nset -euo pipefail\n"
            'RUNTIME="$(cd "$(dirname "$0")" && pwd)"\n'
            + "ROOT=" + shlex.quote(str(root)) + "\n"
            + 'export PYTHONPATH="$RUNTIME/site-packages:$ROOT/src:$ROOT"\n'
            + "unset PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE LD_PRELOAD LD_LIBRARY_PATH\n"
            + "export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1\n"
            + "export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 ATEN_CPU_CAPABILITY=default\n"
            + "export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1\n"
            + "CPU=\"$(" + shlex.quote(str(python)) + " -S -c 'import os; print(min(os.sched_getaffinity(0)))')\"\n"
            + "exec taskset -c \"$CPU\" " + shlex.quote(str(python)) + ' -S -B "$@"\n')


def install(root, acquisition, runtime, expected_lock_sha256):
    require(sys.version_info[:2] == (3, 12) and sys.flags.no_site, "Invoke verified Python 3.12 with -S")
    root, acquisition, runtime = root.resolve(), acquisition.resolve(), runtime.resolve()
    require((root / "src/heteronpu").is_dir(), "Wrong repository root")
    require(acquisition.is_relative_to(root / "work") and runtime.is_relative_to(root / "work"),
            "Private acquisition/runtime must remain below current repository work")
    require(not runtime.exists(), "Fresh nonexistent runtime required")
    lock_path = acquisition / "official_runtime.lock.json"
    require(digest(lock_path) == expected_lock_sha256, "Reviewed dependency lock SHA mismatch")
    lock = json.loads(lock_path.read_bytes())
    require(lock["status"] == "VERIFIED_ARTIFACTS_READY_NOT_INSTALLED" and
            lock.get("wheel_metadata_closure_checked") is True and lock.get("installation_executed") is False,
            "Acquisition not verified and locked")
    require(len(lock["artifacts"]) == 38 and len({x["name"] for x in lock["artifacts"]}) == 38,
            "Expected complete unique locked artifact set")
    inventories = {}
    for item in lock["artifacts"]:
        path = acquisition / item["relative_path"]
        require(path.resolve().is_relative_to(acquisition), "Acquisition path escape")
        verify(path, item)
        inventories[item["name"]] = zip_inventory(path)
    archive = acquisition / lock["transformers"]["filename"]
    require(lock["transformers"]["url"] == CANONICAL and
            lock["transformers"]["sha256"] == ARCHIVE_SHA256 and lock["transformers"]["bytes"] == 28003985,
            "Canonical archive lock differs")
    verify(archive, lock["transformers"])
    inventories["transformers_archive"] = zip_inventory(archive, official_archive=True)
    with zipfile.ZipFile(archive) as source:
        for entry in lock["source_checks"].values():
            raw = source.read(entry["archive_member"])
            require(len(raw) == entry["bytes"] and hashlib.sha256(raw).hexdigest() == entry["sha256"],
                    "Official source member differs")
    started = time.monotonic()
    runtime.mkdir(parents=True)
    try:
        for name in ("home", "cache", "tmp", "guard", "bootstrap-pip", "site-packages", "verified-downloads", "built-wheels", "provenance", "transformers-stage"):
            (runtime / name).mkdir()
        shutil.copyfile(lock_path, runtime / "dependency_lock.json")
        write_json(runtime / "zip_inventory.json", inventories)
        sources = {"installer_source": Path(__file__).resolve(),
                   "driver_source": Path(__file__).resolve().parent / "pip_qwen35_offline_driver.py",
                   "guard_source": Path(__file__).resolve().parent / "qwen35_runtime_network_guard.py",
                   "backend_runner_source": Path(__file__).resolve().parent / "qwen35_backend_runner.py"}
        for name, source in sources.items():
            shutil.copyfile(source, runtime / "provenance" / source.name)
        shutil.copyfile(sources["guard_source"], runtime / "guard/sitecustomize.py")
        shutil.copyfile(archive, runtime / "verified-downloads" / CANONICAL.rsplit("/", 1)[1])
        pip_item = next(x for x in lock["artifacts"] if x["name"] == "pip")
        require(pip_item["version"] == "26.2.1" and pip_item["installation_role"] == "bootstrap_only", "Pinned pip missing")
        bootstrap = runtime / "bootstrap-pip"
        with zipfile.ZipFile(acquisition / pip_item["relative_path"]) as wheel:
            for info in wheel.infolist():
                target = bootstrap / info.filename
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(wheel.read(info))
        write_json(runtime / "bootstrap_manifest.json", {str(p.relative_to(bootstrap)): record(p, root)
                   for p in sorted(bootstrap.rglob("*")) if p.is_file()})
        venv.EnvBuilder(system_site_packages=False, with_pip=False, symlinks=True).create(runtime / "build-venv")
        python = runtime / "build-venv/bin/python"
        require(python.resolve() == Path(sys.executable).resolve(), "Build interpreter differs")
        local_requirements = []
        for item in lock["artifacts"]:
            if item["installation_role"] != "bootstrap_only":
                local_requirements.append((acquisition / item["relative_path"]).as_uri() + " --hash=sha256:" + item["sha256"])
        (runtime / "local_wheels.lock.txt").write_text("\n".join(local_requirements) + "\n")
        ledger = acquisition / "network.jsonl"
        extension = acquisition / "window_extension.json"
        write_json(runtime / "acquisition.json", {"schema": 1, "status": "VERIFIED_ACQUISITION_REUSED_OFFLINE",
                   "source_lock": record(lock_path, root), "source_ledger": record(ledger, root),
                   "window_extension": record(extension, root), "network_acquired_bytes": lock["network_acquired_bytes"],
                   "duplicate_archive_gets_included": True, "install_network_bytes": 0})
        # Minimal child environment. This does not modify any stored user/proxy/security settings.
        env = {"PATH": str(Path(sys.executable).resolve().parent) + ":/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC"}
        env.update(HOME=str(runtime / "home"), XDG_CACHE_HOME=str(runtime / "cache"),
                   TMPDIR=str(runtime / "tmp"), PYTHONPATH=":".join(map(str, (runtime / "guard", bootstrap, runtime / "site-packages"))),
                   PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PIP_CONFIG_FILE=os.devnull,
                   PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1", QWEN35_RUNTIME_ROOT=str(runtime),
                   ATEN_CPU_CAPABILITY="default", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1")
        driver = runtime / "provenance/pip_qwen35_offline_driver.py"
        for mode in ("wheels", "transformers"):
            command = [str(python), "-I", "-S", "-B", str(driver), "--runtime", str(runtime), "--mode", mode]
            with (runtime / ("install_" + mode + ".log")).open("wb") as log:
                process = subprocess.Popen(command, env=env, cwd=runtime, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    returncode = process.wait(timeout=180)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    # Parent exit does not prove all descendants exited. Always
                    # follow the full grace interval with process-group SIGKILL.
                    time.sleep(5)
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)
                    raise TimeoutError("Offline install stage exceeded 180 seconds; complete child process group terminated")
            require(returncode == 0, "Offline pip " + mode + " failed; preserve log and do not qualify")
        # pip --target cannot merge an existing bin directory safely. Preserve the
        # genuine separate Transformers target and copy only noncolliding files.
        stage, site = runtime / "transformers-stage", runtime / "site-packages"
        merge_records = {}
        for source in sorted(stage.rglob("*")):
            require(not source.is_symlink(), "Unexpected installed Transformers symlink")
            relative = source.relative_to(stage)
            target = site / relative
            if source.is_dir():
                require(not target.exists() or target.is_dir(), "Transformers directory/file collision")
                target.mkdir(parents=True, exist_ok=True)
            else:
                require(not target.exists(), "Transformers file collision; never overwrite prior packages")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                require(digest(source) == digest(target), "Transparent stage copy differs")
                merge_records[str(relative)] = {"source": record(source, root), "installed": record(target, root)}
        require(merge_records and (site / "bin/transformers").is_file(), "Complete Transformers stage merge missing")
        write_json(runtime / "transformers_merge_manifest.json", {"schema": 1, "method": "collision-rejecting file copy; native RECORD and PEP610 bytes unchanged", "files": merge_records})
        built = list((runtime / "tmp").rglob("transformers-5.16.0.dev0-*.whl"))
        require(len(built) == 1, "Exactly one genuine retained built Transformers wheel required")
        shutil.copyfile(built[0], runtime / "built-wheels" / built[0].name)
        origin = built[0].with_name("origin.json")
        require(origin.is_file(), "Native built-wheel origin.json missing")
        shutil.copyfile(origin, runtime / "built-wheels/origin.json")
        direct_paths = list((runtime / "site-packages").glob("transformers-*.dist-info/direct_url.json"))
        require(len(direct_paths) == 1, "Native Transformers direct_url missing")
        direct = json.loads(direct_paths[0].read_bytes())
        require(direct.get("url") == CANONICAL and direct.get("archive_info", {}).get("hashes", {}).get("sha256") == ARCHIVE_SHA256,
                "Native canonical direct_url mismatch; never repair it")
        wrapper = runtime / "python.sh"
        wrapper.write_text(wrapper_text(Path(sys.executable).resolve(), root))
        wrapper.chmod(0o755)
        events = [json.loads(x) for x in (runtime / "network_guard.jsonl").read_text().splitlines()]
        activations = [x for x in events if x["event"] == "guard_activated"]
        require(any(x["parent_driver"] for x in activations) and any(not x["parent_driver"] for x in activations),
                "Parent/backend guard activation not observed")
        require(all(x["allowed"] or (x.get("expected_self_test") is True and x["parent_driver"] is True and x["event"] == "socket.__new__") for x in events), "Unexpected denied network/process attempt; inspect before accepting")
        backend_pids = {x["pid"] for x in events if x["event"] == "backend_entry_verified"}
        spawned_pids = {int(x["detail"]) for x in events if x["event"] == "backend_spawned"}
        require(backend_pids and backend_pids == spawned_pids, "Every backend process must have explicit verified guard activation")
        require(any(x["event"] == "socket_guard_self_test" for x in events) and
                any(x["event"] == "pip_transport_self_test" for x in events), "Negative transport tests missing")
        artifacts = {name: record(runtime / "provenance" / source.name, root) for name, source in sources.items()}
        for name, relative in {"guard_installed": "guard/sitecustomize.py", "bootstrap_manifest": "bootstrap_manifest.json",
                "dependency_lock": "dependency_lock.json", "acquisition_report": "acquisition.json", "zip_inventory": "zip_inventory.json",
                "wheel_install_report": "install_wheels.json", "transformers_install_report": "install_transformers.json",
                "network_guard_log": "network_guard.jsonl", "python_wrapper": "python.sh", "build_venv_config": "build-venv/pyvenv.cfg",
                "wheel_install_log": "install_wheels.log", "transformers_install_log": "install_transformers.log",
                "built_transformers_origin": "built-wheels/origin.json", "local_wheel_requirements": "local_wheels.lock.txt", "transformers_merge_manifest": "transformers_merge_manifest.json"}.items():
            artifacts[name] = record(runtime / relative, root)
        artifacts["built_transformers_wheel"] = record(runtime / "built-wheels" / built[0].name, root)
        artifacts["transformers_direct_url"] = record(direct_paths[0], root)
        checks = {"fresh_runtime": True, "all_inputs_sha_verified_before_use": True, "safe_zip_inventory": True,
                  "pinned_bootstrap_pip": True, "offline_locked_wheel_install_succeeded": True,
                  "canonical_native_cache_transformers_install_succeeded": True, "native_pep610_unmodified": True,
                  "parent_and_backend_audit_guard_observed": True, "no_network_or_unexpected_spawn_observed": True,
                  "native_built_wheel_retained": True, "transformers_stage_merged_without_collision_or_metadata_edits": True}
        receipt = {"schema": 1, "status": "PASS_OFFLINE_LOCKED_INSTALL", "checks": checks, "artifacts": artifacts,
                   "created_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.monotonic() - started,
                   "network_enforcement": {"type": "Python audit plus all pip HTTP transport denied", "native_os_sandbox": False,
                    "install_network_bytes": 0, "guard_activations": activations, "socket_guard_exercised": True,
                    "pip_download_blocked": True, "unexpected_network_attempts": 0, "verified_backend_pids": sorted(backend_pids), "limits": "Does not constrain malicious native code; official sources statically inspected and hash-pinned"},
                   "pip_preparer_hook": "Only sets native download_dir to a fresh verified canonical-filename archive cache; Link/hash/PEP610 unchanged",
                   "trust_boundary": {"host_interpreter": str(Path(sys.executable).resolve()), "sha256": digest(sys.executable),
                    "python": sys.version, "host_stdlib_trusted": True, "complete_os_source_closure": False},
                   "scope": "Installation only, not fresh runtime qualification, capture, replay, numerical PASS, or RTL"}
        write_json(runtime / "runtime_install.json", receipt)
        print(json.dumps({"status": receipt["status"], "runtime": str(runtime), "elapsed_seconds": receipt["elapsed_seconds"]}))
    except BaseException as error:
        write_json(runtime / "installation_failure.json", {"status": "FAILED_OFFLINE_INSTALL", "exception_type": type(error).__name__,
                   "error": str(error), "traceback": traceback.format_exc(), "partial_outputs_preserved": True,
                   "runtime_readiness_claimed": False, "elapsed_seconds": time.monotonic() - started})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--acquisition", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True, help="Independent reviewer-confirmed acquisition lock SHA256")
    parser.add_argument("--execute", action="store_true", help="Required after independent review; performs installation")
    args = parser.parse_args()
    require(args.execute, "Plan only: pass --execute only after source review")
    install(args.root, args.acquisition, args.runtime, args.expected_lock_sha256)


if __name__ == "__main__":
    main()
