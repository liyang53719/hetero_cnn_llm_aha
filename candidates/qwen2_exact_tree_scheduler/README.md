# Exact original tree: five contexts and two A slots

Status: **executable software arithmetic + event-scheduling candidate only**.
No Chisel/RTL execution, synthesis, official model/full-block run, CI run, or
hardware performance claim. Only this new directory is changed. Base source:
`810866d9fb137d45c7261c8d65ea1d4085faacc3`.

## Run the small checks

```
python -m pytest -q candidates/qwen2_exact_tree_scheduler/test_model.py
python -m candidates.qwen2_exact_tree_scheduler.model
```

Tests compile only the small local host oracle, into pytest's temporary folder,
with `-fno-fast-math -ffp-contract=off -fno-tree-vectorize`. Require an x86 host,
`g++`, RNE, and FTZ/DAZ disabled. They neither import nor execute full-block code.
`arithmetic.py` uses integer exact significands and one binary32 RNE rounding per
Add/FMA; the independent C++ oracle uses actual host `fmaf` and the source loop.
The accepted numeric domain is finite operands **and finite intermediates**,
including gradual underflow, signed zero and cancellation. Overflow/NaN/Inf are
explicitly rejected. No claim of coverage for all IEEE exception payloads.

## The exact graph, not a reassociated sum

For each of 4096 physical M16×N256 outputs, partial p has 24 ordered operations:
`partial[p] = fma(A16[64*t+p], B256[64*t+p], partial[p])`, t=0..23, initialized to
positive zero. Physical slices remain different N columns. They are not the
logical reduction lanes. Keep FP32 throughout; no bias/RoPE or BF16 boundary
moves. The original explicit final `+0.0f` is a separate operation.

The original register offsets 4,2,1 followed by lane offsets 4,2,1 yield four
complete 16-leaf trees, named for their lane pair: S04, S26, S15, S37.
S04 DFS leaves are 0,32,16,48,8,40,24,56,4,36,20,52,12,44,28,60.
The other trees have the corresponding lane-pair residues. `SUBTREES` retains
every original ordered left/right edge. A depth-four tree needs five contexts.

1. Compute S04; commit to A0 and release its context.
2. Compute S26; restore S04; add T0=S04+S26; commit T0 over consumed A0.
3. Compute S15; commit to A1 and release its context.
4. Compute S37; restore S15; add T1=S15+S37.
5. Restore T0; add ROOT=T0+T1; perform original ROOT+0.

Exactly three 16-KiB A writes and three 16-KiB A reads. No other partial spill,
no six-context allocation, no result-FIFO borrowing, no multiply-by-zero hold.
A context is released only after its consuming Add return or full spill fence.
The A slot cannot be overwritten until its previous value has been restored.
The decoder validates canonical FMA names and independent per-context progress,
all ordered tree edges, spill identity, single-consumption restore, ROOT→RAW zero
tail and RAW-only output. Actual A-fill/B-fill completion gates FMA issue; B is
bound to its partial p. Numeric and event engines independently interpret the
same Op program; they are not a payload-carrying transaction cosimulation.

## New interfaces: explicit, conditional, currently unimplemented

`wide_candidate` assumes a **new opt-in exact-tree mode** with these interfaces:

- Ordered FP32 `Add(dst,lhs,rhs)` and `AddZero(dst)` using the SAME 4096 FMA cells'
  internal arithmetic path. Default model latency is five stages. This requires
  full FP32 injection, two-context source selection, write arbitration and new
  rounding/control. Existing BF16 FMA input ports cannot perform this operation.
  Reuse of the internal path without extra arithmetic lanes is an architectural
  assumption requiring datapath implementation/synthesis; it is not established.
- New 64-byte context-packet read and committed-write/restore ports. Contexts are
  locked for the entire vector transfer. No hidden 16-KiB restore buffer exists.
- New A transaction acceptance/commit receipt and whole-slot fence. Existing
  SyncReadMem writes have no such external ACK interface. A commit receipt must
  prove the write landed; a fixed delay or response timeout is not a receipt.
- New owner/command mode must permit tagged context lifetimes and Add/restore.
  Existing MatrixPipeline `seen/closed/clear/last` rules cannot simply accept
  this instruction stream. The default legacy command path remains unchanged.
- Every accepted operation keeps epoch, tile, sequence, node, context, rhs, slot,
  partial, k, packet and half metadata until its matching return. Old non-emit
  FMA result returns are still consumed, with credit. Their existing readers,
  metadata FIFO and result buffers remain reserved and unchanged.

`vector16_baseline` changes only Add service to sequential packets through the
existing shared sixteen-ALU loan (default request-to-response latency two),
plus the same **new** context read/write ports. It is not an already wired path.
The current loan's strict exception status also needs validation against the
candidate's finite-underflow domain before claiming hardware numeric support.
No second set of 16 or 4096 arithmetic units is instantiated by this model.

Alternative FIFO-frontier is deliberately not implemented. It would need its
own opt-in producer/consumer ownership mode, readable tagged frontier entries,
capacity accounting including every old non-emit reader, and explicit
retirement/abort semantics. The existing FIFO is not spare accumulator storage.

## Physical ledger and port assumptions

- Existing 4096 MACs; 5×4096 FP32 accumulator words = 80 KiB.
- Keep existing 80 KiB leaf result registers, 32 KiB result FIFO, and 16 KiB
  `finalValue` separately. None is credited as a tree register or spare spill.
