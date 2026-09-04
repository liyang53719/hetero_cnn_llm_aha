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
  CANARY_OUT="$ROOT/work/results/vision_root_owner_canary_v3/$name" \
  EXPECTED_MARKER="${name}_ROOT_OWNER_CANARY_V3_PASS" \
    "$COMMON"
}

run_root ROOT_VISION_PATCH HeteroVisionPatchEmbedPrimitiveV3 VISION_PATCH
run_root ROOT_VISION_TRANSFORMER HeteroVisionTransformerBlockPrimitiveV3 VISION_TRANSFORMER
run_root ROOT_VISION_MERGE HeteroVisionPatchMergePrimitiveV3 VISION_MERGE
run_root ROOT_VISION_INJECT HeteroMultimodalInjectPrimitiveV3 VISION_INJECT

echo "VISION_ROOT_OWNER_CANARY_V3_PASS roots=4 paths=4 reference_injection=0"
