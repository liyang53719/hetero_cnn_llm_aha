# L4 pool and residual closeout

Status: PASS. L4 remains `IN_PROGRESS`.

The dedicated INT8 SFU tile passes 100,000 arithmetic operations and is
integrated into canonical SFU channels 0/1 through a transaction-locked mux.
The original AHA/KV stream and full L3 combined 100k regressions remain green.

- standalone RTL: 50k max-pool plus 50k saturating residual operations,
  750,000 cycles, FNV64 `36668a808367d67f`;
- canonical endpoint: 10,000 round trips and 20,000 Matrix completions;
- max-pool trace: 6 cycles, 80 semantic/128 physical bytes, 3 conflicts;
- residual trace: 7 cycles, 192 semantic/physical bytes, 3 conflicts;
- strict lint and all data/BE/tag/tensor/last/format checks pass.

Because Gemmini ExtMem read responses lack byte enables, dedicated direct
outputs are zero-filled and presented as one full 512-bit beat. Semantic BE is
retained inside the arithmetic tile; masked partial-tail persistence must use
the Shared-L2 fallback path.

Evidence: `reports/execution/l4_pool_residual_result.json`,
`scripts/run_l4_pool_residual_complete.sh`, and
`work/results/l4_pool_residual_canonical/tb.log`.
