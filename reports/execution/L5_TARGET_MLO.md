# L5 target streamed M/L/O and O/L

Status: PASS as the third restartable target-shape segment; L5 remains
`IN_PROGRESS`.

The segment consumes exact Q-RoPE, rotated-K-GQA and V-GQA hashes. Each of 12
heads streams two dot128 scores through the pinned scale `0x3db504f3`, updates
the LANES=128 online-softmax state in token order, computes one reciprocal L,
and normalizes O over eight physical 16-lane chunks. No score file or matrix is
created.

Final M, L, O and all 1536 attention lanes match the operation-order model.
Measured totals are 900 cycles: 648 dot, 108 online-update, 48 reciprocal and
96 normalization cycles. O and attention FNV64 values are
`5043ca46aa8a793e` and `271fc94d3914bf2b`. The attention SHA256 is
`86c06c97e24153ce786b30f4e15fb7b76f48eacf2126adc33be94412837eb681`.

Against true two-token softmax using the same streamed scores, maximum
attention error is `3.11093333e-4`, below the frozen `0.002` limit. Lint/build
allocations were about 475/797 MB and simulation 12 MB, with no OOM.
