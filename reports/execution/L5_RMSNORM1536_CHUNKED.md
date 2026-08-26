# L5 global RMSNorm1536

Status: PASS as a target-shape payload subgate; L5 remains `IN_PROGRESS`.

One physical 16-lane square/reduction tile is reused across all 96 chunks. The
partial sums are accumulated in fixed FP32 order, multiplied by the exact
FP32 `1/1536` constant `0x3a2aaaab`, combined with the pinned Qwen epsilon
`1e-6` (`0x358637bd`), and passed through one global reciprocal square root.
The resulting scale and 1536 weights are then applied over 96 output chunks.
No chunk is normalized independently.

All 1536 outputs in 1,000 deterministic vectors match the operation-order
model bit-for-bit. Measured totals are 389,998 cycles: 288,000 reduction,
3,000 reciprocal-square-root and 96,000 output cycles. Output FNV64 is
`75e7b057b6b5d948`; vector SHA256 is
`67ef9c7b12ae0b1771293d4a62d78a7933b1af81e62a497f8674a8373530a5a2`.
The maximum absolute error against a float64 RMSNorm reference is
`8.83896267e-7`, below the frozen `2e-5` limit.

Strict lint allocated about 103 MB, the j4 build about 494 MB and simulation
25 MB. CPU affinity remained 8-25, MemoryMax was 10 GiB, and no OOM event was
observed.
