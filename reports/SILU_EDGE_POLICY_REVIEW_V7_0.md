# Fused SiLU edge-policy review v7.0

The existing 128-entry FP16 direct-SiLU LUT candidates remain valid for ordinary finite BF16 inference values and have already passed standalone E1/DC. The new bit-oriented special-value sweep found two contracts that were not previously frozen.

## Findings

1. A finite, nonzero BF16 gate can round to `Q4.12 == 0`. The current even-sized LUT has no exact zero grid point, so that input is evaluated near the midpoint and can produce about `9.9945e-4` instead of a local `x/2` or FTZ result.
2. A finite gate at or below the `-8` clamp is forced to zero. Multiplying that approximation by an infinite `up` operand produces NaN (`0 * Inf`) while exact finite SiLU would retain a nonzero sign and yield an infinity class.
3. NaN comparison must be class-based; payload bit-exactness is not a stable cross-tool contract.

## Decision gate

Do not select the final one/two-lane implementation until the edge contract is reviewed. The recommended minimum inference-oriented policy is:

- preserve NaN class, not payload;
- define an explicit FTZ/local-zero rule when finite nonzero `gate` maps to `Q4.12 == 0`;
- define the finite-clamped-gate times infinite-up class, or explicitly state that Inf is diagnostic-only and require deterministic NaN behavior;
- add zero, subnormal, LUT-boundary, Inf and NaN-class vectors to the local RTL test.

## Local decision and closure

The policy review is now approved:

- finite nonzero `gate` with `Q4.12 == 0` uses the local `gate/2` limit;
- finite gate clamped at or below -8 times infinite `up` follows IEEE and
  produces NaN class;
- NaN comparison remains class-based.

The q12-zero RTL correction removed the approximately `9.9945e-4` midpoint
bias. One- and two-lane E1 and 1 GHz DC were rerun and pass. Final lane
selection still requires measured producer stall.
