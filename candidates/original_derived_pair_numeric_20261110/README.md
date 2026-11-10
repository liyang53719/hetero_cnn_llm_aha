# Original phase2 derived/pair owner with real scalar and vector arithmetic

## Scope and source

This harness instantiates the unchanged pinned `GdnRuntimeChunkDerivedAndPairV2Owner`,
`BlockScalarFloatPolicyV2`, and `UnifiedVectorElement32BankV4`, with their real
HardFloat arithmetic. It runs head0/chunk0 of an M128/runtime16 legacy job.
The physical bank source remains the original 32-lane module. The testbench
routes sixteen payload lanes to its low sixteen and pads the upper sixteen with
+0, matching the ordinary client lane convention. Optimization may prune constant
upper-lane logic: this is not evidence of physical 32-lane or 4096-MAC resources.

The single-owner testbench adapter retains vector policy/gradual/format mode until
response. It is explicitly NOT the original production authority router, lease
manager, scheduler, or full top. Scalar and vector results are calculated by the
original hardware, not software responders.

## Synthetic prerequisite and oracle

The prerequisite phase1 memory is regenerated from the pinned `scalar_core.py`
synthetic fixture and legacy cumulative recipe. Its receipt is supplied by the
testbench. This is not producer-authenticated stage provenance and does not rerun
or establish phase1 execution. Python executes the hash-verified source bytes,
not imported bytecode. No trained weights, user payload or NPZ is used.

Expected phase2 writes follow the exact scalar source order: kb=K*beta,
vb=V*beta, kbg=kb*exp(cumulative), qg=Q*exp(cumulative),
ke=K*exp(final-cumulative), and the lower-triangular exponential pair matrix.
Every FP32 node rounds separately. This is the original approximate exponential
recipe, not correctly rounded exp or Torch equality.

A full phase2 completion requires all 2,816 accepted write beats (180,224 bytes),
235,584 read bytes, exactly 2,209 scalar exponentials, 2,144 vector adds and
2,560 vector multiplies, each with matching request/result counts. The harness
also checks decay value and its context/layout/head/chunk identity, numerical
policy, receipt identity/status/drain fields, and three cycles of held done.
Actual accepted write data is recorded in a local memory image for possible
subsequent stage integration. That image is not a published artifact.

## Bounded execution and native compatibility

The initial Treadle calibration is retained separately. It hit the 90 CPU-second
limit after elaboration and before its first 100-cycle checkpoint. It is NOT a
partial numerical pass and does not establish any throughput or write count.
No full Treadle run is attempted.

Native simulation uses the independently verified official Debian Verilator
5.032 wrapper and pinned JNA5.13. The first native attempt failed before simulation
at GCC PCH inclusion: ChiselTest forces the top header before Verilator's generated
PCH, violating GCC's first-header requirement. The runner sets make variables
`VK_PCH_I_FAST=` and `VK_PCH_I_SLOW=` to disable only automatic PCH inclusion.
Generated C++ sources still include their ordinary generated headers; no circuit
source or arithmetic is changed.

Run offline:

    python run.py --jar-dir ../tail_identity_1934/runtime \
      --jar-dir ../host93_class_compile_attempt_v1_20261018/dependencies \
      --jar-dir ../host93_jar87_acquisition_attempt_v1_20261018/artifacts \
      --verilator-dir ../native_phase2_probe_0033/runtime

The default native job limit is 150,000 cycles and 240 wall seconds. JVM heap is
2,400 MB and ActiveProcessorCount=1 bounds compiler jobs. Each process tree has
its own process group; timeout kills that group and waits for its main process.
PID, start-time ticks, boot identity, elapsed time and terminal result are saved.
Source/JAR hashes and executed source hashes accompany each result.

`SUMMARY.json` states what actually executed. `DELIVERY_FILES.json` is the source-
only publication allowlist. Generated fixture TSVs, decay input, actual memory,
classes, RTL/IR, native outputs, runtime files and raw logs are excluded.

Even a full one-head/chunk phase2 pass does not prove another chunk/head/policy,
phase3/4, the full original M128 top, BF16 boundaries, trained models, synthesis,
timing or QoR. Five full original-Chisel M128 blocks remain 0/5. The architecture
target remains 4096 MAC / 8x512 / Vector32 unchanged. No checkout edit or push is
performed by this directory.
