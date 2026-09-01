# Local-agent handoff v7.17 — main only

## Closed in this checkpoint

```text
v7.8 sandbox baseline                       PASS
L10.1 frozen-DDC owner hierarchy link/STA  PASS
  WNS +0.00000864267 ns; area 2,313,314.648873 um2
  6 owners; parent local area 0; double-count 0
L10.2 SRAM macro DB inventory              PASS
  4096 KiB; 124 physical macros; overlap 0
  SP/DP Liberty->DB and timing arcs linked
Payload P1                                PASS, 168/168 checkpoints
Payload P2 reference continuity           PASS, 7/7 groups bit-exact
Payload P2 RTL transaction control         PASS, 168/168, injection 0
```

## Open boundary

P2 has no real Matrix/SFU payload datapath execution. Reference continuity and
RTL control are separate evidence paths. L5.6d P2 real datapath and P3
continuous 28-layer/device-backend remain OPEN.

L10.3/L10.4 remain OPEN. DP GDS2 and all SRAM LEF are blocked by the ARM
physical-view generator; no post-route/PVT/OCV or SAIF claim is made.

## Next

Implement/select a real payload datapath or device backend for P2/P3. Preserve
CPU 8-23, 24/30 GiB memory caps, <=600 s tasks, main-only pushes, and the two
untracked user runtime scripts.
