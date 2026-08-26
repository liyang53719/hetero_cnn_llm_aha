# L5 q384 operation-count controller

Status: PASS for RTL command/count sequencing; q384 numerical payload and
measured latency remain pending.

The24-command controller counts35,094,528 Matrix steps,344,064 RoPE pairs,
887,040 dot/online updates,4,608 reciprocals,36,864 normalization chunks,
3,440,640 SiLU scalars and215,040 product chunks. Score-matrix commands are
zero; measured-latency-valid remains low. Command FNV64 is `8477806a1ef3a7d2`.
Build allocation was234 MB and simulation7 MB, with no OOM.
