# L5 target split-half RoPE and post-RoPE K GQA

Status: PASS as the second restartable target-shape segment; L5 remains
`IN_PROGRESS`.

The segment consumes the exact biased-Q/K hashes from the target QKV receipt.
For each 128-d head, lane `i` is paired with lane `i+64`; adjacent even/odd
pairing is not used. Coefficients use the pinned theta `1e6` and positions 0/1.
Twelve Q heads and two KV heads per token pass through the proven FP32 pair
primitive. A separate 16-lane endpoint then multicasts rotated K from each KV
head to six query heads.

All 1,024 RoPE pairs and 32 multicast inputs/192 outputs match the
operation-order model. Measured totals are 4,392 cycles: 4,096 RoPE and 296
multicast cycles. Q-RoPE FNV64 is `b4a725a0e8740d6b`; rotated K0/K1 GQA
FNV64 values are `1e473c44ecaff411` and `5a2b6037ffaa744d`.

Q-RoPE, K-RoPE and expanded rotated-K SHA256 values are respectively
`da6332ce70e15a4d10299ccc3b5dddede3f4c76feddb6c76f3399f301b4e5f22`,
`793c1a31a878ce1e405d2730e88670ebbb1b0695d1f21d7499a64f1201bf889d`
and `ced3130a6ca76bcec9c283b520a0a05421b7c3225af30ae92d015f0c3586bd4c`.
Backpressure stability and all head/chunk/last/tag sidebands pass. Lint/build
allocations were about 33/297 MB and simulation 7 MB, with no OOM.
