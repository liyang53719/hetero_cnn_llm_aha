# L5 FP32 RoPE pair

Status: PASS primitive; L5 remains `IN_PROGRESS`.

The registered ready/valid primitive computes even*cos - odd*sin and even*sin
+ odd*cos using four separately rounded HardFloat multiplications and two
HardFloat additions; it does not silently use fused operations. Ten thousand
float32 operation-order vectors pass under output backpressure with one-pair
per-cycle acceptance. Output FNV64 is `69a2b272f40d4885`; only expected inexact
flags occur.

Sin/cos coefficient generation remains outside this primitive and will be
provided by the frozen RoPE program/controller.
