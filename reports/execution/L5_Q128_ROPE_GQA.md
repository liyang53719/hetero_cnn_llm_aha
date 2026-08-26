# L5 q128 split-half RoPE and K/V GQA

Status: PASS; q128 causal attention and downstream phases remain
`IN_PROGRESS`.

All 128 positions use pinned theta1e6 and split-half D128 pairing. The RTL
executes 98,304 Q plus 16,384 K pairs, then multicasts rotated K and direct V
from two KV heads to 12 query heads. All 4,096 multicast inputs and 24,576
outputs pass numerically and structurally.

Measured totals are 491,520 cycles: 458,752 RoPE and 32,768 GQA cycles. Q/K/V
GQA FNV64 values are `ce257947e96b814a`, `85a9dab97d66e17d`, and
`aba0a426b0433f1d`. Q-RoPE/K-RoPE/K-GQA/V-GQA SHA256 values are
`1e259f27...`, `39ae84dd...`, `499da9e0...`, `5c3169a4...`.

Lint/build allocations were about 33/425 MB and simulation 10 MB, with no OOM.
