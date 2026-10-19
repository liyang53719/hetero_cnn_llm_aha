#!/usr/bin/env python3
"""Trusted Python bootstrap for a same-buffer pinned, source-only cold suite.

Usage: python3 run_cold.py --source /path/to/public --repo /path/to/checkout
       python3 -O run_cold.py --source /path/to/public --repo /path/to/checkout
No C++/RTL/compiler/native child process or network is used. The test is compiled
as Python only after size/SHA verification of the very bytes passed to compile.
The runner is the small trust root; its distributed receipt pins the runner.
"""
import argparse
import hashlib
from pathlib import Path
import sys

TEST_SIZE = 29959
TEST_SHA256 = "eb07b1ae2870ec3e91eb612a818838cb2de8862aed789bf0aa10fbfcbdd8a959"


def deny_external_execution(event, args):
    if (event.startswith(("socket.", "subprocess.", "ctypes.")) or
            event in {"os.system", "os.exec", "os.posix_spawn", "os.fork", "os.forkpty", "os.spawn"}):
        raise RuntimeError("cold suite forbids network/native subprocess: " + event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent,
                        help="relocatable public source bundle")
    parser.add_argument("--repo", type=Path, required=True,
                        help="read-only checkout containing the 31 SOURCE_PINS members")
    args = parser.parse_args()
    root = args.source.resolve()
    test_path = root / "test_capsule_cold.py"
    raw = test_path.read_bytes()
    if len(raw) != TEST_SIZE or hashlib.sha256(raw).hexdigest() != TEST_SHA256:
        raise SystemExit("REFUSED: test size/SHA256 differs before Python compile/exec")
    sys.addaudithook(deny_external_execution)
    namespace = {"__name__": "_pinned_cold_suite", "__file__": str(test_path),
                 "_PINNED_TEST_BUFFER": raw, "_PINNED_TEST_PIN": (TEST_SIZE, TEST_SHA256),
                 "_PINNED_ROOT": str(root), "_PINNED_REPO": str(args.repo.resolve())}
    code = compile(raw, str(test_path), "exec", dont_inherit=True)
    exec(code, namespace)
    return namespace["run"]()


if __name__ == "__main__":
    raise SystemExit(main())
