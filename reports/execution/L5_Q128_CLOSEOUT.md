# L5 q128 prefill closeout

Status: PASS for q128; L5 remains `IN_PROGRESS` for q384 and decode contexts.

The hash chain covers all128 tokens from input RMS/QKV through split-half RoPE,
post-RoPE GQA,99,072 causal streamed M/L/O updates, OProj, norm2, gate/up,
SiLU/product, down and final residual. No score matrix is materialized.

Segmented RTL payload measures11,698,176 Matrix steps,46,792,704 Matrix cycles
and61,101,824 active cycles. The separate24-command RTL trace controller
reproduces the same step/cycle totals with zero score commands. Final q128
SHA256 is `39bb6930340ecc70a81e508f2ecde0006ba933dd9e175a051441ccd3e4004b8d`.
