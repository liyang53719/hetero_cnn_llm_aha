# L5 q384 QKV numerical batches0-23

Status: PASS; downstream q384 phases remain `IN_PROGRESS`.

Twenty-four restartable16-token batches use one four-thread RTL binary and
exact operation-order goldens. Every batch measures98,304 Matrix steps and
401,504 cycles with all norm/Q/K/V nodes passing. The parameterized binary also
reproduces the historical q128 batch0 hashes exactly.

Aggregates are2,359,296 Matrix steps and9,636,096 cycles:9,437,184 Matrix,
149,760 RMS and49,152 bias cycles. Input/norm/Q/K/V SHA256 values are
`6a372c48...`,`77965488...`,`a5d2e31e...`,`69a7f29c...`,`71db3e37...`.
Build allocation was1,240 MB; each simulation101 MB. No OOM occurred.
