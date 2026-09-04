#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
COMMON="$ROOT/scripts/run_qwen2_root_owner_canary_v3.sh"

run_root() {
  local define=$1
  local rtl=$2
  local name=$3
  ROOT_DEFINE="$define" \
  ROOT_RTL="$ROOT/generated/operator_primitives_v3/roots/$rtl.sv" \
  CANARY_OUT="$ROOT/work/results/qwen35_root_owner_canary_v3/$name" \
  EXPECTED_MARKER="${name}_ROOT_OWNER_CANARY_V3_PASS" \
    "$COMMON"
}

run_root ROOT_GDN HeteroGatedDeltaNetPrimitiveV3 QWEN35_GDN
run_root ROOT_DENSE HeteroQwen35DenseAttentionPrimitiveV3 QWEN35_DENSE
run_root ROOT_MOE HeteroMoePrimitiveV3 QWEN35_MOE
run_root ROOT_MTP_COMMIT HeteroMtpVerifyResolvePrimitiveV3 QWEN35_MTP_COMMIT
run_root ROOT_MTP_ROLLBACK HeteroMtpVerifyResolvePrimitiveV3 QWEN35_MTP_ROLLBACK

echo "QWEN35_ROOT_OWNER_CANARY_V3_PASS roots=4 paths=5 reference_injection=0"
