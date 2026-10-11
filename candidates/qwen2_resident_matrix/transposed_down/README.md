# Default-off chunk-major Down on the existing retained Matrix path

This candidate layers `owner_down.patch` after the frozen transposed seed
composition. `QwenOwnerKernel.enableTransposedDown` defaults false and requires
both transposed Dense and seed profiles. The kernel instantiates exactly one
selected owner and one fixed bank allocation. It does not add an arithmetic
array, FMA, accumulator context, SRAM, operand FIFO, or result queue.

The selected owner uses local K chunks of at most2560, with global K and the
full job row stride kept separately. Qwen2-1.5B layer0 Down therefore runs
2560/2560/2560/1280. Each chunk visits every global N32 context in ascending
groups of at most five before the next A refill. N1536 has ten groups per
sweep, with three local contexts in its final96-column group.

## Source composition and default-off behavior

`check_frontend.py` composes the five frozen seed patches from the original
`825caff3a6c618419c49c7da452e009ce86ae8b5` source, validates the entire old seed
composition, then applies the Down patch. `source_pins.json` binds originals,
patches, and postimages. The old candidate files and receipts are not edited.

The old owner and bank source bodies remain exact prefixes of their composed
files, including assertion source line identities. The new selected class
extends the same owner/service composition and uses wider local bank ports.
Only the selected class elaborates. The existing Matrix seed controller,
service adapter, retained endpoint and physical seed leaf are unchanged.
The bounded frontend also emits all seven prior small circuits, checking exact
normalized disabled owner/bank/service/FIFO equality without relaxing the
normalizer, alongside two enabled Down circuits. The full actual kernel source
is typechecked; the full kernel is not elaborated. No retained SV is parsed,
executed, synthesized, or sent through EDA by this candidate.

## Local and global coordinates

A remains sixteen1376x256-bit1R1W banks; B remains sixteen160x256-bit1R1W banks,
786432 bytes total. A local chunk occupies at most1280 words per bank. The
remaining96 words do not become a second allocation or a hidden cache.

- A DDR address: `job.a + (row * job.k + chunkBase) * activationBytes + beat*64`
- B DDR address: `job.b + ((chunkBase + localK) * job.n + nBase + column) * weightBytes`
- A gather uses local K; full job K is never substituted with chunk depth
- A beat and kWord fields widen7 to8 bits; local K fields widen11 to12 bits
- The local gather includes bit11; the128-row B-half floor retains bits11:7
- Zeroing touches only the current legal local chunk extent, then ingress
  waits for both BF16 upper-half and synchronous RMW commit fences

All first-chunk contexts start with clear=true. Every later chunk restores the
previous raw FP32 prefix and starts with clear=false. Accepted updates retain
increasing global K. Each chunk closes every active local context. Prefix
writes contain raw finite FP32, without BF16 output conversion; final output
conversion occurs only on the last chunk. The actual Qwen2 Down recipe has no
bias. Bias handling for other graph operations remains an external final-only
step, as in the frozen owner contract.

## In-place prefix sweep transaction

The workspace remains an explicit snapshotted internal reservation: valid,
base, extent, generation, and maximum chunk depth. It is not an alias of
Command128 fields or job.c, and no fixed private DDR address is invented.
Multi-chunk jobs require16384 bytes per global N32 context. Single-chunk jobs
validate the same lease/address/generation but do not require unused per-N
prefix capacity. Thus K1536/N8960 can reuse the786432-byte Down lease with zero
prefix traffic. Addresses are aligned, spans remain in the56-bit domain, and
the reservation may not overlap any live A/B/destination span. Production Host
allocation, ownership, and binding remain OPEN.

`committedPrefixEnd` identifies the completed previous K sweep and remains
unchanged while the next sweep executes. Two ordered12-bit context frontiers
track complete seed ACKs and complete prefix writes. A context can be read
only from that previous committed sweep, exactly at the restore frontier, and
before its overwrite frontier. Its scratch address can be overwritten only
after all256 raw beats and the corresponding seed ACK have restored it. The
same allocation therefore contains old and new versions during a sweep; it
is never treated as an immutable full-memory snapshot.

Every current-sweep prefix byte must ACK, every context must close, and every
Matrix group must complete successfully before the new sweep becomes readable.
Only then do chunkBase and committedPrefixEnd advance, the frontiers reset,
and A refill begin. Final writeBytes excludes every prefix store. A failure
invalidates the prefix and poisons admission until a coordinated owner, DMA,
service and leaf reset. A partially overwritten sweep is not resumable.

The Down layer also fixes an inherited error-drain gap: an accepted seed begin
now creates an explicit outstanding obligation retired only by its physical
ACK. Both successful and error completion wait for it. A malformed sole ACK
retires that obligation and poisons the owner. Withholding an abort/error ACK
after MatrixDone cannot strand a terminal ACK behind finish/locked. The old
seed-only candidate and its receipts remain frozen and still lack this explicit
fence; the new result does not retroactively validate that old error path.
A generation number alone never establishes reset freshness.

