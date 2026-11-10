# Connected original phase1 → phase2 → phase3/4 numerical chain

This one-shot integration instantiates the unchanged original
`GdnRuntimeChunkLoadPrepV2Owner`, `GdnRuntimeChunkDerivedAndPairV2Owner` and
`GdnRuntimeChunkTransposeV2Owner`, with one shared original
`BlockScalarFloatPolicyV2` and original `UnifiedVectorElement32BankV4`.
The case is M128 head0/chunk0, runtime16, legacy cumulative/decay/vector policy.

## Actual stage provenance

Only synthetic prepared Q/K/V/log-decay/beta input beats exist initially in the
memory model. No phase1 scratch values or later outputs are installed from an
oracle. Each accepted memory write is checked against an independent source-order
oracle and stored as the actual downstream memory value.

The original phase1 result bundle is accepted directly by phase2. Context and
layout are retained from the actual initial job acceptance. The original phase2
result is accepted directly by phase3/4. Testbench observation registers retain
these results but do not fabricate the handoff receipts or counts. Both handoffs
require all preceding expected reads/writes and no pending memory response.
Every downstream prepared-scratch read requires an actual phase1 write; every
transpose KE read requires an actual phase2 write.

The input producer/preprocessor receipt and initial-state prerequisite receipt
are still supplied synthetically by the testbench. The test does not execute or
prove those earlier producers, state initialization, Q/K normalization or raw
convolution. Prepared Q is already scaled, as required by the owner interface.
This removes the former synthetic *phase1* receipt/memory handoff, not every
external prerequisite. It is not full prefill or full M128 model evidence.

## Expected completion

- Phase1: 64 actual shared-scalar adds; 1,600 reads and 1,600 writes.
- Phase2: 2,209 exp, 2,144 vector adds, 2,560 vector multiplies; 3,681 reads and 2,816 writes.
- Phase3/4: K and actual KE transposes; 1,024 reads and 1,024 writes.
- Total: 6,305 reads and 5,440 writes, or 87,040 exact FP32 output words.

The harness checks stage receipt status/counts/identity/drain, actual phase2 decay
value and identity, numerical policies, and held terminal results. Missing the
terminal result within 150,000 cycles fails closed with a nonzero assertion exit.
All expectations derive from hash-verified `scalar_core.py` source bytes and an
independent transpose expression. Python never supplies arithmetic responses.
The oracle uses the original approximate exponential recipe, not Torch/libm
correctly rounded exponential equality. No weights or NPZ payloads are used.

## Routing and execution limits

The routing is a sequential, single-job testbench scheduler, not the production
authority/router or full top. The original bank source has32 lanes; only its low16
client path is exercised, with +0 upper lanes that tools may optimize away.
This is not physical32-lane or4096-MAC resource proof. The unchanged target is
4096 MAC / 8x512 / Vector32; full original M128 blocks remain0/5.

Run offline using the existing pinned official dependencies:

    python run.py --jar-dir ../tail_identity_1934/runtime \
      --jar-dir ../host93_class_compile_attempt_v1_20261018/dependencies \
      --jar-dir ../host93_jar87_acquisition_attempt_v1_20261018/artifacts \
      --verilator-dir ../native_phase2_probe_0033/runtime \
      --cycles 150000 --wall-seconds 240

Each native process tree is launched in a dedicated group; timeout kills that
group and reaps its main process. Identity records include boot/PID/start time.
The JVM uses a2.4GB heap and one active processor. The build-only make override
`VK_PCH_I_FAST= VK_PCH_I_SLOW=` avoids the verified ChiselTest/GCC PCH include-order
conflict. Generated C++ still includes its ordinary headers. No original hardware
source is modified. No standalone previously passed suite is rerun.

`SUMMARY.json` records the observed result. `DELIVERY_FILES.json` allows source,
hashes and compact evidence only. Generated TSV/decay/actual-memory data, jars,
classes, native binaries, RTL/IR and raw logs are excluded. The uncompiled draft
`ChainWrapper.scala.txt` is redundant and excluded from delivery.
