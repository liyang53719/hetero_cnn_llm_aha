# iDMA logical read batching: component-verified candidate

Base remote source: 6fe37991d98402114689377a93dea7892e875ac3.
The Chisel adapter has an opt-in maxBeats=64 mode. Default remains 16; Host production is not switched by this commit.
One unchanged pinned iDMA backend splits each 4-KiB logical read into <=16-beat physical AXI segments. A registered four-entry segment tracker validates each segment and preserves the final whole-transfer commit fence. Stores remain <=16 beats.

Current sandbox results: actual Chisel compilation/emission, Verilator and retained-iDMA test exit 0; 22 streamed cases (including three read-fault/reset pairs and a five-request timing comparison), one ordinary metadata read. Each accepted payload word is checked by the existing independent address oracle; stalled data/control and final backend commit are checked.
A same-DUT microtest took 317 cycles for four 16-beat requests versus 288 for one 64-beat request. These are component counts with the original jitter algorithm, not whole-request utilization or a 50% PASS.

Initial elaboration detected a combinational loop in a fall-through segment FIFO. The final design uses a registered FIFO; the failed output directory is retained.

Reproduce: `bash chisel/continuous_prefill/scripts/run_idma_read_batch_gate.sh /absolute/NEW/output`, with the existing locked IDMA_EXPORT and compiler environment. No manual RTL editing.
Dense and complete Host real16 two-layer integration are subsequent gates; no automatic production switch or full-network claim is made here.
