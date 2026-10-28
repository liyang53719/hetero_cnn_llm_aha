# Reproduction dependency contract

This package contains source, pins and summarized evidence, not installed runtimes,
weights, binary inputs or reference outputs. It is not a self-contained numerical
PASS bundle. Runtime and payload acquisition must be reproduced separately.

## Required inputs

- An isolated Python 3.12 runtime with the exact official Torch CPU wheel and
  framework versions identified by the archive-derived sidecar. The observed fresh
  runtime was Python 3.12.14; no historical Python-runtime arithmetic equivalence is claimed.
- Official complete tensor files and semantic `*.receipt.json` files beneath
  `PAYLOAD_ROOT/<profile.model>/`, using the pinned tensor acquisition plan. No
  truncated expert tensors or reference-generated routing IDs are valid inputs.
- Exact checkpoint `config.json`, checked against `profiles.json`.
- Reviewed runtime receipt and its SHA256, separately established from locked
  artifacts. A receipt is not replaced by self-calibration from live imports.
- Sidecar and its SHA256, generated with `derive_sidecar.py` from verified archives.
- Runtime wrapper that sets source paths and original dispatch/thread settings:
  profile0 AVX512/4threads; profiles1..4 DEFAULT/1thread. All use original Torch
  CPU build, deterministic algorithms, no autocast and FP32 default constructor.

Keep each runner adjacent to its unmodified `profiles.json`, `stimulus.py` and
`tensor_acquisition_plan.json`. These are immutable source-version dependencies.
The v2 runner adds original dictionary-cache handling; v3 additionally sets the
exact 35B original experts implementation to eager. Neither changes topk.
The dedicated P0 cache arm accepts only profile0 and verifies exact output against
the frozen no-cache output digest before capturing actual final rotated K/V.

## Parameterized invocation (replace placeholders)

```sh
python bounded_reference.py \
  --site "$ISOLATED_SITE" --sidecar "$SIDECAR" --sidecar-sha "$SIDECAR_SHA" \
  --run-dir "$NEW_RUN_DIR" --rss-gib 3 --cpu-seconds 1200 --wall-seconds 1800 \
  -- "$RUNTIME_WRAPPER" "$RUNNER_DIR/run_reference.py" \
  --profile "$PROFILE" --payload "$PAYLOAD_ROOT" --config "$CHECKPOINT_CONFIG" \
  --runtime-receipt "$RUNTIME_RECEIPT" --runtime-receipt-sha256 "$RECEIPT_SHA" \
  --runtime-source-pins "$SIDECAR" --runtime-source-pins-sha256 "$SIDECAR_SHA" \
  --output "$NEW_RUN_DIR/reference" --execute-reviewed
```

Resource admission is external and mandatory. Limits are process limits, not a
license to reduce block geometry or hardware resources. Only the launcher-owned
process group may be terminated by this launcher. Source-path templates in
historical RUN_P*.sh are local execution records, not portable entrypoints.

Binary tensors remain local. Publish only reproducible source, pins, hashes,
small summaries and failure attribution. Python reference completion does not
establish Chisel or RTL numerical correctness or hardware MAC utilization.
