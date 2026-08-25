# L2 wrapper-only macro integration gap audit

## Gemmini

`rtl/integration/gemmini_rocc_command_adapter.sv` implements only a command
translation and response-event contract. It does not instantiate generated
`Gemmini.sv`; the 157-port official boundary still requires Rocket RoCC status,
PTW, and TileLink scratchpad/accumulator connectivity. Therefore its existing
tests and DC result are wrapper-only contract evidence, **not L2 macro PASS**.

L2 implementation must retain the generated RocketTile/RoCC/PTW/TileLink
context and translate one project descriptor into the official RoCC sequence.
It must not add a hand-written partial TileLink or identity-PTW substitute.

## AHA

The L1 generated 4x16 Garnet and Gaussian flow pass, but repository RTL has no
Garnet config-loader, 512-bit-to-lane gearbox, tag/last skid buffering, or
reset/config/run FSM. The existing `cgra_sfu_vector` is clean-room SFU logic,
not the generated Garnet macro wrapper.

## L2 entrance criteria

1. **Complete:** freeze exact generated Gemmini wrapper boundary and
   RocketTile-provided context; preserve upstream source clean. Evidence:
   `gemmini_macro_contract_lock.json` and the boundary verifier result.
2. **Complete:** regenerate the pinned 4x16 Garnet `Interconnect`, freeze its
   69 native ports and 25-file simulator closure, and lint the complete named
   binding with Verilator. Evidence: `work/generated/l2_aha_garnet_4x16/`.
3. **Open:** add unit tests proving original and adapter path output/memory/event
   equivalence before connecting them to shared fabric in L3.
