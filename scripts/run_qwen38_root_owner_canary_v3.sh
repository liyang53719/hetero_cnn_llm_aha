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
  CANARY_OUT="$ROOT/work/results/qwen38_root_owner_canary_v3/$name" \
  EXPECTED_MARKER="${name}_ROOT_OWNER_CANARY_V3_PASS" \
    "$COMMON"
}

run_root ROOT_GDN38 HeteroGatedDeltaNetPrimitiveV3 QWEN38_GDN
run_root ROOT_QSA HeteroQsaPrimitiveV3 QWEN38_QSA
run_root ROOT_PLE HeteroPlePrimitiveV3 QWEN38_PLE
run_root ROOT_HYPER_READ HeteroQwen38GatedResidualReadPrimitiveV3 QWEN38_HYPER_READ
run_root ROOT_HYPER_WRITE HeteroQwen38GatedResidualWritePrimitiveV3 QWEN38_HYPER_WRITE
run_root ROOT_FINAL_HYPER HeteroQwen38FinalHyperMergePrimitiveV3 QWEN38_FINAL_HYPER
run_root ROOT_MOE38 HeteroMoePrimitiveV3 QWEN38_MOE
run_root ROOT_MTP38_COMMIT HeteroMtpVerifyResolvePrimitiveV3 QWEN38_MTP_COMMIT
run_root ROOT_MTP38_ROLLBACK HeteroMtpVerifyResolvePrimitiveV3 QWEN38_MTP_ROLLBACK

echo "QWEN38_ROOT_OWNER_CANARY_V3_PASS roots=7 paths=9 reference_injection=0"
