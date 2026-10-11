# Retained accumulator seed leaf

Source-only patch against frozen commit `825caff3a6c618419c49c7da452e009ce86ae8b5`.
The seven original source files are unchanged. Apply this patch alongside the
parent service/owner patches in a separate source overlay.

- Patch: `retained_accumulator_seed.patch`
- SHA256: `9d88bfc1e3f071a7fd0027865bd30726bf9f3b5cc2b589cc38f4cebb78366b98`
- `source_manifest.json`: base/postimage hashes keyed by source path.
- `dependency_manifest.json`: 13 actual retained-source dependencies and the
  unchanged generated FMA roots. The ICG hash is its existing required pin,
  not evidence that a physical ICG file was validated during this work.
- `abi.json`: exact optional pin directions/widths and parameter selection.

## Reproduce the checks

From the repository root:

```sh
python3 candidates/qwen2_resident_matrix/transposed_seed/leaf/test_seed_leaf_contract.py
```

Only Python standard library and Git are needed. The test reconstructs seven
frozen files under a temporary work overlay, verifies patch/base/postimage and
dependency pins, applies the patch there, runs 13 source/model checks, and removes
the temporary overlay. It does not modify the tracked source or need preexisting
generated artifacts, a compiler, an SV simulator, network access, or an install.

The eight independent model cases cover all five contexts and 32 clusters,
finite raw-bit preservation, short/duplicate/skipped/extra beats, every identity
field, nonfinite rejection without writes, partial abort, held ACK abort, late
transport, and rejection of busy begin while accepted arithmetic drains. The
explicit token/data cycle model injects begin at input, pre, mul, post/round,
and a stalled result, with and without output backpressure. It checks payload,
flags, result/flags pointers, issue/completion counts, blocked new issue, and no
seed writes before reservation; a raw-begin-freeze mutation must fail. Five
source checks verify patch/dependency pins, the single accumulator write port,
physical lane mapping and valid wiring, registered commit ACK, and optional ABI.
These are source and independent event/cycle-model checks, not retained RTL
execution or clock-gate validation evidence.

## Actual hierarchy and ABI

The actual `qwen2_matrix_command_endpoint` binds the existing outer array, front
controller, scheduler, 32 clusters, and 16 lanes per cluster. Each lane retains
its original `accumulator_bank[0:4]`, result FIFO, and four HardFloat helpers.
Cluster k receives raw words for row k/2, columns (k%2)*16 through (k%2)*16+15.

`RetainedMatrixEndpoint(enableAccumulatorSeed:Boolean=false)` leaves the default
Chisel ABI and parameter map unchanged. Enabled service instances expose the
23 Option pins in `abi.json` and pass `ENABLE_ACCUMULATOR_SEED=1` to the same
actual RTL module. All other retained adapters retain the default constructor.

Shared context/tag/sequence/source-generation inputs remain stable through the
transaction. The parent validates sliceMask and performs selected-leaf all-ready
begin/commit broadcast. Raw arithmetic busy/out-valid exclude seed reservation.
Keep the selected ICG awake throughout reservation, streaming, commit, ACK and
invalidation. Drive seed_abort_i for selected controller invalidation/group abort.

## Transaction and failure contract

Reservation requires genuine arithmetic quiescence and invalidates scheduler and
all lane bank-valid bits. Exactly 32 ordered 512-bit cluster beats write raw FP32
through the same accumulator write port. Both zero signs and all finite subnormals
are preserved. Exponent255 values are rejected. No seed beat enters HardFloat,
result/flags FIFOs, or arithmetic counters.

Commit requires matching identity and count32, then marks every bank valid on
one edge. The identity-preserving ACK is registered after that edge and immutable
under backpressure. Its handshake releases reservation; the parent still blocks
arithmetic until whole-transaction acknowledgement completes.

Busy begin is a terminal rejection/reset-required condition, not ordinary
backpressure: new admission stops immediately, while already accepted FMA data,
results and flags drain intact. Datapath hold begins only after reservation.
Malformed/late transport and abort poison the leaf until coordinated reset.
Abort suppresses concurrent commit; later invalidation clears the remembered bank
even after leaf ACK consumption. resetRequired dominates a held success ACK.

## Resource ledger and limits

- 109 added control FF per endpoint: identity99, count6, reserved/ACK/error/poison4;
  872 FF across eight enabled slices. No payload FF, accumulator, SRAM, or FPU added.
- Per lane: one 32-bit data mux and 3-bit context mux feed one existing bank write
  assignment. Existing bank-valid bits gain reserve/commit/invalidate controls.
- Per cluster: no new state. Seed write selects one of 32 clusters; flags FIFO
  and pointers hold only during reserved seed ownership.
- Buffered control width is 13 by default, 20 when enabled. Additional signals
  are datapath hold/reserve/commit/invalidate/context3. Raw data fans to 32 clusters.
- Per front: 99-bit identity comparison, 6-bit count checks, 16 exponent checks
  and control gates. Default-off constant pruning removes seed state/selections.

This is a source estimate. No SystemVerilog compilation, retained RTL simulation,
formal equivalence, synthesis, timing, power, or QoR validation was performed.
