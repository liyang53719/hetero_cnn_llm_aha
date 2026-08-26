# L5 target head-dimension-128 scaled dot

Status: PASS as the first target-shape payload subgate; L5 remains
`IN_PROGRESS`.

The RTL reuses one physical 16-lane FP32 multiply/reduction tile over eight
chunks, accumulates partial sums in a fixed order and applies the pinned Qwen
attention scale `0x3db504f3` (`1/sqrt(128)` rounded to FP32).

Ten thousand operation-order vectors pass bit-for-bit. The maximum absolute
error against a float64 dot reference is `7.32342283e-7`, below the frozen
`1e-4` limit. Measured cycles are 262,500, output FNV64 is
`2da983ea0be13f0b`, and vector SHA256 is
`68f4eaa4033ac36ce28223fdf15d81bd5da14b0fc826da48dcf69e8369333dab`.
Strict lint/build/test used CPU 8-25, j4 and the 10 GiB cgroup cap; build
allocation was about 323 MB and simulation allocation 17 MB.
