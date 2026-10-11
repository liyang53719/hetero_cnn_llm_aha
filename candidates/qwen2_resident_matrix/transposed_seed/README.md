# Default-off physical FP32 prefix save and restore

This isolated source candidate extends the actual transposed Dense owner and
retained Matrix service at frozen commit
`825caff3a6c618419c49c7da452e009ce86ae8b5`. It adds an optional raw FP32 seed route
all the way to the existing SystemVerilog `accumulator_bank[0:4]`. It does not
add an alternative arithmetic array, FMA, accumulator bank or SRAM.

The completed bounded numerical check uses the same saved actual Qwen2-1.5B
layer0 M128/K1536/N160 n0 and Wq inputs as the old unchunked owner check. It
splits the increasing-K reduction at768, writes and acknowledges actual first
chunk physical values, rereads those bytes, restores the same five host-model
banks, and completes K768..1535. All20,480 final FP32 values match the frozen
old unchunked output bit-for-bit; separate bias addition matches saved qr.
This is source, independent control-model, host-FMA and Chisel frontend evidence.
No retained SystemVerilog was parsed, simulated or synthesized. It is not a
complete Down projection, full-block run, native-M128 acceptance or QoR result.
Native-M128/FP32-final FAIL evidence and pending numerical policy are unchanged.

## Reproducible source composition

Apply these patches to an isolated snapshot, in this order:

1. Frozen `transposed_route/combined_service.patch`
2. Frozen `transposed_owner/owner_selection.patch`
3. `service_seed.patch`
4. `owner_prefix.patch`
5. `leaf/retained_accumulator_seed.patch`

Include the three existing transposed-owner Scala sources and the unchanged
`MatrixAccumulatorSeedProtocol.scala`/`MatrixAccumulatorSeedController.scala`.
`source_pins.json` identifies every original source, patch and postimage.
`leaf/source_manifest.json` and `leaf/dependency_manifest.json` cover the actual
retained endpoint, array, front/scheduler, cluster and lane dependency tree.
Frozen existing files are not edited in this deliverable.

`QwenOwnerKernel.enableTransposedSeed` defaults false and requires the existing
transposed Dense profile. Its elaboration selects exactly one owner. The old
owner class remains byte-identical; the seed owner is an explicit alternative
in the same patched source. Disabled owner, SRAM, service and queue/result
modules have exact normalized CHIRRTL equality to the prior frozen frontend,
for both single and burst writes. New endpoint Option ports are absent when
disabled: original22 ports versus enabled45 ports and parameter1.

## Transaction, physical layout and failures

The internal `TransposedPrefixWorkspace` input is a snapshotted reservation:
valid, base, extent, generation and splitK. It must be64-byte aligned, cover
16384 bytes per global N32 context, avoid all A/B/destination spans, and stay in
the56-bit address domain. Generation must be nonzero; splitK must be a positive
multiple of128 smaller than K. M16/M128 and K<=1536 admission remain unchanged.
This input is deliberately not derived from `job.c` or a private fixed address.
Production Host allocation and binding remain OPEN until an actual reservation
is validated. A generation number alone never establishes reset freshness.

The first group ends at splitK and its physical results use the existing
16KiB `finalValue` register buffer. Prefix DDR layout is
context × physical[16][256] raw FP32, row-major. Every write is one512-bit beat.
All active contexts' prefix writes must ACK successfully and Matrixdone must
arrive successfully before the whole window becomes readable. Prefix ACK bytes
are separate from final `writeBytes`; prefix stores cannot count as published
logical output. Result/store draining continues before waiting for Matrixdone.

The second group resets seen/closed and tracks seeded contexts separately.
The frozen seed controller walks slice s, then cluster q. Its DDR beat is
`16*(q>>1)+2*s+(q&1)`, with exactly one512-bit holding register and one read
outstanding. The 16 values in a beat are raw FP32, with both zero signs,
subnormals and all finite FP32 values preserved. Prefixes use no BF16 output
range restriction. All arithmetic issues wait until all required seed ACKs.
The first post-seed issue has clear=false and global K=splitK. Ordinary first
issues retain clear=true. Finish must close every seeded context, including
one which has not issued yet.

Retained reservation invalidates the chosen context, then32 ordered cluster
beats per slice reuse each lane's sole existing accumulator write port. Commit
sets the same scheduler/lane valid bits only after all writes; ACK is registered
and echoes tag, sequence, generation and context. A held ACK is immutable;
concurrent abort suppresses controller committed even if the held ACK says
success. Seed writes never advance arithmetic/result/flags FIFOs or counters.
Seed reservation is separate from arithmetic busy. Quiescence uses empty real
service tags/results plus selected raw arithmetic busy/out-valid signals.

