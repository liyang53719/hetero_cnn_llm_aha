# Local Agent 84bb280 audit and sandbox v7.5 independent validation

## Audit decision

`84bb2802fc197e6ab8bb14b7868a716d3af7a4f8` correctly closes L5.3 and L5.4 while keeping L5.5 open.

Accepted local evidence:

- L5.3 q128/q384/q1024 numerical E2, deterministic random backpressure, 354,816 QK/SFU/PV transactions, no loss/duplicate/reorder/deadlock, and zero score/probability DDR materialization.
- L5.4 fused SiLU edge policy and one-lane selection, with zero measured producer stall and queue high-water mark 7.
- The 4-lane tile / 4-row merge candidate passes numerical E1 and component DC, but its stress projection is 314.448097 t/s and therefore does not close the 315 t/s review gate.

The correct project state is therefore:

```text
L5.3 PASS
L5.4 PASS_SELECTED_ONE_LANE
L5.5 OPEN — balanced 8x8 SFU required
```

## Independent sandbox recalculation

A separate implementation, not importing the repository planning model, reproduced:

```text
4x4 nominal 315.488706 t/s
4x4 stress  314.448097 t/s
8x8 nominal 323.764205 t/s
8x8 stress  322.944106 t/s
```

The conservative 8x8 stress estimate is 2.522% above the 315 t/s hard review floor and 0.920% above the 320 t/s preferred engineering floor. This is sufficient for local RTL evaluation, but not for an E3 or final performance claim.

The independent numerical check covered random, identical-score, dominant-last, extreme-range and block-boundary distributions across 80 rows. Maximum output error was `8.940696716308594e-08`; maximum normalized-weight sum error was `5.960464477539063e-08`.

## Qwen model resource envelopes

The resource arithmetic was independently reproduced:

```text
Qwen3.5-35B-A3B
  GDN recurrent state      60 MiB / sequence
  BF16 dense KV             5 GiB / sequence at 262144 context
  minimum on-chip staging   0.875 MiB before Matrix scratch

Qwen3.8-Flash-Next
  GDN recurrent state     108 MiB / sequence
  BF16 QSA KV               6 GiB / sequence at 262144 context
  compressed QSA index    192 MiB / sequence
  minimum on-chip staging   1.40625 MiB before Matrix scratch
```

Qwen3.5 is `qwen3_5_moe` with dense GQA and a single residual stream. Flash-Next is `qwen4_exp` with QSA, PLE and four-branch gated residual. Their service curves and state layouts must remain separate.

## Next local-agent gate

Implement and measure the balanced eight-lane Block32 tile and eight-row M/L/O merge. Required order:

1. Numerical E1 for the same 16 frozen tile cases and eight-row merge vectors.
2. Deterministic random backpressure with no loss, duplication, reordering or deadlock.
3. CLN22UL 1 GHz DC with WNS >= 0 and no unmapped/black-box cells.
4. Measured q1024 stress projection: hard floor 315 t/s; preferred floor 320 t/s.
5. Only after the measured gate passes, run Matrix/SFU/iDMA/DDR integrated E3.

The planning targets are `tile16 stress <=336 cycles` with merge8 stress 323, or `merge8 stress <=516 cycles` with tile stress 254. These are system-performance envelopes, not standalone component pass criteria.

## Evidence boundary

This report accepts the d718 sandbox implementation and planning model. It does not claim 8x8 RTL elaboration, Verilator E1, CLN22UL E4, integrated E3, official-model execution, or post-route signoff.
