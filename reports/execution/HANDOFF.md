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
  Matrix utilization; 6477952/188416 DDR read/write bytes.
- Replayed at1.25ns with100/40GBps bandwidth envelope: numerical PASS, same
  cycles, zero DDR throttle cycles. This is not a DRAM bank/refresh/latency model.
- Bandwidth model unit:10k saturated+10k random cycles PASS; 128B credit cap.
  AXI512 port max51.2GB/s at800MHz. Report Q1024_DDR_BANDWIDTH_ENVELOPE_RESULT.json.
- Report qwen2_first9_tile16_pinned_idma_result.json now includes fragment metrics.
- First9 attribution conserved: DMA pending611467 (49.0%), local read response
  pending226048 (18.1%), Matrix accepted98304 (7.88%), Matrix ready stall0,
  other311352 (includes SFU work). Q/K/V operation cycles total1089337.
- Evidence Q1024_FIRST9_ATTRIBUTION_RESULT.json. Counts are priority occupancy
  buckets, not proof all waiting cycles can be eliminated.
- iDMA audit found default rsp.error tied0. Wrapper now captures AXI SLVERR/
  DECERR, drains current flat transfer, fails closed until reset. Error injection,
  response hold4cycles and reset recovery192bytes PASS; upstream untouched.
- Fall-through response buffer avoids consumer-ready deadlock without extra normal
  cycles. First9 remains1247233cycles;2383-flat normal regression PASS.
- Q1024_IDMA_ERROR_RESPONSE_RESULT.json; no multi-outstanding enabled; wrapper DC stale.
- Packed group8 weight layout PASS: Matrix weight K-stride runtime; same768KiB.
  Q group8 batch2:49152 BF16 outputs exact, weight DMA requests48->6, bytes unchanged.
- Separate pinned DMA:786432 destination bytes exact; 1536flat requests/group
  instead of12288 for8 independent column tiles. No joint speedup claim yet.
- Removed elaboration BATCH_COUNT; controller runtime input1..64. Same control
  binary tested1/2/64, rejected0/65, snapshot checked. Trace-only not numerical.
- Evidence Q1024_PACKED_GROUP8_RESULT.json. Payload/scheduler DC stale.
- Joint packed group8 + pinned-iDMA + AXI/L2 + Matrix + DDR now PASS:
  49152 BF16 outputs exact, 11328flat requests, 917864ROI cycles,
  75497472 usefulMACs (16.065% fragment utilization), DDR throttle0.
- Only norm input/weights preloaded; no L2/output injection. Joint test now uses
  genuine token rows0_31, no repeated-row fixture.917864cycles/49152 outputs PASS.
- Golden generators accept token offset and separate output directories; row
  manifests pin token IDs/slice hashes, model revision and norm file hashes.
- Q1024_GROUP8_JOINT_PINNED_IDMA_RESULT.json holds source/log hashes and limits.
- True rows0_31 Q/K/V now all PASS in one runtime-selected binary, same hardware:
  Q49152 outputs/917864cycles; K8192/149154; V8192/149154; DDR throttle0.
- Separate projection results use Q1024_GROUP8_JOINT_PINNED_IDMA{,_K,_V}_RESULT.json.
  Do not sum independent ROI runs into a full decoder/model performance claim.
- Small VCS cross-process save/restore PASS: debug_access+r required; restore
  starts atcycle78, ends1000;235 complete state records match baseline exactly.
- Saves static/associative memory, dynamic queue, pipeline state. Evidence
  Q1024_CHECKPOINT_CONTINUITY_RESULT.json; this is not yet a real accelerator checkpoint.
- Real K projection cross-process checkpoints now PASS atcycle15993 (DMA busy224,
  flat761) and47993 (partial K870). Both restore8192 exact outputs/149154cycles.
- Q1024_REAL_CHECKPOINT_RESULT.json. Keep .chk + .chk.FILES + .chk.ucli together;
  never rebuild simulator/shared libraries during a chain; snapshots stay ignored.

## Unique next action

Reuse first9's verified pinned-iDMA/AXI/L2 wiring to connect the generic descriptor
tile iterator, runtime transpose, Matrix payload and checked output DMA.
DDR ceiling, ROI attribution, fail-closed iDMA errors and packed group layout verified.
q1024 fixtures COMPLETE: original1024 tokens have13 distinct IDs, all covered by
verified layer0 norm/raw QKV rows. Exact token-keyed golden reuse only; forbidden
for RoPE/attention/later layers. Full-fixture first32 K numerical PASS.

Continuous K segment0 VALID atcycle799993/144384 Matrix steps. Do not rebuild
simv_group8_checkpoint or regenerate fixture identity during this chain.
Segment1 reached1599993 but is FAILED: nested Tcl restore corrupts UCLI variable
restoration (readonly synopsys_root); do not resume from segment1.
Original snapshots retained, not edited. Canonical initial Tcl restored to its
saved hash24ea0b46. New resume script uses top-level restore and external locked
next-path control. This fix still needs chained validation and explicit retry.

Next: add failed-attempt retry preserving receipt/log/snapshot, test top-level
restore/save chaining, then retry segment1 from valid segment0. Report
Q1024_CONTINUOUS_REPLAY_PROGRESS.json. No full q1024 numerical PASS yet.
Tile ACK must follow checked output writeback. Compare DDR values.
Do not report schedule enumeration cycles as measured Matrix/model cycles.
Keep useful MACs separate from executed/padded MACs.
