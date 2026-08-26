# L5 q1024 QKV batches 0-63

Status: PASS; q1024 RoPE/GQA remains next.

One unchanged runtime-configured QKV RTL binary executes all 64 q1024
16-token batches, followed by q128 and q384 batch-0 compatibility runs without
recompilation. Every batch passes RMSNorm, Q/K/V projection and bias checks.

Each batch measures 98,304 physical Matrix steps and 401,504 cycles. The
aggregate is 6,291,456 steps and 25,696,256 cycles: 25,165,824 Matrix, 399,360
RMSNorm and 131,072 bias cycles.

Concatenated Q/K/V SHA256 values are
`4e67c4cc15bf3a72ea1f49b773832f411ff6b7445352887b9c60fe5ef0728e0f`,
`7a1daa90c38a3d680827e1663984d7bb9b63ee2298a78226a94fe2c8014c85de`
and `1853b21c3f348d347cf42adb5a996964c546fa5f88f01954769f45d6d5f7829f`.
The shared binary SHA256 is
`8f9a561ea23cc2df9bcbe2da8dddf7740d830c4d2b80df0a81b960a48e2ce085`.
Build allocation was 1,240 MB and each simulation allocated 101 MB; no OOM.
