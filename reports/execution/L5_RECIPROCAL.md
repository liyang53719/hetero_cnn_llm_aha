# L5 FP32 reciprocal

Status: PASS primitive; L5 remains `IN_PROGRESS`.

Positive normal inputs with exponent 2..253 use a 16-segment mantissa linear
estimate, one fixed Newton-Raphson iteration and exact power-of-two scaling.
Zero maps to +Inf, +Inf to zero, and unsupported negative/NaN/subnormal inputs
to qNaN with domain error.

Dense and 10k-random maximum relative errors are 9.31905e-7 and 9.19391e-7,
below the frozen 2e-6 threshold. RTL is exact to the operation-order model,
accepts one input/cycle and produces FNV64 `39c9a60dc4466b55`.
