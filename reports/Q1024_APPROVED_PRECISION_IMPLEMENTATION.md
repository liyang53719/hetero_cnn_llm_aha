# Approved mixed-precision implementation

- Matrix operands at most BF16, FP32 accumulation; no FP32-operand Matrix array.
- Ordinary tensors BF16; sensitive operations may retain FP32 based on evidence.
- Preserve FP32 for OProj/Down results and attention/final residual tensors. Archived boundary analysis exceeds0.002 with BF16 rounding at these boundaries.
- Threshold0.002 unchanged; no reference substitution or reduced coverage.

Execution order:

1. Add explicit compiler precision policy. Determine dtype by producer binding identity before allocation so all aliased roots agree; resize DDR allocations, retain existing public codes.
2. Emit into a new directory; do not overwrite current frozen descriptor images or simulation inputs. Legacy BF16 generation remains reproducible via explicit legacy mode.
3. Add runtime BF16/FP32 writeback to the same Matrix payload and validate data, byte enables, row pitch, bounds and backpressure. Matrix A/B remain16-bit.
4. Propagate destination dtype through descriptor decode, grouped controller, DMA strides/counts and actual-output export. Keep Q/K/V BF16 behavior unchanged.
5. Match residual/SFU loaders to FP32 producers; retain explicit BF16 conversion at subsequent Matrix inputs. Regress numeric gates before claiming integration PASS.
6. Integrate portable IEEE754 TB comparison after frozen attention service finishes. Existing hi/lo PV evidence is not a pure single-BF16-probability path; re-audit this boundary under the approved policy before release.

No polling of the waiting service. One heavy task, CPU8-23, max30GiB, child commands<=600s. HANDOFF<=40 lines. Implementation or reference alignment is not claimed until verified.
