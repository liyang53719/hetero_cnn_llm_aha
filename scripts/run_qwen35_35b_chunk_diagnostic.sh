#!/usr/bin/env bash
# Reuse independently calibrated full-shape QKV/N32 reference reports.
# No downloads, reference-output injection, or new acceptance threshold.
set -euo pipefail
if [[ $# != 6 ]]; then
  echo 'usage: bash scripts/run_qwen35_35b_chunk_diagnostic.sh M QKV_REPORT QKV_SHA AB_REPORT AB_SHA FRESH_OUTPUT' >&2
  exit 2
fi
case "$1" in 16|128) ;; *) echo 'M must be 16 or 128' >&2; exit 2;; esac
: "${MATRIX_SERVICE_LIBRARY:?set pinned Matrix library}"
: "${MATRIX_SERVICE_COMPILE_RECEIPT:?set Matrix build receipt}"
: "${GDN_VECTOR16_LIBRARY:?set pinned Vector library}"
: "${HETERO_35B_RUNTIME_PROFILE:?set validated runtime profile}"
export PYTHONDONTWRITEBYTECODE=1
"${HETERO_PYTHON_WRAPPER:-work/runtime_recovery/python.sh}" -m candidates.qwen35_35b_prep.run \
  --payload work/qwen35_35b_qkv_payload_recovery \
  --manifest-sha256 26dd763dacaa328ecdbed1ae7cf29bb31a5808ea82bbc27477bfed2d9645400c \
  --reference-report "$2" --reference-report-sha256 "$3" \
  --conv-payload work/qwen35_35b_conv_payload \
  --conv-manifest-sha256 6bc7d86de3c31fee0eb77becf56cc72b627a793d85bbe87cd718995c88ff9c20 \
  --ab-payload work/qwen35_35b_ab_payload \
  --ab-manifest-sha256 33bedd6de939a892678e5ba9335c4655d2b2c18690ed1418d96e9455af4db9b5 \
  --ab-reference-report "$4" --ab-reference-report-sha256 "$5" \
  --tokens "$1" --full-qkv --chunk \
  --reduction-policy torch_2_10_cpu_default_f32_8lane_4ilp_128 \
  --gate-policy 35b_finite_nonpositive_fp32_dual_p7_exp \
  --wall-seconds 1800 --output "$6"
