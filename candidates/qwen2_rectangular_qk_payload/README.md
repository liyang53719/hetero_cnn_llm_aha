# Tiny rectangular QK actual-payload candidate

**Source-only synthetic numerical/address evidence. No existing source edits,
business weights, live/whole-block run, RTL result, timing prediction or changed
acceptance gate.** The normal 16-query rectangle is the bounded first step. It
does not implement softmax, PV, resident-cache transport or a new full owner.

## Exact live arithmetic retained

For every causally selected query/key pair:

1. Convert source FP32 containers to BF16 at the Matrix input boundary.
2. Start each of 16 stripe accumulators at positive zero. Stripe `s` performs
   exactly eight FP32 FMAs at depths `s+16*t`, `t=0..7` in order.
3. Check selected causal lanes for finite results after **every** FMA step.
   Physical noncausal lanes may contain nonfinite values and are ignored,
   matching the live selected-lane policy. Missing query/key padding uses +0;
   real future keys are still physically computed, not replaced by padding.
4. Fold stripes 0 through 15, strictly in order, starting from **positive zero**.
5. Materialize the completed dot to BF16; multiply that value in FP32 by the
   exact scale word `0x3db504f3`; materialize the scaled result to BF16 again.

Fold Add and scale Mul retain the current `legacy_scalar` fatal policy for
invalid/div0/overflow/inexact-underflow. FMA underflow flags alone are not fatal;
the Matrix owner checks selected finiteness. C++ host arithmetic requires RNE
and rejects FTZ/DAZ/non-RNE MXCSR. It is compiled without contraction/fast-math;
FMA explicitly calls `fmaf`. These checks are software evidence, not an FPU/RTL
validation. Finite payload outputs are compared bitwise, including signed zeros.

The old rectangular script's unrounded FP32 score is **not** used. A fixed
synthetic witness has total `0x3f808000`, rounds its dot to `0x3f800000`, and
produces a different score from scaling the unrounded dot.

## Physical payload and finite storage

The actual native array is `accum[5][16][256]`, totaling 80 KiB. Normal mode
uses `a[row]=Q[qbase+row,depth]`, `b[col]=K[col,depth]`, matching the existing
MatrixPipeline broadcast/column wiring. Five independent stripe contexts run
in groups 5/5/5/1; each terminal partial goes to its fixed B slot before the
strictly ordered scalar fold. Only 1–4 real 32-column slices are enabled for
M≤128. There are still only 4096 physical MAC lanes and five contexts.

The Python runner has exactly the original A 688-KiB and B 80-KiB byte arrays;
input data is actually read by the reused bank/word/byte addresses before forming
native payloads. The maximum original single-KV-head layout reserves 84 KiB
inside A: Q BF16 4 KiB, K and V BF16 32 KiB each, score and probability FP32 8 KiB
each. V/prob are reserved but unused in this QK-only candidate. B reserves five
16-KiB partial slots, 80 KiB total, even though columns above 127 are unused here.
No extra cache allocation is added: this layout is separate from proposals for
a 256-KiB all-head FP32 resident cache, and is not simultaneously double-counted
with that layout. A/B ownership must be remapped only at a drained stage boundary.

One reusable 16-KiB terminal `out` buffer corresponds to existing `finalValue`.
Existing two service result FIFO tiles are not repurposed. The C++ API executes
synchronously; it does not claim that return FIFO, partial-store ACK, context
reuse fences, backpressure, abort or input DMA have been implemented. Actual
debug callbacks observe the partials and completed dot/score from this one
payload execution. Testbench reference/observation dictionaries are not hardware
storage and never feed candidate values.

## Required new interfaces and physical limits

- A new default-off rectangular QK owner/profile must drive five contexts,
  exact stripe/step tags, slice masks, causal-selection metadata, real result
  retirement, B partial store/commit fences and group drain. Existing host normal
  profiles only admit context zero and incompatible group shapes. Their generic
  payload shape is reusable, their current admission is not.
- A selected-causal-lane finite adapter must inspect each returning step. The
  current legacy normal backend tolerates unselected nonfinite cells, but the
  transposed Dense backend rejects all input/final lanes and has 16-aligned group
  bounds. It cannot execute this eight-step/selected-only recipe unchanged.
- A new SRAM gather/partial route and arbitration is necessary. The reused
  token-major A layout has one read port per bank. A full 16Q×128K payload needs
  16 query-word reads plus 128 key-word reads: nine reads per bank. The current
  model performs those element accesses but assigns no cycles and claims no
  free simultaneous gathers or hidden line cache. Partial FP32 store/read costs,
  scalar fold dependencies, input fill and commit fences remain to be scheduled.
- The existing transposed mux candidate could map 32Q×128K to all 4096 cells,
  but requires a new compatible eight-step QK profile and selected-lane policy.
  This batch does not implement or claim that route.

`wide_issues=128` per query tile is **work**, not total cycles. `physical_fmas`
counts enabled slice cells, `16*columns` per issue. The separate
`fixed_4096_lane_issue_capacity` counts `4096*wide_issues`; neither is measured
hardware utilization. `useful_fmas` counts only causal pairs. Every valid score
still needs 16 dependent scalar Adds and one checked scale Mul; that work is
not hidden in the wide-issue count. No claim of 80%/90% whole-block performance
follows from reducing Matrix commands. Hardware cycles/utilization: null.

For geometric context only, M128/12 heads have eight tiles per head, rounded
column counts 32,32,64,64,96,96,128,128. This yields 12,288 proposed QK wide
issues, 15,728,640 enabled-cell FMAs and 12,681,216 useful FMAs. These counts
do not include any softmax/PV, scalar latency or memory schedule.

## Sources

- `candidates/qwen2_resident_matrix/official_bf16/owners.py:118–139`: actual live
  QK depth8 steps, 16-stripe fold and two BF16 materializations.
- `candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py:77–96`:
  default scalar policy, input conversion, selected lane extraction and finite
  checks on every returned step.
- `candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py:73–80,150–184`:
  BF16 and original scalar fatal policy.
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala:67–99`:
  five-context legality and normal `a[16]`/`b[256]` physical broadcast.
- `candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp:178–235`:
  current native profiles, context-zero admission, unselected-nonfinite behavior.
- `scripts/qwen2_rectangular_attention_numeric.py:162–221`: original stripe
  mapping/storage. Its final FP32-only score recipe is intentionally replaced
  here by the current live boundaries, without modifying that script.
- `scripts/qwen2_rectangular_attention_model.py:88–136`: reused physical A/B
  capacities and tensor addresses, not an extra cache.
- `candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp:31–76`
  and `transposed_route/combined_service.patch:108–130`: incompatible current
  transposed admission/finite policy and optional physical mux route.

## Reproduce the bounded tests

```sh
/workspace/shared/hetero-contracts-venv/bin/python -m pytest -q candidates/qwen2_rectangular_qk_payload/test_model.py
/workspace/shared/hetero-contracts-venv/bin/python -O -m pytest -q candidates/qwen2_rectangular_qk_payload/test_model.py
```

Nine tests cover capacity/address uniqueness, actual payload/padding, signed
zero, cancellation, the two-rounding witness, M17 tail/causal mask, unselected
nonfinite isolation versus selected failure, finite/overflow/underflow gates and
eight-step progress. Numeric comparisons use the independently reviewed integer
FP32 FMA/Add/RNE functions, not the C++ candidate's own results as its reference.
Only small synthetic tiles execute; no full-M128 numeric or business run occurs.
