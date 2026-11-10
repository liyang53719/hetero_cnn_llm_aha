# Connected original phase1 → phase5 numerical check

## Result

PASS on the first authorized native run, without retries. Original phase1 load/prep, phase2 derived/pair, phases3/4 transpose and default phase5 ExecuteOwnerV8 ran in one connected test. Runtime admission was M128,16 value heads, head0, chunk0, legacy numeric policy. This checks one64-row chunk, not both chunks or a full block.

The chain completed279513 cycles,41377 memory reads and5696 accepted writes. All91136 output words matched the independent pinned scalar oracle, including the additional256 UT write beats/4096 UT words. Phase5 independently reported35072 reads,65792 vector requests/results and202240 cycles; scratch output acknowledgment was16384 bytes. Terminal status, drained/stageComplete, context/layout/receipt identity and held-done stability were checked.

Actual phase1 handoff occurred atcycle6593 after1600 reads/writes. Phase2 handoff occurred at73176 after5281 reads/4416 writes. Actual phase4 handoff occurred at77273 after6305 reads/5440 writes. Phase5 consumed that actual phase4 receipt, with context/layout/head/chunk and decay wired from the actual transpose result. No synthetic intermediate completion was supplied.

Compile took17.42 wall seconds. The native generation/build/run stage took45.41 seconds, including a4.891-second simulation loop. A dedicated process group,240-second wall budget,210/215-second soft/hard CPU bounds,2.4GB Java heap and one compilation job were used. No failed attempts or reruns occurred.

## Memory and arithmetic provenance

Only synthetic prepared Q/K/V/log-decay/beta input bytes are initially loaded. The prepared-producer and initial-state prerequisite receipts are synthetic. All phase1 scratch, phase2 writes, transposes and UT outputs are actual accepted writes into the same mutable memory map. No oracle memory image replaces runtime data between phases. A frozen set of all5440 actual writes before phase5 guards every phase5 read. All prior phase1/phase2/transpose checks remain in the harness.

Exactly one original BlockScalarFloatPolicyV2 instance is shared by phase1/phase2. Exactly one original UnifiedVectorElement32BankV4 instance is shared sequentially by phase2/phase5. The ordinary route uses low16 lanes and ties upper16 inputs to+0; unused lanes may be optimized away. The bank's32 source lanes are not a physical resource proof. Architecture targets4096 MACs/8x512/Vector32 are unchanged.

The original fresh-top leaf collection selects GdnRuntimeChunkExecuteOwnerV8. Phase5 computes KB64x128 × KT128x64, using ascending-K separately rounded FP32 Mul then Add from+0, followed by one Pair multiplication per output. The independent oracle follows that exact order, without FMA or reassociation. V8 uses the shared ordinary vector route, not MatrixPipeline or a4096-MAC array. The opt-in ExecuteOwner32 route was not selected.

This is a connected numerical unit test, not full prefill/block, trained-model accuracy, physical allocation, QoR, production arbitration, fault recovery or root-publication qualification. Other heads/chunks, runtime32, guarded policies and phases6–17 remain untested here. Full original-block acceptance remains0/5.

## Source identity and reproduction

All40 upstream Scala input hashes are checked before compilation. They include the existing exact receipt-class compilation adapter; original owner/arithmetic bytes were not modified. results/EXECUTED_SOURCE_HASHES.json binds the executed harness/runner/generator. FIXTURE_SUMMARY.json contains stimulus/expected hashes, not their tensor payloads. Existing phase1–4 fixture bytes were verified identical to the passing baseline before launch.

Use a fresh directory to preserve archived results:

    python run.py --jar-dir /path/to/official/jars --verilator-dir /path/to/verified/verilator-wrapper --cycles 1500000 --wall-seconds 240

The runner uses ChiselTest/Verilator with Java ActiveProcessorCount=1 and build-only MAKEFLAGS overrides VK_PCH_I_FAST= VK_PCH_I_SLOW=. These disable forced precompiled-header inclusion, without changing original/generated hardware. It supervises only its own process group. No downloads occur in this runner.

Generated TSV arrays/actual memory, jars/classes, circuit/native files and raw logs remain local and are excluded. No Host, old PID40532, reservation or unrelated checkout was touched.

SOURCE_SELECTION.json contains the exact default LeafCollection selector excerpt and full-file SHA256/git blob, verified against the tracked original-top checkout. It does not claim a new independent fetch of the current remote selector. Phase5 counters65792 are measured vector requests/results; Add/Mul subtotals are source-schedule expectations only, not separately observed counters.
