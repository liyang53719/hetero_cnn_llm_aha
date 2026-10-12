# FP32 true-chunk GDN software mapping candidate

This directory adds a real chunk64 computation. M128 executes two chunk
transforms and two sequential chunk state updates per head. It does not loop
over the M1 recurrent owner. It does not change the retained BF16 Matrix
interface, use Matrix, narrow Q/K/state to BF16, or create a new arithmetic
array. This is a candidate mapping onto the existing 16-lane Vector Add/Mul
capability, not an integrated RTL owner. Native production numerical gates,
hardware latency/II, arbitration integration, synthesis, and 80% throughput
acceptance are **not passed or inferred**.

## Source capability and limits

- `integration/gemmini/EmitHeteroFP32Alu.scala:8-17`: each primitive contains
  AddRecFN and MulRecFN, selects Add/Mul, uses FP32 round-near-even and
  tininess-after-rounding, and exposes five exception flags.
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/ElementwiseMemoryEngine.scala:54-58`:
  exactly 16 such lanes are instantiated. Existing owner policy faults on
  flags `[4:1]`, including **inexact underflow**. Exact subnormal products and
  signed zero are supported. The candidate defaults to this policy. Its explicit
  `ieee_rne_finite_gradual_underflow` software mode accepts finite UF/inexact
  while retaining original rounded bits and all exception flags. This control
  selection is not yet connected to the current Chisel owner. The
  retained owner is not already an externally leased matrix/solve engine;
  scheduling these micro-operations onto its lanes remains an explicit future
  integration task. No free external issue port or integrated Chisel exception-policy control is
  claimed.
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala:17-18,74-80`:
  Scalar MulIeeeRne opcode 6 has a different underflow policy. Its existence
  does not silently grant the Vector owner that policy.
- The pinned official `torch_chunk_gated_delta_rule` is at
  `config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py:291-427`.
  `GdnRecurrentOwner.scala:7-28` describes the separate M1 source and cannot
  supply an M128 chunk proof.

All exp requests use the **same caller-owned PrepScalar** as prep, by its
ExpNegative opcode. There is no NumPy exp, libm exp, extra SFU, or second
scalar instance in the implementation. Upper-triangular pair decays become
zero before subtraction/exp and never issue an exp request. Finite nonpositive
arguments retain the original service's `abs(x) >= 80 -> +0` behavior. The
report counts saturations and records the largest magnitude as an FP32 word.
This approximate source exp must still be compared to native output and the
complete native FP32 state. It is not advertised as correctly rounded exp.

`vector16.cpp` is a host accelerator for **Add or Mul on up to 16 lanes**,
with separate FP32 rounding and exception flags. Its optional host batch calls
that same primitive twice, first Mul for all active lanes, then Add, and stops
before Add if Mul faults. It contains no dot, matmul, solver, or reduction
routine. Compilation uses one compiler process,
`-fno-fast-math -ffp-contract=off -frounding-math`; the build receipt binds
source, compiler, arguments, and library hashes. Active lane operations and
vector issues are counted separately. Inexact underflow remains fatal in the default legacy mode, as in the
existing Vector owner. The explicit IEEE candidate still requires an
explicit source policy change and new validation.

Every host primitive call checks FE_TONEAREST and reads x86 MXCSR to reject
FTZ and DAZ before performing arithmetic. It never clears either control bit
or changes rounding mode to make a call succeed. An architecture without this
verified inspection route fails closed. The tiny mode regression changes
controls only in an isolated test process through a test-only helper; the
production library exposes only a read-only environment-status query.

The first numeric failure is retained in `owner.report()['first_numerical_failure']`
with phase, head, chunk, relevant row/column/reduction index, and memory
sequence. A Vector failure adds operation, active lane count, two 16-slot raw
FP32 operand lists, 16 result slots, aggregate flags and per-lane flags.
Inactive slots are null; rejected host environments have no result or flags
because arithmetic was not executed. Diagnostics capture the failing call
directly; they do not rerun it or overwrite the first failure. Scalar/read/
materialization failures identify their own operation and available raw data;
unexposed scalar exception flags are null, never fabricated.

## API and integration

