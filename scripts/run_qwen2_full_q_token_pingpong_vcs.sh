#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
OUT=${OUT:-$ROOT/work/results/qwen2_full_q_token_pingpong} FULL_Q=1 OVERLAP=1 "$ROOT/scripts/run_qwen2_idma_descriptor_compute_top_vcs.sh"
