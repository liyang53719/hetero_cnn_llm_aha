# L5 hidden256 tiled GEMV

Status: PASS Matrix-only hidden256 subgate; L5 remains `IN_PROGRESS`.

One 256x256 BF16 GEMV is tiled onto the unchanged physical logical 16x32 array:
eight output-column tiles and 256 K steps per tile, for 2,048 accepted steps.
All 256 FP32 outputs match a libm-fmaf golden. Measured cycles are 8,601 and
output FNV64 is `a2406e28b5b747eb`.

Only array row0 is active for this one-token GEMV, so active-lane utilization is
6.25%; useful end-to-end MAC/cycle utilization is about 1.4883%. These values
are reported rather than claiming the 512-MAC peak for a batch-one GEMV.

This does not close hidden256 block integration; global chunked RMSNorm and all
remaining nodes still follow.
