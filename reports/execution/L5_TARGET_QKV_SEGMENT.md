# L5 target RMSNorm and QKV payload segment

Status: PASS as the first restartable target-shape segment; L5 remains
`IN_PROGRESS`.

Two deterministic hidden1536 tokens pass through the global RMSNorm1536. The
current token then runs a 1536x1536 Q projection; previous/current tokens each
run 1536x256 K and V projections. Every GEMV uses the unchanged physical 16x32
BF16/FP32 array. The 16-lane QKV endpoint applies the pinned FP32 Q/K/V biases
and verifies the six-way GQA mapping and sidebands.

All 16 frozen nodes match the operation-order model. The RTL counter reports
exactly 122,880 physical array steps. Measured totals are 493,100 cycles:
491,520 Matrix, 780 RMSNorm and 800 QKV boundary cycles. Q output FNV64 is
`6fc5d6dc59b3e9e8`; expanded K0/K1 FNV64 values are
`1e473c44ecaff411`/`76e68a3c973e52c5`; expanded V0/V1 values are
`a64b018b4549d685`/`49a990c042b1a079`.

The matrix-weight image SHA256 is
`4beac16c43bdf4ce8f728e6a315ea22a21eb2600fc172ec6fdc8b1d5a7b5fec9`.
The biased Q/K/V hashes are `480793d5...`, `7d81d5a9...`, and `f8c257ca...`.
The next segment must consume those exact biased outputs.

The unrotated expanded `k_gqa` output is mapping diagnostics only and is not an
attention input. Qwen ordering remains bias -> RoPE on Q/K -> K multicast;
V can be multicast directly. Strict lint/build allocations were about
560/814 MB and simulation 27 MB, with no OOM.