```python
from candidates.qwen35_gdn_prefill.chunk.model import ChunkJob, ChunkOwner, TypedChunkDriver
from candidates.qwen35_gdn_prefill.chunk.vector import Vector16, build_library

# Build explicitly once, and retain ONE Vector16 along with the existing scalar.
vector = Vector16(build_library("/tmp/gdn-vector16"))
owner = ChunkOwner(existing_shared_prep_scalar, vector)
job = ChunkJob(tag=..., input=prep_base, state_in=previous_state_base,
               state_out=new_state_staging, output=core_staging,
               scratch=chunk_scratch_base, tokens=128, cold=True,
               expected_generation=0)
# Allocate fresh exact output/state/scratch spans in the SAME TypedMemory.
# Prep input must already have actual accepted writes, ACKs and publication.
driver = TypedChunkDriver(owner, memory, job, current_generation=0,
                          published_state_base=None)
while driver.response is None:
    driver.tick()
receipt = driver.response
```

`ChunkOwner(..., host_batch=True)` explicitly enables the optional host-call
batching candidate; the default is `False`. Only adjacent Mul then Add in
`_matmul` and `_solve`, after the same received memory beat, share one Python
to C++ call. Each still executes two ordered, separately rounded logical
16-lane issues, with no FMA. Memory yields, operand arrival, scratch requests,
write ACKs and model ticks are unchanged. The first fault retains the actual
failing operation's operands, rounded results and lane flags; a Mul fault
does not count or execute Add. Both primitives independently apply the same
read-only rounding/FTZ/DAZ guard and preserve caller sticky exception flags.

The report exposes `host_batch` and `host_call_counts` (`single` and
`mul_add`) separately from unchanged `vector_issue_counts` and
`vector_lane_operations`. Reset preserves the selected mode, and changing
it during an admitted driver job is rejected. Fewer host calls or lower CPU
wall time imply no hardware-cycle, bandwidth, II or throughput improvement.

The input always has the real prep layout `[M,6400]` FP32, row stride 25,600
bytes: Q2048, K2048, V2048, and 16 gate packets of `(g,beta,14 positive zeros)`.
Q is already L2-normalized and chunk-scaled; the chunk owner does neither
again. K, V, Q and state remain FP32 throughout. Beta's existing BF16
materialization is supplied by prep, not repeated by this owner.

Default output is packed BF16 `[M,16,128]`, row stride 4096 bytes. Default
state staging is FP32 `[16,128,128]`, 1,048,576 bytes. Both are independent
complete spans. M128 core output is 524,288 bytes. All address computations
use checked aligned 56-bit spans; every allocation, including unused cold
state-in address range, must be disjoint. The API does not accept arbitrary
strides. It rejects M outside 1..128 and generation overflow.

Reduced heads / Dk multiples of 16 / Dv multiples of 32 are explicitly
synthetic test geometry. They retain the real prep input offsets and stride,
but their **output and state spans are compact reduced geometry**, not
zero-filled production-size tensors. Their arithmetic dimension is reported;
they do not certify production geometry. Default geometry has no such change.

For a warm call pass `cold=False`, the exact current generation, and
`published_state_base=job.state_in`. That base is the caller's last committed
state, and its bytes must be a non-readonly TypedMemory region with every beat
actually written, ACKed and published. A readonly/native fixture, earlier
unpublished state, or merely plausible dimensions do not qualify. Cold jobs
write zero initial state into workspace and **never read state_in**.

Success only creates a `ChunkResult` with `staging_complete=True`. Neither
`TypedChunkDriver` nor `ChunkOwner` publishes output/state, commits history,
or advances generation. The block coordinator must validate the two complete
staged spans plus its other state dependencies, atomically publish all of its
state, and advance generation once. Failure may leave partial private writes;
they are unusable and no receipt claims a joint commit. No root coordinator
or frozen-prefix implementation is changed by this candidate.

## Dataflow and storage

Per chunk, with all reductions ascending from positive zero:

1. Ascending FP32 cumulative g; padded rows have Q/K/V/g/beta zero.
2. Kbeta, Vbeta, pair decay, Qdecayed, Kdecayed, and Kbeta-decayed.
3. `ut = (Kbeta @ K.T) * pair`; `intra = (Q @ K.T) * pair`.
4. Unit-diagonal forward solves for Vbeta and Kbeta-decayed. Each row forms
   an ascending FP32 sum of previous solved rows and subtracts it from RHS;
   the stored ut diagonal is ignored and no division is needed.
5. `vnew = solvedV - solvedK @ state`.
6. `out = Qdecayed @ state + intra @ vnew`.
7. `next = state * chunk_decay + Kdecayed.T @ vnew`.

Every Mul and Add is separately FP32 RNE. Subtraction is sign-bit inversion
plus Add. Dot K order is explicitly ascending. These choices can differ from
Torch/BLAS reduction and triangular-solve order, so synthetic bit agreement
with the independent matching-order oracle is not native numerical signoff.
Only final core storage rounds BF16 RNE. State never rounds BF16.

