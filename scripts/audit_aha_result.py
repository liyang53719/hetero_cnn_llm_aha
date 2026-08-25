#!/usr/bin/env python3
"""Read one AHA baseline result directory without launching or waiting on jobs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = ["garnet_rtl.sha256", "gaussian_map.log", "gaussian_pnr.log", "gaussian_test.log"]
ERROR_MARKERS = ("%Error:", "fatal error:", "SIGSEGV", "Traceback", "*** FAILED ***", "Error 1")


def first_error(directory: Path) -> str | None:
    for name in ("gaussian_test.log", "docker.log", "gaussian_pnr.log", "gaussian_map.log"):
        path = directory / name
        if not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            if any(marker in line for marker in ERROR_MARKERS):
                return f"{name}: {line.strip()}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result_dir = args.result_dir
    result: dict[str, object] = {
        "result_dir": str(result_dir),
        "status": "INCOMPLETE",
        "missing": [name for name in REQUIRED if not (result_dir / name).is_file() or (result_dir / name).stat().st_size == 0],
    }
    result_json = result_dir / "result.json"
    if result_json.is_file():
        try:
            result["runner_result"] = json.loads(result_json.read_text())
        except json.JSONDecodeError as exc:
            result["result_json_error"] = str(exc)
    test_log = result_dir / "gaussian_test.log"
    if not result["missing"] and test_log.is_file() and "Integer (Bit-accurate) comparison passed." in test_log.read_text(errors="replace"):
        result["status"] = "PASS"
    else:
        error = first_error(result_dir)
        if error:
            result["status"] = "FAIL"
            result["first_error"] = error
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
