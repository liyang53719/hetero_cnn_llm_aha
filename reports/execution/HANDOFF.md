# Current handoff: three-model q1024 performance recovery

- Goal ACTIVE. Plan: reports/THREE_MODEL_Q1024_PERFORMANCE_PLAN.md.
- Branch main; all code generated from canonical sources, no generated RTL hand edits.
- Full-request q1024 measured models: 0/3. Operator/canary/DC PASS is not this gate.
- BF16 peak: 512 MAC/cycle at 800MHz = 409.6 GMAC/s; full-request utilization unknown.
- CPU8-23, one heavy task, Verilator j4, DC8, MemoryHigh24G/Max30G,
  MemAvailable>10GiB, disk>50GiB, timeout600s, blocking waits.
- Preserve two user runtime scripts; never commit PDK, upstream trees or large results.

## Verified current progress

- Receipt admission: 12 tests; rejects synthetic/incomplete/old-clock measurement.
- Exact-depth endpoint: six opcodes K4, 12288 FP32 comparisons PASS.
- Runtime-K local-memory payload: same RTL K1/4/17/1536 PASS.
- Tail/admission: 3584 output/sentinel locations, seven illegal requests PASS.
- K1536 local-memory tile: 8663 cycles, 786432 useful MACs =17.73% tile utilization.
  This is not DDR/full-request performance; serial A/B supply and one context remain.
- Descriptor iterator: Qwen2 3072 tile addresses/order checked, but test tile ACKs
  synthetic. Generic tails and >4GiB address checks PASS.
- Fixed real iDMA expander bug: noncontiguous rows formerly truncated at1024/64B.
  Row+offset iteration now sends every chunk/tail.
- Unit expansion: 841 requests/109000 bytes. Pinned iDMA VCS: 2383 requests,
  3373 read/write beats, 3073B load and129B store strided rows, zero backend errors.
- Report: Q1024_IDMA_STRIDED_CHUNK_RESULT.json. Backend test checks requests/beats;
  it does not establish destination byte equality.
- Modified endpoint/payload/DMA and combined DC remain stale until rerun.
- Runtime transpose: fixed1KiB buffer, K1/17/32/33/1536/8960 PASS, 338528
  checked16-bit locations; bounds/overlap/read errors checked.
- Replaced existing norm loader transpose: 24576 BF16 values exact.
- Existing group8 batch2 Matrix chain revalidated: 147456steps, 75497472MACs,
  49152 BF16 outputs exact; 48 weight tiles loaded once. DMA remains behavioral
  in that harness, rows are repeated canonical16; not q1024 numerical closure.
- K1536 transpose source reads reduced24576->768 with unchanged output layout.
- Evidence Q1024_RUNTIME_TRANSPOSE_RESULT.json; latest readiness hashes updated.
- Recovered existing first9 same-run pinned-iDMA/AXI/L2/Matrix/SFU chain; current
  source revalidated, DDR intermediate outputs checked without injection.
- Exact first9 rows16 ROI: 1247233cycles, 50331648 usefulMACs, ~7.88% wall
  Matrix utilization; 6477952/188416 DDR read/write bytes. This is a fragment
  on ideal axi_sim_mem, NOT calibrated LPDDR or complete-layer/model performance.
- Report qwen2_first9_tile16_pinned_idma_result.json now includes fragment metrics.

## Unique next action

Reuse first9's verified pinned-iDMA/AXI/L2 wiring to connect the generic descriptor
tile iterator, runtime transpose, Matrix payload and checked output DMA.
Add calibrated DDR bandwidth and attribution counters before full-request claims.
Tile ACK must follow checked output writeback. Compare DDR values.
Do not report schedule enumeration cycles as measured Matrix/model cycles.
Keep useful MACs separate from executed/padded MACs.
