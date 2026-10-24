"""Fresh-runtime Python-level no-network guard, not a native OS sandbox.

Copied as sitecustomize.py and automatically loaded by isolated-venv backend
children. The parent permits only exact pinned pip PEP517 helper invocations.
No network event, shell command, arbitrary child process or backend subprocess
is permitted. This does not claim to constrain malicious native code.
"""
import json
import os
from pathlib import Path
import sys
import time

RUNTIME = Path(os.environ["QWEN35_RUNTIME_ROOT"]).resolve()
LOG = RUNTIME / "network_guard.jsonl"
PARENT_PID = int(os.environ["QWEN35_PARENT_GUARD_PID"])
PARENT = os.getpid() == PARENT_PID
SELF_TEST = False
RUNNER = RUNTIME / "provenance/qwen35_backend_runner.py"
HELPER = RUNTIME / "bootstrap-pip/pip/_vendor/pyproject_hooks/_in_process/_in_process.py"
HOOKS = {"get_requires_for_build_wheel", "prepare_metadata_for_build_wheel", "build_wheel"}


def record(event, allowed, detail):
    row = {"time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "pid": os.getpid(), "parent_driver": PARENT, "event": event,
           "allowed": allowed, "detail": detail, "expected_self_test": SELF_TEST}
    with LOG.open("a") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")


def audit(event, args):
    if event.startswith("socket."):
        record(event, False, "network denied before operation")
        raise PermissionError("Offline runtime installation forbids Python socket operations")
    if event == "subprocess.Popen":
        executable, command, cwd, env = args
        allowed = (PARENT and isinstance(command, (list, tuple)) and len(command) == 8
                   and Path(command[0]).resolve() == Path(sys.executable).resolve()
                   and command[1:4] == ["-I", "-S", "-B"]
                   and Path(command[4]).resolve() == RUNNER.resolve()
                   and Path(command[5]).resolve() == HELPER.resolve()
                   and command[6] in HOOKS
                   and Path(command[7]).resolve().is_relative_to(RUNTIME / "tmp")
                   and cwd is not None and Path(cwd).resolve().is_relative_to(RUNTIME / "tmp")
                   and env is not None
                   and env.get("_PYPROJECT_HOOKS_BUILD_BACKEND") == "setuptools.build_meta:__legacy__"
                   and not env.get("_PYPROJECT_HOOKS_BACKEND_PATH")
                   and env.get("PYTHONNOUSERSITE") == "1"
                   and env.get("PYTHONPATH") == os.environ["PYTHONPATH"]
                   and env.get("QWEN35_PARENT_GUARD_PID") == str(PARENT_PID)
                   and env.get("QWEN35_RUNTIME_ROOT") == str(RUNTIME))
        record(event, bool(allowed), "pinned PEP517 helper" if allowed else "unexpected child denied")
        if not allowed:
            raise PermissionError("Unexpected installer subprocess denied")
    if event in {"os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty"}:
        record(event, False, "shell or direct process spawn denied")
        raise PermissionError("Offline installer forbids shell and direct process spawns")


sys.addaudithook(audit)
GUARD_ACTIVE = True
record("guard_activated", True, "Python-level audit; no native sandbox claim")
