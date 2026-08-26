# L5 RMSNorm and SiLU

Status: PASS primitives. The heterogeneous SFU primitive set is closed; L5
remains `IN_PROGRESS` for block integration.

The 16-lane RMSNorm composes FP32 square, balanced reduction, epsilon, closed
rsqrt and two per-lane multiplies. Ten thousand vectors pass in 50,001 cycles;
maximum float64-reference error is 6.77e-7 and FNV64 is `4bc51b06e7de8d31`.

Stable SiLU computes exp(-abs(x)), reciprocal(1+exp), and sign-selected output
without positive-exponent overflow. Ten thousand vectors over [-16,16] pass in
83,334 cycles; maximum error is 0.00016854 and FNV64 is `327f224f2976b9e0`.
