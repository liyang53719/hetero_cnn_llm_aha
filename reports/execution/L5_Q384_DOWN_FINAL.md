# L5 q384 down projection and final residual

Status: PASS; q384 unified measured trace remains pending.

One runtime-configured RTL binary executes all 24 q384 16-token batches and
then q128 batch 0 without recompilation. Every q384 batch checks the full
8960x1536 down projection and final residual against the C++ operation-order
golden.

Each batch measures 430,080 physical Matrix steps, 1,720,320 Matrix cycles and
1,536 residual cycles. Aggregates are 10,321,920 steps, 41,287,680 Matrix
cycles, 36,864 residual cycles and 41,324,544 total cycles.

Concatenated down/final SHA256 values are
`65df822c1971fbf4bf0e0c31f1911da28464e0904ca2bc356bf98b79b97cf501`
and `bff9f576c195042d3bb772a7ba39c727f4eab0bcfc041752aed24081f885b31c`.
The shared binary SHA256 is
`c1b36373547dce9dd8c30cbbae3d3b48432b62cfe6b329d9621c6e57e557b766`.
Build allocation was 1,204 MB; each simulation allocated 130 MB. There were no
mismatches, timeouts or OOM events.
