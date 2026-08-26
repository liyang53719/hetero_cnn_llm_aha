# L5 q1024 causal M/L/O numerical blocker

Status: BLOCKED_DECISION. L5 remains IN_PROGRESS.

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
