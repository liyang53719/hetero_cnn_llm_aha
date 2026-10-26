# Numeric qualification boundaries — not a domain-restricted full MoE PASS

This r2 candidate compiled successfully and reached one real hardware-simulation
transaction checkpoint, then the original five-test attempt failed its CPU120
budget before the first spec completed. The pinned official eager H32 synthetic
Golden is a Torch reference; only the exact partial hardware scope in SUMMARY is established.

## Materialization under test

For each expert in ascending expert ID, and shared last, each lane performs:

1. Expand the already materialized raw BF16 expert output and BF16 weight to
   FP32 by appending sixteen zero bits.
2. Issue the existing shared `ScalarOp.MulIeeeRne` operation.
3. Apply the existing hardware `TensorMath.bf16Rne`; retain the BF16 product.
4. Expand BF16 accumulator and BF16 product to FP32; issue existing `Add`.
5. Materialize BF16 again and retain that accumulator before the next expert.

No TensorMath/BlockScalarFloat arithmetic is changed by this candidate, and
consumer itself instantiates no ALU. The unit wrapper connects one existing
scalar circuit; it is not the final complete4096 hardware or proof of full top
resource sharing. Actual expert down projection/router/shared gate remain
Torch-produced fixture data in this unit test, not Chisel-computed operators.

## Concrete unresolved supported-input gaps

The existing scalar rejects NaN/Inf operands and FP32 overflow. The consumer
also rejects a finite FP32 value that rounds to BF16 Infinity. Official BF16
can produce/propagate those values. This is an explicit unfinished arithmetic
policy, not an assertion that those legal BF16 inputs are invalid:

- `BF16(0x7f7f) + BF16(0x7f7f)` overflows FP32 and BF16; official IEEE result is
  positive Infinity, while the existing scalar reports an error.
- `BF16(0x7f7f) + BF16(0x7b00)` = max finite BF16 + 2^119 gives exact finite
  FP32 `0x7f7f8000`, whose BF16 RNE result is `0x7f80` Infinity. Scalar Add can
  compute the finite midpoint, but current consumer rejects the materialized
  Infinity. This boundary must not be hidden by changing the reference or
  declaring all finite BF16 operands supported.
- NaN/Inf expert outputs are explicitly rejected, not propagated. A later
  shared IEEE policy or justified model-domain contract is required; this
  candidate is not full official BF16 semantics.

These examples are source/IEEE deductions, not newly executed Torch/Chisel
edge-case tests. Any subsequent numeric execution must retain actual
error/flags and separately report tested finite cases and this open gap.

## Why Add-underflow rejection is not silently ignored

Every finite BF16 value is an integer multiple of 2^-133. A real sum of two
expanded finite BF16 values remains on that lattice. If its magnitude is in
FP32's subnormal range (<2^-126), it is one of the exact representable lattice
points with magnitude <128 * 2^-133. It therefore cannot require FP32 inexact
rounding. IEEE after-rounding underflow is tiny AND inexact, so it should not
assert for this particular BF16-expanded Add invariant. This reasoning does
not apply to arbitrary FP32 scalar clients and does not authorize relaxing
legacy Add's error policy. The test checks the real scalar error on every
result and exercises 2 and 4 times the smallest BF16 subnormal in lane2; it
never masks a scalar error. General correctness of the scalar is not proved
by this finite set of cases.

## Protocol boundaries

The consumer has no clear/abort input. Scalar arbitration must bind its single
outstanding request to the original owner until response fire; an untagged
response cannot independently verify an epoch. On failure after a response,
remaining contribution beats are consumed/drained without further arithmetic,
then a held error result is returned with the original identity and zero
payload. Error payload is not a numerical result. Top-level reset/quiescence,
producer receipts and unique transaction lifetime remain integration duties.
