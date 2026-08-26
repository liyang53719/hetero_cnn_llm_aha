# L5 Qwen2 q1024 prefill contract and unified controller

Status: PASS for operation-count contract and controller; numerical payload and
measured latency remain pending.

The same runtime controller used for q128/q384 now has an 11-bit sequence
field and accepts 128, 384 and 1024 in one compiled binary. It rejects 256.
There is no q1024-specific RTL source selection.

The q1024 contract freezes 64 physical 16-token row batches, 93,585,408
Matrix steps, 917,504 RoPE pairs, 6,297,600 causal dot/online updates, 12,288
reciprocals, 98,304 normalization chunks, 9,175,040 SiLU scalars and 573,440
product chunks. It requires streamed causal attention and zero score-matrix
writeback.

Cycle fields remain null until the q1024 payload phases pass. The current
670,480,384-cycle figure is only a pre-execution expectation and must not be
reported as measured.
