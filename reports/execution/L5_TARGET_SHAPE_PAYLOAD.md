# L5 target-shape segmented payload aggregate

Status: PASS for segmented RTL payload; target-shape closure remains
`IN_PROGRESS` until the integrated controller trace/count passes.

Eight restartable receipts form one exact hash chain from two hidden1536 input
tokens through RMSNorm, Q/K/V, split-half RoPE, post-RoPE GQA, streamed M/L/O,
OProj, both residuals and the 8960-wide MLP. Every saved node passes and no
score matrix is materialized.

Measured array steps sum to 1,486,848: 122,880 QKV, 73,728 OProj, 860,160
gate/up and 430,080 down. Measured Matrix cycles sum to 5,947,392. All segmented
RTL cycles sum to 6,036,046, including 88,654 non-Matrix cycles. Final SHA256
is `872ffcab7daf957e1e4caf3db5c8e063e95bfe760ec5060fcb4264f6c66deffe`.

These are sums of measured restartable payload segments, not a single
integrated-controller runtime. The next gate must replay the same operation
sequence through one RTL controller and separately classify its trace/count
cycles before target-shape closure.
