# L5 target gate and up projections

Status: PASS as the sixth restartable target-shape segment; L5 remains
`IN_PROGRESS`.

The segment consumes the exact norm2 hash. Two independent, bias-free
1536x8960 BF16 matrices run in restartable gate and up phases on the unchanged
physical 16x32 BF16/FP32 array. All 8,960 outputs of each projection match the
operation-order model.

Each phase reports exactly 430,080 array steps and 1,720,320 cycles; combined
steps are 860,160. Gate/up FNV64 values are `0127a2ddb01d86d6` and
`bb6b92bf6e34ad36`. Gate weight/output hashes are `d3ad4b84...`/`ec204a74...`;
up values are `dc769e1a...`/`581709c8...`.

Strict lint/build allocations were about 492/745 MB. Each simulation allocated
45 MB and completed without OOM.
