# L5 q384 causal streamed M/L/O and O/L

Status: PASS; q384 OProj/MLP/down remain pending.

One runtime-configured M/L/O binary executes workload384 then workload128
without recompilation. q384 performs887,040 causal dot/online updates,4,608
reciprocals and36,864 normalization chunks with no score matrix.

Measured totals are29,313,792 cycles:23,950,080 dot,5,308,416 online,18,432
reciprocal and36,864 normalization. Attention SHA256 is `901a32a4...`; maximum
true-softmax error is `7.23469859e-4`, below0.002. q128 compatibility FNVs are
unchanged. Shared binary SHA256 is `3024a1e6...`; build allocation996 MB and
simulation60 MB, with no OOM.
