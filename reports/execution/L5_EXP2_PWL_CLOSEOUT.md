# L5 exp2 PWL closeout

Status: PASS primitive; L5 remains `IN_PROGRESS`.

The online-softmax exp2 primitive uses a frozen 256-segment table over [-16,0],
HardFloat floor(x*16) range reduction and HardFloat multiply/add. Below-range
inputs produce zero and nonnegative inputs produce one. Dense maximum absolute
and relative errors are 0.000229600947 and 0.000235417932, below the unchanged
0.00025/0.0003 limits.

Ten thousand exact-PWL RTL vectors pass under backpressure with one input per
cycle and FNV64 `471eda2f98d404cb`. Jointly emitted HardFloat primitives have
SHA256 `2e818b2b26885b73c2475e7a66adaaa00361be27d3ea577a1e196bb1d0484c63`.
