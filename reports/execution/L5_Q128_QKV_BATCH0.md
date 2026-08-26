# L5 q128 QKV numerical row batch0

Status: PASS for tokens 0-15; q128 remains `IN_PROGRESS` until batches1-7 and
all downstream phases pass.

Sixteen global RMSNorm1536 operations feed all 16 physical array rows. The
batch runs complete Q/K/V projections with the frozen target weights and
biases. All normalized, Q, K and V outputs match operation-order goldens.

The RTL counter reports exactly 98,304 Matrix steps: Q 73,728 and K/V 12,288
each. Measured totals are 401,504 cycles: 393,216 Matrix, 6,240 RMSNorm and
2,048 bias cycles. Q/K/V FNV64 values are `462cfe6bc16b09b7`,
`5d02210cc8f117bd` and `c2e4bd2a0425988f`.

The full 128-token input image SHA256 is `39917c9e...`; batch0 Q/K/V hashes are
`002082a1...`, `a7f3acfa...`, `42d0886d...`. Lint/build allocations were about
568/950 MB and simulation 28 MB, with no OOM.
