# Matrix → resident FFN window candidate

This increment composes on `17baa23c1d540681c52038ea8a224dc7fd96e811`.
It changes the actual Dense owner, shared A banks, internal typed IO and kernel
routing in an isolated, default-off source profile. No production Host fusion,
RTL generation, hardware execution, native acceptance or area/timing result is
claimed. Full Host/kernel sources are typechecked; only bounded owners, banks,
SiLU and their tile harness are elaborated to CHIRRTL.

## Data and lifecycle

`enableFfnWindow=false` preserves both the original profile and the previously
published tiles-on/window-off profile, including ports and normalized IR.
An enabled request carries the complete normal job plus identity, global column
base `ng`, width, gate/up slot and explicit A reuse. `job.n` remains the full
8960-column stride; the accepted window is 32, 64, 96, 128 or 160 columns, with
32-aligned `ng` and widened overflow checks. Ordinary dtype, full-span, alias,
workspace and byte-count validation still applies.

The A lease records base, input dtype, M, K, byte stride and identity. It becomes
valid only after actual A DMA and pending ingress RMW retire at aFence. Reuse
checks every field. Normal command acceptance, low A modification, explicit
invalidation, error, abort and reset invalidate it. Same-edge invalidation wins
over aFence. Accepted memory/Matrix/tile transactions drain before terminal
status; a held completion cannot turn into an early public success.

A Matrix result is consumed before the two-entry result FIFO fills. The existing
16 KiB `finalValue` and eight-bit prefix cursor are reused, with no new result
array. For context c, local column j, row group g and lane l:

- value(l) = finalValue(j % 16)(128*(j/16) + 16*g + l)
- tile.index = g*cols + 32*c + j

The bank's optional Matrix producer order accepts this context-major write
sequence. Its bit exists only in the enabled window profile. Sealed reads keep
the original row-group-major order. Producer order is a begin-only attribute;
seal/release validate the stored identity and shape. An RMW pauses new operand
bank reads and waits for the accepted synchronous response, while queued Matrix
steps may still progress. Waiting for the whole operand queue would deadlock
with the bounded Matrix result queue and is explicitly tested.

The typed internal result has committed tile beats and `ddrWriteBytes=0`.
It is never sent to the normal owner/Host completion port. Full normal output
spans remain admission requirements; they are not marked DDR-live by this
candidate. SiLU consumes actual sealed gate/up through the same physical banks
and original 16-lane recipe, then writes act into slot 2.

## Evidence and resource limits

- Actual Scala/HardFloat source typecheck: 89 files; 14 CHIRRTL emissions.
- Original-disabled and tiles-on/window-off normalized IR and ports match.
- Net metadata registers added to 17baa: 262 bits (259 owner, 3 bank tag bits).
- SRAM stays 32 banks, 768 KiB, one read and one write per bank. Existing
  finalValue, operand/metadata/result queues and single SFU are reused.
- Added selection, comparison and arbitration logic has not been synthesized.
- Python tests are a source-bound event/port model, not cycle-accurate Chisel.

The frozen real-data host capture executes raw n1 FP32 DDR → BF16 RNE A bank,
BF16 official layer-0 weights → real bank packets → sequential-K FP32 FMA,
actual Matrix result → tile RMW → original SiLU → act. Both raw weight tensors
are addressed through one physical-address map; role/tag never selects a private
memory bucket. All actual outputs complete before independent direct dots or
saved producer outputs are decoded for comparison.

M16/K1536/N32/ng0 and M128/K1536/N160/ng160 each pass. Gate, up and act match both
independent raw-input arithmetic and the prior full-graph v0 producer bitwise.
The M128 case loads 786432 B of FP32 A once; Up performs zero A DDR reads and zero
A ingress RMW. Each projection reads 491520 B of weights and sends 7680 Matrix
packets, yielding five results and 1280 tile beats. Each of the three outputs
has 20480 values. This is a bounded FFN window, not all 8960 columns or a full
block. M16 uses the first 16 rows of the saved M128 n1 input.

Capture/model/tool hashes and any post-capture source difference are explicitly
recorded in `delivery_manifest.json`; later admission fixes do not inherit an
old execution identity. The first attempt stopped before arithmetic because a
trace serializer truncated the internal 64-bit DMA tag; its failure is retained.

CPU time, model ticks and physical SRAM bytes are not hardware cycles, iDMA
measurements or MAC utilization. Every 64 B effective tile transfer uses the
existing wider physical bank ports. The original native/FP32-final FAIL and
pending numerical policy remain unchanged.

## Reproduce

Run `python -m unittest discover -s candidates/qwen2_resident_matrix/ffn_window
-p 'test_*.py' -v` (on one line). The frontend checker uses SHA-locked Maven jars,
fixed HardFloat, and immutable source preimages. Its CLI accepts `--out`,
`--cache` and `--hardfloat`; `--audit-existing` verifies retained compiled source
and IR and runs only the auditor, without Java.

`check_numeric.py --out <new-directory> --only-rows 16`, then `--only-rows 128`,
requires the exact local payload/provenance files in `precision_pins.json`.
It never uploads weights. The CI runs source/control/synthetic arithmetic guards
and frontend checks; it does not regenerate the local actual-model capture.

## Next production closure

1. Prevalidate the public Dense Gate / Dense Up / Activation command group,
   including full descriptors, permissions, events and exclusive consumers.
2. Route the accepted group from Host through the kernel window interface,
   then the existing tile/SiLU bridge. Preserve ordinary DDR fallback.
3. Drain act through the original DDR write/ACK path, using existing finalValue
   for row-major packing; publish only after all true ACKs and release slot 2.
4. Run all 56 N160 groups before the existing full-K Down consumes act. A direct
   act→Down path must first resolve the large-K A reload/high-slot conflict.

These items are open. No private Command128 opcode or repurposed bias field has
been introduced, and no DDR bytes are fabricated for resident completion.
