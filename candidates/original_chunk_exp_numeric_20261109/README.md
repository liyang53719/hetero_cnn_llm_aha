# Original scalar phase-2 exponential numerical unit evidence

This is a bounded actual Chisel/Treadle execution of the unmodified pinned
`BlockScalarFloatPolicyV2`, including its real HardFloat arithmetic circuits.
Policy 0 exercises the original legacy recipe; policy 1 exercises gradual-decay
range reduction and subnormal scaling. No Python callback supplies DUT results.

The source-order oracle is `scalar_core.py`, copied exactly from
`prefill_rounding_1934`. The generator hashes its bytes and executes that verified
buffer rather than importing a potentially stale bytecode cache. Expected values
are the pinned source recipe, not correctly rounded libm exp or Torch equality.

The deterministic synthetic M128 fixture is split into two chunk64 sequences.
For each policy and chunk, select five evenly spaced source-order calls from
cumulative, remain, and lower-triangular pair categories plus the chunk decay.
This samples 64 calls from the two 2,209-call chunk pools per policy; a further
24 calls test signed zero, tiny negative input, legacy saturation, normal/subnormal
transition, underflow-to-zero, and extreme finite negative input. No checkpoint,
trained weights, user input array, or NPZ is used. Generated Scala arrays stay local.

Each result must equal the expected raw FP32 word. The harness changes request
inputs after acceptance, checks busy backpressure and every returned field, holds
results for three stalled cycles, and verifies consume/re-ready behavior.
The numerical oracle does not derive exception flags; zero flags/nonprimitive
status are checked against the module's ExpNegative transport contract.

Run offline with the three existing local jar directories:

    python run.py --jar-dir ../tail_identity_1934/runtime \
      --jar-dir ../host93_class_compile_attempt_v1_20261018/dependencies \
      --jar-dir ../host93_jar87_acquisition_attempt_v1_20261018/artifacts

Every compile/simulation stage is bounded to 90 CPU seconds (95 hard) and 120 wall
seconds with a 1,200 MB JVM heap and one active processor. The pinned dependency
catalog contains five optional unavailable jars; 32 verified local runtime jars
are sufficient for this RawTester path. No sbt or Verilator is involved.

Scope is primitive numerical evidence only: it does not execute the phase-2
owner/vector operations, all 4,418 exponential calls, phase3/4, full M128 blocks,
BF16 boundaries, trained models, synthesis, timing or physical resource proof.
Five full original-Chisel M128 blocks remain 0/5; 4096 MAC / 8x512 / Vector32 is
unchanged. The checkout and remote are not modified by this directory.

`DELIVERY_FILES.json` is the publication allowlist. Generated fixtures, classfiles,
IR, runtime jars, dependency resolution paths, raw logs and test-run directories
are not publishable artifacts. `SUMMARY.json` records the observed result.