Every selected ICG stays awake through begin, beat, commit, ACK backpressure,
abort and invalidate. A busy raw begin blocks new issue, poisons the interface,
and permits already accepted token/data/flags/result work to drain. Successful
reservation alone holds arithmetic data paths. The earlier raw-begin hold bug
was fixed and the bounded token/data model detects that rejected mutation;
this is not a physical clock-gating or RTL timing validation.

Prefix read/write failures suppress final publication. A malformed sole physical
terminal retires that obligation and poisons the owner, preventing a wait for a
second terminal the adapter will not send. Missing physical terminals never
manufacture timeout success. Late seed ACK/abort remains poisoned until a
coordinated DMA/owner/service/leaf reset; local reset cannot prove freshness.

## Resource ledger

Existing allocations remain sixteen A1376×256 and sixteen B160×256 SRAMs,
768KiB total, with exactly1R1W per bank; operandFIFO4, metadataFIFO8,
resultbuffers2 and the16KiB finalValue buffer remain. Eight retained endpoints
still contain4096 BF16-product/FP32-FMA lanes and five accumulator contexts.

Added register payload is805 bits in the owner (including512 data-hold bits),
37 bits in the service,138 bits in the seed controller, and a source-counted
109 bits per leaf (872 total):1852 bits combined. The frontend receipt derives
the first three counts from actual emitted register types. Leaf109 comprises
99 identity bits,6 beat-count bits, reserve/ACK-valid/ACK-error/poison bits.

Each existing lane bank write port gains a32-bit raw/FMA data mux,3-bit context
mux and write-enable/valid controls. There are32 cluster selectors per endpoint,
a20-bit enabled control broadcast versus13 bits disabled, endpoint identity and
finite checks, owner physical-prefix gather/address selectors, and service
broadcast/demultiplex/ACK logic. Seed data fans out across32 clusters. These are
real logic additions; physical area, fanout closure and timing remain unmeasured.

## Bounded checks and retained evidence

Small owner/service and frozen-default control tests:

    PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s candidates/qwen2_resident_matrix/transposed_seed -p 'test_*.py' -v
    PYTHONDONTWRITEBYTECODE=1 python candidates/qwen2_resident_matrix/transposed_seed/leaf/test_seed_leaf_contract.py

Real-input host check (strict tiny C++ helper,60-second ceiling):

    python candidates/qwen2_resident_matrix/transposed_seed/check_numeric_smoke.py --out NEW_WORK_DIRECTORY

The runner pins n0, Wq, bias, saved qr, original arithmetic helper bodies and
old unchunked acknowledged output. It saves readable exact model/helper/runner
snapshots, actual81,920-byte acknowledged prefix before first seed begin,
102,400 bytes of accepted seed records (1280 records ×80 bytes), and final
ACKed outputs. The host banks are erased at rollover; old residual values or a
golden result cannot supply restoration. Raw tensors and executables belong in
work evidence only, never Git.

Frontend (87 SHA-pinned cached jars; one Java CPU,1024MiB,180s per command):

    python candidates/qwen2_resident_matrix/transposed_seed/check_frontend.py --out NEW_WORK_DIRECTORY --cache work/matrix_frontend_20261011/jars --hardfloat work/upstream/hardfloat_continuous

This typechecks84 actual Scala sources including full QwenOwnerKernel and pinned
HardFloat, then emits only seven small owner/service CHIRRTL circuits. It does
not elaborate the full kernel or generate RTL. `--validate-only` performs no
compiler work. `--audit-existing OLD_DIRECTORY --out NEW_DIRECTORY` validates
successful saved compilation/emission sources and audits the same IR without
rerunning commands.

Current evidence: `work/qwen2_transposed_seed_20261011/`. The original
`frontend_01` records a failed Python resource matcher after both Java commands
succeeded: it expected `smem` for existing Chisel `cmem` queues. That receipt is
preserved. `frontend_audit_02` audits the same immutable IR with corrected exact
queue/ABI/resource checks and no new compile. `numeric_03` binds the final
model/runner and retains raw prefix/seed captures. Earlier numerical receipts
are preserved with their original source identities. No full-chain repeat ran.

Remaining dependencies include actual retained-RTL execution, physical reset
fencing, production Host workspace binding, larger K/chunk composition, and
full Down/full-block integration. K2560 is the next bounded extension; K8960
and full Down resident-A admission are not added here.
