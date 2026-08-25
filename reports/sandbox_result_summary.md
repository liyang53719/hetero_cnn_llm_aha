# Sandbox architecture result summary

Status: **PASS**

- CNN exact regression max absolute error: `0`
- BF16 toy Transformer block, contiguous vs paged KV max absolute error: `0.0`
- INT8 KV toy Transformer block max/mean absolute error: `0.00781250` / `0.00206484`
- 32×64 INT8 peak assumption at 1 GHz: `2.048 TMAC/s`
- 500 token/s for an assumed 1.5B dense model requires `36.6%` of that INT8 peak before attention and other overheads.
- 10 token/s requires approximately `15.0 GB/s` W8 or `7.5 GB/s` W4 weight traffic before other traffic.
- SRAM partition sum: `4096 KiB`; declared total: `4096 KiB`.

The cycle estimates in `architecture_results.json` are architecture models, not measured RTL results. W4 storage-only mode halves weight bytes but retains the INT8 MAC rate. The 4.096 TMAC/s W4 value is a future native dual-dot target and must not be claimed until RTL simulation and DC synthesis close.
