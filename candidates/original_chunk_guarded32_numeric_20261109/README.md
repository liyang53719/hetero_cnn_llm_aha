# Guarded runtime32 original-Chisel phase-1 checks

## Completed numerical evidence

Both single-chunk runs passed with the original GdnRuntimeChunkLoadPrepV2Owner and original HeteroFP32Alu/HardFloat AddRecFN in ChiselTest/Treadle. Each run admitted runtime valueHeads=32, keyHeads=16, M128, head0, guarded TwoSum cumsum; chunk0 and chunk1 were separate fresh runs.

Each case performed 832 actual hardware FP32 Add requests/results, 1,600 memory reads and 1,600 writes, completed in 8,064 simulated cycles, and bit-compared all 25,600 output words against the pinned scalar oracle. This covers Q/K/V copy words, cumulative gate/beta words and padding. Total: 51,200 words. The DUT done status, drained flag and stageComplete were asserted. Runtime32 addresses use 51,200-byte prepared rows, 16,384-byte role strides and gate offset 49,152.

Chunk0: 90.48 wall seconds, 94.53 CPU seconds, 185,576 KiB max RSS. Chunk1: 89.67 wall seconds, 93.99 CPU seconds, 184,012 KiB max RSS. Both exited 0 under independent 120 CPU / 150 wall-second caps. Compile exited 0. Compact progress and resource measurements are in SUMMARY.json.

The prior run batched legacy and guarded cases under one 160 CPU-second cap. The direct terminal cause was SIGXCPU. The new runtime32 cases alone required about 188.5 CPU seconds; their independent completion supports budget insufficiency rather than an intrinsic guarded deadlock. The earlier runtime16 guarded cases were not rerun, so their success and absence of every possible prior stall are not established. No legacy case was rerun. No simulation result from the earlier incomplete guarded runs is inherited.

## Scope and limits

This is a phase-1 simulation unit check, not a full block or RTL/hardware qualification. Full original M128 block acceptance remains 0/5. There is no evidence here for the fixed4096-MAC implementation/QoR, other heads, prepared producer, derived/exp/matrix/solve/state stages, full Host, shared scalar arbitration, transport stalls/errors, or root publication. Previous-stage receipts are synthetic prerequisites; they do not prove those stages ran. Numeric policy.decay is set to1 but phase1 does not execute decay.

The wrapper registers the original hardware ALU result. It does not replace floating-point additions with software arithmetic. The supplied memory service is always ready, with one outstanding transaction and matching tagged responses. Counters and simulator throughput are testbench evidence, not hardware performance estimates.

## Identity

Thirty pinned Scala inputs comprise 29 complete original files and PreparedReceiptExactExcerpt.scala, an exact receipt-class excerpt with package/import declarations added as a compilation adapter. Original arithmetic/owner bytes are unchanged. SOURCE_PINS.json describes the excerpt selection and hashes. MAIN_IDENTITY.json records byte equality to the published local candidate plus exact-commit remote pin checks. The main checkout was not reconstructed or modified.

EXECUTED_SOURCE_HASHES.json binds the actual compiled harness, generated stimulus and local launch script. FINAL_SOURCE_HASHES.json binds the portable deliverable. The final harness and generator are the same bytes used in the completed numerical runs. The portable runner replaces local path discovery only; it passed syntax/identity checks, but was not used to repeat numerical simulations. The local launch script is retained as historical source in results/ExecutedLocalRunner.py.

## Offline reproduction

Use Python3, Java21 and local official Maven jars matching DEPENDENCIES.json:

    python run.py --jar-dir /path/to/jars --chunk 0 --verify-only
    python run.py --jar-dir /path/to/jars --chunk 0
    python run.py --jar-dir /path/to/jars --chunk 1

Use a fresh copy for each reproduction to preserve archived summaries. The runner only selects guarded runtime32 cases; it cannot rerun legacy cases. Each invocation compiles and runs just the selected chunk with finite limits. Multiple --jar-dir arguments are supported. No network download is performed. DEPENDENCY_USAGE.json identifies the32 used jars and five absent entries that were unnecessary for this execution path.

The generator verifies scalar_core.py bytes before executing the buffer, avoiding stale bytecode. Fixture.scala is generated locally and must not be published. The source package excludes jars/classes, generated fixture words, FIRRTL/IR, raw logs, array dumps and weights. No Host job, old PID40532, reservation or other checkout was changed.
