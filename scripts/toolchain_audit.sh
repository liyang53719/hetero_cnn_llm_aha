#!/usr/bin/env bash
set -euo pipefail
for tool in python3 git cmake gcc g++ clang java sbt docker verilator iverilog yosys slang surelog sv2v; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '%-12s %s\n' "$tool" "$(command -v "$tool")"
  else
    printf '%-12s MISSING\n' "$tool"
  fi
done
