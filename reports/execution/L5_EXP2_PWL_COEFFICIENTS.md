# L5 exp2 PWL coefficient freeze

Status: coefficient/error gate PASS; RTL compile/simulation pending memory
availability, so exp2 and L5 remain `IN_PROGRESS`.

The online-softmax exp2 domain is frozen to [-16,0]. Inputs below -16 produce
zero and inputs at or above zero produce one. The interior uses 256 linear
segments of width 1/16, evaluated as float32(m*x) followed by float32(+b).

Dense per-segment analysis (4097 points per segment) gives maximum absolute
error 0.000229600947 and maximum relative error 0.000235417932, below the
precommitted 0.00025 and 0.0003 limits. An independent 10k directed/random
vector set gives 0.000229384617 absolute and 0.000235373915 relative error.

Tracked artifacts include the coefficient table, policy JSON, HardFloat
floor(x*16) emitter, exp2 RTL and exact-PWL testbench. They are not marked RTL
PASS until the converter is emitted and simulation runs. At this checkpoint
MemAvailable was about 11.5 GiB due to unrelated MATLAB workloads, so no new
SBT/Verilator heavy task was started.
