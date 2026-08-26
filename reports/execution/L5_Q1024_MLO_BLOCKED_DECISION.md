# L5 q1024 causal M/L/O numerical blocker

Status: DECISION_READY. L5 remains IN_PROGRESS pending production-RTL approval.

The q1024 streamed golden consumes all frozen q1024 RoPE/GQA hashes and runs
6,297,600 causal updates without materializing a score matrix. The existing
single-chain FP32 online M/L/O policy completes, but its maximum attention
error is `0.00535758407`, above the frozen `0.002` threshold.

Increasing only the exp2 PWL from 256 to 1024 segments does not fix the issue:
the error becomes `0.00543530853`. M hashes are identical while L/O/attention
change, showing that long-chain FP32 state accumulation—not local exp2 table
resolution—is the dominant blocker. The threshold must not be relaxed.

Recommended decision: add a hierarchical online-softmax mode with fixed
128-token blocks. Each block produces FP32 M/L/O using the existing engine;
block summaries are merged with the standard stable M/L/O merge equations.
For q1024 this adds 43,008 head-block merges and needs only current block plus
global M/L/O state (about 12.2 KiB for 12 heads), never a score matrix. Keep
q128/q384 in legacy mode to preserve their accepted hashes; select block mode
at runtime for sequence lengths above 384 in the same RTL binary.

Alternative: widen long-lived L/O state and merge arithmetic to FP64. This has
larger RTL, verification and early-PPA impact and is not recommended before the
block-128 candidate is evaluated.

The block-128 operation-order candidate has now been evaluated and passes:
maximum attention error is `0.000612999275`, with 43,008 summary merges and no
score matrix. Its M/L/O/attention hashes are `ab9a5d50...`, `7598efac...`,
`5a05bb37...` and `0aaf1c76...`. A refactored 8-worker legacy q128 run
reproduces all four accepted hashes exactly. This validates the recommended
algorithm but does not authorize or prove the production RTL change.

RTL interface audit confirms this is a real architectural extension. The
accepted `fp32_online_softmax` exposes only `clear`, score/value input and
current M/L/O output; it cannot load or merge an external summary. The minimal
implementation is therefore a sibling `fp32_online_softmax_merge128` micro-op,
not a modification of the legacy token-update module. It would consume two
130-word FP32 summaries, reuse two existing exp2 paths plus scalar/vector
add-multiply logic, and emit one merged summary. Serial-head execution needs
1,040 bytes of live state; a 12-head parallel implementation needs 12,480
bytes. The runtime controller would invoke it only after block boundaries for
sequence lengths above 384, preserving the q128/q384 datapath and hashes.
