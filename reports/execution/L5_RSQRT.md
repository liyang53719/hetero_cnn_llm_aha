# L5 FP32 reciprocal square root

Status: PASS primitive; L5 remains `IN_PROGRESS`.

Exponent parity selects mantissa normalization into [1,2) or [2,4), each with
16 linear segments. One fixed Newton step and exact power-of-two scaling give
dense/random maximum relative errors 2.60870e-7/2.39254e-7, below the frozen
2e-6 limit. Ten thousand RTL vectors and special-value policies pass with one
input/cycle and FNV64 `a918b199b4b06b8a`.
