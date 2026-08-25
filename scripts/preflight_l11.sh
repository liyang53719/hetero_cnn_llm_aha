#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/reports/execution/preflight.json"
mkdir -p "$(dirname "$OUT")"

docker_state=missing
if command -v docker >/dev/null 2>&1; then
  if docker version >/dev/null 2>&1; then
    docker_state=ready
  else
    docker_state=installed_not_ready
  fi
fi

dc_state=missing
if command -v dc_shell >/dev/null 2>&1; then dc_state=ready; fi
vcs_state=missing
if command -v vcs >/dev/null 2>&1; then vcs_state=ready; fi
lc_state=missing
if command -v lc_shell >/dev/null 2>&1; then lc_state=ready; fi

free_gib=$(df -BG --output=avail "$ROOT" | tail -n 1 | tr -dc '0-9')
mem_gib=$(awk '/MemAvailable/ {printf "%d", $2 / 1024 / 1024}' /proc/meminfo)
cpus=$(awk '/Cpus_allowed_list/ {print $2}' /proc/self/status)

jq -n \
  --arg generated_at "$(date --iso-8601=seconds)" \
  --arg cpus_allowed "$cpus" \
  --arg docker "$docker_state" \
  --arg dc_shell "$dc_state" \
  --arg vcs "$vcs_state" \
  --arg lc_shell "$lc_state" \
  --argjson free_gib "$free_gib" \
  --argjson mem_available_gib "$mem_gib" \
  '{generated_at:$generated_at,cpus_allowed:$cpus_allowed,docker:$docker,dc_shell:$dc_shell,vcs:$vcs,lc_shell:$lc_shell,free_gib:$free_gib,mem_available_gib:$mem_available_gib,storage_gate:($free_gib >= 250),memory_gate:($mem_available_gib >= 8)}' \
  > "$OUT"

jq . "$OUT"