## Resource changes

The frontend counts131 additional register bits over the seed profile:
129 in the selected owner and two in the widened bank request registers.
These comprise the global16-bit chunk base,16-bit committed prefix end,
two12-bit ordered frontiers,64-bit per-sweep acknowledged-byte count, one
outstanding-seed bit, and ten widened coordinate/workspace bits. Together
with the prior1852-bit seed ledger, the source/CHIRRTL total is1983 bits over
the frozen unseeded profile. It is a source register count, not synthesized
flip-flops or area.

New logic includes full-stride global/local address selection, local extent
selection, wider A gather selectors, sweep counter comparisons, read-before-
overwrite gates, and the outstanding-seed completion fence. The existing
per-lane raw/FMA data muxes, five accumulator contexts,16KiB finalValue,
four-entry operand FIFO, eight-entry metadata FIFO and two-entry result queue
remain. Physical area, timing, fanout and RAM inference still need measurement.

## Validation and remaining limits

Small tests cover actual bank coordinates past localK2047, full-K row stride,
all48 global contexts and tail96, four sweeps, same-address prefix versions,
whole-sweep MatrixDone/ACK fences, native BF16 K8960 ingress, raw FP32 prefix
range, seed backpressure, early/error MatrixDone, malformed/read/write/late-ACK
failure, final-write errors, and coordinated reset. A separate single-chunk
K32/N8960 control check uses the same786432-byte lease without prefix traffic.
These are independent control models and source contracts, not RTL simulation.

The numerical runner pins actual phase12 activation, real output-major Down
weights, and their provenance receipts before execution. Accepted bank-model
A/B packets alone drive the same five C++16x256 host accumulator banks. Every
group erases those banks. Continuation requires accepted seed packets reread
from the live ACK-backed prefix allocation. Snapshots and version ledgers are
observers only. The independent increasing-K dot product and saved phase13
comparison are used only after the final output ACK and owner response.

No native-M128 or FP32-final numerical acceptance changes. The original FAIL
evidence and unapproved numerical policy remain. Retained-RTL execution,
physical latency/clocking/reset fencing, production Host binding, full-block
execution on this selected source, and physical QoR remain separate gates.

Reproduce the cheap source/control gate:

    PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s candidates/qwen2_resident_matrix/transposed_down -p 'test_*.py' -v

Reproduce the source/cache validation without a compiler:

    python candidates/qwen2_resident_matrix/transposed_down/check_frontend.py --out NEW_WORK_DIRECTORY --cache work/matrix_frontend_20261011/jars --hardfloat work/upstream/hardfloat_continuous --validate-only

The same command without `--validate-only` typechecks85 actual Scala sources
with87 SHA-pinned cached jars and HardFloat, using one Java CPU,1024MiB heap,
and180 seconds per command, then emits the nine bounded CHIRRTL circuits.
Raw tensors, executables, emitted circuits, and detailed receipts stay under
`work/qwen2_transposed_down_20261011/`; they are never Git payloads.


Reproduce the actual-input numerical slice, with all sources and input receipts
pinned before arithmetic (strict small C++ helper,180-second ceiling):

    python candidates/qwen2_resident_matrix/transposed_down/check_numeric_smoke.py --columns 160 --out NEW_WORK_DIRECTORY

`--columns 1536` selects the full40-group Down host-model projection with the
same source and helper. The runner validates every group's global N position,
three-context tail, previous MatrixDone and write ACKs; seed commit identities
include global context. It does not alter the existing full-block dataflow run.

Preserved initial captures `numeric_01` and `frontend_01` precede the final
single-chunk compatibility and owned-seed drain fix and retain those original
identities. `frontend_02` is the final85-source/nine-circuit capture;
`numeric_02` binds the current model/helper/runner and source composition for
actual M128/K8960/N160, with zero mismatches across20,480 final FP32 values.
Its three raw prefixes total245760 ACK-written bytes, with3840 exact-version
rereads/seed beats and15 seed ACKs. Its final acknowledged output is81920 bytes.

`numeric_full_03` executes the complete M128/K8960/N1536 Down projection through
this final host model in44.41 seconds. All196608 final FP32 values match both
the independent direct dot and the saved phase13 output, byte-for-byte. It
records40 groups,430080 accepted steps,192 physical results,144 seed ACKs and
36864 seed beats. The three prefix sweeps read and ACK-write2359296 bytes in
the same786432-byte allocation. Final output is786432 bytes. There are538624
read descriptors,43008 total write ACKs, and49152 write data beats. Final
SHA256 is `48c8e5509f94fa9dae7dc0e13ffd2811d4aabda518e3c1a64ed4d79e415c8af1`.

The separate read-only `artifact_audit_01.json` checks every one of the36864
saved seed records against its actual preceding acknowledged sweep snapshot,
all12288 per-address write1/read1/write2/read2/write3/read3 chains, and all
196608 final values. It binds final source snapshots to current source pins
without reexecuting arithmetic. These full-Down results remain host evidence;
no complete selected-source block or retained RTL ran.
