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

## Unique next action

Connect descriptor tile iterator to repaired strided DMA, generalize existing
row-major-to-K-major staging, then real Matrix payload and output DMA.
Tile ACK must follow checked output writeback. Compare DDR values.
Do not report schedule enumeration cycles as measured Matrix/model cycles.
Keep useful MACs separate from executed/padded MACs.
