#!/usr/bin/env bash
# Run one project task in a user cgroup so a compiler spike cannot trigger a
# global OOM. All project build/test/synthesis calls are pinned to CPU 8-23.
set -euo pipefail

MIN_AVAILABLE_KIB=${MIN_AVAILABLE_KIB:-16777216} # 16 GiB admission floor
MEMORY_HIGH=${MEMORY_HIGH:-24G}
MEMORY_MAX=${MEMORY_MAX:-30G}

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi

available_kib=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
if (( available_kib < MIN_AVAILABLE_KIB )); then
  echo "RESOURCE_GUARD: MemAvailable=${available_kib}KiB is below ${MIN_AVAILABLE_KIB}KiB" >&2
  exit 75
fi

exec systemd-run --user --scope --quiet \
  -p "MemoryHigh=${MEMORY_HIGH}" \
  -p "MemoryMax=${MEMORY_MAX}" \
  taskset -c 8-23 "$@"
