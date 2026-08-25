# L2 macro boundary contract

This document freezes the integration boundary before wrapper RTL is allowed to
claim macro equivalence.  It applies to the canonical L1 upstream checkouts;
generated artifacts remain under `work/generated/` and are not committed.

## Gemmini

The generated `Gemmini` macro is a **Rocket RoCC peripheral**, not a standalone
matrix core.  Its exact `Gemmini.sv` SHA256 and 157-port manifest are locked in
`gemmini_macro_contract_lock.json` and `gemmini_port_manifest.json`.

The only valid path is:

```text
128-bit command -> typed descriptor -> Gemmini RoCC micro-op sequence
  -> RocketTile command router/status -> generated Gemmini
  -> RocketTile PTW + TileLink -> memory
```

The project command selects a descriptor; it must not be reinterpreted as one
Gemmini instruction.  In particular, an abstract `GEMM` operation is a sequence
of official `CONFIG`, `LOAD`, `COMPUTE`, `STORE`, and completion/fence actions.
`io_resp` is used by Gemmini counter operations and is not a general completion
interface; macro completion requires a defined quiescence/fence observation in
the retained RocketTile context.

`gemmini_rocc_command_adapter` and
`hetero_npu_gemmini_rocc_integration_v0` remain clean-room contract test
adapters.  They must never be wired directly to `Gemmini.sv`, PTW, or a locally
invented TileLink responder, and their passing testbench is not L2 evidence.

## AHA/Garnet

`scripts/generate_aha_l2_macro.sh` regenerates the pinned AHA image's 4x16
`Interconnect` macro into `work/generated/l2_aha_garnet_4x16/`, records image
digest/commit/hash, and extracts an ANSI port manifest.  The subsequent wrapper
must consume that manifest and preserve every native config/stream/control port.
It may add only project-side config loading, 512-bit stream gearboxes, skid
buffers, reset/config/run sequencing, and completion observation.  It must not
substitute `cgra_sfu_vector` for generated Garnet when claiming macro results.

The locked 4x16 macro exposes four `glb2io_17` and four `io2glb_17` ready/valid
lanes plus four independent 1-bit lanes.  A 17-bit lane is an AHA-native
payload, while end-of-stream is represented by the separate 1-bit IO network;
the high bit of a 17-bit value can encode sparse control tokens.  Project
`last`/tag must therefore remain wrapper metadata until lowering has selected
the bitstream's native data and EOS lane placement.  It must not be packed into
bit 16 or forced onto a fixed lane.

The generated macro uses SystemVerilog array constructs that Icarus 11.0 does
not parse.  Its binding gate is therefore the pinned host Verilator 5.050 with
the exported official dependency closure, not an Icarus fallback.

## Required L2 evidence still outstanding

1. A project-owned descriptor lowerer that emits a checked official Gemmini
   micro-op sequence for mvin/mvout, WS/OS GEMM, and convolution.
2. A retained-RocketTile harness proving baseline C commands and lowered
   descriptor commands have identical writes, events, and numerical outputs.
3. A generated-Garnet wrapper harness proving Gaussian map data/config trace
   equivalence with upstream, including backpressure and reset/config/run.
4. Clean upstream trees before and after every wrapper run.
