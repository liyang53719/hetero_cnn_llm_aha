# L5 target down projection and final residual

Status: PASS as the eighth restartable target-shape segment; L5 remains
`IN_PROGRESS` pending controller trace/count.

The segment consumes exact product and residual1 hashes. One bias-free
8960x1536 BF16 down matrix runs on the physical 16x32 BF16/FP32 array, followed
by exactly 96 final-residual chunks through one 16-lane FP32 tile.

All 1536 down and final outputs match the operation-order model. The RTL
counter reports exactly 430,080 array steps. Measured totals are 1,720,416
cycles: 1,720,320 Matrix and 96 residual cycles. Down/final FNV64 values are
`eb523a74de935f4f` and `adaf6bf039064f05`.

Weight/down/final SHA256 values are `d81729d2...`, `51e3f87e...`, and
`872ffcab7daf957e1e4caf3db5c8e063e95bfe760ec5060fcb4264f6c66deffe`.
Lint/build allocations were about 504/758 MB and simulation 46 MB, with no
OOM.
