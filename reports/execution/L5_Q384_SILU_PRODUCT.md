# L5 q384 SiLU and gate-times-up

Status: PASS; q384 down/final remains pending.

The q128/q384 testbench is compiled once and selects only runtime workload and
vector paths. On q384 it checks 3,440,640 SiLU scalars and 215,040 16-lane
products against the frozen operation-order model. The same binary then
re-runs q128 without recompilation.

Measured q384 latency is 31,180,800 cycles: 30,965,760 SiLU cycles and 215,040
product cycles. SiLU/product SHA256 values are
`8fd5ff3f96e255ea246ecb5fc1c0bb94041a588c4d3307beb587f19e93a8fcb4`
and `8e2484ecca62c93071ecd7c4f0c3ae9cf0933a6cd652124ba379c9b9b72f0f15`.
The maximum SiLU error is `5.32558411e-05`, below the fixed 0.002 limit.

The shared binary SHA256 is
`7e651ef94b3fd496c0b400e9a9638cd2312c0f5270e3b5da0dddfeda61e25ce4`.
The q384 and q128 product FNV64 values are `0f730832ba0b1bf6` and
`846f7a0cfdae4c97`. Simulation allocation was 59 MB with zero OOM events.
