# Bounded raw Dense → official Bias handoff candidate

**Source-only, default off; no production/Chisel wiring, hardware cycles,
full-block execution, or changed acceptance contract.** This is a small actual
payload/ownership/ACK model plus an integer byte ledger, not a DMA throughput or
whole-block schedule simulator. The unreviewed frontier sibling is not imported.

## What executes

The caller reserves one of three output-tile credits before presenting a real
4096-word FP32 raw tile. Storage corresponds to the existing two 16-KiB service
FIFO entries plus one 16-KiB `finalValue`; it is separate from the five-context
80-KiB accumulator and proposed 80-KiB frontier reuse. There is no overflow list.
Raw tiles use logical M128×N32 row-major coordinates, with explicit panel and
tensor identity. This model does not generate projection values or claim that
the projection FMA graph executed.
Reservation represents an accepted root operation, including an outstanding
producer-return obligation. Abort retains every such tag (at most three) until
its matching return drains. Wrong return identity poisons without consuming the
original obligation; a matching error/nonfinite return drains but cannot publish.

The consumer has two 64-B bias cache packets and one held 64-B output packet.
These are candidate reuse of scalar packet registers/request storage, subject
to a new paired-mode ownership gate. Each accepted raw packet computes the
existing reviewed integer FP32 `add`, then one BF16 RNE, preserving the resulting
BF16 word in a **32-bit FP32 container**. There is no pre-bias rounding. Accepted
domain is finite inputs/intermediates/results, including signed zero/subnormals;
overflow is rejected. Arithmetic latency is not modeled or asserted free in a
hardware prediction: this class validates event causality and payloads only.

One shared DMA object accepts at most one 64-B request, including competing X/W
reads, bias-cache reads and final writes. The request identity includes epoch,
sequence, kind, coordinates and address. A missing ACK holds the packet/credit;
a wrong tag poisons without dropping the original accepted transaction. Abort
stops admission, clears unissued work, drains accepted traffic and never publishes
success. This uses the conservative original request granularity; it does not
implement/claim the proposed strided multi-beat ABI.

`producer_done` means all raw packets were accepted and their biased values were
safely captured. It can precede the final write ACK. `done` additionally requires
all final Bias DDR write ACKs and an empty common DMA port. Neither synthesizes
the old raw DDR write/publication fence. The paired interface must be integrated
explicitly rather than calling an old raw-output stage successful without writes.

The optional debug callback observes the actual raw payload at the same
`accept_raw` event; it cannot inject values. The tests reconstruct all K raw
coordinates from that stream. The callback is a testbench observation sink, not
unbounded candidate hardware storage. Hardware DDR debug export costs another
14,336 Q+K beats, explicitly selectable in the ledger. This synthetic test does
not substitute for the future full same-stimulus reference comparison.
An observer exception poisons after the accepted event, retains outstanding
producer/DMA return obligations, and can never produce successful completion.

## Complete byte boundaries

All floors assume a single shared total 512-bit data path. They omit protocol
gaps, arithmetic/control cost and final drain, so they are necessary bounds only.
The current Q and K owners each reload X; one shared cold X below requires an
explicit **new resident lease**, not implemented by current jobs.

| Q+K boundary | One new shared X lease | Current two X loads |
|---|---:|---:|
| X FP32 wire read beats | 12,288 | 24,576 |
| W BF16 read beats | 86,016 | 86,016 |
| Standalone raw DDR output beats | 14,336 | 14,336 |
| Standalone transfer floor | 112,640 | 124,928 |
| Fused final Bias FP32-container writes | 14,336 | 14,336 |
| Optimistic per-panel cached bias reads | 112 | 112 |
| Fused floor through final Bias ACK | 112,752 | 125,040 |

Useful projection issue equivalents are 86,016. Even the new one-X case has
standalone ceiling 76.3636% and fused-final ceiling about 76.2878%. The internal
raw-consumed boundary excludes final materialization and is never substituted
for the combined final-write boundary. Fusion saves raw writes plus raw Bias
reads **once**, 28,672 beats = 1,835,008 B, relative to an equally bias-cached
unfused path. Original uncached Bias rereads add another 14,224 beats; that
separate caching improvement is not credited as handoff savings. A local ceiling
below 80% does not prove a whole-block ceiling below 80%.

`warm_fullblock`, `hardware_cycles`, and `hardware_utilization` remain null. No
upstream resident proof, independent memory channel or packed-BF16 final wire
format is assumed.

## Minimal future wiring and tests, not performed here

1. Add default-off paired Dense/Bias begin admission: match epoch, both jobs,
   tensor shape, Dense raw destination/Bias source and non-overlapping final
   spans. Fence both old owner modes; preserve all legacy readers and defaults.
2. Reserve the existing three result credits before root emit. Route
   `finalValue` to a tagged `(panel,row,half)` 16-lane raw stream. Retain one
   consumer output packet until its real DMA ACK; never borrow frontier slots.
3. Add coordinate-aware Bias cache and FP32-add-then-RNE output. Account the
   actual Vector16 ALU and RNE latency. Current Chisel Bias only add/stores;
   the official software rounding boundary is not already wired there.
4. Keep a distinct raw-consumed producer acknowledgement and final materialized
   consumer acknowledgement. Shared abort/drain poisons both; only the latter
   completes the paired writeback fence. Retain original standalone raw DDR mode.
5. Unit-test old-mode equivalence, reader isolation, fixed tile credits, wrong
   identity/epoch, final ACK loss, mixed memory errors, output backpressure and
   actual raw-fire debug comparison before any broader run.

## Source evidence

- `candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseOwner.scala`
  lines 40–44 (`finalValue`), 131–158 (capture/layout), 164–194 (real output ACK).
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala`
  lines 7–22 (two independent output FIFO entries), 49–58 and 77–85 (metadata,
  emit credit and existing result-reader contract).
- `candidates/qwen2_resident_matrix/official_bf16/owners.py` lines 62–70:
  actual raw read, FP32 bias add, then BF16 materialization, FP32 wire containers.
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala`
  lines 512–515: current owner-driven Bias add/store; new RNE route still needed.
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockWritebackFence.scala`
  lines 7–11, 37–67: successful real ACK coverage, poison and pending fence.
- `candidates/qwen2_resident_matrix/ffn_public/prefix_execution.py` lines 152–169:
  current terminal/publish requires exactly-once physical DDR coverage.

## Reproduce

From the repository root:

```sh
/workspace/shared/hetero-contracts-venv/bin/python -m pytest -q candidates/qwen2_raw_bias_handoff/test_model.py
/workspace/shared/hetero-contracts-venv/bin/python -O -m pytest -q candidates/qwen2_raw_bias_handoff/test_model.py
/workspace/shared/hetero-contracts-venv/bin/python -m candidates.qwen2_raw_bias_handoff.model
```

Fourteen tests: finite post-add rounding, opt-in/admission, three tile credits,
payload/backpressure, shared W/Bias DMA contention, wrong ACK drain, bad payload
abort, complete same-stimulus K observation/address coverage and final fence,
missing/error ACK, complete cold byte/savings boundaries, wrong producer epoch,
abort with accepted roots, nonfinite producer return, and observer failure.
