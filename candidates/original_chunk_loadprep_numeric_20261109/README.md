# Original Chisel load/prep phase-1 numerical check

## Executed result

The byte-pinned original GdnRuntimeChunkLoadPrepV2Owner and original HeteroFP32Alu (HardFloat AddRecFN, FP32 RNE, after-rounding tininess) compiled and executed with ChiselTest 6 / Treadle. The wrapper registers one actual hardware ALU response; it does not calculate the additions in software.

Two completed cases: legacy ascending policy, runtime16, one head, M128 chunk0 and chunk1. Each completed 1,600 reads, 1,600 writes, 6,528 cycles and 25,600 bit-compared output words. All Q/K/V copies and cumulative-gate/beta payloads matched the prior pinned scalar oracle. Total completed coverage: 51,200 words, including zero padding. Each chunk reset its cumulative state.

The four-case run stopped on its configured 160 CPU-second limit (SIGXCPU, exit -24; 166.27 wall seconds). Guarded-policy cases have no completed result. This is a PARTIAL result, not a passing entire test suite. Original executed harness is results/ExecutedLoadPrepCheck.scala, with source/fixture hashes in results/EXECUTED_SOURCE_HASHES.json. Generated fixture payload is intentionally excluded.

This is phase-1 unit-level simulation, not a full M128 model/block, RTL/hardware qualification, performance estimate, 4096-MAC resource proof or root publication. Full original-block acceptance remains 0/5. The prepared producer, derived/exp/matrix/solve/state phases, runtime32 layout, other heads, arbitration, stalled transports, error paths and full Host are not tested. Initial/previous-stage receipts are synthetic testbench prerequisites, not evidence those stages executed.

## Portable reproduction

Use Python 3 and Java 21. Provide locally obtained official Maven jars matching DEPENDENCIES.json. No network access occurs in the runner. Paths are recursive and repeatable:

    python run.py --jar-dir /path/to/jars --verify-only
    python run.py --jar-dir /path/to/jars

The default repeats the original four-case runtime16 test with the same 160 CPU / 200 wall second per-process bounds and 1,200 MB Java heap. A nonzero exit or timeout is not a pass. Run in a fresh copy to preserve archived results.

For future guarded runtime32-only coverage, avoiding repeating legacy cases:

    python run.py --jar-dir /path/to/jars --guarded32-only

The runtime32 option uses 51,200-byte rows, 16,384-byte role strides and 49,152-byte gate offsets. It is compile-checked only, NOT simulated. It still selects only head0. Original production sources are unchanged.

The fixture generator hashes the local scalar_core.py bytes before compile/exec and avoids importing potentially stale bytecode. It generates local Fixture.scala; its output was verified identical to the completed run. The generated fixture, classes, jars, FIRRTL and test directories must never be included in delivery.

## Dependency evidence

DEPENDENCIES.json is the merged desired official pin catalog, not a claim every jar was present. results/ACTUAL_DEPENDENCIES.json records the actual 32 used jars and five absent entries. The absent parser/ScalaTest jars did not block compilation or the two completed simulations. The no-network runner separately records used and absent jars. Missing jars may still prevent a different code path from running.

No network download was required; the exact local dependency subset is recorded. No Host job was launched, no old PID/reservation was modified and the original checkout was not changed.

The 30 pinned Scala compilation inputs comprise 29 complete original files plus PreparedReceiptExactExcerpt.scala, a compilation adapter containing the exact original receipt-class excerpt with package/import declarations added. The excerpt is not a complete original file; its original source hash and selection are recorded in SOURCE_PINS.json.

Final portable harness source compiled successfully after the runtime32 option was added (14.34 seconds). Only the earlier archived harness has the two completed numerical cases. Final run.py and generate_fixture.py passed Python syntax checks; the final fixture generator reproduced the exact executed fixture hash.
