# Official Gemmini generated interface audit

Generated collateral:

- Chipyard commit: `e602d917dcc495c58cabe906535e411707096c9c`
- Gemmini submodule commit: `8c3f9923a44a2fe2c7930587be297d6d4f8c09ca`
- CIRCT: `firtool-1.75.0`
- Config: `GemminiRocketConfig`
- Generated module: `work/upstream/chipyard_gemmini/sims/verilator/generated-src/chipyard.harness.TestHarness.GemminiRocketConfig/gen-collateral/Gemmini.sv`

## Port boundary

The generated `Gemmini` module has 157 ports:

| Boundary | Port count | Meaning |
|---|---:|---|
| `io_cmd_*` | 49 | Rocket RoCC command plus architectural status/privilege fields |
| `io_resp_*` | 4 | RoCC response and register result |
| `io_ptw_*` | 80 | Page-table walker request/response and PMP/status context |
| `auto_spad_id_out_*` | 20 | TileLink scratchpad/accumulator client, including A/D channels |
| `io_busy`, `io_interrupt` and clock/reset | 4 | Tile/RoCC lifecycle signals |

The module is instantiated at `RocketTile.sv:1000` and connected as follows:

- `io_cmd_*` is driven by the Rocket command router (`RocketTile.sv:1023-1072`);
- `io_resp_*` is consumed by the Rocket response arbiter (`RocketTile.sv:1073-1077` and `1841-1852`);
- `io_ptw_*` is connected to the Rocket PTW (`RocketTile.sv:1078-1158`, `1401-...`);
- `auto_spad_id_out_*` is connected to TileLink buffers and the system bus (`RocketTile.sv:1003-1022`).

## Integration conclusion

The official generated Gemmini cannot be connected directly to the project
128-bit hetero command shell as a small standalone Matrix macro. A faithful
wrapper must either:

1. retain the generated RocketTile/RoCC/PTW/TileLink context and translate the
   project descriptor into a RoCC command sequence; or
2. introduce a deliberately modified Gemmini generator that exports a new
   standalone operand/scratchpad boundary after the official baseline is
   closed.

The current project therefore keeps the official Gemmini as an independently
generated and cycle-tested baseline, while the clean-room integrated numerical
shell provides the L11 Matrix/SFU/KV contract. No direct official-macro
equivalence is claimed until the RoCC/PTW/TileLink adapter is implemented and
verified.

Evidence of the current official baseline is in
`reports/stage_gate_status.json` and
`work/results/gemmini_baseline_minimal_v3/`.
