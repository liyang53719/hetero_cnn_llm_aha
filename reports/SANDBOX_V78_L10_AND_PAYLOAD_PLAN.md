# Sandbox v7.8 — L10 early-PPA and L5.6 evidence boundary

## Audit decision

The current main branch has passed the balanced 8×8 Attention SFU gates, a composed real-RTL E3 at 321.869395 token/s, a 28-layer count/trace E3 at 320.791599 token/s, official-weight reference checkpoints, 160 bit-exact LM-head samples, and a 7,840-value reduced four-layer cross-RTL replay.

Those results justify starting L10 early PPA. They do **not** justify the claim that a continuous 28-layer payload numerical RTL replay is closed. The trace and cross-replay reports explicitly retain reduced-payload non-claims.

The normalized L5.6 subgates are:

```text
L5.6a 28-layer cycle/count trace E3             PASS
L5.6b official reference + sampled LM-head RTL  PASS
L5.6c reduced four-layer cross-RTL replay       PASS
L5.6d continuous 28-layer payload numerical RTL OPEN
```

L10 may proceed in parallel with L5.6d.

## Early-PPA risk

Pre-layout accepted margins are extremely small. The current screening manifest includes Matrix H3, Attention control/SFU, selected SiLU and refined rsqrt. Multiple blocks have less than one picosecond of WNS and the smallest margin is below 0.01 ps.

The component-area sums in the v7.8 report are **screening values only**. A real integrated-top report must avoid counting frozen DDCs and their parents twice.

Local L10 must close four bounded gates:

1. hierarchy-preserving integrated synthesis;
2. SRAM macro replacement and bank/port validation;
3. post-route setup/hold plus PVT/OCV and design-rule closure;
4. workload-derived SAIF power.

No vectorless DC power result is accepted as final power evidence.

## Full-payload closure plan

The sandbox generates 168 checkpoints: six phases for each of 28 layers. The local execution sequence is:

1. capture every layer/phase checkpoint from the exact official revision;
2. replay seven continuous four-layer groups without hidden-state injection inside a group;
3. execute a continuous 28-layer payload replay or the real backend equivalent without intermediate reference-state injection.

The plan is test collateral, not numerical evidence.
