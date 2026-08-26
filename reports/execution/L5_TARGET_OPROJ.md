# L5 target OProj and first residual

Status: PASS as the fourth restartable target-shape segment; L5 remains
`IN_PROGRESS`.

The segment consumes the exact attention and current-token hashes. One
deterministic bias-free 1536x1536 BF16 OProj runs on the unchanged physical
16x32 BF16/FP32 array, followed by 96 FP32 residual chunks through one 16-lane
tile.

All 1536 OProj and residual outputs match the operation-order model. The RTL
counter reports exactly 73,728 array steps. Measured totals are 295,008 cycles:
294,912 Matrix and 96 residual cycles. OProj/residual FNV64 values are
`262952301c1ea9b7` and `4645c71c8f64448d`.

Weight, OProj and residual1 SHA256 values are respectively
`27c1f27c834a25a28ff32d3956e5fff028c1a565e46f9013cb11c91ce55ed6b3`,
`96ded41e243a37dd1e1c385f4486453cfc60fbc0449c14f42d43d0f937b90173`
and `df2d5af8926229b7c3ea34aa7c0dfc1ad381fee5cd7149d86b5b01739f518671`.
Lint/build allocations were about 504/822 MB and simulation 24 MB, with no
OOM.
