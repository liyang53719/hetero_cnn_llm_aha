# L5.2 Revision 8A candidate approval

## Decision

`APPROVE_CANDIDATE_E0_WITH_LOCAL_GATES`.

Revision 8A is a concrete replacement candidate for the failed Revision-7 H3
control path. It is not yet canonical RTL and it does not close L5.2.

## Frozen microarchitecture

```text
accepted issue
    │ context + clear
    ▼
Pre ── context tag
    ▼
Mul ── context tag
    ▼
Post ─ context tag
    ▼ output_write edge
Round result → lane-local bank[context]
                    │
                    ├─ output reads bank[output_context]
                    └─ later same-context issue reads the same bank
```

The four accumulator banks also implement the output-stage storage. A result is
written when Post advances into Output, one architectural stage before external
completion may be accepted. The scheduler still keeps the context busy until
the output handshake, so the early-written state is not externally reusable or
visible before the original completion point. If Output stalls, the bank and
output-context tag remain stable.

Implementation hierarchy:

```text
1 source-mapped front-control block
  scheduler + elastic valid chain + aligned context tags

32 source-mapped cluster16 blocks
  16 lanes/cluster × 32 = 512 lanes
  four banks/lane

1 retained flag/reset glue block
```

## Unchanged contracts

- physical geometry: `16x32`, 512 BF16 MAC lanes;
- four architectural accumulator contexts;
- four-cycle FMA feedback latency and no-stall II=1;
- public module ports and command/completion ordering;
- RNE, tininess-after-rounding and exception behavior;
- generated HardFloat source and aggregate SHA;
- 1.0 ns clock, 0.08 ns uncertainty and 0.10 ns I/O budget.

## Sandbox evidence

- 1,000,000-operation cycle-level differential against Revision 7: PASS;
- 500,000 additional operations across 20 seeds: PASS;
- public ready/valid/context/last/value/busy/valid/counters cycle-exact;
- final context state equal;
- 500,612 same-cycle context reuses in the primary run;
- candidate source contract: PASS;
- local Tcl contract: no multicycle, no synchronous-data false path, no retime;
- source-ready tests include a 120,000-sample Revision7-vs-Revision8A lane compare,
  the existing million-step 512-lane E1 and a 50,000-step arbitrary-context test.

## Required local gates

1. Source-level Revision7-vs-Revision8A lane comparison passes.
2. Candidate 512-lane E1 passes 1,000,000 dependent steps and 10,000 random-backpressure operations.
3. Candidate arbitrary-context/clear/backpressure E1 passes 50,000 operations.
4. Candidate lane WNS >= 0, unmapped/unresolved = 0.
5. Candidate lane source-to-mapped equivalence or approved gate comparison passes.
6. Source-mapped 16-lane cluster WNS >= 0; exactly 16 physical lanes.
7. Joint front-control WNS >= 0.
8. Structural H3 has one front-control block, 32 cluster16 blocks and 512 lanes;
   WNS >= 0 and unmapped/unresolved = 0.
9. Area and power delta are recorded.
10. E1 is rerun after accepted mapped evidence.

## Stop rules

One normal and one high-effort attempt are allowed for lane, cluster and front.
Any remaining negative WNS, equivalence failure, E1 failure or H3 failure stops
as `BLOCKED_ARCHITECTURE_DECISION`. The following remain forbidden:

- fifth context or additional pipeline cycle;
- smaller array or lower frequency;
- synchronous-data false path or multicycle exception;
- register retiming;
- generated HardFloat edit;
- direct promotion of candidate files before E1/E4 closure.
