# L5 unified q128/q384 measured prefill trace

Status: PASS.

One runtime-configured controller binary executes q128 and q384 sequentially
without recompilation and rejects unsupported q256. Its 24 commands use only
latencies already measured by the corresponding numerical RTL subgates.

- q128: 11,698,176 Matrix steps, 61,101,824 active cycles and 61,101,874 wall
  cycles.
- q384: 35,094,528 Matrix steps, 202,769,664 active cycles and 202,769,714 wall
  cycles.
- Both lengths issue 24 commands and zero score-matrix commands.

At 1 GHz, the single-block measured throughputs are 2,094.86 token/s for q128
and 1,893.77 token/s for q384. These are one-block RTL controller rates, not a
28-layer end-to-end model claim.

The shared binary SHA256 is
`bbbf19355c8793cd90a1f413cdcb82b740df55347b85cde3570472289761b979`.
Command FNV64 values are `29012cbdbd1b3252` and `f6753b21f668b852`.
