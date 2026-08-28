# L5 local-agent audit after Revision 7

## Audited commit

```text
4dec4a8df6b246f01778925745b7ae21292f74a3
l5: record Revision7 gates and H3 timing failure
```

Decision: `ACCEPT_PARTIAL`.

## Accepted evidence

- Revision-7 single four-context lane source remap: WNS `+0.000141501 ns`, zero unmapped/unresolved. This is a marginal component pass, not physical signoff.
- Post-synthesis functional gate comparison: 120,032 cycle-exact samples, zero mismatch and zero unknown output. It is zero-delay/no-SDF evidence, not Formality or timing simulation.
- Real 16x32/512-lane E1: 1,000,000 dependent steps at II=1 and 10,000 random-backpressure steps pass.
- The generated HardFloat aggregate remains pinned at SHA-256 `d36c11122854248d01bcf4c5c8bc6f07d9517127b34f6c1b7c6d65e89c193268`.

## Rejected closure claim

Revision-7 H3 is not accepted:

```text
WNS             -0.926028 ns
TNS             -49161.85 ns
unmapped        0
unresolved      0
lane instances  512
lane variants   1
```

The top path starts in scheduler/FIFO completion state, crosses same-cycle
completion/bypass generation and global context broadcast, then enters the
lane accumulator mux and HardFloat Pre. The source-remapped lane assumes its
control/data inputs arrive near the 0.10 ns block input budget; H3 delivers the
bypass select much later. This is now a real microarchitectural control path,
not a synthesis hierarchy problem. More Revision-7 compile effort is forbidden.

## Audit decision

- L5.1 remains closed under its component E1/E4 contract, with effectively zero engineering margin.
- L5.2 E1 remains accepted.
- L5.2 E4 remains open.
- Revision 7 is frozen as failed at H3.
- Revision 8A is approved only as a candidate for local E1/E4 evaluation.

Revision 8A removes completion-handshake control from the accumulator data path.
The four context banks become the output-stage registers: when Post advances to
Output, the rounded result is written into the bank tagged by the aligned
context pipeline. Architectural completion, busy/valid updates and external
visibility remain tied to the unchanged output handshake. Same-context reissue
therefore reads an already committed local bank and no longer requires a global
completion-to-Pre bypass.

This preserves four contexts, four-cycle feedback, 16x32 physical geometry,
public interfaces and generated HardFloat arithmetic. It changes internal state
placement and must not replace production RTL before all local gates pass.