- Reserve 384 KiB for the full M128 BF16 A activation allocation, plus two existing
  A slots = 32 KiB: 416 KiB total of 688 KiB. This does not assert existing
  StreamingDense supports M128 resident issue; this candidate issues M16 tiles.
- A slot word mapping: word=2*packet+half; bank=word%16;
  row=768+32*slot+word//16. Slot rows are 768..831; activation rows stay below768.
- The following port mapping uses ordinary StreamingDense bank layout and
  requires a new route/arbitration path. It does not reuse TileBank API semantics:
  current TileBank reads all 16×256-bit banks per 64-byte logical transaction and
  performs read-modify-write, with owner-quiescent single-transaction admission.
  Its flat iDMA wrapper also has one active transfer; internal AXI concurrency
  does not create independent tagged transfers.
- Each A write uses the existing globally selected **one 32-byte bank write**.
  A 64-byte read phase uses two distinct banks. Do not infer dual writes.
  Each bank has separate 1R/1W ports; the physical roofline allows read/write
  overlap even though this conservative scheduler does not overlap them.
- B holds one partial's 24×256 BF16 values = 12 KiB of existing 80 KiB. No double
  buffering benefit or free prefetch is credited. Native B fill uses two banks.
- One additional bounded 64-byte packet hold, one outstanding transaction and
  one held response. Five-stage arithmetic remains physical; this scheduler
  intentionally uses at most one in-flight result. Metadata/control widths,
  FP32 source muxes, context ports, routing and timing/area are unpriced.

## What cycles mean

The default is a deliberately serialized DFS policy, **not the best schedule**.
Each partial's 24 FMAs waits for its own five-stage return. It does not interleave
independent leaves into free contexts, nor issue on the response edge. A future
scheduler may do that within the same five live-context limit and exact graph.

A request costs one accepted issue cycle plus the named positive response
latency. Only matching accepted responses return credit. Missing ACK stalls
forever; the test harness bound fails rather than declaring success. Request
and response backpressure are counted separately. Abort poisons the epoch,
invalidates all context/slot ownership, stops new issue, and drains accepted
transactions. Reset cannot forge outstanding credit; old epoch responses cannot
commit new data. In-flight A writes may land after abort, so the A lease remains
poisoned until drained. This is not rollback.

The modeled boundary is the first cold M16 activation-read request through the
last accepted raw-output write ACK. It includes cold A fill, every B fill,
operand SRAM read, all FMA/Add returns, context transfer, A commit ACK, and raw
output ACK. Descriptor admission, host command transport, bias/RoPE and all other
owners are outside this **projection-tile** boundary. No full-block denominator
is produced. Times/latencies of all new interfaces are conditional parameters.

Default results, before additional backpressure:

- Wide candidate: 88,448 model cycles/tile; model MAC ratio 1.7366%.
- Vector16 baseline: 235,008 model cycles/tile; model MAC ratio 0.6536%.
- 56 independent cold tiles (M128 Q+K): 4,953,088 / 13,160,448 model cycles.
  This deliberately reloads A for each N tile; no cross-tile reuse is claimed.

The separate physical-port roofline uses `max`, not a sum, across independently
usable resources. Wide: max(1536 FMA + 64 Add issue slots, 1536 A writes, 768 A
reads)=1600 cycles, giving a **conditional optimistic 96% ceiling**, not achieved
performance or an 80% impossibility proof. Vector16: 16,384 Add requests with
three-cycle exclusive request/response cadence gives a 49,152-cycle floor,
3.125% ceiling. Both deliberately omit fill, RAW recurrence, transfer, return,
ACK and contention penalties and must not be confused with the serialized model.
For the modeled **cold tile** boundary, the unique B payload is 1536×256×2 =
786,432 bytes. Existing B fill accepts at most 64 bytes/cycle, imposing at least
12,288 write-accept cycles even with perfect compute/fill overlap. Taking max
with the preceding port floor gives a conditional **12.5% cold-tile ceiling**
for wide mode (Vector16 remains 3.125%). This is the relevant cold-fill bound;
96% applies only to the local bound that excludes fills. Neither is a measured
result, nor a whole-block bound. The cold ceiling omits all other costs and
cannot be improved simply by moving the same finite fill to an earlier cycle.
Cross-tile residency/reuse would need a different explicitly bounded scope.
`hardware_cycles` and `hardware_utilization` remain null in every report.

## Read-only source anchors

- `candidates/qwen2_aten_q_projection_candidate/kernel.cpp:49-63`: p=8r+lane,
  k=64t+p, 24 FMA steps, both ordered reduction trees, explicit +0.
- `candidates/qwen2_qk_aten_reduction_candidate/kernel.cpp:19-36`: same graph,
  independent `fmaf`, software-only 64-output partial workspace.
- `rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv:15-16,32-40,51-61`:
  separate five accumulator/result banks, BF16 inputs, five pipeline stages.
- `rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv:21-60`:
  context busy/metadata FIFO and return-driven release.
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala:7-22,49-76,94-110`:
  two result entries, metadata credits, mandatory non-emit output consumption.
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/StreamingDense.scala:47-61,72,123-138,260-275`:
  A/B storage, selected single A write, existing finalValue, A16/B256 mapping.
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/ElementwiseRegisterLoan.scala:27-37,49-57,70-98,118-127`:
  exclusive shared sixteen ALUs, tagged response, abort/loan arbitration.
