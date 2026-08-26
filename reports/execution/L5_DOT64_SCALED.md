# L5 FP32 dot64 scaled reduction

Status: PASS as a hidden256 attention subgate; L5 remains `IN_PROGRESS`.

The RTL multiplies 64 FP32 pairs through one physical 16-lane tile, performs a
balanced reduction for each of four chunks, accumulates the partial sums in a
fixed order and applies the supplied FP32 scale. It therefore exercises the
same reduction order used by the hidden256 head-dimension-64 attention path.

Ten thousand deterministic vectors pass bit-for-bit. The maximum absolute
error against a float64 dot reference is `4.04839181e-6`, below the frozen
`5e-5` bound. Measured cycles are 140,001 and output FNV64 is
`a8cdc6c17108168c`. Strict lint, j4 build and simulation used CPU 8-25 and the
10 GiB cgroup cap.
