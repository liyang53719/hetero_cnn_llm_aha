# Stanford AHA integration/patch policy

No AHA/Garnet/Lake/Canal/PEak source is included here. First reproduce the official Garnet generation and Gaussian map/PnR/test flow with the pinned recursive submodule set.

Order:

1. External 512-bit stream/config/event wrapper; no upstream edit.
2. Real boundary backpressure and skid buffers.
3. PEak semantics and mapper rules for reduction primitives.
4. FP32 reduction tile and BF16 vector operations.
5. RoPE, exp2/PWL, reciprocal/rsqrt, online-softmax state update.
6. Lake memory controllers for tensor tile/reduction schedules.
7. Heterogeneous tile integration in Garnet/Canal graph.

Do not add a large nonlinear unit to every generic PE. Prefer sparse heterogeneous SFU/reduction tiles and retain ordinary PE density.
