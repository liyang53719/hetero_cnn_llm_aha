#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
taskset -c 8-23 python3 scripts/verify_local_upstream_integrity.py
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
  scripts/run_memory_capped.sh timeout --foreground --signal=INT \
  --kill-after=30s 600s ./scripts/sandbox_validate.sh
