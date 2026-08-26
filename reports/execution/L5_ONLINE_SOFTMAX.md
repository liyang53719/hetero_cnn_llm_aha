# L5 online softmax M/L/O

Status: PASS primitive; L5 remains `IN_PROGRESS`.

The scalar state machine stores only running M, L and four O lanes. For each
token it computes alpha/beta with the closed exp2 primitive and updates L/O in
fixed FP32 operation order. No attention score matrix is materialized.

One hundred 100-token sequences cover rising/falling maxima and long negative
gaps. All 10k state updates match the exact PWL operation model. Final normalized
O/L differs from float64 batch softmax by at most 0.000175086, below the frozen
0.002 limit. RTL uses 49,750 cycles and produces FNV64 `07fbc6afceab5417`.
