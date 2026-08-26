# L5 target post-attention RMSNorm1536

Status: PASS as the fifth restartable target-shape segment; L5 remains
`IN_PROGRESS`.

The segment consumes the exact residual1 hash and applies a frozen 1536-lane
weight through the proven global 96-chunk RMSNorm, with epsilon `1e-6` and one
reciprocal square root. All 1536 outputs match the operation-order model.

Measured total is 390 cycles: 288 reduction, 3 rsqrt and 96 output cycles.
Norm2 FNV64 is `44816bc1983da5ce`; norm weight and norm2 SHA256 values are
`7785c762e20b178ddd03ae05f5b95d9edc81236f7d60015bd685738a142a5418`
and `bb884b8182e44eac53dc64f5c06cdbce752509a343fe9331e2ee8db433831385`.
Lint/build allocations were about 103/366 MB and simulation 7 MB, with no OOM.
