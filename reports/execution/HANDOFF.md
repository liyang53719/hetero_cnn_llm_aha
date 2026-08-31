# Local-agent handoff v6.10 — main only

## Git hard gate

Only `main` is allowed. Before work: fetch, pull `--ff-only`, run
`scripts/check_main_only_workflow.sh`. Before push: fetch, rebase if advanced,
rerun affected gates, and fast-forward push. No branch or force-push.

## Accepted

```text
L5.2 Matrix H3                 PASS, WNS +0.00490451 ns
Attention controller E1/DC    PASS, WNS +0.00191498 ns, area 1773.408002
Trace-coupled q128/384/1024    PASS_NOT_SINGLE_SIM
Block32 weight SFU E1/DC      PASS, WNS +0.0000125766 ns, area 13949.754056
SiLU one-lane E1/DC           PASS, WNS +0.0000521541 ns, area 10559.276031
SiLU two-lane E1/DC           PASS, WNS +0.0000220537 ns, area 19747.364067
```

HardFloat cache reuse requires exact Scala-source, upstream-commit and output
hash match. Power is vectorless DC, not SAIF. All timing margins are high-risk.

## Unique next action

Build one q128 simulation containing controller, Revision8B-B QK/PV service,
`fp32_block32_softmax_weights` and Block128 M/L/O merge. The trace bridge and
separate q128 numerical RTL cannot close E2. Then q384 and reviewed q1024 rows
with exactly43,008 merges, random backpressure and zero score/probability DDR.

Measure Matrix producer stall in that run. Select one SiLU lane at <=2%, else
two, and rerun selected path. L5.5 still waits; pre-route floor315 token/s.

CPU8-23, MemoryHigh24G/Max30G, 600s/task. Keep two untracked runtime scripts out.
