# Resident FFN group: explicit execution profile

This is the successor composition to `ffn_drain`, on the same pinned production
Host, kernel, Dense owner, 4096-MAC Matrix service, 786,432-byte bank allocation,
original sixteen-lane SiLU owner, and original iDMA. `group.patch` edits those
actual Host/kernel/top sources; it is not an independent arithmetic harness.
`check_frontend.py` composes the frozen earlier patches and this patch in order.
The three new Scala files are production modules/entry point in that composition.

## Public contract

`enableResidentFfn=false` is the default. The ordinary emitter and driver keep
their original behavior. The separate `EmitHostResidentFfn` entry point selects
the new execution contract. This profile is for the original Qwen2 shape and
BF16 weights, not the native Qwen3.5 profiles.

The profile reads the ordinary three consecutive Command128 commands:
Dense (`0x20`), Dense (`0x20`), Activation (`0x35`). It uses their real descriptor,
policy, engine and event fields; there is no private opcode, command flag,
`bias_index` convention, fixed PC or fixed DDR address. A candidate Gate is
identified by M=16 or 128, K=1536, N=8960, FP32 A/D and BF16 W. A candidate with
an invalid following Up/Activation is rejected before resident computation.
Other ordinary operations keep the existing execution path.

Gate and Up D are explicitly **virtual full allocations** in this profile.
Their completion events confirm the internal producer work, not materialized
DDR tensors. Host software and debug readers must not read those two DDR
allocations, including after their events. The original driver which reads
Gate/Up DDR after every completion is not compatible with this opt-in contract;
use the ordinary profile when that visibility is required. Activation is the
only materialized output of the group. No ordinary driver was silently changed.

All three full tensor records, public policies, permissions, shapes, dtypes,
alias checks, workspace separation and event dependencies pass before compute.
Up must use the same full A allocation as Gate. Activation must consume the same
full Gate/Up allocations; allocation identity excludes the consumer policy tail.
The six distinct spans A, Wgate, Wup, Gate, Up and Act are pairwise disjoint.

A bounded preflight then reads every public command's three tensor roots with
the existing Record128Reader/TypedTensorReader and launch permissions. An absent
Softmax B is skipped. Every full-span intersection with Gate or Up is rejected
except Gate-PC D, Up-PC D, and Activation-PC A/B, each with exact full allocation
identity. This rejects additional readers, writers, aliases and padding overlaps
before the first Gate. It does not prevalidate the semantics of every unrelated
future opcode or policy. Those retain the ordinary decoder's behavior. Descriptor
and command tables remain in the existing read-only launch regions.

The scanner does not forbid legitimate A generation before the group or A reuse
after it. The coordinator serializes all owners for the entire group, so no
other command can modify its sources while the A lease is live. The two virtual
entries are capacity-checked with a widened `virtualCount + 2` and reserved only
after the whole scan. Neither Gate nor Up is inserted into the DDR-live table.

## Actual ownership path

The production kernel instantiates `FfnResidentCoordinator`. A group owns all
normal, window, tile, drain and SiLU services until its terminal handshake. There
are no parallel external tile/window/drain ports when the resident profile is on.
For each of the 56 N=160 groups, it performs:

1. Flush/select Gate's real iDMA weight window; issue Gate and validate its typed
   DDR-zero completion and full sealed tile in slot 0.
2. Flush/select Up's real weight window; issue Up with the same A lease and
   validate its typed DDR-zero completion in slot 1.
3. Run the moved production `FfnTileSiluBridge` through the original bank service
   and sixteen SFU lanes; seal slot 2 and release slots 0/1.
4. Flush/disable the weight window; submit the independent typed Activation drain
   and validate all real DDR ACK bytes, consumed beats and slot-2 release.
5. Advance N only after that validated terminal. Every Gate after the first and
   every Up uses the same retained A lease and group identity.

Each handoff occupies a full no-request cycle. The existing adapter refuses
request admission on its flush cycle. Ordinary Down later selects its normal
weight window through the unchanged ordinary job handshake.

Final success requires 573,440 actual ACK bytes for M16 or 4,587,520 for M128,
then explicit A-lease invalidation and an observed drained/unleased state. Only
then can the Host accept the aggregate result and emit the three original PC,
engine and signal-event completions. Activation becomes DDR-live after the third
completion is accepted. Ordinary K=8960 Down reads that DDR tensor; no direct
Act-to-Down shortcut is present because large-K loading reuses the high slots.

Abort and service errors stop new work and drain accepted memory, Matrix, bank
RMW and SFU paths. A held terminal's payload never changes. A sticky poison
sideband blocks Host success even for a later one-cycle abort while stalled.
Host applies that fence both to aggregate result acceptance and each public
completion. No failed group publishes Activation as DDR-live.

## Counts, resources and evidence boundary

Coordinator cycles count actual clock edges from request acceptance to the first
terminal-valid edge, including handoff, waiting, Matrix, SFU and drain cycles;
held terminal cycles are excluded. Useful/executed MACs sum actual accepted
window/drain terminal counters, including work reported on failed terminals.
These are source counter paths, not a measured performance result or a shape
prediction. The historical fixed 4096-MAC, full-wall-cycle denominator is unchanged.

The coordinator stores metadata only. Relative to the already enabled
window/drain/tile kernel that previously exposed external tile/SFU ports, the
resident group adds 3,389 coordinator register bits and 2,398 Host metadata bits.
It also moves the previously harness-only bridge into the production kernel:
that is 592 additional kernel register bits, including its 512-bit Gate payload
hold. The bridge is counted once, even though its algorithm/source is reused.
Two new one-bit registered poison handoffs in kernel/top are source-accounted
(the full kernel/top is not elaborated here). The group-specific ledger is thus
6,381 register bits including those two bits; it excludes earlier unchanged
candidate bank/owner/loan deltas already recorded by their own receipts.

There are no extra payload holds beyond that migrated bridge, no new Dense
result buffers or SRAM arrays, and no added Matrix engine, SiLU arithmetic lane,
or DMA engine. The original sixteen-lane SiLU owner remains the single arithmetic
consumer. Existing Dense result holds, bank RMW holds and the prior drain storage
ledger remain unchanged.

The bounded frontend typechecks the actual full source composition and elaborates
only the coordinator/bridge and real Host parser (21 commands, 32 events), with
exact default-off parser and bridge CHIRRTL comparisons. It does not elaborate
the full Host top or Matrix kernel, generate RTL, execute arithmetic, or establish
area, timing, performance or numerical acceptance. Native arithmetic and FP32
final acceptance remain FAIL/unapproved under the parent numerical policy.

## Current bounded evidence

- `work/ffn_group_frontend_20261012T0027/summary.json`: PASS, 95 actual source
  files typechecked, six bounded CHIRRTL targets, 38.20 seconds total.
- Exact normalized default-off Host parser and moved bridge CHIRRTL equal their
  immutable pre-group definitions. Actual enabled Host parser and coordinator
  elaborate without duplicated arithmetic or SRAM.
- Eight source/composition guards pass with the exact final drain0024 parent.
- Control-model evidence is separate from this frontend and from arithmetic.
  No RTL, full top/kernel elaboration, native arithmetic, FP32-final, numerical
  policy, physical QoR or performance acceptance is implied.
