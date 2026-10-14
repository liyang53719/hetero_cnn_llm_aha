#!/usr/bin/env bash
# Reuse independent QKV/N32/N4096/O K4096 reference reports.
# No downloads, reference-output injection, or new acceptance threshold.
set -euo pipefail
if [[ $# != 10 ]]; then
  echo 'usage: bash scripts/run_qwen35_35b_postnorm_diagnostic.sh M QKV_REPORT QKV_SHA AB_REPORT AB_SHA Z_REPORT Z_SHA O_REPORT O_SHA FRESH_OUTPUT' >&2
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
  --chunk-matmul-policy "${HETERO_CHUNK_MATMUL_POLICY:-row1_streaming}" \
  --reduction-policy torch_2_10_cpu_default_f32_8lane_4ilp_128 \
  --gate-policy 35b_finite_nonpositive_fp32_dual_p7_exp \
  --gated-norm \
  --z-norm-payload work/qwen35_35b_z_norm_payload \
  --z-norm-manifest-sha256 844ee510c0ba106233bd5cd63f869a162f494b3a0640d4696d7edee1cce6ec8e \
  --z-reference-report "$6" --z-reference-report-sha256 "$7" \
  --output-projection \
  --o-payload work/qwen35_35b_o_payload \
  --o-manifest-sha256 88260a7389c631177cc9766b5f65e2407bec33a7bcbd7e7904bda70eea50e9b5 \
  --o-reference-report "$8" --o-reference-report-sha256 "$9" \
  --postnorm --postnorm-payload work/qwen35_35b_postnorm_payload \
  --postnorm-manifest-sha256 9fe42b27599c7e83524b899638f595b8bac9e5c6c4eaf2750a18c9a521712ba0 \
  --wall-seconds 1800 --output "${10}"
