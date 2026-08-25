#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi

# Keep the user-requested spelling. On this host the cgroup constrains it to
# CPUs 8-23, which taskset resolves transparently.
exec taskset -c "${L11_CPUSET:-8-25}" "$@"
