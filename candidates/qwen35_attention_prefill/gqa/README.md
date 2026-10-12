# Memory-fed BF16 causal GQA software model

This candidate models the existing `Bf16CausalGqaOwner.scala` recipe using the
caller's one `MatrixService`, one `NormRopeScalar` and one `TypedMemory`. It is
source-only software execution, not Chisel/RTL execution, native acceptance,
physical RAM inference or hardware timing evidence. It creates no Matrix,
Scalar or DMA instance and performs no alternate attention-reference math.

`Bf16CausalGqaJob` admits BF16 Q `[tokens,8,256]`, K/V
`[cache_length,2,256]`, `tokens <=128`, `cache_length <=256`, and
`query_start + tokens == cache_length`. K starts at `cache_base`, V at
`cache_base + capacity_tokens*1024`. The entire combined capacity is reserved
for alias checking; the actual published K and V regions cover valid tokens
and may be physically separate allocations with a gap. Context is one output
`[tokens,8,256]`. All three inputs require actual upstream producer writes,
ACK coverage and terminal publication; readonly/oracle inputs are rejected.

## Arithmetic and resources

The owner retains exactly these packed arithmetic payload banks:

| Bank | Geometry | Bytes |
| --- | --- | ---: |
| Q | 16x256 BF16 | 8192 |
| K | 32x256 BF16 | 16384 |
| score/exp/probability (reused) | 16x256 FP32 | 16384 |
| QK terminal | 16x32 BF16 | 1024 |
| context terminal | 16x256 BF16 | 8192 |
| V | 256 BF16 | 512 |

There are also bounded maxima/seen/control values. These logical payload
counts do not claim Python object sizes or physical bank allocation. Matrix
owns its existing accumulator and held immutable 16x256 FP32 result.

QK uses rectangular normal profile 1, opcode `0x23`, slice mask 1, 256 steps.
PV uses the same profile, opcode `0x24`, mask 255, `cache_length` steps. Step
index always increases from zero; context is zero; clear is first only;
last/finish/emit are last only. There is no legacy reply. The actual Matrix
result is retired after provisional conversion of all active 32-lane beats,
then the actual matching MatrixDone is retired before consumers may use it.

Two explicit QK operand routing policies are supported:

- `QkOrder.LegacyAscending`: production source order d0..255.
- `QkOrder.PairHighFirst`: d=`index ^ 1`, therefore 1,0,3,2,...,255,254.

LegacyAscending is the default and preserves the production route.
PairHighFirst is explicitly selected by a candidate caller, motivated by the independent
fullshape diagnostic in `work/l3_matrix_qk_pair_diagnostic_20261012`. That prior
evidence does not itself validate this owner integration. The policy is not
AVX512 BF16 instruction emulation: no DAZ/FTZ behavior is claimed. There is no
coordinate-specific arithmetic or output correction.

QK rounds to BF16, scale 1/16 is a separate shared FP32 multiply then BF16
rounding, and row maxima include only causal keys. Softmax uses source FP32
subtract, shared degree-7 ExpNegative, increasing-key FP32 sum/division, and
terminal BF16 probabilities. An unmasked difference <= -80 is Unsupported,
with attention status 3; there is no silent saturation or threshold change.
Masked probabilities are exact zero. PV accumulates every key in increasing
order, including masked zero probabilities, then converts to BF16.

## Integration and lifecycle

Construct `Bf16CausalGqaOwner(matrix, scalar, observer=None)`, a validated
`Bf16CausalGqaJob`, and `TypedBf16CausalGqaDriver(owner, memory, job)`. The
driver accepts no intermediate arithmetic arrays. Continue its `tick()` until
`response` is present. Ready controls independently stall memory requests,
memory returns, Matrix group/step/result/done, scalar calls and owner terminal.
Successful Context publication requires every actual write-data beat, every
successful ACK, every Matrix result/done, and accepted successful owner
terminal. The same Matrix ownership remains held until terminal acceptance.
Whole-block generation/root publication is deliberately outside this owner.

The host adapter seals actual producer write/ACK coverage as exact immutable
frozensets after full validation. Tick boundaries check the sealed object
identities, while source bytes are still compared on every tick and terminal
hashes remain mandatory. Output metadata is temporarily mutable only around
the existing real memory write/ACK calls, then validated and sealed again.
Only after terminal acceptance is output metadata returned to ordinary sets,
so an untouched aborted destination remains reusable by other producers.
This reduces Python integrity-check work without changing modeled requests,
arithmetic, cycles, bytes, or hardware resources. Injected exceptions inside
memory methods remain fail-closed; resumable drain is not promised for them.

Errors and explicit abort drain accepted memory and held Matrix result/done,
publish no Context, and poison admission until owner and shared Matrix receive
a coordinated reset after terminal retirement. The synchronous scalar API
has no unreturned accepted request; scalar-ready models request acceptance,
not a latency pipeline. Explicit software abort and late-ACK byte accounting
are transport-model extensions, not claims about a Chisel abort pin.

Optional observer events have signature
`(stage, token, head, first_key, tuple_of_FP32_words)`. BF16 nodes are widened
by shifting left 16. Stages are `qk_bf16`, `scaled_scores_bf16`,
`row_max_fp32`, `score_difference_fp32`, `exp_fp32`, `sum_exp_fp32`,
`probability_fp32`, `probabilities_bf16`, and `context_bf16`. The singular
probability event is each actual returned division result before BF16
conversion, or zero from the actual masked-probability branch. No native
masked-logits addition is invented. Only actually computed nodes are
reported. Callback return values are ignored. All retained observer snapshots
and driver identity snapshots are explicitly host-only diagnostic storage.

## Small tests

`test_gqa.py` requires explicit prebuilt `MATRIX_SERVICE_LIBRARY` and
`MATRIX_SERVICE_COMPILE_RECEIPT`, verifies their exact source/compile identity,
and never builds or searches for a library. Missing or invalid bindings fail
the suite rather than skipping it. `run_small_tests.py --out <fresh-dir>`
records actual test exit and source/library identities before and after.
The normal small runner includes both `test_gqa` and `test_coverage_seal`.
Most tests use <=2 query tokens and <=3 cache tokens; one explicit synthetic
M17/cache33 case crosses both bounded tile loops and independently accounts
for BF16 probability rounding in every expected context value. Tests use
an independent system `libm.fmaf` QK witness, hand-computable causal uniform
softmax/PV, real synthetic producer data/ACK/terminal publication, and transport
fault cases. It neither fetches a model nor runs full M16/M128 fixtures. A
passing small gate is not fullshape numerical acceptance or hardware signoff.
