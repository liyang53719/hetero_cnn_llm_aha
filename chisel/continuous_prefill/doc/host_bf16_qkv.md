# Experimental Host Q/K/V projections

This route is default off (`bf16Qkv=false`) and is **PROJECTION_ONLY**. It does
not implement Q/K Norm, RoPE, attention or a full Qwen3.5 block. The old Host V
route, its fixture format and its driver remain separate.

The public Command128 program contains three sequential MATRIX_GEMM commands:
Q role 0, N=4096; K role 1, N=512; V role 2, N=512. All use H=1024 and native
BF16 rank-2 contiguous A/B/D tensors. Q stores eight interleaved heads, each
containing 256 query content columns followed by 256 gate columns. All three
commands read the same authentic layer3 normalized activation. Completion events
order execution; Q is not K's activation, and K is not V's activation.

The version-2 owner-managed policy retains nine zero address sentinels and norm
policy 0. Every full allocation is checked before selecting its active token
window. The contract is `config/host_bf16_qkv_descriptor_contract.json`.

## Source admission

`scripts/pack_host_bf16_qkv_fixture.py OUTPUT` defaults to the code-pinned
official capture, baseline/cold/base0/count1. `--variant`, `--phase`,
`--token-base` and `--token-count` select a bounded window. Fresh in-process
callers pass the existing `CaptureSession` returned by `rebuild_session()` to
`pack_fixture()` and retain that same session for verification/execution.
Neither CLI accepts arbitrary NPZ files, weights, trusted digests or fresh saved
receipts. All fixture data stays under ignored `work/`.

Producer 07 supplies A; 08 supplies packed native Q+gate comparison bytes; 17
and 26 supply native K/V comparison bytes. All eleven layer3 weights are checked
against the existing pinned payload loader, and only official Wq/Wk/Wv are
transposed to K-major order. Model revision is
`2fc06364715b967f1860aea9cf38778875588b17`, Transformers revision is
`14e738b5d0cc69aa27a95dde272aea41fde44f2f`. Full native audit FAIL statuses,
failed producer records and report hashes remain in the fixture manifest.

Optional independent terminal reuse reads only the frozen full128 summary with
SHA256 `7a825ff9195db77e5889ecd2c4a4cf6f120454a39160493cd82661b806f97a51`
and selected terminal files. Every selected head must match the actual raw A
and K-major W hash. A fresh capture with different bytes cannot reuse these
terminals. No accumulator trace is loaded, expanded or regenerated.

`scripts/verify_host_bf16_qkv_fixture.py FIXTURE` repacks the authenticated inputs
and compares the complete manifest, inventory and every file byte. A fresh
fixture requires its live session through the Python API.

## Actual execution and evidence

The C++ driver is `tests/host_bf16_qkv.cpp`, built against the real
`EmitHostBf16Qkv OUT [burstWrites=0|1]` HostBlockTop. It uses the retained eight
Matrix slices and one iDMA. Its CLI is `VHostBlockTop FIXTURE OUTPUT MODE`.
Modes are `pass`, `last-write-error`, `activation-read-error`,
`weight-read-error`, `output-alias`, and `reset-recovery`.

The first three fault modes fail V after Q/K have completed. The alias mode
makes K's active destination overlap Q's published active output, including for
base127. Reset recovery faults Q's first activation read, observes poison, resets
the same DUT, and completes three commands without changing DDR input constants
or inserting expected output data. The second run writes artifacts beneath
`OUTPUT/recovery/`.

The sole simulated memory is indexed by actual physical DDR address. It starts
with sentinel bytes everywhere except readonly tables, A and official weights.
Only acknowledged successful AXI writes change it. The reference is separate:
sequential K=0..1023 FP32 `std::fma`, then BF16 round-to-nearest-even. The driver
checks all prior physical outputs after each completion and at finish; prefix,
suffix, future outputs and guards must remain untouched. Each command's final
write response is delayed at least 53 cycles; its completion is held for at
least 11 cycles. Result backpressure and poison are also checked.

`actual_q/k/v.bf16le`, `reference_q/k/v.bf16le`, a complete `ddr_after.bin`, and
`writable_after_commandN.bin` snapshots support independent validation. The
compact physical aperture is 12,156,928 bytes; a writable snapshot is 1,327,104
bytes. At count1 a pass or V fault uses about 15.41 MiB, the alias case 14.14 MiB,
and reset plus recovery 28.29 MiB. Six modes total about 104.1 MiB plus logs.
These are local evidence files, never upload artifacts or checked-in payloads.

`host_bf16_qkv_execution.verify_execution()` checks the raw artifacts and event
sequence. It reconstructs all ACKed physical writes, checks intermediate and
final memory, compares actual/reference/optional frozen terminals, and computes
native Q content, Q gate, K and V metrics independently. Each comparison retains
max absolute error <=0.03125 and mean absolute error <=0.005. Unknown, duplicate,
missing, early-ACK, early-publication or inconsistent events are rejected.
Artifact verification alone is explicitly not DUT identity verification.

For an actual case, use `run_case(build, fixture, mode, session, label=...)`.
This checks the source manifest, all bound build sources, HardFloat, binary, RTL
and fixture before and after execution. This numerical acceptance gate also
requires exact input-bound independent integer/C terminals. Missing terminals
block execution acceptance; artifact-only C++ comparisons are explicitly a
weaker diagnostic, including for a different legitimate fresh capture.
`run_representative()` requires all six
modes and only then writes a projection-only aggregate result. A build receipt
with `BUILT_HOST_QKV_PROJECTIONS_ONLY_NOT_NUMERICAL_PASS` never grants acceptance.

Local execution on 2026-10-09 completed baseline cold/base0/count1,
carried/base127/count1 and cold output-alias. Both pass cases checked 5,120
BF16 words with zero canonical differences and 762,218 cycles; alias rejected
K before its owner with status 9 and preserved Q. All three physical DDR
apertures were checked. These historical runs bind 403 dirty-build source
hashes above base commit 78e60a5, with the recorded SIG9/overlapping-generation
recovery qualification. They are not an exact-new-commit clean CI result.
See `doc/U00_2_HOST_QKV_PROJECTION_20261009_CN.md` at the repository root.
Other actual fault/reset cases and fresh CI remain open; count16/full128
execution, Norm/RoPE and complete-block acceptance are not established.
