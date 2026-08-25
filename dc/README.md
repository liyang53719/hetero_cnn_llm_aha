# 22nm DC gate

The included flow is a standard-cell smoke and timing gate. It does not infer the production 4 MiB memory system from registers. For the final macro build:

1. Replace scratchpad, accumulator, CGRA local memory, shared L2 and KV staging arrays with foundry SRAM wrappers.
2. Add the SRAM `.db` views to `link_library`; keep memory cells as characterized macros, not synthesized flops.
3. Generate a dedicated file list for each upstream-derived macro and run `dc/synth_22nm.tcl` with `TOP`, `RTL_FILELIST` and `STD_CELL_DBS`.
4. Use a 1.0 ns primary clock, 0.08 ns uncertainty and explicit I/O budgets as the initial contract. Tighten or relax only through a recorded architecture decision.
5. A stage passes only with zero unresolved references/unmapped cells, no latches outside intentional arrays/control state, no combinational loops, and non-negative setup slack. Hold, power and congestion remain separate gates.

The current clean-room KV contract uses resettable register arrays and is intentionally small. It is a protocol model, not the production SRAM implementation.
