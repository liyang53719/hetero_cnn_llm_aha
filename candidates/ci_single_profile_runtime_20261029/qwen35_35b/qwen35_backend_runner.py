#!/usr/bin/env python3
"""Fail-closed trusted entrypoint for an unmodified pinned pip PEP517 helper."""
import os
import hashlib
from pathlib import Path
import runpy
import sys

runtime = Path(os.environ["QWEN35_RUNTIME_ROOT"]).resolve()
if not sys.flags.no_site or not sys.dont_write_bytecode or sys.version_info[:2] != (3, 12) or len(sys.argv) != 4:
    raise RuntimeError("Isolated explicit backend entrypoint required")
helper, hook, control = sys.argv[1:]
expected = runtime / "bootstrap-pip/pip/_vendor/pyproject_hooks/_in_process/_in_process.py"
if Path(helper).resolve() != expected or hook not in {"get_requires_for_build_wheel", "prepare_metadata_for_build_wheel", "build_wheel"}:
    raise RuntimeError("Unexpected PEP517 helper or hook")
if expected.stat().st_size != 12216 or hashlib.sha256(expected.read_bytes()).hexdigest() != "a9c5cc866c7ffcc209ab5d201875b7980e1397c772f18cc731c7309cda0a970d":
    raise RuntimeError("Pinned official backend helper changed")
if not Path(control).resolve().is_relative_to(runtime / "tmp") or not Path.cwd().is_relative_to(runtime / "tmp"):
    raise RuntimeError("Backend control/source directory outside private temp root")
if os.environ.get("_PYPROJECT_HOOKS_BUILD_BACKEND") != "setuptools.build_meta:__legacy__" or os.environ.get("_PYPROJECT_HOOKS_BACKEND_PATH"):
    raise RuntimeError("Unexpected build backend")
if any(("site-packages" in p or "dist-packages" in p) and Path(p).resolve() != runtime / "site-packages" for p in sys.path):
    raise RuntimeError("Ambient backend site-packages present")
sys.path[:0] = [str(runtime / "guard"), str(runtime / "bootstrap-pip"), str(runtime / "site-packages")]
# This explicit import is not CPython's optional, exception-swallowing site hook.
import sitecustomize
if not sitecustomize.GUARD_ACTIVE or Path(sitecustomize.__file__).resolve() != runtime / "guard/sitecustomize.py":
    raise RuntimeError("Required backend audit guard did not activate")
sitecustomize.record("backend_entry_verified", True, "Explicit guard imported before official backend helper")
sys.argv = [helper, hook, control]
runpy.run_path(helper, run_name="__main__")
