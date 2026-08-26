# L5 q1024 RoPE and GQA

Status: PASS; q1024 causal M/L/O remains next.

One runtime-configured binary executes q1024, q128 and q384 without
recompilation. q1024 checks 786,432 Q and 131,072 K split-half RoPE pairs,
then performs post-RoPE K and V GQA multicast to 196,608 outputs.

Measured q1024 latency is 3,932,160 cycles: 3,670,016 RoPE and 262,144 GQA
cycles. Q-RoPE/K-RoPE/K-GQA/V-GQA SHA256 values are `68c1313d...`,
`f5c9918e...`, `901bab11...` and `350e3167...`. The shared binary SHA256 is
`53558f8b05e43964ed14c24252b2a0c6b6db5121c7d80b6f282af9bee211dbfe`.
Build allocation was 433 MB and simulation allocation 34 MB, with zero OOM.
