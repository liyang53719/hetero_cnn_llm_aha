# L5 target SiLU and gate-times-up

Status: PASS as the seventh restartable target-shape segment; L5 remains
`IN_PROGRESS`.

The segment consumes exact gate/up hashes. All 8,960 gate lanes pass through
the proven stable FP32 SiLU, then one physical 16-lane multiplier tile executes
exactly 560 gate-times-up chunks. Every SiLU and product output matches the
operation-order model.

Measured totals are 81,200 cycles: 80,640 scalar-SiLU and 560 product cycles.
SiLU/product FNV64 values are `1b452878ca70ee00` and `c6999069e8808987`.
SHA256 values are `bd6c5d5562a086545a0953721b0984420bff1ba909ff9a4ba3b78bfb732f932e`
and `5076748a33e3b316acc2647554cea7d193b50099d6fa40ebdb1dec67a716fb1c`.

Maximum SiLU error against the true function is `5.29363902e-5`, below the
frozen `0.002` limit. Lint/build allocations were about 56/319 MB and
simulation 7 MB, with no OOM.
