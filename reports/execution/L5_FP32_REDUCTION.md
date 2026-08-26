# L5 FP32 add, multiply and reduction

Status: PASS primitive group; L5 remains `IN_PROGRESS`.

Pinned HardFloat FP32 add/mul passes 10,000 bit-exact vectors and the invalid
Inf-times-zero case. Generated ALU SHA256 is
`5ebf571d028c02ebb21d892f13461ba81a36845b02a7671d6f7906ddd216eef0`.

`fp32_reduce16` is a balanced 15-adder tree with elastic input/output registers.
It passes 10,000 vectors generated with the same pairwise FP32 rounding order,
accepts one vector per cycle, and produces FNV64 `eb1a9f9acb34f5b5` in 12,503
backpressured cycles. Only the expected inexact flag is observed.

This closes reduction/add/mul primitives, not the complete heterogeneous SFU.
