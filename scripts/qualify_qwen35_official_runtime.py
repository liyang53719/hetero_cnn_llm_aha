#!/usr/bin/env python3
"""Qualify a fresh, already installed Qwen3.5 reference runtime, without networking.

Invoke ONLY through the new runtime's python.sh, in a fresh process:
  RUNTIME/python.sh -B scripts/qualify_qwen35_official_runtime.py \
      --root ROOT --runtime RUNTIME --artifact-root ACQUISITION_DIRECTORY \
      --expected-lock-sha256 INDEPENDENTLY_REVIEWED_LOCK_SHA256

This program never installs packages, downloads models, constructs model layers,
loads weights, captures tensors, or runs reference/candidate numerical work.
Readiness proves the measured Python-package scope, NOT complete interpreter/OS
provenance or numerical correctness. Failed attempts are retained and never
create runtime_receipt.json. Existing qualification output is never overwritten.
All imports at module scope are standard-library only, enabling fixture tests.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import importlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import stat
import sys
import sysconfig
import time
import traceback
from urllib.parse import urlsplit
import zipfile

REVISION = "14e738b5d0cc69aa27a95dde272aea41fde44f2f"
ARCHIVE_URL = "https://github.com/huggingface/transformers/archive/" + REVISION + ".zip"
ARCHIVE_SHA256 = "15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d"
TORCH_SHA256 = "ee40b8a4b4b2cf0670c6fd4f35a7ef23871af956fecb238fbf5da15a72650b1d"
PIP_SHA256 = "71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e"
TORCH_COMMIT = "449b1768410104d3ed79d3bcfe4ba1d65c7f22c0"
SOURCE_PINS = {
    "cache_utils.py": (107721, "abdcb0ae88aa5b924ef7d76879db680e9af8f3ec1dafbba7ce446ecb521a944b"),
    "masking_utils.py": (80642, "af3d84dfe82a0b57c40625c89fb32b2cd6bf7351432ee5e76a9e8eac4289575b"),
    "models/qwen3_5/modeling_qwen3_5.py": (88051, "aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18"),
    "models/qwen3_5/configuration_qwen3_5.py": (8281, "2f26c4bb911772d42a5f16e82bdea4b9ba1ac07872df527ec228622d35f3c30e"),
}
SOURCE_SYMLINKS = {
    "transformers-" + REVISION + "/" + name: payload for name, payload in {
        "AGENTS.md": b".ai/AGENTS.md", "CLAUDE.md": b".ai/AGENTS.md",
        "docs/source/en/contributing.md": b"../../../CONTRIBUTING.md",
        "docs/source/en/notebooks.md": b"../../../notebooks/README.md",
    }.items()
}
SCOPE = "FRESH_ISOLATED_PINNED_PYTHON_RUNTIME_ONLY"
REQUIRED_CHECKS = frozenset({
    "python312", "no_site_or_user_site", "clean_sys_path", "preimport_environment",
    "one_cpu_affinity", "lock_and_retained_artifacts", "offline_install_evidence",
    "exact_distribution_set", "installed_record_integrity", "locked_wheel_payloads",
    "official_transformers_payload", "canonical_direct_url", "python_and_wheel_compatibility",
    "actual_metadata_dependency_closure", "import_origins", "pinned_versions",
    "qualification_network_process_guard",
    "torch_default_dispatch", "torch_one_thread", "deterministic_highest_no_autocast",
    "installed_tree_unchanged", "provenance_unchanged",
})
FIXED_ARTIFACTS = frozenset({
    "python_wrapper", "qualifier_source", "dependency_lock", "acquisition_report",
    "pip_wheels_report", "pip_transformers_report", "installer_report",
    "installer_source", "pip_driver_source", "network_guard_source", "backend_runner_source",
    "transformers_archive", "interpreter_manifest", "installed_manifest", "qualification_output",
})
THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalized(name):
    require(isinstance(name, str) and bool(name), "missing distribution name")
    return re.sub(r"[-_.]+", "-", name).lower()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs)


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def safe_relative(value):
    require(isinstance(value, str) and value and "\\" not in value and "\x00" not in value, "invalid relative path")
    p = PurePosixPath(value)
    require(not p.is_absolute() and all(x not in ("", ".", "..") for x in value.split("/")),
            "unsafe relative path: " + value)
    return p


def bounded_file(root, path):
    root, path = Path(root).resolve(), Path(path).absolute()
    require(path.is_relative_to(root), "file outside repository root: " + str(path))
    current = path
    while current != root:
        require(not current.is_symlink(), "symlink in artifact path: " + str(current))
        current = current.parent
    require(path.is_file() and path.resolve().is_relative_to(root), "missing/escaped artifact: " + str(path))
    return path.resolve()


def file_record(root, path):
    path = bounded_file(root, path)
    before = path.stat()
    value = {"path": str(path.relative_to(Path(root).resolve())), "bytes": before.st_size, "sha256": digest(path)}
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "file changed while hashing: " + str(path))
    return value


def verify_record(root, record):
    require(type(record) is dict and type(record.get("bytes")) is int and record["bytes"] >= 0,
            "invalid measured artifact record")
    safe_relative(record.get("path"))
    require(isinstance(record.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", record["sha256"]),
            "invalid artifact digest")
    actual = file_record(root, Path(root) / record["path"])
    require(actual == {key: record[key] for key in actual}, "artifact bytes/hash drift: " + record["path"])
    return actual


def write_new(path, value):
    raw = encoded(value)
    with Path(path).open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    # Immutability is a no-overwrite program contract, not an OS security claim.


def zip_members(archive, source_archive=False):
    result, normalized_names = {}, set()
    for info in archive.infolist():
        name = info.filename.rstrip("/")
        safe_relative(name)
        require(name not in normalized_names, "duplicate ZIP member: " + info.filename)
        normalized_names.add(name)
        if stat.S_ISLNK(info.external_attr >> 16):
            expected = SOURCE_SYMLINKS.get(name)
            require(source_archive and expected is not None and archive.read(info) == expected,
                    "unapproved symlink ZIP member: " + name)
        require(stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK),
                "special ZIP member: " + name)
        require(not info.flag_bits & 1, "encrypted ZIP member: " + name)
        result[info.filename] = info
    return result


def hash_stream(handle):
    h, count = hashlib.sha256(), 0
    while chunk := handle.read(1024 * 1024):
        h.update(chunk)
        count += len(chunk)
    return count, h.hexdigest()


def verify_direct_url(value):
    require(type(value) is dict and value.get("url") == ARCHIVE_URL and
            value.get("archive_info", {}).get("hashes", {}).get("sha256") == ARCHIVE_SHA256,
            "Transformers requires pip-native canonical archive URL and SHA256")
    require("dir_info" not in value and "vcs_info" not in value, "editable/VCS provenance is not canonical archive provenance")


def require_checks(checks):
    require(type(checks) is dict and set(checks) == REQUIRED_CHECKS and
            all(type(v) is bool and v for v in checks.values()), "missing, false, or nonboolean qualification check")


def validate_receipt(receipt):
    require(receipt.get("status") == "PASS_ISOLATED_PINNED_RUNTIME_READY" and receipt.get("scope") == SCOPE,
            "runtime receipt identity mismatch")
    require_checks(receipt.get("checks"))
    artifacts = receipt.get("artifacts")
    require(type(artifacts) is dict and FIXED_ARTIFACTS <= set(artifacts), "missing required runtime artifacts")
    require(all(any(k.startswith(prefix) for k in artifacts) for prefix in ("wheel:", "installed:", "bootstrap:")),
            "missing measured package/native/bootstrap inventory")
    require(receipt.get("complete_environment_closure") is False and
            receipt.get("official_capture_executed") is False and receipt.get("numerical_pass") is False and
            receipt.get("rtl_executed") is False, "runtime readiness scope overclaim")


def inventory_site(root, site):
    result = {}
    for path in sorted(site.rglob("*")):
        require(not path.is_symlink(), "installed symlink: " + str(path))
        if path.is_file():
            require(path.suffix not in (".pyc", ".pyo"), "bytecode present; install with --no-compile: " + str(path))
            require((path.suffix != ".pth" or path.relative_to(site).as_posix() == "distutils-precedence.pth") and
                    not path.name.endswith(".egg-link"), "unexpected path/code-injection artifact: " + str(path))
            result[str(path.relative_to(site))] = file_record(root, path)
    require(bool(result), "empty installed tree")
    return result


def distribution_inventory(site):
    # Nested vendored *.dist-info are payload, NOT independent installed packages.
    result = {}
    for folder in sorted(site.glob("*.dist-info")):
        require(folder.is_dir() and not folder.is_symlink(), "invalid dist-info")
        dist = importlib.metadata.PathDistribution(folder)
        name = normalized(dist.metadata.get("Name"))
        require(name not in result, "duplicate top-level distribution: " + name)
        require((folder / "RECORD").is_file(), "missing installed RECORD: " + name)
        result[name] = (dist, folder)
    require(bool(result) and not list(site.glob("*.egg-info")), "missing distributions or unsupported egg-info")
    return result


def verify_installed_records(root, site, distributions, inventory):
    owners = {}
    for name, (dist, folder) in distributions.items():
        seen = set()
        for row in csv.reader(io.StringIO((folder / "RECORD").read_text())):
            require(len(row) == 3, "malformed RECORD row: " + name)
            relative, hashed, size = row
            # Native pip --target retains the temporary prefix's ../../bin
            # spelling in RECORD while moving scripts into TARGET/bin. Never
            # resolve that spelling against the live filesystem or edit RECORD.
            if relative.startswith("../../bin/"):
                script = relative.removeprefix("../../bin/")
                require(PurePosixPath(script).name == script and script not in ("", ".", ".."),
                        "invalid pip target script relocation")
                relative = "bin/" + script
            elif relative.startswith("../../share/"):
                relative = relative.removeprefix("../../")
            safe_relative(relative)
            require(relative not in seen and relative in inventory, "duplicate/unowned/missing installed RECORD file: " + relative)
            seen.add(relative)
            require(relative not in owners, "file shared by distributions: " + relative)
            owners[relative] = name
            record = inventory[relative]
            if hashed:
                algorithm, separator, value = hashed.partition("=")
                require(separator and algorithm == "sha256", "unsupported RECORD digest: " + relative)
                expected = base64.urlsafe_b64encode(bytes.fromhex(record["sha256"])).rstrip(b"=").decode()
                require(value == expected and size == str(record["bytes"]), "installed RECORD mismatch: " + relative)
            else:
                require(relative == str((folder / "RECORD").relative_to(site)) and size == "",
                        "unhashed installed file other than RECORD: " + relative)
    require(set(owners) == set(inventory), "unowned files in installed tree: " + repr(sorted(set(inventory) - set(owners))[:10]))
    return owners


def wheel_target(member):
    parts = PurePosixPath(member).parts
    if len(parts) >= 3 and parts[0].endswith(".data"):
        require(parts[1] in ("purelib", "platlib", "scripts", "data"), "unsupported wheel data location: " + member)
        require(parts[1] != "data" or parts[2] == "share", "unsupported wheel data payload: " + member)
        return "/".join(((["bin"] if parts[1] == "scripts" else []) + list(parts[2:])))
    return member


def verify_wheel_payload(path, name, site, inventory, owners, installed_metadata):
    matched = set()
    with zipfile.ZipFile(path) as archive:
        members = zip_members(archive)
        metadata = [n for n in members if len(PurePosixPath(n).parts) == 2 and n.endswith(".dist-info/METADATA")]
        require(len(metadata) == 1, "wheel has ambiguous metadata: " + name)
        raw = archive.read(metadata[0])
        message = BytesParser().parsebytes(raw)
        require(normalized(message["Name"]) == name, "wheel metadata name mismatch")
        require(raw == installed_metadata.read_bytes(), "installed metadata differs from pinned wheel: " + name)
        for member, info in members.items():
            if info.is_dir() or member == str(PurePosixPath(metadata[0]).parent / "RECORD"):
                continue
            target = wheel_target(member)
            require(target in inventory and owners.get(target) == name, "missing/reassigned wheel payload: " + target)
            # pip is permitted to rewrite only the leading shebang of wheel scripts.
            if ".data/scripts/" in member:
                expected = archive.read(member).split(b"\n", 1)
                actual = (site / target).read_bytes().split(b"\n", 1)
                require(len(expected) == len(actual) == 2 and expected[0].startswith(b"#!") and
                        actual[0].startswith(b"#!") and expected[1] == actual[1], "wheel script content drift: " + target)
            else:
                with archive.open(member) as handle:
                    size, sha = hash_stream(handle)
                require((size, sha) == (inventory[target]["bytes"], inventory[target]["sha256"]),
                        "installed payload differs from pinned wheel: " + target)
            matched.add(target)
    return matched


def verify_entrypoint_script(path, entrypoint, executable):
    """Exact Linux launcher emitted by the fixed pip 26.2.1 template."""
    executable = str(executable).encode()
    require(b" " not in executable and b"'" not in executable and b"\n" not in executable,
            "unsupported launcher interpreter spelling")
    if len(executable) + 3 <= 127:
        shebang = b"#!" + executable + b"\n"
    else:
        shebang = b"#!/bin/sh\n'''exec' " + executable + b' "$0" "$@"\n' + b"' '''\n"
    require(entrypoint.attr is not None, "missing entrypoint callable")
    template = ("import sys\nfrom %(module)s import %(import_name)s\n"
                "if __name__ == '__main__':\n"
                "    sys.argv[0] = sys.argv[0].removesuffix('.exe')\n"
                "    sys.exit(%(func)s())\n")
    body = (template % {"module": entrypoint.module, "import_name": entrypoint.attr.split(".")[0],
                        "func": entrypoint.attr}).encode()
    require(Path(path).read_bytes() == shebang + body,
            "generated entrypoint differs from pinned pip template: " + str(path))


def verify_source_payload(archive_path, site, inventory):
    prefix = "transformers-" + REVISION + "/src/transformers/"
    installed = {key for key in inventory if key.startswith("transformers/")}
    matched = set()
    with zipfile.ZipFile(archive_path) as archive:
        members = zip_members(archive, source_archive=True)
        for key in installed:
            member = prefix + key.removeprefix("transformers/")
            require(member in members and not members[member].is_dir(), "installed Transformers file absent from pinned source: " + key)
            with archive.open(member) as handle:
                size, sha = hash_stream(handle)
            require((size, sha) == (inventory[key]["bytes"], inventory[key]["sha256"]), "Transformers source payload drift: " + key)
            matched.add(key)
    require(bool(matched), "empty Transformers installed source")
    for relative, expected in SOURCE_PINS.items():
        actual = inventory.get("transformers/" + relative, {})
        require((actual.get("bytes"), actual.get("sha256")) == expected, "fixed official source identity mismatch: " + relative)
    return matched


def dependency_closure(distributions, wheel_records):
    # This import is delayed until packaging's installed bytes match its pinned wheel.
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.tags import sys_tags
    from packaging.utils import parse_wheel_filename
    from packaging.version import Version
    environment = default_environment()
    tags = set(sys_tags())
    for record in wheel_records:
        _, _, _, available_tags = parse_wheel_filename(record["filename"])
        require(bool(tags & available_tags), "wheel incompatible with current interpreter: " + record["filename"])
    extras = {name: {""} for name in distributions}
    rows = []
    for name, (dist, _) in distributions.items():
        required_python = dist.metadata.get("Requires-Python")
        require(not required_python or Version(platform.python_version()) in SpecifierSet(required_python),
                "Requires-Python conflict: " + name)
    while True:
        changed = False
        rows = []
        for name, (dist, _) in distributions.items():
            for raw in dist.requires or []:
                requirement = Requirement(raw)
                active = requirement.marker is None or any(requirement.marker.evaluate(dict(environment, extra=extra)) for extra in extras[name])
                if not active:
                    continue
                target = normalized(requirement.name)
                require(requirement.url is None, "undeclared direct dependency URL: " + raw)
                require(target in distributions, "missing dependency: " + name + " requires " + raw)
                installed = distributions[target][0]
                require(Version(installed.version) in requirement.specifier, "dependency version conflict: " + name + " requires " + raw)
                provided = {normalized(x) for x in installed.metadata.get_all("Provides-Extra", [])}
                requested = {normalized(x) for x in requirement.extras}
                require(requested <= provided, "dependency requests missing extras: " + raw)
                if not requested <= extras[target]:
                    extras[target].update(requested)
                    changed = True
                rows.append({"from": name, "requirement": raw, "to": target, "installed": installed.version})
        if not changed:
            break
    return {"environment": environment, "activated_extras": {k: sorted(v - {""}) for k, v in extras.items()}, "requirements": rows}


def audit_paths(root, runtime):
    site = runtime / "site-packages"
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    stdlib_zip = stdlib.parent / ("python%d%d.zip" % sys.version_info[:2])
    allowed = {site, root, root / "src", Path(__file__).resolve().parent, stdlib, stdlib / "lib-dynload", stdlib_zip}
    require(all(p and Path(p).resolve() in allowed for p in sys.path), "unexpected sys.path entry: " + repr(sys.path))
    require(sys.path.count(str(site)) == 1, "isolated site path absent/duplicated")
    expected_pythonpath = [str(site), str(root / "src"), str(root)]
    require(os.environ.get("PYTHONPATH", "").split(os.pathsep) == expected_pythonpath, "PYTHONPATH differs from exact wrapper contract")
    for path in sys.path:
        p = Path(path).resolve()
        require(not any(part in ("site-packages", "dist-packages") for part in p.parts) or p == site, "host site leakage")
    return stdlib


def is_qualifier_main_alias(name, module, path):
    # multiprocessing installs this alias even when it never starts a child.
    return (name in ("__main__", "__mp_main__") and module is sys.modules.get("__main__") and
            Path(path).resolve() == Path(__file__).resolve())


def audit_modules(root, runtime, stdlib):
    modules = {}
    for name, module in sorted(sys.modules.items()):
        if module is None:
            continue
        paths = []
        # Do not trigger lazy-module __getattr__ while auditing paths.
        origin = vars(module).get("__file__")
        if origin:
            paths.append(origin)
        paths.extend(list(vars(module).get("__path__", [])))
        for value in paths:
            p = Path(value).resolve()
            isolated = p.is_relative_to(runtime / "site-packages")
            standard = p.is_relative_to(stdlib) and not any(x in ("site-packages", "dist-packages") for x in p.parts)
            own = is_qualifier_main_alias(name, module, p)
            require(isolated or standard or own, "module imported outside isolated packages/stdlib: " + name + " -> " + str(p))
        if origin and Path(origin).is_file():
            modules[name] = str(Path(origin).resolve())
    return modules


def audit_native_libraries(root, runtime, inventory):
    """Measure Linux mapped binaries; system libraries remain explicit trust."""
    paths = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or not fields[5].startswith("/"):
            continue
        require(not fields[5].endswith(" (deleted)"), "deleted mapped binary cannot be qualified")
        paths.add(Path(fields[5].replace(r"\040", " ")).resolve())
    result = {}
    site = runtime / "site-packages"
    system_roots = tuple(Path(x).resolve() for x in ("/usr/lib", "/usr/lib64", "/lib", "/lib64"))
    interpreter_root = Path(sys.base_prefix).resolve()
    for path in sorted(paths):
        if path.is_relative_to(site):
            relative = str(path.relative_to(site))
            require(relative in inventory, "loaded native binary absent from installed inventory")
            require(file_record(root, path) == inventory[relative], "loaded native binary changed")
            result[str(path)] = dict(inventory[relative], boundary="pinned_runtime_package")
        else:
            require(not any(x in ("site-packages", "dist-packages") for x in path.parts), "host native package leaked")
            require(path == Path(sys.executable).resolve() or path.is_relative_to(interpreter_root) or
                    any(path.is_relative_to(base) for base in system_roots), "unexpected external mapped binary: " + str(path))
            require(path.is_file(), "mapped binary missing")
            result[str(path)] = {"bytes": path.stat().st_size, "sha256": digest(path),
                                 "boundary": "trusted_existing_interpreter_or_OS_not_source_closed"}
    require(bool(result), "no measured native process map")
    return result


def verify_pip_report(report, expected):
    require(type(report.get("install")) is list and report["install"], "empty native pip report")
    actual = {}
    for item in report["install"]:
        metadata = item.get("metadata", {})
        name = normalized(metadata.get("name"))
        require(name not in actual, "duplicate pip report distribution: " + name)
        actual[name] = item
    require(set(actual) == set(expected), "native pip report package set mismatch")
    for name, record in expected.items():
        item = actual[name]
        require(item["metadata"].get("version") == record["version"], "pip report version drift: " + name)
        require(item.get("download_info", {}).get("archive_info", {}).get("hashes", {}).get("sha256") == record["sha256"],
                "pip report archive SHA mismatch: " + name)
    return actual


def verify_network_evidence(events, enforcement):
    """Recheck measured guard probes and every backend PID, not report booleans."""
    require(type(events) is list and bool(events), "empty guard ledger")
    allowed_events = {"guard_activated", "socket.__new__", "socket_guard_self_test", "pip_transport_self_test",
                      "ancillary_probes_disabled", "ipv6_ancillary_probe_suppressed", "subprocess.Popen",
                      "backend_spawned", "backend_entry_verified"}
    for event in events:
        require(type(event.get("pid")) is int and event["pid"] > 0 and
                type(event.get("parent_driver")) is bool and event.get("event") in allowed_events and
                type(event.get("allowed")) is bool and type(event.get("expected_self_test")) is bool,
                "invalid/unexpected guard event")
        probe = event["event"] in ("socket.__new__", "socket_guard_self_test")
        require(event["expected_self_test"] is probe and
                event["allowed"] is (event["event"] != "socket.__new__"),
                "unexpected denial or mislabeled self-test")
        if event["event"] not in ("guard_activated", "backend_entry_verified"):
            require(event["parent_driver"], "unexpected backend operation")
        if event["event"] == "backend_entry_verified":
            require(not event["parent_driver"], "backend verification attributed to parent")
    activations = [e for e in events if e["event"] == "guard_activated"]
    parents = {e["pid"] for e in activations if e["parent_driver"]}
    children = {e["pid"] for e in activations if not e["parent_driver"]}
    require(len(parents) == 2 and len(activations) == len(parents) + len(children),
            "exactly two distinct guarded installer phases required")
    for pid in parents:
        owned = [e for e in events if e["pid"] == pid]
        names = [e["event"] for e in owned]
        require(names[0] == "guard_activated" and all(names.count(name) == 1 for name in
                ("socket.__new__", "socket_guard_self_test", "pip_transport_self_test", "ancillary_probes_disabled",
                 "ipv6_ancillary_probe_suppressed")) and
                names.index("socket.__new__") < names.index("socket_guard_self_test") and
                names.index("ancillary_probes_disabled") < names.index("ipv6_ancillary_probe_suppressed") <
                names.index("pip_transport_self_test"),
                "missing/duplicate/misordered negative guard probe")
    spawned = [int(e["detail"]) for e in events if e["event"] == "backend_spawned"]
    verified = [e["pid"] for e in events if e["event"] == "backend_entry_verified"]
    require(children and len(spawned) == len(set(spawned)) and len(verified) == len(set(verified)) and
            set(spawned) == set(verified) == children and
            sum(e["event"] == "subprocess.Popen" for e in events) == len(spawned),
            "spawned/activated/verified backend PID sets differ")
    require(enforcement.get("native_os_sandbox") is False and enforcement.get("install_network_bytes") == 0 and
            enforcement.get("socket_guard_exercised") is True and enforcement.get("pip_download_blocked") is True and
            enforcement.get("unexpected_network_attempts") == 0 and enforcement.get("guard_activations") == activations and
            enforcement.get("verified_backend_pids") == sorted(children), "guard summary contradicts measured ledger")
    return {"parent_pids": sorted(parents), "verified_backend_pids": sorted(children), "socket_denial_probes": len(parents)}


def qualify(args, output):
    root, runtime, artifact_root = (Path(x).resolve() for x in (args.root, args.runtime, args.artifact_root))
    site = runtime / "site-packages"
    checks = {name: False for name in REQUIRED_CHECKS}
    artifacts = {}
    def forbid_network_or_child(event, arguments):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn",
                                                    "os.spawn", "os.fork", "os.forkpty"}:
            raise PermissionError("Runtime qualification never performs networking or launches subprocesses: " + event)
    sys.addaudithook(forbid_network_or_child)
    checks["qualification_network_process_guard"] = True
    def add(name, path):
        require(name not in artifacts, "duplicate artifact label: " + name)
        artifacts[name] = file_record(root, path)
    require(runtime.is_relative_to(root / "work") and artifact_root.is_relative_to(root), "runtime/acquisition root outside current repository")
    require(sys.version_info[:2] == (3, 12) and platform.python_implementation() == "CPython" and sys.byteorder == "little", "CPython 3.12 little-endian required")
    checks["python312"] = True
    require(sys.flags.no_site == 1 and sys.flags.no_user_site == 1 and sys.dont_write_bytecode,
            "wrapper must use -S, PYTHONNOUSERSITE=1 and -B")
    require("sitecustomize" not in sys.modules and "usercustomize" not in sys.modules, "startup customizations were imported")
    checks["no_site_or_user_site"] = True
    stdlib = audit_paths(root, runtime)
    checks["clean_sys_path"] = True
    require(not any(name in sys.modules for name in ("torch", "numpy", "transformers")), "numerical packages imported before preflight")
    require(os.environ.get("ATEN_CPU_CAPABILITY") == "default" and all(os.environ.get(k) == "1" for k in THREAD_ENV), "thread/DEFAULT policy missing before import")
    require(os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1", "offline model policy missing")
    require(not os.environ.get("PYTHONHOME") and not os.environ.get("LD_PRELOAD"), "ambient interpreter/native injection setting")
    checks["preimport_environment"] = True
    affinity = sorted(os.sched_getaffinity(0))
    require(len(affinity) == 1, "wrapper must pin exactly one allowed CPU before import")
    checks["one_cpu_affinity"] = True
    fixed = {
        "python_wrapper": runtime / "python.sh", "qualifier_source": Path(__file__),
        "dependency_lock": runtime / "dependency_lock.json", "acquisition_report": runtime / "acquisition.json",
        "pip_wheels_report": runtime / "install_wheels.json", "pip_transformers_report": runtime / "install_transformers.json",
        "installer_report": runtime / "runtime_install.json", "installer_source": root / "scripts/install_qwen35_official_runtime.py",
        "pip_driver_source": root / "scripts/pip_qwen35_offline_driver.py", "network_guard_source": runtime / "guard/sitecustomize.py",
        "backend_runner_source": root / "scripts/qwen35_backend_runner.py",
    }
    for name, path in fixed.items():
        add(name, path)
    lock, install = read_json(fixed["dependency_lock"]), read_json(fixed["installer_report"])
    require(re.fullmatch(r"[0-9a-f]{64}", args.expected_lock_sha256 or "") and
            artifacts["dependency_lock"]["sha256"] == args.expected_lock_sha256,
            "dependency lock differs from independently reviewed SHA256")
    require(lock.get("schema") == 1 and lock.get("python") == "3.12", "dependency lock schema/interpreter drift")
    locked = lock.get("artifacts")
    require(type(locked) is list and bool(locked), "empty dependency lock")
    wheel_records, wheel_paths = {}, {}
    for record in locked:
        name = normalized(record.get("name"))
        require(name not in wheel_records and record.get("filename", "").endswith(".whl"), "duplicate/non-wheel lock artifact")
        require(record.get("installation_role") == "bootstrap_only" if name == "pip" else
                record.get("installation_role") in ("runtime", "runtime_and_backend"), "unexpected locked installation role")
        safe_relative(record["filename"])
        relative = record.get("relative_path", "wheels/" + record["filename"])
        safe_relative(relative)
        path = artifact_root / relative
        actual = file_record(root, path)
        require(actual["bytes"] == record.get("bytes") and actual["sha256"] == record.get("sha256"), "locked wheel identity mismatch: " + name)
        url = urlsplit(record.get("url", ""))
        require(url.scheme == "https" and not url.username and not url.password and not url.query and not url.fragment and
                url.hostname in ("files.pythonhosted.org", "download.pytorch.org"), "nonofficial wheel origin")
        wheel_records[name], wheel_paths[name] = record, path
        add("wheel:" + name, path)
    require(wheel_records.get("torch", {}).get("version") == "2.10.0+cpu" and wheel_records["torch"]["sha256"] == TORCH_SHA256 and
            wheel_records.get("numpy", {}).get("version") == "2.3.5", "fixed Torch/NumPy lock drift")
    transformer = lock.get("transformers", {})
    require(transformer.get("url") == ARCHIVE_URL and transformer.get("sha256") == ARCHIVE_SHA256, "fixed Transformers lock drift")
    safe_relative(transformer.get("filename"))
    archive = artifact_root / transformer["filename"]
    add("transformers_archive", archive)
    require(artifacts["transformers_archive"]["bytes"] == transformer.get("bytes") and artifacts["transformers_archive"]["sha256"] == ARCHIVE_SHA256, "Transformers archive identity mismatch")
    checks["lock_and_retained_artifacts"] = True
    require(install.get("schema") == 1 and install.get("status") == "PASS_OFFLINE_LOCKED_INSTALL", "offline installation not verified successful")
    install_checks = install.get("checks")
    require(type(install_checks) is dict and install_checks and all(type(v) is bool and v for v in install_checks.values()), "missing/failed installer checks")
    provenance = install.get("artifacts")
    require(type(provenance) is dict and provenance, "missing measured installation provenance")
    for name, record in provenance.items():
        artifacts["install_provenance:" + name] = verify_record(root, record)
        require((root / record["path"]).is_relative_to(runtime), "installation provenance belongs to another runtime")
    require(all(any(r["bytes"] == artifacts[name]["bytes"] and r["sha256"] == artifacts[name]["sha256"] for r in provenance.values())
                for name in ("installer_source", "pip_driver_source", "network_guard_source", "backend_runner_source", "dependency_lock")),
            "installation provenance not bound to exact installer/driver/guard/lock")
    acquisition = read_json(fixed["acquisition_report"])
    require(acquisition.get("status") == "VERIFIED_ACQUISITION_REUSED_OFFLINE" and
            acquisition.get("install_network_bytes") == 0, "acquisition report identity mismatch")
    for name in ("source_lock", "source_ledger", "window_extension"):
        artifacts["acquisition_provenance:" + name] = verify_record(root, acquisition.get(name))
    require(artifacts["acquisition_provenance:source_lock"]["sha256"] == args.expected_lock_sha256,
            "acquisition source lock differs from reviewed install lock")
    trust = install.get("trust_boundary", {})
    require(trust.get("sha256") == digest(sys.executable) and trust.get("python") == sys.version and
            trust.get("host_stdlib_trusted") is True and trust.get("complete_os_source_closure") is False,
            "interpreter changed since installation or installation overclaims closure")
    enforcement = install.get("network_enforcement", {})
    guard_record = provenance.get("network_guard_log")
    require(type(guard_record) is dict, "missing guard event ledger")
    guard_events = [json.loads(line) for line in (root / guard_record["path"]).read_text().splitlines()]
    network_checks = verify_network_evidence(guard_events, enforcement)
    # Bootstrap is an exact pinned artifact, never an unnamed host-pip exception.
    require(wheel_records.get("pip", {}).get("version") == "26.2.1" and
            wheel_records["pip"]["sha256"] == PIP_SHA256 and
            wheel_records["pip"].get("installation_role") == "bootstrap_only", "fixed pinned bootstrap pip identity absent")
    bootstrap = runtime / "bootstrap-pip"
    with zipfile.ZipFile(wheel_paths["pip"]) as z:
        members = zip_members(z)
        expected = {n for n, info in members.items() if not info.is_dir()}
        actual_files = {str(p.relative_to(bootstrap)) for p in bootstrap.rglob("*") if p.is_file()}
        require(actual_files == expected, "bootstrap pip extraction set drift")
        for member in sorted(expected):
            add("bootstrap:" + member, bootstrap / member)
            with z.open(member) as handle:
                length, sha = hash_stream(handle)
            require((length, sha) == (artifacts["bootstrap:" + member]["bytes"], artifacts["bootstrap:" + member]["sha256"]), "bootstrap pip byte drift")
    checks["offline_install_evidence"] = True
    inventory = inventory_site(root, site)
    distributions = distribution_inventory(site)
    expected_distributions = set(wheel_records) - {"pip"} | {"transformers"}
    require(set(distributions) == expected_distributions, "installed distribution set differs from exact lock: " + repr(sorted(set(distributions) ^ expected_distributions)))
    for name in set(wheel_records) - {"pip"}:
        require(distributions[name][0].version == wheel_records[name]["version"], "installed version differs from lock: " + name)
    checks["exact_distribution_set"] = True
    owners = verify_installed_records(root, site, distributions, inventory)
    checks["installed_record_integrity"] = True
    matched = set()
    for name in sorted(set(wheel_records) - {"pip"}):
        matched.update(verify_wheel_payload(wheel_paths[name], name, site, inventory, owners, distributions[name][1] / "METADATA"))
    checks["locked_wheel_payloads"] = True
    tf_dist, tf_folder = distributions["transformers"]
    require(tf_dist.version == "5.19.0.dev0", "fixed Transformers version drift")
    built_wheels = [record for record in provenance.values()
                    if Path(record["path"]).name.startswith("transformers-") and record["path"].endswith(".whl")]
    require(len(built_wheels) == 1, "one retained native pip-built Transformers wheel required")
    built_wheel = root / built_wheels[0]["path"]
    built_origin = provenance.get("built_transformers_origin")
    require(type(built_origin) is dict, "native built-wheel origin missing")
    verify_direct_url(read_json(root / built_origin["path"]))
    matched.update(verify_wheel_payload(built_wheel, "transformers", site, inventory, owners, tf_folder / "METADATA"))
    matched.update(verify_source_payload(archive, site, inventory))
    checks["official_transformers_payload"] = True
    direct_url_path = tf_folder / "direct_url.json"
    direct_url = read_json(direct_url_path)
    verify_direct_url(direct_url)
    wheel_report = read_json(fixed["pip_wheels_report"])
    verify_pip_report(wheel_report, {n: r for n, r in wheel_records.items() if n != "pip"})
    tf_report = read_json(fixed["pip_transformers_report"])
    tf_item = verify_pip_report(tf_report, {"transformers": {"version": tf_dist.version, "sha256": ARCHIVE_SHA256}})["transformers"]
    verify_direct_url(tf_item["download_info"])
    require(tf_item.get("is_direct") is True, "Transformers native pip report is not direct canonical install")
    checks["canonical_direct_url"] = True
    merge_record = provenance.get("transformers_merge_manifest")
    require(type(merge_record) is dict, "missing transparent stage-copy evidence")
    merge = read_json(root / merge_record["path"])
    merge_files = merge.get("files")
    require(merge.get("schema") == 1 and type(merge_files) is dict and bool(merge_files), "empty Transformers merge evidence")
    transformer_files = {relative for relative, owner in owners.items() if owner == "transformers"}
    require(set(merge_files) == transformer_files, "Transformers staged merge inventory differs")
    for relative, pair in merge_files.items():
        safe_relative(relative)
        source, installed = verify_record(root, pair["source"]), verify_record(root, pair["installed"])
        require(source["path"] == str((runtime / "transformers-stage" / relative).relative_to(root)) and
                installed == inventory[relative] and (source["bytes"], source["sha256"]) ==
                (installed["bytes"], installed["sha256"]), "stage merge altered bytes or provenance")
        artifacts["transformers_stage:" + relative] = source
    # Residual files must be pip-generated metadata or console entrypoints, never
    # unanchored importable source. Every residual byte is still RECORD-verified.
    generated = []
    for relative in sorted(set(inventory) - matched):
        parts = PurePosixPath(relative).parts
        owner = owners[relative]
        metadata = len(parts) == 2 and parts[0] == distributions[owner][1].name
        generated_metadata = metadata and parts[1] in {"RECORD", "INSTALLER", "REQUESTED", "direct_url.json", "METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "licenses"}
        entrypoints = {ep.name: ep for ep in distributions[owner][0].entry_points
                       if ep.group in ("console_scripts", "gui_scripts")}
        entry_script = len(parts) == 2 and parts[0] == "bin" and parts[1] in entrypoints
        require(generated_metadata or entry_script, "unanchored installed payload: " + relative)
        if entry_script:
            verify_entrypoint_script(site / relative, entrypoints[parts[1]], runtime / "build-venv/bin/python")
        if metadata and parts[1] == "METADATA":
            require(owner == "transformers", "unanchored wheel metadata: " + relative)
        generated.append(relative)
    for name in ("packaging", "torch", "numpy", "transformers"):
        spec = importlib.util.find_spec(name)
        require(spec is not None and spec.origin is not None and Path(spec.origin).resolve().is_relative_to(site),
                "top-level import would leave isolated site: " + name)
    closure = dependency_closure(distributions, list(wheel_records.values()) + [{"filename": built_wheel.name}])
    checks["python_and_wheel_compatibility"] = True
    checks["actual_metadata_dependency_closure"] = True
    torch = importlib.import_module("torch")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    numpy = importlib.import_module("numpy")
    for module_name in ("yaml", "pytest", "huggingface_hub", "tokenizers", "safetensors", "transformers.cache_utils",
                        "transformers.masking_utils", "transformers.models.qwen3_5.configuration_qwen3_5",
                        "transformers.models.qwen3_5.modeling_qwen3_5"):
        importlib.import_module(module_name)
    require(torch.__version__ == "2.10.0+cpu" and torch.version.git_version == TORCH_COMMIT and numpy.__version__ == "2.3.5", "actual Torch/NumPy version/commit drift")
    checks["pinned_versions"] = True
    require(torch.backends.cpu.get_cpu_capability() == "DEFAULT", "Torch DEFAULT dispatch not active")
    checks["torch_default_dispatch"] = True
    require(torch.get_num_threads() == torch.get_num_interop_threads() == 1 and sorted(os.sched_getaffinity(0)) == affinity, "CPU/thread policy drift")
    checks["torch_one_thread"] = True
    with torch.inference_mode():
        require(torch.is_inference_mode_enabled() and not torch.is_grad_enabled() and
                not torch.is_autocast_enabled("cpu") and not torch.is_autocast_enabled("cuda") and
                torch.are_deterministic_algorithms_enabled() and torch.get_float32_matmul_precision() == "highest",
                "inference/deterministic/precision/autocast policy drift")
    checks["deterministic_highest_no_autocast"] = True
    modules = audit_modules(root, runtime, stdlib)
    native_libraries = audit_native_libraries(root, runtime, inventory)
    audit_paths(root, runtime)
    checks["import_origins"] = True
    require(inventory_site(root, site) == inventory, "installed tree changed during qualification")
    checks["installed_tree_unchanged"] = True
    for record in list(artifacts.values()):
        verify_record(root, record)
    checks["provenance_unchanged"] = True
    # Every installed file is a direct receipt artifact, so capture.py checks it
    # again rather than trusting an unchanged manifest over a mutable site tree.
    for relative, record in inventory.items():
        artifacts["installed:" + relative] = record
    interpreter_manifest = {
        "schema": 1, "python": sys.version, "executable": str(Path(sys.executable).resolve()),
        "executable_bytes": Path(sys.executable).stat().st_size, "executable_sha256": digest(sys.executable),
        "stdlib_root": str(stdlib), "loaded_stdlib_files": {}, "trust_boundary":
        "Existing CPython executable, standard library and OS/native loader are measured where loaded, not rebuilt or fully source-closed.",
        "complete_interpreter_os_closure": False, "loaded_native_libraries": native_libraries,
    }
    for path in sorted(set(modules.values())):
        p = Path(path)
        if p.is_relative_to(stdlib) and not p.is_relative_to(site):
            interpreter_manifest["loaded_stdlib_files"][str(p.relative_to(stdlib))] = {"bytes": p.stat().st_size, "sha256": digest(p)}
    write_new(output / "interpreter_manifest.json", interpreter_manifest)
    add("interpreter_manifest", output / "interpreter_manifest.json")
    installed_manifest = {"schema": 1, "files": inventory, "distributions": {n: d.version for n, (d, _) in distributions.items()},
                          "dependency_closure": closure, "pip_generated_files": generated, "loaded_modules": modules,
                          "canonical_transformers_direct_url": direct_url, "offline_install_observations": network_checks}
    write_new(output / "installed_manifest.json", installed_manifest)
    add("installed_manifest", output / "installed_manifest.json")
    require_checks(checks)
    result = {"schema": 1, "status": "PASS_QUALIFICATION_CHECKS", "scope": SCOPE, "checks": checks,
              "created_utc": datetime.now(timezone.utc).isoformat(), "affinity": affinity, "sys_path": sys.path,
              "environment": {k: os.environ.get(k) for k in THREAD_ENV + ("ATEN_CPU_CAPABILITY", "PYTHONNOUSERSITE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")},
              "torch": torch.__version__, "torch_commit": torch.version.git_version, "numpy": numpy.__version__,
              "official_capture_executed": False, "numerical_pass": False, "rtl_executed": False,
              "complete_environment_closure": False, "package_dependency_closure_verified": True,
              "scope_note": "Import/source/binary/dependency/runtime-policy checks only. No model construction, weights, tensors, capture, candidate replay or numerical PASS. Eval mode belongs to later actual model capture, not an invented model here."}
    write_new(output / "qualification.json", result)
    add("qualification_output", output / "qualification.json")
    receipt = dict(result, status="PASS_ISOLATED_PINNED_RUNTIME_READY", artifacts=artifacts)
    validate_receipt(receipt)
    for record in artifacts.values():
        verify_record(root, record)
    candidate = output / "runtime_receipt.candidate.json"
    write_new(candidate, receipt)
    # An exclusive hard link publishes only a complete, fsynced receipt and
    # cannot replace a concurrently created receipt. Keep the candidate evidence.
    os.link(candidate, runtime / "runtime_receipt.json")
    return {"status": receipt["status"], "receipt": file_record(root, runtime / "runtime_receipt.json"), "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--expected-lock-sha256", required=True, help="Independently reviewed dependency-lock SHA256")
    parser.add_argument("--wall-seconds", type=int, default=240)
    args = parser.parse_args(argv)
    root, runtime = Path(args.root).resolve(), Path(args.runtime).resolve()
    require(runtime.is_relative_to(root / "work") and runtime.is_dir(), "existing fresh runtime must be below ROOT/work")
    require(not (runtime / "runtime_receipt.json").exists() and not (runtime / "runtime_receipt.json").is_symlink(),
            "runtime receipt already exists; never overwrite or inherit readiness")
    output = runtime / "qualification"
    require(not output.exists() and not output.is_symlink(), "qualification already attempted; preserve it and use a fresh runtime")
    require(1 <= args.wall_seconds <= 600, "qualification wall budget must be 1..600 seconds")
    output.mkdir()
    start = time.monotonic()
    def expired(signum, frame):
        raise TimeoutError("runtime qualification exceeded bounded wall budget")
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(args.wall_seconds)
    try:
        result = qualify(args, output)
    except BaseException as exc:
        write_new(output / "failure.json", {"status": "FAILED_RUNTIME_QUALIFICATION", "error": str(exc),
                  "exception_type": type(exc).__name__, "traceback": traceback.format_exc(),
                  "elapsed_seconds": time.monotonic() - start, "ready_receipt_created": (runtime / "runtime_receipt.json").exists(),
                  "partial_evidence_preserved": True})
        raise
    finally:
        signal.alarm(0)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
