# L5 hidden256 global chunked RMSNorm

Status: PASS as a hidden256 SFU subgate; L5 remains `IN_PROGRESS`.

The RTL reuses one 16-lane square/reduction datapath across 16 chunks. It
accumulates the 16 partial sums in a fixed FP32 order, computes one global
`mean + epsilon` and reciprocal square root, then emits 16 weighted output
chunks. It does not normalize each chunk independently.

The deterministic operation-order model and RTL agree bit-for-bit on all 256
outputs in 1,000 vectors. The measured totals are 69,998 cycles, including
48,000 reduction cycles, 3,000 reciprocal-square-root cycles and 16,000 output
cycles. Output FNV64 is `b9943043e156b835`; the vector file SHA256 is
`07459711c8d09628ad412c88141cd59cde0bfcbd3096857a458ccbb13825d63e`.

The reused 16-lane reduction was separately regressed for 10,000 vectors after
moving to the joint BF16/FP32 HardFloat emission. It remains bit-exact with
FNV64 `eb1a9f9acb34f5b5`. All lint/build/test commands used CPU 8-25, at most
four build jobs and the 10 GiB cgroup cap.

This closes only global hidden256 RMSNorm. The next subgate composes the full
hidden256 block and verifies every frozen intermediate node.
