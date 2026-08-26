# L5 q128 QKV numerical batches0-7

Status: PASS for complete q128 RMSNorm/QKV; downstream q128 phases remain
`IN_PROGRESS`.

One unchanged RTL binary processes eight restartable 16-token row batches.
Every batch uses all 16 physical rows, performs 16 global RMSNorms and complete
Q/K/V projections with frozen weights and biases. All batch node hashes pass.

Each batch measures 98,304 Matrix steps and 401,504 cycles. Aggregates are
786,432 Matrix steps and 3,212,032 cycles: 3,145,728 Matrix, 49,920 RMSNorm and
16,384 bias cycles. Concatenated norm/Q/K/V SHA256 values are `b77753a3...`,
`90e5f377...`, `59a0989d...`, and `6f12dcc1...`.

The full input SHA256 remains `39917c9e...`. Shared lint/build allocations were
about 568/822 MB; each simulation allocated 28 MB. No OOM occurred.
