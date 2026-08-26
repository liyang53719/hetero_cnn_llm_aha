# L5 Qwen2 q384 prefill closeout

Status: PASS. L5 remains IN_PROGRESS for q1024 prefill and decode
128/1024/4096.

The q384 path uses the same runtime-configured RTL sources and compiled binary
as q128 for every functional class. QKV, split-half RoPE/GQA, causal streamed
M/L/O, OProj/residual/norm2, gate/up, SiLU/product and down/final all pass their
frozen numerical models. No full attention score matrix is materialized.

The final q384 output SHA256 is
`bff9f576c195042d3bb772a7ba39c727f4eab0bcfc041752aed24081f885b31c`.
The unified controller measures 35,094,528 physical Matrix steps and
202,769,664 active cycles. At 1 GHz this is 202.770 ms per block and 1,893.77
token/s for the block. Payload numerics and controller cycle measurement remain
separately classified.