All 24 named intermediate matrix types and the initial state use an explicit
single-assignment DDR scratch allocation described by `ScratchPlan`.
`job.scratch_bytes` is its exact required extent. The largest local matrix
cache is a 16x16 transpose tile (1024 bytes), reused for K and decayed K;
that is its FP32 payload size, not Python object storage or a certified
hardware-register allocation. The Python `_compute` generator retains at
least nine FP32 lists across suspension, plus nested helper locals. The host
adapter has 64 FP32 buffer words, 16 lane-flag words and two issue-flag words;
the rounded product reuses a Mul input buffer. A Vector failure
capture stores up to another 64 scalar words plus Python/container metadata.
Peak live Python storage is not measured, and no fixed total vector/register
bound is asserted. `hardware_register_allocation_established` is false.
No all-token/all-head tensor is kept by the owner. Scratch is private to the admitted owner, written once
per beat, and readable only after that beat's physical write ACK. It is never
published as an externally consumable tensor. Scratch accesses still use
real TypedMemory addresses, guards, write descriptors, data and responses;
the local capability checks access to ACKed bytes without pretending the
whole region has reached public tensor publication.

There is exactly one memory request in flight. Request payload holds under
backpressure. One accepted response discharges that obligation; wrong tags,
wrong byte counts, memory errors or malformed data poison the owner. Reset
during an outstanding transaction drains it into one Aborted terminal.
Reset cannot erase a held terminal. Abort may invalidate held success before
terminal acceptance. Faulted owners remain locked until the transport is
drained and the held terminal retired, then explicit reset permits reuse.

## Focused checks

Run:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m unittest candidates.qwen35_gdn_prefill.chunk.test_model -v
```

Checks include true M128 chunk64x2 with random stalls, independent step-FP32
core bytes and full-state bytes, FP64 mathematical-exp tolerance, actual
cold64/writeback/publication/warm64 continuity on the same resources, final
state-ACK failure, held terminal, abort/reset drain, malformed protocol,
readonly/native input rejection, alias/overflow bounds, original exp
saturation for cumulative g below -80, and retained Vector exception policy.
The original 10-check suite passed in 10.393 seconds before diagnostic changes;
the expanded suite additionally checks FTZ/DAZ rejection and exact first-UF
capture. Those earlier results remain historical evidence, not a substitute
for the revised suite.
Host-batch mode-pair checks compare every held/accepted request, response and
terminal in order, including payloads and tags; all output, full state and
scratch bytes and write/ACK coverage; logical issues, lanes and flags; cold
and warm success; numerical and memory faults; abort/reset drain; and terminal
backpressure. Direct primitive checks include signed zero, exact subnormals,
fatal inexact underflow and overflow, nonfinite inputs, a separate-rounding
versus FMA counterexample, 1..16 active lanes, and unchanged FTZ/DAZ/rounding
controls and sticky exceptions. These are small synthetic tests without
Torch and do not replace actual-boundary or production validation.
No production 16-head M128 run, official native comparison, RTL or throughput
test is performed here.

## Explicit IEEE exception candidate and preserved failures

`Vector16(..., exception_policy="ieee_rne_finite_gradual_underflow")` selects
fatal flags `[4:2]` instead of the legacy `[4:1]`; the arithmetic result and
raw five flags are unchanged. Both modes reject nonfinite operands/results,
invalid/div0/overflow, non-RNE rounding and FTZ/DAZ. The original C ABI still
selects the legacy mask. The typed driver binds both policy and mask through
the transaction. This is a software control candidate: sharing the physical
Vector and adding a latched policy selection in Chisel remain open.

The real legacy all-head M16 boundary run reached its staging terminal in
174.48 host seconds, with all 32,768 BF16 core and 262,144 FP32 state words
matching the independent fixed-order reference. The following M128 attempt
rejected the first finite inexact-underflow result in 0.153 host seconds; its
failed receipt is retained, not reclassified. Head0/chunk0/row18/lane4 computes
`b7ae8141 * 07dd24d3 = 804b5f58`, a valid negative subnormal with flags 3.
The explicit policy tests cover that case, ties-even, signed zero, gradual
subnormals, unchanged legacy rejection, fatal exceptions, and complete small
chunk/batch equivalence. They do not imply the production fullblock passed.

The original ExpNegative saturation remains unchanged. Its M128 prepared
input domain has 70,688 requests, 4,705 arguments of magnitude at least80,
and 1,618 nonzero native results discarded by saturation (largest1.775e-35).
This is a local primitive diagnostic, not a bound on final output/state.
Fullblock native thresholds and all end-to-end gates remain required.
