# L1 Gemmini weight-stationary audit — 2026-08-25

## Scope

This audit runs the canonical `matmul_ws-baremetal` binary from the clean,
pinned `chipyard_gemmini` checkout under the already generated
`GemminiRocketConfig` Verilator simulator. It is a full `N=2`
weight-stationary workload, not the smaller `FAST=1` variant.

## Identity

- Chipyard commit: `e602d917dcc495c58cabe906535e411707096c9c`
- Gemmini commit: `8c3f9923a44a2fe2c7930587be297d6d4f8c09ca`
- Source SHA256 (`bareMetalC/matmul_ws.c`):
  `50e85f9988709b9d6f399766788b75aa875e1f0791bae37c7e8d4dbe4649cf63`
- Binary SHA256 (`build/bareMetalC/matmul_ws-baremetal`):
  `433566fdf0f6abd5a070dfd1315bc73227cc6de624b52385c1b8acf8943355c8`
- Simulator: `simulator-chipyard.harness-GemminiRocketConfig`, Verilator 5.050.
- Affinity: `taskset -c 8-25`; verified effective simulator affinity `8-23`.

## Command and result

The command is recorded in
`work/results/l1_gemmini_ws_revalidation/task.json`; its raw transcript is
`work/results/l1_gemmini_ws_revalidation/verilator_matmul_ws.log`.

It terminated at the unchanged TestDriver limit:

```text
*** FAILED *** (timeout) after 10000001 simulation cycles
```

There was no numerical mismatch output. Because the canonical run emits no
intermediate progress counter, the execution policy does not permit increasing
the cycle budget. The earlier `verilator_matmul_ws_20m.log` records a `$finish`
but has no captured invocation or binary hash; it is therefore historical,
non-authoritative evidence and cannot close this gate.

## Conclusion

`matmul_os` remains a valid Verilator PASS, but the canonical full WS RTL gate
is **not PASS**. L1 remains open pending an upstream-supported way to close the
WS workload without changing its source, simulator configuration, or timeout
policy. The `FAST=1` WS run is retained only as targeted coverage.
